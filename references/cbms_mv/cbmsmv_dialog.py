# -*- coding: utf-8 -*-
"""
2027 CBMS Form 2 Map Validation (CBMS MV) - Dialog UI
------------------------------------------------------
Custom GUI dialog for validating CBMS Form 2 household data,
geotagged building points, and reference base layers against
established PSA validation rules and spatial constraints.

All components, configurations, and reference implementations for
this tool are self-contained within references/cbms_mv.
Algorithms are dynamically discovered from gmd_scripts/cbms_mv.
"""

import os
import sys
import ast
import json
import datetime
from typing import Optional, List, Dict, Any

from qgis.core import (
    Qgis,
    QgsProject,
    QgsVectorLayer,
    QgsMapLayer,
    QgsApplication,
    QgsMessageLog,
    QgsSettings,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingUtils,
    QgsProviderRegistry,
)
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal, QSize
from qgis.PyQt.QtGui import QIcon, QColor, QFont, QTextCursor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QTabWidget,
    QWidget,
    QFrame,
    QMessageBox,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QLineEdit,
    QTextEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QFileDialog,
    QApplication,
)

try:
    import processing
except ImportError:
    processing = None

SETTINGS_KEY_FORM2 = "gemma/cbmsmv/form2_json_path"
SETTINGS_KEY_POINTS = "gemma/cbmsmv/points_geojson_path"
SETTINGS_KEY_BASE = "gemma/cbmsmv/base_gpkg_path"
SETTINGS_KEY_LOAD_INPUTS = "gemma/cbmsmv/load_inputs_in_layers"

try:
    from ...gmd_scripts.gmdhelpers import load_cbms_json_to_layer
except (ImportError, ValueError):
    try:
        from gmd_scripts.gmdhelpers import load_cbms_json_to_layer
    except (ImportError, ValueError):
        _plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if _plugin_root not in sys.path:
            sys.path.insert(0, _plugin_root)
        from gmd_scripts.gmdhelpers import load_cbms_json_to_layer


# ---------------------------------------------------------------------------
# Dynamic Rule Discovery from gmd_scripts/cbms_mv
# ---------------------------------------------------------------------------
def discover_cbms_mv_rules(cbms_mv_dir: str) -> List[Dict[str, Any]]:
    """
    Dynamically scan the gmd_scripts/cbms_mv directory and extract:
      - Validation ID: the python file name without .py
      - Validation Check Name: the first line of shortHelpString()
      - Description: the full help string
      - has_base: whether the algorithm accepts BASE_LAYER (.gpkg)

    When a developer adds a new script to gmd_scripts/cbms_mv,
    it automatically appears in the dialog without modifying code.
    """
    rules: List[Dict[str, Any]] = []

    if not os.path.isdir(cbms_mv_dir):
        return rules

    for filename in sorted(os.listdir(cbms_mv_dir)):
        if not filename.endswith(".py") or filename.startswith(("_", ".")):
            continue

        val_id = filename[:-3]
        file_path = os.path.join(cbms_mv_dir, filename)

        help_str = ""
        has_base_layer = False

        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                content = fh.read()

            tree = ast.parse(content)
            for node in ast.walk(tree):
                # Extract shortHelpString return value
                if isinstance(node, ast.FunctionDef) and node.name == "shortHelpString":
                    for stmt in node.body:
                        if isinstance(stmt, ast.Return):
                            if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                                help_str = stmt.value.value
                            elif hasattr(ast, "Str") and isinstance(stmt.value, ast.Str):
                                help_str = stmt.value.s

                # Check if BASE_LAYER parameter is assigned/used
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "BASE_LAYER":
                            has_base_layer = True

        except Exception as exc:
            help_str = f"Error reading algorithm help: {exc}"

        # First line of shortHelpString is the Validation Check Name
        lines = [line.strip() for line in help_str.strip().split("\n") if line.strip()]
        first_line = lines[0] if lines else val_id.replace("_", " ").title()
        desc = " ".join(lines[1:]) if len(lines) > 1 else help_str.strip()

        rules.append({
            "id": val_id,
            "name": first_line,
            "desc": desc,
            "has_base": has_base_layer,
            "file_path": file_path,
            "default": True,
        })

    return rules


class ProcessingFeedbackBridge(QgsProcessingFeedback):
    """Bridges QGIS Processing feedback messages to the dialog log console."""

    def __init__(self, log_info_fn, log_warn_fn, log_err_fn):
        super().__init__()
        self.log_info_fn = log_info_fn
        self.log_warn_fn = log_warn_fn
        self.log_err_fn = log_err_fn

    def pushInfo(self, info: str):
        if info and self.log_info_fn:
            self.log_info_fn(info)

    def reportError(self, error: str, fatalError: bool = False):
        if error:
            if fatalError and self.log_err_fn:
                self.log_err_fn(error)
            elif self.log_warn_fn:
                self.log_warn_fn(error)


class CbmsmvDialog(QDialog):
    """
    2027 CBMS Form 2 Map Validation (CBMS MV) Dialog UI.
    Provides three core tabs:
      1. Data Config     : File-based Primary Input Data Sources & Output destination.
      2. Validation Rules: Dynamic, filterable registry of cbms_mv algorithms.
      3. Execution Logs  : Live metrics, progress, and execution console.
    """

    def __init__(
        self,
        iface,
        project: Optional[QgsProject] = None,
        offline_editing=None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent or (iface.mainWindow() if iface else None))
        self.iface = iface
        self.project = project or QgsProject.instance()
        self.offline_editing = offline_editing
        self.settings = QgsSettings()

        # Resolve path to gmd_scripts/cbms_mv
        self.cbms_mv_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "gmd_scripts", "cbms_mv")
        )

        self.setWindowTitle("2027 CBMS Form 2 Map Validation")
        self.setMinimumSize(840, 680)
        self.resize(900, 720)

        self._rules: List[Dict[str, Any]] = []
        self._rule_checkboxes: Dict[str, QTableWidgetItem] = {}
        self._is_validating = False

        self.context = QgsProcessingContext()
        self.context.setProject(self.project)

        self._setup_dialog_icon()
        self._init_ui()
        self._apply_styling()
        self._load_saved_settings()
        self.refresh_rules()

    # -----------------------------------------------------------------------
    # Setup & Icons
    # -----------------------------------------------------------------------
    def _setup_dialog_icon(self):
        """Set the window icon using available SVG assets."""
        icon_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons")
        )
        for icon_name in ("mbi_validator.svg", "scan_errors.svg", "others.svg"):
            icon_path = os.path.join(icon_dir, icon_name)
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                break

    # -----------------------------------------------------------------------
    # UI Layout Construction
    # -----------------------------------------------------------------------
    def _init_ui(self):
        """Initialize and assemble the main layout and tabs."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. Header Banner
        header_widget = self._create_header_banner()
        main_layout.addWidget(header_widget)

        # 2. Three Main Tabs: Data Config, Validation Rules, Execution Logs
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("mainTabWidget")

        self.tab_data_config = self._create_tab_data_config()
        self.tab_validation_rules = self._create_tab_validation_rules()
        self.tab_execution_logs = self._create_tab_execution_logs()

        self.tab_widget.addTab(self.tab_data_config, "📋  Data Config")
        self.tab_widget.addTab(self.tab_validation_rules, "⚙️  Validation Rules")
        self.tab_widget.addTab(self.tab_execution_logs, "📊  Execution Logs")

        main_layout.addWidget(self.tab_widget, stretch=1)

        # 3. Bottom Action Bar
        bottom_bar = self._create_bottom_action_bar()
        main_layout.addWidget(bottom_bar)

    # -----------------------------------------------------------------------
    # Header Banner
    # -----------------------------------------------------------------------
    def _create_header_banner(self) -> QWidget:
        """Create the top brand banner with title, description, and dynamic count badge."""
        banner = QFrame()
        banner.setObjectName("headerBanner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(16, 12, 16, 12)
        banner_layout.setSpacing(14)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_label = QLabel("2027 CBMS Form 2 Map Validation")
        title_label.setObjectName("headerTitle")

        subtitle_label = QLabel(
            "Spatial & Attribute Consistency Validation Engine for CBMS Form 2 Datafiles, "
            "Geotagged Points, and Reference Base Layers"
        )
        subtitle_label.setObjectName("headerSubtitle")

        text_layout.addWidget(title_label)
        text_layout.addWidget(subtitle_label)
        banner_layout.addLayout(text_layout, stretch=1)

        self.lbl_header_badge = QLabel("READY")
        self.lbl_header_badge.setObjectName("headerBadge")
        banner_layout.addWidget(self.lbl_header_badge)

        return banner

    # -----------------------------------------------------------------------
    # Tab 1: Data Config
    # -----------------------------------------------------------------------
    def _create_tab_data_config(self) -> QWidget:
        """
        Create the Data Config tab containing filepaths for:
          - Form 2 Data File (.json)
          - Geotagged Building Points (.geojson)
          - Base Layers (.gpkg)
        along with output and destination settings.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(14)

        # -------------------------------------------------------------------
        # Group 1: Primary Input Data Sources (Filepaths)
        # -------------------------------------------------------------------
        grp_sources = QGroupBox("Primary Input Data Sources")
        grp_sources.setObjectName("sectionGroup")
        grid_sources = QGridLayout(grp_sources)
        grid_sources.setContentsMargins(14, 16, 14, 14)
        grid_sources.setSpacing(12)

        # 1. Form 2 Data File (.json)
        lbl_form2 = QLabel("Form 2 Data File (.json):")
        lbl_form2.setStyleSheet("font-weight: bold; color: #2C3E50;")
        self.file_form2 = QgsFileWidget()
        self.file_form2.setDialogTitle("Select Form 2 Data File (.json)")
        self.file_form2.setFilter("CBMS Form 2 JSON Files (*.json);;All Files (*.*)")
        self.file_form2.setStorageMode(QgsFileWidget.GetFile)
        self.file_form2.fileChanged.connect(self._on_inputs_changed)

        self.lbl_status_form2 = QLabel("")
        self.lbl_status_form2.setFixedWidth(24)
        self.lbl_status_form2.setAlignment(Qt.AlignCenter)

        grid_sources.addWidget(lbl_form2, 0, 0)
        grid_sources.addWidget(self.file_form2, 0, 1)
        grid_sources.addWidget(self.lbl_status_form2, 0, 2)

        # 2. Geotagged Building Points (.geojson)
        lbl_points = QLabel("Geotagged Building Points (.geojson):")
        lbl_points.setStyleSheet("font-weight: bold; color: #2C3E50;")
        self.file_points = QgsFileWidget()
        self.file_points.setDialogTitle("Select Geotagged Building Points (.geojson)")
        self.file_points.setFilter("GeoJSON Vector Files (*.geojson);;All Files (*.*)")
        self.file_points.setStorageMode(QgsFileWidget.GetFile)
        self.file_points.fileChanged.connect(self._on_inputs_changed)

        self.lbl_status_points = QLabel("")
        self.lbl_status_points.setFixedWidth(24)
        self.lbl_status_points.setAlignment(Qt.AlignCenter)

        grid_sources.addWidget(lbl_points, 1, 0)
        grid_sources.addWidget(self.file_points, 1, 1)
        grid_sources.addWidget(self.lbl_status_points, 1, 2)

        # 3. Base Layers (.gpkg)
        lbl_base = QLabel("Base Layers (.gpkg):")
        lbl_base.setStyleSheet("font-weight: bold; color: #2C3E50;")
        self.file_base = QgsFileWidget()
        self.file_base.setDialogTitle("Select Base Layers (.gpkg)")
        self.file_base.setFilter("GeoPackage Database Files (*.gpkg);;All Files (*.*)")
        self.file_base.setStorageMode(QgsFileWidget.GetFile)
        self.file_base.fileChanged.connect(self._on_inputs_changed)

        self.lbl_status_base = QLabel("")
        self.lbl_status_base.setFixedWidth(24)
        self.lbl_status_base.setAlignment(Qt.AlignCenter)

        grid_sources.addWidget(lbl_base, 2, 0)
        grid_sources.addWidget(self.file_base, 2, 1)
        grid_sources.addWidget(self.lbl_status_base, 2, 2)

        # Single option for loading primary input data sources into QGIS Layers Panel
        self.chk_load_inputs_canvas = QCheckBox("Load primary input data sources into QGIS Layers Panel")
        self.chk_load_inputs_canvas.setToolTip(
            "If checked, automatically loads Form 2 JSON (via load_cbms_json_to_layer), Geotagged Building Points, "
            "and all sublayers in Base Layers GPKG into QGIS Layers Panel during validation."
        )
        self.chk_load_inputs_canvas.stateChanged.connect(self._on_inputs_changed)
        grid_sources.addWidget(self.chk_load_inputs_canvas, 3, 0, 1, 3)

        container_layout.addWidget(grp_sources)

        # -------------------------------------------------------------------
        # Group 2: Validation Output & Workspace Settings
        # -------------------------------------------------------------------
        grp_output = QGroupBox("Validation && Output Settings")
        grp_output.setObjectName("sectionGroup")
        vbox_output = QVBoxLayout(grp_output)
        vbox_output.setContentsMargins(14, 16, 14, 14)
        vbox_output.setSpacing(10)

        # Output Mode: In-Memory vs GeoPackage
        mode_layout = QHBoxLayout()
        lbl_mode = QLabel("Output Destination:")
        lbl_mode.setStyleSheet("font-weight: bold; color: #2C3E50;")
        self.radio_memory = QRadioButton("Temporary In-Memory Layers (Recommended)")
        self.radio_memory.setChecked(True)
        self.radio_file = QRadioButton("Export Results to GeoPackage")

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_memory)
        self.mode_group.addButton(self.radio_file)
        self.radio_file.toggled.connect(self._toggle_output_file_visibility)

        mode_layout.addWidget(lbl_mode)
        mode_layout.addWidget(self.radio_memory)
        mode_layout.addWidget(self.radio_file)
        mode_layout.addStretch()
        vbox_output.addLayout(mode_layout)

        # File widget for GeoPackage export (initially hidden)
        self.gpkg_widget = QWidget()
        gpkg_layout = QHBoxLayout(self.gpkg_widget)
        gpkg_layout.setContentsMargins(0, 0, 0, 0)
        lbl_gpkg = QLabel("Output GeoPackage:")
        lbl_gpkg.setStyleSheet("font-weight: bold; color: #2C3E50;")
        self.file_widget_gpkg = QgsFileWidget()
        self.file_widget_gpkg.setStorageMode(QgsFileWidget.SaveFile)
        self.file_widget_gpkg.setFilter("GeoPackage Files (*.gpkg)")
        self.file_widget_gpkg.setDialogTitle("Save Validation Results GeoPackage")
        gpkg_layout.addWidget(lbl_gpkg)
        gpkg_layout.addWidget(self.file_widget_gpkg, stretch=1)
        self.gpkg_widget.setVisible(False)
        vbox_output.addWidget(self.gpkg_widget)

        # Checkboxes
        self.chk_load_canvas = QCheckBox("Add generated error/flag layers directly into QGIS Canvas")
        self.chk_load_canvas.setChecked(True)
        vbox_output.addWidget(self.chk_load_canvas)

        self.chk_group_layers = QCheckBox("Group validation result layers under '2027 CBMS MV Results'")
        self.chk_group_layers.setChecked(True)
        vbox_output.addWidget(self.chk_group_layers)

        self.chk_summary_report = QCheckBox("Generate validation audit report (JSON && Summary CSV)")
        self.chk_summary_report.setChecked(False)
        vbox_output.addWidget(self.chk_summary_report)

        container_layout.addWidget(grp_output)
        container_layout.addStretch()

        scroll_area.setWidget(container)
        layout.addWidget(scroll_area)

        return tab

    def _toggle_output_file_visibility(self, checked: bool):
        """Show or hide GeoPackage export destination widget."""
        self.gpkg_widget.setVisible(checked)

    def _on_inputs_changed(self):
        """Update file existence indicators (✓ / ❌) beside input boxes and persist settings."""
        form2 = self.file_form2.filePath().strip()
        points = self.file_points.filePath().strip()
        base = self.file_base.filePath().strip()

        # Check if '2027 CBMS Primary Inputs' group already exists in QGIS layer tree
        proj = self.project if hasattr(self, "project") and self.project else QgsProject.instance()
        if proj and proj.layerTreeRoot() and proj.layerTreeRoot().findGroup("2027 CBMS Primary Inputs"):
            if hasattr(self, "chk_load_inputs_canvas"):
                self.chk_load_inputs_canvas.setChecked(False)

        # Persist paths and load options
        self.settings.setValue(SETTINGS_KEY_FORM2, form2)
        self.settings.setValue(SETTINGS_KEY_POINTS, points)
        self.settings.setValue(SETTINGS_KEY_BASE, base)
        if hasattr(self, "chk_load_inputs_canvas"):
            self.settings.setValue(SETTINGS_KEY_LOAD_INPUTS, self.chk_load_inputs_canvas.isChecked())

        # Update indicator status icons beside input boxes
        if hasattr(self, "lbl_status_form2"):
            if form2:
                if os.path.exists(form2):
                    self.lbl_status_form2.setText("<span style='color: #27AE60; font-weight: bold; font-size: 14px;'>✓</span>")
                    self.lbl_status_form2.setToolTip("Form 2 JSON file exists")
                else:
                    self.lbl_status_form2.setText("<span style='color: #E74C3C; font-weight: bold; font-size: 14px;'>❌</span>")
                    self.lbl_status_form2.setToolTip("Form 2 JSON file not found")
            else:
                self.lbl_status_form2.setText("<span style='color: #E74C3C; font-weight: bold; font-size: 14px;'>❌</span>")
                self.lbl_status_form2.setToolTip("Form 2 JSON file required")

        if hasattr(self, "lbl_status_points"):
            if points:
                if os.path.exists(points):
                    self.lbl_status_points.setText("<span style='color: #27AE60; font-weight: bold; font-size: 14px;'>✓</span>")
                    self.lbl_status_points.setToolTip("Geotagged Building Points file exists")
                else:
                    self.lbl_status_points.setText("<span style='color: #E74C3C; font-weight: bold; font-size: 14px;'>❌</span>")
                    self.lbl_status_points.setToolTip("Geotagged Building Points file not found")
            else:
                self.lbl_status_points.setText("<span style='color: #E74C3C; font-weight: bold; font-size: 14px;'>❌</span>")
                self.lbl_status_points.setToolTip("Geotagged Building Points file required")

        if hasattr(self, "lbl_status_base"):
            if base:
                if os.path.exists(base):
                    self.lbl_status_base.setText("<span style='color: #27AE60; font-weight: bold; font-size: 14px;'>✓</span>")
                    self.lbl_status_base.setToolTip("Base Layers GeoPackage exists")
                else:
                    self.lbl_status_base.setText("<span style='color: #E74C3C; font-weight: bold; font-size: 14px;'>❌</span>")
                    self.lbl_status_base.setToolTip("Base Layers GeoPackage not found")
            else:
                self.lbl_status_base.setText("")
                self.lbl_status_base.setToolTip("Base Layers GeoPackage is optional")

    def _load_saved_settings(self):
        """Load previously saved filepaths and load options from QSettings if available."""
        saved_form2 = self.settings.value(SETTINGS_KEY_FORM2, "", type=str)
        saved_points = self.settings.value(SETTINGS_KEY_POINTS, "", type=str)
        saved_base = self.settings.value(SETTINGS_KEY_BASE, "", type=str)
        saved_load_inputs = self.settings.value(SETTINGS_KEY_LOAD_INPUTS, False, type=bool)

        if saved_form2:
            self.file_form2.setFilePath(saved_form2)
        if saved_points:
            self.file_points.setFilePath(saved_points)
        if saved_base:
            self.file_base.setFilePath(saved_base)

        if hasattr(self, "chk_load_inputs_canvas"):
            self.chk_load_inputs_canvas.setChecked(bool(saved_load_inputs))

        self._on_inputs_changed()

    # -----------------------------------------------------------------------
    # Tab 2: Validation Rules (Dynamic)
    # -----------------------------------------------------------------------
    def _create_tab_validation_rules(self) -> QWidget:
        """
        Create the Validation Rules tab displaying dynamically discovered algorithms.
        Columns:
          - Enable (Checkbox)
          - Validation ID (Algorithm filename without .py)
          - Validation Check Name (First line of shortHelpString)
          - Base Layer (Required / —)
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Filter & Quick Action Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("🔍  Search rules by Validation ID, check name, or keyword...")
        self.edit_filter.setClearButtonEnabled(True)
        self.edit_filter.textChanged.connect(self._filter_rules_table)
        toolbar.addWidget(self.edit_filter, stretch=1)

        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(lambda: self._set_all_rules_checked(True))
        btn_deselect_all = QPushButton("Deselect All")
        btn_deselect_all.clicked.connect(lambda: self._set_all_rules_checked(False))
        btn_base_only = QPushButton("With Base Layer")
        btn_base_only.setToolTip("Select only algorithms requiring Base Layers (.gpkg)")
        btn_base_only.clicked.connect(self._select_base_layer_rules_only)
        btn_no_base = QPushButton("No Base Layer")
        btn_no_base.setToolTip("Select only algorithms that do not require Base Layers")
        btn_no_base.clicked.connect(self._select_no_base_layer_rules_only)

        btn_refresh = QToolButton()
        btn_refresh.setText("🔄")
        btn_refresh.setToolTip("Refresh and re-scan algorithms in gmd_scripts/cbms_mv")
        btn_refresh.clicked.connect(self.refresh_rules)

        toolbar.addWidget(btn_select_all)
        toolbar.addWidget(btn_deselect_all)
        toolbar.addWidget(btn_base_only)
        toolbar.addWidget(btn_no_base)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        # Rules Table
        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(4)
        self.rules_table.setHorizontalHeaderLabels([
            "Enable",
            "Validation ID",
            "Validation Check Name",
            "Base Layer",
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.rules_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.verticalHeader().setVisible(False)

        layout.addWidget(self.rules_table, stretch=1)

        # Rule counts label
        self.lbl_rules_count = QLabel("")
        self.lbl_rules_count.setStyleSheet("font-size: 11px; color: #555;")
        layout.addWidget(self.lbl_rules_count)

        return tab

    def refresh_rules(self):
        """
        Dynamically scan gmd_scripts/cbms_mv and populate the table.
        Preserves previously checked states when refreshing.
        """
        prev_states = {
            val_id: item.checkState()
            for val_id, item in self._rule_checkboxes.items()
        }

        self._rules = discover_cbms_mv_rules(self.cbms_mv_dir)
        self._populate_rules_table(prev_states)
        self._update_rule_counts()

    def _populate_rules_table(self, prev_states: Optional[Dict[str, Qt.CheckState]] = None):
        """Populate the table with the dynamically discovered cbms_mv algorithms."""
        prev_states = prev_states or {}
        self.rules_table.blockSignals(True)
        self.rules_table.setRowCount(len(self._rules))
        self._rule_checkboxes.clear()

        for row, rule in enumerate(self._rules):
            val_id = rule["id"]

            # 0. Checkbox
            item_check = QTableWidgetItem()
            item_check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            default_state = prev_states.get(val_id, Qt.Checked if rule.get("default", True) else Qt.Unchecked)
            item_check.setCheckState(default_state)
            self._rule_checkboxes[val_id] = item_check
            self.rules_table.setItem(row, 0, item_check)

            # 1. Validation ID
            item_id = QTableWidgetItem(val_id)
            item_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_id.setFont(QFont("Consolas", 9, QFont.Bold))
            self.rules_table.setItem(row, 1, item_id)

            # 2. Validation Check Name
            item_name = QTableWidgetItem(rule["name"])
            tooltip_text = f"{rule['name']}\n\n{rule['desc']}\n\nValidation ID: {val_id}\nFile: {rule.get('file_path', '')}"
            item_name.setToolTip(tooltip_text)
            item_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.rules_table.setItem(row, 2, item_name)

            # 3. Base Layer Required indicator
            has_base = rule["has_base"]
            item_base = QTableWidgetItem(" Required " if has_base else " — ")
            item_base.setTextAlignment(Qt.AlignCenter)
            item_base.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if has_base:
                item_base.setForeground(QColor("#2B6CB0"))
                item_base.setFont(QFont("Segoe UI", 9, QFont.Bold))
                item_base.setToolTip("Requires Base Layers (.gpkg) file")
            else:
                item_base.setForeground(QColor("#A0AEC0"))
                item_base.setToolTip("Does not require Base Layers (.gpkg)")
            self.rules_table.setItem(row, 3, item_base)

        self.rules_table.blockSignals(False)
        self.rules_table.itemChanged.connect(self._on_rule_item_changed)

    def _on_rule_item_changed(self, item):
        """Handle checkbox changes in the rules table."""
        if item.column() == 0:
            self._update_rule_counts()

    def _filter_rules_table(self, text: str):
        """Filter rows based on search input matching Validation ID or Validation Check Name."""
        search = text.strip().lower()
        for row in range(self.rules_table.rowCount()):
            if not search:
                self.rules_table.setRowHidden(row, False)
                continue
            val_id = self.rules_table.item(row, 1).text().lower()
            val_name = self.rules_table.item(row, 2).text().lower()
            match = (search in val_id) or (search in val_name)
            self.rules_table.setRowHidden(row, not match)
        self._update_rule_counts()

    def _set_all_rules_checked(self, checked: bool):
        """Batch set all rules checked or unchecked."""
        state = Qt.Checked if checked else Qt.Unchecked
        self.rules_table.blockSignals(True)
        for item in self._rule_checkboxes.values():
            item.setCheckState(state)
        self.rules_table.blockSignals(False)
        self._update_rule_counts()

    def _select_base_layer_rules_only(self):
        """Select only rules that require Base Layers (.gpkg)."""
        self.rules_table.blockSignals(True)
        for rule in self._rules:
            item = self._rule_checkboxes[rule["id"]]
            item.setCheckState(Qt.Checked if rule["has_base"] else Qt.Unchecked)
        self.rules_table.blockSignals(False)
        self._update_rule_counts()

    def _select_no_base_layer_rules_only(self):
        """Select only rules that do not require Base Layers."""
        self.rules_table.blockSignals(True)
        for rule in self._rules:
            item = self._rule_checkboxes[rule["id"]]
            item.setCheckState(Qt.Unchecked if rule["has_base"] else Qt.Checked)
        self.rules_table.blockSignals(False)
        self._update_rule_counts()

    def _update_rule_counts(self):
        """Update the rule counter label, footer status, and KPI metrics."""
        total = len(self._rules)
        enabled = sum(
            1 for item in self._rule_checkboxes.values()
            if item.checkState() == Qt.Checked
        )
        base_req = sum(
            1 for rule in self._rules
            if self._rule_checkboxes[rule["id"]].checkState() == Qt.Checked and rule["has_base"]
        )

        base_str = f" ({base_req} require Base Layer)" if base_req else ""
        self.lbl_rules_count.setText(f"{enabled} of {total} validation rules enabled{base_str}")
        self.lbl_footer_status.setText(f"Ready • {enabled} validation rule(s) selected")
        if hasattr(self, "lbl_header_badge"):
            self.lbl_header_badge.setText(f"{total} RULES DETECTED")
        if hasattr(self, "lbl_kpi_rules"):
            self.lbl_kpi_rules.setText(str(enabled))
        if hasattr(self, "lbl_kpi_base_req"):
            self.lbl_kpi_base_req.setText(str(base_req))

    # -----------------------------------------------------------------------
    # Tab 3: Execution Logs
    # -----------------------------------------------------------------------
    def _create_tab_execution_logs(self) -> QWidget:
        """Create the Execution Logs tab with metrics, progress bar, and console."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # KPI Cards Row
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.lbl_kpi_rules = self._create_kpi_card(kpi_layout, "Rules Queued", "0", "#2980B9")
        self.lbl_kpi_base_req = self._create_kpi_card(kpi_layout, "Requires Base", "0", "#805AD5")
        self.lbl_kpi_flagged = self._create_kpi_card(kpi_layout, "Issues Flagged", "0", "#C0392B")
        self.lbl_kpi_layers = self._create_kpi_card(kpi_layout, "Result Layers", "0", "#27AE60")

        layout.addLayout(kpi_layout)

        # Progress Section
        progress_box = QVBoxLayout()
        progress_box.setSpacing(4)

        self.lbl_progress_status = QLabel("Status: Idle — Ready to run validation")
        self.lbl_progress_status.setStyleSheet("font-weight: bold; font-size: 11px; color: #2C3E50;")
        progress_box.addWidget(self.lbl_progress_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("validationProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_box.addWidget(self.progress_bar)

        layout.addLayout(progress_box)

        # Log Console Header & Utilities
        log_header = QHBoxLayout()
        log_title = QLabel("Execution Log Console:")
        log_title.setStyleSheet("font-weight: bold; color: #2C3E50;")
        log_header.addWidget(log_title)
        log_header.addStretch()

        btn_clear_log = QToolButton()
        btn_clear_log.setText("Clear")
        btn_clear_log.setToolTip("Clear the log console")
        btn_clear_log.clicked.connect(self._clear_log)
        log_header.addWidget(btn_clear_log)

        btn_copy_log = QToolButton()
        btn_copy_log.setText("Copy")
        btn_copy_log.setToolTip("Copy entire log content to clipboard")
        btn_copy_log.clicked.connect(self._copy_log)
        log_header.addWidget(btn_copy_log)

        btn_save_log = QToolButton()
        btn_save_log.setText("Save Log...")
        btn_save_log.setToolTip("Save console output to a text file")
        btn_save_log.clicked.connect(self._save_log)
        log_header.addWidget(btn_save_log)

        layout.addLayout(log_header)

        # Dark Styled Console
        self.txt_console = QTextEdit()
        self.txt_console.setObjectName("consoleLog")
        self.txt_console.setReadOnly(True)
        self.txt_console.setFont(QFont("Consolas", 10))
        layout.addWidget(self.txt_console, stretch=1)

        # Initial Welcome Log Message
        self._log_info("2027 CBMS Form 2 Map Validation (CBMS MV) initialized.")
        self._log_info("Algorithms dynamically discovered from gmd_scripts/cbms_mv.")
        self._log_info("Specify input filepaths in 'Data Config', select rules, and click 'Run Validation'.")

        return tab

    def _create_kpi_card(self, parent_layout: QHBoxLayout, title: str, initial_val: str, color_hex: str) -> QLabel:
        """Helper to create stylized KPI counter card."""
        card = QFrame()
        card.setObjectName("kpiCard")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(10, 8, 10, 8)
        vbox.setSpacing(2)

        lbl_val = QLabel(initial_val)
        lbl_val.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color_hex};")
        lbl_val.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 10px; color: #666; text-transform: uppercase; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignCenter)

        vbox.addWidget(lbl_val)
        vbox.addWidget(lbl_title)
        parent_layout.addWidget(card)

        return lbl_val

    # -----------------------------------------------------------------------
    # Bottom Action Bar
    # -----------------------------------------------------------------------
    def _create_bottom_action_bar(self) -> QWidget:
        """Create the bottom footer action bar."""
        footer = QFrame()
        footer.setObjectName("bottomBar")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(10)

        self.lbl_footer_status = QLabel("Ready")
        self.lbl_footer_status.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self.lbl_footer_status, stretch=1)

        self.btn_run = QPushButton("  ▶  Run Validation  ")
        self.btn_run.setObjectName("btnRun")
        self.btn_run.setShortcut("Ctrl+Return")
        self.btn_run.setToolTip("Run Map Validation (Ctrl+Enter)")
        self.btn_run.clicked.connect(self.run_validation)

        self.btn_reset = QPushButton("Reset Form")
        self.btn_reset.clicked.connect(self._reset_form)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)

        layout.addWidget(self.btn_reset)
        layout.addWidget(self.btn_close)
        layout.addWidget(self.btn_run)

        return footer

    # -----------------------------------------------------------------------
    # Styling & Theming
    # -----------------------------------------------------------------------
    def _apply_styling(self):
        """Apply modern, polished stylesheets conforming to Gemma plugin standards."""
        self.setStyleSheet("""
            QDialog {
                background-color: #F8F9FA;
            }
            #headerBanner {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1A365D, stop:1 #2B6CB0);
                border-radius: 8px;
            }
            #headerTitle {
                color: #FFFFFF;
                font-size: 16px;
                font-weight: bold;
            }
            #headerSubtitle {
                color: #CBD5E0;
                font-size: 11px;
            }
            #headerBadge {
                background-color: #38A169;
                color: #FFFFFF;
                font-size: 9px;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                letter-spacing: 0.5px;
            }
            #sectionGroup {
                font-weight: bold;
                color: #2C3E50;
                border: 1px solid #D0D7DE;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                background-color: #FFFFFF;
            }
            #sectionGroup::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #1A365D;
            }
            #kpiCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
            }
            #validationProgressBar {
                border: 1px solid #CBD5E0;
                border-radius: 4px;
                text-align: center;
                background-color: #EDF2F7;
                height: 18px;
                font-size: 10px;
                font-weight: bold;
            }
            #validationProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3182CE, stop:1 #63B3ED);
                border-radius: 3px;
            }
            #consoleLog {
                background-color: #1A202C;
                color: #E2E8F0;
                border: 1px solid #2D3748;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, monospace;
            }
            #btnRun {
                background-color: #2B6CB0;
                color: #FFFFFF;
                font-weight: bold;
                padding: 7px 18px;
                border-radius: 5px;
                border: none;
                font-size: 12px;
            }
            #btnRun:hover {
                background-color: #2C5282;
            }
            #btnRun:pressed {
                background-color: #1A365D;
            }
            #btnRun:disabled {
                background-color: #A0AEC0;
            }
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                gridline-color: #EDF2F7;
            }
            QTableWidget::item:selected {
                background-color: #EBF8FF;
                color: #2B6CB0;
            }
            QHeaderView::section {
                background-color: #EDF2F7;
                color: #2D3748;
                font-weight: bold;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #CBD5E0;
            }
        """)

    # -----------------------------------------------------------------------
    # Logging Utilities
    # -----------------------------------------------------------------------
    def _get_timestamp(self) -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _log_info(self, message: str):
        ts = self._get_timestamp()
        html = f"<span style='color: #48BB78;'>[{ts}]</span> <span style='color: #63B3ED;'>[INFO]</span> {message}"
        self.txt_console.append(html)
        self.txt_console.moveCursor(QTextCursor.End)

    def _log_step(self, step: str, message: str):
        ts = self._get_timestamp()
        html = f"<span style='color: #48BB78;'>[{ts}]</span> <span style='color: #ECC94B;'>[{step}]</span> <b>{message}</b>"
        self.txt_console.append(html)
        self.txt_console.moveCursor(QTextCursor.End)

    def _log_warning(self, message: str):
        ts = self._get_timestamp()
        html = f"<span style='color: #48BB78;'>[{ts}]</span> <span style='color: #ED8936;'>[WARNING]</span> {message}"
        self.txt_console.append(html)
        self.txt_console.moveCursor(QTextCursor.End)

    def _log_error(self, message: str):
        ts = self._get_timestamp()
        html = f"<span style='color: #48BB78;'>[{ts}]</span> <span style='color: #F56565;'>[ERROR]</span> <b>{message}</b>"
        self.txt_console.append(html)
        self.txt_console.moveCursor(QTextCursor.End)

    def _log_success(self, message: str):
        ts = self._get_timestamp()
        html = f"<span style='color: #48BB78;'>[{ts}]</span> <span style='color: #48BB78;'>[SUCCESS]</span> <b>{message}</b>"
        self.txt_console.append(html)
        self.txt_console.moveCursor(QTextCursor.End)

    def _clear_log(self):
        self.txt_console.clear()

    def _copy_log(self):
        self.txt_console.selectAll()
        self.txt_console.copy()
        cursor = self.txt_console.textCursor()
        cursor.clearSelection()
        self.txt_console.setTextCursor(cursor)
        self.lbl_footer_status.setText("Log copied to clipboard")

    def _save_log(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Validation Log", "cbms_mv_log.txt", "Text Files (*.txt);;All Files (*.*)"
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.txt_console.toPlainText())
                self._log_success(f"Log successfully saved to: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Could not save log file:\n{e}")

    # -----------------------------------------------------------------------
    # Form Reset
    # -----------------------------------------------------------------------
    def _reset_form(self):
        """Reset inputs and table selections to defaults."""
        self.file_form2.setFilePath("")
        self.file_points.setFilePath("")
        self.file_base.setFilePath("")
        self.radio_memory.setChecked(True)
        self.file_widget_gpkg.setFilePath("")
        self._set_all_rules_checked(True)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Status: Idle — Ready to run validation")
        self.lbl_kpi_flagged.setText("0")
        self.lbl_kpi_layers.setText("0")
        self._on_inputs_changed()
        self._log_info("Form reset to default settings.")

    # -----------------------------------------------------------------------
    # Dynamic Algorithm Loader
    # -----------------------------------------------------------------------
    def _get_algorithm_instance(self, val_id: str) -> Optional[QgsProcessingAlgorithm]:
        """
        Locate and instantiate a QgsProcessingAlgorithm for the given val_id.
        Tries:
          1. QgsApplication.processingRegistry() (if registered in GmdPipelineProvider)
          2. Package relative import: ...gmd_scripts.cbms_mv.{val_id}
          3. Direct file location spec loader
        """
        alg = None
        # 1. Processing registry check
        reg_alg = QgsApplication.processingRegistry().algorithmById(f"gmd_pipeline:{val_id}")
        if reg_alg:
            alg = reg_alg.createInstance()

        # 2. Package relative import
        if not alg:
            try:
                import importlib
                mod = importlib.import_module(f"...gmd_scripts.cbms_mv.{val_id}", package=__package__)
                for attr in dir(mod):
                    cls = getattr(mod, attr)
                    if (
                        isinstance(cls, type)
                        and issubclass(cls, QgsProcessingAlgorithm)
                        and cls is not QgsProcessingAlgorithm
                    ):
                        alg = cls()
                        break
            except Exception:
                pass

        # 3. Direct file spec loader fallback
        if not alg:
            file_path = os.path.join(self.cbms_mv_dir, f"{val_id}.py")
            if os.path.exists(file_path):
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(f"gmd_scripts.cbms_mv.{val_id}", file_path)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        mod.__package__ = "gmd_scripts.cbms_mv"
                        spec.loader.exec_module(mod)
                        for attr in dir(mod):
                            cls = getattr(mod, attr)
                            if (
                                isinstance(cls, type)
                                and issubclass(cls, QgsProcessingAlgorithm)
                                and cls is not QgsProcessingAlgorithm
                            ):
                                alg = cls()
                                break
                except Exception as exc:
                    self._log_error(f"Could not load algorithm file '{val_id}.py': {exc}")

        # Ensure initAlgorithm() has been called so parameterDefinitions() is populated
        if alg and hasattr(alg, "initAlgorithm"):
            try:
                if not alg.parameterDefinitions():
                    alg.initAlgorithm()
            except Exception:
                pass

        return alg

    def _get_or_create_layer_group(self, group_name: str):
        """Find or create a top-level group in the QGIS Layer Tree."""
        proj = self.project if self.project else QgsProject.instance()
        root = proj.layerTreeRoot()
        grp = root.findGroup(group_name)
        if not grp:
            grp = root.insertGroup(0, group_name)
        return grp

    def _discover_gpkg_sublayer_uris_and_names(self, gpkg_path: str) -> List[tuple]:
        """Discover all vector sublayer names and URIs inside a GeoPackage file."""
        sublayer_items = []

        # Strategy 1: QgsProviderRegistry OGR provider metadata
        try:
            md = QgsProviderRegistry.instance().providerMetadata("ogr")
            if md:
                subs = md.sublayers(gpkg_path)
                for sub in subs:
                    uri = sub.uri() if hasattr(sub, "uri") else f"{gpkg_path}|layername={sub.name()}"
                    name = sub.name() if hasattr(sub, "name") else os.path.basename(gpkg_path)
                    sublayer_items.append((uri, name))
        except Exception:
            pass

        # Strategy 2: SQLite gpkg_contents table query fallback
        if not sublayer_items:
            try:
                import sqlite3
                conn = sqlite3.connect(gpkg_path)
                cursor = conn.cursor()
                cursor.execute("SELECT table_name FROM gpkg_contents WHERE data_type IN ('features', 'attributes')")
                rows = cursor.fetchall()
                conn.close()
                for r in rows:
                    tname = r[0]
                    sub_uri = f"{gpkg_path}|layername={tname}"
                    sublayer_items.append((sub_uri, tname))
            except Exception:
                pass

        # Strategy 3: Single layer fallback if no sublayers discovered
        if not sublayer_items:
            sublayer_items.append((gpkg_path, os.path.basename(gpkg_path)))

        return sublayer_items

    def _load_primary_input_sources_if_requested(self, form2_path: str, points_path: str, base_path: str):
        """Load checked primary input data sources into their own QGIS Layer Group."""
        if not hasattr(self, "chk_load_inputs_canvas") or not self.chk_load_inputs_canvas.isChecked():
            return

        proj = self.project if self.project else QgsProject.instance()
        group_name = "2027 CBMS Primary Inputs"
        inputs_group = self._get_or_create_layer_group(group_name)

        # 1. Form 2 Data File (.json) using load_cbms_json_to_layer from gmdhelpers
        if form2_path and os.path.exists(form2_path):
            try:
                self._log_info(f"Loading Form 2 JSON into QGIS Layers via load_cbms_json_to_layer: {os.path.basename(form2_path)}")
                layer_name = f"Form 2 ({os.path.basename(form2_path)})"
                table_layer = load_cbms_json_to_layer(form2_path, layer_name=layer_name, add_to_project=False)
                if table_layer and table_layer.isValid():
                    proj.addMapLayer(table_layer, False)
                    inputs_group.addLayer(table_layer)
                    self._log_success(f"Form 2 JSON table layer '{layer_name}' loaded into group '{group_name}'.")
                else:
                    self._log_error(f"Form 2 JSON table layer is invalid: {form2_path}")
            except Exception as e:
                self._log_error(f"Failed to load Form 2 JSON into QGIS Layers: {e}")

        # 2. Geotagged Building Points (.geojson)
        if points_path and os.path.exists(points_path):
            try:
                self._log_info(f"Loading Geotagged Building Points into QGIS Layers: {os.path.basename(points_path)}")
                layer_name = f"Building Points ({os.path.basename(points_path)})"
                pt_layer = QgsVectorLayer(points_path, layer_name, "ogr")
                if pt_layer.isValid():
                    proj.addMapLayer(pt_layer, False)
                    inputs_group.addLayer(pt_layer)
                    self._log_success(f"Building Points layer '{layer_name}' loaded into group '{group_name}'.")
                else:
                    self._log_error(f"Geotagged Building Points layer is invalid: {points_path}")
            except Exception as e:
                self._log_error(f"Failed to load Geotagged Building Points into QGIS Layers: {e}")

        # 3. Base Layers (.gpkg) - Loads ALL sublayers in the GPKG file into group
        if base_path and os.path.exists(base_path):
            try:
                self._log_info(f"Loading all Base Layers GPKG sublayers into group '{group_name}': {os.path.basename(base_path)}")
                sublayer_items = self._discover_gpkg_sublayer_uris_and_names(base_path)
                loaded_count = 0

                for sub_uri, sub_name in sublayer_items:
                    blayer = QgsVectorLayer(sub_uri, sub_name, "ogr")
                    if blayer.isValid():
                        proj.addMapLayer(blayer, False)
                        inputs_group.addLayer(blayer)
                        loaded_count += 1

                if loaded_count > 0:
                    self._log_success(f"Successfully loaded {loaded_count} Base Layer(s) into group '{group_name}'.")
                else:
                    self._log_error(f"Could not load any valid sublayers from Base Layers GPKG: {base_path}")
            except Exception as e:
                self._log_error(f"Failed to load Base Layers into QGIS Layers Panel: {e}")

        # Uncheck canvas loading checkbox after loading inputs to prevent duplicate loading
        self.chk_load_inputs_canvas.setChecked(False)

    # -----------------------------------------------------------------------
    # Execution Logic: Iterating Selected Algorithms
    # -----------------------------------------------------------------------
    def run_validation(self):
        """
        Execute the validation pipeline by iterating through the enabled
        algorithms in gmd_scripts/cbms_mv and passing the three standardized
        Input Data Sources.
        """
        if processing is None:
            QMessageBox.critical(
                self,
                "Processing Error",
                "QGIS Processing framework is unavailable in this environment.",
            )
            return

        form2_path = self.file_form2.filePath().strip()
        points_path = self.file_points.filePath().strip()
        base_path = self.file_base.filePath().strip()

        # 1. Verify primary file inputs
        if not form2_path:
            QMessageBox.warning(
                self,
                "Missing Form 2 Data File",
                "Please specify the Form 2 Data File (.json) in the 'Data Config' tab.",
            )
            self.tab_widget.setCurrentIndex(0)
            return

        if not points_path:
            QMessageBox.warning(
                self,
                "Missing Geotagged Points File",
                "Please specify the Geotagged Building Points (.geojson) in the 'Data Config' tab.",
            )
            self.tab_widget.setCurrentIndex(0)
            return

        if not os.path.exists(form2_path):
            QMessageBox.critical(
                self,
                "File Not Found",
                f"Form 2 Data File does not exist:\n{form2_path}",
            )
            self.tab_widget.setCurrentIndex(0)
            return

        if not os.path.exists(points_path):
            QMessageBox.critical(
                self,
                "File Not Found",
                f"Geotagged Building Points file does not exist:\n{points_path}",
            )
            self.tab_widget.setCurrentIndex(0)
            return

        # 2. Get enabled validation rules
        selected_rules = [
            rule for rule in self._rules
            if self._rule_checkboxes[rule["id"]].checkState() == Qt.Checked
        ]

        if not selected_rules:
            QMessageBox.warning(
                self,
                "No Rules Selected",
                "Please enable at least one validation rule in the 'Validation Rules' tab.",
            )
            self.tab_widget.setCurrentIndex(1)
            return

        # 3. Check Base Layer dependency
        rules_requiring_base = [r for r in selected_rules if r["has_base"]]
        if rules_requiring_base and (not base_path or not os.path.exists(base_path)):
            rule_list = "\n".join(f"  • [{r['id']}] {r['name']}" for r in rules_requiring_base)
            reply = QMessageBox.question(
                self,
                "Base Layers (.gpkg) Not Provided",
                f"The following {len(rules_requiring_base)} selected rule(s) require a Base Layers (.gpkg) file:\n\n"
                f"{rule_list}\n\n"
                f"Do you want to proceed by automatically skipping these {len(rules_requiring_base)} rule(s)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                self.tab_widget.setCurrentIndex(0)
                return

            selected_rules = [r for r in selected_rules if not r["has_base"]]
            if not selected_rules:
                QMessageBox.warning(
                    self,
                    "No Rules to Run",
                    "All selected rules require Base Layers (.gpkg). Please provide the Base Layers file to continue.",
                )
                self.tab_widget.setCurrentIndex(0)
                return

        # 4. Switch to Execution Logs tab and initialize session
        self.tab_widget.setCurrentIndex(2)
        self.btn_run.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Status: Initializing validation session...")

        self._log_step("INIT", "=== 2027 CBMS Form 2 Map Validation Session Started ===")
        self._log_info(f"Form 2 Data File (.json)    : {form2_path}")
        self._log_info(f"Geotagged Points (.geojson) : {points_path}")
        self._log_info(f"Base Layers (.gpkg)         : {base_path if base_path else '(None provided)'}")
        self._log_info(f"Destination                 : {'In-Memory Layers' if self.radio_memory.isChecked() else self.file_widget_gpkg.filePath()}")
        self._log_info(f"Queued Validation Algorithms: {len(selected_rules)}")

        # 5. Execution context and feedback
        self.context = QgsProcessingContext()
        self.context.setProject(self.project or QgsProject.instance())
        feedback = ProcessingFeedbackBridge(self._log_info, self._log_warning, self._log_error)

        # Load primary input data sources into QGIS Layers Panel if requested by user
        self._load_primary_input_sources_if_requested(form2_path, points_path, base_path)

        total_rules = len(selected_rules)
        total_flagged_issues = 0
        total_output_layers = 0
        execution_summary: List[Dict[str, Any]] = []

        gpkg_export_path = self.file_widget_gpkg.filePath().strip() if self.radio_file.isChecked() else None

        # 6. Iterate through all selected algorithms
        for i, rule in enumerate(selected_rules):
            val_id = rule["id"]
            check_name = rule["name"]

            pct = int((i / total_rules) * 100)
            self.progress_bar.setValue(pct)
            self.lbl_progress_status.setText(f"Status: Executing [{val_id}] ({i+1}/{total_rules})...")
            self._log_step("RUN", f"[{i+1}/{total_rules}] Running '{val_id}'")
            self._log_info(f"Check: {check_name}")

            QApplication.processEvents()

            # Locate algorithm instance or registered algorithm ID
            reg_id = f"gmd_pipeline:{val_id}"
            is_registered = QgsApplication.processingRegistry().algorithmById(reg_id) is not None
            alg = self._get_algorithm_instance(val_id)

            if not is_registered and not alg:
                self._log_error(f"Failed to instantiate algorithm '{val_id}'. Skipping.")
                execution_summary.append({
                    "id": val_id,
                    "name": check_name,
                    "status": "Failed (Could not load)",
                    "features_flagged": 0,
                })
                continue

            # Pass registered ID string if registered in QGIS (native Processing engine execution),
            # otherwise pass the alg instance.
            alg_target = reg_id if is_registered else alg

            # Assemble standardized parameter dictionary
            # Standard parameters for all CBMS MV algorithms:
            params: Dict[str, Any] = {
                "INPUT_DATA": form2_path,
                "INPUT_LAYER": points_path,
                "OUTPUT": "TEMPORARY_OUTPUT",
            }

            # Always pass BASE_LAYER if provided
            if base_path:
                params["BASE_LAYER"] = base_path

            # If user selected GeoPackage export instead of in-memory
            if gpkg_export_path:
                params["OUTPUT"] = f"ogr:dbname='{gpkg_export_path}' table='{val_id}' (geom)"

            # Inspect algorithm parameter definitions for any auxiliary parameters
            param_defs = [p.name() for p in alg.parameterDefinitions()] if alg else []
            if "OUTPUT_ERRORS" in param_defs:
                params["OUTPUT_ERRORS"] = "TEMPORARY_OUTPUT"
            if "OPEN_FOR_EDITING" in param_defs:
                params["OPEN_FOR_EDITING"] = False

            # Execute the algorithm
            try:
                result = processing.run(alg_target, params, context=self.context, feedback=feedback)
            except Exception as exc:
                self._log_error(f"Execution error running '{val_id}': {exc}")
                execution_summary.append({
                    "id": val_id,
                    "name": check_name,
                    "status": f"Error: {exc}",
                    "features_flagged": 0,
                })
                continue

            # Process output layer
            flagged_count = 0
            out_dest = result.get("OUTPUT")
            out_layer = None

            if out_dest:
                if isinstance(out_dest, QgsVectorLayer):
                    out_layer = out_dest
                elif isinstance(out_dest, str):
                    proj = self.project if self.project else QgsProject.instance()
                    out_layer = QgsProcessingUtils.mapLayerFromString(out_dest, self.context)
                    if not out_layer and proj:
                        out_layer = proj.mapLayer(out_dest)
                    if not out_layer and gpkg_export_path and os.path.exists(gpkg_export_path):
                        gpkg_layer_uri = f"{gpkg_export_path}|layername={val_id}"
                        out_layer = QgsVectorLayer(gpkg_layer_uri, val_id, "ogr")
                    if not out_layer and os.path.exists(out_dest):
                        out_layer = QgsVectorLayer(out_dest, val_id, "ogr")

            if out_layer and out_layer.isValid():
                flagged_count = out_layer.featureCount()
                total_flagged_issues += flagged_count

                if flagged_count > 0:
                    self._log_warning(f"'{val_id}' completed: {flagged_count:,} issue(s) flagged.")
                    total_output_layers += 1

                    # Add layer to QGIS canvas
                    if self.chk_load_canvas.isChecked():
                        if hasattr(self.context, "takeResultLayer"):
                            try:
                                take_lyr = self.context.takeResultLayer(out_dest if isinstance(out_dest, str) else out_layer.id())
                                if take_lyr and take_lyr.isValid():
                                    out_layer = take_lyr
                            except Exception:
                                pass

                        out_layer.setName(f"{val_id} ({flagged_count})")
                        proj = self.project if self.project else QgsProject.instance()

                        if self.chk_group_layers.isChecked():
                            grp = self._get_or_create_layer_group("2027 CBMS MV Results")
                            proj.addMapLayer(out_layer, False)
                            grp.addLayer(out_layer)
                        else:
                            proj.addMapLayer(out_layer)
                else:
                    self._log_success(f"'{val_id}' completed: 0 issues flagged (Clean).")

            # Check auxiliary output (e.g. remarks error summary)
            aux_dest = result.get("OUTPUT_ERRORS")
            if aux_dest:
                aux_layer = None
                if isinstance(aux_dest, QgsVectorLayer):
                    aux_layer = aux_dest
                elif isinstance(aux_dest, str):
                    proj = self.project if self.project else QgsProject.instance()
                    aux_layer = QgsProcessingUtils.mapLayerFromString(aux_dest, self.context)
                    if not aux_layer and proj:
                        aux_layer = proj.mapLayer(aux_dest)

                if aux_layer and aux_layer.isValid() and aux_layer.featureCount() > 0:
                    if self.chk_load_canvas.isChecked():
                        if hasattr(self.context, "takeResultLayer"):
                            try:
                                take_aux = self.context.takeResultLayer(aux_dest if isinstance(aux_dest, str) else aux_layer.id())
                                if take_aux and take_aux.isValid():
                                    aux_layer = take_aux
                            except Exception:
                                pass

                        aux_layer.setName(f"{val_id}_summary ({aux_layer.featureCount()})")
                        proj = self.project if self.project else QgsProject.instance()

                        if self.chk_group_layers.isChecked():
                            grp = self._get_or_create_layer_group("2027 CBMS MV Results")
                            proj.addMapLayer(aux_layer, False)
                            grp.addLayer(aux_layer)
                        else:
                            proj.addMapLayer(aux_layer)

            # Record summary entry
            execution_summary.append({
                "id": val_id,
                "name": check_name,
                "status": "Flagged" if flagged_count > 0 else "Passed",
                "features_flagged": flagged_count,
            })

            # Update live KPIs
            self.lbl_kpi_flagged.setText(f"{total_flagged_issues:,}")
            self.lbl_kpi_layers.setText(str(total_output_layers))

        # 7. Finalize execution session
        self.progress_bar.setValue(100)
        self.lbl_progress_status.setText("Status: Validation complete!")
        self.btn_run.setEnabled(True)

        self._log_step("SUMMARY", "=== Validation Execution Finished ===")
        self._log_info(f"Total Algorithms Executed : {len(execution_summary)}")
        self._log_info(f"Total Issues Flagged      : {total_flagged_issues:,}")
        self._log_info(f"Generated Result Layers   : {total_output_layers}")

        # Generate summary audit report file if selected
        if self.chk_summary_report.isChecked():
            report_dir = os.path.dirname(points_path)
            report_path = os.path.join(report_dir, f"cbms_mv_summary_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            try:
                with open(report_path, "w", encoding="utf-8") as rf:
                    json.dump({
                        "session_date": datetime.datetime.now().isoformat(),
                        "form2_data": form2_path,
                        "points_data": points_path,
                        "base_data": base_path,
                        "total_algorithms_run": len(execution_summary),
                        "total_issues_flagged": total_flagged_issues,
                        "results": execution_summary,
                    }, rf, indent=2)
                self._log_success(f"Audit report saved to: {report_path}")
            except Exception as r_exc:
                self._log_warning(f"Could not write audit report file: {r_exc}")

        self.lbl_footer_status.setText(f"Validation complete • {total_flagged_issues:,} issue(s) flagged")
