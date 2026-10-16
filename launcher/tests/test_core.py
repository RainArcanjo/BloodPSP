from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib
import json
import os
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

from bloodpsp_launcher.config import ConfigDocument, ConfigError, fingerprint, tokens, quote
from bloodpsp_launcher.controls import bind_button, read_bindings, reset_bindings
from bloodpsp_launcher.install import REQUIRED, InstallPlan, InstallError, game_destination, install, optional_files, scan_game
from bloodpsp_launcher.releases import ReleaseError, validate_pbp, get_latest, download_asset
from bloodpsp_launcher.resources import default_document


def make_pbp(path: Path, marker: bytes = b"bloodogg\0music/\0"):
    payload = b"\x7fELF" + marker
    data = b"\0PBP" + struct.pack("<I8I", 0x10000, 40, 44, 44, 44, 44, 44, 44, 44 + len(payload)) + b"SFO!" + payload
    path.write_bytes(data)
    return validate_pbp(path)


def make_game(path: Path):
    path.mkdir()
    for name in REQUIRED:
        prefix = b"RFF\x1a" if name.endswith(".RFF") else b"game-data-"
        (path / name).write_bytes(prefix + name.encode())
    return path


def hashes(folder: Path):
    return {str(p.relative_to(folder)): fingerprint(p) for p in folder.rglob("*") if p.is_file()}


class ConfigTests(unittest.TestCase):
    def test_templates_roundtrip_and_physical_controls(self):
        for scheme in ("current", "legacy"):
            doc = default_document(scheme)
            self.assertEqual(doc.to_bytes(), doc.clone().to_bytes())
            self.assertTrue(all(read_bindings(doc, scheme).values()))

    def test_comments_crlf_quotes_and_unknown_options_survive(self):
        data = b'; keep this\r\n[KeyDefinitions]\r\nPrevious_Weapon = ";" ""  ; binding\r\n[Unknown]\r\nMyValue = "a; b"\r\n'
        doc = ConfigDocument(data)
        self.assertEqual(doc.to_bytes(), data)
        doc.set("keydefinitions", "Previous_Weapon", '"X" ""')
        self.assertEqual(doc.to_bytes(), data.replace(b'";" ""', b'"X" ""'))
        self.assertEqual(tokens(doc.get("Unknown", "MyValue")), ["a; b"])

    def test_bom_and_windows_1252_preserved(self):
        for data in (b'\xef\xbb\xbf[X]\nName = "Ol\xc3\xa1"\n', b'[X]\r\nName = "Ol\xe1"\r\n'):
            doc = ConfigDocument(data)
            self.assertEqual(doc.to_bytes(), data)
            doc.set("X", "Other", "1")
            self.assertIn(data, doc.to_bytes())

    def test_invalid_and_duplicate_values_rejected(self):
        for raw in (b"X = 1", b"[X]\nA = 1\nA = 2\n", b'[X]\nA = "unterminated\n'):
            with self.assertRaises(ConfigError):
                ConfigDocument(raw)
        doc = ConfigDocument(b"[X]\nA = 1\n")
        with self.assertRaises(ConfigError):
            doc.set("X", "A", "1\nB = 2")

    def test_key_string_escape_semantics(self):
        for value in ('; "hello"', "a\\b", "line\nnext", "Tab", ""):
            self.assertEqual(tokens(quote(value)), [value])

    def test_save_backup_and_external_edit_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nblood.cfg"
            old = b"[X]\r\nA = 1\r\n"
            path.write_bytes(old)
            doc = ConfigDocument(old)
            before = fingerprint(path)
            doc.set("X", "A", 2)
            backup = doc.save(path, before)
            self.assertEqual(backup.read_bytes(), old)
            self.assertIn(b"A = 2", path.read_bytes())
            path.write_bytes(old)
            with self.assertRaises(ConfigError):
                doc.save(path, "stale-hash")
            self.assertEqual(path.read_bytes(), old)

    def test_remapping_uses_current_keyboard_path(self):
        doc = default_document()
        bind_button(doc, "current", "cross", "Jump")
        self.assertEqual(read_bindings(doc, "current")["cross"], ("Jump",))
        self.assertNotIn("RCtrl", tokens(doc.get("KeyDefinitions", "Weapon_Fire")))
        self.assertIn("Space", tokens(doc.get("KeyDefinitions", "Jump")))

    def test_legacy_aliases_cannot_trigger_previous_action(self):
        doc = default_document("legacy")
        bind_button(doc, "legacy", "up", "Weapon_Fire")
        self.assertNotIn("W", tokens(doc.get("KeyDefinitions", "Move_Forward")))
        self.assertNotIn("Up", tokens(doc.get("KeyDefinitions", "Move_Forward")))
        self.assertEqual(read_bindings(doc, "legacy")["up"], ("Weapon_Fire",))

    def test_full_binding_failure_is_atomic(self):
        doc = default_document()
        doc.set("KeyDefinitions", "Jump", '"Space" "E"')
        before = doc.to_bytes()
        with self.assertRaises(ConfigError):
            bind_button(doc, "current", "cross", "Jump")
        self.assertEqual(doc.to_bytes(), before)

    def test_reset_does_not_reset_graphics(self):
        doc = default_document()
        doc.set("Screen Setup", "Gamma", 5)
        bind_button(doc, "current", "cross", "Jump")
        reset_bindings(doc, default_document())
        self.assertEqual(read_bindings(doc, "current")["cross"], ("Weapon_Fire",))
        self.assertEqual(doc.number("Screen Setup", "Gamma"), 5)


class ReleaseTests(unittest.TestCase):
    def test_pbp_structure_and_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "game.pbp"
            self.assertTrue(make_pbp(path).ogg)
            self.assertEqual(make_pbp(path, b"old").scheme, "legacy")
            midi_only = make_pbp(path, b"SOUNDFONT.SF2\0")
            self.assertEqual(midi_only.scheme, "current")
            self.assertFalse(midi_only.ogg)
            path.write_bytes(b"MZ" + b"x" * 100)
            with self.assertRaises(ReleaseError):
                validate_pbp(path)
            make_pbp(path)
            raw = bytearray(path.read_bytes())
            struct.pack_into("<I", raw, 32, 999999)
            path.write_bytes(raw)
            with self.assertRaises(ReleaseError):
                validate_pbp(path)

    def test_release_api_errors_and_repository_validation(self):
        with self.assertRaises(ReleaseError):
            get_latest("../../bad")
        for status in (403, 404, 429):
            with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://github.com", status, "test", None, None)):
                with self.assertRaises(ReleaseError):
                    get_latest()

    def test_pbp_preferred_to_zip(self):
        release = {"assets": [{"name": "bundle.zip"}, {"name": "other.pbp"}, {"name": "EBOOT.PBP"}]}
        with patch("urllib.request.urlopen", return_value=BytesIO(json.dumps(release).encode())):
            self.assertEqual(get_latest()["download_assets"][0]["name"], "EBOOT.PBP")

    def test_download_checks_digest_and_size(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            info = make_pbp(root / "valid.pbp")
            data = info.path.read_bytes()
            asset = {"name": "EBOOT.PBP", "size": len(data), "digest": "sha256:" + info.sha256,
                     "browser_download_url": "https://github.com/owner/repo/releases/download/test/EBOOT.PBP"}
            with patch("urllib.request.urlopen", return_value=BytesIO(data)):
                copied = download_asset(asset, root / "cache", lambda *args: None)
            self.assertEqual(copied.sha256, info.sha256)
            with patch("urllib.request.urlopen", return_value=BytesIO(data[:-2])):
                with self.assertRaises(ReleaseError):
                    download_asset(asset, root / "bad", lambda *args: None)
            with patch("urllib.request.urlopen", return_value=BytesIO(data)):
                with self.assertRaises(ReleaseError):
                    download_asset(dict(asset, digest="sha256:wrong"), root / "bad", lambda *args: None)
            self.assertFalse(list((root / "bad").glob("*.PBP")))

    def test_zip_does_not_extract_arbitrary_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = make_pbp(root / "valid.pbp").path.read_bytes()
            stream = BytesIO()
            with zipfile.ZipFile(stream, "w") as z:
                z.writestr("../../outside.txt", "do not extract")
                z.writestr("package/EBOOT.PBP", data)
            raw = stream.getvalue()
            asset = {"name": "game.zip", "size": len(raw), "browser_download_url": "https://github.com/test/repo/releases/download/x/game.zip"}
            with patch("urllib.request.urlopen", return_value=BytesIO(raw)):
                result = download_asset(asset, root / "cache", lambda *args: None)
            self.assertEqual(result.path.read_bytes(), data)
            self.assertFalse((root.parent / "outside.txt").exists())


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = make_game(self.root / "source")
        self.eboot = make_pbp(self.root / "EBOOT.PBP")
        self.target = game_destination(self.root / "card")
        self.plan = InstallPlan(self.source, self.target, self.eboot, default_document().to_bytes(), None)

    def tearDown(self):
        self.temp.cleanup()

    def run_install(self, plan=None, progress=lambda *args: None, cancelled=lambda: False):
        return install(plan or self.plan, progress, cancelled)

    def test_destination_accepts_card_psp_game_and_game_folder(self):
        for path in (self.root / "card", self.root / "card/PSP", self.root / "card/PSP/GAME", self.target):
            self.assertEqual(game_destination(path), self.target)

    def test_case_insensitive_required_files(self):
        (self.source / "BLOOD.INI").rename(self.source / "blood.ini")
        self.assertTrue(all(scan_game(self.source).values()))

    def test_only_game_assets_and_allowed_optional_files_are_copied(self):
        (self.source / "blood02.ogg").write_bytes(b"OggS-test")
        (self.source / "BLOOD.EXE").write_bytes(b"do not copy")
        maps = self.source / "usermaps/subfolder"
        maps.mkdir(parents=True)
        (maps / "TEST.MAP").write_bytes(b"map")
        (maps / "test.def").write_bytes(b"description")
        (maps / "TEST.BAK").write_bytes(b"backup")
        before = hashes(self.source)
        result = self.run_install()
        self.assertEqual(result["files"], 30)
        self.assertTrue((self.target / "music/blood02.ogg").is_file())
        self.assertTrue((self.target / "usermaps/subfolder/TEST.MAP").is_file())
        self.assertTrue((self.target / "usermaps/subfolder/test.def").is_file())
        self.assertFalse((self.target / "BLOOD.EXE").exists())
        self.assertFalse(list(self.target.rglob("*.BAK")))
        self.assertEqual(before, hashes(self.source))

    def test_missing_assets_leave_existing_installation_intact(self):
        self.run_install()
        before = hashes(self.target)
        (self.source / "TABLES.DAT").unlink()
        with self.assertRaises(InstallError):
            self.run_install()
        self.assertEqual(before, hashes(self.target))

    def test_update_backs_up_eboot_and_preserves_cfg_and_saves(self):
        self.run_install()
        save = self.target / "game0000.sav"
        save.write_bytes(b"USER SAVE")
        old_eboot = (self.target / "EBOOT.PBP").read_bytes()
        old_cfg = (self.target / "nblood.cfg").read_bytes()
        other = make_pbp(self.root / "updated.pbp", b"bloodogg\0music/\0-new")
        result = self.run_install(InstallPlan(self.source, self.target, other, None, None))
        self.assertEqual(save.read_bytes(), b"USER SAVE")
        self.assertEqual((self.target / "nblood.cfg").read_bytes(), old_cfg)
        self.assertEqual((Path(result["backup"]) / "EBOOT.PBP").read_bytes(), old_eboot)

    def test_io_failure_rolls_back_completed_replacements(self):
        self.run_install()
        before = hashes(self.target)
        new = make_pbp(self.root / "updated.pbp", b"new")
        (self.source / "BLOOD.RFF").write_bytes(b"RFF\x1a-new")
        real_replace = os.replace
        failed = False
        def fail_once(src, dest):
            nonlocal failed
            if Path(dest).name == "BLOOD.RFF" and ".bloodpsp-stage-" in str(src) and not failed:
                failed = True
                raise OSError("simulated USB disconnect")
            return real_replace(src, dest)
        with patch("bloodpsp_launcher.install.os.replace", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.run_install(InstallPlan(self.source, self.target, new, None, None))
        self.assertTrue(failed)
        self.assertEqual(before, hashes(self.target))

    def test_cancellation_during_commit_rolls_back(self):
        self.run_install()
        before = hashes(self.target)
        new = make_pbp(self.root / "updated.pbp", b"new")
        stop = threading.Event()
        with self.assertRaises(InstallError):
            self.run_install(InstallPlan(self.source, self.target, new, None, None),
                             lambda value, message: stop.set() if value >= 89 else None, stop.is_set)
        self.assertEqual(before, hashes(self.target))

    def test_cfg_external_edit_during_staging_is_preserved(self):
        self.run_install()
        expected = fingerprint(self.target / "nblood.cfg")
        changed = False
        def update(value, message):
            nonlocal changed
            if not changed:
                (self.target / "nblood.cfg").write_bytes(b"[External]\nEdit = 1\n")
                changed = True
        plan = InstallPlan(self.source, self.target, self.eboot, self.plan.config, expected)
        with self.assertRaises(InstallError):
            self.run_install(plan, update)
        self.assertEqual((self.target / "nblood.cfg").read_bytes(), b"[External]\nEdit = 1\n")


if __name__ == "__main__":
    unittest.main()
