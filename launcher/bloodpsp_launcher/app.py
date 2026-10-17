from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import os
import sys
import threading
import traceback

from PySide6.QtCore import Qt, Signal, Slot, QObject, QThread, QSettings, QStandardPaths, QUrl, QTimer
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QPalette, QColor, QFont, QFontDatabase, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QSlider, QGroupBox, QFileDialog, QMessageBox, QStackedWidget,
    QFrame, QScrollArea, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QProgressBar, QTextEdit, QDockWidget, QDialog, QDialogButtonBox, QTabBar,
)

from . import __version__
from .config import ConfigDocument, ConfigError, fingerprint, quote, tokens
from .controls import SCHEMES, SCHEME_LABELS, ACTION_LABELS
from .install import scan_game, game_destination, InstallPlan, install
from .releases import REPOSITORY, get_latest, download_asset, validate_pbp, PbpInfo
from .resources import default_document, resource
from .schema import VIDEO, AUDIO, GAME, ALL_FIELDS, BOOLEAN_FIELDS, DESCRIPTIONS
from .widgets import icon, label, ValueDelegate
from .controls_editor import ControlsEditor
from .profiles import ProfileStore
from .mappings import has_native_mappings, read_mappings


class Worker(QObject):
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, function, cancel: threading.Event):
        super().__init__()
        self.function = function
        self.cancel = cancel

    @Slot()
    def run(self):
        try:
            self.done.emit(self.function(self.progress.emit, self.cancel.is_set))
        except Exception as ex:
            self.failed.emit(str(ex), traceback.format_exc())
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        settings_path = os.environ.get("BLOODPSP_LAUNCHER_STATE")
        self.settings = QSettings(settings_path, QSettings.Format.IniFormat) if settings_path else QSettings("BloodPSP", "Launcher")
        appdata = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        self.cache = appdata / "downloads"
        self.log_path = appdata / "launcher.log"
        self.profile_store = ProfileStore(Path(settings_path).parent / "profiles.json" if settings_path else appdata / "profiles.json")
        self.doc = default_document()
        self.original = self.doc.to_bytes()
        self.config_path: Path | None = None
        self.config_hash = None
        self.eboot: PbpInfo | None = None
        self.release: dict | None = None
        self.scheme = "current"
        self.refreshing = True
        self.busy = False
        self.close_pending = False
        self.cancel = threading.Event()
        self.thread = None
        self.worker = None
        self.fields = {}
        self.control_combos = {}
        self.setWindowTitle("BloodPSP Launcher")
        self.setWindowIcon(icon("blood", size=128))
        self.resize(1080, 860)
        self.setMinimumSize(900, 680)
        self._build_actions()
        self._build_shell()
        self._build_install_page()
        self._build_controls_page()
        self._build_video_page()
        self._build_audio_page()
        self._build_game_page()
        self._build_advanced_page()
        self._build_about_page()
        self._build_log()
        self.apply_theme(str(self.settings.value("theme", "dark")))
        self.nav.setCurrentIndex(0)
        self.refreshing = False
        self.refresh()
        self.update_destination()
        self.scan_source()
        remembered = str(self.settings.value("eboot", ""))
        bundled = Path(sys.executable).parent / "EBOOT.PBP" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent / "EBOOT.PBP"
        for candidate in (Path(remembered) if remembered else None, bundled):
            if candidate is None or not candidate.is_file():
                continue
            try:
                self.accept_eboot(validate_pbp(candidate))
                break
            except Exception:
                pass
        remembered_cfg = str(self.settings.value("config", ""))
        if remembered_cfg and Path(remembered_cfg).is_file():
            self.load_config(Path(remembered_cfg))

    @property
    def dirty(self):
        return self.doc.to_bytes() != self.original

    def _action(self, text, callback, symbol=None, shortcut=None):
        action = QAction(icon(symbol) if symbol else self.windowIcon(), text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    def _build_actions(self):
        self.open_action = self._action("Open CFG…", self.open_config, "folder", QKeySequence.StandardKey.Open)
        self.save_action = self._action("Save CFG", self.save_config, "save", QKeySequence.StandardKey.Save)
        self.save_as_action = self._action("Save CFG as…", lambda: self.save_config(True), "save", QKeySequence.StandardKey.SaveAs)
        self.eboot_action = self._action("Select EBOOT…", self.choose_eboot, "folder")
        self.open_folder_action = self._action("Open output folder", self.open_target, "folder")
        filemenu = self.menuBar().addMenu("&File")
        for action in (self.open_action, self.save_action, self.save_as_action, self.eboot_action):
            filemenu.addAction(action)
        filemenu.addSeparator()
        filemenu.addAction("Exit", self.close, QKeySequence.StandardKey.Quit)
        self.tools_menu = self.menuBar().addMenu("&Tools")
        self.tools_menu.addAction(self.open_folder_action)
        self.tools_menu.addAction("Open output CFG", self.open_target_config)
        appearance = self.menuBar().addMenu("&View")
        themes = QActionGroup(self)
        self.theme_actions = {}
        for key, text in (("dark", "Dark theme"), ("light", "Light theme")):
            action = QAction(text, self, checkable=True)
            action.triggered.connect(lambda checked=False, key=key: self.apply_theme(key))
            themes.addAction(action)
            appearance.addAction(action)
            self.theme_actions[key] = action
        helpmenu = self.menuBar().addMenu("&Help")
        helpmenu.addAction("About", lambda: self.nav.setCurrentIndex(6))
        helpmenu.addAction("BloodPSP on GitHub", lambda: QDesktopServices.openUrl(QUrl("https://github.com/" + REPOSITORY)))

    def _build_shell(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.header_logo = QLabel()
        self.header_logo.setPixmap(QPixmap(str(resource("assets/bloodpsp-header.png"))).scaled(
            164, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        header.addWidget(self.header_logo)
        header.addStretch()
        cfg = QVBoxLayout()
        self.cfg_status = label("Default configuration", "Muted")
        self.cfg_status.setMaximumWidth(480)
        cfg.addWidget(self.cfg_status)
        buttons = QHBoxLayout()
        open_button = QPushButton("Open CFG…")
        open_button.clicked.connect(self.open_config)
        save_button = QPushButton("Save CFG")
        save_button.clicked.connect(lambda: self.save_config())
        self.cfg_buttons = (open_button, save_button)
        buttons.addWidget(open_button)
        buttons.addWidget(save_button)
        cfg.addLayout(buttons)
        header.addLayout(cfg)
        layout.addLayout(header)
        self.nav = QTabBar()
        self.nav.setExpanding(False)
        self.nav.setDrawBase(True)
        for title in ("Setup", "Controls", "Video", "Audio", "Game", "Advanced", "About"):
            self.nav.addTab(title)
        self.nav.currentChanged.connect(self.navigate)
        layout.addWidget(self.nav)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(170)
        self.progress_bar.hide()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel.set)
        self.cancel_button.hide()
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().addPermanentWidget(self.cancel_button)
        self.statusBar().showMessage("Ready")

    def page(self, title, subtitle=""):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(10)
        scroll.setWidget(widget)
        self.stack.addWidget(scroll)
        return layout

    def _path_row(self, initial, placeholder, callback):
        layout = QHBoxLayout()
        edit = QLineEdit(initial)
        edit.setPlaceholderText(placeholder)
        button = QPushButton("Browse…")
        button.setIcon(icon("folder"))
        button.setProperty("icon_name", "folder")
        button.clicked.connect(callback)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return layout, edit

    def _build_install_page(self):
        layout = self.page("Setup")
        group = QGroupBox("EBOOT")
        box = QVBoxLayout(group)
        row, self.eboot_edit = self._path_row("", "Select EBOOT.PBP", self.choose_eboot)
        self.eboot_edit.setReadOnly(True)
        box.addLayout(row)
        row = QHBoxLayout()
        self.eboot_status = label("No EBOOT selected", "Muted")
        row.addWidget(self.eboot_status, 1)
        self.release_button = QPushButton("Download latest from GitHub")
        self.release_button.clicked.connect(self.query_release)
        row.addWidget(self.release_button)
        box.addLayout(row)
        self.release_row = QWidget()
        row = QHBoxLayout(self.release_row)
        row.setContentsMargins(0, 0, 0, 0)
        self.asset_combo = QComboBox()
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.download_release)
        row.addWidget(self.asset_combo, 1)
        row.addWidget(self.download_button)
        self.release_row.hide()
        box.addWidget(self.release_row)
        self.release_label = label("", "Muted")
        self.release_label.hide()
        box.addWidget(self.release_label)
        layout.addWidget(group)
        group = QGroupBox("Game files")
        box = QVBoxLayout(group)
        row, self.source_edit = self._path_row(str(self.settings.value("source", "")), "Blood installation folder", self.choose_source)
        self.source_edit.editingFinished.connect(self.scan_source)
        box.addLayout(row)
        self.source_status = label("", "Muted", True)
        box.addWidget(self.source_status)
        layout.addWidget(group)
        group = QGroupBox("Output")
        box = QVBoxLayout(group)
        default_output = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)) / "BloodPSP" / "Export")
        row, self.target_edit = self._path_row(str(self.settings.value("target", default_output)), "PSP memory stick or output folder", self.choose_target)
        self.target_edit.editingFinished.connect(self.update_destination)
        box.addLayout(row)
        self.target_preview = label("", "Muted", True)
        self.target_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.target_preview)
        row = QHBoxLayout()
        self.write_config = QCheckBox("Apply editor settings")
        self.write_config.setChecked(True)
        self.write_config.setToolTip("Leave unchecked to keep the configuration already in the output folder.")
        row.addWidget(self.write_config)
        row.addStretch()
        load_existing = QPushButton("Edit output CFG")
        load_existing.clicked.connect(self.open_target_config)
        row.addWidget(load_existing)
        box.addLayout(row)
        self.destination_note = label("", "Muted", True)
        self.destination_note.hide()
        box.addWidget(self.destination_note)
        layout.addWidget(group)
        row = QHBoxLayout()
        row.addStretch()
        self.build_result = label("", "BuildResult")
        row.addWidget(self.build_result)
        self.install_button = QPushButton("BUILD PSP FOLDER")
        self.install_button.setObjectName("Primary")
        self.install_button.clicked.connect(self.prepare_install)
        row.addWidget(self.install_button)
        layout.addLayout(row)
        layout.addStretch()

    def _build_controls_page(self):
        layout = self.page("Controls")
        self.controls_editor = ControlsEditor(self.profile_store)
        self.controls_editor.edit_requested.connect(self.mutate)
        self.controls_editor.apply_requested.connect(self.apply_controls)
        self.controls_editor.scheme_selected.connect(self.select_scheme)
        self.controls_editor.preset_saved.connect(lambda name: self.statusBar().showMessage("Preset saved: " + name))
        self.scheme_combo = self.controls_editor.scheme_combo
        self.controller = self.controls_editor.controller
        self.axis_combos = self.controls_editor.axis_combos
        self.axis_scales = self.controls_editor.axis_scales
        layout.addWidget(self.controls_editor, 1)

    def add_fields(self, layout, title, fields):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for field in fields:
            if field.kind == "bool":
                widget = QCheckBox(field.label)
                widget.toggled.connect(lambda value, field=field: self.set_value(field.section, field.key, int(value)))
                form.addRow("", widget)
            elif field.kind == "slider":
                row = QHBoxLayout()
                widget = QSpinBox()
                widget.setRange(field.minimum, field.maximum)
                widget.setMaximumWidth(90)
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(field.minimum, field.maximum)
                slider.valueChanged.connect(widget.setValue)
                widget.valueChanged.connect(slider.setValue)
                widget.valueChanged.connect(lambda value, field=field: self.set_value(field.section, field.key, value))
                row.addWidget(slider, 1)
                row.addWidget(widget)
                form.addRow(field.label, row)
            else:
                widget = QSpinBox()
                widget.setRange(field.minimum, field.maximum)
                widget.setMaximumWidth(180)
                widget.valueChanged.connect(lambda value, field=field: self.set_value(field.section, field.key, value))
                form.addRow(field.label, widget)
            widget.setToolTip(field.tip or f"[{field.section}] {field.key}")
            self.fields[(field.section, field.key)] = widget
        layout.addWidget(group)

    def _build_video_page(self):
        layout = self.page("Video")
        group = QGroupBox("Display")
        form = QFormLayout(group)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("480 × 272 (PSP native)", (480, 272))
        self.resolution_combo.addItem("320 × 200", (320, 200))
        self.resolution_combo.setToolTip("Lower resolution improves performance. Native resolution requires a compatible EBOOT.")
        self.resolution_combo.currentIndexChanged.connect(self.resolution_changed)
        form.addRow("Resolution", self.resolution_combo)
        layout.addWidget(group)
        self.add_fields(layout, "Picture and camera", VIDEO)
        layout.addStretch()

    def _build_audio_page(self):
        layout = self.page("Audio")
        self.add_fields(layout, "Playback", AUDIO)
        group = QGroupBox("Quality")
        form = QFormLayout(group)
        self.sample_combo = QComboBox()
        self.sample_combo.addItem("22,050 Hz", 22050)
        self.sample_combo.addItem("44,100 Hz", 44100)
        self.sample_combo.currentIndexChanged.connect(lambda index: self.set_value("Sound Setup", "MixRate", self.sample_combo.currentData()))
        form.addRow("Sample rate", self.sample_combo)
        self.audio_compatibility = label("", "Muted", True)
        form.addRow(self.audio_compatibility)
        layout.addWidget(group)
        layout.addStretch()

    def _build_game_page(self):
        layout = self.page("Game")
        self.add_fields(layout, "Preferences", GAME)
        group = QGroupBox("Player")
        form = QFormLayout(group)
        self.player_name = QLineEdit()
        self.player_name.setMaxLength(15)
        self.player_name.editingFinished.connect(lambda: self.set_value("Comm Setup", "PlayerName", quote(self.player_name.text())))
        form.addRow("Name", self.player_name)
        layout.addWidget(group)
        layout.addStretch()

    def _build_advanced_page(self):
        layout = self.page("Advanced", "")
        row = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search settings…")
        self.filter_edit.textChanged.connect(self.filter_tree)
        row.addWidget(self.filter_edit, 1)
        add = QPushButton("Add setting…")
        add.clicked.connect(self.add_option)
        row.addWidget(add)
        layout.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setObjectName("ConfigTree")
        self.tree.setHeaderLabels(["Setting", "Value", "Description"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(440)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree.setItemDelegate(ValueDelegate(BOOLEAN_FIELDS, self.tree))
        self.tree.itemChanged.connect(self.tree_changed)
        layout.addWidget(self.tree, 1)
        layout.addWidget(label('Key bindings use two quoted strings, e.g. "Space" "". Some NBlood settings do not apply to the PSP port.', "Muted", True))

    def _build_about_page(self):
        layout = self.page("About")
        layout.addWidget(label("BloodPSP Launcher " + __version__))
        row = QHBoxLayout()
        project = QPushButton("GitHub")
        project.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/" + REPOSITORY)))
        row.addWidget(project)
        notices = QPushButton("Credits and licenses")
        notices.clicked.connect(self.open_notices)
        row.addWidget(notices)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def open_notices(self):
        path = resource("licenses/THIRD-PARTY-NOTICES.md") if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent / "THIRD-PARTY-NOTICES.md"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _build_log(self):
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        self.log_dock = QDockWidget("Activity", self)
        self.log_dock.setWidget(self.log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()
        self.tools_menu.addAction(self.log_dock.toggleViewAction())
        self.tools_menu.addAction("Open log file", self.open_log)

    def apply_theme(self, theme):
        dark = theme == "dark"
        palette = QPalette()
        colors = {
            QPalette.ColorRole.Window: "#292b2e" if dark else "#f0f0f0",
            QPalette.ColorRole.WindowText: "#e4e4e4" if dark else "#202020",
            QPalette.ColorRole.Base: "#202225" if dark else "#ffffff",
            QPalette.ColorRole.AlternateBase: "#2c2e31" if dark else "#f5f5f5",
            QPalette.ColorRole.Text: "#e4e4e4" if dark else "#202020",
            QPalette.ColorRole.Button: "#36383c" if dark else "#e6e6e6",
            QPalette.ColorRole.ButtonText: "#e4e4e4" if dark else "#202020",
            QPalette.ColorRole.Highlight: "#456b92",
            QPalette.ColorRole.HighlightedText: "#ffffff",
            QPalette.ColorRole.PlaceholderText: "#96999f" if dark else "#737373",
            QPalette.ColorRole.ToolTipBase: "#36383c" if dark else "#ffffff",
            QPalette.ColorRole.ToolTipText: "#eeeeee" if dark else "#202020",
        }
        for role, color in colors.items():
            palette.setColor(role, QColor(color))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#858585"))
        QApplication.instance().setPalette(palette)
        muted = "#a5a8ac" if dark else "#666666"
        self.setStyleSheet(f"""
            QLabel#Muted {{ color: {muted}; }}
            QGroupBox {{ margin-top: 10px; padding: 14px 10px 10px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}
            QLineEdit, QComboBox, QSpinBox {{ min-height: 24px; }}
            QPushButton {{ min-height: 26px; padding: 0 10px; }}
            QPushButton#Primary, QPushButton#Accent {{ background: #244fce; color: white; border: 1px solid #3c6be4; border-radius: 5px; font-weight: 600; }}
            QPushButton#Primary {{ min-height: 34px; padding: 0 18px; }}
            QPushButton#Primary:hover, QPushButton#Accent:hover {{ background: #3062e3; }}
            QPushButton#Primary:disabled, QPushButton#Accent:disabled {{ background: #424957; color: #969ba5; border-color: #555d6b; }}
            QLabel#BuildResult {{ color: {"#6ad89b" if dark else "#168044"}; font-weight: 700; padding: 0 12px; }}
            QLabel#CapturePreview {{ font-size: 19px; font-weight: 600; color: {"#91b4ff" if dark else "#244fce"}; }}
            QTableWidget {{ border: 1px solid {"#454a53" if dark else "#bec5ce"}; border-radius: 5px; }}
            QHeaderView::section {{ padding: 7px; border: none; border-bottom: 1px solid {"#454a53" if dark else "#bec5ce"}; }}
            QTableWidget QComboBox {{ margin: 2px 4px; }}
            QToolButton#DeleteMapping {{ border: none; margin: 3px 7px; }}
            QToolButton#DeleteMapping:hover {{ background: {"#62313a" if dark else "#f5dce1"}; border-radius: 4px; }}
            QTabBar::tab {{ min-width: 68px; padding: 7px 10px; }}
            QToolButton#PspButton {{ background: transparent; border: 2px solid transparent; border-radius: 7px; }}
            QToolButton#PspButton:hover, QToolButton#PspButton:checked {{ border-color: #77a9db; background: rgba(85, 153, 221, 65); }}
            QTreeWidget::item {{ padding: 3px; }}
        """)
        self.theme_actions["dark" if dark else "light"].setChecked(True)
        self.settings.setValue("theme", theme)

    def navigate(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)
            if row == 5 and hasattr(self, "tree"):
                self.refresh_tree()

    def update_state(self):
        name = self.cfg_status.fontMetrics().elidedText(str(self.config_path), Qt.TextElideMode.ElideMiddle, 440) if self.config_path else "Default configuration"
        self.cfg_status.setText(name + (" · Unsaved changes" if self.dirty else ""))
        self.cfg_status.setToolTip(str(self.config_path) if self.config_path else "Bundled default configuration")
        self.setWindowTitle(("* " if self.dirty else "") + "BloodPSP Launcher")

    def mutate(self, function, from_tree=False):
        if self.refreshing or self.busy:
            return
        try:
            updated = self.doc.clone()
            function(updated)
            updated.to_bytes()
            if has_native_mappings(updated):
                read_mappings(updated, self.scheme)
            self.doc = updated
        except (ConfigError, ValueError) as ex:
            QMessageBox.warning(self, "Configuration", str(ex))
        self.refresh(skip_tree=from_tree)

    def set_value(self, section, key, value):
        if value is not None:
            self.mutate(lambda doc: doc.set(section, key, value))

    def refresh(self, skip_tree=False):
        self.refreshing = True
        try:
            for field in ALL_FIELDS:
                widget = self.fields[(field.section, field.key)]
                value = self.doc.number(field.section, field.key)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                else:
                    widget.setRange(min(field.minimum, value), max(field.maximum, value))
                    widget.setValue(value)
            dimensions = (self.doc.number("Screen Setup", "ScreenWidth"), self.doc.number("Screen Setup", "ScreenHeight"))
            self._combo_value(self.resolution_combo, dimensions, f"{dimensions[0]} × {dimensions[1]} — imported")
            rate = self.doc.number("Sound Setup", "MixRate")
            self._combo_value(self.sample_combo, rate, str(rate) + " Hz — imported")
            name = tokens(self.doc.get("Comm Setup", "PlayerName", '"Player"'))
            self.player_name.setText(name[0] if name else "")
            self.refresh_bindings()
            if not skip_tree:
                self.refresh_tree()
            if self.eboot:
                self.audio_compatibility.setText("OGG playback supported." if self.eboot.ogg else "This EBOOT does not support OGG playback.")
            else:
                self.audio_compatibility.setText("")
            self.update_state()
        finally:
            self.refreshing = False

    @staticmethod
    def _combo_value(combo, value, text):
        # Qt converts tuple userData to a list; QVariant equality does not
        # match a later tuple, so compare normalized Python values instead.
        expected = tuple(value) if isinstance(value, (tuple, list)) else value
        index = -1
        for i in range(combo.count()):
            candidate = combo.itemData(i)
            if isinstance(candidate, (tuple, list)):
                candidate = tuple(candidate)
            if candidate == expected:
                index = i
                break
        if index < 0:
            combo.addItem(text, value)
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    def refresh_bindings(self):
        self.controls_editor.refresh(self.doc, self.scheme, self.eboot)
        self.control_combos = self.controls_editor.control_combos









    def select_scheme(self, scheme):
        if self.refreshing or scheme not in SCHEMES:
            return
        self.scheme = scheme
        self.refresh()

    def resolution_changed(self, index):
        dimensions = self.resolution_combo.currentData()
        if dimensions:
            def change(doc):
                doc.set("Screen Setup", "ScreenWidth", dimensions[0])
                doc.set("Screen Setup", "ScreenHeight", dimensions[1])
            self.mutate(change)

    def refresh_tree(self):
        previous = self.refreshing
        self.refreshing = True
        self.tree.clear()
        sections = {}
        for entry in self.doc.entries.values():
            if entry.section not in sections:
                sections[entry.section] = QTreeWidgetItem(self.tree, [entry.section])
                sections[entry.section].setExpanded(True)
            description = DESCRIPTIONS.get((entry.section, entry.key), ACTION_LABELS.get(entry.key, ""))
            item = QTreeWidgetItem(sections[entry.section], [entry.key, entry.value, description])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(1, Qt.ItemDataRole.UserRole, (entry.section, entry.key))
            item.setToolTip(1, "Double-click to edit.")
        self.refreshing = previous
        self.filter_tree(self.filter_edit.text())

    def filter_tree(self, text):
        query = text.casefold().strip()
        for i in range(self.tree.topLevelItemCount()):
            section = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(section.childCount()):
                item = section.child(j)
                visible = not query or query in (section.text(0) + " " + " ".join(item.text(c) for c in range(3))).casefold()
                item.setHidden(not visible)
                any_visible |= visible
            section.setHidden(not any_visible)

    def tree_changed(self, item, column):
        if self.refreshing or column != 1:
            return
        identity = item.data(1, Qt.ItemDataRole.UserRole)
        if identity:
            self.mutate(lambda doc: doc.set(*identity, item.text(1)), from_tree=True)
            # On a rejected edit, put the original value back in the table.
            self.refreshing = True
            item.setText(1, self.doc.get(*identity))
            self.refreshing = False

    def add_option(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add setting")
        box = QVBoxLayout(dialog)
        form = QFormLayout()
        section = QComboBox()
        section.setEditable(True)
        section.addItems([name for name, _ in self.doc.sections.values()])
        key, value = QLineEdit(), QLineEdit()
        form.addRow("Section", section)
        form.addRow("Setting", key)
        form.addRow("Value", value)
        box.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        box.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = section.currentText().strip()
            if not name or any(c in name for c in "[]\r\n"):
                QMessageBox.warning(self, "Configuration", "Enter a valid section name.")
                return
            self.set_value(name, key.text().strip(), value.text())

    def allow_discard(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved changes", "Save your changes before continuing?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_config()
        return answer == QMessageBox.StandardButton.Discard

    def open_config(self):
        if not self.allow_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Blood configuration", str(self.config_path.parent) if self.config_path else "", "Configuration (*.cfg);;All files (*)")
        if path:
            self.load_config(Path(path))

    def load_config(self, path):
        try:
            document = ConfigDocument.load(path)
            if has_native_mappings(document):
                read_mappings(document, self.scheme)
            self.doc, self.original = document, document.to_bytes()
            self.config_path = path.resolve()
            self.config_hash = fingerprint(path)
            self.settings.setValue("config", str(self.config_path))
            self.refresh()
            self.update_destination()
            self.controls_editor.selected_profile = ""
            self.controls_editor.reload_profiles()
            adjacent_eboot = path.parent / "EBOOT.PBP"
            if adjacent_eboot.is_file():
                self.accept_eboot(validate_pbp(adjacent_eboot))
            self.append_log("Opened CFG: " + str(path))
            self.statusBar().showMessage("Configuration loaded.")
        except Exception as ex:
            self.show_error("Could not open CFG", ex)

    def apply_controls(self):
        if self.busy:
            return False
        self.controls_editor.show_apply_status(False)
        if self.eboot and has_native_mappings(self.doc) and not self.eboot.native_controls:
            self.show_error("Apply controls", "This EBOOT cannot read custom mappings. Select the EBOOT included with this release and build the PSP folder first.")
            return False
        if not self.save_config():
            return False
        self.controls_editor.show_apply_status(True)
        self.statusBar().showMessage("Controls saved to " + str(self.config_path) + ". Restart the game.")
        return True

    def save_config(self, save_as=False):
        path = self.config_path
        expected = self.config_hash
        if not path or save_as:
            chosen, _ = QFileDialog.getSaveFileName(self, "Save configuration", str(path) if path else "nblood.cfg", "Configuration (*.cfg)")
            if not chosen:
                return False
            path = Path(chosen)
            # QFileDialog confirms overwrites. If this is the same open file,
            # still use its original fingerprint to detect external edits.
            expected = self.config_hash if self.config_path and path.resolve() == self.config_path else fingerprint(path)
        try:
            backup = self.doc.save(path, expected)
            self.config_path, self.config_hash = path.resolve(), fingerprint(path)
            self.original = self.doc.to_bytes()
            self.settings.setValue("config", str(self.config_path))
            self.update_state()
            self.append_log("Saved CFG: " + str(path) + (" | Backup: " + str(backup) if backup else ""))
            self.statusBar().showMessage("Saved: " + str(path))
            return True
        except Exception as ex:
            self.show_error("Could not save CFG", ex)
            return False

    def choose_eboot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select EBOOT", "", "PSP executable (*.pbp);;All files (*)")
        if path:
            try:
                self.accept_eboot(validate_pbp(Path(path)))
            except Exception as ex:
                self.show_error("Invalid EBOOT", ex)

    def accept_eboot(self, info):
        self.eboot = info
        self.eboot_edit.setText(str(info.path))
        self.eboot_status.setText(f"{SCHEME_LABELS[info.scheme]} · {info.size / 1048576:.2f} MiB")
        self.eboot_status.setToolTip("SHA-256: " + info.sha256)
        self.eboot_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.scheme = info.scheme
        if not self.config_path and not self.dirty:
            self.doc = default_document(info.scheme)
            self.original = self.doc.to_bytes()
        self.refreshing = True
        self.scheme_combo.setCurrentIndex(self.scheme_combo.findData(self.scheme))
        self.refreshing = False
        self.settings.setValue("eboot", str(info.path))
        self.refresh()
        self.append_log("Selected EBOOT: " + info.sha256)

    def query_release(self):
        self.start_task(lambda progress, cancelled: get_latest(REPOSITORY), self.release_loaded, "Checking GitHub Releases…")

    def release_loaded(self, release):
        self.release = release
        self.asset_combo.clear()
        for asset in release["download_assets"]:
            self.asset_combo.addItem(f"{asset['name']}  •  {asset['size'] / 1048576:.2f} MiB", asset)
        self.release_row.setVisible(self.asset_combo.count() > 1)
        date = release.get("published_at", "")[:10]
        self.release_label.setText(f"{release.get('name') or release['tag_name']}  •  {date}")
        self.release_label.show()
        if self.asset_combo.count() == 1:
            self.pending_download = True

    def download_release(self):
        asset = self.asset_combo.currentData()
        if asset:
            self.start_task(lambda progress, cancelled: download_asset(asset, self.cache, progress, cancelled), self.accept_eboot, "Downloading EBOOT…")

    def choose_source(self):
        path = QFileDialog.getExistingDirectory(self, "Blood game folder", self.source_edit.text())
        if path:
            self.source_edit.setText(path)
            self.scan_source()

    def scan_source(self):
        path = self.source_edit.text().strip()
        if not path:
            self.source_status.setText("Select your Blood installation folder.")
            return
        try:
            files = scan_game(Path(path))
            missing = [name for name, value in files.items() if value is None]
            if missing:
                self.source_status.setText(f"{len(files) - len(missing)}/{len(files)} files found. Missing: " + ", ".join(missing))
            else:
                self.source_status.setText("Game files ready")
            self.settings.setValue("source", path)
        except Exception as ex:
            self.source_status.setText(str(ex))

    def choose_target(self):
        path = QFileDialog.getExistingDirectory(self, "PSP memory stick or output folder", self.target_edit.text())
        if path:
            self.target_edit.setText(path)
            self.update_destination()

    def target(self):
        text = self.target_edit.text().strip()
        if not text:
            raise ConfigError("Select an output folder.")
        return game_destination(Path(text).absolute())

    def update_destination(self):
        try:
            target = self.target()
            self.target_preview.setText(str(target))
            cfg = target / "nblood.cfg"
            editing_target = self.config_path is not None and self.config_path == cfg.resolve()
            if cfg.exists() and not editing_target:
                self.write_config.setChecked(False)
                self.destination_note.setText("Existing CFG will be kept. Enable Apply editor settings to replace it.")
                self.destination_note.show()
            else:
                self.write_config.setChecked(True)
                self.destination_note.setText("")
                self.destination_note.hide()
            self.settings.setValue("target", self.target_edit.text().strip())
        except Exception as ex:
            self.target_preview.setText(str(ex))

    def open_target_config(self):
        try:
            path = self.target() / "nblood.cfg"
            if not path.is_file():
                raise ConfigError("No nblood.cfg exists in the output folder yet.")
            if self.allow_discard():
                self.load_config(path)
        except Exception as ex:
            self.show_error("Output configuration", ex)

    def prepare_install(self):
        try:
            if not self.eboot:
                raise ConfigError("Select or download an EBOOT first.")
            if has_native_mappings(self.doc) and not self.eboot.native_controls:
                raise ConfigError("This EBOOT cannot read custom mappings. Select the EBOOT included with this release first.")
            self.build_result.setText("")
            source_text = self.source_edit.text().strip()
            if not source_text:
                raise ConfigError("Select the Blood game folder.")
            target = self.target()
            cfg = self.doc.to_bytes() if self.write_config.isChecked() else None
            if cfg is None and not (target / "nblood.cfg").is_file():
                raise ConfigError("Enable Apply editor settings to create a CFG for this installation.")
            if self.config_path and self.config_path == (target / "nblood.cfg").resolve():
                expected = self.config_hash
            else:
                expected = fingerprint(target / "nblood.cfg")
            plan = InstallPlan(Path(source_text), target, self.eboot, cfg, expected,
                               True, True)
            self.start_task(lambda progress, cancelled: install(plan, progress, cancelled), self.install_finished, "Building PSP folder…")
        except Exception as ex:
            self.show_error("Build PSP folder", ex)

    def install_finished(self, result):
        self.append_log(json.dumps(result, ensure_ascii=False))
        target_cfg = Path(result["target"]) / "nblood.cfg"
        if self.write_config.isChecked():
            self.config_path = target_cfg.resolve()
            self.config_hash = fingerprint(target_cfg)
            self.settings.setValue("config", str(self.config_path))
            self.original = self.doc.to_bytes()
            self.update_state()
        self.build_result.setText("BUILD DONE")
        text = f"PSP folder ready:\n{result['target']}"
        if result["backup"]:
            text += "\n\nBackup:\n" + result["backup"]
        QMessageBox.information(self, "Build complete", text)

    def open_target(self):
        try:
            target = self.target()
            if not target.is_dir():
                raise ConfigError("Build the PSP folder first.")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        except Exception as ex:
            self.show_error("PSP folder", ex)

    def append_log(self, message):
        text = datetime.now().strftime("%H:%M:%S") + "  " + message
        self.log.append(text)
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError:
            pass

    def open_log(self):
        self.append_log("Opened log file.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path)))

    def show_error(self, title, error):
        self.append_log(title + ": " + str(error))
        QMessageBox.warning(self, title, str(error))

    def start_task(self, function, callback, message):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self.callback = callback
        self.stack.setEnabled(False)
        self.nav.setEnabled(False)
        for button in self.cfg_buttons:
            button.setEnabled(False)
        self.tools_menu.setEnabled(False)
        for action in (self.open_action, self.save_action, self.save_as_action, self.eboot_action):
            action.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.cancel_button.show()
        self.statusBar().showMessage(message)
        self.append_log(message)
        self.thread = QThread(self)
        self.worker = Worker(function, self.cancel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.task_progress)
        self.worker.done.connect(self.task_done)
        self.worker.failed.connect(self.task_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.task_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(int, str)
    def task_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.statusBar().showMessage(message)

    @Slot(object)
    def task_done(self, result):
        if self.cancel.is_set():
            self.statusBar().showMessage("Operation stopped.")
            return
        try:
            self.callback(result)
            self.progress_bar.setValue(100)
            self.statusBar().showMessage("Done.")
        except Exception as ex:
            self.show_error("Operation", ex)

    @Slot(str, str)
    def task_failed(self, message, trace):
        self.append_log(trace)
        if self.cancel.is_set():
            self.statusBar().showMessage("Cancelled. Previous files preserved.")
        else:
            self.show_error("Could not complete operation", message)
            self.statusBar().showMessage("Operation failed. See Activity for details.")

    @Slot()
    def task_finished(self):
        self.busy = False
        self.stack.setEnabled(True)
        self.nav.setEnabled(True)
        for button in self.cfg_buttons:
            button.setEnabled(True)
        self.tools_menu.setEnabled(True)
        for action in (self.open_action, self.save_action, self.save_as_action, self.eboot_action):
            action.setEnabled(True)
        self.progress_bar.hide()
        self.cancel_button.hide()
        self.thread = None
        self.worker = None
        if self.close_pending:
            QTimer.singleShot(0, self.close)
        elif getattr(self, "pending_download", False):
            self.pending_download = False
            if not self.cancel.is_set():
                QTimer.singleShot(0, self.download_release)

    def closeEvent(self, event):
        if self.busy:
            self.cancel.set()
            self.close_pending = True
            self.statusBar().showMessage("Finishing operation before closing…")
            event.ignore()
            return
        if not self.allow_discard():
            self.close_pending = False
            event.ignore()
            return
        self.settings.sync()
        event.accept()


def configure_application(app):
    app.setOrganizationName("BloodPSP")
    app.setApplicationName("BloodPSP Launcher")
    app.setStyle("Fusion")
    # The offscreen test platform has no Windows font database. Use installed
    # system fonts for test captures; fonts are never redistributed.
    if app.platformName() == "offscreen" and os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisym.ttf"):
            if (fonts / name).exists():
                QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Segoe UI", 10))


def main():
    app = QApplication(sys.argv)
    configure_application(app)
    window = MainWindow()
    window.show()
    return app.exec()
