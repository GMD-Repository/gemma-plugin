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
import csv
import datetime
from typing import Optional, List, Dict, Any, Tuple

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
    QgsFeature,
    QgsFeatureRequest,
)
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal, QSize
from qgis.PyQt.QtGui import QIcon, QColor, QFont, QTextCursor, QKeySequence
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
    QStackedWidget,
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
    QShortcut,
)

try:
    import processing
except ImportError:
    processing = None

SETTINGS_KEY_FORM2 = "gemma/cbmsmv/form2_csv_path"
SETTINGS_KEY_FORM2_LEGACY = "gemma/cbmsmv/form2_json_path"
SETTINGS_KEY_POINTS = "gemma/cbmsmv/points_geojson_path"
SETTINGS_KEY_BASE = "gemma/cbmsmv/base_gpkg_path"
SETTINGS_KEY_LOAD_INPUTS = "gemma/cbmsmv/load_inputs_in_layers"
SETTINGS_KEY_SELECTED_RULES = "gemma/cbmsmv/selected_rules"

try:
    from ...gmd_scripts.gmdhelpers import load_cbms_json_to_layer, load_cbms_csv_to_layer
except (ImportError, ValueError):
    try:
        from gmd_scripts.gmdhelpers import load_cbms_json_to_layer, load_cbms_csv_to_layer
    except (ImportError, ValueError):
        _plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if _plugin_root not in sys.path:
            sys.path.insert(0, _plugin_root)
        from gmd_scripts.gmdhelpers import load_cbms_json_to_layer, load_cbms_csv_to_layer

try:
    from .cbmsmv_review_dock import CbmsMvReviewDock, is_valid_qobject
except (ImportError, ValueError):
    try:
        from cbmsmv_review_dock import CbmsMvReviewDock, is_valid_qobject
    except (ImportError, ValueError):
        _ref_dir = os.path.dirname(__file__)
        if _ref_dir not in sys.path:
            sys.path.insert(0, _ref_dir)
        from cbmsmv_review_dock import CbmsMvReviewDock, is_valid_qobject

try:
    from .cbms_mv_fix import get_fix_handler, has_fix
except (ImportError, ValueError):
    try:
        from cbms_mv_fix import get_fix_handler, has_fix
    except (ImportError, ValueError):
        _fix_dir = os.path.join(os.path.dirname(__file__), "cbms_mv_fix")
        if _fix_dir not in sys.path:
            sys.path.insert(0, _fix_dir)
        try:
            from cbms_mv_fix import get_fix_handler, has_fix
        except Exception:
            get_fix_handler = lambda v: None
            has_fix = lambda v: False


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

        # Standard desktop window controls: Minimize, Maximize, Close
        self.setWindowFlags(
            (self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            | Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )

        self._rules: List[Dict[str, Any]] = []
        self._rule_checkboxes: Dict[str, QTableWidgetItem] = {}
        self._result_layers: Dict[str, Dict[str, Any]] = {}
        self._execution_summary: List[Dict[str, Any]] = []
        self._is_validating = False
        self._active_review_dock = None
        self._pending_json_edits: Dict[str, Dict[str, Any]] = {}

        self.context = QgsProcessingContext()
        self.context.setProject(self.project)

        # Scoped Ctrl+S shortcut for saving changes without conflicting with QGIS global shortcuts
        self._save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self._save_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._save_shortcut.activated.connect(self._on_shortcut_save)

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
        """Initialize and assemble the main layout, view stack, and persistent action bar."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. Top Navigation Bar (compact)
        nav_bar = self._create_top_bar()
        main_layout.addWidget(nav_bar)

        # 2. Main View Stack: Page 0 = Results Workspace, Page 1 = Configuration View
        self.main_stack = QStackedWidget()
        self.main_stack.setObjectName("mainStack")

        self.page_results = self._create_page_results()
        self.page_config = self._create_page_config()

        self.main_stack.addWidget(self.page_results)  # index 0: Results
        self.main_stack.addWidget(self.page_config)   # index 1: Configuration

        # Backward compatibility alias
        self.tab_widget = self.config_tab_widget

        main_layout.addWidget(self.main_stack, stretch=1)

        # 3. Bottom Action Bar
        bottom_bar = self._create_bottom_action_bar()
        main_layout.addWidget(bottom_bar)

    # -----------------------------------------------------------------------
    # Top Navigation Bar
    # -----------------------------------------------------------------------
    def _create_top_bar(self) -> QWidget:
        """Create a compact top navigation bar with view switch button."""
        bar = QFrame()
        bar.setObjectName("topNavBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 2, 4, 4)
        bar_layout.setSpacing(10)

        bar_layout.addStretch()

        # View Switch Button
        self.btn_header_config = QPushButton("⚙️  Configuration")
        self.btn_header_config.setObjectName("btnHeaderConfig")
        self.btn_header_config.setToolTip("Configure input files, validation rules, and inspect logs")
        self.btn_header_config.clicked.connect(self._toggle_view)
        bar_layout.addWidget(self.btn_header_config)

        return bar

    # -----------------------------------------------------------------------
    # View Switching & Navigation
    # -----------------------------------------------------------------------
    def _toggle_view(self):
        """Toggle between Results Workspace and Configuration View."""
        if self.main_stack.currentIndex() == 0:
            self._switch_to_config()
        else:
            self._switch_to_results()

    def _switch_to_results(self):
        """Switch to Results Workspace (Page 0)."""
        self.main_stack.setCurrentIndex(0)
        if hasattr(self, "btn_header_config"):
            self.btn_header_config.setText("⚙️  Configuration")
            self.btn_header_config.setToolTip("Configure input files, validation rules, and inspect logs")

    def _switch_to_config(self, tab_index: Optional[int] = None):
        """Switch to Configuration View (Page 1), optionally selecting a tab."""
        self.main_stack.setCurrentIndex(1)
        if tab_index is not None and hasattr(self, "config_tab_widget"):
            self.config_tab_widget.setCurrentIndex(tab_index)
        if hasattr(self, "btn_header_config"):
            self.btn_header_config.setText("Home")
            self.btn_header_config.setToolTip("Return to Results Workspace")

    # -----------------------------------------------------------------------
    # Page 1: Configuration View
    # -----------------------------------------------------------------------
    def _create_page_config(self) -> QWidget:
        """
        Create the Configuration View page housing the 3 original tabs:
          1. Data Config
          2. Validation Rules
          3. Execution Logs
        """
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 2, 4, 4)

        lbl_title = QLabel("⚙️  Configuration & Validation Rules")
        lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1A365D;")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.config_tab_widget = QTabWidget()
        self.config_tab_widget.setObjectName("configTabWidget")

        self.tab_data_config = self._create_tab_data_config()
        self.tab_validation_rules = self._create_tab_validation_rules()
        self.tab_execution_logs = self._create_tab_execution_logs()

        self.config_tab_widget.addTab(self.tab_data_config, "📋  Data Config")
        self.config_tab_widget.addTab(self.tab_validation_rules, "⚙️  Validation Rules")
        self.config_tab_widget.addTab(self.tab_execution_logs, "📊  Execution Logs")

        layout.addWidget(self.config_tab_widget, stretch=1)
        return page

    # -----------------------------------------------------------------------
    # Page 0: Main Screen Results Workspace
    # -----------------------------------------------------------------------
    def _create_page_results(self) -> QWidget:
        """Create the Results Workspace with empty state and dynamic result tabs."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.results_stack = QStackedWidget()
        self.results_stack.setObjectName("resultsStack")

        # Subpage 0: Empty state
        self.empty_state_widget = self._create_empty_state_widget()
        self.results_stack.addWidget(self.empty_state_widget)

        # Subpage 1: Results tabs
        self.results_tab_widget = QTabWidget()
        self.results_tab_widget.setObjectName("resultsTabWidget")
        self.results_stack.addWidget(self.results_tab_widget)

        layout.addWidget(self.results_stack, stretch=1)
        return page

    def _create_empty_state_widget(self) -> QWidget:
        """Create a clean empty state card shown before any validation has been executed."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(30, 40, 30, 40)

        card = QFrame()
        card.setObjectName("emptyStateCard")
        card.setMaximumWidth(620)
        card.setStyleSheet("""
            #emptyStateCard {
                background-color: #FFFFFF;
                border: 2px dashed #CBD5E0;
                border-radius: 12px;
                padding: 32px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel("📋")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 48px;")
        card_layout.addWidget(icon_lbl)

        title_lbl = QLabel("No Validation Results Yet")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 600; color: #1A365D;")
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Configure your primary input files (Form 2 JSON, Geotagged Building Points GeoJSON, and Base GPKG) "
            "and select validation rules in Configuration, then click Run Validation.\n\n"
            "Flagged issues will be displayed here in separate tabs with full attribute inspection and QGIS canvas zoom."
        )
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 11.5px; color: #718096; line-height: 1.5;")
        card_layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignCenter)

        btn_cfg = QPushButton("  ⚙️  Open Configuration  ")
        btn_cfg.setStyleSheet("""
            QPushButton {
                background-color: #EDF2F7;
                color: #2D3748;
                font-weight: 600;
                padding: 8px 16px;
                border-radius: 6px;
                border: 1px solid #CBD5E0;
                font-size: 11.5px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                color: #1A202C;
            }
        """)
        btn_cfg.clicked.connect(lambda: self._switch_to_config(0))

        btn_quick_run = QPushButton("  ▶  Run Validation  ")
        btn_quick_run.setStyleSheet("""
            QPushButton {
                background-color: #2B6CB0;
                color: #FFFFFF;
                font-weight: 600;
                padding: 8px 20px;
                border-radius: 6px;
                border: none;
                font-size: 11.5px;
            }
            QPushButton:hover {
                background-color: #2C5282;
            }
        """)
        btn_quick_run.clicked.connect(self.run_validation)

        btn_row.addWidget(btn_cfg)
        btn_row.addWidget(btn_quick_run)
        card_layout.addLayout(btn_row)

        layout.addWidget(card)
        return container

    def _populate_results_workspace(
        self,
        execution_summary: List[Dict[str, Any]],
        result_layers: Dict[str, Dict[str, Any]],
    ):
        """
        Populate the Results Workspace with:
          1. Tab 0: Summary Overview (Scorecard table of all executed rules)
          2. Dynamic Tabs: One tab per rule that produced flagged features (>0)
        """
        self.results_tab_widget.clear()

        # Tab 0: Summary Overview
        summary_tab = self._create_summary_tab(execution_summary, result_layers)
        self.results_tab_widget.addTab(summary_tab, "📊  Summary Overview")

        # Dynamic Error Tabs
        for val_id, item in result_layers.items():
            layer = item["layer"]
            rule = item["rule"]
            count = item["count"]
            check_name = rule["name"]

            err_tab = self._create_result_layer_tab(val_id, check_name, layer, count)
            tab_title = f"🔴  {val_id} ({count})"
            tab_index = self.results_tab_widget.addTab(err_tab, tab_title)
            self.results_tab_widget.setTabToolTip(tab_index, f"{check_name} — {count} flagged feature(s)")

        # Switch subpage of results_stack to show the tab widget
        self.results_stack.setCurrentIndex(1)
        self.results_tab_widget.setCurrentIndex(0)

    def _create_summary_tab(
        self,
        execution_summary: List[Dict[str, Any]],
        result_layers: Dict[str, Dict[str, Any]],
    ) -> QWidget:
        """Create the Summary Scorecard tab showing all executed rules."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top KPI Scorecards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        total_rules = len(execution_summary)
        flagged_rules = sum(1 for s in execution_summary if s.get("features_flagged", 0) > 0)
        clean_rules = sum(1 for s in execution_summary if s.get("features_flagged", 0) == 0 and not str(s.get("status", "")).startswith(("Error", "Failed")))
        total_flags = sum(s.get("features_flagged", 0) for s in execution_summary)

        self._create_kpi_card(kpi_row, "Rules Tested", str(total_rules), "#2980B9")
        self._create_kpi_card(kpi_row, "Passed (Clean)", str(clean_rules), "#27AE60")
        self._create_kpi_card(kpi_row, "Rules Flagged", str(flagged_rules), "#E53E3E")
        self._create_kpi_card(kpi_row, "Total Issues", f"{total_flags:,}", "#C53030")

        layout.addLayout(kpi_row)

        # Scorecard Table
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            "Status",
            "Validation ID",
            "Validation Check Name",
            "Issues Flagged",
            "Action",
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setRowCount(len(execution_summary))

        for row, s in enumerate(execution_summary):
            val_id = s.get("id", "")
            name = s.get("name", "")
            status = s.get("status", "")
            flags = s.get("features_flagged", 0)
            has_layer = val_id in result_layers

            # 0. Status Badge
            if flags > 0:
                status_item = QTableWidgetItem(" 🔴 Flagged ")
                status_item.setForeground(QColor("#C53030"))
            elif str(status).startswith(("Error", "Failed")):
                status_item = QTableWidgetItem(" ⚠️ Error ")
                status_item.setForeground(QColor("#DD6B20"))
            else:
                status_item = QTableWidgetItem(" 🟢 Clean ")
                status_item.setForeground(QColor("#27AE60"))
            status_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, status_item)

            # 1. Validation ID
            id_item = QTableWidgetItem(val_id)
            id_item.setFont(QFont("Consolas", 9))
            table.setItem(row, 1, id_item)

            # 2. Check Name
            name_item = QTableWidgetItem(name)
            table.setItem(row, 2, name_item)

            # 3. Issues Flagged
            flags_item = QTableWidgetItem(f"{flags:,}")
            flags_item.setTextAlignment(Qt.AlignCenter)
            if flags > 0:
                flags_item.setForeground(QColor("#C53030"))
                flags_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            else:
                flags_item.setForeground(QColor("#27AE60"))
            table.setItem(row, 3, flags_item)

            # 4. Action Button
            if flags > 0 and has_layer:
                btn_view = QPushButton("View Tab ➔")
                btn_view.setStyleSheet("""
                    QPushButton {
                        background-color: #EDF2F7;
                        color: #2B6CB0;
                        font-weight: bold;
                        border: 1px solid #CBD5E0;
                        border-radius: 3px;
                        padding: 3px 8px;
                        font-size: 10px;
                    }
                    QPushButton:hover {
                        background-color: #BEE3F8;
                    }
                """)
                btn_view.clicked.connect(lambda checked=False, vid=val_id: self._jump_to_result_tab(vid))
                table.setCellWidget(row, 4, btn_view)
            else:
                empty_act = QTableWidgetItem("—")
                empty_act.setTextAlignment(Qt.AlignCenter)
                empty_act.setForeground(QColor("#A0AEC0"))
                table.setItem(row, 4, empty_act)

        # Connect double-click on row to jump to tab if flagged
        def _on_summary_row_double_clicked(row, col):
            id_it = table.item(row, 1)
            if id_it:
                self._jump_to_result_tab(id_it.text())
        table.cellDoubleClicked.connect(_on_summary_row_double_clicked)

        layout.addWidget(table, stretch=1)
        return tab

    def _jump_to_result_tab(self, val_id: str):
        """Switch results_tab_widget to the tab matching val_id."""
        if not val_id:
            return
        target = str(val_id)
        for ti in range(1, self.results_tab_widget.count()):
            if target in self.results_tab_widget.tabText(ti):
                self.results_tab_widget.setCurrentIndex(ti)
                break

    def _create_result_layer_tab(
        self,
        val_id: str,
        check_name: str,
        layer: QgsVectorLayer,
        count: int,
    ) -> QWidget:
        """Create an interactive feature table tab with in-place cell editing, multiselect, and fix actions."""
        tab = QWidget()
        tab.setProperty("val_id", val_id)
        tab.setProperty("check_name", check_name)

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Mini Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Title & count
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        lbl_vname = QLabel(f"<b>{check_name}</b>")
        lbl_vname.setToolTip(f"Validation ID: {val_id}")
        lbl_vname.setStyleSheet("font-size: 11px; color: #1A365D;")
        if count == 0:
            lbl_vcount = QLabel(
                "<span style='color: #2F855A; font-weight: bold;'>✓ 0 flagged features.</span> "
                "All issues for this validation check are resolved!"
            )
        else:
            lbl_vcount = QLabel(
                f"<span style='color: #C53030; font-weight: bold;'>{count:,}</span> flagged feature(s) detected. "
                f"Click row to zoom; double-click cell to edit in-place."
            )
        lbl_vcount.setStyleSheet("font-size: 10px; color: #4A5568;")
        title_box.addWidget(lbl_vname)
        title_box.addWidget(lbl_vcount)
        toolbar.addLayout(title_box, stretch=1)

        # Search filter
        edit_filter = QLineEdit()
        edit_filter.setPlaceholderText("🔍  Filter rows in this table...")
        edit_filter.setClearButtonEnabled(True)
        edit_filter.setFixedWidth(210)
        toolbar.addWidget(edit_filter)

        # Select All / None toggle
        btn_select_all = QPushButton("☑  Select All")
        btn_select_all.setToolTip("Toggle select all or none of visible rows")
        btn_select_all.setStyleSheet("""
            QPushButton {
                background-color: #EDF2F7;
                color: #2D3748;
                font-weight: 600;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid #CBD5E0;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                color: #1A202C;
            }
        """)
        toolbar.addWidget(btn_select_all)

        # Batch Fix Selected Button
        has_auto_fix = has_fix(val_id)
        btn_fix_selected = QPushButton("⚡  Fix Selected (0)")
        btn_fix_selected.setEnabled(False)
        btn_fix_selected.setToolTip(
            f"Apply automated fix to checked rows ({val_id})" if has_auto_fix else f"No automated fix available for '{val_id}'"
        )
        btn_fix_selected.setStyleSheet("""
            QPushButton:enabled {
                background-color: #F0FFF4;
                color: #22543D;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
                border: 1px solid #C6F6D5;
                font-size: 11px;
            }
            QPushButton:hover:enabled {
                background-color: #C6F6D5;
                color: #1C4532;
            }
            QPushButton:disabled {
                background-color: #F7FAFC;
                color: #A0AEC0;
                border: 1px solid #E2E8F0;
            }
        """)
        toolbar.addWidget(btn_fix_selected)

        # Save Layer Changes
        btn_save_changes = QPushButton("💾  Save Changes")
        btn_save_changes.setToolTip("Commit edits on GeoJSON and JSON to disk and re-run check (Ctrl+S)")
        btn_save_changes.setStyleSheet("""
            QPushButton {
                background-color: #EBF8FF;
                color: #2B6CB0;
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
                border: 1px solid #BEE3F8;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #BEE3F8;
                color: #1A365D;
            }
        """)
        btn_save_changes.clicked.connect(lambda checked=False, v=val_id: self._save_changes(v))
        toolbar.addWidget(btn_save_changes)

        layout.addLayout(toolbar)

        # Feature Table
        table = QTableWidget()
        field_names = [f.name() for f in layer.fields()] if layer and layer.isValid() else []
        headers = ["☑"] + field_names + ["Action"]
        action_col = len(headers) - 1
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(True)

        table.setColumnWidth(0, 38)
        table.setColumnWidth(action_col, 136)

        table.setProperty("is_populating", True)

        if layer and layer.isValid():
            features = list(layer.getFeatures())
            table.setRowCount(len(features))
            table.setSortingEnabled(False)

            field_names_lower = {f.name().lower(): f.name() for f in layer.fields()}
            sf_fid_col = field_names_lower.get("sf_fid")
            df_fid_col = field_names_lower.get("df_fid")
            fid_col = sf_fid_col or field_names_lower.get("fid") or df_fid_col

            sf_uuid_col = field_names_lower.get("sf_map_uuid")
            df_uuid_col = field_names_lower.get("df_map_uuid")
            uuid_col = sf_uuid_col or field_names_lower.get("map_uuid") or df_uuid_col

            for row_idx, feat in enumerate(features):
                err_fid = feat.id()
                # Resolve source IDs for GeoJSON (sf_) and Form 2 JSON (df_)
                source_fid = feat[fid_col] if fid_col and feat[fid_col] is not None else feat.id()
                sf_fid_val = feat[sf_fid_col] if sf_fid_col and feat[sf_fid_col] is not None else source_fid
                df_fid_val = feat[df_fid_col] if df_fid_col and feat[df_fid_col] is not None else None

                uuid_val = feat[uuid_col] if uuid_col else None
                uuid_str = str(uuid_val).strip() if uuid_val is not None else ""
                sf_uuid_val = feat[sf_uuid_col] if sf_uuid_col else uuid_val
                sf_uuid_str = str(sf_uuid_val).strip() if sf_uuid_val is not None else ""
                df_uuid_val = feat[df_uuid_col] if df_uuid_col else uuid_val
                df_uuid_str = str(df_uuid_val).strip() if df_uuid_val is not None else ""

                # Column 0: Checkbox
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                chk_item.setCheckState(Qt.Unchecked)
                chk_item.setData(Qt.UserRole, source_fid)
                chk_item.setData(Qt.UserRole + 1, uuid_str)
                chk_item.setData(Qt.UserRole + 3, err_fid)
                chk_item.setData(Qt.UserRole + 4, df_fid_val)
                chk_item.setData(Qt.UserRole + 5, df_uuid_str)
                chk_item.setData(Qt.UserRole + 6, sf_fid_val)
                chk_item.setData(Qt.UserRole + 7, sf_uuid_str)
                table.setItem(row_idx, 0, chk_item)

                # Attribute Data Columns (1 to len(field_names))
                for col_idx, fname in enumerate(field_names):
                    val = feat[fname]
                    val_str = "" if val is None else str(val)
                    item = QTableWidgetItem(val_str)
                    fn_lower = fname.lower()
                    if fn_lower in ("fid", "sf_fid", "df_fid", "ref_fid"):
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        item.setToolTip("Record FID (read-only primary key anchor)")
                    elif fn_lower.startswith("ref_"):
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        item.setToolTip("Reference dataset attribute (read-only)")
                    else:
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                    item.setData(Qt.UserRole, source_fid)
                    item.setData(Qt.UserRole + 1, uuid_str)
                    item.setData(Qt.UserRole + 2, fname)
                    item.setData(Qt.UserRole + 3, err_fid)
                    item.setData(Qt.UserRole + 4, df_fid_val)
                    item.setData(Qt.UserRole + 5, df_uuid_str)
                    item.setData(Qt.UserRole + 6, sf_fid_val)
                    item.setData(Qt.UserRole + 7, sf_uuid_str)
                    table.setItem(row_idx, col_idx + 1, item)

                # Column Action: Edit & Fix buttons
                action_widget = QWidget()
                action_layout = QHBoxLayout(action_widget)
                action_layout.setContentsMargins(4, 2, 4, 2)
                action_layout.setSpacing(4)
                action_layout.setAlignment(Qt.AlignCenter)

                btn_row_edit = QPushButton("Edit")
                btn_row_edit.setToolTip(f"Open Navigation Review Dock / Feature Form for feature #{row_idx + 1}")
                btn_row_edit.setStyleSheet("""
                    QPushButton {
                        background-color: #EBF8FF;
                        color: #2B6CB0;
                        font-weight: 600;
                        padding: 2px 7px;
                        border-radius: 3px;
                        border: 1px solid #BEE3F8;
                        font-size: 10.5px;
                    }
                    QPushButton:hover {
                        background-color: #BEE3F8;
                        color: #1A365D;
                    }
                """)
                btn_row_edit.clicked.connect(
                    lambda checked=False, s_id=source_fid, u=uuid_str: self._launch_review_dock(
                        val_id, check_name, layer, target_fid=s_id, target_uuid=u
                    )
                )
                action_layout.addWidget(btn_row_edit)

                btn_row_fix = QPushButton("Fix")
                if has_auto_fix:
                    btn_row_fix.setToolTip(f"Run automated fix for feature #{row_idx + 1} ({val_id})")
                    btn_row_fix.setStyleSheet("""
                        QPushButton {
                            background-color: #F0FFF4;
                            color: #22543D;
                            font-weight: 600;
                            padding: 2px 7px;
                            border-radius: 3px;
                            border: 1px solid #C6F6D5;
                            font-size: 10.5px;
                        }
                        QPushButton:hover {
                            background-color: #C6F6D5;
                            color: #1C4532;
                        }
                    """)
                    btn_row_fix.clicked.connect(
                        lambda checked=False, s_id=source_fid, u=uuid_str, r=row_idx: self._execute_fix(
                            val_id, layer, table, target_fids=[s_id], target_uuids=[u], target_rows=[r]
                        )
                    )
                else:
                    btn_row_fix.setEnabled(False)
                    btn_row_fix.setToolTip(f"No automated fix registered for '{val_id}'")
                    btn_row_fix.setStyleSheet("""
                        QPushButton {
                            background-color: #F7FAFC;
                            color: #A0AEC0;
                            padding: 2px 7px;
                            border-radius: 3px;
                            border: 1px solid #E2E8F0;
                            font-size: 10.5px;
                        }
                    """)
                action_layout.addWidget(btn_row_fix)

                table.setCellWidget(row_idx, action_col, action_widget)

            table.setSortingEnabled(True)

        table.setProperty("is_populating", False)

        # Wire Signals
        table.itemChanged.connect(
            lambda item: self._on_table_item_changed(val_id, layer, table, item, btn_fix_selected)
        )
        table.itemClicked.connect(
            lambda item: self._on_table_row_clicked(layer, table, item.row())
        )
        btn_select_all.clicked.connect(
            lambda: self._toggle_select_all(table, btn_select_all, btn_fix_selected, val_id)
        )
        btn_fix_selected.clicked.connect(
            lambda: self._fix_selected_features(val_id, layer, table)
        )
        edit_filter.textChanged.connect(
            lambda text: self._filter_feature_table(table, text)
        )

        layout.addWidget(table, stretch=1)
        return tab

    def _on_table_item_changed(
        self,
        val_id: str,
        layer: QgsVectorLayer,
        table: QTableWidget,
        item: QTableWidgetItem,
        btn_fix_selected: Optional[QPushButton] = None,
    ):
        """Handle checkbox toggles and direct cell value editing."""
        if table.property("is_populating"):
            return

        col = item.column()
        row = item.row()

        # Case 1: Checkbox toggled in Column 0
        if col == 0:
            if btn_fix_selected:
                checked_count = sum(
                    1 for r in range(table.rowCount())
                    if table.item(r, 0) and table.item(r, 0).checkState() == Qt.Checked
                )
                btn_fix_selected.setText(f"⚡  Fix Selected ({checked_count})")
                btn_fix_selected.setEnabled(has_fix(val_id) and checked_count > 0)
            return

        # Case 2: Action column
        if col >= table.columnCount() - 1:
            return

        # Case 3: Data attribute cell edited in-place
        field_name = item.data(Qt.UserRole + 2)
        target_fid = item.data(Qt.UserRole)
        map_uuid = item.data(Qt.UserRole + 1)
        err_fid = item.data(Qt.UserRole + 3)
        df_fid = item.data(Qt.UserRole + 4)
        df_uuid = item.data(Qt.UserRole + 5)
        sf_fid = item.data(Qt.UserRole + 6) or target_fid
        sf_uuid = item.data(Qt.UserRole + 7) or map_uuid
        fn_lower = field_name.lower()
        if not field_name or fn_lower in ("fid", "sf_fid", "df_fid", "ref_fid") or fn_lower.startswith("ref_"):
            return

        new_val_str = item.text().strip()

        # If map_uuid was edited, keep cached UUID in table items synchronized
        if fn_lower in ("map_uuid", "sf_map_uuid"):
            sf_uuid = new_val_str
            item.setData(Qt.UserRole + 7, new_val_str)
            item.setData(Qt.UserRole + 1, new_val_str)
            chk_item = table.item(row, 0)
            if chk_item:
                chk_item.setData(Qt.UserRole + 7, new_val_str)
                chk_item.setData(Qt.UserRole + 1, new_val_str)
        elif fn_lower == "df_map_uuid":
            df_uuid = new_val_str
            item.setData(Qt.UserRole + 5, new_val_str)
            chk_item = table.item(row, 0)
            if chk_item:
                chk_item.setData(Qt.UserRole + 5, new_val_str)

        # 1. Update in results memory layer
        if layer and layer.isValid():
            f_idx = layer.fields().indexOf(field_name)
            if f_idx != -1:
                if not layer.isEditable():
                    layer.startEditing()
                layer.changeAttributeValue(err_fid if err_fid is not None else target_fid, f_idx, new_val_str)

        # 2. If it's a df_ column -> update Form 2 layer and buffer for disk save
        if fn_lower.startswith("df_"):
            clean_prop = field_name[3:]
            form2_layer = self._get_or_load_form2_layer()
            if form2_layer and form2_layer.isValid():
                form2_feat = self._find_form2_feature(form2_layer, fid=df_fid, map_uuid=df_uuid or map_uuid)
                if form2_feat:
                    target_f_name = (
                        clean_prop
                        if (clean_prop in [f.name() for f in form2_layer.fields()])
                        else field_name
                    )
                    f_idx = form2_layer.fields().indexOf(target_f_name)
                    if f_idx != -1:
                        if not form2_layer.isEditable():
                            form2_layer.startEditing()
                        form2_layer.changeAttributeValue(form2_feat.id(), f_idx, new_val_str)

            rec_k = f"fid_{df_fid}" if df_fid is not None else f"uuid_{df_uuid or map_uuid}"
            if rec_k not in self._pending_json_edits:
                self._pending_json_edits[rec_k] = {
                    "df_fid": df_fid,
                    "uuid": df_uuid or map_uuid,
                    "props": {},
                }
            self._pending_json_edits[rec_k]["props"][clean_prop] = new_val_str
            self.lbl_footer_status.setText(f"Updated '{clean_prop}' = '{new_val_str}' for Form 2 record (Press Ctrl+S to save)")

        # 3. If it's an sf_ or unprefixed column -> update main building points layer in memory
        else:
            main_layer = self._get_or_load_main_building_layer()
            if main_layer and main_layer.isValid():
                main_feat = self._find_main_feature(main_layer, fid=sf_fid, map_uuid=sf_uuid)
                if main_feat:
                    # Strip sf_ prefix if main layer has unprefixed field
                    target_m_name = (
                        field_name[3:]
                        if (field_name.startswith("sf_") and field_name not in [f.name() for f in main_layer.fields()])
                        else field_name
                    )
                    m_idx = main_layer.fields().indexOf(target_m_name)
                    if m_idx != -1:
                        if not main_layer.isEditable():
                            main_layer.startEditing()
                        main_layer.changeAttributeValue(main_feat.id(), m_idx, new_val_str)
            self.lbl_footer_status.setText(f"Updated '{field_name}' = '{new_val_str}' for feature FID #{sf_fid} (Press Ctrl+S to save)")

        # Subtle highlight to show cell was manually modified
        item.setBackground(QColor("#FEFCBF"))

    def _find_main_feature(
        self,
        main_layer: QgsVectorLayer,
        fid: Any = None,
        map_uuid: Optional[str] = None,
    ) -> Optional[QgsFeature]:
        """
        Locate a feature in main_layer prioritizing fid, then fallback to map_uuid.
        Guarantees correct feature resolution even if duplicate map_uuids exist.
        """
        if not main_layer or not main_layer.isValid():
            return None

        # 1. Locate by fid attribute if 'fid' field exists in main_layer
        if fid is not None and "fid" in [f.name().lower() for f in main_layer.fields()]:
            try:
                if isinstance(fid, int) or (isinstance(fid, str) and str(fid).isdigit()):
                    expr = f'"fid" = {int(fid)}'
                else:
                    expr = f'"fid" = \'{str(fid).replace(chr(39), chr(39)+chr(39))}\''
                for f in main_layer.getFeatures(QgsFeatureRequest().setFilterExpression(expr)):
                    return f
            except Exception:
                pass

        # 2. Locate by QGIS internal feature ID
        if fid is not None:
            try:
                feat = main_layer.getFeature(int(fid))
                if feat.isValid():
                    return feat
            except Exception:
                pass

        # 3. Fallback: Locate by map_uuid
        if map_uuid:
            clean_uuid = str(map_uuid).strip().replace("'", "''")
            for f in main_layer.getFeatures(QgsFeatureRequest().setFilterExpression(f'"map_uuid" = \'{clean_uuid}\'')):
                return f

        return None

    def _find_form2_feature(
        self,
        form2_layer: QgsVectorLayer,
        fid: Any = None,
        map_uuid: Optional[str] = None,
    ) -> Optional[QgsFeature]:
        """
        Locate a feature in form2_layer prioritizing fid, then fallback to map_uuid.
        """
        if not form2_layer or not form2_layer.isValid():
            return None

        f_names_lower = [f.name().lower() for f in form2_layer.fields()]

        # 1. Locate by fid attribute if 'fid' or 'df_fid' exists
        for fid_name in ("fid", "df_fid"):
            if fid is not None and fid_name in f_names_lower:
                try:
                    if isinstance(fid, int) or (isinstance(fid, str) and str(fid).isdigit()):
                        expr = f'"{fid_name}" = {int(fid)}'
                    else:
                        expr = f'"{fid_name}" = \'{str(fid).replace(chr(39), chr(39)+chr(39))}\''
                    for f in form2_layer.getFeatures(QgsFeatureRequest().setFilterExpression(expr)):
                        return f
                except Exception:
                    pass

        # 2. Locate by QGIS internal feature ID
        if fid is not None:
            try:
                feat = form2_layer.getFeature(int(fid))
                if feat.isValid():
                    return feat
            except Exception:
                pass

        # 3. Fallback: Locate by map_uuid
        if map_uuid:
            clean_uuid = str(map_uuid).strip().replace("'", "''")
            for uuid_col in ("map_uuid", "df_map_uuid"):
                if uuid_col in f_names_lower:
                    try:
                        for f in form2_layer.getFeatures(QgsFeatureRequest().setFilterExpression(f'"{uuid_col}" = \'{clean_uuid}\'')):
                            return f
                    except Exception:
                        pass

        return None

    def _toggle_select_all(
        self,
        table: QTableWidget,
        btn_select_all: QPushButton,
        btn_fix_selected: QPushButton,
        val_id: str,
    ):
        """Toggle checking/unchecking all visible rows in the table."""
        visible_rows = [r for r in range(table.rowCount()) if not table.isRowHidden(r)]
        all_checked = all(
            table.item(r, 0) and table.item(r, 0).checkState() == Qt.Checked
            for r in visible_rows
        ) if visible_rows else False

        target_state = Qt.Unchecked if all_checked else Qt.Checked
        table.setProperty("is_populating", True)
        for r in visible_rows:
            it = table.item(r, 0)
            if it:
                it.setCheckState(target_state)
        table.setProperty("is_populating", False)

        checked_count = len(visible_rows) if target_state == Qt.Checked else 0
        btn_fix_selected.setText(f"⚡  Fix Selected ({checked_count})")
        btn_fix_selected.setEnabled(has_fix(val_id) and checked_count > 0)
        btn_select_all.setText("☐  Select None" if target_state == Qt.Checked else "☑  Select All")

    def _fix_selected_features(self, val_id: str, layer: QgsVectorLayer, table: QTableWidget):
        """Batch execute fix for all checked rows in the table."""
        target_fids = []
        target_uuids = []
        target_rows = []
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if item0 and item0.checkState() == Qt.Checked:
                fid_val = item0.data(Qt.UserRole)
                uuid_val = item0.data(Qt.UserRole + 1)
                target_fids.append(fid_val)
                target_uuids.append(str(uuid_val).strip() if uuid_val else "")
                target_rows.append(r)

        if not target_fids and not target_uuids:
            QMessageBox.information(self, "No Selection", "Please select at least one row using the checkboxes.")
            return

        self._execute_fix(val_id, layer, table, target_fids=target_fids, target_uuids=target_uuids, target_rows=target_rows)

    def _execute_fix(
        self,
        val_id: str,
        layer: QgsVectorLayer,
        table: QTableWidget,
        target_fids: Optional[List[Any]] = None,
        target_uuids: Optional[List[str]] = None,
        target_rows: Optional[List[int]] = None,
    ):
        """Execute automated fix for one or more features using registered fix handler."""
        handler = get_fix_handler(val_id)
        if not handler:
            QMessageBox.warning(
                self,
                "No Fix Available",
                f"No automated fix algorithm has been registered for '{val_id}'.\n\n"
                f"To add one, create references/cbms_mv/cbms_mv_fix/{val_id}_fix.py.",
            )
            return

        main_layer = self._get_or_load_main_building_layer()
        if not main_layer or not main_layer.isValid():
            QMessageBox.critical(
                self,
                "Layer Missing",
                "Cannot run fix: Geotagged Building Points layer is not loaded.",
            )
            return

        try:
            feedback = QgsProcessingFeedback()
            try:
                res = handler(main_layer, target_fids=target_fids, target_uuids=target_uuids, feedback=feedback)
            except TypeError:
                res = handler(main_layer, target_uuids or target_fids, feedback=feedback)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Fix Error",
                f"An error occurred while executing fix for '{val_id}':\n{exc}",
            )
            return

        if not res.get("success"):
            QMessageBox.warning(
                self,
                "Fix Incomplete",
                res.get("message", "Fix did not complete successfully."),
            )
            return

        updated_values = res.get("updated_values", {})
        fixed_count = res.get("fixed_count", len(updated_values))

        # Synchronize table cells and layer
        table.setProperty("is_populating", True)
        try:
            if not layer.isEditable():
                layer.startEditing()

            rows_to_check = target_rows if target_rows is not None else list(range(table.rowCount()))
            for r in rows_to_check:
                item0 = table.item(r, 0)
                if not item0:
                    continue
                r_fid = item0.data(Qt.UserRole)
                r_uuid = str(item0.data(Qt.UserRole + 1)).strip() if item0.data(Qt.UserRole + 1) else ""
                r_err_fid = item0.data(Qt.UserRole + 3)

                # Prioritize fid lookup, fallback to uuid
                col_updates = None
                if r_fid in updated_values:
                    col_updates = updated_values[r_fid]
                elif str(r_fid) in updated_values:
                    col_updates = updated_values[str(r_fid)]
                elif r_uuid and r_uuid in updated_values:
                    col_updates = updated_values[r_uuid]

                if col_updates:
                    for c in range(1, table.columnCount() - 1):
                        c_item = table.item(r, c)
                        if c_item:
                            fname = c_item.data(Qt.UserRole + 2)
                            if fname in col_updates:
                                new_text = str(col_updates[fname])
                                c_item.setText(new_text)
                                # Highlight fixed cell in green
                                c_item.setBackground(QColor("#C6F6D5"))
                                # Also update result layer
                                f_idx = layer.fields().indexOf(fname)
                                if f_idx != -1:
                                    layer.changeAttributeValue(r_err_fid if r_err_fid is not None else r_fid, f_idx, new_text)
                                # If fname is df_*, buffer into pending JSON edits
                                if fname.lower().startswith("df_"):
                                    r_df_fid = c_item.data(Qt.UserRole + 4)
                                    r_df_uuid = c_item.data(Qt.UserRole + 5)
                                    rec_k = f"fid_{r_df_fid}" if r_df_fid is not None else f"uuid_{r_df_uuid or r_uuid}"
                                    if rec_k not in self._pending_json_edits:
                                        self._pending_json_edits[rec_k] = {
                                            "df_fid": r_df_fid,
                                            "uuid": r_df_uuid or r_uuid,
                                            "props": {},
                                        }
                                    self._pending_json_edits[rec_k]["props"][fname[3:]] = new_text

                    # Uncheck row after successful fix
                    item0.setCheckState(Qt.Unchecked)

                    # Update the row's Fix button to show Fixed
                    action_cell = table.cellWidget(r, table.columnCount() - 1)
                    if action_cell:
                        for btn in action_cell.findChildren(QPushButton):
                            if btn.text() == "Fix":
                                btn.setText("✓ Fixed")
                                btn.setEnabled(False)
                                btn.setStyleSheet("""
                                    QPushButton {
                                        background-color: #C6F6D5;
                                        color: #22543D;
                                        font-weight: bold;
                                        padding: 2px 7px;
                                        border-radius: 3px;
                                        border: 1px solid #9AE6B4;
                                        font-size: 10.5px;
                                    }
                                """)
        finally:
            table.setProperty("is_populating", False)

        # Refresh map canvas if available
        if self.iface:
            self.iface.mapCanvas().refresh()

        self.lbl_footer_status.setText(f"⚡ Successfully fixed {fixed_count} feature(s) for '{val_id}'.")
        QMessageBox.information(
            self,
            "Fix Complete",
            f"Successfully applied fix to {fixed_count} feature(s) for rule:\n{val_id}\n\n"
            f"Changes are buffered.\n"
            f"Click 'Save Changes' in the toolbar (or press Ctrl+S) to commit to disk and re-run check.",
        )

    def _on_shortcut_save(self):
        """Handle Ctrl+S shortcut, strictly scoped to this dialog window and its child controls."""
        if not self.isActiveWindow():
            return
        self._save_changes()

    def _save_csv_changes(self) -> Tuple[bool, int, str]:
        """
        Commit pending attribute edits to the Form 2 CSV file on disk.
        Returns (success: bool, updated_count: int, message: str).
        """
        form2_path = self.file_form2.filePath().strip() if hasattr(self, "file_form2") else ""
        if not form2_path:
            return False, 0, "Form 2 CSV Data File path is not specified."
        if not os.path.exists(form2_path):
            return False, 0, f"Form 2 CSV Data File does not exist on disk:\n{form2_path}"

        if not self._pending_json_edits:
            return True, 0, "No pending Form 2 edits."

        try:
            with open(form2_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    return False, 0, "CSV file is empty."
                rows = list(reader)
        except Exception as e:
            return False, 0, f"Failed to read Form 2 CSV file:\n{e}"

        header_lower = [h.strip().lower() for h in header]
        fid_idx = None
        for target in ("fid", "df_fid"):
            if target in header_lower:
                fid_idx = header_lower.index(target)
                break

        uuid_idx = None
        for target in ("map_uuid", "df_map_uuid"):
            if target in header_lower:
                uuid_idx = header_lower.index(target)
                break

        updated_count = 0
        for rec_k, record_info in self._pending_json_edits.items():
            t_fid = record_info.get("df_fid")
            t_uuid = str(record_info.get("uuid") or "").strip()
            props = record_info.get("props", {})

            target_row_idx = None

            # 1. Match by fid column if present
            if fid_idx is not None and t_fid is not None:
                t_fid_str = str(t_fid).strip()
                for r_idx, row in enumerate(rows):
                    if fid_idx < len(row) and str(row[fid_idx]).strip() == t_fid_str:
                        target_row_idx = r_idx
                        break

            # 2. Match by 1-based row index if no explicit fid column
            if target_row_idx is None and fid_idx is None and t_fid is not None:
                try:
                    row_num = int(t_fid) - 1
                    if 0 <= row_num < len(rows):
                        target_row_idx = row_num
                except (ValueError, TypeError):
                    pass

            # 3. Match by map_uuid
            if target_row_idx is None and uuid_idx is not None and t_uuid:
                for r_idx, row in enumerate(rows):
                    if uuid_idx < len(row) and str(row[uuid_idx]).strip() == t_uuid:
                        target_row_idx = r_idx
                        break

            if target_row_idx is not None:
                row = rows[target_row_idx]
                while len(row) < len(header):
                    row.append("")
                for prop_name, new_val in props.items():
                    clean_p = prop_name.lower()
                    clean_df_p = f"df_{clean_p}"
                    col_idx = None
                    for idx, h in enumerate(header_lower):
                        if h == clean_p or h == clean_df_p:
                            col_idx = idx
                            break
                    if col_idx is not None:
                        row[col_idx] = str(new_val) if new_val is not None else ""
                updated_count += 1

        # Atomic write back to Form 2 CSV file
        tmp_file = form2_path + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
            os.replace(tmp_file, form2_path)
        except Exception as e:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            return False, 0, f"Error saving Form 2 CSV to disk:\n{e}"

        self._pending_json_edits.clear()

        # If a Form 2 table layer is loaded into QGIS canvas, refresh it
        if self.project:
            for lyr in self.project.mapLayers().values():
                if lyr.name().startswith("Form 2 (") or (hasattr(lyr, "source") and lyr.source() == form2_path):
                    try:
                        lyr.dataProvider().forceReload()
                        lyr.triggerRepaint()
                    except Exception:
                        pass

        return True, updated_count, f"Successfully saved {updated_count} record(s) to Form 2 CSV."

    def _save_json_changes(self) -> Tuple[bool, int, str]:
        """
        Commit pending JSON attribute edits to the Form 2 JSON file on disk.
        Returns (success: bool, updated_count: int, message: str).
        """
        form2_path = self.file_form2.filePath().strip()
        if not form2_path:
            return False, 0, "Form 2 Data File path is not specified."
        if not os.path.exists(form2_path):
            return False, 0, f"Form 2 Data File does not exist on disk:\n{form2_path}"

        if not self._pending_json_edits:
            return True, 0, "No pending JSON edits."

        try:
            with open(form2_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, 0, f"Failed to read/parse Form 2 JSON file:\n{e}"

        # Locate records container (mirroring load_cbms_json in gmdhelpers)
        records = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            for key in ["records", "features", "data", "cover_page"]:
                if key in data and isinstance(data[key], list):
                    records = data[key]
                    break
            if not records:
                records = [data]

        has_fid_in_props = False
        for rec in records:
            props = rec.get("properties", rec) if isinstance(rec, dict) else {}
            if isinstance(props, dict) and any(str(k).strip().lower() == "fid" for k in props.keys()):
                has_fid_in_props = True
                break

        updated_count = 0
        for rec_key, record_info in self._pending_json_edits.items():
            t_df_fid = record_info.get("df_fid")
            t_uuid = str(record_info.get("uuid") or "").strip()
            props_to_update = record_info.get("props", {})

            target_rec = None

            # 1. Match by 1-based index if no explicit fid property exists
            if not has_fid_in_props and t_df_fid is not None:
                try:
                    idx = int(t_df_fid) - 1
                    if 0 <= idx < len(records):
                        candidate = records[idx]
                        c_props = candidate.get("properties", candidate) if isinstance(candidate, dict) else candidate
                        if isinstance(c_props, dict):
                            c_uuid = str(c_props.get("map_uuid") or c_props.get("df_map_uuid") or "").strip()
                            if not t_uuid or not c_uuid or c_uuid == t_uuid:
                                target_rec = candidate
                except (ValueError, TypeError):
                    pass

            # 2. Match by explicit 'fid' in record properties
            if target_rec is None and t_df_fid is not None:
                t_fid_str = str(t_df_fid).strip()
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    c_props = rec.get("properties", rec) if isinstance(rec.get("properties"), dict) else rec
                    if not isinstance(c_props, dict):
                        continue
                    for k, v in c_props.items():
                        if str(k).strip().lower() in ("fid", "df_fid") and str(v).strip() == t_fid_str:
                            target_rec = rec
                            break
                    if target_rec is not None:
                        break

            # 3. Match by map_uuid
            if target_rec is None and t_uuid:
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    c_props = rec.get("properties", rec) if isinstance(rec.get("properties"), dict) else rec
                    if not isinstance(c_props, dict):
                        continue
                    for k, v in c_props.items():
                        if str(k).strip().lower() in ("map_uuid", "df_map_uuid") and str(v).strip() == t_uuid:
                            target_rec = rec
                            break
                    if target_rec is not None:
                        break

            if target_rec is not None and isinstance(target_rec, dict):
                target_dict = (
                    target_rec.get("properties", target_rec)
                    if isinstance(target_rec.get("properties"), dict)
                    else target_rec
                )
                for prop_name, new_val in props_to_update.items():
                    matched_key = None
                    for existing_k in target_dict.keys():
                        if existing_k == prop_name or existing_k.lower() == prop_name.lower():
                            matched_key = existing_k
                            break
                    if not matched_key:
                        for existing_k in target_dict.keys():
                            if existing_k == f"df_{prop_name}" or existing_k.lower() == f"df_{prop_name}".lower():
                                matched_key = existing_k
                                break

                    final_key = matched_key if matched_key else prop_name

                    existing_val = target_dict.get(final_key)
                    typed_val = new_val
                    if existing_val is not None:
                        if isinstance(existing_val, bool):
                            typed_val = str(new_val).lower() in ("true", "1", "yes", "t")
                        elif isinstance(existing_val, int) and not isinstance(existing_val, bool):
                            try:
                                typed_val = int(new_val)
                            except (ValueError, TypeError):
                                typed_val = new_val
                        elif isinstance(existing_val, float):
                            try:
                                typed_val = float(new_val)
                            except (ValueError, TypeError):
                                typed_val = new_val
                    elif new_val == "":
                        typed_val = None

                    target_dict[final_key] = typed_val

                updated_count += 1

        # Atomic write back to Form 2 JSON file
        tmp_file = form2_path + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, form2_path)
        except Exception as e:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            return False, 0, f"Error saving Form 2 JSON to disk:\n{e}"

        self._pending_json_edits.clear()

        # If a Form 2 table layer is loaded into QGIS canvas, refresh it
        if self.project:
            for lyr in self.project.mapLayers().values():
                if lyr.name().startswith("Form 2 (") or (hasattr(lyr, "source") and lyr.source() == form2_path):
                    try:
                        lyr.dataProvider().forceReload()
                        lyr.triggerRepaint()
                    except Exception:
                        pass

        return True, updated_count, f"Successfully saved {updated_count} record(s) to Form 2 JSON."

    def _save_changes(self, target_val_id: Optional[str] = None) -> bool:
        """
        Commit pending edits on both the Geotagged Building Points (.geojson)
        and Form 2 Data (.json) files to disk, and automatically re-run the
        validation check for the current/target validation ID.
        """
        # Ensure any active cell editor in the table commits its value
        focus_w = QApplication.focusWidget()
        if focus_w and isinstance(focus_w, QLineEdit) and focus_w.parent():
            p = focus_w.parent()
            if isinstance(p, QTableWidget):
                p.clearFocus()
                p.setFocus()
            elif p.parent() and isinstance(p.parent(), QTableWidget):
                p.parent().clearFocus()
                p.parent().setFocus()

        main_layer = self._get_or_load_main_building_layer()
        geojson_saved = False
        geojson_err = None

        # 1. Commit GeoJSON Layer changes if dirty
        if main_layer and main_layer.isValid() and main_layer.isEditable() and main_layer.isModified():
            try:
                success = main_layer.commitChanges()
                if success:
                    main_layer.startEditing()  # Keep editable for continued workflow
                    geojson_saved = True
                else:
                    errors = main_layer.commitErrors()
                    geojson_err = "\n".join(errors) if errors else "Unknown commit error."
            except Exception as exc:
                geojson_err = str(exc)

        if geojson_err:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to commit changes to Geotagged Building Points (.geojson):\n{geojson_err}",
            )
            return False

        # 2. Commit Form 2 Data (CSV or JSON) changes if dirty
        form2_saved = False
        form2_updated_count = 0
        form2_path = self.file_form2.filePath().strip() if hasattr(self, "file_form2") else ""
        form2_layer = self._get_or_load_form2_layer()

        if form2_path.lower().endswith(".csv"):
            if form2_layer and form2_layer.isValid() and form2_layer.isEditable() and form2_layer.isModified():
                try:
                    success = form2_layer.commitChanges()
                    if success:
                        form2_layer.startEditing()
                        form2_saved = True
                        form2_updated_count = len(self._pending_json_edits)
                        self._pending_json_edits.clear()
                    else:
                        errors = form2_layer.commitErrors()
                        form2_err = "\n".join(errors) if errors else "Unknown commit error."
                        QMessageBox.critical(
                            self,
                            "Save Failed",
                            f"Failed to commit changes to Form 2 CSV layer:\n{form2_err}",
                        )
                        return False
                except Exception as exc:
                    QMessageBox.critical(
                        self,
                        "Save Failed",
                        f"Error committing Form 2 CSV layer:\n{exc}",
                    )
                    return False
            elif self._pending_json_edits:
                ok, form2_updated_count, form2_msg = self._save_csv_changes()
                if not ok:
                    QMessageBox.critical(
                        self,
                        "Save Failed",
                        f"Failed to commit changes to Form 2 CSV file:\n{form2_msg}",
                    )
                    return False
                form2_saved = True
        elif form2_path.lower().endswith(".json") and self._pending_json_edits:
            ok, form2_updated_count, form2_msg = self._save_json_changes()
            if not ok:
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Failed to commit changes to Form 2 Data (.json):\n{form2_msg}",
                )
                return False
            form2_saved = True
        elif self._pending_json_edits:
            ok, form2_updated_count, form2_msg = self._save_csv_changes()
            if not ok:
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Failed to commit changes to Form 2 table:\n{form2_msg}",
                )
                return False
            form2_saved = True

        # 3. Assemble saved message
        saved_parts = []
        if geojson_saved:
            saved_parts.append("Building Points (.geojson)")
        if form2_saved:
            fmt = "CSV" if form2_path.lower().endswith(".csv") else "JSON"
            saved_parts.append(f"Form 2 Data ({form2_updated_count} record(s) in .{fmt.lower()})")

        if saved_parts:
            saved_msg = f"Successfully saved edits to: {' and '.join(saved_parts)}."
        else:
            saved_msg = "No unsaved edits pending on disk."

        # 4. Determine validation ID to re-run
        val_id = target_val_id
        if not val_id and hasattr(self, "results_tab_widget"):
            cur_widget = self.results_tab_widget.currentWidget()
            if cur_widget:
                val_id = cur_widget.property("val_id")
            if not val_id and self.results_tab_widget.currentIndex() > 0:
                cur_text = self.results_tab_widget.tabText(self.results_tab_widget.currentIndex())
                for r in self._rules:
                    if r["id"] in cur_text:
                        val_id = r["id"]
                        break

        # 5. Re-run validation check if a valid val_id is active
        if val_id:
            self._rerun_validation_check(val_id, saved_msg=saved_msg)
        else:
            self.lbl_footer_status.setText(f"💾 {saved_msg}")
            QMessageBox.information(
                self,
                "Changes Saved",
                f"{saved_msg}\n\nAll changes have been successfully committed to disk.",
            )

        return True

    def _save_main_layer_changes(self):
        """Backwards compatible alias for _save_changes."""
        return self._save_changes()

    def _rerun_validation_check(self, val_id: str, saved_msg: str = ""):
        """
        Execute a single validation rule using fresh disk data and update its
        corresponding tab in the Results Workspace as well as the Summary Overview.
        """
        form2_path = self.file_form2.filePath().strip()
        points_path = self.file_points.filePath().strip()
        base_path = self.file_base.filePath().strip()

        if not form2_path or not os.path.exists(form2_path):
            self.lbl_footer_status.setText(f"💾 {saved_msg} (Cannot re-run: Form 2 JSON missing)")
            return
        if not points_path or not os.path.exists(points_path):
            self.lbl_footer_status.setText(f"💾 {saved_msg} (Cannot re-run: Building Points file missing)")
            return

        rule = next((r for r in self._rules if r["id"] == val_id), None)
        if not rule:
            rule = {"id": val_id, "name": val_id.replace("_", " ").title(), "has_base": False}

        if rule.get("has_base") and (not base_path or not os.path.exists(base_path)):
            self.lbl_footer_status.setText(f"💾 {saved_msg} (Cannot re-run: Base Layers GPKG required)")
            return

        reg_id = f"gmd_pipeline:{val_id}"
        is_registered = QgsApplication.processingRegistry().algorithmById(reg_id) is not None
        alg = self._get_algorithm_instance(val_id)
        if not is_registered and not alg:
            self.lbl_footer_status.setText(f"💾 {saved_msg} (Could not instantiate algorithm '{val_id}')")
            return

        alg_target = reg_id if is_registered else alg

        self.lbl_footer_status.setText(f"⚡ Re-running check '{val_id}' with fresh data...")
        QApplication.processEvents()

        params = {
            "INPUT_DATA": form2_path,
            "INPUT_LAYER": points_path,
            "OUTPUT": "TEMPORARY_OUTPUT",
        }
        if base_path:
            params["BASE_LAYER"] = base_path

        param_defs = [p.name() for p in alg.parameterDefinitions()] if alg else []
        if "OUTPUT_ERRORS" in param_defs:
            params["OUTPUT_ERRORS"] = "TEMPORARY_OUTPUT"
        if "OPEN_FOR_EDITING" in param_defs:
            params["OPEN_FOR_EDITING"] = False

        feedback = ProcessingFeedbackBridge(self._log_info, self._log_warning, self._log_error)
        self._log_step("RERUN", f"Re-running validation check '{val_id}' after saving changes...")

        try:
            result = processing.run(alg_target, params, context=self.context, feedback=feedback)
        except Exception as exc:
            self._log_error(f"Execution error re-running '{val_id}': {exc}")
            QMessageBox.critical(
                self,
                "Re-run Error",
                f"{saved_msg}\n\nError executing validation algorithm '{val_id}':\n{exc}",
            )
            return

        # Retrieve output layer
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
                if not out_layer and os.path.exists(out_dest):
                    out_layer = QgsVectorLayer(out_dest, val_id, "ogr")

        if out_layer and out_layer.isValid():
            new_count = out_layer.featureCount()
        else:
            new_count = 0
            out_layer = QgsVectorLayer("none", val_id, "memory")

        # Update result layers dictionary
        self._result_layers[val_id] = {
            "layer": out_layer,
            "rule": rule,
            "count": new_count,
        }

        # Update execution summary entry
        found_in_summary = False
        for s_entry in self._execution_summary:
            if s_entry["id"] == val_id:
                s_entry["features_flagged"] = new_count
                s_entry["status"] = "Flagged" if new_count > 0 else "Passed"
                found_in_summary = True
                break
        if not found_in_summary:
            self._execution_summary.append({
                "id": val_id,
                "name": rule["name"],
                "status": "Flagged" if new_count > 0 else "Passed",
                "features_flagged": new_count,
            })

        # Update KPI scorecards
        total_flagged = sum(item["count"] for item in self._result_layers.values())
        self.lbl_kpi_flagged.setText(f"{total_flagged:,}")
        flagged_layers = sum(1 for item in self._result_layers.values() if item["count"] > 0)
        self.lbl_kpi_layers.setText(str(flagged_layers))

        # Update QGIS Canvas Layer if canvas loading is enabled
        proj = self.project if self.project else QgsProject.instance()
        if proj and self.chk_load_canvas.isChecked():
            # Remove old layer for this val_id if present
            matching_ids = [
                l.id() for l in proj.mapLayers().values()
                if l.name().startswith(f"{val_id} (") or l.name() == val_id
            ]
            if matching_ids:
                proj.removeMapLayers(matching_ids)

            # If new issues exist, load updated layer into group or project
            if new_count > 0 and out_layer.isValid():
                out_layer.setName(f"{val_id} ({new_count})")
                if self.chk_group_layers.isChecked():
                    grp = self._get_or_create_layer_group("2027 CBMS MV Results")
                    proj.addMapLayer(out_layer, False)
                    grp.addLayer(out_layer)
                else:
                    proj.addMapLayer(out_layer)

            if self.iface:
                self.iface.mapCanvas().refresh()

        # Update Results Tab
        target_tab_idx = None
        for ti in range(1, self.results_tab_widget.count()):
            w = self.results_tab_widget.widget(ti)
            if w and w.property("val_id") == val_id:
                target_tab_idx = ti
                break
            if val_id in self.results_tab_widget.tabText(ti):
                target_tab_idx = ti
                break

        new_tab = self._create_result_layer_tab(val_id, rule["name"], out_layer, new_count)
        tab_title = f"🔴  {val_id} ({new_count})" if new_count > 0 else f"🟢  {val_id} (0)"

        if target_tab_idx is not None:
            self.results_tab_widget.removeTab(target_tab_idx)
            self.results_tab_widget.insertTab(target_tab_idx, new_tab, tab_title)
            self.results_tab_widget.setTabToolTip(target_tab_idx, f"{rule['name']} — {new_count} flagged feature(s)")
            self.results_tab_widget.setCurrentIndex(target_tab_idx)
        else:
            tab_idx = self.results_tab_widget.addTab(new_tab, tab_title)
            self.results_tab_widget.setTabToolTip(tab_idx, f"{rule['name']} — {new_count} flagged feature(s)")
            self.results_tab_widget.setCurrentIndex(tab_idx)

        # Update Summary Overview (Tab 0)
        if self.results_tab_widget.count() > 0:
            active_idx = self.results_tab_widget.currentIndex()
            new_summary = self._create_summary_tab(self._execution_summary, self._result_layers)
            self.results_tab_widget.removeTab(0)
            self.results_tab_widget.insertTab(0, new_summary, "📊  Summary Overview")
            self.results_tab_widget.setCurrentIndex(active_idx)

        # User feedback
        if new_count == 0:
            self._log_success(f"'{val_id}' re-run complete: 0 flagged issues! All issues resolved.")
            self.lbl_footer_status.setText(f"🎉 '{val_id}' resolved! 0 flagged features remaining.")
            QMessageBox.information(
                self,
                "Check Re-run: Clean!",
                f"{saved_msg}\n\n"
                f"🎉 Re-run of validation check '{val_id}' completed:\n"
                f"0 flagged issues detected!\n\n"
                f"All features for this validation check are now consistent and valid.",
            )
        else:
            self._log_warning(f"'{val_id}' re-run complete: {new_count:,} flagged feature(s) remaining.")
            self.lbl_footer_status.setText(f"💾 Changes saved • '{val_id}' re-run: {new_count:,} issue(s) remaining.")
            QMessageBox.information(
                self,
                "Check Re-run Complete",
                f"{saved_msg}\n\n"
                f"Re-run of validation check '{val_id}' completed:\n"
                f"{new_count:,} flagged feature(s) remaining in this check.",
            )

    def _on_table_row_clicked(self, layer: QgsVectorLayer, table: QTableWidget, row: int):
        """Zoom and flash canvas feature when clicking any table row."""
        item0 = table.item(row, 0)
        if not item0:
            return
        target_fid = item0.data(Qt.UserRole)
        map_uuid = item0.data(Qt.UserRole + 1)
        err_fid = item0.data(Qt.UserRole + 3)

        if not self.iface:
            return

        canvas = self.iface.mapCanvas()
        main_layer = self._get_or_load_main_building_layer()
        target_layer = main_layer if (main_layer and main_layer.isValid()) else layer

        if not target_layer or not target_layer.isValid():
            return

        feat = None
        if target_layer == main_layer:
            feat = self._find_main_feature(main_layer, fid=target_fid, map_uuid=map_uuid)
        if not feat and layer and layer.isValid() and err_fid is not None:
            feat = layer.getFeature(int(err_fid))

        if feat and feat.isValid():
            try:
                self.iface.setActiveLayer(target_layer)
                target_layer.selectByIds([feat.id()])
                if target_layer.isSpatial():
                    canvas.zoomToFeatureIds(target_layer, [feat.id()])
                    canvas.flashFeatureIds(target_layer, [feat.id()])
                    canvas.refresh()
                self.lbl_footer_status.setText(f"Zoomed to feature FID #{target_fid} in '{target_layer.name()}'")
            except Exception as exc:
                self.lbl_footer_status.setText(f"Could not zoom to feature: {exc}")

    def _filter_feature_table(self, table: QTableWidget, text: str):
        """Filter table rows matching search string across data columns."""
        search = text.strip().lower()
        last_col = max(0, table.columnCount() - 1)
        for row in range(table.rowCount()):
            if not search:
                table.setRowHidden(row, False)
                continue
            match = False
            for col in range(1, last_col):
                it = table.item(row, col)
                if it and search in it.text().lower():
                    match = True
                    break
            table.setRowHidden(row, not match)

    def _export_layer_to_csv(self, layer: QgsVectorLayer, val_id: str):
        """Export the result layer attributes to a CSV file."""
        if not layer or not layer.isValid():
            QMessageBox.warning(self, "Export Error", "Layer is not valid for export.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {val_id} to CSV",
            f"{val_id}_results.csv",
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not filename:
            return

        try:
            with open(filename, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                field_names = [f.name() for f in layer.fields()]
                writer.writerow(field_names)
                for feat in layer.getFeatures():
                    row_vals = [feat[fname] if feat[fname] is not None else "" for fname in field_names]
                    writer.writerow(row_vals)

            QMessageBox.information(
                self,
                "Export Succeeded",
                f"Successfully exported {layer.featureCount():,} records to:\n{filename}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{exc}")

    # -----------------------------------------------------------------------
    # Review & Fix Dock Integration (Check & Update Pattern)
    # -----------------------------------------------------------------------
    def _get_or_load_main_building_layer(self) -> Optional[QgsVectorLayer]:
        """
        Locate the main Geotagged Building Points layer in the QGIS project matching
        the input file path. If not currently loaded, loads it into the project.
        """
        points_path = self.file_points.filePath().strip() if hasattr(self, "file_points") else ""
        if not points_path or not os.path.exists(points_path):
            QMessageBox.warning(
                self,
                "Missing Building Points Layer",
                "Geotagged Building Points (.geojson) file path is not configured or does not exist.\n\n"
                "Please configure a valid points file in the 'Data Config' tab first.",
            )
            return None

        proj = self.project if self.project else QgsProject.instance()
        norm_path = os.path.normpath(points_path).lower()

        # 1. Search existing project layers
        for layer in proj.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                src = os.path.normpath(layer.source().split("|")[0]).lower()
                if src == norm_path:
                    return layer

        # 2. Not loaded in project yet, load it
        try:
            layer_name = f"Building Points ({os.path.basename(points_path)})"
            pt_layer = QgsVectorLayer(points_path, layer_name, "ogr")
            if pt_layer.isValid():
                group_name = "2027 CBMS Primary Inputs"
                grp = self._get_or_create_layer_group(group_name)
                proj.addMapLayer(pt_layer, False)
                grp.addLayer(pt_layer)
                self._log_info(f"Loaded main building points layer into '{group_name}': {layer_name}")
                return pt_layer
            else:
                QMessageBox.critical(
                    self,
                    "Layer Load Error",
                    f"Failed to load building points file:\n{points_path}",
                )
                return None
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Layer Load Exception",
                f"Error loading building points layer:\n{exc}",
            )
            return None

    def _get_or_load_form2_layer(self) -> Optional[QgsVectorLayer]:
        """
        Locate the Form 2 table layer (CSV/JSON) in the QGIS project matching
        the input file path. If not currently loaded, loads it into the project.
        """
        form2_path = self.file_form2.filePath().strip() if hasattr(self, "file_form2") else ""
        if not form2_path or not os.path.exists(form2_path):
            return None

        proj = self.project if self.project else QgsProject.instance()
        norm_path = os.path.normpath(form2_path).lower()

        # 1. Search existing project layers
        for layer in proj.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                src = os.path.normpath(layer.source().split("|")[0]).lower()
                if src == norm_path or (layer.name().startswith("Form 2 (") and src == norm_path):
                    return layer

        # 2. Not loaded in project yet, load it
        try:
            layer_name = f"Form 2 ({os.path.basename(form2_path)})"
            if form2_path.lower().endswith(".csv"):
                table_layer = QgsVectorLayer(form2_path, layer_name, "ogr")
            else:
                table_layer = load_cbms_json_to_layer(form2_path, layer_name=layer_name, add_to_project=False)

            if table_layer and table_layer.isValid():
                group_name = "2027 CBMS Primary Inputs"
                grp = self._get_or_create_layer_group(group_name)
                proj.addMapLayer(table_layer, False)
                grp.addLayer(table_layer)
                self._log_info(f"Loaded Form 2 layer into '{group_name}': {layer_name}")
                return table_layer
        except Exception as exc:
            self._log_error(f"Error loading Form 2 layer: {exc}")

        return None

    def _launch_review_dock(
        self,
        val_id: str,
        check_name: str,
        error_layer: QgsVectorLayer,
        start_index: int = 0,
        target_fid: Optional[Any] = None,
        target_uuid: Optional[str] = None,
    ):
        """Launch or update the interactive Check & Update Review Dock."""
        if not error_layer or not error_layer.isValid():
            QMessageBox.warning(self, "Invalid Layer", "The validation error layer is invalid.")
            return

        if error_layer.featureCount() == 0:
            QMessageBox.information(
                self,
                "No Issues",
                f"Validation check '{val_id}' has 0 flagged issues to review.",
            )
            return

        main_layer = self._get_or_load_main_building_layer()
        if not main_layer:
            return

        # Close existing dock if one is already open
        if self._active_review_dock:
            dock = self._active_review_dock
            self._active_review_dock = None
            try:
                try:
                    dock.dock_closed.disconnect(self._on_review_dock_closed)
                except Exception:
                    pass
                dock.parent_dialog = None
                dock.close()
            except Exception:
                pass

        try:
            dock = CbmsMvReviewDock(
                parent_dialog=self,
                val_id=val_id,
                check_name=check_name,
                error_layer=error_layer,
                main_layer=main_layer,
                start_index=start_index,
            )
            dock.dock_closed.connect(self._on_review_dock_closed)

            if self.iface:
                self.iface.addDockWidget(Qt.RightDockWidgetArea, dock)

            dock.show()
            dock.raise_()
            if target_fid is not None:
                dock.jump_to_fid(target_fid, target_uuid)
            else:
                dock.jump_to_index(start_index)
            self._active_review_dock = dock

            # Minimize main dialog to give full visibility to canvas and dock
            self.showMinimized()
            self.lbl_footer_status.setText(
                f"Reviewing '{val_id}' in dock (Item {dock.current_index + 1}/{error_layer.featureCount():,})"
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error Launching Review Dock",
                f"Failed to open review dock:\n{exc}",
            )

    def _on_review_dock_closed(self):
        """Slot triggered when review dock is closed."""
        self._active_review_dock = None
        if is_valid_qobject(self):
            try:
                self.showNormal()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass

    def closeEvent(self, event):
        """Prompt to save unsaved edits and clean up active review dock when dialog closes."""
        main_layer = self._get_or_load_main_building_layer()
        has_unsaved = (
            (main_layer and main_layer.isValid() and main_layer.isEditable() and main_layer.isModified())
            or bool(self._pending_json_edits)
        )
        if has_unsaved:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes in your GeoJSON / Form 2 JSON data.\n\nDo you want to save them before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Save:
                if not self._save_changes():
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        if hasattr(self, "_active_review_dock") and self._active_review_dock:
            dock = self._active_review_dock
            self._active_review_dock = None
            try:
                try:
                    dock.dock_closed.disconnect(self._on_review_dock_closed)
                except Exception:
                    pass
                dock.parent_dialog = None
                dock.close()
            except Exception:
                pass
        super().closeEvent(event)


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

        # 1. Form 2 Data File (.csv)
        lbl_form2 = QLabel("Form 2 Data File (.csv):")
        lbl_form2.setStyleSheet("font-weight: bold; color: #2C3E50;")
        self.file_form2 = QgsFileWidget()
        self.file_form2.setDialogTitle("Select Form 2 Data File (.csv)")
        self.file_form2.setFilter("CBMS Form 2 CSV Files (*.csv *.CSV);;JSON Files (*.json *.JSON);;All Files (*.*)")
        self.file_form2.setStorageMode(QgsFileWidget.GetFile)
        self.file_form2.fileChanged.connect(self._on_inputs_changed)

        self.lbl_status_form2 = QLabel("")
        self.lbl_status_form2.setFixedWidth(24)
        self.lbl_status_form2.setAlignment(Qt.AlignCenter)

        grid_sources.addWidget(lbl_form2, 0, 0)
        grid_sources.addWidget(self.file_form2, 0, 1)
        grid_sources.addWidget(self.lbl_status_form2, 0, 2)

        # 2. Geotagged Building Points (.geojson)
        lbl_points = QLabel("Form 2 Geotagged Building Points (.geojson):")
        lbl_points.setStyleSheet("font-weight: bold; color: #2C3E50;")
        self.file_points = QgsFileWidget()
        self.file_points.setDialogTitle("Select Form 2 Geotagged Building Points (.geojson)")
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
            "If checked, automatically loads Form 2 CSV/table, Geotagged Building Points, "
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
        self.chk_load_canvas.setChecked(False)
        vbox_output.addWidget(self.chk_load_canvas)

        self.chk_group_layers = QCheckBox("Group validation result layers under '2027 CBMS MV Results'")
        self.chk_group_layers.setChecked(False)
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
                    self.lbl_status_form2.setToolTip("Form 2 Data file exists")
                else:
                    self.lbl_status_form2.setText("<span style='color: #E74C3C; font-weight: bold; font-size: 14px;'>❌</span>")
                    self.lbl_status_form2.setToolTip("Form 2 Data file not found")
            else:
                self.lbl_status_form2.setText("<span style='color: #E74C3C; font-weight: bold; font-size: 14px;'>❌</span>")
                self.lbl_status_form2.setToolTip("Form 2 Data file required")

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
        saved_form2 = self.settings.value(SETTINGS_KEY_FORM2, "", type=str) or self.settings.value(SETTINGS_KEY_FORM2_LEGACY, "", type=str)
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

        btn_refresh = QToolButton()
        btn_refresh.setText("🔄")
        btn_refresh.setToolTip("Refresh and re-scan algorithms in gmd_scripts/cbms_mv")
        btn_refresh.clicked.connect(self.refresh_rules)

        toolbar.addWidget(btn_select_all)
        toolbar.addWidget(btn_deselect_all)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        # Rules Table
        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(3)
        self.rules_table.setHorizontalHeaderLabels([
            "Enable",
            "Validation ID",
            "Validation Check Name",
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.verticalHeader().setVisible(False)

        layout.addWidget(self.rules_table, stretch=1)

        # Rule counts label
        self.lbl_rules_count = QLabel("")
        self.lbl_rules_count.setStyleSheet("font-size: 11px; color: #555;")
        layout.addWidget(self.lbl_rules_count)

        return tab

    def _save_rule_settings(self):
        """Persist currently checked validation rule IDs into QSettings."""
        enabled_rules = [
            val_id for val_id, item in self._rule_checkboxes.items()
            if item.checkState() == Qt.Checked
        ]
        self.settings.setValue(SETTINGS_KEY_SELECTED_RULES, json.dumps(enabled_rules))

    def _get_saved_enabled_rule_ids(self) -> Optional[set]:
        """Load the set of saved enabled rule IDs from QSettings if present."""
        raw = self.settings.value(SETTINGS_KEY_SELECTED_RULES, None)
        if raw is not None:
            try:
                if isinstance(raw, str):
                    loaded = json.loads(raw)
                    if isinstance(loaded, list):
                        return set(loaded)
                elif isinstance(raw, list):
                    return set(raw)
            except Exception:
                pass
        return None

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
        saved_enabled = self._get_saved_enabled_rule_ids()

        self.rules_table.blockSignals(True)
        self.rules_table.setRowCount(len(self._rules))
        self._rule_checkboxes.clear()

        for row, rule in enumerate(self._rules):
            val_id = rule["id"]

            # 0. Checkbox
            item_check = QTableWidgetItem()
            item_check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            
            if prev_states and val_id in prev_states:
                state = prev_states[val_id]
            elif saved_enabled is not None:
                state = Qt.Checked if val_id in saved_enabled else Qt.Unchecked
            else:
                state = Qt.Checked if rule.get("default", True) else Qt.Unchecked

            item_check.setCheckState(state)
            self._rule_checkboxes[val_id] = item_check
            self.rules_table.setItem(row, 0, item_check)

            # 1. Validation ID
            item_id = QTableWidgetItem(val_id)
            item_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_id.setFont(QFont("Consolas", 9))
            self.rules_table.setItem(row, 1, item_id)

            # 2. Validation Check Name
            item_name = QTableWidgetItem(rule["name"])
            tooltip_text = f"{rule['name']}\n\n{rule['desc']}\n\nValidation ID: {val_id}\nFile: {rule.get('file_path', '')}"
            item_name.setToolTip(tooltip_text)
            item_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.rules_table.setItem(row, 2, item_name)

        self.rules_table.blockSignals(False)
        self.rules_table.itemChanged.connect(self._on_rule_item_changed)

    def _on_rule_item_changed(self, item):
        """Handle checkbox changes in the rules table."""
        if item.column() == 0:
            self._update_rule_counts()
            self._save_rule_settings()

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
        self._save_rule_settings()

    def _update_rule_counts(self):
        """Update the rule counter label, footer status, and KPI metrics."""
        total = len(self._rules)
        enabled = sum(
            1 for item in self._rule_checkboxes.values()
            if item.checkState() == Qt.Checked
        )

        self.lbl_rules_count.setText(f"{enabled} of {total} validation rules enabled")
        self.lbl_footer_status.setText(f"Ready • {enabled} validation rule(s) selected")
        if hasattr(self, "lbl_kpi_rules"):
            self.lbl_kpi_rules.setText(str(enabled))

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
        lbl_val.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {color_hex};")
        lbl_val.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 9.5px; color: #718096; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;")
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

        self.btn_reset = QPushButton("Reset Form")
        self.btn_reset.clicked.connect(self._reset_form)
        layout.addWidget(self.btn_reset)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)

        self.btn_run = QPushButton("  ▶  Run Validation  ")
        self.btn_run.setObjectName("btnRun")
        self.btn_run.setShortcut("Ctrl+Return")
        self.btn_run.setToolTip("Run Map Validation (Ctrl+Enter)")
        self.btn_run.clicked.connect(self.run_validation)
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
                font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", sans-serif;
                font-size: 11.5px;
                color: #2D3748;
            }
            QWidget {
                font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", sans-serif;
            }
            #topNavBar {
                background-color: transparent;
                border: none;
            }
            #btnHeaderConfig {
                background-color: #EDF2F7;
                color: #2B6CB0;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 5px;
                border: 1px solid #CBD5E0;
                font-size: 11px;
            }
            QPushButton#btnHeaderConfig:hover {
                background-color: #E2E8F0;
                color: #1A365D;
                border: 1px solid #A0AEC0;
            }
            #sectionGroup {
                font-weight: 600;
                font-size: 12px;
                color: #1A365D;
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
                font-weight: 600;
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
                font-family: "Consolas", "Cascadia Code", monospace;
                font-size: 10.5px;
                line-height: 1.4;
            }
            #btnRun {
                background-color: #2B6CB0;
                color: #FFFFFF;
                font-weight: 600;
                padding: 7px 18px;
                border-radius: 5px;
                border: none;
                font-size: 11.5px;
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
                font-size: 11px;
                color: #2D3748;
            }
            QTableWidget::item:selected {
                background-color: #EBF8FF;
                color: #2B6CB0;
            }
            QHeaderView::section {
                background-color: #EDF2F7;
                color: #2D3748;
                font-size: 11px;
                font-weight: 600;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #CBD5E0;
            }
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #EDF2F7;
                color: #4A5568;
                font-size: 11px;
                font-weight: 600;
                padding: 6px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #2B6CB0;
                border: 1px solid #E2E8F0;
                border-bottom-color: #FFFFFF;
            }
            QLineEdit {
                font-size: 11px;
                padding: 4px 8px;
                border: 1px solid #CBD5E0;
                border-radius: 4px;
                background-color: #FFFFFF;
                color: #2D3748;
            }
            QLineEdit:focus {
                border-color: #3182CE;
            }
            QPushButton {
                font-size: 11px;
                font-weight: 600;
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
        """Reset inputs, table selections, and results to defaults."""
        self.file_form2.setFilePath("")
        self.file_points.setFilePath("")
        self.file_base.setFilePath("")
        self.radio_memory.setChecked(True)
        self.file_widget_gpkg.setFilePath("")
        self.settings.remove(SETTINGS_KEY_SELECTED_RULES)
        self._set_all_rules_checked(True)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Status: Idle — Ready to run validation")
        self.lbl_kpi_flagged.setText("0")
        self.lbl_kpi_layers.setText("0")
        self._result_layers.clear()
        self._execution_summary.clear()
        if hasattr(self, "results_tab_widget"):
            self.results_tab_widget.clear()
        if hasattr(self, "results_stack"):
            self.results_stack.setCurrentIndex(0)
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

    def _remove_layer_group(self, group_name: str) -> bool:
        """
        Detect if group_name exists in the layer tree. If it does, remove all its layers
        from the project and remove the group node. Returns True if removed, False otherwise.
        """
        proj = self.project if self.project else QgsProject.instance()
        root = proj.layerTreeRoot()
        grp = root.findGroup(group_name)
        if grp:
            layer_ids = [tree_layer.layerId() for tree_layer in grp.findLayers() if tree_layer and tree_layer.layerId()]
            if layer_ids:
                proj.removeMapLayers(layer_ids)
            still_grp = root.findGroup(group_name)
            if still_grp:
                root.removeChildNode(still_grp)
            return True
        return False

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

        # 1. Form 2 Data File (.csv / .json)
        if form2_path and os.path.exists(form2_path):
            try:
                layer_name = f"Form 2 ({os.path.basename(form2_path)})"
                if form2_path.lower().endswith(".csv"):
                    self._log_info(f"Loading Form 2 CSV into QGIS Layers via load_cbms_csv_to_layer: {os.path.basename(form2_path)}")
                    table_layer = load_cbms_csv_to_layer(form2_path, layer_name=layer_name, add_to_project=False)
                else:
                    self._log_info(f"Loading Form 2 JSON into QGIS Layers via load_cbms_json_to_layer: {os.path.basename(form2_path)}")
                    table_layer = load_cbms_json_to_layer(form2_path, layer_name=layer_name, add_to_project=False)

                if table_layer and table_layer.isValid():
                    proj.addMapLayer(table_layer, False)
                    inputs_group.addLayer(table_layer)
                    self._log_success(f"Form 2 table layer '{layer_name}' loaded into group '{group_name}'.")
                else:
                    self._log_error(f"Form 2 table layer is invalid: {form2_path}")
            except Exception as e:
                self._log_error(f"Failed to load Form 2 into QGIS Layers: {e}")

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
            self._switch_to_config(0)
            return

        if not points_path:
            QMessageBox.warning(
                self,
                "Missing Geotagged Points File",
                "Please specify the Geotagged Building Points (.geojson) in the 'Data Config' tab.",
            )
            self._switch_to_config(0)
            return

        if not os.path.exists(form2_path):
            QMessageBox.critical(
                self,
                "File Not Found",
                f"Form 2 Data File does not exist:\n{form2_path}",
            )
            self._switch_to_config(0)
            return

        if not os.path.exists(points_path):
            QMessageBox.critical(
                self,
                "File Not Found",
                f"Geotagged Building Points file does not exist:\n{points_path}",
            )
            self._switch_to_config(0)
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
            self._switch_to_config(1)
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
                self._switch_to_config(0)
                return

            selected_rules = [r for r in selected_rules if not r["has_base"]]
            if not selected_rules:
                QMessageBox.warning(
                    self,
                    "No Rules to Run",
                    "All selected rules require Base Layers (.gpkg). Please provide the Base Layers file to continue.",
                )
                self._switch_to_config(0)
                return

        # 4. Switch to Execution Logs tab and initialize session
        self._switch_to_config(2)
        self.btn_run.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Status: Initializing validation session...")

        self._log_step("INIT", "=== 2027 CBMS Form 2 Map Validation Session Started ===")
        self._log_info(f"Form 2 Data File (.json)    : {form2_path}")
        self._log_info(f"Geotagged Points (.geojson) : {points_path}")
        self._log_info(f"Base Layers (.gpkg)         : {base_path if base_path else '(None provided)'}")
        self._log_info(f"Destination                 : {'In-Memory Layers' if self.radio_memory.isChecked() else self.file_widget_gpkg.filePath()}")
        self._log_info(f"Queued Validation Algorithms: {len(selected_rules)}")

        # Clear previous results
        self._result_layers.clear()
        self._execution_summary.clear()

        # 5. Execution context and feedback
        self.context = QgsProcessingContext()
        self.context.setProject(self.project or QgsProject.instance())
        feedback = ProcessingFeedbackBridge(self._log_info, self._log_warning, self._log_error)

        # Load primary input data sources into QGIS Layers Panel if requested by user
        self._load_primary_input_sources_if_requested(form2_path, points_path, base_path)

        # Remove existing '2027 CBMS MV Results' group to prevent stale error layers
        if self.chk_group_layers.isChecked():
            if self._remove_layer_group("2027 CBMS MV Results"):
                self._log_info("Detected existing '2027 CBMS MV Results' layer group. Removed previous results before writing new layers.")

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

                    # Register in result layers dictionary for the Results Workspace tabs
                    self._result_layers[val_id] = {
                        "layer": out_layer,
                        "rule": rule,
                        "count": flagged_count,
                    }

                    # Add layer to QGIS canvas
                    if self.chk_load_canvas.isChecked():
                        if hasattr(self.context, "takeResultLayer"):
                            try:
                                take_lyr = self.context.takeResultLayer(out_dest if isinstance(out_dest, str) else out_layer.id())
                                if take_lyr and take_lyr.isValid():
                                    out_layer = take_lyr
                                    self._result_layers[val_id]["layer"] = out_layer
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

        # Populate Results Workspace and switch to it
        self._execution_summary = execution_summary
        self._populate_results_workspace(execution_summary, self._result_layers)
        self._switch_to_results()

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
