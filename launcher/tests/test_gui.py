from pathlib import Path
import os
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, Qt

from bloodpsp_launcher.app import MainWindow, configure_application
from bloodpsp_launcher.controls import read_bindings
from test_core import make_pbp, make_game


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        configure_application(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        os.environ["BLOODPSP_LAUNCHER_STATE"] = str(Path(self.temp.name) / "state.ini")
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.original = self.window.doc.to_bytes()
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def test_default_state_and_all_options_available(self):
        w = self.window
        self.assertFalse(w.dirty)
        for index in range(7):
            w.nav.setCurrentIndex(index)
            self.app.processEvents()
            self.assertEqual(w.stack.currentIndex(), index)
        count = sum(w.tree.topLevelItem(i).childCount() for i in range(w.tree.topLevelItemCount()))
        self.assertEqual(count, len(w.doc.entries))

    def test_controls_change_actual_cfg_bindings(self):
        w = self.window
        combo = w.control_combos["cross"]
        combo.setCurrentIndex(combo.findData("Jump"))
        self.assertEqual(read_bindings(w.doc, "current")["cross"], ("Jump",))
        self.assertTrue(w.dirty)

    def test_visual_editor_updates_cfg_and_keeps_unknown_values(self):
        w = self.window
        w.doc.set("Additional", "Untouched", '"keep; this"')
        w.refresh()
        checkbox = w.fields[("Sound Setup", "MusicToggle")]
        checkbox.setChecked(False)
        self.assertEqual(w.doc.number("Sound Setup", "MusicToggle"), 0)
        self.assertEqual(w.doc.get("Additional", "Untouched"), '"keep; this"')
        w.resolution_combo.setCurrentIndex(1)
        self.assertEqual(w.doc.number("Screen Setup", "ScreenWidth"), 320)
        self.assertEqual(w.doc.number("Screen Setup", "ScreenHeight"), 200)

    def test_table_edit_updates_curated_field(self):
        w = self.window
        parent = next(w.tree.topLevelItem(i) for i in range(w.tree.topLevelItemCount()) if w.tree.topLevelItem(i).text(0) == "Sound Setup")
        item = next(parent.child(i) for i in range(parent.childCount()) if parent.child(i).text(0) == "MusicVolume")
        item.setText(1, "79")
        self.assertEqual(w.doc.number("Sound Setup", "MusicVolume"), 79)
        self.assertEqual(w.fields[("Sound Setup", "MusicVolume")].value(), 79)

    def test_installed_cfg_becomes_active_document(self):
        w = self.window
        target = Path(self.temp.name) / "game"
        target.mkdir()
        w.doc.set("Sound Setup", "MusicVolume", 80)
        (target / "nblood.cfg").write_bytes(w.doc.to_bytes())
        with patch("bloodpsp_launcher.app.QMessageBox.information"):
            w.install_finished({"target": str(target), "files": 27, "backup": None})
        self.assertEqual(w.config_path, (target / "nblood.cfg").resolve())
        self.assertFalse(w.dirty)

    def test_prepare_copies_ogg_and_maps_without_prompts(self):
        w = self.window
        root = Path(self.temp.name)
        source = make_game(root / "source")
        (source / "blood02.ogg").write_bytes(b"OggS-test")
        maps = source / "usermaps"
        maps.mkdir()
        (maps / "TEST.MAP").write_bytes(b"test map")
        w.accept_eboot(make_pbp(root / "EBOOT.PBP"))
        w.source_edit.setText(str(source))
        w.target_edit.setText(str(root / "output"))
        completed = []
        w.install_finished = lambda result: completed.append(result)
        w.prepare_install()
        deadline = time.monotonic() + 5
        while w.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(w.busy)
        self.assertEqual(len(completed), 1)
        self.assertEqual((w.target() / "music/blood02.ogg").read_bytes(), b"OggS-test")
        self.assertEqual((w.target() / "usermaps/TEST.MAP").read_bytes(), b"test map")

    def test_latest_release_download_chains_after_query(self):
        w = self.window
        pbp = make_pbp(Path(self.temp.name) / "EBOOT.PBP")
        asset = {"name": "EBOOT.PBP", "size": pbp.size}
        release = {"tag_name": "test", "download_assets": [asset]}
        with patch("bloodpsp_launcher.app.get_latest", return_value=release), patch("bloodpsp_launcher.app.download_asset", return_value=pbp) as download:
            w.query_release()
            deadline = time.monotonic() + 5
            while (w.busy or w.eboot is None) and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
            self.assertFalse(w.busy)
            self.assertEqual(w.eboot.sha256, pbp.sha256)
            download.assert_called_once()

    def test_visual_psp_buttons_select_actual_bindings(self):
        w = self.window
        w.nav.setCurrentIndex(1)
        self.app.processEvents()
        self.assertFalse(w.controller.artwork.isNull())
        with patch.object(w.control_combos["cross"], "showPopup") as popup:
            w.controller.buttons["cross"].click()
            popup.assert_called_once()
        self.assertEqual(w.controller.current, "cross")
        w.scheme_combo.setCurrentIndex(w.scheme_combo.findData("legacy"))
        self.assertIn("run", w.control_combos)
        self.assertEqual(w.scheme_combo.currentText(), "Standard 2")

    def test_background_completion_runs_on_gui_thread(self):
        w = self.window
        result = []
        w.start_task(lambda progress, cancelled: "done", lambda value: result.append((value, QThread.currentThread() == self.app.thread())), "Test")
        deadline = time.monotonic() + 5
        while w.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(w.busy)
        self.assertEqual(result, [("done", True)])
        self.assertTrue(w.stack.isEnabled())

    def test_background_error_reenables_interface(self):
        w = self.window
        errors = []
        def fail(progress, cancelled):
            raise ValueError("test failure")
        with patch.object(w, "show_error", side_effect=lambda title, message: errors.append(str(message))):
            w.start_task(fail, lambda result: None, "Test")
            deadline = time.monotonic() + 5
            while w.busy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
        self.assertEqual(errors, ["test failure"])
        self.assertFalse(w.busy)
        self.assertTrue(w.stack.isEnabled())


if __name__ == "__main__":
    unittest.main()
