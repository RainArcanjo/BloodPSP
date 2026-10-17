from pathlib import Path
import os
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox
from PySide6.QtCore import QThread, Qt

from bloodpsp_launcher.app import MainWindow, configure_application
from bloodpsp_launcher.controls import read_bindings
from test_core import make_pbp, make_game
from bloodpsp_launcher.capture import CaptureDialog
from bloodpsp_launcher.mappings import Mapping, read_mappings, write_mappings
from bloodpsp_launcher.controls import actions
from bloodpsp_launcher.config import ConfigDocument, fingerprint


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

    def test_bundled_eboot_is_selected_on_first_start(self):
        bundled = Path(self.temp.name) / "EBOOT.PBP"
        make_pbp(bundled, b"BloodPSP.Controls.v1\0")
        with patch("bloodpsp_launcher.app.sys.frozen", True, create=True), patch("bloodpsp_launcher.app.sys.executable", str(bundled.with_name("BloodPSPLauncher.exe"))):
            window = MainWindow()
        try:
            self.assertEqual(window.eboot.path, bundled)
            self.assertTrue(window.eboot.native_controls)
        finally:
            window.close()

    def test_remembered_eboot_takes_priority_over_bundled(self):
        bundled = Path(self.temp.name) / "EBOOT.PBP"
        selected = Path(self.temp.name) / "selected.PBP"
        make_pbp(bundled)
        make_pbp(selected, b"BloodPSP.Controls.v1\0")
        self.window.settings.setValue("eboot", str(selected))
        self.window.settings.sync()
        with patch("bloodpsp_launcher.app.sys.frozen", True, create=True), patch("bloodpsp_launcher.app.sys.executable", str(bundled.with_name("BloodPSPLauncher.exe"))):
            window = MainWindow()
        try:
            self.assertEqual(window.eboot.path, selected)
        finally:
            window.close()

    def test_controls_change_actual_cfg_bindings(self):
        w = self.window
        combo = w.control_combos["cross"]
        combo.setCurrentIndex(combo.findData("Jump"))
        self.assertEqual(read_bindings(w.doc, "current")["cross"], ("Jump",))
        self.assertTrue(w.dirty)

    def test_apply_controls_button_writes_active_cfg_and_confirms_save(self):
        w = self.window
        path = Path(self.temp.name) / "nblood.cfg"
        path.write_bytes(w.doc.to_bytes())
        w.config_path, w.config_hash = path, fingerprint(path)
        w.mutate(lambda doc: write_mappings(doc, [Mapping(("cross", "right"), "Jump")]))
        w.controls_editor.axis_scales[0].setValue(-32768)
        w.controls_editor.apply_button.click()
        saved = ConfigDocument.load(path)
        self.assertEqual(read_mappings(saved), [Mapping(("cross", "right"), "Jump")])
        self.assertEqual(saved.number("Controls", "JoystickAnalogScale0"), -32768)
        self.assertFalse(w.dirty)
        self.assertEqual(w.controls_editor.apply_status.text(), "Controls saved. Restart the game.")

    def test_cancelled_apply_does_not_claim_controls_were_saved(self):
        w = self.window
        with patch("bloodpsp_launcher.app.QFileDialog.getSaveFileName", return_value=("", "")):
            w.controls_editor.apply_button.click()
        self.assertIsNone(w.config_path)
        self.assertIsNone(w.controls_editor.applied_bytes)
        self.assertNotIn("Controls saved", w.controls_editor.apply_status.text())

    def test_apply_does_not_overwrite_external_changes_or_claim_success(self):
        w = self.window
        path = Path(self.temp.name) / "nblood.cfg"
        path.write_bytes(w.doc.to_bytes())
        w.config_path, w.config_hash = path, fingerprint(path)
        external = w.doc.clone()
        external.set("Sound Setup", "MusicVolume", 19)
        path.write_bytes(external.to_bytes())
        with patch.object(w, "show_error"):
            w.controls_editor.apply_button.click()
        self.assertEqual(path.read_bytes(), external.to_bytes())
        self.assertIsNone(w.controls_editor.applied_bytes)
        self.assertNotIn("Controls saved", w.controls_editor.apply_status.text())

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
        w.controller.buttons["cross"].click()
        selected = w.controls_editor.table.currentRow()
        self.assertEqual(w.controls_editor.mappings[selected].buttons, ("cross",))
        self.assertEqual(w.controller.current, "cross")
        w.scheme_combo.setCurrentIndex(w.scheme_combo.findData("legacy"))
        self.assertTrue(any(m.buttons == ("square", "l") for m in w.controls_editor.mappings))
        self.assertEqual(w.scheme_combo.currentText(), "Standard 2")

    def test_resolution_list_does_not_duplicate_on_edits(self):
        w = self.window
        for volume in range(100, 130):
            w.set_value("Sound Setup", "MusicVolume", volume)
        self.assertEqual(w.resolution_combo.count(), 2)
        self.assertEqual(w.resolution_combo.currentText(), "480 × 272 (PSP native)")
        w.resolution_combo.setCurrentIndex(1)
        w.refresh()
        self.assertEqual(w.resolution_combo.count(), 2)
        self.assertEqual(w.doc.number("Screen Setup", "ScreenWidth"), 320)

    def test_trash_removes_mapping_and_saved_cfg_reopens_with_combo(self):
        w = self.window
        panel = w.controls_editor
        first = panel.mappings[0]
        panel.table.cellWidget(0, 2).click()
        self.assertNotIn(first, read_mappings(w.doc))
        mappings = [*read_mappings(w.doc), Mapping(("cross", "r"), "Jump")]
        w.mutate(lambda doc: write_mappings(doc, mappings))
        cfg = Path(self.temp.name) / "nblood.cfg"
        w.config_path = cfg
        w.config_hash = None
        self.assertTrue(w.save_config())
        w.load_config(cfg)
        self.assertIn(Mapping(("cross", "r"), "Jump"), read_mappings(w.doc))
        self.assertFalse(w.dirty)

    def test_profile_saved_and_loaded_in_editor(self):
        w = self.window
        panel = w.controls_editor
        w.mutate(lambda doc: write_mappings(doc, [Mapping(("cross", "r"), "Jump")]))
        with patch("bloodpsp_launcher.controls_editor.QInputDialog.getText", return_value=("Rain", True)):
            panel.save_profile()
        w.mutate(lambda doc: write_mappings(doc, []))
        panel.profile_combo.setCurrentIndex(0)
        panel.profile_combo.setCurrentIndex(panel.profile_combo.findData("Rain"))
        self.assertEqual(read_mappings(w.doc), [])
        panel.load_profile_button.click()
        self.assertEqual(read_mappings(w.doc), [Mapping(("cross", "r"), "Jump")])

    def test_reload_selected_preset_restores_analog_settings(self):
        w = self.window
        panel = w.controls_editor
        with patch("bloodpsp_launcher.controls_editor.QInputDialog.getText", return_value=("Rain", True)):
            panel.save_profile()
        original = w.doc.number("Controls", "JoystickAnalogScale0")
        panel.axis_scales[0].setValue(-32768)
        self.assertEqual(w.doc.number("Controls", "JoystickAnalogScale0"), -32768)
        self.assertEqual(panel.profile_combo.currentData(), "Rain")
        panel.load_profile_button.click()
        self.assertEqual(w.doc.number("Controls", "JoystickAnalogScale0"), original)

    def test_mapping_cells_supply_button_icons_and_accessible_names(self):
        w = self.window
        w.mutate(lambda doc: write_mappings(doc, [Mapping(("cross", "right"), "Jump")]))
        w.nav.setCurrentIndex(1)
        self.app.processEvents()
        item = w.controls_editor.table.item(0, 0)
        self.assertEqual(item.data(Qt.ItemDataRole.UserRole), ["cross", "right"])
        self.assertEqual(item.toolTip(), "Cross + Right")
        self.assertEqual(w.controls_editor.table.itemDelegateForColumn(0).__class__.__name__, "ChordDelegate")

    def test_loading_smaller_preset_leaves_no_overlapping_action_editors(self):
        w = self.window
        w.nav.setCurrentIndex(1)
        for mappings in ([Mapping(("cross",), "Jump"), Mapping(("right",), "Open")], [Mapping(("cross", "right"), "Jump")]):
            w.mutate(lambda doc: write_mappings(doc, mappings))
            self.app.processEvents()
        table = w.controls_editor.table
        visible_combos = [c for c in table.findChildren(QComboBox) if c.isVisible()]
        self.assertEqual(len(visible_combos), 1)
        self.assertIs(visible_combos[0], table.cellWidget(0, 1))
        self.assertGreaterEqual(visible_combos[0].geometry().left(), table.columnViewportPosition(1))

    def test_capture_dialog_confirms_after_release_grace_period(self):
        class Reader:
            name = "PS4 Controller"
            pressed = set()
            closed = False
            def poll(self): return self.pressed
            def close(self): self.closed = True
        reader = Reader()
        dialog = CaptureDialog(actions(self.window.doc), reader=reader)
        dialog.timer.stop()
        with patch("bloodpsp_launcher.capture.time.monotonic") as now:
            for timestamp, pressed in [(0, set()), (.01, {'cross'}), (.05, {'cross', 'r'}), (.1, {'r'}), (.2, set()), (.399, set())]:
                now.return_value = timestamp
                reader.pressed = pressed
                dialog.poll()
                self.assertIsNone(dialog.mapping)
            now.return_value = .401
            dialog.poll()
        self.assertEqual(dialog.mapping, Mapping(("cross", "r"), "Jump"))
        self.assertTrue(reader.closed)

    def test_cancelled_capture_does_not_add_mapping(self):
        class Reader:
            name = "PS4 Controller"
            closed = False
            def poll(self): return set()
            def close(self): self.closed = True
        before = self.window.doc.to_bytes()
        reader = Reader()
        dialog = CaptureDialog(actions(self.window.doc), reader=reader)
        dialog.reject()
        self.assertIsNone(dialog.mapping)
        self.assertTrue(reader.closed)
        self.assertEqual(self.window.doc.to_bytes(), before)

    def test_invalid_native_table_edit_leaves_document_unchanged(self):
        w = self.window
        w.mutate(lambda doc: write_mappings(doc, [Mapping(("cross",), "Jump")]))
        before = w.doc.to_bytes()
        with patch("bloodpsp_launcher.app.QMessageBox.warning"):
            w.set_value("PSP Controls", "Count", 99)
        self.assertEqual(w.doc.to_bytes(), before)

    def test_last_saved_cfg_is_restored_on_next_launch(self):
        w = self.window
        w.set_value("Sound Setup", "MusicVolume", 17)
        path = Path(self.temp.name) / "nblood.cfg"
        w.config_path, w.config_hash = path, None
        self.assertTrue(w.save_config())
        w.settings.sync()
        second = MainWindow()
        try:
            self.assertEqual(second.config_path, path.resolve())
            self.assertEqual(second.doc.number("Sound Setup", "MusicVolume"), 17)
            self.assertFalse(second.dirty)
        finally:
            second.close()

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
