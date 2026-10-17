"""GitHub Releases client: bounded downloads, digest and PBP validation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import hashlib
import json
import re
import struct
import tempfile
import urllib.error
import urllib.request
import zipfile

from .config import atomic_write

REPOSITORY = "RainArcanjo/BloodPSP"
USER_AGENT = "BloodPSP-Launcher/0.4.0"
MAX_DOWNLOAD = 128 * 1024 * 1024
KNOWN_LEGACY = {"5162eef05d7df54a639ce73f596ec3c6171aac3f86d66a71ea8b67d11a5320ae"}


class ReleaseError(ValueError):
    pass


@dataclass(frozen=True)
class PbpInfo:
    path: Path
    size: int
    sha256: str
    scheme: str
    ogg: bool
    native_controls: bool = False


def validate_pbp(path: Path) -> PbpInfo:
    size = path.stat().st_size
    if size < 44 or size > MAX_DOWNLOAD:
        raise ReleaseError("The EBOOT has an invalid size.")
    data = path.read_bytes()
    if data[:4] != b"\0PBP":
        raise ReleaseError("The selected file is not a valid EBOOT.PBP.")
    offsets = struct.unpack_from("<8I", data, 8)
    if offsets[0] < 40 or list(offsets) != sorted(offsets) or offsets[-1] > size:
        raise ReleaseError("The EBOOT structure is incomplete or corrupt.")
    if offsets[7] - offsets[6] < 4 or data[offsets[6]:offsets[6] + 4] not in (b"\x7fELF", b"~PSP"):
        raise ReleaseError("The EBOOT does not contain a recognized PSP executable.")
    digest = hashlib.sha256(data).hexdigest()
    ogg = b"bloodogg\0" in data and b"music/\0" in data
    has_wa59_audio = b"SOUNDFONT.SF2\0" in data
    scheme = "current" if digest not in KNOWN_LEGACY and (ogg or has_wa59_audio) else "legacy"
    return PbpInfo(path.resolve(), size, digest, scheme, ogg, b"BloodPSP.Controls.v1\0" in data)


def get_latest(repository: str = REPOSITORY) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ReleaseError("Use owner/repository format, e.g. RainArcanjo/BloodPSP.")
    request = urllib.request.Request(f"https://api.github.com/repos/{repository}/releases/latest",
                                     headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ReleaseError("The GitHub response exceeded the expected size.")
        release = json.loads(data)
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            raise ReleaseError("No public release found. Select a local EBOOT instead.") from ex
        if ex.code in (403, 429):
            raise ReleaseError("GitHub rate limit reached. Try later or select a local EBOOT.") from ex
        raise ReleaseError(f"GitHub returned HTTP {ex.code}.") from ex
    except (urllib.error.URLError, TimeoutError) as ex:
        raise ReleaseError("Could not connect to GitHub. Check your connection or select a local EBOOT.") from ex
    assets = [a for a in release.get("assets", []) if a.get("name", "").lower().endswith((".pbp", ".zip"))]
    assets.sort(key=lambda a: (a["name"].casefold() != "eboot.pbp", a["name"].lower().endswith(".zip"), a["name"]))
    if not assets:
        raise ReleaseError("The latest release has no EBOOT.PBP or ZIP package. Select a local EBOOT.")
    release["download_assets"] = assets
    return release


def download_asset(asset: dict, cache: Path, progress: Callable[[int, str], None], cancelled: Callable[[], bool] = lambda: False) -> PbpInfo:
    url = asset.get("browser_download_url", "")
    if not url.startswith("https://github.com/"):
        raise ReleaseError("The download URL does not belong to GitHub.")
    expected_size = int(asset.get("size", 0))
    if expected_size <= 0 or expected_size > MAX_DOWNLOAD:
        raise ReleaseError("The download size exceeds the 128 MiB limit.")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="download-", dir=cache) as temporary:
        downloaded = Path(temporary) / "asset"
        digest = hashlib.sha256()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response, downloaded.open("wb") as output:
                count = 0
                while block := response.read(128 * 1024):
                    if cancelled():
                        raise ReleaseError("Download cancelled.")
                    count += len(block)
                    if count > MAX_DOWNLOAD or count > expected_size:
                        raise ReleaseError("The download exceeded the size reported by GitHub.")
                    output.write(block)
                    digest.update(block)
                    progress(min(99, count * 100 // expected_size), "Downloading EBOOT from GitHub…")
        except (urllib.error.URLError, TimeoutError) as ex:
            raise ReleaseError("Download interrupted. No installation files were changed.") from ex
        if count != expected_size:
            raise ReleaseError("The download is incomplete. Try again.")
        expected_digest = asset.get("digest")
        if expected_digest and expected_digest != "sha256:" + digest.hexdigest():
            raise ReleaseError("The download hash does not match the GitHub digest.")
        pbp = downloaded
        if asset["name"].lower().endswith(".zip"):
            with zipfile.ZipFile(downloaded) as archive:
                candidates = [i for i in archive.infolist() if Path(i.filename).name.casefold() == "eboot.pbp" and not i.is_dir()]
                if len(candidates) != 1 or not 44 <= candidates[0].file_size <= MAX_DOWNLOAD:
                    raise ReleaseError("The ZIP must contain exactly one EBOOT.PBP with a valid size.")
                pbp = Path(temporary) / "EBOOT.PBP"
                with archive.open(candidates[0]) as stream, pbp.open("wb") as output:
                    count = 0
                    while block := stream.read(128 * 1024):
                        count += len(block)
                        if count > MAX_DOWNLOAD:
                            raise ReleaseError("The EBOOT in the ZIP exceeded the size limit.")
                        output.write(block)
        info = validate_pbp(pbp)
        destination = cache / f"EBOOT-{info.sha256}.PBP"
        atomic_write(destination, pbp.read_bytes())
    progress(100, "EBOOT downloaded and verified.")
    return validate_pbp(destination)
