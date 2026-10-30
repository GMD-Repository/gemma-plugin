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
import tempfile
from typing import Optional, List, Dict, Any, Tuple, Callable

from qgis.core import (
    Qgis,
    NULL,
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
    QgsField,
    QgsWkbTypes,
)
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal, QSize, QEvent, QObject, QVariant
from qgis.PyQt.QtGui import QIcon, QColor, QFont, QTextCursor, QKeySequence, QPalette
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
    QDockWidget,
    QComboBox,
    QMenu,
)
try:
    from qgis.PyQt.QtWidgets import QAction, QActionGroup
except ImportError:
    try:
        from qgis.PyQt.QtGui import QAction, QActionGroup
    except ImportError:
        from PyQt5.QtWidgets import QAction, QActionGroup

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
    from qgis.PyQt import sip
except ImportError:
    try:
        import sip
    except ImportError:
        sip = None


def is_valid_qobject(obj) -> bool:
    """Safely check whether a Qt C++ wrapper object is still alive and not deleted."""
    if obj is None:
        return False
    if sip is not None:
        try:
            return not sip.isdeleted(obj)
        except (RuntimeError, TypeError, AttributeError):
            return False
    try:
        obj.objectName()
        return True
    except (RuntimeError, AttributeError):
        return False


def ensure_processing_initialized():
    """Ensure QGIS core Processing providers (including 'native') are registered and available."""
    try:
        from qgis.core import QgsApplication
        reg = QgsApplication.processingRegistry()
        if reg and (not reg.providerById("native") or not reg.algorithmById("native:refactorfields")):
            from processing.core.Processing import Processing
            Processing.initialize()
    except Exception:
        pass


def _is_empty_val(v) -> bool:
    """Check if an attribute value is empty, None, or NULL."""
    if v is None or v == NULL:
        return True
    s = str(v).strip()
    return not s or s.lower() in ("null", "none")


try:
    from .cbmsmv_review_dock import CbmsMvReviewDock
except (ImportError, ValueError):
    try:
        from cbmsmv_review_dock import CbmsMvReviewDock
    except (ImportError, ValueError):
        _ref_dir = os.path.dirname(__file__)
        if _ref_dir not in sys.path:
            sys.path.insert(0, _ref_dir)
        from cbmsmv_review_dock import CbmsMvReviewDock

try:
    from .cbms_mv_fix import get_fix_handler, has_fix, make_unique_feature_key
except (ImportError, ValueError):
    try:
        from cbms_mv_fix import get_fix_handler, has_fix, make_unique_feature_key
    except (ImportError, ValueError):
        _fix_dir = os.path.join(os.path.dirname(__file__), "cbms_mv_fix")
        if _fix_dir not in sys.path:
            sys.path.insert(0, _fix_dir)
        try:
            from cbms_mv_fix import get_fix_handler, has_fix, make_unique_feature_key
        except Exception:
            get_fix_handler = lambda v: None
            has_fix = lambda v: False
            make_unique_feature_key = lambda f, u: f"{f}_{u}" if (f and u) else (f"{f}_" if f else (f"_{u}" if u else ""))

try:
    from .cbms_mv_targets import (
        resolve_target_columns,
        CBMS_MV_RULE_TARGET_FIELDS,
        CBMS_MV_CATEGORIES,
        get_rule_category,
        get_category_info,
        get_rule_workflow_info,
    )
except (ImportError, ValueError):
    try:
        from cbms_mv_targets import (
            resolve_target_columns,
            CBMS_MV_RULE_TARGET_FIELDS,
            CBMS_MV_CATEGORIES,
            get_rule_category,
            get_category_info,
            get_rule_workflow_info,
        )
    except Exception:
        resolve_target_columns = lambda v, f, c=None: []
        CBMS_MV_RULE_TARGET_FIELDS = {}
        CBMS_MV_CATEGORIES = {}
        get_rule_category = lambda v: "other"
        get_category_info = lambda k: {"label": k.title(), "desc": "", "icon": "mActionOptions.svg"}
        get_rule_workflow_info = lambda v, f=0: (5000000, "Phase 5: Other Checks")


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
        target_fields = None

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

                # Check if BASE_LAYER parameter is assigned/used or TARGET_FIELDS declared
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "BASE_LAYER":
                                has_base_layer = True
                            elif target.id in ("TARGET_FIELDS", "TARGET_COLUMNS"):
                                if isinstance(node.value, (ast.List, ast.Tuple)):
                                    extracted = []
                                    for elt in node.value.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                            extracted.append(elt.value)
                                        elif hasattr(ast, "Str") and isinstance(elt, ast.Str):
                                            extracted.append(elt.s)
                                    if extracted:
                                        target_fields = extracted

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
            "category": get_rule_category(val_id),
            "has_base": has_base_layer,
            "target_fields": target_fields or CBMS_MV_RULE_TARGET_FIELDS.get(val_id, []),
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


# ---------------------------------------------------------------------------
# Horizontal Mouse Wheel Filter (Shift + Mouse Scroll Support on Windows)
# ---------------------------------------------------------------------------
class HorizontalScrollWheelFilter(QObject):
    """
    Event filter enabling Shift + Mouse Wheel horizontal scrolling
    for QAbstractItemView tables on Windows / Qt.
    """
    def __init__(self, parent_view: QAbstractItemView):
        super().__init__(parent_view)
        self.view = parent_view

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ShiftModifier:
                delta_y = event.angleDelta().y()
                delta_x = event.angleDelta().x()
                # On Windows, physical mouse scroll with Shift delivers vertical delta (delta_y != 0, delta_x == 0).
                # Redirect this to the horizontal scrollbar.
                if delta_y != 0 and delta_x == 0:
                    h_bar = self.view.horizontalScrollBar()
                    if h_bar and (h_bar.isVisible() or h_bar.maximum() > 0):
                        step = h_bar.singleStep() or 20
                        num_steps = int(delta_y / 120)
                        if num_steps == 0:
                            num_steps = 1 if delta_y > 0 else -1
                        # Wheel up (delta_y > 0) -> scroll left (decrease value)
                        # Wheel down (delta_y < 0) -> scroll right (increase value)
                        h_bar.setValue(h_bar.value() - num_steps * max(step * 3, 30))
                        event.accept()
                        return True
        return super().eventFilter(obj, event)


def enable_shift_scroll(table: QAbstractItemView):
    """Attach HorizontalScrollWheelFilter to table, viewport, and header."""
    if not table:
        return
    flt = HorizontalScrollWheelFilter(table)
    table.installEventFilter(flt)
    if table.viewport():
        table.viewport().installEventFilter(flt)
    if hasattr(table, "horizontalHeader") and table.horizontalHeader():
        table.horizontalHeader().installEventFilter(flt)
    table._shift_scroll_filter = flt


# ---------------------------------------------------------------------------
# Custom Sortable Table Widget Item (Numeric & Priority Ranking)
# ---------------------------------------------------------------------------
class SortableTableWidgetItem(QTableWidgetItem):
    """
    QTableWidgetItem supporting numeric and custom rank comparisons via Qt.UserRole
    before falling back to standard string comparison.
    """
    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            my_val = self.data(Qt.UserRole)
            other_val = other.data(Qt.UserRole)
            if my_val is not None and other_val is not None:
                try:
                    return my_val < other_val
                except TypeError:
                    pass
        return super().__lt__(other)

class CbmsmvDockWidget(QDockWidget):
    """
    Dedicated QDockWidget wrapper for docking the CBMS MV tool into QGIS.
    Tracks user closure explicitly via closeEvent to prevent spurious closes
    during drag-and-drop undocking or floating.
    """
    closed = pyqtSignal()

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(title, parent)

    def resizeEvent(self, event):
        """Ensure contained widget recalibrates dynamic frame dimensions when dock/floating window is resized."""
        super().resizeEvent(event)
        try:
            w = self.widget()
            if w and is_valid_qobject(w):
                w.setGeometry(self.rect())
                if w.layout():
                    w.layout().activate()
                w.updateGeometry()
                w.update()
        except Exception:
            pass

    def closeEvent(self, event):
        """Emit closed signal when user clicks the [X] button on the dock widget."""
        try:
            self.closed.emit()
        except Exception:
            pass
        super().closeEvent(event)


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
        self.chk_load_canvas = None
        self.chk_group_layers = None

        # Theme detection: check application / widget palette brightness
        palette = self.palette()
        bg_color = palette.color(palette.Window)
        self.current_theme = "dark" if bg_color.lightness() < 128 else "light"

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
        self._is_docked = False
        self._is_switching_dock = False
        self._user_toggled_load_inputs = False
        self._dock_widget: Optional[QDockWidget] = None
        ensure_processing_initialized()
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

        # Connect to project signals to keep load inputs default synchronized with layers panel
        if self.project:
            try:
                self.project.projectRead.connect(self._on_project_changed)
                self.project.cleared.connect(self._on_project_changed)
            except Exception:
                pass

        # Restore docked mode if user previously had it docked
        was_docked = self.settings.value("cbms_mv/is_docked", False, type=bool)
        if was_docked and self.iface and hasattr(self.iface, "addDockWidget"):
            QTimer.singleShot(50, lambda: self.dock_window() if is_valid_qobject(self) else None)

    @property
    def should_load_canvas(self) -> bool:
        """Safely determine if validation result layers should be added to QGIS canvas."""
        chk = getattr(self, "chk_load_canvas", None)
        return bool(chk and hasattr(chk, "isChecked") and chk.isChecked())

    @property
    def should_group_layers(self) -> bool:
        """Safely determine if validation result layers should be grouped under '2027 CBMS MV Results'."""
        chk = getattr(self, "chk_group_layers", None)
        return bool(chk and hasattr(chk, "isChecked") and chk.isChecked())

    @property
    def is_dark(self) -> bool:
        """Return True if running in dark mode/theme."""
        return getattr(self, "current_theme", "light") == "dark"

    def _get_theme_colors(self) -> Dict[str, str]:
        """Return semantic color palette adapted for light or dark mode."""
        if self.is_dark:
            return {
                "dialog_bg": "#202124",
                "surface_bg": "#292A2D",
                "surface_elevated": "#35363A",
                "surface_hover": "#3C4043",
                "border": "#484F58",
                "border_subtle": "#3C4043",
                "border_focus": "#58A6FF",
                "text_primary": "#E8EAED",
                "text_secondary": "#9AA0A6",
                "text_muted": "#80868B",
                "title": "#8AB4F8",
                "accent": "#1A73E8",
                "accent_hover": "#1765CC",
                "accent_pressed": "#1557B0",
                "accent_light": "#1C355E",
                "accent_light_text": "#8AB4F8",
                "accent_light_border": "#284E88",
                "success_bg": "#133A1E",
                "success_text": "#3FB950",
                "success_border": "#236E35",
                "success_hover": "#1B4D28",
                "danger_bg": "#3D1F1F",
                "danger_text": "#FF6B6B",
                "danger_border": "#6E2B2B",
                "danger_hover": "#502828",
                "danger_active_bg": "#4E2323",
                "danger_active_text": "#FEB2B2",
                "warning_bg": "#3D3300",
                "warning_text": "#FAF089",
                "warning_border": "#665400",
                "table_grid": "#3C4043",
                "table_header_bg": "#303134",
                "card_bg": "#292A2D",
                "card_hover_bg": "#303134",
                "console_bg": "#1A202C",
                "console_border": "#2D3748",
                "console_text": "#E2E8F0",
                "disabled_bg": "#2D3139",
                "disabled_text": "#5F6368",
                "disabled_border": "#3C4043",
                "selected_item_bg": "#17385E",
                "selected_item_text": "#8AB4F8",
                "target_col_bg": "#192738",
                "target_col_header_bg": "#1E334D",
                "target_col_border": "#58A6FF",
                "target_badge_bg": "#1C355E",
                "target_badge_text": "#8AB4F8",
                "target_badge_border": "#284E88",
            }
        else:
            return {
                "dialog_bg": "#F8F9FA",
                "surface_bg": "#FFFFFF",
                "surface_elevated": "#EDF2F7",
                "surface_hover": "#E2E8F0",
                "border": "#CBD5E0",
                "border_subtle": "#E2E8F0",
                "border_focus": "#3182CE",
                "text_primary": "#2D3748",
                "text_secondary": "#718096",
                "text_muted": "#A0AEC0",
                "title": "#1A365D",
                "accent": "#2B6CB0",
                "accent_hover": "#2C5282",
                "accent_pressed": "#1A365D",
                "accent_light": "#EBF8FF",
                "accent_light_text": "#2B6CB0",
                "accent_light_border": "#BEE3F8",
                "success_bg": "#F0FFF4",
                "success_text": "#22543D",
                "success_border": "#C6F6D5",
                "success_hover": "#C6F6D5",
                "danger_bg": "#FFF5F5",
                "danger_text": "#C53030",
                "danger_border": "#FEB2B2",
                "danger_hover": "#FED7D7",
                "danger_active_bg": "#FED7D7",
                "danger_active_text": "#9B2C2C",
                "warning_bg": "#FEFCBF",
                "warning_text": "#2D3748",
                "warning_border": "#F6E05E",
                "table_grid": "#EDF2F7",
                "table_header_bg": "#EDF2F7",
                "card_bg": "#FFFFFF",
                "card_hover_bg": "#F7FAFC",
                "console_bg": "#1A202C",
                "console_border": "#2D3748",
                "console_text": "#E2E8F0",
                "disabled_bg": "#F7FAFC",
                "disabled_text": "#A0AEC0",
                "disabled_border": "#E2E8F0",
                "selected_item_bg": "#EBF8FF",
                "selected_item_text": "#2B6CB0",
                "target_col_bg": "#F0F7FF",
                "target_col_header_bg": "#E1EFFF",
                "target_col_border": "#3182CE",
                "target_badge_bg": "#EBF8FF",
                "target_badge_text": "#2B6CB0",
                "target_badge_border": "#BEE3F8",
            }

    def _style_row_edit_button(self, btn: QPushButton):
        """Apply theme-aware styling to an Edit button in the feature table."""
        colors = self._get_theme_colors()
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent_light']};
                color: {colors['accent_light_text']};
                font-weight: 600;
                padding: 2px 7px;
                border-radius: 3px;
                border: 1px solid {colors['accent_light_border']};
                font-size: 10.5px;
            }}
            QPushButton:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['title']};
            }}
        """)

    def _style_row_fix_button(self, btn: QPushButton, enabled: bool = True, fixed: bool = False):
        """Apply theme-aware styling to a Fix button in the feature table."""
        colors = self._get_theme_colors()
        if fixed:
            succ_ic = QgsApplication.getThemeIcon("mIconSuccess.svg")
            if not succ_ic.isNull():
                btn.setIcon(succ_ic)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['success_bg']};
                    color: {colors['success_text']};
                    font-weight: bold;
                    padding: 2px 7px;
                    border-radius: 3px;
                    border: 1px solid {colors['success_border']};
                    font-size: 10.5px;
                }}
            """)
        elif enabled:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['success_bg']};
                    color: {colors['success_text']};
                    font-weight: 600;
                    padding: 2px 7px;
                    border-radius: 3px;
                    border: 1px solid {colors['success_border']};
                    font-size: 10.5px;
                }}
                QPushButton:hover {{
                    background-color: {colors['success_hover']};
                    color: {colors['success_text']};
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['disabled_bg']};
                    color: {colors['disabled_text']};
                    padding: 2px 7px;
                    border-radius: 3px;
                    border: 1px solid {colors['disabled_border']};
                    font-size: 10.5px;
                }}
            """)

    def _style_row_delete_button(self, btn: QPushButton, is_deleted: bool = False):
        """Apply theme-aware styling to a Delete button in the feature table."""
        colors = self._get_theme_colors()
        if is_deleted:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['danger_active_bg']};
                    color: {colors['danger_active_text']};
                    font-weight: 600;
                    padding: 2px 7px;
                    border-radius: 3px;
                    border: 1px solid {colors['danger_border']};
                    font-size: 10.5px;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['danger_bg']};
                    color: {colors['danger_text']};
                    font-weight: 600;
                    padding: 2px 7px;
                    border-radius: 3px;
                    border: 1px solid {colors['danger_border']};
                    font-size: 10.5px;
                }}
                QPushButton:hover {{
                    background-color: {colors['danger_hover']};
                    color: {colors['danger_active_text']};
                }}
            """)

    def _style_table_cell(self, item: QTableWidgetItem, state: str = "normal"):
        """Apply theme-aware background and foreground colors to a table cell."""
        colors = self._get_theme_colors()
        if state == "deleted":
            item.setBackground(QColor(colors["danger_active_bg"]))
            item.setForeground(QColor(colors["danger_active_text"]))
        elif state == "modified":
            item.setBackground(QColor(colors["warning_bg"]))
            item.setForeground(QColor(colors["warning_text"]))
        elif state == "fixed":
            item.setBackground(QColor(colors["success_bg"]))
            item.setForeground(QColor(colors["success_text"]))
        elif state == "target":
            item.setBackground(QColor(colors["target_col_bg"]))
            item.setForeground(QColor(colors["text_primary"]))
        else:
            item.setBackground(QColor(colors["surface_bg"]))
            item.setForeground(QColor(colors["text_primary"]))

    def _scroll_to_column(self, table: QTableWidget, col_name: str, field_names: List[str]):
        """Scroll the table horizontally to bring the target column into center view."""
        if not is_valid_qobject(self) or not is_valid_qobject(table):
            return
        if not table or not field_names or col_name not in field_names:
            return
        try:
            col_idx = field_names.index(col_name) + 1  # Account for column 0 (checkbox)
            if table.rowCount() > 0:
                item = table.item(0, col_idx)
                if item:
                    table.scrollToItem(item, QAbstractItemView.EnsureVisible)
            elif hasattr(table, "horizontalScrollBar"):
                h_bar = table.horizontalScrollBar()
                if h_bar:
                    col_x = table.columnViewportPosition(col_idx)
                    h_bar.setValue(max(0, col_x - 100))
        except (RuntimeError, Exception):
            pass

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
        # Root layout of the QDialog
        self._dialog_layout = QVBoxLayout(self)
        self._dialog_layout.setContentsMargins(0, 0, 0, 0)
        self._dialog_layout.setSpacing(0)

        # Central container holding the entire UI (can be reparented between dialog and dock widget)
        self._central_container = QWidget()
        self._central_container.setObjectName("cbmsmvCentralContainer")
        self._central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container_layout = QVBoxLayout(self._central_container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(8)

        # 1. Top Navigation Bar (compact)
        nav_bar = self._create_top_bar()
        container_layout.addWidget(nav_bar)

        # 2. Main View Stack: Page 0 = Results Workspace, Page 1 = Configuration View
        self.main_stack = QStackedWidget()
        self.main_stack.setObjectName("mainStack")

        self.page_results = self._create_page_results()
        self.page_config = self._create_page_config()

        self.main_stack.addWidget(self.page_results)  # index 0: Results
        self.main_stack.addWidget(self.page_config)   # index 1: Configuration

        # Backward compatibility alias
        self.tab_widget = self.config_tab_widget

        container_layout.addWidget(self.main_stack, stretch=1)

        # 3. Bottom Action Bar
        bottom_bar = self._create_bottom_action_bar()
        container_layout.addWidget(bottom_bar)

        self._dialog_layout.addWidget(self._central_container, 1)

    # -----------------------------------------------------------------------
    # Top Navigation Bar
    # -----------------------------------------------------------------------
    def _create_top_bar(self) -> QWidget:
        """Create a compact top navigation bar with dock toggle and view switch buttons."""
        bar = QFrame()
        bar.setObjectName("topNavBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 2, 4, 4)
        bar_layout.setSpacing(8)

        # Title badge
        lbl_title = QLabel("CBMS Form 2 Map Validation")
        lbl_title.setObjectName("lblDialogTitle")
        lbl_title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {self._get_theme_colors()['title']};")
        bar_layout.addWidget(lbl_title)

        bar_layout.addStretch()

        # Dock Toggle Button (Attribute Table style with native QGIS mDockify icon)
        self.btn_dock = QPushButton("Switch to Dock Mode")
        self.btn_dock.setObjectName("btnDock")
        dock_icon = QgsApplication.getThemeIcon("mDockify.svg")
        if not dock_icon.isNull():
            self.btn_dock.setIcon(dock_icon)
            self.btn_dock.setIconSize(QSize(16, 16))
        self.btn_dock.setToolTip("Dock this window at the bottom of the QGIS interface (like Attribute Table) (Ctrl+D)")
        self.btn_dock.setShortcut(QKeySequence("Ctrl+D"))
        self.btn_dock.clicked.connect(self.toggle_dock)
        bar_layout.addWidget(self.btn_dock)

        # View Switch Button
        self.btn_header_config = QPushButton("Configuration")
        self.btn_header_config.setObjectName("btnHeaderConfig")
        cfg_icon = QgsApplication.getThemeIcon("mActionOptions.svg")
        if not cfg_icon.isNull():
            self.btn_header_config.setIcon(cfg_icon)
            self.btn_header_config.setIconSize(QSize(16, 16))
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
            self.btn_header_config.setText("Configuration")
            cfg_icon = QgsApplication.getThemeIcon("mActionOptions.svg")
            if not cfg_icon.isNull():
                self.btn_header_config.setIcon(cfg_icon)
            self.btn_header_config.setToolTip("Configure input files, validation rules, and inspect logs")

    def _switch_to_config(self, tab_index: Optional[int] = None):
        """Switch to Configuration View (Page 1), optionally selecting a tab."""
        self.main_stack.setCurrentIndex(1)
        if tab_index is not None and hasattr(self, "config_tab_widget"):
            self.config_tab_widget.setCurrentIndex(tab_index)
        if hasattr(self, "btn_header_config"):
            self.btn_header_config.setText("Validation Results")
            res_icon = QgsApplication.getThemeIcon("mActionShowTable.svg")
            if not res_icon.isNull():
                self.btn_header_config.setIcon(res_icon)
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

        lbl_title = QLabel("Configuration & Validation Rules")
        lbl_title.setObjectName("lblConfigTitle")
        lbl_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {self._get_theme_colors()['title']};")
        top_bar.addWidget(lbl_title)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.config_tab_widget = QTabWidget()
        self.config_tab_widget.setObjectName("configTabWidget")
        self.config_tab_widget.setUsesScrollButtons(True)
        tb_config = self.config_tab_widget.tabBar()
        if tb_config is not None:
            tb_config.setElideMode(Qt.ElideNone)
            tb_config.setExpanding(False)
            tb_config.setUsesScrollButtons(True)

        self.tab_data_config = self._create_tab_data_config()
        self.tab_validation_rules = self._create_tab_validation_rules()
        self.tab_execution_logs = self._create_tab_execution_logs()

        data_icon = QgsApplication.getThemeIcon("mActionAddOgrLayer.svg")
        rules_icon = QgsApplication.getThemeIcon("mActionOptions.svg")
        logs_icon = QgsApplication.getThemeIcon("mMessageLog.svg")

        self.config_tab_widget.addTab(self.tab_data_config, data_icon if not data_icon.isNull() else QIcon(), "Data Config")
        self.config_tab_widget.addTab(self.tab_validation_rules, rules_icon if not rules_icon.isNull() else QIcon(), "Validation Rules")
        self.config_tab_widget.addTab(self.tab_execution_logs, logs_icon if not logs_icon.isNull() else QIcon(), "Execution Logs")

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
        self.results_tab_widget.setUsesScrollButtons(True)
        tb_results = self.results_tab_widget.tabBar()
        if tb_results is not None:
            tb_results.setElideMode(Qt.ElideNone)
            tb_results.setExpanding(False)
            tb_results.setUsesScrollButtons(True)
        self.results_tab_widget.currentChanged.connect(self._on_results_tab_changed)
        self.results_stack.addWidget(self.results_tab_widget)

        layout.addWidget(self.results_stack, stretch=1)
        return page

    def _on_results_tab_changed(self, index: int):
        """When switching to a category tab, auto-scroll the active check's table to the first target column."""
        if index <= 0:
            return
        cat_widget = self.results_tab_widget.widget(index)
        if not cat_widget:
            return
        stacked = cat_widget.findChild(QStackedWidget, "stackedCategoryTables")
        target_tab = stacked.currentWidget() if stacked else cat_widget
        if target_tab:
            table = target_tab.findChild(QTableWidget)
            if table and hasattr(table, "horizontalScrollBar") and table.horizontalScrollBar():
                QTimer.singleShot(50, lambda: table.horizontalScrollBar().setValue(0) if is_valid_qobject(self) and is_valid_qobject(table) else None)

    def _create_empty_state_widget(self) -> QWidget:
        """Create a clean empty state card shown before any validation has been executed."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(30, 40, 30, 40)

        colors = self._get_theme_colors()

        card = QFrame()
        card.setObjectName("emptyStateCard")
        card.setMaximumWidth(620)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignCenter)
        tbl_icon = QgsApplication.getThemeIcon("mActionShowTable.svg")
        if not tbl_icon.isNull():
            icon_lbl.setPixmap(tbl_icon.pixmap(48, 48))
        card_layout.addWidget(icon_lbl)

        title_lbl = QLabel("No Validation Results Yet")
        title_lbl.setObjectName("lblEmptyStateTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {colors['title']};")
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Configure your primary input files (Form 2 JSON, Geotagged Building Points GeoJSON, and Base GPKG) "
            "and select validation rules in Configuration, then click Run Validation.\n\n"
            "Flagged issues will be displayed here in separate tabs with full attribute inspection and QGIS canvas zoom."
        )
        desc_lbl.setObjectName("lblEmptyStateDesc")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"font-size: 11.5px; color: {colors['text_secondary']}; line-height: 1.5;")
        card_layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignCenter)

        btn_cfg = QPushButton("Open Configuration")
        btn_cfg.setObjectName("btnEmptyStateConfig")
        cfg_icon = QgsApplication.getThemeIcon("mActionOptions.svg")
        if not cfg_icon.isNull():
            btn_cfg.setIcon(cfg_icon)
        btn_cfg.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                font-weight: 600;
                padding: 8px 16px;
                border-radius: 6px;
                border: 1px solid {colors['border']};
                font-size: 11.5px;
            }}
            QPushButton:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['title']};
            }}
        """)
        btn_cfg.clicked.connect(lambda: self._switch_to_config(0))

        btn_quick_run = QPushButton("Run Validation")
        btn_quick_run.setObjectName("btnEmptyStateRun")
        run_icon = QgsApplication.getThemeIcon("mActionStart.svg")
        if not run_icon.isNull():
            btn_quick_run.setIcon(run_icon)
        btn_quick_run.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent']};
                color: #FFFFFF;
                font-weight: 600;
                padding: 8px 20px;
                border-radius: 6px;
                border: none;
                font-size: 11.5px;
            }}
            QPushButton:hover {{
                background-color: {colors['accent_hover']};
            }}
        """)
        btn_quick_run.clicked.connect(self.run_validation)

        btn_row.addWidget(btn_cfg)
        btn_row.addWidget(btn_quick_run)
        card_layout.addLayout(btn_row)

        layout.addWidget(card)
        return container

    def _create_category_tab(
        self,
        cat_key: str,
        cat_items: List[Tuple[str, Dict[str, Any]]],
    ) -> QWidget:
        """
        Create a Category Tab containing a top check-selector toolbar
        and a QStackedWidget switching between the check result tables.
        """
        colors = self._get_theme_colors()
        cat_info = get_category_info(cat_key)

        tab = QWidget()
        tab.setProperty("category_key", cat_key)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. Top Sub-Navigation Toolbar
        nav_frame = QFrame()
        nav_frame.setObjectName("categoryNavFrame")
        nav_frame.setStyleSheet(f"""
            #categoryNavFrame {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['border']};
                border-radius: 5px;
            }}
        """)
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(8, 6, 8, 6)
        nav_layout.setSpacing(8)

        # Category Icon & Label
        cat_ic = QgsApplication.getThemeIcon(cat_info["icon"])
        if not cat_ic.isNull():
            lbl_cat_icon = QLabel()
            lbl_cat_icon.setPixmap(cat_ic.pixmap(16, 16))
            nav_layout.addWidget(lbl_cat_icon)

        lbl_cat_title = QLabel(f"<b>{cat_info['label']}</b>")
        lbl_cat_title.setStyleSheet(f"font-size: 11.5px; color: {colors['title']};")
        lbl_cat_title.setToolTip(cat_info["desc"])
        nav_layout.addWidget(lbl_cat_title)

        nav_layout.addSpacing(6)

        lbl_select = QLabel("Validation Check:")
        lbl_select.setStyleSheet(f"font-size: 11px; color: {colors['text_secondary']};")
        nav_layout.addWidget(lbl_select)

        combo_checks = QComboBox()
        combo_checks.setObjectName("comboCategoryChecks")
        combo_checks.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 3px 8px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
                min-width: 260px;
            }}
            QComboBox:focus {{
                border-color: {colors['border_focus']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selected_item_bg']};
                selection-color: {colors['selected_item_text']};
            }}
        """)

        btn_prev_check = QToolButton()
        prev_ic = QgsApplication.getThemeIcon("mActionPrevious.svg")
        if not prev_ic.isNull():
            btn_prev_check.setIcon(prev_ic)
        else:
            btn_prev_check.setText("◀")
        btn_prev_check.setToolTip("Previous validation check in this category")

        btn_next_check = QToolButton()
        next_ic = QgsApplication.getThemeIcon("mActionNext.svg")
        if not next_ic.isNull():
            btn_next_check.setIcon(next_ic)
        else:
            btn_next_check.setText("▶")
        btn_next_check.setToolTip("Next validation check in this category")

        lbl_check_counter = QLabel(f"1 of {len(cat_items)} checks")
        lbl_check_counter.setStyleSheet(f"font-size: 10.5px; color: {colors['text_secondary']}; font-weight: 500;")

        nav_layout.addWidget(combo_checks, stretch=1)
        nav_layout.addWidget(btn_prev_check)
        nav_layout.addWidget(btn_next_check)
        nav_layout.addWidget(lbl_check_counter)

        layout.addWidget(nav_frame)

        # 2. QStackedWidget containing each check's table
        stacked_tables = QStackedWidget()
        stacked_tables.setObjectName("stackedCategoryTables")

        for idx, (val_id, item) in enumerate(cat_items):
            layer = item["layer"]
            rule = item["rule"]
            count = item["count"]
            check_name = rule["name"]

            err_table_tab = self._create_result_layer_tab(val_id, check_name, layer, count, rule=rule)
            stacked_tables.addWidget(err_table_tab)

            check_ic = QgsApplication.getThemeIcon("mIconCritical.svg" if count > 0 else "mIconSuccess.svg")
            combo_checks.addItem(
                check_ic if not check_ic.isNull() else QIcon(),
                f"{val_id} — {check_name} ({count:,})",
                val_id,
            )

        def _on_check_changed(idx: int):
            if idx < 0 or idx >= stacked_tables.count():
                return
            stacked_tables.setCurrentIndex(idx)
            lbl_check_counter.setText(f"{idx + 1} of {stacked_tables.count()} checks")
            btn_prev_check.setEnabled(idx > 0)
            btn_next_check.setEnabled(idx < stacked_tables.count() - 1)
            active_tab = stacked_tables.currentWidget()
            if active_tab:
                tbl = active_tab.findChild(QTableWidget)
                if tbl and hasattr(tbl, "horizontalScrollBar") and tbl.horizontalScrollBar():
                    QTimer.singleShot(50, lambda: tbl.horizontalScrollBar().setValue(0) if is_valid_qobject(self) and is_valid_qobject(tbl) else None)

        combo_checks.currentIndexChanged.connect(_on_check_changed)
        btn_prev_check.clicked.connect(lambda: combo_checks.setCurrentIndex(max(0, combo_checks.currentIndex() - 1)))
        btn_next_check.clicked.connect(lambda: combo_checks.setCurrentIndex(min(combo_checks.count() - 1, combo_checks.currentIndex() + 1)))

        _on_check_changed(0)
        layout.addWidget(stacked_tables, stretch=1)
        return tab

    def _populate_results_workspace(
        self,
        execution_summary: List[Dict[str, Any]],
        result_layers: Dict[str, Dict[str, Any]],
    ):
        """
        Populate the Results Workspace with:
          1. Tab 0: Summary Overview (Scorecard table of all executed rules)
          2. Category Tabs (Two-Tier layout): Grouped by error category with check-selection dropdown
        """
        self.results_tab_widget.clear()

        # Tab 0: Summary Overview
        summary_tab = self._create_summary_tab(execution_summary, result_layers)
        sum_icon = QgsApplication.getThemeIcon("mActionShowTable.svg")
        self.results_tab_widget.addTab(summary_tab, sum_icon if not sum_icon.isNull() else QIcon(), "Summary Overview")

        # Group result layers by category
        cat_groups: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for val_id, item in result_layers.items():
            cat = item["rule"].get("category") or get_rule_category(val_id)
            cat_groups.setdefault(cat, []).append((val_id, item))

        # Order categories logically according to CBMS_MV_CATEGORIES order
        ordered_cat_keys = [k for k in CBMS_MV_CATEGORIES.keys() if k in cat_groups]
        for k in cat_groups.keys():
            if k not in ordered_cat_keys:
                ordered_cat_keys.append(k)

        # Create Category Tabs
        for cat_key in ordered_cat_keys:
            cat_items = cat_groups[cat_key]
            cat_info = get_category_info(cat_key)
            cat_flag_count = sum(item["count"] for _, item in cat_items)

            cat_tab = self._create_category_tab(cat_key, cat_items)
            tab_title = f"{cat_info['label']} ({cat_flag_count:,})"
            tab_icon = QgsApplication.getThemeIcon(cat_info["icon"] if cat_flag_count > 0 else "mIconSuccess.svg")
            tab_index = self.results_tab_widget.addTab(cat_tab, tab_icon if not tab_icon.isNull() else QIcon(), tab_title)
            self.results_tab_widget.setTabToolTip(
                tab_index,
                f"{cat_info['label']} — {cat_flag_count:,} flagged feature(s) across {len(cat_items)} check(s)",
            )

        # Ensure tabs do not elide, do not compress, and show scroll buttons when needed
        tb = self.results_tab_widget.tabBar()
        if tb is not None:
            tb.setElideMode(Qt.ElideNone)
            tb.setExpanding(False)
            tb.setUsesScrollButtons(True)

        # Switch subpage of results_stack to show the tab widget
        self.results_stack.setCurrentIndex(1)
        self.results_tab_widget.setCurrentIndex(0)

    def _create_summary_tab(
        self,
        execution_summary: List[Dict[str, Any]],
        result_layers: Dict[str, Dict[str, Any]],
    ) -> QWidget:
        """Create the Summary Scorecard tab showing all executed rules with search, filtering, and sorting."""
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
        error_rules = total_rules - flagged_rules - clean_rules

        colors = self._get_theme_colors()

        # Scorecards with click-to-filter capability
        kpi_colors = {
            "tested": "#4DA3FF" if self.is_dark else "#2980B9",
            "passed": "#48BB78" if self.is_dark else "#27AE60",
            "flagged": "#F56565" if self.is_dark else "#E53E3E",
            "total": "#FC8181" if self.is_dark else "#C53030",
        }
        self._create_kpi_card(kpi_row, "Rules Tested", str(total_rules), kpi_colors["tested"], on_click=lambda: combo_filter.setCurrentIndex(0))
        self._create_kpi_card(kpi_row, "Passed (Clean)", str(clean_rules), kpi_colors["passed"], on_click=lambda: combo_filter.setCurrentIndex(2))
        self._create_kpi_card(kpi_row, "Rules Flagged", str(flagged_rules), kpi_colors["flagged"], on_click=lambda: combo_filter.setCurrentIndex(1))
        self._create_kpi_card(kpi_row, "Total Issues", f"{total_flags:,}", kpi_colors["total"], on_click=lambda: combo_sort.setCurrentIndex(1))

        layout.addLayout(kpi_row)

        # Filter & Search Toolbar (styled same as category nav bar)
        filter_frame = QFrame()
        filter_frame.setObjectName("summaryFilterFrame")
        filter_frame.setStyleSheet(f"""
            #summaryFilterFrame {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['border']};
                border-radius: 5px;
            }}
        """)
        filter_bar = QHBoxLayout(filter_frame)
        filter_bar.setContentsMargins(8, 6, 8, 6)
        filter_bar.setSpacing(8)

        # 1. Search Box
        search_edit = QLineEdit()
        filter_icon = QgsApplication.getThemeIcon("mActionFilter.svg")
        if not filter_icon.isNull():
            search_edit.addAction(filter_icon, QLineEdit.LeadingPosition)
        search_edit.setPlaceholderText("Search validation ID or check name...")
        search_edit.setClearButtonEnabled(True)
        search_edit.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 8px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {colors['border_focus']};
            }}
        """)
        filter_bar.addWidget(search_edit, stretch=2)

        # 2. Status Filter Combo
        combo_filter = QComboBox()
        combo_filter.addItem(f"Show: All Rules ({total_rules})", "all")
        crit_icon = QgsApplication.getThemeIcon("mIconCritical.svg")
        combo_filter.addItem(crit_icon if not crit_icon.isNull() else QIcon(), f"Flagged Only ({flagged_rules})", "flagged")
        succ_icon = QgsApplication.getThemeIcon("mIconSuccess.svg")
        combo_filter.addItem(succ_icon if not succ_icon.isNull() else QIcon(), f"Clean Only ({clean_rules})", "clean")
        if error_rules > 0:
            warn_icon = QgsApplication.getThemeIcon("mIconWarning.svg")
            combo_filter.addItem(warn_icon if not warn_icon.isNull() else QIcon(), f"Errors Only ({error_rules})", "error")
        combo_filter.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 10px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
                min-width: 140px;
            }}
            QComboBox:focus {{
                border-color: {colors['border_focus']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selected_item_bg']};
                selection-color: {colors['selected_item_text']};
            }}
        """)
        filter_bar.addWidget(combo_filter)

        # 3. Category Filter Combo
        combo_cat_filter = QComboBox()
        combo_cat_filter.addItem("Category: All", "all")
        used_cats = []
        for s in execution_summary:
            ck = s.get("category") or get_rule_category(s.get("id", ""))
            if ck not in used_cats:
                used_cats.append(ck)
        ordered_cats = [k for k in CBMS_MV_CATEGORIES.keys() if k in used_cats] + [k for k in used_cats if k not in CBMS_MV_CATEGORIES]
        for ck in ordered_cats:
            c_info = get_category_info(ck)
            c_count = sum(1 for s in execution_summary if (s.get("category") or get_rule_category(s.get("id", ""))) == ck)
            c_icon = QgsApplication.getThemeIcon(c_info["icon"])
            combo_cat_filter.addItem(c_icon if not c_icon.isNull() else QIcon(), f"{c_info['label']} ({c_count})", ck)
        combo_cat_filter.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 10px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
                min-width: 145px;
            }}
            QComboBox:focus {{
                border-color: {colors['border_focus']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selected_item_bg']};
                selection-color: {colors['selected_item_text']};
            }}
        """)
        filter_bar.addWidget(combo_cat_filter)

        # 4. Quick Sort Helper Combo
        combo_sort = QComboBox()
        combo_sort.addItem("Sort: Default", (6, Qt.AscendingOrder))
        combo_sort.addItem("Sort: Remaining Flags (High → Low)", (4, Qt.DescendingOrder))
        combo_sort.addItem("Sort: Remaining Flags (Low → High)", (4, Qt.AscendingOrder))
        combo_sort.addItem("Sort: Status (Flagged First)", (0, Qt.AscendingOrder))
        combo_sort.addItem("Sort: Category (A → Z)", (1, Qt.AscendingOrder))
        combo_sort.addItem("Sort: Validation ID (A → Z)", (2, Qt.AscendingOrder))
        combo_sort.addItem("Sort: Check Name (A → Z)", (3, Qt.AscendingOrder))
        combo_sort.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 10px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
                min-width: 165px;
            }}
            QComboBox:focus {{
                border-color: {colors['border_focus']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selected_item_bg']};
                selection-color: {colors['selected_item_text']};
            }}
        """)
        filter_bar.addWidget(combo_sort)

        # 5. Visible count label
        lbl_visible_count = QLabel(f"Showing {total_rules} of {total_rules} rules")
        lbl_visible_count.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 10.5px; font-weight: 500;")
        filter_bar.addWidget(lbl_visible_count)

        layout.addWidget(filter_frame)

        # Scorecard Table
        tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table = QTableWidget()
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Status",
            "Category",
            "Validation ID",
            "Validation Check Name",
            "Issues Flagged",
            "Action",
            "Workflow Rank",
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        table.setColumnHidden(6, True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setRowCount(len(execution_summary))

        ordered_summary = sorted(
            execution_summary,
            key=lambda item: get_rule_workflow_info(
                item.get("id", ""),
                flags=item.get("features_flagged", 0),
                status=item.get("status", ""),
            )[0]
        )

        for row, s in enumerate(ordered_summary):
            val_id = s.get("id", "")
            name = s.get("name", "")
            status = s.get("status", "")
            flags = s.get("features_flagged", 0)
            has_layer = val_id in result_layers

            # Workflow rank & phase label for dependency-based sorting
            wf_rank, wf_phase = get_rule_workflow_info(val_id, flags=flags, status=status)

            # 0. Status Badge
            if flags > 0:
                status_item = SortableTableWidgetItem("Flagged")
                crit_icon = QgsApplication.getThemeIcon("mIndicatorBadLayer.svg")
                if not crit_icon.isNull():
                    status_item.setIcon(crit_icon)
                status_item.setForeground(QColor("#FC8181" if self.is_dark else "#C53030"))
                status_item.setData(Qt.UserRole, 0)
            elif str(status).startswith(("Error", "Failed")):
                status_item = SortableTableWidgetItem("Error")
                warn_icon = QgsApplication.getThemeIcon("mIconWarning.svg")
                if not warn_icon.isNull():
                    status_item.setIcon(warn_icon)
                status_item.setForeground(QColor("#F6AD55" if self.is_dark else "#DD6B20"))
                status_item.setData(Qt.UserRole, 1)
            else:
                status_item = SortableTableWidgetItem("Clean")
                succ_icon = QgsApplication.getThemeIcon("mIconSuccess.svg")
                if not succ_icon.isNull():
                    status_item.setIcon(succ_icon)
                status_item.setForeground(QColor("#48BB78" if self.is_dark else "#27AE60"))
                status_item.setData(Qt.UserRole, 2)
            status_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setToolTip(f"Status: {status_item.text()}\nWorkflow Priority: {wf_phase}")
            table.setItem(row, 0, status_item)

            # 1. Category
            cat_key = s.get("category") or get_rule_category(val_id)
            cat_info = get_category_info(cat_key)
            cat_item = SortableTableWidgetItem(cat_info["label"])
            c_ic = QgsApplication.getThemeIcon(cat_info["icon"])
            if not c_ic.isNull():
                cat_item.setIcon(c_ic)
            cat_item.setData(Qt.UserRole, cat_key)
            cat_item.setFont(QFont("Segoe UI", 9))
            cat_item.setToolTip(f"Category: {cat_info['label']} — {cat_info['desc']}\nWorkflow Priority: {wf_phase}")
            table.setItem(row, 1, cat_item)

            # 2. Validation ID
            id_item = SortableTableWidgetItem(val_id)
            id_item.setFont(QFont("Consolas", 9))
            id_item.setData(Qt.UserRole, val_id)
            id_item.setToolTip(f"Validation ID: {val_id}\nWorkflow Priority: {wf_phase}")
            table.setItem(row, 2, id_item)

            # 3. Check Name
            name_item = SortableTableWidgetItem(name)
            name_item.setData(Qt.UserRole, name.lower())
            name_item.setToolTip(f"{name}\n\nRecommended Order: {wf_phase}")
            table.setItem(row, 3, name_item)

            # 4. Issues Flagged (numeric comparison)
            flags_item = SortableTableWidgetItem(f"{flags:,}")
            flags_item.setTextAlignment(Qt.AlignCenter)
            flags_item.setData(Qt.UserRole, int(flags))
            if flags > 0:
                flags_item.setForeground(QColor("#FC8181" if self.is_dark else "#C53030"))
                flags_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            else:
                flags_item.setForeground(QColor("#48BB78" if self.is_dark else "#27AE60"))
            table.setItem(row, 4, flags_item)

            # 5. Action Item (clickable item avoids setCellWidget detachment bug during sorting)
            if flags > 0 and has_layer:
                act_item = SortableTableWidgetItem("View Tab")
                fwd_icon = QgsApplication.getThemeIcon("mActionForward.svg")
                if not fwd_icon.isNull():
                    act_item.setIcon(fwd_icon)
                act_item.setTextAlignment(Qt.AlignCenter)
                act_item.setForeground(QColor(colors["accent_light_text"]))
                act_item.setBackground(QColor(colors["accent_light"]))
                act_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                act_item.setData(Qt.UserRole, 0)
                act_item.setToolTip(f"Click or double-click to switch to '{val_id}' results tab")
                table.setItem(row, 5, act_item)
            else:
                empty_act = SortableTableWidgetItem("—")
                empty_act.setTextAlignment(Qt.AlignCenter)
                empty_act.setForeground(QColor(colors["text_muted"]))
                empty_act.setData(Qt.UserRole, 1)
                table.setItem(row, 5, empty_act)

            # 6. Workflow Rank (Hidden column for native Qt item sorting)
            rank_item = SortableTableWidgetItem(str(wf_rank))
            rank_item.setData(Qt.UserRole, int(wf_rank))
            table.setItem(row, 6, rank_item)

            # Ensure all summary scorecard items are strictly read-only
            for col_i in range(7):
                it = table.item(row, col_i)
                if it:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        # Filter logic
        def _apply_filter():
            search_txt = search_edit.text().strip().lower()
            mode = combo_filter.currentData()
            sel_cat = combo_cat_filter.currentData()
            visible = 0
            for r in range(table.rowCount()):
                st_item = table.item(r, 0)
                cat_item = table.item(r, 1)
                id_item = table.item(r, 2)
                name_item = table.item(r, 3)
                flag_item = table.item(r, 4)
                if not (st_item and cat_item and id_item and name_item and flag_item):
                    continue
                flags_val = flag_item.data(Qt.UserRole) or 0
                st_rank = st_item.data(Qt.UserRole)
                cat_val = cat_item.data(Qt.UserRole) or ""

                match_mode = True
                if mode == "flagged":
                    match_mode = (flags_val > 0)
                elif mode == "clean":
                    match_mode = (flags_val == 0 and st_rank == 2)
                elif mode == "error":
                    match_mode = (st_rank == 1)

                match_cat = True
                if sel_cat and sel_cat != "all":
                    match_cat = (cat_val == sel_cat)

                match_search = True
                if search_txt:
                    match_search = (
                        search_txt in id_item.text().lower()
                        or search_txt in name_item.text().lower()
                        or search_txt in cat_item.text().lower()
                    )

                show = match_mode and match_cat and match_search
                table.setRowHidden(r, not show)
                if show:
                    visible += 1

            lbl_visible_count.setText(f"Showing {visible} of {table.rowCount()} rules")

        search_edit.textChanged.connect(_apply_filter)
        combo_filter.currentIndexChanged.connect(_apply_filter)
        combo_cat_filter.currentIndexChanged.connect(_apply_filter)

        # Sort combo handler
        def _on_sort_changed(index):
            data = combo_sort.itemData(index)
            if data and isinstance(data, (tuple, list)):
                col, order = data
                if col >= 0:
                    table.sortItems(col, order)

        combo_sort.currentIndexChanged.connect(_on_sort_changed)

        # Connect cell click and double-click to jump to tab
        def _on_summary_cell_clicked(row, col):
            if col == 5:
                id_it = table.item(row, 2)
                if id_it:
                    self._jump_to_result_tab(id_it.text())

        def _on_summary_row_double_clicked(row, col):
            id_it = table.item(row, 2)
            if id_it:
                self._jump_to_result_tab(id_it.text())

        table.cellClicked.connect(_on_summary_cell_clicked)
        table.cellDoubleClicked.connect(_on_summary_row_double_clicked)

        # Enable sorting & horizontal scroll
        table.setSortingEnabled(True)
        enable_shift_scroll(table)

        # Default sort: Recommended Workflow (Phase 1 → 4) so operators follow the logical fix pipeline
        table.sortItems(6, Qt.AscendingOrder)
        combo_sort.setCurrentIndex(0)

        layout.addWidget(table, stretch=1)
        return tab

    def _jump_to_result_tab(self, val_id: str):
        """Switch results_tab_widget to the category tab and check matching val_id."""
        if not val_id:
            return
        target = str(val_id)
        for ti in range(1, self.results_tab_widget.count()):
            tab_widget = self.results_tab_widget.widget(ti)
            if not tab_widget:
                continue
            combo = tab_widget.findChild(QComboBox, "comboCategoryChecks")
            if combo:
                idx = combo.findData(target)
                if idx >= 0:
                    self.results_tab_widget.setCurrentIndex(ti)
                    combo.setCurrentIndex(idx)
                    return
            if target in self.results_tab_widget.tabText(ti):
                self.results_tab_widget.setCurrentIndex(ti)
                return

    def _create_result_layer_tab(
        self,
        val_id: str,
        check_name: str,
        layer: QgsVectorLayer,
        count: int,
        rule: Optional[Dict[str, Any]] = None,
    ) -> QWidget:
        """Create an interactive feature table tab with in-place cell editing, multiselect, and fix actions."""
        tab = QWidget()
        tab.setProperty("val_id", val_id)
        tab.setProperty("check_name", check_name)

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Resolve target columns for highlighting, chips, and auto-scroll
        field_names = [f.name() for f in layer.fields()] if layer and layer.isValid() else []
        rule_target_fields = rule.get("target_fields") if rule else None
        target_cols = resolve_target_columns(val_id, field_names, rule_target_fields)
        has_auto_fix = bool(has_fix(val_id))

        tab.setProperty("target_cols", target_cols)
        tab.setProperty("field_names", field_names)

        # Title & count (Header above toolbar)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        colors = self._get_theme_colors()
        lbl_vname = QLabel(f"<b>{check_name}</b>")
        lbl_vname.setWordWrap(False)
        lbl_vname.setToolTip(f"{check_name}\n(Validation ID: {val_id})")
        lbl_vname.setStyleSheet(f"font-size: 11px; color: {colors['title']};")
        
        success_col = "#3FB950" if self.is_dark else "#2F855A"
        danger_col = "#FC8181" if self.is_dark else "#C53030"
        if count == 0:
            lbl_vcount = QLabel(
                f"<span style='color: {success_col}; font-weight: bold;'>0 flagged features.</span> "
                "All issues for this validation check are resolved!"
            )
        else:
            lbl_vcount = QLabel(
                f"<span style='color: {danger_col}; font-weight: bold;'>{count:,}</span> flagged feature(s) detected. "
                f"Click row to zoom; double-click cell to edit in-place."
            )
        lbl_vcount.setWordWrap(False)
        lbl_vcount.setToolTip("Click row to zoom; double-click cell to edit in-place.")
        lbl_vcount.setStyleSheet(f"font-size: 10px; color: {colors['text_secondary']};")
        title_box.addWidget(lbl_vname)
        title_box.addWidget(lbl_vcount)
        layout.addLayout(title_box)

        # Mini Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        # Search filter
        edit_filter = QLineEdit()
        filter_icon = QgsApplication.getThemeIcon("mActionFilter.svg")
        if not filter_icon.isNull():
            edit_filter.addAction(filter_icon, QLineEdit.LeadingPosition)
        edit_filter.setPlaceholderText("Filter rows...")
        edit_filter.setClearButtonEnabled(True)
        edit_filter.setMinimumWidth(110)
        edit_filter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit_filter.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 8px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {colors['border_focus']};
            }}
        """)
        toolbar.addWidget(edit_filter, stretch=1)

        # Select All / None toggle
        btn_select_all = QPushButton("Select All")
        sel_icon = QgsApplication.getThemeIcon("mActionSelectAll.svg")
        if not sel_icon.isNull():
            btn_select_all.setIcon(sel_icon)
        btn_select_all.setToolTip("Toggle select all or none of visible rows")
        btn_select_all.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        btn_select_all.setMinimumWidth(98)
        btn_select_all.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                font-weight: 600;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid {colors['border']};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['title']};
            }}
        """)
        toolbar.addWidget(btn_select_all)

        # Actions Normal Dropdown (placed to the right of Select All)
        combo_actions = QComboBox()
        combo_actions.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo_actions.setMinimumContentsLength(8)
        combo_actions.setMaximumWidth(210)
        combo_actions.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if combo_actions.view():
            combo_actions.view().setMinimumWidth(380)
        dropdown_icon = QgsApplication.getThemeIcon("mActionOptions.svg")
        if not dropdown_icon.isNull():
            combo_actions.addItem(dropdown_icon, "Actions")
        else:
            combo_actions.addItem("Actions")

        concat_ic = QgsApplication.getThemeIcon("mActionCalculateField.svg")
        if not concat_ic.isNull():
            combo_actions.addItem(concat_ic, "Concatenate the ea_geocode")
        else:
            combo_actions.addItem("Concatenate the ea_geocode")

        del_icon_menu = QgsApplication.getThemeIcon("mActionDeleteSelected.svg")
        if not del_icon_menu.isNull():
            combo_actions.addItem(del_icon_menu, "Delete selected features")
        else:
            combo_actions.addItem("Delete selected features")

        geom_ic = QgsApplication.getThemeIcon("mActionCapturePoint.svg")
        if not geom_ic.isNull():
            combo_actions.addItem(geom_ic, "Generate point geometry")
        else:
            combo_actions.addItem("Generate point geometry")

        dup_ic = QgsApplication.getThemeIcon("mActionDeleteSelected.svg")
        if not dup_ic.isNull():
            combo_actions.addItem(dup_ic, "Delete duplicate features (retain one)")
        else:
            combo_actions.addItem("Delete duplicate features (retain one)")

        concat_bsn_ic = QgsApplication.getThemeIcon("mActionCalculateField.svg")
        if not concat_bsn_ic.isNull():
            combo_actions.addItem(concat_bsn_ic, "Concatenate the bsn_geoid")
        else:
            combo_actions.addItem("Concatenate the bsn_geoid")

        copy_geom_ic = QgsApplication.getThemeIcon("mActionEditCopy.svg")
        if not copy_geom_ic.isNull():
            combo_actions.addItem(copy_geom_ic, "Copy the geometry and paste it into the longitude and latitude columns")
        else:
            combo_actions.addItem("Copy the geometry and paste it into the longitude and latitude columns")

        update_coord_ic = QgsApplication.getThemeIcon("mActionCalculateField.svg")
        if not update_coord_ic.isNull():
            combo_actions.addItem(update_coord_ic, "Update Datafile's Coordinates")
        else:
            combo_actions.addItem("Update Datafile's Coordinates")

        update_geom_ic = QgsApplication.getThemeIcon("mActionMoveFeaturePoint.svg")
        if update_geom_ic.isNull():
            update_geom_ic = QgsApplication.getThemeIcon("mActionCapturePoint.svg")
        if not update_geom_ic.isNull():
            combo_actions.addItem(update_geom_ic, "Update point geometry using sf_longitude and sf_latitude")
        else:
            combo_actions.addItem("Update point geometry using sf_longitude and sf_latitude")

        combo_actions.setCursor(Qt.PointingHandCursor)
        combo_actions.setToolTip("Select an action to execute for checked features")

        arrow_icon_name = "arrow_down_dark.svg" if self.is_dark else "arrow_down.svg"
        arrow_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", arrow_icon_name)
        ).replace("\\", "/")

        combo_actions.setStyleSheet(f"""
            QComboBox {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                font-weight: 600;
                padding: 5px 24px 5px 8px;
                border-radius: 4px;
                border: 1px solid {colors['border']};
                font-size: 11px;
                min-height: 18px;
                min-width: 200px;
                max-width: 250px;
            }}
            QComboBox:hover {{
                background-color: {colors['surface_hover']};
                border-color: {colors['border_focus']};
                color: {colors['title']};
            }}
            QComboBox:focus {{
                border-color: {colors['border_focus']};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid {colors['border']};
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                background-color: {colors['surface_elevated']};
            }}
            QComboBox::drop-down:hover {{
                background-color: {colors['surface_hover']};
            }}
            QComboBox::down-arrow {{
                image: url('{arrow_path}');
                width: 9px;
                height: 9px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 0px;
                font-size: 11px;
                selection-background-color: {colors['selected_item_bg']};
                selection-color: {colors['selected_item_text']};
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 12px;
                min-height: 22px;
            }}
        """)

        # Update Selected Button (placed to the right of the Action dropdown button)
        btn_update_selected = QPushButton("Apply Fix Action")
        apply_icon = QgsApplication.getThemeIcon("mActionApply.svg")
        if not apply_icon.isNull():
            btn_update_selected.setIcon(apply_icon)
        else:
            calc_icon = QgsApplication.getThemeIcon("mActionCalculateField.svg")
            if not calc_icon.isNull():
                btn_update_selected.setIcon(calc_icon)
        btn_update_selected.setCursor(Qt.PointingHandCursor)
        btn_update_selected.setToolTip("Execute the selected action from the dropdown on all checked features")
        btn_update_selected.setEnabled(False)
        btn_update_selected.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        btn_update_selected.setMinimumWidth(138)
        btn_update_selected.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent_light']};
                color: {colors['accent_light_text']};
                font-weight: bold;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid {colors['accent_light_border']};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['title']};
            }}
            QPushButton:disabled {{
                background-color: {colors['disabled_bg']};
                color: {colors['disabled_text']};
                border-color: {colors['disabled_border']};
            }}
        """)

        def _on_trigger_update_selected():
            if not is_valid_qobject(self):
                return
            checked_count = sum(
                1 for r in range(table.rowCount())
                if table.item(r, 0) and table.item(r, 0).checkState() == Qt.Checked
            )
            sel_count = (
                len(set(i.row() for i in table.selectionModel().selectedRows()))
                if hasattr(table, "selectionModel") and table.selectionModel()
                else 0
            )
            idx = combo_actions.currentIndex()
            if checked_count == 0 and sel_count == 0:
                if idx == 4:
                    reply = QMessageBox.question(
                        self,
                        "Check All Records for Duplicates?",
                        "No rows are ticked.\n\n"
                        "Do you want to check all records in this tab for duplicates?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes,
                    )
                    if reply != QMessageBox.Yes:
                        return
                    self._on_deduplicate_features(
                        val_id, layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected, process_all=True
                    )
                    return

                QMessageBox.information(
                    self,
                    "Nothing Selected",
                    "Please tick the box of at least one row before clicking Update Selected."
                )
                return

            if idx == 1:
                self._on_concatenate_ea_geocode(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            elif idx == 2:
                self._delete_selected_features(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            elif idx == 3:
                self._on_generate_point_geometry(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            elif idx == 4:
                self._on_deduplicate_features(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            elif idx == 5 or "bsn_geoid" in combo_actions.itemText(idx).lower() or "bsn" in combo_actions.itemText(idx).lower():
                self._on_concatenate_bsn_geoid(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            elif idx == 6 or ("copy" in combo_actions.itemText(idx).lower() and ("geometry" in combo_actions.itemText(idx).lower() or "longitude" in combo_actions.itemText(idx).lower() or "latitude" in combo_actions.itemText(idx).lower())):
                self._on_copy_geometry_to_coordinates(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            elif idx == 7 or ("update" in combo_actions.itemText(idx).lower() and "datafile" in combo_actions.itemText(idx).lower()):
                self._on_update_datafile_coordinates(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            elif idx == 8 or ("update" in combo_actions.itemText(idx).lower() and ("geometry" in combo_actions.itemText(idx).lower() or "sf_longitude" in combo_actions.itemText(idx).lower())):
                self._on_update_point_geometry(
                    layer, table, combo_actions=combo_actions, btn_update_selected=btn_update_selected
                )
            else:
                QMessageBox.information(
                    self,
                    "Choose an Action",
                    "Please choose an action from the Actions dropdown first."
                )

        btn_update_selected.clicked.connect(_on_trigger_update_selected)

        def _on_combo_actions_changed(idx: int):
            if not is_valid_qobject(self) or not is_valid_qobject(table):
                return
            combo_actions.setToolTip(combo_actions.itemText(idx))
            action_text = combo_actions.itemText(idx).lower()
            if "duplicate" in action_text or idx == 4:
                # Automatically select/check all features in the tab
                table.setProperty("is_populating", True)
                visible_count = 0
                for r in range(table.rowCount()):
                    if not table.isRowHidden(r):
                        it = table.item(r, 0)
                        if it:
                            it.setCheckState(Qt.Checked)
                            visible_count += 1
                table.setProperty("is_populating", False)
                table.selectAll()
                btn_update_selected.setText(f"Apply Fix Action ({visible_count})" if visible_count > 0 else "Apply Fix Action")
                btn_update_selected.setEnabled(visible_count > 0)
                if btn_select_all:
                    btn_select_all.setText("Select None")
                    toggle_ic = QgsApplication.getThemeIcon("mActionDeselectAll.svg")
                    if not toggle_ic.isNull():
                        btn_select_all.setIcon(toggle_ic)
            else:
                checked_count = sum(
                    1 for r in range(table.rowCount())
                    if not table.isRowHidden(r) and table.item(r, 0) and table.item(r, 0).checkState() == Qt.Checked
                )
                sel_count = (
                    len(set(i.row() for i in table.selectionModel().selectedRows() if not table.isRowHidden(i.row())))
                    if hasattr(table, "selectionModel") and table.selectionModel()
                    else 0
                )
                active_sel_count = checked_count if checked_count > 0 else sel_count
                btn_update_selected.setText(f"Apply Fix Action ({active_sel_count})" if active_sel_count > 0 else "Apply Fix Action")
                btn_update_selected.setEnabled(active_sel_count > 0)

        combo_actions.currentIndexChanged.connect(_on_combo_actions_changed)
        combo_actions.activated.connect(_on_combo_actions_changed)

        toolbar.addWidget(combo_actions)
        toolbar.addWidget(btn_update_selected)


        # Save Layer Changes
        btn_save_changes = QPushButton("Save Changes")
        save_icon = QgsApplication.getThemeIcon("mActionSaveEdits.svg")
        if not save_icon.isNull():
            btn_save_changes.setIcon(save_icon)
        btn_save_changes.setToolTip("Commit edits on GeoJSON and JSON to disk and re-run check (Ctrl+S)")
        btn_save_changes.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        btn_save_changes.setMinimumWidth(125)
        btn_save_changes.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent_light']};
                color: {colors['accent_light_text']};
                font-weight: bold;
                padding: 5px 12px;
                border-radius: 4px;
                border: 1px solid {colors['accent_light_border']};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['title']};
            }}
        """)
        btn_save_changes.clicked.connect(lambda checked=False, v=val_id: self._prompt_save_confirmation(v))
        toolbar.addWidget(btn_save_changes)

        layout.addLayout(toolbar)

        # Feature Table
        table = QTableWidget()
        enable_shift_scroll(table)

        # Target Field Hint Bar with Quick Focus Chips
        if target_cols:
            hint_bar = QHBoxLayout()
            hint_bar.setContentsMargins(2, 0, 2, 2)
            hint_bar.setSpacing(6)

            lbl_hint = QLabel("<b>Target Field(s) to Review/Edit:</b>")
            lbl_hint.setStyleSheet(f"font-size: 11px; color: {colors['target_badge_text']};")
            hint_bar.addWidget(lbl_hint)

            for t_col in target_cols:
                btn_chip = QPushButton(t_col)
                pin_icon = QgsApplication.getThemeIcon("mActionHighlightFeature.svg")
                if not pin_icon.isNull():
                    btn_chip.setIcon(pin_icon)
                    btn_chip.setIconSize(QSize(12, 12))
                btn_chip.setCursor(Qt.PointingHandCursor)
                btn_chip.setToolTip(f"Click to scroll directly to '{t_col}' column")
                btn_chip.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {colors['target_badge_bg']};
                        color: {colors['target_badge_text']};
                        border: 1px solid {colors['target_badge_border']};
                        border-radius: 10px;
                        padding: 2px 8px;
                        font-size: 10.5px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{
                        background-color: {colors['accent_hover']};
                        color: #FFFFFF;
                        border-color: {colors['accent_hover']};
                    }}
                """)
                btn_chip.clicked.connect(lambda checked=False, c=t_col: self._scroll_to_column(table, c, field_names))
                hint_bar.addWidget(btn_chip)

            hint_bar.addStretch()
            layout.addLayout(hint_bar)

        # Ensure sf_status exists on layer if building point geojson status is present
        if layer and layer.isValid():
            has_status_field = any(f.name().lower() in ("status", "sf_status") for f in layer.fields())
            if not has_status_field:
                try:
                    layer.dataProvider().addAttributes([QgsField("sf_status", QVariant.String)])
                    layer.updateFields()
                except Exception:
                    pass

        headers = [""] + [fn for fn in field_names] + ["Action"]
        action_col = len(headers) - 1
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        h_item0 = table.horizontalHeaderItem(0)
        if h_item0:
            sel_icon = QgsApplication.getThemeIcon("mActionSelectAll.svg")
            if not sel_icon.isNull():
                h_item0.setIcon(sel_icon)
            h_item0.setToolTip("Select / Deselect All")

        for c_idx, fn in enumerate(field_names):
            if fn in target_cols:
                h_item = table.horizontalHeaderItem(c_idx + 1)
                if h_item:
                    pin_icon = QgsApplication.getThemeIcon("mActionHighlightFeature.svg")
                    if not pin_icon.isNull():
                        h_item.setIcon(pin_icon)
                    h_item.setToolTip(f"Target column for validation check '{val_id}' (review/edit this field)")
                    h_item.setForeground(QColor(colors["target_badge_text"]))

        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(True)
        table.verticalHeader().setCursor(Qt.PointingHandCursor)
        table.verticalHeader().setToolTip("Click row number to select row, toggle checkbox, and zoom to feature")

        table.setColumnWidth(0, 38)
        table.setColumnWidth(action_col, 80)
        table.setColumnHidden(action_col, True)

        table.setProperty("is_populating", True)

        if layer and layer.isValid():
            features = list(layer.getFeatures())
            table.setRowCount(len(features))
            table.setSortingEnabled(False)

            field_names_lower = {f.name().lower(): f.name() for f in layer.fields()}
            sf_fid_col = field_names_lower.get("sf_fid")
            df_fid_col = field_names_lower.get("df_fid")
            fid_col = sf_fid_col or field_names_lower.get("fid") or df_fid_col

            sf_uuid_col = field_names_lower.get("sf_map_uuid") or field_names_lower.get("sf_mapid")
            df_uuid_col = field_names_lower.get("df_map_uuid") or field_names_lower.get("df_mapid")
            uuid_col = sf_uuid_col or field_names_lower.get("map_uuid") or field_names_lower.get("mapid") or df_uuid_col or field_names_lower.get("uuid")

            def _is_empty(v):
                if v is None or v == NULL:
                    return True
                s = str(v).strip()
                return not s or s.lower() in ("null", "none")

            for row_idx, feat in enumerate(features):
                err_fid = feat.id()
                # Resolve source IDs for GeoJSON (sf_) and Form 2 JSON (df_)
                raw_fid = feat[fid_col] if fid_col else None
                source_fid = raw_fid if (fid_col and not _is_empty(raw_fid)) else feat.id()
                raw_sf_fid = feat[sf_fid_col] if sf_fid_col else None
                sf_fid_val = raw_sf_fid if (sf_fid_col and not _is_empty(raw_sf_fid)) else None
                raw_df_fid = feat[df_fid_col] if df_fid_col else None
                df_fid_val = raw_df_fid if (df_fid_col and not _is_empty(raw_df_fid)) else None

                sf_uuid_val = feat[sf_uuid_col] if sf_uuid_col else None
                sf_uuid_str = str(sf_uuid_val).strip() if (sf_uuid_val is not None and not _is_empty(sf_uuid_val)) else ""
                df_uuid_val = feat[df_uuid_col] if df_uuid_col else None
                df_uuid_str = str(df_uuid_val).strip() if (df_uuid_val is not None and not _is_empty(df_uuid_val)) else ""
                uuid_val = feat[uuid_col] if uuid_col else None
                uuid_str = str(uuid_val).strip() if (uuid_val is not None and not _is_empty(uuid_val)) else ""
                if not uuid_str:
                    uuid_str = df_uuid_str or sf_uuid_str or ""

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
                is_row_deleted = False
                for col_idx, fname in enumerate(field_names):
                    val = feat[fname]
                    val_str = "" if val is None else str(val)
                    item = QTableWidgetItem(val_str)
                    fn_lower = fname.lower()
                    if (fn_lower in ("status", "sf_status") and val_str.strip().lower() == "deleted") or (
                        fn_lower in ("is_deleted", "sf_is_deleted") and (val is True or val_str.strip().lower() in ("true", "1", "deleted"))
                    ):
                        is_row_deleted = True
                        self._style_table_cell(item, "deleted")
                    elif fn_lower in ("fid", "sf_fid", "df_fid", "ref_fid"):
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        item.setToolTip("Record FID (read-only primary key anchor)")
                        if fname in target_cols:
                            self._style_table_cell(item, "target")
                    elif fn_lower.startswith("ref_"):
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        item.setToolTip("Reference dataset attribute (read-only)")
                        if fname in target_cols:
                            self._style_table_cell(item, "target")
                    elif fn_lower in ("x_geometry", "y_geometry", "distance_m"):
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        item.setToolTip("Derived geometry value (read-only)")
                        if fname in target_cols:
                            self._style_table_cell(item, "target")
                    else:
                        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                        if fname in target_cols:
                            self._style_table_cell(item, "target")
                            item.setToolTip(f"Target field for '{val_id}' — review or edit this value")
                    item.setData(Qt.UserRole, source_fid)
                    item.setData(Qt.UserRole + 1, uuid_str)
                    item.setData(Qt.UserRole + 2, fname)
                    item.setData(Qt.UserRole + 3, err_fid)
                    item.setData(Qt.UserRole + 4, df_fid_val)
                    item.setData(Qt.UserRole + 5, df_uuid_str)
                    item.setData(Qt.UserRole + 6, sf_fid_val)
                    item.setData(Qt.UserRole + 7, sf_uuid_str)
                    item.setData(Qt.UserRole + 20, val_str)
                    table.setItem(row_idx, col_idx + 1, item)

                # Column Action: Edit button only (commented out until a dedicated workflow is defined)
                # action_widget = QWidget()
                # action_layout = QHBoxLayout(action_widget)
                # action_layout.setContentsMargins(4, 2, 4, 2)
                # action_layout.setSpacing(4)
                # action_layout.setAlignment(Qt.AlignCenter)
                #
                # btn_row_edit = QPushButton("Edit")
                # btn_row_edit.setToolTip(f"Open Navigation Review Dock / Feature Form for feature #{row_idx + 1}")
                # self._style_row_edit_button(btn_row_edit)
                # btn_row_edit.clicked.connect(
                #     lambda checked=False, s_id=source_fid, u=uuid_str, df_u=df_uuid_str, sf_u=sf_uuid_str: self._launch_review_dock(
                #         val_id, check_name, layer, target_fid=s_id, target_uuid=u or df_u or sf_u
                #     )
                # )
                # action_layout.addWidget(btn_row_edit)
                #
                # table.setCellWidget(row_idx, action_col, action_widget)

            table.setSortingEnabled(True)

        table.setProperty("is_populating", False)

        # Wire Signals
        table.itemChanged.connect(
            lambda item: self._on_table_item_changed(
                val_id, layer, table, item, combo_actions=combo_actions, btn_update_selected=btn_update_selected
            )
        )
        table.itemClicked.connect(
            lambda item: self._on_table_row_clicked(
                layer, table, item.row(), col=item.column(), combo_actions=combo_actions, btn_update_selected=btn_update_selected
            )
        )
        table.verticalHeader().sectionClicked.connect(
            lambda row: self._on_vertical_header_section_clicked(
                layer, table, row, combo_actions=combo_actions, btn_update_selected=btn_update_selected
            )
        )
        table.horizontalHeader().sectionClicked.connect(
            lambda col: self._toggle_select_all(
                table, btn_select_all, val_id=val_id, combo_actions=combo_actions, btn_update_selected=btn_update_selected
            ) if col == 0 else None
        )
        btn_select_all.clicked.connect(
            lambda: self._toggle_select_all(
                table, btn_select_all, val_id=val_id, combo_actions=combo_actions, btn_update_selected=btn_update_selected
            )
        )
        edit_filter.textChanged.connect(
            lambda text: self._filter_feature_table(table, text)
        )

        layout.addWidget(table, stretch=1)

        # Keep table anchored at Column 0 so row checkboxes and primary IDs are immediately visible
        if hasattr(table, "horizontalScrollBar") and table.horizontalScrollBar():
            QTimer.singleShot(50, lambda: table.horizontalScrollBar().setValue(0) if is_valid_qobject(self) and is_valid_qobject(table) else None)

        return tab

    # -----------------------------------------------------------------------
    # Process: Table In-Place Cell Editing & Feature Lookup
    # -----------------------------------------------------------------------
    def _on_table_item_changed(
        self,
        val_id: str,
        layer: QgsVectorLayer,
        table: QTableWidget,
        item: QTableWidgetItem,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
    ):
        """Handle checkbox toggles and direct cell value editing."""
        if hasattr(table, "property") and table.property("is_populating"):
            return

        col = item.column()
        row = item.row()

        # Case 1: Checkbox toggled in Column 0
        if col == 0:
            checked_count = sum(
                1 for r in range(table.rowCount())
                if table.item(r, 0) and table.item(r, 0).checkState() == Qt.Checked
            )
            if combo_actions:
                combo_actions.setItemText(0, "Actions")
            elif btn_actions:
                btn_actions.setText("Actions ▾")
            if btn_update_selected:
                btn_update_selected.setText(f"Apply Fix Action ({checked_count})" if checked_count > 0 else "Apply Fix Action")
                btn_update_selected.setEnabled(checked_count > 0 or bool(combo_actions and combo_actions.currentIndex() == 4))
            return

        # Case 2: Action column
        if col >= table.columnCount() - 1:
            return

        # Case 3: Data attribute cell edited in-place
        field_name = item.data(Qt.UserRole + 2)
        if not field_name:
            h_it = table.horizontalHeaderItem(col)
            field_name = h_it.text().strip() if h_it else ""
            if field_name:
                item.setData(Qt.UserRole + 2, field_name)

        if not field_name:
            return

        fn_lower = str(field_name).strip().lower()
        if fn_lower in ("fid", "sf_fid", "df_fid", "ref_fid", "x_geometry", "y_geometry", "distance_m", "action", "") or fn_lower.startswith("ref_"):
            return

        chk_item = table.item(row, 0)
        target_fid = item.data(Qt.UserRole) if item.data(Qt.UserRole) is not None else (chk_item.data(Qt.UserRole) if chk_item else None)
        orig_map_uuid = item.data(Qt.UserRole + 1) or (chk_item.data(Qt.UserRole + 1) if chk_item else None)
        err_fid = item.data(Qt.UserRole + 3) if item.data(Qt.UserRole + 3) is not None else (chk_item.data(Qt.UserRole + 3) if chk_item else None)
        df_fid = item.data(Qt.UserRole + 4) if item.data(Qt.UserRole + 4) is not None else (chk_item.data(Qt.UserRole + 4) if chk_item else None)
        orig_df_uuid = item.data(Qt.UserRole + 5) or (chk_item.data(Qt.UserRole + 5) if chk_item else None)
        sf_fid = item.data(Qt.UserRole + 6) or (chk_item.data(Qt.UserRole + 6) if chk_item else None) or target_fid
        orig_sf_uuid = item.data(Qt.UserRole + 7) or (chk_item.data(Qt.UserRole + 7) if chk_item else None) or orig_map_uuid

        new_val_str = item.text().strip()
        is_del_field = fn_lower in ("is_deleted", "sf_is_deleted")

        # Handle boolean is_deleted editing: parse any input gracefully
        if is_del_field:
            raw_clean = new_val_str.lower()
            is_del = raw_clean in ("true", "1", "t", "yes", "y", "deleted")
            normalized_str = "true" if is_del else "false"
            bool_to_save = is_del

            # Normalize the text in the cell if user typed something else (e.g. "yes", "T", "random text")
            if item.text() != normalized_str:
                table.setProperty("is_populating", True)
                try:
                    item.setText(normalized_str)
                finally:
                    table.setProperty("is_populating", False)

            # Style the cell based on deletion state
            self._style_table_cell(item, "deleted" if is_del else "normal")

            # Update row action button if present
            act_w = table.cellWidget(row, table.columnCount() - 1)
            if act_w:
                for child in act_w.findChildren(QPushButton):
                    if child.text() in ("Delete", "Deleted"):
                        child.setText("Deleted" if is_del else "Delete")
                        self._style_row_delete_button(child, is_deleted=is_del)

            # 1. Update in results memory layer
            if layer and layer.isValid():
                f_idx = layer.fields().indexOf(field_name)
                if f_idx != -1:
                    if not layer.isEditable():
                        layer.startEditing()
                    f_type = layer.fields().at(f_idx).type()
                    val_to_set_layer = bool_to_save if f_type == QVariant.Bool else normalized_str
                    layer.changeAttributeValue(err_fid if err_fid is not None else target_fid, f_idx, val_to_set_layer)

            # 2. Update main building points layer
            main_layer = self._get_or_load_main_building_layer()
            if main_layer and main_layer.isValid():
                main_feat = self._find_main_feature(main_layer, fid=sf_fid, map_uuid=orig_sf_uuid or orig_map_uuid)
                if main_feat:
                    target_m_name = (
                        field_name[3:]
                        if (field_name.startswith("sf_") and field_name not in [f.name() for f in main_layer.fields()])
                        else field_name
                    )
                    m_idx = main_layer.fields().indexOf(target_m_name)
                    if m_idx != -1:
                        if not main_layer.isEditable():
                            main_layer.startEditing()
                        m_type = main_layer.fields().at(m_idx).type()
                        val_to_set_main = bool_to_save if m_type == QVariant.Bool else normalized_str
                        main_layer.changeAttributeValue(main_feat.id(), m_idx, val_to_set_main)

            self.lbl_footer_status.setText(
                f"Set '{field_name}' = '{normalized_str}' ({'deleted' if is_del else 'active'}) for feature FID #{sf_fid} (Press Ctrl+S to save)"
            )
            return

        # 1. Update in results memory layer
        if layer and layer.isValid():
            f_idx = layer.fields().indexOf(field_name)
            if f_idx != -1:
                if not layer.isEditable():
                    layer.startEditing()
                layer.changeAttributeValue(err_fid if err_fid is not None else target_fid, f_idx, new_val_str)

        # Check if this column is a UUID/mapid column
        UUID_FIELD_NAMES = ("map_uuid", "mapid", "sf_map_uuid", "df_map_uuid", "df_mapid", "sf_mapid", "uuid")
        is_uuid_edit = fn_lower in UUID_FIELD_NAMES

        applied_to_form2 = False
        applied_to_main = False

        # 2. Update Form 2 layer and buffer for disk save if it's a df_ column OR a uuid edit
        if fn_lower.startswith("df_") or is_uuid_edit:
            clean_prop = field_name[3:] if fn_lower.startswith("df_") else field_name
            form2_layer = self._get_or_load_form2_layer()
            if form2_layer and form2_layer.isValid():
                form2_feat = self._find_form2_feature(
                    form2_layer, fid=df_fid, map_uuid=orig_df_uuid or orig_map_uuid
                )
                if form2_feat:
                    target_f_name = None
                    if is_uuid_edit:
                        for cand in ("mapid", "df_mapid", "map_uuid", "df_map_uuid", "uuid"):
                            idx = form2_layer.fields().lookupField(cand)
                            if idx != -1:
                                target_f_name = form2_layer.fields().at(idx).name()
                                break
                    if not target_f_name:
                        for cand in (clean_prop, field_name, f"df_{clean_prop}"):
                            idx = form2_layer.fields().lookupField(cand)
                            if idx != -1:
                                target_f_name = form2_layer.fields().at(idx).name()
                                break
                    if target_f_name:
                        f_idx = form2_layer.fields().indexOf(target_f_name)
                        if f_idx != -1:
                            if not form2_layer.isEditable():
                                form2_layer.startEditing()
                            form2_layer.changeAttributeValue(form2_feat.id(), f_idx, new_val_str)
                            applied_to_form2 = True

            # Always anchor pending edits by original disk uuid/fid so disk save matches record correctly
            disk_uuid = orig_df_uuid or orig_map_uuid
            rec_k = f"fid_{df_fid}" if df_fid is not None else f"uuid_{disk_uuid}"
            if rec_k not in self._pending_json_edits:
                self._pending_json_edits[rec_k] = {
                    "df_fid": df_fid,
                    "uuid": disk_uuid,
                    "props": {},
                }
            if is_uuid_edit:
                # Store under all common key aliases so both CSV (mapid) and GeoJSON/JSON (map_uuid) match
                self._pending_json_edits[rec_k]["props"]["map_uuid"] = new_val_str
                self._pending_json_edits[rec_k]["props"]["mapid"] = new_val_str
                self._pending_json_edits[rec_k]["props"]["df_map_uuid"] = new_val_str
                self._pending_json_edits[rec_k]["props"]["df_mapid"] = new_val_str
            else:
                self._pending_json_edits[rec_k]["props"][clean_prop] = new_val_str

            if is_uuid_edit or fn_lower in ("df_map_uuid", "df_mapid"):
                item.setData(Qt.UserRole + 5, new_val_str)
                if chk_item:
                    chk_item.setData(Qt.UserRole + 5, new_val_str)

            if not is_uuid_edit:
                self.lbl_footer_status.setText(f"Updated '{clean_prop}' = '{new_val_str}' for Form 2 record (Press Ctrl+S to save)")

        # 3. Update main building points layer in memory if it's an sf_ / unprefixed column OR a uuid edit
        if (not fn_lower.startswith("df_")) or is_uuid_edit:
            main_layer = self._get_or_load_main_building_layer()
            if main_layer and main_layer.isValid():
                main_feat = self._find_main_feature(
                    main_layer,
                    fid=sf_fid,
                    map_uuid=orig_sf_uuid or orig_map_uuid or orig_df_uuid,
                    is_editing_uuid=is_uuid_edit,
                )
                if main_feat:
                    target_m_name = None
                    if is_uuid_edit:
                        for cand in ("map_uuid", "sf_map_uuid", "mapid", "uuid"):
                            idx = main_layer.fields().lookupField(cand)
                            if idx != -1:
                                target_m_name = main_layer.fields().at(idx).name()
                                break
                    if not target_m_name:
                        for cand in (field_name[3:] if field_name.startswith("sf_") else field_name, field_name):
                            idx = main_layer.fields().lookupField(cand)
                            if idx != -1:
                                target_m_name = main_layer.fields().at(idx).name()
                                break
                    if target_m_name:
                        m_idx = main_layer.fields().indexOf(target_m_name)
                        if m_idx != -1:
                            if not main_layer.isEditable():
                                main_layer.startEditing()
                            field_type = main_layer.fields().at(m_idx).type()
                            if field_type == QVariant.Bool:
                                val_to_set = new_val_str.strip().lower() in ("true", "1", "t", "yes", "deleted")
                            else:
                                val_to_set = new_val_str
                            main_layer.changeAttributeValue(main_feat.id(), m_idx, val_to_set)
                            applied_to_main = True

            if is_uuid_edit:
                item.setData(Qt.UserRole + 7, new_val_str)
                item.setData(Qt.UserRole + 1, new_val_str)
                if chk_item:
                    chk_item.setData(Qt.UserRole + 7, new_val_str)
                    chk_item.setData(Qt.UserRole + 1, new_val_str)

            if is_uuid_edit:
                status_targets = []
                if applied_to_main:
                    status_targets.append("Building Points")
                if applied_to_form2 or self._pending_json_edits:
                    status_targets.append("Form 2 Data")
                target_desc = " & ".join(status_targets) if status_targets else "layer(s)"
                self.lbl_footer_status.setText(f"Updated UUID/mapid = '{new_val_str}' for {target_desc} (Press Ctrl+S to save)")
            elif applied_to_main:
                self.lbl_footer_status.setText(f"Updated '{field_name}' = '{new_val_str}' for feature FID #{sf_fid} (Press Ctrl+S to save)")
            else:
                self._log_warning(f"Could not locate feature in main building layer for '{field_name}' = '{new_val_str}' (FID: {sf_fid}, UUID: {orig_sf_uuid}).")
                self.lbl_footer_status.setText(f"Updated '{field_name}' in table, but feature not found in building layer (Press Ctrl+S to save)")

        # Update cell styling for other fields
        if fn_lower in ("status", "sf_status"):
            is_del = (new_val_str.lower() == "deleted")
            self._style_table_cell(item, "deleted" if is_del else "modified")
            act_w = table.cellWidget(row, table.columnCount() - 1)
            if act_w:
                for child in act_w.findChildren(QPushButton):
                    if child.text() in ("Delete", "Deleted"):
                        child.setText("Deleted" if is_del else "Delete")
                        self._style_row_delete_button(child, is_deleted=is_del)
        else:
            # Subtle highlight to show cell was manually modified
            self._style_table_cell(item, "modified")

    def _find_main_feature(
        self,
        main_layer: QgsVectorLayer,
        fid: Any = None,
        map_uuid: Optional[str] = None,
        is_editing_uuid: bool = False,
    ) -> Optional[QgsFeature]:
        """
        Locate a feature in main_layer prioritizing fid, then fallback to map_uuid.
        Guarantees correct feature resolution even if duplicate map_uuids exist.
        """
        if not main_layer or not main_layer.isValid():
            return None

        # Clean fid to avoid checking string 'NULL' or None
        clean_fid = None
        if fid is not None and fid != NULL:
            s = str(fid).strip()
            if s and s.lower() not in ("null", "none"):
                clean_fid = int(s) if s.isdigit() else fid

        m_flds = {f.name().lower(): f.name() for f in main_layer.fields()}
        u_col = m_flds.get("map_uuid") or m_flds.get("sf_map_uuid") or m_flds.get("mapid") or m_flds.get("uuid")

        # 1. Primary: Locate by native QGIS internal feature ID ($id)
        if clean_fid is not None:
            try:
                feat = main_layer.getFeature(int(clean_fid))
                if feat.isValid():
                    clean_u = str(map_uuid).strip() if map_uuid else ""
                    if not clean_u or not u_col:
                        return feat
                    feat_u = str(feat[u_col] or "").strip()
                    if feat_u == clean_u:
                        return feat
            except Exception:
                pass

        # 2. Fallback: Locate by map_uuid / mapid across all alias columns
        if map_uuid:
            clean_uuid = str(map_uuid).strip().replace("'", "''")
            if clean_uuid and clean_uuid.lower() not in ("null", "none"):
                for cand_col in ("map_uuid", "sf_map_uuid", "mapid", "sf_mapid", "uuid"):
                    if cand_col in m_flds:
                        real_col = m_flds[cand_col]
                        try:
                            for f in main_layer.getFeatures(QgsFeatureRequest().setFilterExpression(f'"{real_col}" = \'{clean_uuid}\'')):
                                return f
                        except Exception:
                            pass

        # 3. Fallback: Locate by fid attribute if 'fid' field exists in main_layer
        if clean_fid is not None and "fid" in m_flds:
            try:
                fid_attr = m_flds["fid"]
                if isinstance(clean_fid, int):
                    expr = f'"{fid_attr}" = {clean_fid}'
                else:
                    expr = f'"{fid_attr}" = \'{str(clean_fid).replace(chr(39), chr(39)+chr(39))}\''
                for f in main_layer.getFeatures(QgsFeatureRequest().setFilterExpression(expr)):
                    return f
            except Exception:
                pass

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

        # 3. Fallback: Locate by map_uuid or mapid
        if map_uuid:
            clean_uuid = str(map_uuid).strip().replace("'", "''")
            for uuid_col in ("mapid", "df_mapid", "map_uuid", "df_map_uuid", "uuid"):
                if uuid_col in f_names_lower:
                    try:
                        for f in form2_layer.getFeatures(QgsFeatureRequest().setFilterExpression(f'"{uuid_col}" = \'{clean_uuid}\'')):
                            return f
                    except Exception:
                        pass

        return None

    # -----------------------------------------------------------------------
    # Process: Table Selection & Batch Toolbar Actions
    # -----------------------------------------------------------------------
    def _toggle_select_all(
        self,
        table: QTableWidget,
        btn_select_all: QPushButton,
        val_id: Optional[str] = None,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
    ):
        """Toggle checking/unchecking all visible rows in the table."""
        if not is_valid_qobject(self) or not is_valid_qobject(table):
            return
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
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions ▾")
        if btn_update_selected:
            btn_update_selected.setText(f"Apply Fix Action ({checked_count})" if checked_count > 0 else "Apply Fix Action")
            btn_update_selected.setEnabled(checked_count > 0)
        btn_select_all.setText("Select None" if target_state == Qt.Checked else "Select All")
        toggle_ic = QgsApplication.getThemeIcon(
            "mActionDeselectAll.svg" if target_state == Qt.Checked else "mActionSelectAll.svg"
        )
        if not toggle_ic.isNull():
            btn_select_all.setIcon(toggle_ic)

    def _delete_selected_features(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        **kwargs,
    ):
        """Directly mark checked features as 'deleted' regardless of validation check or file."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        if not is_valid_qobject(table):
            return

        from .cbms_mv_fix import cbms_mv_fix
        cbms_mv_fix.delete_selected_features(
            self,
            layer,
            table,
            combo_actions=combo_actions,
            btn_actions=btn_actions,
            btn_update_selected=btn_update_selected,
        )

    def _on_concatenate_ea_geocode(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        **kwargs,
    ):
        """Directly concatenate EA geocode on checked features regardless of validation check or file."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        self._fix_selected_features("concatenate_ea_geocode", layer, table)
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions ▾")
        if btn_update_selected:
            btn_update_selected.setText("Apply Fix Action")
            btn_update_selected.setEnabled(False)

    def _on_concatenate_bsn_geoid(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        **kwargs,
    ):
        """Directly concatenate BSN GEOID on checked features regardless of validation check or file."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        self._fix_selected_features("concatenate_bsn_geoid", layer, table)
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions ▾")
        if btn_update_selected:
            btn_update_selected.setText("Apply Fix Action")
            btn_update_selected.setEnabled(False)

    def _on_copy_geometry_to_coordinates(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        **kwargs,
    ):
        """Directly copy point geometry to coordinates on checked features regardless of validation check or file."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        self._fix_selected_features("copy_geometry_to_coordinates", layer, table)
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions ▾")
        if btn_update_selected:
            btn_update_selected.setText("Apply Fix Action")
            btn_update_selected.setEnabled(False)

    def _on_update_datafile_coordinates(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        **kwargs,
    ):
        """Directly update datafile coordinates (df_longitude, df_latitude) based on sf_longitude and sf_latitude."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        self._fix_selected_features("update_datafiles_coordinates", layer, table)
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions ▾")
        if btn_update_selected:
            btn_update_selected.setText("Apply Fix Action")
            btn_update_selected.setEnabled(False)

    def _on_generate_point_geometry(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        **kwargs,
    ):
        """Directly generate point geometry for checked features regardless of validation check or file."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        self._fix_selected_features("generate_point_geometry", layer, table)
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions ▾")
        if btn_update_selected:
            btn_update_selected.setText("Apply Fix Action")
            btn_update_selected.setEnabled(False)

    def _on_update_point_geometry(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        **kwargs,
    ):
        """Directly update point geometry using sf_longitude and sf_latitude for selected/checked features."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        self._fix_selected_features("update_point_geometry", layer, table)
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions")
        if btn_update_selected:
            btn_update_selected.setText("Apply Fix Action")
            btn_update_selected.setEnabled(False)

    def _on_deduplicate_features(
        self,
        *args,
        combo_actions: Optional[QComboBox] = None,
        btn_actions: Optional[Any] = None,
        btn_update_selected: Optional[QPushButton] = None,
        process_all: bool = False,
        **kwargs,
    ):
        """Directly deduplicate features regardless of validation check or file."""
        if not is_valid_qobject(self):
            return
        if len(args) >= 2 and hasattr(args[1], "rowCount"):
            layer, table = args[0], args[1]
        elif len(args) >= 3 and hasattr(args[2], "rowCount"):
            layer, table = args[1], args[2]
        else:
            layer = kwargs.get("layer")
            table = kwargs.get("table")

        if not is_valid_qobject(table):
            return

        from .cbms_mv_fix.deduplicate_features_fix import deduplicate_features
        deduplicate_features(
            self,
            layer,
            table,
            combo_actions=combo_actions,
            btn_actions=btn_actions,
            btn_update_selected=btn_update_selected,
            process_all=process_all,
        )
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        elif btn_actions:
            btn_actions.setText("Actions ▾")
        if btn_update_selected:
            btn_update_selected.setText("Apply Fix Action")
            btn_update_selected.setEnabled(False)

    def _fix_selected_features(self, val_id: str, layer: QgsVectorLayer, table: QTableWidget):
        """Batch execute fix for all checked rows in the table, deduplicated by unique (fid + map_uuid)."""
        if not is_valid_qobject(self):
            return
        target_fids = []
        target_uuids = []
        target_rows = []
        target_keys = set()
        seen_keys = set()
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if item0 and item0.checkState() == Qt.Checked:
                s_id = item0.data(Qt.UserRole)
                u = item0.data(Qt.UserRole + 1)
                e_id = item0.data(Qt.UserRole + 3)
                df_f = item0.data(Qt.UserRole + 4)
                df_u = item0.data(Qt.UserRole + 5)
                sf_f = item0.data(Qt.UserRole + 6)
                sf_u = item0.data(Qt.UserRole + 7)
                # Prioritize primary layer FID (sf_f or s_id) over memory layer err_fid
                best_fid = sf_f if (sf_f is not None and str(sf_f).strip() not in ("", "NULL", "None")) else s_id
                if not best_fid or str(best_fid).strip() in ("", "NULL", "None"):
                    best_fid = df_f or e_id

                best_uuid = sf_u or u or df_u
                if best_uuid and str(best_uuid).strip() in ("", "NULL", "None"):
                    best_uuid = ""

                ukey = make_unique_feature_key(best_fid, best_uuid)
                if ukey:
                    target_keys.add(ukey)
                    target_keys.add(ukey.lower())

                target_rows.append(r)
                target_fids.append(best_fid if (best_fid is not None and str(best_fid).strip() not in ("", "NULL", "None")) else None)
                target_uuids.append(str(best_uuid).strip() if (best_uuid and str(best_uuid).strip() not in ("", "NULL", "None")) else "")

        if not target_fids and not target_uuids and not target_rows:
            # Fallback: if no checkboxes are ticked, check if rows are highlighted / selected via selectionModel
            if hasattr(table, "selectionModel") and table.selectionModel():
                sel_rows = sorted(set(idx.row() for idx in table.selectionModel().selectedRows()))
                for r in sel_rows:
                    item0 = table.item(r, 0)
                    if item0:
                        s_id = item0.data(Qt.UserRole)
                        u = item0.data(Qt.UserRole + 1)
                        e_id = item0.data(Qt.UserRole + 3)
                        df_f = item0.data(Qt.UserRole + 4)
                        df_u = item0.data(Qt.UserRole + 5)
                        sf_f = item0.data(Qt.UserRole + 6)
                        sf_u = item0.data(Qt.UserRole + 7)
                        best_fid = sf_f if (sf_f is not None and str(sf_f).strip() not in ("", "NULL", "None")) else s_id
                        if not best_fid or str(best_fid).strip() in ("", "NULL", "None"):
                            best_fid = df_f or e_id

                        best_uuid = sf_u or u or df_u
                        if best_uuid and str(best_uuid).strip() in ("", "NULL", "None"):
                            best_uuid = ""

                        ukey = make_unique_feature_key(best_fid, best_uuid)
                        if ukey:
                            target_keys.add(ukey)
                            target_keys.add(ukey.lower())

                        target_rows.append(r)
                        target_fids.append(best_fid if (best_fid is not None and str(best_fid).strip() not in ("", "NULL", "None")) else None)
                        target_uuids.append(str(best_uuid).strip() if (best_uuid and str(best_uuid).strip() not in ("", "NULL", "None")) else "")

        if not target_fids and not target_uuids and not target_rows:
            QMessageBox.information(self, "Nothing Selected", "Please tick the checkbox or select at least one row first.")
            return

        self._execute_fix(
            val_id,
            layer,
            table,
            target_fids=target_fids,
            target_uuids=target_uuids,
            target_rows=target_rows,
            target_keys=target_keys,
        )

    def _execute_fix(
        self,
        val_id: str,
        layer: QgsVectorLayer,
        table: QTableWidget,
        target_fids: Optional[List[Any]] = None,
        target_uuids: Optional[List[str]] = None,
        target_rows: Optional[List[int]] = None,
        target_keys: Optional[Any] = None,
    ):
        """Execute automated fix for one or more features using registered fix handler."""
        if not is_valid_qobject(self):
            return
        handler = get_fix_handler(val_id)
        if not handler:
            QMessageBox.warning(
                self,
                "No Automatic Fix",
                f"There is no automatic fix for this check ('{val_id}'). Please edit the values directly in the table.",
            )
            return

        main_layer = self._get_or_load_main_building_layer() if hasattr(self, "_get_or_load_main_building_layer") else None
        active_target_layer = main_layer if (main_layer and main_layer.isValid()) else layer
        if not active_target_layer or not active_target_layer.isValid():
            QMessageBox.critical(
                self,
                "Map Layer Missing",
                "The fix cannot run because the building points layer is not loaded.",
            )
            return

        if active_target_layer and active_target_layer.isValid() and not active_target_layer.isEditable():
            try:
                active_target_layer.startEditing()
            except Exception:
                pass
        if layer and layer.isValid() and layer != active_target_layer and not layer.isEditable():
            try:
                layer.startEditing()
            except Exception:
                pass

        try:
            feedback = QgsProcessingFeedback()
            try:
                res = handler(
                    active_target_layer,
                    target_fids=target_fids,
                    target_uuids=target_uuids,
                    feedback=feedback,
                    error_layer=layer,
                    table=table,
                    dialog=self,
                    target_rows=target_rows,
                    target_keys=target_keys,
                )
            except TypeError as te:
                te_msg = str(te).lower()
                if "keyword argument" in te_msg or "positional argument" in te_msg or "takes" in te_msg:
                    res = handler(active_target_layer, target_uuids or target_fids, feedback=feedback)
                else:
                    raise te

        except Exception as exc:
            import traceback
            err_details = traceback.format_exc()
            try:
                from qgis.core import Qgis, QgsMessageLog
                QgsMessageLog.logMessage(f"Fix execution error for '{val_id}':\n{err_details}", "CBMS MV", Qgis.Critical)
            except Exception:
                pass
            QMessageBox.critical(
                self,
                "Fix Failed",
                f"Something went wrong while applying the fix for '{val_id}':\n{exc}",
            )
            return

        if not res.get("success"):
            QMessageBox.warning(
                self,
                "Fix Not Applied",
                res.get("message", "The fix could not be applied."),
            )
            return

        updated_values = res.get("updated_values", {})
        fixed_count = res.get("fixed_count", len(updated_values))

        target_rows_set = set(target_rows) if target_rows is not None else None
        # Synchronize table cells and layer across all rows matching unique features
        table.setProperty("is_populating", True)
        try:
            if not layer.isEditable():
                layer.startEditing()

            # Check rows in table: if target_rows is provided, only process targeted rows
            for r in range(table.rowCount()):
                if target_rows_set is not None and r not in target_rows_set:
                    continue
                item0 = table.item(r, 0)
                if not item0:
                    continue
                r_fid = item0.data(Qt.UserRole)
                r_uuid = str(item0.data(Qt.UserRole + 1)).strip() if item0.data(Qt.UserRole + 1) else ""
                r_err_fid = item0.data(Qt.UserRole + 3)
                r_df_fid = item0.data(Qt.UserRole + 4)
                r_df_uuid = str(item0.data(Qt.UserRole + 5) or "").strip()
                r_sf_fid = item0.data(Qt.UserRole + 6)
                r_sf_uuid = str(item0.data(Qt.UserRole + 7) or "").strip()

                best_rfid = r_sf_fid if (r_sf_fid is not None and str(r_sf_fid).strip() not in ("", "NULL", "None")) else r_fid
                if not best_rfid or str(best_rfid).strip() in ("", "NULL", "None"):
                    best_rfid = r_df_fid or r_err_fid
                best_ruuid = r_sf_uuid or r_uuid or r_df_uuid

                # Check unique key match
                row_ukey = make_unique_feature_key(best_rfid, best_ruuid)
                alt_ukey = make_unique_feature_key(r_fid, r_uuid)

                # Collect all candidate keys for matching updated_values
                col_updates = None
                fid_candidates = []
                for k in (row_ukey, row_ukey.lower() if row_ukey else None, alt_ukey, alt_ukey.lower() if alt_ukey else None):
                    if k:
                        fid_candidates.append(k)

                # Table row namespaced key
                fid_candidates.append(f"row_{r}")

                # UUID candidate matches
                for u_cand in (best_ruuid, r_uuid, r_df_uuid, r_sf_uuid):
                    if u_cand and str(u_cand).strip().lower() not in ("", "null", "none"):
                        fid_candidates.extend([str(u_cand).strip(), str(u_cand).strip().lower()])

                # Feature ID candidates (role_off in 0, 3, 4, 6)
                for role_off in (0, 3, 4, 6):
                    v = item0.data(Qt.UserRole + role_off)
                    if v is not None and str(v).strip().lower() not in ("", "null", "none"):
                        fid_candidates.extend([v, f"fid_{v}"])

                for cand in fid_candidates:
                    try:
                        if cand in updated_values:
                            col_updates = updated_values[cand]
                            break
                    except TypeError:
                        pass

                if col_updates:
                    for c in range(1, table.columnCount() - 1):
                        c_item = table.item(r, c)
                        if c_item:
                            fname = c_item.data(Qt.UserRole + 2)
                            if fname in col_updates:
                                new_text = str(col_updates[fname])
                                c_item.setText(new_text)
                                # Highlight fixed cell in green
                                self._style_table_cell(c_item, "fixed")
                                # Also update result layer
                                f_idx = layer.fields().indexOf(fname)
                                if f_idx != -1:
                                    layer.changeAttributeValue(r_err_fid if r_err_fid is not None else r_fid, f_idx, new_text)
                                # If fname is df_* or uuid/mapid, buffer into pending JSON edits
                                fname_l = fname.lower()
                                is_fix_uuid = fname_l in ("map_uuid", "mapid", "sf_map_uuid", "df_map_uuid", "df_mapid", "uuid")
                                if fname_l.startswith("df_") or is_fix_uuid:
                                    r_df_fid = c_item.data(Qt.UserRole + 4)
                                    r_df_uuid = c_item.data(Qt.UserRole + 5)
                                    rec_k = f"fid_{r_df_fid}" if r_df_fid is not None else f"uuid_{r_df_uuid or r_uuid}"
                                    if rec_k not in self._pending_json_edits:
                                        self._pending_json_edits[rec_k] = {
                                            "df_fid": r_df_fid,
                                            "uuid": r_df_uuid or r_uuid,
                                            "props": {},
                                        }
                                    if is_fix_uuid:
                                        self._pending_json_edits[rec_k]["props"]["map_uuid"] = new_text
                                        self._pending_json_edits[rec_k]["props"]["mapid"] = new_text
                                        self._pending_json_edits[rec_k]["props"]["df_map_uuid"] = new_text
                                        self._pending_json_edits[rec_k]["props"]["df_mapid"] = new_text
                                    else:
                                        self._pending_json_edits[rec_k]["props"][fname[3:] if fname_l.startswith("df_") else fname] = new_text

                    # Always ensure col_updates for df_* and map_uuid/bsn_geoid/ea_geocode are buffered for CSV persistence
                    r_df_fid_buf = item0.data(Qt.UserRole + 4) or item0.data(Qt.UserRole + 2)
                    r_df_uuid_buf = str(item0.data(Qt.UserRole + 5) or r_uuid or "").strip()
                    rec_k_buf = f"fid_{r_df_fid_buf}" if r_df_fid_buf is not None else f"uuid_{r_df_uuid_buf}"
                    if r_df_fid_buf is not None or r_df_uuid_buf:
                        buf_props: Dict[str, str] = {}
                        for col_k, col_v in col_updates.items():
                            col_kl = str(col_k).lower()
                            if col_kl in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid"):
                                buf_props["map_uuid"] = str(col_v)
                                buf_props["mapid"] = str(col_v)
                                buf_props["df_map_uuid"] = str(col_v)
                                buf_props["df_mapid"] = str(col_v)
                            elif col_kl in ("bsn_geoid", "df_bsn_geoid"):
                                buf_props["bsn_geoid"] = str(col_v)
                                buf_props["df_bsn_geoid"] = str(col_v)
                            elif col_kl in ("ea_geocode", "df_ea_geocode"):
                                buf_props["ea_geocode"] = str(col_v)
                                buf_props["df_ea_geocode"] = str(col_v)
                            elif col_kl in ("bsn", "df_bsn", "bsn_code", "df_bsn_code"):
                                buf_props["bsn"] = str(col_v)
                                buf_props["df_bsn"] = str(col_v)
                                buf_props["bsn_code"] = str(col_v)
                                buf_props["df_bsn_code"] = str(col_v)
                            elif col_kl in ("region_code", "df_region_code", "reg_code", "df_reg_code"):
                                buf_props["region_code"] = str(col_v)
                                buf_props["df_region_code"] = str(col_v)
                            elif col_kl in ("province_code", "df_province_code"):
                                buf_props["province_code"] = str(col_v)
                                buf_props["df_province_code"] = str(col_v)
                            elif col_kl in ("city_mun_code", "df_city_mun_code"):
                                buf_props["city_mun_code"] = str(col_v)
                                buf_props["df_city_mun_code"] = str(col_v)
                            elif col_kl in ("barangay_code", "df_barangay_code", "barangay__code", "df_barangay__code"):
                                buf_props["barangay_code"] = str(col_v)
                                buf_props["df_barangay_code"] = str(col_v)
                                buf_props["barangay__code"] = str(col_v)
                                buf_props["df_barangay__code"] = str(col_v)
                            elif col_kl in ("ean", "df_ean"):
                                buf_props["ean"] = str(col_v)
                                buf_props["df_ean"] = str(col_v)
                            elif col_kl.startswith("df_"):
                                buf_props[col_k[3:]] = str(col_v)
                                buf_props[col_k] = str(col_v)
                        if buf_props:
                            if rec_k_buf not in self._pending_json_edits:
                                self._pending_json_edits[rec_k_buf] = {
                                    "df_fid": r_df_fid_buf,
                                    "uuid": r_df_uuid_buf,
                                    "props": {},
                                }
                            self._pending_json_edits[rec_k_buf]["props"].update(buf_props)

                    # Uncheck row after successful fix
                    item0.setCheckState(Qt.Unchecked)

                    # Update the row's Fix button to show Fixed
                    action_cell = table.cellWidget(r, table.columnCount() - 1)
                    if action_cell:
                        for btn in action_cell.findChildren(QPushButton):
                            if btn.text() == "Fix":
                                btn.setText("Fixed")
                                btn.setEnabled(False)
                                self._style_row_fix_button(btn, enabled=False, fixed=True)
        finally:
            table.setProperty("is_populating", False)

        # Refresh map canvas if available
        if self.iface:
            self.iface.mapCanvas().refresh()

        if fixed_count == 0:
            self.lbl_footer_status.setText(f"No records were fixed for '{val_id}'.")
            QMessageBox.warning(
                self,
                "Fix Not Applied",
                res.get(
                    "message",
                    f"No records were fixed for '{val_id}'.\n\n"
                    "Please check that the selected row has valid coordinates and is not already on the map.",
                ),
            )
            return

        self.lbl_footer_status.setText(f"Fixed {fixed_count} record(s) for '{val_id}'. Click 'Save Changes' (Ctrl+S) to keep them.")
        QMessageBox.information(
            self,
            "Fix Applied",
            f"Fixed {fixed_count} record(s) for:\n{val_id}\n\n"
            f"These changes are not saved yet.\n"
            f"Click 'Save Changes' (or press Ctrl+S) to keep them.",
        )

    # -----------------------------------------------------------------------
    # Process: Soft Delete & Status Synchronization (Delegated to cbms_mv_fix)
    # -----------------------------------------------------------------------
    def _mark_feature_deleted(
        self,
        val_id: str,
        layer: QgsVectorLayer,
        table: QTableWidget,
        source_fid: Any = None,
        map_uuid: Optional[str] = None,
        err_fid: Any = None,
        button: Optional[QPushButton] = None,
        prompt_confirm: bool = True,
        target_status: Optional[str] = None,
    ):
        """Mark a single feature as 'deleted' via cbms_mv_fix."""
        if not is_valid_qobject(self) or not is_valid_qobject(table):
            return
        from .cbms_mv_fix import cbms_mv_fix
        cbms_mv_fix.mark_feature_deleted(
            self,
            val_id,
            layer,
            table,
            source_fid=source_fid,
            map_uuid=map_uuid,
            err_fid=err_fid,
            button=button,
            prompt_confirm=prompt_confirm,
            target_status=target_status,
        )

    def _sync_feature_status(
        self,
        val_id: str,
        source_fid: Any = None,
        map_uuid: Optional[str] = None,
        new_status: str = "deleted",
    ):
        """Synchronize a status update into table via cbms_mv_fix."""
        from .cbms_mv_fix import cbms_mv_fix
        cbms_mv_fix.sync_feature_status(
            self,
            val_id,
            source_fid=source_fid,
            map_uuid=map_uuid,
            new_status=new_status,
        )

    # -----------------------------------------------------------------------
    # Process: Data Persistence, Save & Discard Confirmation
    # -----------------------------------------------------------------------
    def _on_shortcut_save(self):
        """Handle Ctrl+S shortcut, strictly scoped to this dialog window and its child controls."""
        if not self.isActiveWindow():
            return
        self._prompt_save_confirmation()

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
        for target in ("mapid", "df_mapid", "map_uuid", "df_map_uuid", "uuid", "df_uuid"):
            if target in header_lower:
                uuid_idx = header_lower.index(target)
                break

        # Locate or append updated_columns column
        updated_var_idx = header_lower.index("updated_columns") if "updated_columns" in header_lower else None
        if updated_var_idx is None:
            header.append("updated_columns")
            header_lower.append("updated_columns")
            updated_var_idx = len(header) - 1
            for r in rows:
                r.append("")

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

                changed_cols_for_row = []
                for prop_name, new_val in props.items():
                    clean_p = prop_name.lower()
                    clean_df_p = f"df_{clean_p}"
                    col_idx = None
                    for idx, h in enumerate(header_lower):
                        if h == clean_p or h == clean_df_p:
                            col_idx = idx
                            break
                        # Map map_uuid / mapid to CSV column headers
                        if clean_p in ("map_uuid", "mapid", "uuid", "df_map_uuid", "df_mapid"):
                            if h in ("mapid", "df_mapid", "map_uuid", "df_map_uuid", "uuid"):
                                col_idx = idx
                                break
                        # Map bsn_geoid / df_bsn_geoid to CSV column headers
                        if clean_p in ("bsn_geoid", "df_bsn_geoid"):
                            if h in ("bsn_geoid", "df_bsn_geoid"):
                                col_idx = idx
                                break
                        # Map ea_geocode / df_ea_geocode to CSV column headers
                        if clean_p in ("ea_geocode", "df_ea_geocode"):
                            if h in ("ea_geocode", "df_ea_geocode"):
                                col_idx = idx
                                break
                        # Map bsn / df_bsn / bsn_code to CSV column headers
                        if clean_p in ("bsn", "df_bsn", "bsn_code", "df_bsn_code"):
                            if h in ("bsn", "df_bsn", "bsn_code", "df_bsn_code"):
                                col_idx = idx
                                break
                        # Map region_code / df_region_code / reg_code to CSV column headers
                        if clean_p in ("region_code", "df_region_code", "reg_code", "df_reg_code"):
                            if h in ("region_code", "df_region_code", "reg_code", "df_reg_code"):
                                col_idx = idx
                                break

                    # If column does not exist in CSV header, append it dynamically
                    if col_idx is None:
                        if clean_p in ("bsn_geoid", "df_bsn_geoid"):
                            header.append("bsn_geoid")
                            header_lower.append("bsn_geoid")
                            col_idx = len(header) - 1
                            for r_item in rows:
                                r_item.append("")
                        elif clean_p in ("ea_geocode", "df_ea_geocode"):
                            header.append("ea_geocode")
                            header_lower.append("ea_geocode")
                            col_idx = len(header) - 1
                            for r_item in rows:
                                r_item.append("")

                    if col_idx is not None:
                        actual_col_name = header[col_idx]
                        row[col_idx] = str(new_val) if new_val is not None else ""
                        if actual_col_name.lower() != "updated_columns":
                            var_name = actual_col_name[3:] if actual_col_name.lower().startswith("df_") else actual_col_name
                            changed_cols_for_row.append(var_name)

                if changed_cols_for_row and updated_var_idx is not None:
                    existing_val = str(row[updated_var_idx]).strip() if updated_var_idx < len(row) else ""
                    existing_tokens = [t.strip() for t in existing_val.split("|") if t.strip()]
                    combined = list(dict.fromkeys(existing_tokens + changed_cols_for_row))
                    row[updated_var_idx] = "|".join(combined)

                updated_count += 1

        # Write back to Form 2 CSV file (atomic attempt with fallback for Windows file locks)
        tmp_file = form2_path + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
            try:
                os.replace(tmp_file, form2_path)
            except PermissionError:
                # On Windows, when QGIS holds an open OGR handle on the CSV layer,
                # os.replace fails with [WinError 5] Access is denied.
                # Direct overwrite succeeds because GDAL/OS permits shared write access.
                with open(form2_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(header)
                    writer.writerows(rows)
        except PermissionError as e:
            return False, 0, (
                f"Permission denied while saving Form 2 CSV to disk:\n{e}\n\n"
                "Tip: The file is currently open and locked by another program (e.g., Microsoft Excel).\n"
                "Please close Microsoft Excel (or the application viewing this CSV) and try saving again."
            )
        except Exception as e:
            return False, 0, f"Error saving Form 2 CSV to disk:\n{e}"
        finally:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass

        self._pending_json_edits.clear()

        # If a Form 2 table layer is loaded into QGIS canvas, refresh it
        if self.project:
            for lyr in self.project.mapLayers().values():
                if lyr.name().startswith("Form 2 (") or (hasattr(lyr, "source") and lyr.source() == form2_path):
                    try:
                        lyr.dataProvider().forceReload()
                        lyr.updateFields()
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
                            c_uuid = str(c_props.get("map_uuid") or c_props.get("df_map_uuid") or c_props.get("mapid") or c_props.get("df_mapid") or c_props.get("uuid") or "").strip()
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

            # 3. Match by map_uuid or mapid
            if target_rec is None and t_uuid:
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    c_props = rec.get("properties", rec) if isinstance(rec.get("properties"), dict) else rec
                    if not isinstance(c_props, dict):
                        continue
                    for k, v in c_props.items():
                        if str(k).strip().lower() in ("map_uuid", "df_map_uuid", "mapid", "df_mapid", "uuid") and str(v).strip() == t_uuid:
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
                    if not matched_key and prop_name.lower() in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid"):
                        for existing_k in target_dict.keys():
                            if existing_k.lower() in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid"):
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
                    target_dict[final_key] = typed_val

                # Track updated_columns in JSON record
                updated_key = "updated_columns"
                existing_uv = str(target_dict.get(updated_key) or "").strip()
                existing_tokens = [t.strip() for t in existing_uv.split("|") if t.strip()]
                new_tokens = [
                    (p[3:] if p.lower().startswith("df_") else p)
                    for p in props_to_update.keys()
                    if p.lower() != "updated_columns"
                ]
                if new_tokens:
                    combined = list(dict.fromkeys(existing_tokens + new_tokens))
                    target_dict[updated_key] = "|".join(combined)

                updated_count += 1

        # Write back to Form 2 JSON file (atomic attempt with fallback for Windows file locks)
        tmp_file = form2_path + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            try:
                os.replace(tmp_file, form2_path)
            except PermissionError:
                with open(form2_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except PermissionError as e:
            return False, 0, (
                f"Permission denied while saving Form 2 JSON to disk:\n{e}\n\n"
                "Tip: The file is currently open and locked by another program or text editor.\n"
                "Please close any application holding this file and try saving again."
            )
        except Exception as e:
            return False, 0, f"Error saving Form 2 JSON to disk:\n{e}"
        finally:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass

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
        if focus_w:
            if isinstance(focus_w, QLineEdit):
                parent_table = None
                curr = focus_w.parent()
                while curr:
                    if isinstance(curr, QTableWidget):
                        parent_table = curr
                        break
                    curr = curr.parent()
                if parent_table:
                    parent_table.setFocus()
            focus_w.clearFocus()

        if hasattr(self, "results_tab_widget"):
            try:
                cur_tab = self.results_tab_widget.currentWidget()
                if cur_tab:
                    for tbl in cur_tab.findChildren(QTableWidget):
                        tbl.setCurrentCell(-1, -1)
            except Exception:
                pass

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
                f"Could not save changes to the building points file:\n{geojson_err}",
            )
            return False

        # 2. Commit Form 2 Data (CSV or JSON) changes if dirty
        form2_saved = False
        form2_updated_count = 0
        form2_path = self.file_form2.filePath().strip() if hasattr(self, "file_form2") else ""
        form2_layer = self._get_or_load_form2_layer()

        if form2_path.lower().endswith(".csv"):
            if self._pending_json_edits:
                ok, form2_updated_count, form2_msg = self._save_csv_changes()
                if not ok:
                    QMessageBox.critical(
                        self,
                        "Save Failed",
                        f"Could not save changes to the Form 2 file:\n{form2_msg}",
                    )
                    return False
                form2_saved = True
                if form2_layer and form2_layer.isValid() and form2_layer.isModified():
                    try:
                        form2_layer.rollBack()
                        form2_layer.dataProvider().forceReload()
                        form2_layer.triggerRepaint()
                    except Exception:
                        pass
            elif form2_layer and form2_layer.isValid() and form2_layer.isEditable() and form2_layer.isModified():
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
                            f"Could not save changes to the Form 2 file:\n{form2_err}",
                        )
                        return False
                except Exception as exc:
                    QMessageBox.critical(
                        self,
                        "Save Failed",
                        f"Could not save changes to the Form 2 file:\n{exc}",
                    )
                    return False
        elif form2_path.lower().endswith(".json") and self._pending_json_edits:
            ok, form2_updated_count, form2_msg = self._save_json_changes()
            if not ok:
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Could not save changes to the Form 2 file:\n{form2_msg}",
                )
                return False
            form2_saved = True
        elif self._pending_json_edits:
            ok, form2_updated_count, form2_msg = self._save_csv_changes()
            if not ok:
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Could not save changes to the Form 2 file:\n{form2_msg}",
                )
                return False
            form2_saved = True

        # 3. Assemble saved message
        saved_parts = []
        if geojson_saved:
            saved_parts.append("Building Points")
        if form2_saved:
            saved_parts.append(f"Form 2 Data ({form2_updated_count} record(s))")

        if saved_parts:
            saved_msg = f"Saved changes to: {' and '.join(saved_parts)}."
        else:
            saved_msg = "There were no changes to save."

        # 4. Determine validation ID to re-run
        val_id = target_val_id
        if not val_id and hasattr(self, "results_tab_widget"):
            cur_widget = self.results_tab_widget.currentWidget()
            if cur_widget:
                val_id = cur_widget.property("val_id")
                if not val_id:
                    stacked = cur_widget.findChild(QStackedWidget, "stackedCategoryTables")
                    if stacked and stacked.currentWidget():
                        val_id = stacked.currentWidget().property("val_id")
                if not val_id:
                    combo = cur_widget.findChild(QComboBox, "comboCategoryChecks")
                    if combo and combo.currentData():
                        val_id = combo.currentData()
            if not val_id and self.results_tab_widget.currentIndex() > 0:
                cur_text = self.results_tab_widget.tabText(self.results_tab_widget.currentIndex())
                for r in self._rules:
                    if r["id"] in cur_text:
                        val_id = r["id"]
                        break

        # 5. Re-run validation check if a valid val_id is active (skip when dialog is closing)
        if getattr(self, "_is_closing", False):
            return True

        if val_id:
            self._rerun_validation_check(
                val_id,
                saved_msg=saved_msg,
                trigger_full_rerun_on_clean=True,
            )
        else:
            self.lbl_footer_status.setText(saved_msg)
            QMessageBox.information(
                self,
                "Changes Saved",
                saved_msg,
            )

        return True

    def _save_main_layer_changes(self):
        """Backwards compatible alias for _save_changes."""
        return self._save_changes()

    def _prompt_save_confirmation(self, target_val_id: Optional[str] = None) -> bool:
        """
        Prompt user with Save / Discard / Cancel confirmation when Save Changes is clicked.
        """
        if not is_valid_qobject(self):
            return False

        reply = QMessageBox.question(
            self,
            "Save Changes",
            "Do you want to save your changes?\n\nSave keeps them. Discard undoes all changes. Cancel goes back.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )

        if reply == QMessageBox.Save:
            return self._save_changes(target_val_id)
        elif reply == QMessageBox.Discard:
            return self._discard_changes(target_val_id)
        return False

    def _revert_table_cells_to_original(self, table: QTableWidget, val_id: Optional[str] = None):
        """Revert all cells in table to their cached Qt.UserRole + 20 original unedited values."""
        if not table or not is_valid_qobject(table):
            return
        table.setProperty("is_populating", True)
        try:
            rule = next((r for r in self._rules if r["id"] == val_id), None) if val_id else None
            target_cols = [rule["target_column"]] if (rule and rule.get("target_column")) else []
            for r in range(table.rowCount()):
                chk_it = table.item(r, 0)
                if chk_it:
                    chk_it.setCheckState(Qt.Unchecked)
                for c in range(1, table.columnCount() - 1):
                    it = table.item(r, c)
                    if it:
                        orig = it.data(Qt.UserRole + 20)
                        if orig is not None:
                            it.setText(str(orig))
                        fname = it.data(Qt.UserRole + 2)
                        if fname and fname in target_cols:
                            self._style_table_cell(it, "target")
                        else:
                            self._style_table_cell(it, "default")
                # Reset action cell buttons if present
                act_w = table.cellWidget(r, table.columnCount() - 1)
                if act_w:
                    for btn in act_w.findChildren(QPushButton):
                        if btn.text() in ("Fixed", "Deleted"):
                            btn.setText("Edit" if btn.text() == "Fixed" else "Delete")
                            btn.setEnabled(True)
        finally:
            table.setProperty("is_populating", False)

    def _discard_changes(self, target_val_id: Optional[str] = None) -> bool:
        """
        Discard pending in-memory and buffer edits, restoring layers and table to disk state.
        """
        if not is_valid_qobject(self):
            return False

        # 1. Roll back GeoJSON main building layer edits
        main_layer = self._find_existing_main_building_layer()
        if main_layer and main_layer.isValid() and main_layer.isEditable():
            try:
                main_layer.rollBack()
                main_layer.startEditing()
            except Exception:
                pass

        # 2. Roll back Form 2 layer edits if active
        form2_layer = self._get_or_load_form2_layer()
        if form2_layer and form2_layer.isValid() and form2_layer.isEditable():
            try:
                form2_layer.rollBack()
                form2_layer.startEditing()
            except Exception:
                pass

        # 3. Roll back any result layers if modified in edit buffer
        if hasattr(self, "_result_layers") and self._result_layers:
            for r_info in self._result_layers.values():
                if isinstance(r_info, dict):
                    r_lay = r_info.get("layer")
                    if r_lay and r_lay.isValid() and r_lay.isEditable() and r_lay.isModified():
                        try:
                            r_lay.rollBack()
                            r_lay.startEditing()
                        except Exception:
                            pass

        # 4. Clear pending in-memory Form 2 edits
        self._pending_json_edits.clear()

        # 5. Refresh map canvas
        if self.iface and self.iface.mapCanvas():
            self.iface.mapCanvas().refresh()

        # 6. Resolve validation ID to re-run and refresh table to disk state
        val_id = target_val_id
        results_tab = None
        try:
            results_tab = getattr(self, "results_tab_widget", None)
        except RuntimeError:
            pass

        if not val_id and results_tab:
            cur_widget = results_tab.currentWidget()
            if cur_widget:
                val_id = cur_widget.property("val_id")
                if not val_id:
                    stacked = cur_widget.findChild(QStackedWidget, "stackedCategoryTables")
                    if stacked and stacked.currentWidget():
                        val_id = stacked.currentWidget().property("val_id")
                if not val_id:
                    combo = cur_widget.findChild(QComboBox, "comboCategoryChecks")
                    if combo and combo.currentData():
                        val_id = combo.currentData()
            if not val_id and self.results_tab_widget.currentIndex() > 0:
                cur_text = self.results_tab_widget.tabText(self.results_tab_widget.currentIndex())
                for r in self._rules:
                    if r["id"] in cur_text:
                        val_id = r["id"]
                        break

        # 7. Revert active table cells in-memory as immediate zero-latency feedback
        try:
            if hasattr(self, "results_tab_widget"):
                cur_w = self.results_tab_widget.currentWidget()
                if cur_w:
                    tbl = cur_w.findChild(QTableWidget)
                    if tbl:
                        self._revert_table_cells_to_original(tbl, val_id)
        except Exception:
            pass

        if getattr(self, "_is_closing", False):
            return True

        discard_msg = "Changes discarded. The files are back to how they were."
        if val_id:
            self._rerun_validation_check(
                val_id,
                saved_msg=discard_msg,
                trigger_full_rerun_on_clean=False,
            )
        else:
            self.lbl_footer_status.setText(discard_msg)
            QMessageBox.information(
                self,
                "Changes Discarded",
                "All unsaved changes were undone.",
            )

        return True

    # -----------------------------------------------------------------------
    # Process: Single-Check Validation Re-run & Live Refresh
    # -----------------------------------------------------------------------
    def _rerun_validation_check(
        self,
        val_id: str,
        saved_msg: str = "",
        trigger_full_rerun_on_clean: bool = False,
    ):
        """
        Execute a single validation rule using fresh disk data and update its
        corresponding tab in the Results Workspace as well as the Summary Overview.
        """
        form2_path = self.file_form2.filePath().strip()
        points_path = self.file_points.filePath().strip()
        base_path = self.file_base.filePath().strip()

        if not form2_path or not os.path.exists(form2_path):
            self.lbl_footer_status.setText(f"{saved_msg} (Could not re-check: Form 2 file is missing)")
            return
        if not points_path or not os.path.exists(points_path):
            self.lbl_footer_status.setText(f"{saved_msg} (Could not re-check: Building Points file is missing)")
            return

        rule = next((r for r in self._rules if r["id"] == val_id), None)
        if not rule:
            rule = {"id": val_id, "name": val_id.replace("_", " ").title(), "has_base": False}

        if rule.get("has_base") and (not base_path or not os.path.exists(base_path)):
            self.lbl_footer_status.setText(f"{saved_msg} (Could not re-check: Base Layers file is required)")
            return

        reg_id = f"gmd_pipeline:{val_id}"
        is_registered = QgsApplication.processingRegistry().algorithmById(reg_id) is not None
        alg = self._get_algorithm_instance(val_id)
        if not is_registered and not alg:
            self.lbl_footer_status.setText(f"{saved_msg} (Could not start check '{val_id}')")
            return

        alg_target = alg if alg is not None else reg_id

        self.lbl_footer_status.setText(f"Re-checking '{val_id}'...")
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
                "Re-check Failed",
                f"{saved_msg}\n\nSomething went wrong while re-checking '{val_id}':\n{exc}",
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

        # If saving resolved all remaining issues for this rule, re-run full validation
        # so the Summary Overview reflects updated counts across all enabled checks.
        if new_count == 0 and trigger_full_rerun_on_clean:
            if getattr(self, "_active_review_dock", None):
                dock = self._active_review_dock
                if getattr(dock, "val_id", None) in (None, val_id):
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

            self._log_success(
                f"'{val_id}' re-run complete: 0 flagged issues! Re-running full validation to refresh summary..."
            )
            self.lbl_footer_status.setText(
                f"'{val_id}' has 0 remaining issues. Re-running full validation to update summary..."
            )
            QApplication.processEvents()
            self.run_validation(
                auto_rerun=True,
                resolved_val_id=val_id,
                saved_msg=saved_msg,
            )
            return

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
        if proj and self.should_load_canvas:
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
                if self.should_group_layers:
                    grp = self._get_or_create_layer_group("2027 CBMS MV Results")
                    proj.addMapLayer(out_layer, False)
                    grp.addLayer(out_layer)
                else:
                    proj.addMapLayer(out_layer)

            if self.iface:
                self.iface.mapCanvas().refresh()

        # Update Results Workspace (rebuilds Two-tier Category Tabs & Summary Scorecard, then jumps to check)
        self._populate_results_workspace(self._execution_summary, self._result_layers)
        self._jump_to_result_tab(val_id)

        # User feedback
        if new_count == 0:
            self._log_success(f"'{val_id}' re-run complete: 0 flagged issues! All issues resolved.")
            self.lbl_footer_status.setText(f"Check '{val_id}': no issues left.")
            QMessageBox.information(
                self,
                "All Issues Resolved",
                f"{saved_msg}\n\n"
                f"Re-checked '{val_id}':\n"
                f"No issues found. Everything for this check is now correct.",
            )
        else:
            status_prefix = "Changes discarded" if (saved_msg and "discarded" in saved_msg.lower()) else "Changes saved"
            self.lbl_footer_status.setText(f"{status_prefix} • '{val_id}': {new_count:,} issue(s) left.")
            QMessageBox.information(
                self,
                "Re-check Complete",
                f"{saved_msg}\n\n"
                f"Re-checked '{val_id}':\n"
                f"{new_count:,} record(s) still need fixing.",
            )

    # -----------------------------------------------------------------------
    # Process: Table Navigation, Row Zoom & CSV Export
    # -----------------------------------------------------------------------
    def _on_table_row_clicked(
        self,
        layer: QgsVectorLayer,
        table: QTableWidget,
        row: int,
        col: Optional[int] = None,
        combo_actions: Optional[QComboBox] = None,
        btn_update_selected: Optional[QPushButton] = None,
    ):
        """Zoom and flash canvas feature when clicking any table row, and sync checkbox if data cell clicked."""
        if col is not None and col > 0:
            self._sync_row_checkbox_with_selection(
                layer, table, row, combo_actions=combo_actions, btn_update_selected=btn_update_selected, from_header=False
            )
            return

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

    def _on_vertical_header_section_clicked(
        self,
        layer: QgsVectorLayer,
        table: QTableWidget,
        row_idx: int,
        combo_actions: Optional[QComboBox] = None,
        btn_update_selected: Optional[QPushButton] = None,
    ):
        """When user clicks a row number in the vertical header, sync checkbox with selection and zoom."""
        self._sync_row_checkbox_with_selection(
            layer, table, row_idx, combo_actions=combo_actions, btn_update_selected=btn_update_selected, from_header=True
        )

    def _sync_row_checkbox_with_selection(
        self,
        layer: QgsVectorLayer,
        table: QTableWidget,
        row_idx: int,
        combo_actions: Optional[QComboBox] = None,
        btn_update_selected: Optional[QPushButton] = None,
        from_header: bool = False,
    ):
        """
        Synchronize row checkbox with selection.
        If Shift or Ctrl is NOT held for multi-selection, unchecks all other rows and checks the selected row.
        If Shift or Ctrl IS held (or multiple rows are selected), checks all selected rows together.
        """
        if not is_valid_qobject(self) or not is_valid_qobject(table) or table.property("is_populating"):
            return

        item0 = table.item(row_idx, 0)
        if not item0:
            return

        modifiers = QApplication.keyboardModifiers() if QApplication else Qt.NoModifier
        is_multi_modifier = bool(modifiers & (Qt.ShiftModifier | Qt.ControlModifier))
        sel_rows = sorted(set(idx.row() for idx in table.selectionModel().selectedRows()))
        is_multi_selection = is_multi_modifier or (len(sel_rows) > 1 and row_idx in sel_rows)

        table.setProperty("is_populating", True)
        try:
            if is_multi_selection:
                rows_to_check = sel_rows if (row_idx in sel_rows and len(sel_rows) > 1) else [row_idx]
                for r in rows_to_check:
                    it = table.item(r, 0)
                    if it:
                        it.setCheckState(Qt.Checked)
            else:
                is_already_only_checked = (
                    item0.checkState() == Qt.Checked and
                    sum(1 for r in range(table.rowCount()) if table.item(r, 0) and table.item(r, 0).checkState() == Qt.Checked) == 1
                )
                if from_header and is_already_only_checked:
                    item0.setCheckState(Qt.Unchecked)
                else:
                    for r in range(table.rowCount()):
                        it = table.item(r, 0)
                        if it:
                            it.setCheckState(Qt.Checked if r == row_idx else Qt.Unchecked)
        finally:
            table.setProperty("is_populating", False)

        # Update action buttons and count
        checked_count = sum(
            1 for r in range(table.rowCount())
            if table.item(r, 0) and table.item(r, 0).checkState() == Qt.Checked
        )
        if combo_actions:
            combo_actions.setItemText(0, "Actions")
        if btn_update_selected:
            btn_update_selected.setText(f"Apply Fix Action ({checked_count})" if checked_count > 0 else "Apply Fix Action")
            btn_update_selected.setEnabled(checked_count > 0)

        # Trigger canvas zoom and feature flash
        self._on_table_row_clicked(layer, table, row_idx)

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
            QMessageBox.warning(self, "Export Failed", "There is no data to export.")
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
                "Export Complete",
                f"Exported {layer.featureCount():,} records to:\n{filename}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not export the CSV file:\n{exc}")

    # -----------------------------------------------------------------------
    # Review & Fix Dock Integration (Check & Update Pattern)
    # -----------------------------------------------------------------------
    def _find_existing_main_building_layer(self) -> Optional[QgsVectorLayer]:
        """
        Locate the main Geotagged Building Points layer ONLY if it is already loaded
        in the QGIS project. Never loads or creates new layers in the project.
        """
        points_path = self.file_points.filePath().strip() if hasattr(self, "file_points") else ""
        if not points_path:
            return None

        proj = self.project if self.project else QgsProject.instance()
        norm_path = os.path.normpath(points_path).lower()

        for layer in proj.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                src = os.path.normpath(layer.source().split("|")[0]).lower()
                if src == norm_path:
                    return layer
        return None

    def _get_or_load_main_building_layer(self) -> Optional[QgsVectorLayer]:
        """
        Locate the main Geotagged Building Points layer in the QGIS project matching
        the input file path. If not currently loaded, loads it into the project.
        """
        points_path = self.file_points.filePath().strip() if hasattr(self, "file_points") else ""
        proj = self.project if self.project else QgsProject.instance()

        # 1. Search existing project layers by path
        if points_path:
            norm_path = os.path.normpath(points_path).lower()
            for layer in proj.mapLayers().values():
                if isinstance(layer, QgsVectorLayer) and layer.isValid():
                    src = os.path.normpath(layer.source().split("|")[0]).lower()
                    if src == norm_path:
                        return layer

        # 2. Load from points_path if file exists on disk
        if points_path and os.path.exists(points_path):
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
            except Exception as exc:
                self._log_error(f"Error loading building points layer: {exc}")

        # 3. Fallback: Search existing persistent project layers by geometry and key fields (excluding memory/error layers)
        for layer in proj.mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                if layer.providerType() == "memory":
                    continue
                is_point = False
                try:
                    is_point = (layer.geometryType() == QgsWkbTypes.PointGeometry)
                except Exception:
                    try:
                        is_point = (layer.geometryType() == Qgis.GeometryType.Point)
                    except Exception:
                        pass
                if is_point:
                    fnames = [f.name().lower() for f in layer.fields()]
                    if "sf_map_uuid" in fnames or "map_uuid" in fnames:
                        return layer

        if is_valid_qobject(self):
            QMessageBox.warning(
                self,
                "Building Points File Missing",
                "The Building Points file was not found.\n\n"
                "Please choose a Building Points file in the 'Data Config' tab first.",
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
            QMessageBox.warning(self, "Cannot Open Results", "The results for this check could not be opened.")
            return

        if error_layer.featureCount() == 0:
            QMessageBox.information(
                self,
                "No Issues",
                f"Check '{val_id}' has no issues to review.",
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

        rule_target_fields = None
        for r in getattr(self, "rules", []):
            if r.get("id") == val_id:
                rule_target_fields = r.get("target_fields")
                break

        try:
            dock = CbmsMvReviewDock(
                parent_dialog=self,
                val_id=val_id,
                check_name=check_name,
                error_layer=error_layer,
                main_layer=main_layer,
                start_index=start_index,
                target_fields=rule_target_fields,
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

            # Minimize main dialog if floating to give full visibility to canvas and dock
            if not getattr(self, "_is_docked", False):
                self.showMinimized()
            self.lbl_footer_status.setText(
                f"Reviewing '{val_id}' in dock (Item {dock.current_index + 1}/{error_layer.featureCount():,})"
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Cannot Open Review Panel",
                f"The review panel could not be opened:\n{exc}",
            )

    def _on_review_dock_closed(self):
        """Slot triggered when review dock is closed."""
        self._active_review_dock = None
        if is_valid_qobject(self):
            try:
                if getattr(self, "_is_docked", False) and self._dock_widget:
                    self._dock_widget.show()
                    self._dock_widget.raise_()
                else:
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Docking Management (Attribute Table style)
    # -----------------------------------------------------------------------
    def toggle_dock(self):
        """Toggle between docked mode (bottom center of QGIS) and floating dialog."""
        if not is_valid_qobject(self):
            return
        if self._is_docked:
            self.undock_window()
        else:
            self.dock_window()

    def _restore_central_container_to_dialog(self):
        """Safely reparent central container back into dialog layout, ensuring it is never deleted."""
        if not hasattr(self, "_central_container") or not self._central_container:
            return
        if not is_valid_qobject(self._central_container):
            return

        try:
            if hasattr(self, "_dock_widget") and self._dock_widget:
                if self._dock_widget.widget() == self._central_container:
                    self._dock_widget.setWidget(None)

            self._central_container.setParent(self)
            self._central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._central_container.setMinimumSize(0, 0)
            self._central_container.setMaximumSize(16777215, 16777215)
            self._central_container.setGeometry(self.rect())
            if hasattr(self, "_dialog_layout") and self._dialog_layout:
                self._dialog_layout.removeWidget(self._central_container)
                self._dialog_layout.addWidget(self._central_container, 1)
                self._dialog_layout.activate()
            self._central_container.setVisible(True)
            self._central_container.show()
            if self._central_container.layout():
                self._central_container.layout().activate()
            self._central_container.updateGeometry()
            self._central_container.update()
        except Exception:
            pass

    def dock_window(self):
        """Dock the CBMS MV tool at the bottom center of QGIS mainWindow."""
        if not is_valid_qobject(self):
            return
        if not self.iface or not hasattr(self.iface, "addDockWidget"):
            return

        self._is_switching_dock = True
        try:
            if not self._dock_widget:
                self._dock_widget = CbmsmvDockWidget("2027 CBMS Form 2 Map Validation", self.iface.mainWindow())
                self._dock_widget.setObjectName("CbmsmvMainDock")
                self._dock_widget.setAllowedAreas(
                    Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea | Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
                )
                self._dock_widget.setFeatures(
                    QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
                )
                self._dock_widget.closed.connect(self._on_dock_closed)
                self._dock_widget.topLevelChanged.connect(self._on_dock_top_level_changed)
                self._dock_widget.setStyleSheet(self.styleSheet())

            # Reparent central container to dock widget
            self._dialog_layout.removeWidget(self._central_container)
            self._central_container.setParent(self._dock_widget)
            self._central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._central_container.setMinimumSize(0, 0)
            self._dock_widget.setWidget(self._central_container)
            self._central_container.setVisible(True)
            self._central_container.show()
            if self._central_container.layout():
                self._central_container.layout().activate()

            # Hide the floating dialog
            self.hide()

            # Add to QGIS bottom dock
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self._dock_widget)
            self._dock_widget.show()
            self._dock_widget.raise_()

            self._is_docked = True
            if hasattr(self, "btn_dock"):
                self.btn_dock.setText("Switch to Window Mode")
                self.btn_dock.setToolTip("Undock to a floating standalone window (Ctrl+D)")
            self.settings.setValue("cbms_mv/is_docked", True)
        finally:
            self._is_switching_dock = False

    def undock_window(self):
        """Undock the CBMS MV tool from QGIS mainWindow back into a floating dialog."""
        if not is_valid_qobject(self):
            return
        self._is_switching_dock = True
        try:
            if self._dock_widget:
                if self.iface and hasattr(self.iface, "removeDockWidget"):
                    self.iface.removeDockWidget(self._dock_widget)
                self._dock_widget.hide()

            # Reparent central container back to dialog
            self._restore_central_container_to_dialog()

            if hasattr(self, "main_stack") and self.main_stack.currentWidget():
                self.main_stack.currentWidget().show()
                self.main_stack.currentWidget().setVisible(True)
                if self.main_stack.currentWidget().layout():
                    self.main_stack.currentWidget().layout().activate()
                self.main_stack.show()

            self._is_docked = False
            if hasattr(self, "btn_dock"):
                self.btn_dock.setText("Switch to Dock Mode")
                self.btn_dock.setToolTip("Dock this window at the bottom of the QGIS interface (like Attribute Table) (Ctrl+D)")

            self.showNormal()
            self.raise_()
            self.activateWindow()
            if hasattr(self, "_central_container") and is_valid_qobject(self._central_container):
                self._central_container.setGeometry(self.rect())
                if self._central_container.layout():
                    self._central_container.layout().activate()
            self.updateGeometry()
            self.update()
            if self._dialog_layout:
                self._dialog_layout.activate()
            if self._central_container and self._central_container.layout():
                self._central_container.layout().activate()
            self.settings.setValue("cbms_mv/is_docked", False)
            if hasattr(self, "lbl_footer_status") and self.lbl_footer_status:
                self.lbl_footer_status.setText("")
        finally:
            self._is_switching_dock = False

    def _on_dock_closed(self):
        """Handle dock widget close button [X] clicked by user."""
        if not is_valid_qobject(self):
            return
        if getattr(self, "_is_switching_dock", False) or getattr(self, "_is_closing", False):
            return
        self.close()

    def _on_dock_top_level_changed(self, floating: bool):
        """Handle dock widget becoming floating or re-docking via dragging."""
        if not is_valid_qobject(self):
            return
        if getattr(self, "_is_switching_dock", False) or getattr(self, "_is_closing", False):
            return
        # If the tool is currently in standalone dialog mode (undocked), ignore dock widget signals
        if not getattr(self, "_is_docked", False):
            return
        try:
            if hasattr(self, "_central_container") and is_valid_qobject(self._central_container):
                self._central_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self._central_container.setMinimumSize(0, 0)
                if self._central_container.layout():
                    self._central_container.layout().activate()
                self._central_container.updateGeometry()
                self._central_container.update()
            if self._dock_widget and is_valid_qobject(self._dock_widget):
                w = self._dock_widget.widget()
                if w and is_valid_qobject(w):
                    w.setGeometry(self._dock_widget.rect())
                    if w.layout():
                        w.layout().activate()
        except Exception:
            pass
        if hasattr(self, "lbl_footer_status") and self.lbl_footer_status:
            if floating:
                self.lbl_footer_status.setText(" ")
            else:
                self.lbl_footer_status.setText(" ")

    def resizeEvent(self, event):
        """Ensure child layout and stacked widgets recalibrate dimensions on dialog resize."""
        super().resizeEvent(event)
        try:
            if hasattr(self, "_central_container") and is_valid_qobject(self._central_container):
                self._central_container.setGeometry(self.rect())
                if self._central_container.layout():
                    self._central_container.layout().activate()
                self._central_container.updateGeometry()
            if hasattr(self, "main_stack") and is_valid_qobject(self.main_stack):
                if self.main_stack.layout():
                    self.main_stack.layout().activate()
                cur = self.main_stack.currentWidget()
                if cur and is_valid_qobject(cur):
                    if cur.layout():
                        cur.layout().activate()
                    cur.updateGeometry()
            if hasattr(self, "results_tab_widget") and is_valid_qobject(self.results_tab_widget):
                cur_tab = self.results_tab_widget.currentWidget()
                if cur_tab and is_valid_qobject(cur_tab) and cur_tab.layout():
                    cur_tab.layout().activate()
            if hasattr(self, "_dialog_layout") and self._dialog_layout:
                self._dialog_layout.activate()
        except Exception:
            pass

    def changeEvent(self, event):
        """Handle window state changes (e.g. Maximized, Normalized) and recalibrate layout."""
        super().changeEvent(event)
        try:
            if event.type() == QEvent.WindowStateChange:
                if hasattr(self, "_central_container") and is_valid_qobject(self._central_container):
                    self._central_container.setGeometry(self.rect())
                    if self._central_container.layout():
                        self._central_container.layout().activate()
                    self._central_container.updateGeometry()
                if hasattr(self, "_dialog_layout") and self._dialog_layout:
                    self._dialog_layout.activate()
        except Exception:
            pass

    def showEvent(self, event):
        """Re-check theme when dialog is shown, update styling if changed, and sync load inputs checkbox default."""
        if not is_valid_qobject(self):
            return
        super().showEvent(event)
        try:
            if hasattr(self, "_central_container") and is_valid_qobject(self._central_container):
                self._central_container.setGeometry(self.rect())
                if self._central_container.layout():
                    self._central_container.layout().activate()
                self._central_container.updateGeometry()
        except Exception:
            pass
        try:
            if not getattr(self, "_user_toggled_load_inputs", False) and not getattr(self, "_is_switching_dock", False):
                self._update_load_inputs_default()
        except Exception:
            pass
        try:
            palette = self.palette()
            bg_color = palette.color(palette.Window)
            new_theme = "dark" if bg_color.lightness() < 128 else "light"
            if new_theme != getattr(self, "current_theme", None):
                self.current_theme = new_theme
                self._apply_styling()
        except Exception:
            pass

    def closeEvent(self, event):
        """Prompt to save unsaved edits and clean up active review dock and main dock widget."""
        if not is_valid_qobject(self):
            event.accept()
            return
        self._is_closing = True
        self._user_toggled_load_inputs = False
        try:
            main_layer = self._find_existing_main_building_layer()
            has_unsaved = (
                (main_layer and main_layer.isValid() and main_layer.isEditable() and main_layer.isModified())
                or bool(self._pending_json_edits)
            )
            if has_unsaved:
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have changes that are not saved yet.\n\nDo you want to save them before closing?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save,
                )
                if reply == QMessageBox.Save:
                    if not self._save_changes():
                        event.ignore()
                        self._is_closing = False
                        if getattr(self, "_is_docked", False) and self._dock_widget:
                            self._dock_widget.show()
                        return
                elif reply == QMessageBox.Discard:
                    self._discard_changes()
                elif reply == QMessageBox.Cancel:
                    event.ignore()
                    self._is_closing = False
                    if getattr(self, "_is_docked", False) and self._dock_widget:
                        self._dock_widget.show()
                    return

            # ALWAYS ensure central container is safely reparented back to self BEFORE destroying dock
            self._restore_central_container_to_dialog()

            # Clean up main dock widget if docked
            if hasattr(self, "_dock_widget") and self._dock_widget:
                dock = self._dock_widget
                self._dock_widget = None
                try:
                    if hasattr(dock, "closed"):
                        try:
                            dock.closed.disconnect()
                        except Exception:
                            pass
                    if hasattr(dock, "topLevelChanged"):
                        try:
                            dock.topLevelChanged.disconnect()
                        except Exception:
                            pass
                    if self.iface and hasattr(self.iface, "removeDockWidget"):
                        self.iface.removeDockWidget(dock)
                    dock.deleteLater()
                except Exception:
                    pass

            self._is_docked = False
            self.settings.setValue("cbms_mv/is_docked", False)

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

            if self.project:
                try:
                    self.project.projectRead.disconnect(self._on_project_changed)
                except Exception:
                    pass
                try:
                    self.project.cleared.disconnect(self._on_project_changed)
                except Exception:
                    pass

            super().closeEvent(event)
            try:
                self.finished.emit(0)
            except Exception:
                pass
        finally:
            self._is_closing = False


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
        colors = self._get_theme_colors()
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
        lbl_form2.setStyleSheet(f"font-weight: bold; color: {colors['title']};")
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
        lbl_points.setStyleSheet(f"font-weight: bold; color: {colors['title']};")
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
        lbl_base.setStyleSheet(f"font-weight: bold; color: {colors['title']};")
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
        self.chk_load_inputs_canvas.clicked.connect(self._on_user_toggled_load_inputs)
        self.chk_load_inputs_canvas.stateChanged.connect(self._on_inputs_changed)
        self._update_load_inputs_default()
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
        lbl_mode.setStyleSheet(f"font-weight: bold; color: {colors['title']};")
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
        lbl_gpkg.setStyleSheet(f"font-weight: bold; color: {colors['title']};")
        self.file_widget_gpkg = QgsFileWidget()
        self.file_widget_gpkg.setStorageMode(QgsFileWidget.SaveFile)
        self.file_widget_gpkg.setFilter("GeoPackage Files (*.gpkg)")
        self.file_widget_gpkg.setDialogTitle("Save Validation Results GeoPackage")
        gpkg_layout.addWidget(lbl_gpkg)
        gpkg_layout.addWidget(self.file_widget_gpkg, stretch=1)
        self.gpkg_widget.setVisible(False)
        vbox_output.addWidget(self.gpkg_widget)

        # Checkboxes
        #self.chk_load_canvas = QCheckBox("Add generated error/flag layers directly into QGIS Canvas")
        #self.chk_load_canvas.setChecked(False)
        #vbox_output.addWidget(self.chk_load_canvas)

        #self.chk_group_layers = QCheckBox("Group validation result layers under '2027 CBMS MV Results'")
        #self.chk_group_layers.setChecked(False)
        #vbox_output.addWidget(self.chk_group_layers)

        self.chk_summary_report = QCheckBox("Generate validation audit report (JSON && Summary CSV)")
        self.chk_summary_report.setChecked(True)
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
        """Update file existence indicators beside input boxes and persist settings."""
        form2 = self.file_form2.filePath().strip()
        points = self.file_points.filePath().strip()
        base = self.file_base.filePath().strip()

        # Persist paths and load options
        self.settings.setValue(SETTINGS_KEY_FORM2, form2)
        self.settings.setValue(SETTINGS_KEY_POINTS, points)
        self.settings.setValue(SETTINGS_KEY_BASE, base)
        if hasattr(self, "chk_load_inputs_canvas"):
            self.settings.setValue(SETTINGS_KEY_LOAD_INPUTS, self.chk_load_inputs_canvas.isChecked())

        # Update indicator status icons beside input boxes
        succ_icon = QgsApplication.getThemeIcon("mIconSuccess.svg")
        crit_icon = QgsApplication.getThemeIcon("mIconCritical.svg")

        def _update_file_status(lbl: QLabel, path_val: str, ok_tip: str, missing_tip: str, is_optional: bool = False):
            if not path_val:
                if is_optional:
                    lbl.clear()
                    lbl.setToolTip("Optional input")
                else:
                    if not crit_icon.isNull():
                        lbl.setPixmap(crit_icon.pixmap(14, 14))
                    else:
                        lbl.setText("•")
                    lbl.setToolTip(missing_tip)
                return

            if os.path.exists(path_val):
                if not succ_icon.isNull():
                    lbl.setPixmap(succ_icon.pixmap(14, 14))
                else:
                    lbl.setText("•")
                lbl.setToolTip(ok_tip)
            else:
                if not crit_icon.isNull():
                    lbl.setPixmap(crit_icon.pixmap(14, 14))
                else:
                    lbl.setText("•")
                lbl.setToolTip(missing_tip)

        if hasattr(self, "lbl_status_form2"):
            _update_file_status(
                self.lbl_status_form2,
                form2,
                "Form 2 Data file exists",
                "Form 2 Data file required",
                is_optional=False,
            )

        if hasattr(self, "lbl_status_points"):
            _update_file_status(
                self.lbl_status_points,
                points,
                "Geotagged Building Points file exists",
                "Geotagged Building Points file required",
                is_optional=False,
            )

        if hasattr(self, "lbl_status_base"):
            _update_file_status(
                self.lbl_status_base,
                base,
                "Base Layers GeoPackage exists",
                "Base Layers GeoPackage not found",
                is_optional=True,
            )

    def _has_primary_inputs_group(self) -> bool:
        """
        Check if the '2027 CBMS Primary Inputs' group exists and contains layers in the QGIS Layers Panel.
        Returns:
            bool: True if group exists and contains one or more layers; False otherwise.
        """
        proj = self.project if hasattr(self, "project") and self.project else QgsProject.instance()
        if not proj or not hasattr(proj, "layerTreeRoot"):
            return False
        root = proj.layerTreeRoot()
        if not root:
            return False
        grp = root.findGroup("2027 CBMS Primary Inputs")
        if grp is None:
            return False
        if hasattr(grp, "findLayers"):
            tree_layers = grp.findLayers()
            if not tree_layers:
                return False
            valid_layers = [
                tl for tl in tree_layers
                if tl and getattr(tl, "layer", None) and tl.layer() is not None and tl.layer().isValid()
            ]
            if any(getattr(tl, "layer", None) for tl in tree_layers):
                return len(valid_layers) > 0
            return len(tree_layers) > 0
        if hasattr(grp, "children"):
            return len(grp.children()) > 0
        return True

    def _update_load_inputs_default(self):
        """
        Dynamically update the checked state of chk_load_inputs_canvas based on whether
        the '2027 CBMS Primary Inputs' group is already present in the layers panel.
        Checked by default if group is absent or empty, unchecked if already loaded.
        """
        if not hasattr(self, "chk_load_inputs_canvas"):
            return
        has_group = self._has_primary_inputs_group()
        should_check = not has_group
        self.chk_load_inputs_canvas.blockSignals(True)
        try:
            self.chk_load_inputs_canvas.setChecked(should_check)
        finally:
            self.chk_load_inputs_canvas.blockSignals(False)
        self.settings.setValue(SETTINGS_KEY_LOAD_INPUTS, should_check)

    def _on_user_toggled_load_inputs(self):
        """Track explicit user click on the load primary inputs checkbox."""
        self._user_toggled_load_inputs = True

    def _on_project_changed(self):
        """Handle QGIS project read or cleared event to re-evaluate input layer presence."""
        if not is_valid_qobject(self):
            return
        self._user_toggled_load_inputs = False
        self._update_load_inputs_default()

    def _load_saved_settings(self):
        """Load previously saved filepaths and load options from QSettings if available."""
        saved_form2 = self.settings.value(SETTINGS_KEY_FORM2, "", type=str) or self.settings.value(SETTINGS_KEY_FORM2_LEGACY, "", type=str)
        saved_points = self.settings.value(SETTINGS_KEY_POINTS, "", type=str)
        saved_base = self.settings.value(SETTINGS_KEY_BASE, "", type=str)

        if saved_form2:
            self.file_form2.setFilePath(saved_form2)
        if saved_points:
            self.file_points.setFilePath(saved_points)
        if saved_base:
            self.file_base.setFilePath(saved_base)

        if hasattr(self, "chk_load_inputs_canvas"):
            self._update_load_inputs_default()

        self._on_inputs_changed()

    # -----------------------------------------------------------------------
    # Tab 2: Validation Rules (Dynamic)
    # -----------------------------------------------------------------------
    def _create_tab_validation_rules(self) -> QWidget:
        """
        Create the Validation Rules tab displaying dynamically discovered algorithms.
        Columns:
          - Enable (Checkbox)
          - Category (Label + Icon)
          - Validation ID (Algorithm filename without .py)
          - Validation Check Name (First line of shortHelpString)
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        colors = self._get_theme_colors()

        # Filter & Quick Action Toolbar (styled same as category and summary nav bar)
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("rulesToolbarFrame")
        toolbar_frame.setStyleSheet(f"""
            #rulesToolbarFrame {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['border']};
                border-radius: 5px;
            }}
        """)
        toolbar = QHBoxLayout(toolbar_frame)
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar.setSpacing(8)

        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Search rules by Validation ID, check name, or keyword...")
        filter_icon = QgsApplication.getThemeIcon("mActionFilter.svg")
        if not filter_icon.isNull():
            self.edit_filter.addAction(filter_icon, QLineEdit.LeadingPosition)
        self.edit_filter.setClearButtonEnabled(True)
        self.edit_filter.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 8px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {colors['border_focus']};
            }}
        """)
        self.edit_filter.textChanged.connect(self._filter_rules_table)
        toolbar.addWidget(self.edit_filter, stretch=1)

        self.combo_rule_category = QComboBox()
        self.combo_rule_category.addItem("Category: All", "all")
        self.combo_rule_category.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 4px 10px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
                min-width: 145px;
            }}
            QComboBox:focus {{
                border-color: {colors['border_focus']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
                selection-background-color: {colors['selected_item_bg']};
                selection-color: {colors['selected_item_text']};
            }}
        """)
        self.combo_rule_category.currentIndexChanged.connect(self._filter_rules_table)
        toolbar.addWidget(self.combo_rule_category)

        btn_rule_style = f"""
            QPushButton {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                font-weight: 600;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid {colors['border']};
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['title']};
            }}
        """

        btn_select_all = QPushButton("Select All")
        sel_ic = QgsApplication.getThemeIcon("mActionSelectAll.svg")
        if not sel_ic.isNull():
            btn_select_all.setIcon(sel_ic)
        btn_select_all.setStyleSheet(btn_rule_style)
        btn_select_all.clicked.connect(lambda: self._set_all_rules_checked(True))

        btn_deselect_all = QPushButton("Deselect All")
        desel_ic = QgsApplication.getThemeIcon("mActionDeselectAll.svg")
        if not desel_ic.isNull():
            btn_deselect_all.setIcon(desel_ic)
        btn_deselect_all.setStyleSheet(btn_rule_style)
        btn_deselect_all.clicked.connect(lambda: self._set_all_rules_checked(False))

        btn_refresh = QToolButton()
        ref_ic = QgsApplication.getThemeIcon("mActionRefresh.svg")
        if not ref_ic.isNull():
            btn_refresh.setIcon(ref_ic)
        else:
            btn_refresh.setText("Refresh")
        btn_refresh.setToolTip("Refresh and re-scan algorithms in gmd_scripts/cbms_mv")
        btn_refresh.setStyleSheet(f"""
            QToolButton {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                border-radius: 4px;
                border: 1px solid {colors['border']};
                padding: 4px 8px;
                font-size: 11px;
            }}
            QToolButton:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['title']};
            }}
        """)
        btn_refresh.clicked.connect(self.refresh_rules)

        toolbar.addWidget(btn_select_all)
        toolbar.addWidget(btn_deselect_all)
        toolbar.addWidget(btn_refresh)
        layout.addWidget(toolbar_frame)

        # Rules Table
        self.rules_table = QTableWidget()
        enable_shift_scroll(self.rules_table)
        self.rules_table.setColumnCount(4)
        self.rules_table.setHorizontalHeaderLabels([
            "Enable",
            "Category",
            "Validation ID",
            "Validation Check Name",
        ])
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.verticalHeader().setVisible(False)

        layout.addWidget(self.rules_table, stretch=1)

        # Rule counts label
        self.lbl_rules_count = QLabel("")
        self.lbl_rules_count.setStyleSheet(f"font-size: 11px; color: {colors['text_secondary']};")
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

        # Update category filter dropdown
        if hasattr(self, "combo_rule_category"):
            self.combo_rule_category.blockSignals(True)
            prev_cat = self.combo_rule_category.currentData() or "all"
            self.combo_rule_category.clear()
            self.combo_rule_category.addItem("Category: All", "all")
            used_cats = []
            for r in self._rules:
                ck = r.get("category") or get_rule_category(r.get("id", ""))
                if ck not in used_cats:
                    used_cats.append(ck)
            ordered_cats = [k for k in CBMS_MV_CATEGORIES.keys() if k in used_cats] + [k for k in used_cats if k not in CBMS_MV_CATEGORIES]
            for ck in ordered_cats:
                c_info = get_category_info(ck)
                c_count = sum(1 for r in self._rules if (r.get("category") or get_rule_category(r.get("id", ""))) == ck)
                c_icon = QgsApplication.getThemeIcon(c_info["icon"])
                self.combo_rule_category.addItem(c_icon if not c_icon.isNull() else QIcon(), f"{c_info['label']} ({c_count})", ck)
            idx = self.combo_rule_category.findData(prev_cat)
            if idx >= 0:
                self.combo_rule_category.setCurrentIndex(idx)
            self.combo_rule_category.blockSignals(False)

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

            # 1. Category
            cat_key = rule.get("category") or get_rule_category(val_id)
            cat_info = get_category_info(cat_key)
            item_cat = QTableWidgetItem(cat_info["label"])
            c_ic = QgsApplication.getThemeIcon(cat_info["icon"])
            if not c_ic.isNull():
                item_cat.setIcon(c_ic)
            item_cat.setData(Qt.UserRole, cat_key)
            item_cat.setFont(QFont("Segoe UI", 9))
            item_cat.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.rules_table.setItem(row, 1, item_cat)

            # 2. Validation ID
            item_id = QTableWidgetItem(val_id)
            item_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_id.setFont(QFont("Consolas", 9))
            self.rules_table.setItem(row, 2, item_id)

            # 3. Validation Check Name
            item_name = QTableWidgetItem(rule["name"])
            tooltip_text = f"{rule['name']}\n\n{rule['desc']}\n\nValidation ID: {val_id}\nCategory: {cat_info['label']}\nFile: {rule.get('file_path', '')}"
            item_name.setToolTip(tooltip_text)
            item_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.rules_table.setItem(row, 3, item_name)

        self.rules_table.blockSignals(False)
        self.rules_table.itemChanged.connect(self._on_rule_item_changed)

    def _on_rule_item_changed(self, item):
        """Handle checkbox changes in the rules table."""
        if item.column() == 0:
            self._update_rule_counts()
            self._save_rule_settings()

    def _filter_rules_table(self, *args):
        """Filter rows based on category selection and keyword search matching ID, Name, or Category."""
        search = self.edit_filter.text().strip().lower() if hasattr(self, "edit_filter") else ""
        sel_cat = self.combo_rule_category.currentData() if hasattr(self, "combo_rule_category") else "all"

        for row in range(self.rules_table.rowCount()):
            item_cat = self.rules_table.item(row, 1)
            item_id = self.rules_table.item(row, 2)
            item_name = self.rules_table.item(row, 3)
            if not (item_cat and item_id and item_name):
                continue

            cat_key = item_cat.data(Qt.UserRole) or ""
            match_cat = True
            if sel_cat and sel_cat != "all":
                match_cat = (cat_key == sel_cat)

            match_search = True
            if search:
                match_search = (
                    search in item_id.text().lower()
                    or search in item_name.text().lower()
                    or search in item_cat.text().lower()
                )

            show = match_cat and match_search
            self.rules_table.setRowHidden(row, not show)
        self._update_rule_counts()

    def _set_all_rules_checked(self, checked: bool):
        """Batch set all visible rules checked or unchecked."""
        state = Qt.Checked if checked else Qt.Unchecked
        self.rules_table.blockSignals(True)
        for row in range(self.rules_table.rowCount()):
            if not self.rules_table.isRowHidden(row):
                item = self.rules_table.item(row, 0)
                if item:
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
        visible = sum(
            1 for row in range(self.rules_table.rowCount())
            if not self.rules_table.isRowHidden(row)
        ) if hasattr(self, "rules_table") else total

        if visible < total:
            self.lbl_rules_count.setText(f"{enabled} of {total} validation rules enabled ({visible} matching filter)")
        else:
            self.lbl_rules_count.setText(f"{enabled} of {total} validation rules enabled")
        self.lbl_footer_status.setText(f"Ready • {enabled} validation rule(s) selected")
        if hasattr(self, "lbl_kpi_rules"):
            self.lbl_kpi_rules.setText(str(enabled))

    # -----------------------------------------------------------------------
    # Tab 3: Execution Logs
    # -----------------------------------------------------------------------
    def _create_tab_execution_logs(self) -> QWidget:
        """Create the Execution Logs tab with metrics, progress bar, and console."""
        colors = self._get_theme_colors()
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # KPI Cards Row
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.lbl_kpi_rules = self._create_kpi_card(kpi_layout, "Rules Queued", "0", colors["title"])
        self.lbl_kpi_flagged = self._create_kpi_card(kpi_layout, "Issues Flagged", "0", colors["danger_text"])
        self.lbl_kpi_layers = self._create_kpi_card(kpi_layout, "Result Layers", "0", colors["success_text"])

        layout.addLayout(kpi_layout)

        # Progress Section
        progress_box = QVBoxLayout()
        progress_box.setSpacing(4)

        self.lbl_progress_status = QLabel("Status: Idle — Ready to run validation")
        self.lbl_progress_status.setStyleSheet(f"font-weight: bold; font-size: 11px; color: {colors['title']};")
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
        log_title.setStyleSheet(f"font-weight: bold; color: {colors['title']};")
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

    def _create_kpi_card(
        self,
        parent_layout: QHBoxLayout,
        title: str,
        initial_val: str,
        color_hex: str,
        on_click: Optional[Callable] = None,
    ) -> QLabel:
        """Helper to create stylized KPI counter card with optional click-to-filter action."""
        card = QFrame()
        card.setObjectName("kpiCard")
        if on_click:
            card.setCursor(Qt.PointingHandCursor)
            card.mousePressEvent = lambda e: on_click()
            card.setToolTip(f"Click to filter by: {title}")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(10, 8, 10, 8)
        vbox.setSpacing(2)

        lbl_val = QLabel(initial_val)
        lbl_val.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {color_hex};")
        lbl_val.setAlignment(Qt.AlignCenter)

        colors = self._get_theme_colors()
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 9.5px; color: {colors['text_secondary']}; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;")
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
        colors = self._get_theme_colors()
        footer = QFrame()
        footer.setObjectName("bottomBar")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(10)

        self.lbl_footer_status = QLabel("Ready")
        self.lbl_footer_status.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 11px;")
        layout.addWidget(self.lbl_footer_status, stretch=1)

        self.btn_reset = QPushButton("Reset Form")
        ic_reset = QgsApplication.getThemeIcon("mActionUndo.svg")
        if not ic_reset.isNull():
            self.btn_reset.setIcon(ic_reset)
        self.btn_reset.clicked.connect(self._reset_form)
        layout.addWidget(self.btn_reset)

        self.btn_close = QPushButton("Close")
        ic_close = QgsApplication.getThemeIcon("mActionCancel.svg")
        if not ic_close.isNull():
            self.btn_close.setIcon(ic_close)
        self.btn_close.clicked.connect(self.close)
        layout.addWidget(self.btn_close)

        self.btn_run = QPushButton("  Run Validation  ")
        self.btn_run.setObjectName("btnRun")
        ic_run = QgsApplication.getThemeIcon("mActionStart.svg")
        if not ic_run.isNull():
            self.btn_run.setIcon(ic_run)
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
        colors = self._get_theme_colors()
        qss = f"""
            QDialog {{
                background-color: {colors['dialog_bg']};
                font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", sans-serif;
                font-size: 11.5px;
                color: {colors['text_primary']};
            }}
            QWidget {{
                font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", sans-serif;
                color: {colors['text_primary']};
            }}
            #topNavBar {{
                background-color: transparent;
                border: none;
            }}
            #btnHeaderConfig {{
                background-color: {colors['surface_elevated']};
                color: {colors['title']};
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 5px;
                border: 1px solid {colors['border']};
                font-size: 11px;
            }}
            QPushButton#btnHeaderConfig:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['accent']};
                border: 1px solid {colors['border_focus']};
            }}
            #btnDock {{
                background-color: {colors['surface_elevated']};
                color: {colors['title']};
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 5px;
                border: 1px solid {colors['border']};
                font-size: 11px;
            }}
            QPushButton#btnDock:hover {{
                background-color: {colors['surface_hover']};
                color: {colors['accent']};
                border: 1px solid {colors['border_focus']};
            }}
            QDockWidget {{
                font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", "Helvetica Neue", sans-serif;
                font-size: 11px;
                color: {colors['text_primary']};
                background-color: {colors['dialog_bg']};
            }}
            QDockWidget::title {{
                background-color: {colors['surface_elevated']};
                padding: 6px 10px;
                border-bottom: 1px solid {colors['border']};
                font-weight: bold;
                color: {colors['title']};
            }}
            #sectionGroup {{
                font-weight: 600;
                font-size: 12px;
                color: {colors['title']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                background-color: {colors['surface_bg']};
            }}
            #sectionGroup::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: {colors['title']};
            }}
            #kpiCard {{
                background-color: {colors['card_bg']};
                border: 1px solid {colors['border_subtle']};
                border-radius: 6px;
            }}
            #kpiCard:hover {{
                border-color: {colors['border']};
                background-color: {colors['card_hover_bg']};
            }}
            #validationProgressBar {{
                border: 1px solid {colors['border']};
                border-radius: 4px;
                text-align: center;
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                height: 18px;
                font-size: 10px;
                font-weight: 600;
            }}
            #validationProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {colors['accent']}, stop:1 {colors['title']});
                border-radius: 3px;
            }}
            #consoleLog {{
                background-color: {colors['console_bg']};
                color: {colors['console_text']};
                border: 1px solid {colors['console_border']};
                border-radius: 6px;
                padding: 8px;
                font-family: "Consolas", "Cascadia Code", monospace;
                font-size: 10.5px;
                line-height: 1.4;
            }}
            #btnRun {{
                background-color: {colors['accent']};
                color: #FFFFFF;
                font-weight: 600;
                padding: 7px 18px;
                border-radius: 5px;
                border: none;
                font-size: 11.5px;
            }}
            #btnRun:hover {{
                background-color: {colors['accent_hover']};
            }}
            #btnRun:pressed {{
                background-color: {colors['accent_pressed']};
            }}
            #btnRun:disabled {{
                background-color: {colors['disabled_bg']};
                color: {colors['disabled_text']};
            }}
            QTableWidget {{
                background-color: {colors['surface_bg']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                gridline-color: {colors['table_grid']};
                font-size: 11px;
                color: {colors['text_primary']};
            }}
            QTableWidget::item:selected {{
                background-color: {colors['selected_item_bg']};
                color: {colors['selected_item_text']};
            }}
            QHeaderView::section {{
                background-color: {colors['table_header_bg']};
                color: {colors['text_primary']};
                font-size: 11px;
                font-weight: 600;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid {colors['border']};
            }}
            QTabWidget::pane {{
                border: 1px solid {colors['border']};
                background-color: {colors['surface_bg']};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_secondary']};
                font-size: 11px;
                font-weight: 600;
                padding: 6px 16px;
                min-width: 90px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {colors['surface_bg']};
                color: {colors['title']};
                border: 1px solid {colors['border']};
                border-bottom-color: {colors['surface_bg']};
            }}
            #resultsTabWidget QTabBar::tab {{
                min-width: 100px;
                padding: 6px 16px;
            }}
            QTabBar QToolButton {{
                background-color: {colors['surface_elevated']};
                border: 1px solid {colors['border']};
                border-radius: 3px;
                margin: 2px;
                padding: 1px;
            }}
            QTabBar QToolButton:hover {{
                background-color: {colors['surface_hover']};
                border-color: {colors['border_focus']};
            }}
            QLineEdit {{
                font-size: 11px;
                padding: 4px 8px;
                border: 1px solid {colors['border']};
                border-radius: 4px;
                background-color: {colors['surface_bg']};
                color: {colors['text_primary']};
            }}
            QLineEdit:focus {{
                border-color: {colors['border_focus']};
            }}
            QPushButton {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                font-size: 11px;
                font-weight: 600;
                border-radius: 4px;
                padding: 5px 14px;
                min-width: 60px;
                min-height: 20px;
                outline: none;
            }}
            QPushButton:hover {{
                background-color: {colors['surface_hover']};
                border-color: {colors['border_focus']};
                color: {colors['title']};
            }}
            QPushButton:pressed {{
                background-color: {colors['border']};
            }}
            QPushButton:focus {{
                border-color: {colors['border_focus']};
            }}
            QPushButton:disabled {{
                background-color: {colors['disabled_bg']};
                color: {colors['disabled_text']};
                border-color: {colors['disabled_border']};
            }}
            QMessageBox {{
                background-color: {colors['surface_bg']};
            }}
            QMessageBox QLabel {{
                color: {colors['text_primary']};
                font-size: 11.5px;
            }}
            QMessageBox QPushButton, QDialogButtonBox QPushButton {{
                background-color: {colors['surface_elevated']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border']};
                border-radius: 4px;
                padding: 5px 18px;
                min-width: 70px;
                min-height: 22px;
                font-size: 11px;
                font-weight: 600;
                outline: none;
            }}
            QMessageBox QPushButton:hover, QDialogButtonBox QPushButton:hover {{
                background-color: {colors['surface_hover']};
                border-color: {colors['border_focus']};
                color: {colors['title']};
            }}
            QMessageBox QPushButton:pressed, QDialogButtonBox QPushButton:pressed {{
                background-color: {colors['border']};
            }}
            QMessageBox QPushButton:focus, QDialogButtonBox QPushButton:focus {{
                border-color: {colors['border_focus']};
            }}
            QMessageBox QPushButton:default, QDialogButtonBox QPushButton:default {{
                background-color: {colors['accent']};
                color: #FFFFFF;
                border: 1px solid {colors['accent_hover']};
                font-weight: bold;
            }}
            QMessageBox QPushButton:default:hover, QDialogButtonBox QPushButton:default:hover {{
                background-color: {colors['accent_hover']};
                color: #FFFFFF;
            }}
            QMessageBox QPushButton:default:pressed, QDialogButtonBox QPushButton:default:pressed {{
                background-color: {colors['accent_pressed']};
                color: #FFFFFF;
            }}
            QGroupBox {{
                font-weight: 600;
                border: 1px solid {colors['border']};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                background-color: {colors['surface_bg']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: {colors['title']};
            }}
            QRadioButton, QCheckBox {{
                color: {colors['text_primary']};
                spacing: 6px;
            }}
        """
        self.setStyleSheet(qss)
        if getattr(self, "_dock_widget", None):
            self._dock_widget.setStyleSheet(qss)

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
                QMessageBox.critical(self, "Save Failed", f"Could not save the log file:\n{e}")

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
        try:
            reg_alg = QgsApplication.processingRegistry().algorithmById(f"gmd_pipeline:{val_id}")
            if reg_alg:
                alg = reg_alg.createInstance()
        except Exception:
            alg = None

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
        self._user_toggled_load_inputs = False

    # -----------------------------------------------------------------------
    # Execution Logic: Iterating Selected Algorithms
    # -----------------------------------------------------------------------
    def run_validation(
        self,
        checked: bool = False,
        auto_rerun: bool = False,
        resolved_val_id: Optional[str] = None,
        saved_msg: str = "",
    ):
        """
        Execute the validation pipeline by iterating through the enabled
        algorithms in gmd_scripts/cbms_mv and passing the three standardized
        Input Data Sources.
        """
        if processing is None:
            QMessageBox.critical(
                self,
                "Cannot Run Checks",
                "The QGIS Processing tools are not available. Please enable the Processing plugin in QGIS.",
            )
            return

        form2_path = self.file_form2.filePath().strip()
        points_path = self.file_points.filePath().strip()
        base_path = self.file_base.filePath().strip()

        # 1. Verify primary file inputs
        if not form2_path:
            QMessageBox.warning(
                self,
                "Form 2 File Missing",
                "Please choose the Form 2 data file in the 'Data Config' tab.",
            )
            self._switch_to_config(0)
            return

        if not points_path:
            QMessageBox.warning(
                self,
                "Building Points File Missing",
                "Please choose the Building Points file in the 'Data Config' tab.",
            )
            self._switch_to_config(0)
            return

        if not os.path.exists(form2_path):
            QMessageBox.critical(
                self,
                "File Not Found",
                f"The Form 2 data file could not be found:\n{form2_path}",
            )
            self._switch_to_config(0)
            return

        if not os.path.exists(points_path):
            QMessageBox.critical(
                self,
                "File Not Found",
                f"The Building Points file could not be found:\n{points_path}",
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
                "No Checks Selected",
                "Please tick at least one check in the 'Validation Rules' tab.",
            )
            self._switch_to_config(1)
            return

        # 3. Check Base Layer dependency
        rules_requiring_base = [r for r in selected_rules if r["has_base"]]
        if rules_requiring_base and (not base_path or not os.path.exists(base_path)):
            if not auto_rerun:
                rule_list = "\n".join(f"  • [{r['id']}] {r['name']}" for r in rules_requiring_base)
                reply = QMessageBox.question(
                    self,
                    "Base Layers File Missing",
                    f"These {len(rules_requiring_base)} check(s) need the Base Layers file:\n\n"
                    f"{rule_list}\n\n"
                    f"Do you want to continue and skip these {len(rules_requiring_base)} check(s)?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    self._switch_to_config(0)
                    return

            selected_rules = [r for r in selected_rules if not r["has_base"]]
            if not selected_rules:
                if not auto_rerun:
                    QMessageBox.warning(
                        self,
                        "No Checks to Run",
                        "All selected checks need the Base Layers file. Please choose the Base Layers file to continue.",
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
        ensure_processing_initialized()
        self.context = QgsProcessingContext()
        self.context.setProject(self.project or QgsProject.instance())
        feedback = ProcessingFeedbackBridge(self._log_info, self._log_warning, self._log_error)

        # Load primary input data sources into QGIS Layers Panel if requested by user
        self._load_primary_input_sources_if_requested(form2_path, points_path, base_path)

        # Remove existing '2027 CBMS MV Results' group to prevent stale error layers
        if self.should_group_layers:
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

            # Prefer direct alg instance execution to avoid registry SIP/createInstance lookup issues;
            # fall back to registered string ID if direct instance was not loaded.
            alg_target = alg if alg is not None else reg_id

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
                    if self.should_load_canvas:
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

                        if self.should_group_layers:
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
                    if self.should_load_canvas:
                        if hasattr(self.context, "takeResultLayer"):
                            try:
                                take_aux = self.context.takeResultLayer(aux_dest if isinstance(aux_dest, str) else aux_layer.id())
                                if take_aux and take_aux.isValid():
                                    aux_layer = take_aux
                            except Exception:
                                pass

                        aux_layer.setName(f"{val_id}_summary ({aux_layer.featureCount()})")
                        proj = self.project if self.project else QgsProject.instance()

                        if self.should_group_layers:
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
            report_dir = r"C:\PSA-GIS\UAT Logs"
            try:
                os.makedirs(report_dir, exist_ok=True)
            except Exception:
                report_dir = os.path.dirname(points_path) if points_path and os.path.exists(os.path.dirname(points_path)) else tempfile.gettempdir()

            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            report_path = os.path.join(report_dir, f"cbms_mv_summary_{ts}.json")
            csv_path = os.path.join(report_dir, f"cbms_mv_summary_{ts}.csv")
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

                with open(csv_path, "w", newline="", encoding="utf-8-sig") as cf:
                    writer = csv.writer(cf)
                    writer.writerow(["Check ID", "Check Name", "Status", "Flagged Count"])
                    for row in execution_summary:
                        writer.writerow([
                            row.get("id", ""),
                            row.get("name", ""),
                            row.get("status", ""),
                            row.get("features_flagged", 0),
                        ])
                    writer.writerow([])
                    writer.writerow(["Total Checks Run", len(execution_summary)])
                    writer.writerow(["Total Flagged Issues", total_flagged_issues])

                self._log_success(f"Audit report saved to: {report_path}")
                self._log_success(f"Summary CSV saved to: {csv_path}")
            except Exception as r_exc:
                self._log_warning(f"Could not write audit report file: {r_exc}")

        self.lbl_footer_status.setText(f"Validation complete • {total_flagged_issues:,} issue(s) flagged")

        if auto_rerun:
            msg_lines = []
            if saved_msg:
                msg_lines.append(saved_msg)
            if resolved_val_id:
                msg_lines.append(
                    f"All issues for '{resolved_val_id}' are now resolved (0 remaining)."
                )
            if total_flagged_issues == 0:
                msg_lines.append(
                    "Full validation was re-run: 0 issues remaining across all enabled checks."
                )
            else:
                msg_lines.append(
                    f"Full validation was re-run to update the summary:\n"
                    f"{total_flagged_issues:,} total issue(s) remaining across {total_output_layers} check(s)."
                )
            QMessageBox.information(
                self,
                "All Issues Resolved — Summary Updated",
                "\n\n".join(msg_lines),
            )
