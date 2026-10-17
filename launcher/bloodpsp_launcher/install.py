"""Build PSP/GAME/BloodPSP without consuming the user's original game.

Stage and validate the entire update first. Replace only managed files, keep
backups of changed files, and roll back if any replacement fails. Saves and
unrelated files are never part of the replacement list.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
import hashlib
import json
import os
import shutil
import tempfile

from .config import ConfigDocument, fingerprint
from .releases import PbpInfo, validate_pbp
from . import __version__
from .mappings import has_native_mappings, read_mappings

REQUIRED = ("BLOOD.INI", "BLOOD.RFF", "GUI.RFF", "SOUNDS.RFF", "SURFACE.DAT", "TABLES.DAT",
            *(f"TILES{i:03}.ART" for i in range(18)), "VOXEL.DAT")


class InstallError(ValueError):
    pass


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def directory_index(path: Path) -> dict[str, Path]:
    if not path.is_dir():
        raise InstallError("Select the folder containing the game files.")
    result = {}
    for child in path.iterdir():
        if child.is_file() and not is_link(child):
            name = child.name.casefold()
            if name in result:
                raise InstallError(f"Two files have the same name: {child.name}")
            result[name] = child
    return result


def scan_game(path: Path) -> dict[str, Path | None]:
    index = directory_index(path)
    return {name: index.get(name.casefold()) for name in REQUIRED}


def game_destination(selected: Path) -> Path:
    if selected.name.casefold() == "bloodpsp" and selected.parent.name.casefold() == "game" and selected.parent.parent.name.casefold() == "psp":
        return selected
    if selected.name.casefold() == "game" and selected.parent.name.casefold() == "psp":
        return selected / "BloodPSP"
    if selected.name.casefold() == "psp":
        return selected / "GAME" / "BloodPSP"
    return selected / "PSP" / "GAME" / "BloodPSP"


def optional_files(source: Path, music: bool, maps: bool) -> list[tuple[Path, Path]]:
    result = []
    if music:
        for name in [f"blood{i:02}.ogg" for i in range(2, 10)]:
            for parent in (source / "music", source):
                if not parent.is_dir() or is_link(parent):
                    continue
                candidate = directory_index(parent).get(name)
                if candidate:
                    with candidate.open("rb") as handle:
                        if handle.read(4) != b"OggS":
                            raise InstallError(f"{candidate.name} does not have a valid OGG signature.")
                    result.append((candidate, Path("music") / name))
                    break
    folder = source / "usermaps"
    if maps and folder.is_dir() and not is_link(folder):
        for parent, dirs, files in os.walk(folder, followlinks=False):
            dirs[:] = [d for d in dirs if not is_link(Path(parent) / d)]
            index = {f.casefold(): Path(parent) / f for f in files if not is_link(Path(parent) / f)}
            for name, candidate in index.items():
                if candidate.suffix.casefold() != ".map":
                    continue
                result.append((candidate, Path("usermaps") / candidate.relative_to(folder)))
                description = index.get(candidate.with_suffix(".def").name.casefold())
                if description:
                    result.append((description, Path("usermaps") / description.relative_to(folder)))
    return result


@dataclass(frozen=True)
class InstallPlan:
    source: Path
    target: Path
    eboot: PbpInfo
    config: bytes | None
    config_expected_hash: str | None
    music: bool = True
    maps: bool = True


def checked_output(target: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise InstallError("The package contains an invalid output path.")
    path = target / relative
    for parent in [path, *path.parents]:
        if is_link(parent):
            raise InstallError(f"The output contains a link or junction: {parent}")
        if parent == target.parent:
            break
    if not path.resolve().is_relative_to(target.resolve()):
        raise InstallError("A file would escape the output folder.")
    return path


def install(plan: InstallPlan, progress: Callable[[int, str], None], cancelled: Callable[[], bool] = lambda: False) -> dict:
    files = scan_game(plan.source)
    missing = [name for name, path in files.items() if path is None]
    if missing:
        raise InstallError("Missing required files: " + ", ".join(missing))
    info = validate_pbp(plan.eboot.path)
    if info.sha256 != plan.eboot.sha256:
        raise InstallError("The EBOOT changed after selection. Select it again.")
    if plan.config is not None:
        document = ConfigDocument(plan.config)
        if has_native_mappings(document):
            read_mappings(document, info.scheme)
            if not info.native_controls:
                raise InstallError("This EBOOT cannot read custom mappings. Select the updated EBOOT-controls.PBP.")
    target = plan.target.absolute()
    if target.exists() and not target.is_dir():
        raise InstallError("The output must be a folder.")
    # Refuse reparse points in every existing ancestor, including a card-root
    # selection, so staging and backups stay on the same intended filesystem.
    for ancestor in [target, *target.parents]:
        if is_link(ancestor):
            raise InstallError(f"The output contains a link or junction: {ancestor}")
    copies = [(info.path, Path("EBOOT.PBP"))]
    copies += [(path, Path(name)) for name, path in files.items() if path]
    copies += optional_files(plan.source, plan.music, plan.maps)
    destinations = [str(relative).casefold() for _, relative in copies]
    if len(destinations) != len(set(destinations)):
        raise InstallError("The package contains duplicate filenames.")
    for source, relative in copies:
        checked_output(target, relative)
        if source.stat().st_size <= 0:
            raise InstallError(f"The file {source.name} is empty.")
        if source.suffix.casefold() == ".rff":
            with source.open("rb") as stream:
                if stream.read(4) != b"RFF\x1a":
                    raise InstallError(f"{source.name} is not a valid RFF file.")
    total = sum(source.stat().st_size for source, _ in copies)
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(target.parent).free < total + 4 * 1024 * 1024:
        raise InstallError("Not enough space to build the installation and preserve existing files.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = target.parent / ".bloodpsp-backups" / stamp
    if not backup.resolve().is_relative_to(target.parent.resolve()):
        raise InstallError("The backup folder points outside the output.")
    changes: list[tuple[Path, Path | None]] = []
    records = []
    copied = 0
    stage = Path(tempfile.mkdtemp(prefix=".bloodpsp-stage-", dir=target.parent))
    try:
        for source, relative in copies:
            if cancelled():
                raise InstallError("Installation cancelled. Previous files preserved.")
            output = stage / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with source.open("rb") as stream, output.open("wb") as handle:
                while block := stream.read(256 * 1024):
                    if cancelled():
                        raise InstallError("Installation cancelled. Previous files preserved.")
                    handle.write(block)
                    digest.update(block)
                    copied += len(block)
                    progress(min(88, copied * 88 // max(1, total)), f"Preparing {relative.as_posix()}")
            records.append({"path": relative.as_posix(), "sha256": digest.hexdigest(), "size": output.stat().st_size})
        if validate_pbp(stage / "EBOOT.PBP").sha256 != info.sha256:
            raise InstallError("The EBOOT changed while copying. No files were installed.")
        if plan.config is not None:
            (stage / "nblood.cfg").write_bytes(plan.config)
            records.append({"path": "nblood.cfg", "sha256": hashlib.sha256(plan.config).hexdigest(), "size": len(plan.config)})
        manifest = {"launcher_version": __version__, "installed_at": datetime.now().astimezone().isoformat(),
                    "eboot_sha256": info.sha256, "control_scheme": info.scheme, "files": records}
        (stage / ".bloodpsp-install.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged = [stage / record["path"] for record in records] + [stage / ".bloodpsp-install.json"]
        if plan.config is not None and fingerprint(target / "nblood.cfg") != plan.config_expected_hash:
            raise InstallError("The output CFG changed during preparation. Installation cancelled to preserve it.")
        for index, source in enumerate(staged):
            if cancelled():
                raise InstallError("Installation cancelled. Restoring previous files.")
            relative = source.relative_to(stage)
            output = checked_output(target, relative)
            if output.exists() and fingerprint(output) == fingerprint(source):
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            old = None
            if output.exists():
                if not output.is_file():
                    raise InstallError(f"A folder already occupies the name {relative}.")
                old = backup / relative
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output, old)
            # Record before os.replace so either failure path restores safely.
            changes.append((output, old))
            os.replace(source, output)
            progress(89 + index * 10 // len(staged), f"Installing {relative.as_posix()}")
        for folder in ("music", "usermaps"):
            checked_output(target, Path(folder)).mkdir(exist_ok=True)
        progress(100, "PSP folder ready.")
        return {"target": str(target), "files": len(records), "backup": str(backup) if backup.exists() else None,
                "eboot_sha256": info.sha256, "changed_files": len(changes)}
    except BaseException:
        for output, old in reversed(changes):
            if old and old.exists():
                os.replace(old, output)
            else:
                output.unlink(missing_ok=True)
        raise
    finally:
        # Only the freshly allocated, verified staging directory is removed.
        assert stage.parent.resolve() == target.parent.resolve() and stage.name.startswith(".bloodpsp-stage-")
        shutil.rmtree(stage)
