"""Frozen-executable smoke check, also used to generate UI review images."""
from pathlib import Path
import json
import os
import sys


def main(output: str) -> int:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    os.environ["BLOODPSP_LAUNCHER_STATE"] = str(destination / "state.ini")
    from PySide6.QtWidgets import QApplication
    from .app import MainWindow, configure_application
    from .controls import read_bindings
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    window = MainWindow()
    window.apply_theme("dark")
    window.show()
    app.processEvents()
    assert not window.dirty
    assert not window.header_logo.pixmap().isNull()
    assert not window.controller.artwork.isNull()
    from .widgets import button_icon
    from .controls import SCHEME_LABELS
    for name in window.controller.buttons:
        assert not button_icon(name).pixmap(24, 24).isNull(), name
    assert list(SCHEME_LABELS.values()) == ["Standard 1", "Standard 2"]
    for index, name in ((0, "installation"), (1, "controls"), (2, "video"), (3, "audio"), (5, "all-options")):
        window.nav.setCurrentIndex(index)
        app.processEvents()
        window.grab().save(str(destination / f"{name}.png"))
    window.apply_theme("light")
    window.nav.setCurrentIndex(1)
    app.processEvents()
    window.grab().save(str(destination / "controls-light.png"))
    combo = window.control_combos["cross"]
    combo.setCurrentIndex(combo.findData("Jump"))
    assert read_bindings(window.doc, "current")["cross"] == ("Jump",)
    assert window.dirty
    from .capture import CaptureDialog
    from .controls import actions
    dialog = CaptureDialog(actions(window.doc), parent=window)
    dialog.timer.stop()
    assert dialog.reader is not None, "SDL controller backend unavailable"
    dialog.poll()
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(destination / "map-button.png"))
    backend_name = dialog.reader.name
    dialog.reject()
    report = {"passed": True, "frozen": bool(getattr(sys, "frozen", False)), "cfg_entries": len(window.doc.entries),
              "pages": window.stack.count(), "control_remapping": "cross -> Jump", "qt_platform": app.platformName(),
              "controller_backend": True, "controller": backend_name}
    if os.environ.get("BLOODPSP_SMOKE_DOWNLOAD") == "1":
        from .releases import get_latest, download_asset
        release = get_latest()
        pbp = download_asset(release["download_assets"][0], destination / "download-cache", lambda *args: None)
        report["github_release"] = release["tag_name"]
        report["download_sha256"] = pbp.sha256
    (destination / "smoke-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    window.original = window.doc.to_bytes()
    window.close()
    return 0
