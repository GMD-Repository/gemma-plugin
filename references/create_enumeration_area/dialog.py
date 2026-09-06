# -*- coding: utf-8 -*-
"""
EA Delineation and Merging -- Custom Processing UI Dialog
---------------------------------------------------------
Provides a comprehensive custom user interface for the EA Delineation and Merging
processing workflow. Houses three main tabs:
  Tab 1 — EA Preprocessing         : clips EAs to their Barangay and fills coverage gaps.
  Tab 2 — Create Enumeration Areas : existing EA delineation and merging algorithm.
  Tab 3 — Enumeration Area Merge   : updates previous EAs with 8-digit replacement polygons.

Adapts to dynamic light and dark themes (defaulting to white) and features validation
indicators, layer auto-detection, KPI cards, candidate table filters, and a stylized
console interface.
"""

import os
import re
import math
from qgis.core import (
    Qgis, QgsMessageLog,
    QgsApplication, QgsProject, QgsVectorLayer, QgsCoordinateTransform, QgsSpatialIndex,
    QgsFeature, QgsField, QgsGeometry, QgsProcessingContext, QgsProcessingFeedback,
    QgsCoordinateReferenceSystem, QgsWkbTypes, NULL, QgsMapLayerProxyModel
)
try:
    from qgis.gui import QgsMapLayerComboBox, QgsProjectionSelectionWidget, QgsCollapsibleGroupBox, QgsFileWidget
except ImportError:
    from qgis.gui import QgsMapLayerComboBox, QgsProjectionSelectionWidget, QgsFileWidget
    QgsCollapsibleGroupBox = QGroupBox
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QSpacerItem, QWidget, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QLineEdit, QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTextEdit, QScrollArea, QSplitter, QGridLayout,
    QTextBrowser, QMessageBox, QGroupBox, QToolButton, QListWidget, QListWidgetItem,
    QDialogButtonBox, QAbstractItemView
)
from qgis.PyQt.QtGui import QFont, QPixmap, QColor, QIcon, QTextCursor
from qgis.PyQt.QtCore import Qt, QSize, QCoreApplication, QThread, QObject, pyqtSignal, QVariant, QTimer

# Module-level regex for Tab 3 input validation — compiled once, reused on every
# combo-box change event instead of being re-compiled inside the hot-path method.
_EA_MERGE_8DIGIT_RE = re.compile(r"^\d{8}(_|$)")

# Tab 3 processor helpers — imported once at module load so that
# _ea_merge_validate_inputs (called on every combo-box change) does not
# re-execute a relative import on each invocation.
try:
    from .ea_merge_processor import (
        _field_index_ci as _emg_field_index_ci,
        _first_nonempty_value as _emg_first_nonempty_value,
        _unique_values as _emg_unique_values,
        _GEOCODE_FIELDS as _EMG_GEOCODE_FIELDS,
        _CITYMUN_FIELDS as _EMG_CITYMUN_FIELDS,
    )
except Exception:
    # Fallback stubs in case the module is loaded before the package is fully
    # initialized (e.g. during plugin reload).
    _emg_field_index_ci = None
    _emg_first_nonempty_value = None
    _emg_unique_values = None
    _EMG_GEOCODE_FIELDS = ()
    _EMG_CITYMUN_FIELDS = ()


class ThreadSafeFeedbackHelper(QObject):
    """Helper QObject to marshal GUI updates back to the main thread."""
    append_html = pyqtSignal(str)
    set_val = pyqtSignal(int)

    def __init__(self, log_widget, progress_bar):
        super().__init__()
        self.log_widget = log_widget
        self.progress_bar = progress_bar
        self.append_html.connect(self._on_append_html)
        self.set_val.connect(self._on_set_val)

    def _on_append_html(self, html):
        self.log_widget.append(html)
        self.log_widget.ensureCursorVisible()

    def _on_set_val(self, val):
        self.progress_bar.setValue(val)


class _EAMergeWorker(QObject):
    """Runs EAMergeProcessor.run() in a background QThread.

    All signals are emitted from the worker thread. Because cross-thread
    signal-slot connections default to Qt.QueuedConnection, the connected
    slots (which update Qt widgets) are automatically marshalled back and
    executed on the main GUI thread — so no manual locking is required.
    """
    feedback_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(object)  # payload: EAMergeResult

    def __init__(self):
        super().__init__()
        self._processor = None

    def set_processor(self, processor):
        """Attach the processor after signals are wired up."""
        self._processor = processor

    def run(self):
        """Entry point called by QThread.started signal."""
        try:
            result = self._processor.run()
        except Exception as exc:
            import traceback
            from .ea_merge_processor import EAMergeResult, EAMergeSummary
            result = EAMergeResult(
                success=False,
                error_message=str(exc),
                summary=EAMergeSummary(overall_status="ERROR"),
            )
            result.log_lines.append(f"[ERROR] {exc}")
            result.log_lines.append(traceback.format_exc())
        self.finished_signal.emit(result)

class CustomProcessingFeedback(QgsProcessingFeedback):
    """Subclass of QgsProcessingFeedback to route progress and log updates to custom UI elements."""
    
    def __init__(self, progress_bar, log_widget, run_button, cancel_button):
        super().__init__()
        self.progress_bar = progress_bar
        self.log_widget = log_widget
        self.run_button = run_button
        self.cancel_button = cancel_button
        self.is_cancelled = False
        
        # Helper to marshal GUI thread updates safely from worker threads
        self.helper = ThreadSafeFeedbackHelper(log_widget, progress_bar)
        
        if self.cancel_button:
            self.cancel_button.clicked.connect(self.cancel)

    def setProgress(self, progress):
        self.helper.set_val.emit(int(progress))
        super().setProgress(progress)

    def pushInfo(self, info):
        # Handle formatted HTML tables cleanly
        if isinstance(info, str) and info.startswith("<html_table>") and info.endswith("</html_table>"):
            clean_html = info[12:-13]
            self.helper.append_html.emit(clean_html)
            if QThread.currentThread() == QCoreApplication.instance().thread():
                QCoreApplication.processEvents()
            return

        # Strip any existing leading bracket tag if present to avoid duplication
        clean_text = info
        if clean_text.startswith("[INFO] "):
            clean_text = clean_text[7:]
        elif clean_text.startswith("[WARN] "):
            clean_text = clean_text[7:]
        elif clean_text.startswith("[WARNING] "):
            clean_text = clean_text[10:]
        elif clean_text.startswith("[SUCCESS] "):
            clean_text = clean_text[10:]

        info_lower = info.lower()
        badge = "<span style='color: #0969da; font-weight: bold;'>[INFO]</span>"

        if info.startswith("[WARN]") or info.startswith("[WARNING]") or "warning" in info_lower:
            badge = "<span style='color: #d17a00; font-weight: bold;'>[WARNING]</span>"
        elif "success" in info_lower or "complete" in info_lower or "done" in info_lower:
            badge = "<span style='color: #1a7f37; font-weight: bold;'>[SUCCESS]</span>"

        self.helper.append_html.emit(f"{badge} {clean_text}")
        if QThread.currentThread() == QCoreApplication.instance().thread():
            QCoreApplication.processEvents()

    def reportError(self, error, fatal=False):
        self.helper.append_html.emit(f"<span style='color:#cf222e; font-weight:bold;'>[ERROR] {error}</span>")
        if QThread.currentThread() == QCoreApplication.instance().thread():
            QCoreApplication.processEvents()

    def setProgressText(self, text):
        self.helper.append_html.emit(f"<span style='color:#0969da; font-style:italic;'>[STAGE] {text}</span>")
        if QThread.currentThread() == QCoreApplication.instance().thread():
            QCoreApplication.processEvents()

    def isCanceled(self):
        return self.is_cancelled

    def cancel(self):
        self.is_cancelled = True
        self.helper.append_html.emit("<span style='color:#d17a00; font-weight:bold;'>[CANCEL] Cancellation requested by user...</span>")


class EALauncherDialog(QDialog):
    """Comprehensive Processing UI for EA Delineation and Merging."""

    ALGORITHM_ID = "gmd_pipeline:createea"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EA Delineation and Merging")
        icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "create_ea.svg")
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setMinimumSize(1150, 700)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowTitleHint
        )

        self.feedback = None

        # Pre-EA processing worker reference (QgsTask)
        self._pre_ea_task = None

        # Initialize algorithm instance for help text metadata
        from .algorithm import CreateEAAlgorithm
        self.algo = CreateEAAlgorithm()

        # Candidate lists storage for live search/filter
        self.all_delineation_candidates = []
        self.all_merge_candidates = []

        # Detect QGIS theme (light or dark) based on application palette brightness
        palette = self.palette()
        bg_color = palette.color(palette.Window)
        self.current_theme = "dark" if bg_color.lightness() < 128 else "light"

        self._build_ui()

        # Connect signals for live candidate previews and validators
        self._setup_preview_connections()


    # ── Lifecycle Overrides ──────────────────────────────────────────────────

    def showEvent(self, event):
        """Refreshes all inputs, processes, and results every time the dialog is shown.

        Ensures that whenever the user opens or re-opens the plugin dialog, all
        inputs (layers auto-detected from the active project, default parameters),
        process states (progress bars, cancel/run button states, status banners),
        and results information (results tables, KPI cards, candidate lists,
        summaries, and logs) across all three tabs are completely refreshed.
        """
        super().showEvent(event)
        self.refresh_all()

    def refresh_all(self):
        """Refresh and reset all inputs, processes, and results information across all 3 tabs."""
        self._pre_ea_refresh()
        self._create_ea_refresh()
        self._ea_merge_refresh()

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        """Build the root layout containing the top-level header and tab widget."""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Top Header Row (Title & Subtitle on left, Description Toggle button on right)
        header_container = QHBoxLayout()
        header_container.setContentsMargins(0, 0, 0, 0)
        header_container.setSpacing(8)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_label = QLabel("EA Delineation and Merging")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #2C3E50; padding: 0;")
        text_layout.addWidget(title_label)

        sub_label = QLabel("Step-by-step workflow to prepare boundary layers, create enumeration areas, and merge replacement EA geometries.")
        sub_label.setWordWrap(True)
        sub_label.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        text_layout.addWidget(sub_label)

        header_container.addLayout(text_layout, 1)

        # Unified Description Toggle Button in Top Header
        show_icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "show_description.svg")
        )
        hide_icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "hide_description.svg")
        )
        self.toggle_desc_btn = QToolButton()
        self.toggle_desc_btn.setIcon(
            QIcon(hide_icon_path) if os.path.exists(hide_icon_path)
            else QgsApplication.getThemeIcon("/mActionHideAllLayers.svg")
        )
        self.toggle_desc_btn.setIconSize(QSize(20, 20))
        self.toggle_desc_btn.setFixedSize(28, 28)
        self.toggle_desc_btn.setToolTip("Show / Hide Description Panel")
        self.toggle_desc_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_desc_btn.setStyleSheet("""
            QToolButton {
                border: none;
                background-color: transparent;
                padding: 2px;
                border-radius: 4px;
            }
            QToolButton:hover {
                background-color: rgba(140, 149, 159, 0.2);
            }
        """)
        self.toggle_desc_btn.clicked.connect(self._toggle_current_tab_description)
        header_container.addWidget(self.toggle_desc_btn, 0, Qt.AlignVCenter)

        # Backwards-compatibility aliases
        self.pre_ea_toggle_desc_btn = self.toggle_desc_btn
        self.toggle_help_btn = self.toggle_desc_btn

        root.addLayout(header_container)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #BDC3C7;")
        root.addWidget(line)

        # Top-level tab widget: Tab 1 = EA Preprocessing, Tab 2 = Create Enumeration Areas, Tab 3 = Enumeration Area Merge
        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")
        self.main_tabs.tabBar().setElideMode(Qt.ElideNone)
        self.main_tabs.setStyleSheet("""
            QTabWidget#mainTabs > QTabBar::tab {
                font-weight: bold;
                font-size: 12px;
                min-width: 180px;
                padding: 10px 24px;
                margin-right: 2px;
                background-color: #EAEDED;
                color: #2C3E50;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabWidget#mainTabs > QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #2980B9;
                border-bottom: 3px solid #3498DB;
            }
            QTabWidget#mainTabs > QTabBar::tab:hover:!selected {
                background-color: #D5D8DC;
            }
        """)

        self._build_pre_ea_tab()
        self._build_create_ea_tab()
        self._build_ea_merge_tab()

        self.main_tabs.currentChanged.connect(self._on_main_tab_changed)

        root.addWidget(self.main_tabs, stretch=1)

    def _toggle_current_tab_description(self):
        """Toggle the description panel for whichever main tab is currently active."""
        idx = self.main_tabs.currentIndex()
        if idx == 0:
            self._pre_ea_toggle_description()
        elif idx == 1:
            self.toggle_help()
        elif idx == 2:
            self._ea_merge_toggle_description()

    def _on_main_tab_changed(self, index):
        """Update toggle button icon state when switching tabs."""
        show_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "icons", "show_description.svg"))
        hide_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "icons", "hide_description.svg"))
        
        if index == 0:
            is_vis = self.pre_ea_desc_panel.isVisible()
        elif index == 1:
            is_vis = self.help_panel.isVisible()
        elif index == 2:
            is_vis = self.ea_merge_desc_panel.isVisible() if hasattr(self, 'ea_merge_desc_panel') else False
            self._ea_merge_auto_detect_ea_layer()
        else:
            is_vis = False

        self.toggle_desc_btn.setEnabled(True)

        if is_vis:
            self.toggle_desc_btn.setIcon(QIcon(hide_icon))
            self.toggle_desc_btn.setToolTip("Hide Description Panel")
        else:
            self.toggle_desc_btn.setIcon(QIcon(show_icon))
            self.toggle_desc_btn.setToolTip("Show Description Panel")

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 1 — EA Preprocessing
    # ─────────────────────────────────────────────────────────────────────────

    def _build_pre_ea_tab(self):
        """Build the EA Preprocessing tab (Tab 1) and add it to main_tabs."""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(6, 6, 6, 6)
        tab_layout.setSpacing(6)

        # ── Main Splitter: left (inputs+options) / right (results+log) ────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("preEaSplitter")

        # ── LEFT PANEL ──────────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)
        left_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)

        # ── Input Layers Group ───────────────────────────────────────────
        inputs_group = QGroupBox("Input Layers")
        inputs_layout = QVBoxLayout(inputs_group)
        inputs_layout.setContentsMargins(8, 8, 8, 8)
        inputs_layout.setSpacing(6)

        self.pre_ea_detect_btn = QPushButton("Auto-detect Layers")
        self.pre_ea_detect_btn.setToolTip(
            "Scan project layers and auto-select Barangay (*_bgy) and EA (*_ea / *_ea2024) layers."
        )
        self.pre_ea_detect_btn.clicked.connect(self._pre_ea_auto_detect_layers)
        inputs_layout.addWidget(self.pre_ea_detect_btn)

        # Barangay Layer
        inputs_layout.addWidget(QLabel("Barangay Layer (Polygon)*"))
        self.pre_ea_bgy_combo = QgsMapLayerComboBox()
        self.pre_ea_bgy_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.pre_ea_bgy_combo.setAllowEmptyLayer(True)
        self.pre_ea_bgy_combo.setLayer(None)
        inputs_layout.addWidget(self.pre_ea_bgy_combo)
        self.pre_ea_bgy_status_lbl = QLabel("No layer selected.")
        self.pre_ea_bgy_status_lbl.setWordWrap(True)
        inputs_layout.addWidget(self.pre_ea_bgy_status_lbl)

        # EA Layer
        inputs_layout.addWidget(QLabel("EA Layer (Polygon, Optional)"))
        self.pre_ea_ea_combo = QgsMapLayerComboBox()
        self.pre_ea_ea_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.pre_ea_ea_combo.setAllowEmptyLayer(True)
        self.pre_ea_ea_combo.setLayer(None)
        inputs_layout.addWidget(self.pre_ea_ea_combo)
        self.pre_ea_ea_status_lbl = QLabel("No layer selected.")
        self.pre_ea_ea_status_lbl.setWordWrap(True)
        inputs_layout.addWidget(self.pre_ea_ea_status_lbl)

        # Designated Output Folder
        inputs_layout.addWidget(QLabel("Designated Output Folder*"))
        self.pre_ea_output_folder_widget = QgsFileWidget()
        self.pre_ea_output_folder_widget.setStorageMode(QgsFileWidget.GetDirectory)
        self.pre_ea_output_folder_widget.setDialogTitle("Designate Output Folder for EA Preprocessing")
        inputs_layout.addWidget(self.pre_ea_output_folder_widget)
        self.pre_ea_output_folder_widget.fileChanged.connect(self._pre_ea_validate_inputs)

        # Connect validation
        self.pre_ea_bgy_combo.currentIndexChanged.connect(self._pre_ea_validate_inputs)
        self.pre_ea_ea_combo.currentIndexChanged.connect(self._pre_ea_validate_inputs)

        scroll_layout.addWidget(inputs_group)

        # ── Processing Options Group ─────────────────────────────────────
        options_group = QGroupBox("Processing Options")
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(8, 8, 8, 8)
        options_layout.setSpacing(6)

        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("Gap Area Tolerance (m\u00b2):"))
        self.pre_ea_gap_tol_spin = QDoubleSpinBox()
        self.pre_ea_gap_tol_spin.setRange(0.0, 100000.0)
        self.pre_ea_gap_tol_spin.setDecimals(2)
        self.pre_ea_gap_tol_spin.setValue(1.0)
        self.pre_ea_gap_tol_spin.setToolTip(
            "Gaps smaller than this area (in m\u00b2) are treated as geometry precision artifacts "
            "and ignored. Set to 0 to process all gaps."
        )
        tol_row.addWidget(self.pre_ea_gap_tol_spin)
        options_layout.addLayout(tol_row)

        self.pre_ea_clip_chk = QCheckBox("Clip EA to Barangay Boundary")
        self.pre_ea_clip_chk.setChecked(True)
        self.pre_ea_clip_chk.setToolTip(
            "Remove any EA area that extends outside its parent Barangay polygon."
        )
        options_layout.addWidget(self.pre_ea_clip_chk)

        self.pre_ea_resolve_overlaps_chk = QCheckBox("Resolve EA Overlaps")
        self.pre_ea_resolve_overlaps_chk.setChecked(True)
        self.pre_ea_resolve_overlaps_chk.setToolTip(
            "Detect and eliminate overlapping polygon regions between adjacent EAs within each Barangay."
        )
        options_layout.addWidget(self.pre_ea_resolve_overlaps_chk)

        self.pre_ea_detect_gaps_chk = QCheckBox("Detect Uncovered Barangay Areas")
        self.pre_ea_detect_gaps_chk.setChecked(True)
        self.pre_ea_detect_gaps_chk.setToolTip(
            "After clipping, calculate the area within each Barangay not covered by any EA."
        )
        options_layout.addWidget(self.pre_ea_detect_gaps_chk)

        self.pre_ea_assign_gaps_chk = QCheckBox("Assign Gaps to Contiguous EA")
        self.pre_ea_assign_gaps_chk.setChecked(True)
        self.pre_ea_assign_gaps_chk.setToolTip(
            "Merge each uncovered area into the adjacent EA that shares the longest boundary with it."
        )
        options_layout.addWidget(self.pre_ea_assign_gaps_chk)

        scroll_layout.addWidget(options_group)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        left_widget.setMinimumWidth(300)
        splitter.addWidget(left_widget)

        # ── RIGHT PANEL ─────────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(8)

        self.pre_ea_right_tabs = QTabWidget()
        self.pre_ea_right_tabs.setObjectName("preEaRightTabs")
        right_tabs = self.pre_ea_right_tabs

        # ── Results Tab ─────────────────────────────────────────────────
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        results_layout.setContentsMargins(6, 6, 6, 6)
        results_layout.setSpacing(6)

        self.pre_ea_results_table = QTableWidget()
        self.pre_ea_results_table.setObjectName("preEaResultsTable")
        self.pre_ea_results_table.setColumnCount(7)
        self.pre_ea_results_table.setHorizontalHeaderLabels(
            ["Barangay", "EA", "Original Area (m\u00b2)", "Corrected Area (m\u00b2)",
             "Area Change (m\u00b2)", "Action", "Status"]
        )
        self.pre_ea_results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.pre_ea_results_table.horizontalHeader().setStretchLastSection(True)
        self.pre_ea_results_table.verticalHeader().setVisible(False)
        self.pre_ea_results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.pre_ea_results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.pre_ea_results_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.pre_ea_results_table)

        right_tabs.addTab(results_tab, "Processing Results")

        # ── Summary Tab ─────────────────────────────────────────────────
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(8)

        summary_title = QLabel("EA Preprocessing Summary")
        summary_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        summary_layout.addWidget(summary_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        summary_layout.addWidget(sep)

        summary_grid = QGridLayout()
        summary_grid.setSpacing(4)
        summary_grid.setColumnStretch(1, 1)

        def _add_summary_row(label_text, row_idx):
            lbl = QLabel(label_text)
            val = QLabel("-")
            val.setFont(QFont("Segoe UI", 9, QFont.Bold))
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            summary_grid.addWidget(lbl, row_idx, 0)
            summary_grid.addWidget(val, row_idx, 1)
            return val

        self._pre_ea_sum_bgy_val = _add_summary_row("Barangays Processed:", 0)
        self._pre_ea_sum_ea_val = _add_summary_row("EAs Processed:", 1)
        self._pre_ea_sum_corr_val = _add_summary_row("EAs Requiring Correction:", 2)
        self._pre_ea_sum_clip_val = _add_summary_row("EAs Clipped:", 3)
        self._pre_ea_sum_gaps_det_val = _add_summary_row("Gaps Detected:", 4)
        self._pre_ea_sum_gaps_asgn_val = _add_summary_row("Gaps Assigned:", 5)
        self._pre_ea_sum_unres_val = _add_summary_row("Unresolved Gaps:", 6)
        self._pre_ea_sum_outside_val = _add_summary_row("Final EAs Outside Bgy:", 7)
        self._pre_ea_sum_uncov_val = _add_summary_row("Final Uncovered Area (m\u00b2):", 8)
        self._pre_ea_sum_output_val = _add_summary_row("Output:", 9)

        summary_layout.addLayout(summary_grid)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        summary_layout.addWidget(sep2)

        self._pre_ea_sum_status_lbl = QLabel("Status: -")
        self._pre_ea_sum_status_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        summary_layout.addWidget(self._pre_ea_sum_status_lbl)
        summary_layout.addStretch()

        right_tabs.addTab(summary_tab, "Summary")

        # ── Log Tab ─────────────────────────────────────────────────────
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(6, 6, 6, 6)
        log_layout.setSpacing(4)

        log_controls = QHBoxLayout()
        log_controls.addWidget(QLabel("Processing Log:"))
        log_controls.addStretch()
        self.pre_ea_copy_log_btn = QPushButton("Copy Log")
        self.pre_ea_copy_log_btn.setToolTip("Copy processing log to clipboard.")
        self.pre_ea_copy_log_btn.clicked.connect(self._pre_ea_copy_log)
        log_controls.addWidget(self.pre_ea_copy_log_btn)
        self.pre_ea_clear_log_btn = QPushButton("Clear")
        self.pre_ea_clear_log_btn.setToolTip("Clear the processing log.")
        self.pre_ea_clear_log_btn.clicked.connect(lambda: self.pre_ea_log_console.clear())
        log_controls.addWidget(self.pre_ea_clear_log_btn)
        log_layout.addLayout(log_controls)

        self.pre_ea_log_console = QTextEdit()
        self.pre_ea_log_console.setObjectName("preEaLogConsole")
        self.pre_ea_log_console.setReadOnly(True)
        log_layout.addWidget(self.pre_ea_log_console)

        right_tabs.addTab(log_tab, "Processing Log")

        right_layout.addWidget(right_tabs)
        right_widget.setMinimumWidth(480)
        splitter.addWidget(right_widget)

        # ── Description Panel (third splitter pane) ──────────────────────
        self.pre_ea_desc_panel = QWidget()
        desc_panel_layout = QVBoxLayout(self.pre_ea_desc_panel)
        desc_panel_layout.setContentsMargins(4, 4, 4, 4)
        desc_panel_layout.setSpacing(0)

        self.pre_ea_desc_browser = QTextBrowser()
        self.pre_ea_desc_browser.setObjectName("preEaDescBrowser")
        self.pre_ea_desc_browser.setOpenExternalLinks(True)
        self.pre_ea_desc_browser.setHtml(self._pre_ea_help_html())
        desc_panel_layout.addWidget(self.pre_ea_desc_browser)

        self.pre_ea_desc_panel.setMinimumWidth(240)
        splitter.addWidget(self.pre_ea_desc_panel)
        splitter.setSizes([310, 640, 260])

        tab_layout.addWidget(splitter, 1)

        # ── Bottom Bar ───────────────────────────────────────────────────
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(10, 4, 10, 6)
        bottom_layout.setSpacing(4)

        self.pre_ea_status_banner = QLabel("Ready.")
        self.pre_ea_status_banner.setWordWrap(True)
        self.pre_ea_status_banner.setFont(QFont("Segoe UI", 9, QFont.Bold))
        bottom_layout.addWidget(self.pre_ea_status_banner)

        controls_row = QHBoxLayout()
        self.pre_ea_progress_bar = QProgressBar()
        self.pre_ea_progress_bar.setRange(0, 100)
        self.pre_ea_progress_bar.setValue(0)
        self.pre_ea_progress_bar.setFixedHeight(26)
        controls_row.addWidget(self.pre_ea_progress_bar)

        self.pre_ea_cancel_btn = QPushButton("Cancel")
        self.pre_ea_cancel_btn.setMinimumWidth(80)
        self.pre_ea_cancel_btn.setFixedHeight(26)
        self.pre_ea_cancel_btn.setEnabled(False)
        self.pre_ea_cancel_btn.clicked.connect(self._pre_ea_cancel)
        controls_row.addWidget(self.pre_ea_cancel_btn)

        self.pre_ea_run_btn = QPushButton("Run")
        self.pre_ea_run_btn.setMinimumWidth(120)
        self.pre_ea_run_btn.setFixedHeight(26)
        self.pre_ea_run_btn.clicked.connect(self._pre_ea_run)
        controls_row.addWidget(self.pre_ea_run_btn)

        bottom_layout.addLayout(controls_row)
        tab_layout.addWidget(bottom)

        self.main_tabs.addTab(tab_widget, "EA Preprocessing")

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 1 — EA Preprocessing Slots & Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def _pre_ea_refresh(self):
        """Reset and refresh Tab 1 (EA Preprocessing) inputs, processes, and results."""
        # 1. Reset inputs & options to default
        if hasattr(self, 'pre_ea_bgy_combo'):
            self.pre_ea_bgy_combo.setLayer(None)
        if hasattr(self, 'pre_ea_ea_combo'):
            self.pre_ea_ea_combo.setLayer(None)
        if hasattr(self, 'pre_ea_output_folder_widget'):
            self.pre_ea_output_folder_widget.setFilePath("")
        if hasattr(self, 'pre_ea_gap_tol_spin'):
            self.pre_ea_gap_tol_spin.setValue(1.0)
        if hasattr(self, 'pre_ea_clip_chk'):
            self.pre_ea_clip_chk.setChecked(True)
        if hasattr(self, 'pre_ea_resolve_overlaps_chk'):
            self.pre_ea_resolve_overlaps_chk.setChecked(True)
        if hasattr(self, 'pre_ea_detect_gaps_chk'):
            self.pre_ea_detect_gaps_chk.setChecked(True)
        if hasattr(self, 'pre_ea_assign_gaps_chk'):
            self.pre_ea_assign_gaps_chk.setChecked(True)

        # 2. Re-detect project layers
        self._pre_ea_auto_detect_layers()

        # 3. Reset process states
        if hasattr(self, 'pre_ea_progress_bar'):
            self.pre_ea_progress_bar.setValue(0)
        if hasattr(self, 'pre_ea_cancel_btn'):
            self.pre_ea_cancel_btn.setEnabled(False)
        if hasattr(self, 'pre_ea_status_banner'):
            self.pre_ea_status_banner.setText("Ready.")

        # 4. Reset results & summary info
        if hasattr(self, 'pre_ea_results_table'):
            self.pre_ea_results_table.setRowCount(0)
        for attr in [
            '_pre_ea_sum_bgy_val', '_pre_ea_sum_ea_val', '_pre_ea_sum_corr_val',
            '_pre_ea_sum_clip_val', '_pre_ea_sum_gaps_det_val', '_pre_ea_sum_gaps_asgn_val',
            '_pre_ea_sum_unres_val', '_pre_ea_sum_outside_val', '_pre_ea_sum_uncov_val',
            '_pre_ea_sum_output_val'
        ]:
            val_lbl = getattr(self, attr, None)
            if val_lbl:
                val_lbl.setText("-")
        if hasattr(self, '_pre_ea_sum_status_lbl'):
            self._pre_ea_sum_status_lbl.setText("Status: -")

        # 5. Clear console logs & set active sub-tab
        if hasattr(self, 'pre_ea_log_console'):
            self.pre_ea_log_console.clear()
        if hasattr(self, 'pre_ea_right_tabs'):
            self.pre_ea_right_tabs.setCurrentIndex(0)

    def _pre_ea_auto_detect_layers(self):
        """Auto-detect Barangay (*_bgy) and EA (*_ea, *_ea2024) layers from the QGIS project."""
        layers = list(QgsProject.instance().mapLayers().values())

        bgy_match = None
        ea_match = None

        bgy_patterns = ["_bgy", "_barangay", "_brgy"]
        ea_patterns = ["_ea2024", "_ea2023", "_ea2022", "_ea2025", "_ea2026", "_ea"]

        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            if layer.geometryType() != 2:  # Polygon
                continue
            name_lower = layer.name().lower()

            if bgy_match is None:
                for pat in bgy_patterns:
                    if pat in name_lower:
                        bgy_match = layer
                        break

            if ea_match is None:
                for pat in ea_patterns:
                    if pat in name_lower:
                        ea_match = layer
                        break

            if bgy_match and ea_match:
                break

        if bgy_match:
            self.pre_ea_bgy_combo.setLayer(bgy_match)
        if ea_match:
            self.pre_ea_ea_combo.setLayer(ea_match)

        self._pre_ea_validate_inputs()

    def _pre_ea_auto_arrange_and_detect_layers(self):
        """Auto-arrange project layer tree, apply QML styles, and auto-detect Pre-EA input layers."""
        try:
            from ...gmd_scripts.auto_arrange import auto_arrange_layers
            res = auto_arrange_layers(iface=getattr(self, 'iface', None))
            self._pre_ea_auto_detect_layers()
            self.auto_detect_layers()
            self._ea_merge_auto_detect_ea_layer()
            if hasattr(self, 'pre_ea_log_console'):
                self.pre_ea_log_console.append(
                    f"<span style='color: #0969da; font-weight: bold;'>[INFO]</span> "
                    f"Auto Arrange completed: {res['total']} layers processed ({res['styled']} styled, {res['reordered']} reordered)."
                )
        except Exception as e:
            QgsMessageLog.logMessage(f"Auto Arrange error: {e}", "GEMMA", Qgis.Warning)
            self._pre_ea_auto_detect_layers()
            self._ea_merge_auto_detect_ea_layer()

    def _pre_ea_validate_inputs(self):
        """Validate selected layers and designated output folder."""
        bgy_layer = self.pre_ea_bgy_combo.currentLayer()
        ea_layer = self.pre_ea_ea_combo.currentLayer()

        if not bgy_layer:
            self.pre_ea_bgy_status_lbl.setText("Barangay Layer is required.")
        else:
            self.pre_ea_bgy_status_lbl.setText(
                f"Active: {bgy_layer.featureCount()} polygons ({bgy_layer.crs().authid()})."
            )

        if not ea_layer:
            if bgy_layer:
                self.pre_ea_ea_status_lbl.setText(
                    "No EA layer selected. A new EA layer will be created from the Barangay layer."
                )
            else:
                self.pre_ea_ea_status_lbl.setText("No layer selected.")
        else:
            self.pre_ea_ea_status_lbl.setText(
                f"Active: {ea_layer.featureCount()} EA polygons ({ea_layer.crs().authid()})."
            )

        has_output = bool(self.pre_ea_output_folder_widget.filePath().strip()) if hasattr(self, 'pre_ea_output_folder_widget') else False
        can_run = bool(bgy_layer) and has_output
        self.pre_ea_run_btn.setEnabled(can_run)

    def _pre_ea_cancel(self):
        """Request cancellation of the running Pre-EA processing task."""
        self._pre_ea_cancelled = True
        self._pre_ea_append_log(
            "<span style='color:#d17a00; font-weight:bold;'>[CANCEL] Cancellation requested...</span>"
        )

    def _pre_ea_copy_log(self):
        """Copy the processing log to the clipboard."""
        clipboard = QCoreApplication.instance().clipboard()
        clipboard.setText(self.pre_ea_log_console.toPlainText())
        self.pre_ea_copy_log_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.pre_ea_copy_log_btn.setText("Copy Log"))

    def _pre_ea_toggle_description(self) -> None:
        """Show or hide the Pre-EA description panel."""
        is_visible = not self.pre_ea_desc_panel.isVisible()
        self.pre_ea_desc_panel.setVisible(is_visible)

        show_icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "show_description.svg")
        )
        hide_icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "hide_description.svg")
        )
        if is_visible:
            icon = QIcon(hide_icon_path) if os.path.exists(hide_icon_path) else QIcon()
            self.pre_ea_toggle_desc_btn.setIcon(icon)
            self.pre_ea_toggle_desc_btn.setToolTip("Hide Description Panel")
        else:
            icon = QIcon(show_icon_path) if os.path.exists(show_icon_path) else QIcon()
            self.pre_ea_toggle_desc_btn.setIcon(icon)
            self.pre_ea_toggle_desc_btn.setToolTip("Show Description Panel")

    @staticmethod
    def _pre_ea_help_html() -> str:
        """Return the HTML description string for the Pre-EA Processing description panel."""
        from .pre_ea_processor import PreEAProcessor
        return PreEAProcessor.short_help_string()

    def _pre_ea_append_log(self, html_msg: str):
        """Thread-safe append of HTML message to the Pre-EA log console."""
        self.pre_ea_log_console.append(html_msg)
        self.pre_ea_log_console.ensureCursorVisible()

    def _pre_ea_format_log(self, text: str) -> str:
        """Format plain text log messages with HTML colors based on prefixes."""
        if "[ERROR]" in text:
            return f"<span style='color: #cf222e;'>{text}</span>"
        elif "[WARNING]" in text:
            return f"<span style='color: #d17a00;'>{text}</span>"
        elif "[SUCCESS]" in text or "[PASS]" in text:
            return f"<span style='color: #1a7f37; font-weight: bold;'>{text}</span>"
        elif "[INFO]" in text or "[PHASE" in text:
            return f"<span style='color: #0969da;'>{text}</span>"
        elif "[DEBUG]" in text:
            return f"<span style='color: #8c959f;'>{text}</span>"
        return text

    def _pre_ea_run(self):
        """Execute the EA Preprocessing workflow."""
        bgy_layer = self.pre_ea_bgy_combo.currentLayer()
        ea_layer = self.pre_ea_ea_combo.currentLayer()

        if not bgy_layer:
            QMessageBox.warning(self, "Missing Input", "Please select a Barangay Layer.")
            return

        # Prepare UI for processing
        self.pre_ea_run_btn.setEnabled(False)
        self.pre_ea_cancel_btn.setEnabled(True)
        self.pre_ea_progress_bar.setValue(0)
        self.pre_ea_log_console.clear()
        self.pre_ea_results_table.setRowCount(0)
        self.pre_ea_status_banner.setText("Processing...")

        # Switch to log tab so user sees progress
        right_tabs = self.pre_ea_log_console.parent().parent()
        if hasattr(right_tabs, "setCurrentIndex"):
            right_tabs.setCurrentIndex(2)  # Log tab

        gap_tolerance = self.pre_ea_gap_tol_spin.value()
        clip_to_bgy = self.pre_ea_clip_chk.isChecked()
        resolve_overlaps = self.pre_ea_resolve_overlaps_chk.isChecked()
        detect_gaps = self.pre_ea_detect_gaps_chk.isChecked()
        assign_gaps = self.pre_ea_assign_gaps_chk.isChecked()

        # --- Cancelled flag shared with task --------------------------------
        self._pre_ea_cancelled = False

        def is_cancelled_fn():
            return self._pre_ea_cancelled

        def feedback_callback(msg):
            self._pre_ea_append_log(self._pre_ea_format_log(msg))

        def progress_callback(pct):
            self.pre_ea_progress_bar.setValue(pct)
            QCoreApplication.processEvents()


        # Determine designated output folder
        out_folder = self.pre_ea_output_folder_widget.filePath().strip() if hasattr(self, 'pre_ea_output_folder_widget') else ""
        if not out_folder:
            QMessageBox.warning(self, "Missing Output Folder", "Please designate an output folder before running.")
            self.pre_ea_run_btn.setEnabled(False)
            return

        from .helpers.pre_ea_detector import resolve_target_output_folder
        out_folder = resolve_target_output_folder(out_folder, bool(ea_layer))

        self._pre_ea_append_log(
            f"<span style='color: #0969da; font-weight: bold;'>[INFO]</span> Designated Output Folder: {out_folder}"
        )

        from .pre_ea_processor import PreEAProcessor
        processor = PreEAProcessor()
        result = processor.run(
            barangay_layer=bgy_layer,
            ea_layer=ea_layer,
            gap_tolerance=gap_tolerance,
            clip_to_bgy=clip_to_bgy,
            resolve_overlaps=resolve_overlaps,
            detect_gaps=detect_gaps,
            assign_gaps=assign_gaps,
            output_folder=out_folder,
            feedback_callback=feedback_callback,
            progress_callback=progress_callback,
            is_cancelled_fn=is_cancelled_fn,
        )

        self._pre_ea_on_finished(result)

    def _pre_ea_on_finished(self, result) -> None:
        """Handle completion of the Pre-EA Processing run and update the UI."""
        # Re-enable controls
        self.pre_ea_run_btn.setEnabled(True)
        self.pre_ea_cancel_btn.setEnabled(False)

        summary = result.summary

        if not result.success:
            self.pre_ea_status_banner.setText(f"Error: {result.error_message}")
            return

        # Populate summary tab
        self._pre_ea_sum_bgy_val.setText(str(summary.barangays_processed))
        self._pre_ea_sum_ea_val.setText(str(summary.eas_processed))
        self._pre_ea_sum_corr_val.setText(str(summary.eas_requiring_correction))
        self._pre_ea_sum_clip_val.setText(str(summary.eas_clipped))
        self._pre_ea_sum_gaps_det_val.setText(str(summary.gaps_detected))
        self._pre_ea_sum_gaps_asgn_val.setText(str(summary.gaps_assigned))
        self._pre_ea_sum_unres_val.setText(str(summary.unresolved_gaps))
        self._pre_ea_sum_outside_val.setText(str(summary.final_eas_outside_bgy))
        self._pre_ea_sum_uncov_val.setText(f"{summary.final_uncovered_area:.4f}")
        self._pre_ea_sum_output_val.setText(summary.output_name)

        status_colors = {"PASS": "#1a7f37", "WARNING": "#d17a00", "ERROR": "#cf222e"}
        status_color = status_colors.get(summary.overall_status, "#333")
        self._pre_ea_sum_status_lbl.setText(
            f"<span style='color:{status_color}; font-weight:bold;'>Status: {summary.overall_status}</span>"
        )
        self._pre_ea_sum_status_lbl.setTextFormat(Qt.RichText)

        # Populate results table
        table = self.pre_ea_results_table
        table.setRowCount(0)
        table.setRowCount(len(result.result_rows))

        action_colors = {
            "No Change": ("#f6f8fa", "#333"),
            "Clipped": ("#fff8c5", "#7d4e00"),
            "Overlap Resolved": ("#e6ffec", "#1a7f37"),
            "Gap Assigned": ("#dafbe1", "#1a7f37"),
            "Geometry Fixed": ("#ddf4ff", "#0969da"),
            "Unresolved": ("#ffebe9", "#cf222e"),
            "Error": ("#ffebe9", "#cf222e"),
        }
        if self.current_theme == "dark":
            action_colors = {
                "No Change": ("#2d333b", "#adbac7"),
                "Clipped": ("#3d3300", "#e3b341"),
                "Overlap Resolved": ("#133a1e", "#3fb950"),
                "Gap Assigned": ("#1e3f28", "#2ecc71"),
                "Geometry Fixed": ("#0e2235", "#79c0ff"),
                "Unresolved": ("#3d1f1f", "#ff6b6b"),
                "Error": ("#3d1f1f", "#ff6b6b"),
            }

        for row_idx, row in enumerate(result.result_rows):
            bg, fg = action_colors.get(row.action, ("#f6f8fa", "#333"))
            cells = [
                row.barangay_id,
                row.ea_id,
                f"{row.original_area:.4f}",
                f"{row.corrected_area:.4f}",
                f"{row.area_change:+.4f}",
                row.action,
                row.status,
            ]
            for col_idx, cell_text in enumerate(cells):
                item = QTableWidgetItem(cell_text)
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
                item.setTextAlignment(
                    Qt.AlignCenter if col_idx in (2, 3, 4) else Qt.AlignLeft | Qt.AlignVCenter
                )
                table.setItem(row_idx, col_idx, item)

        # Status banner
        if summary.overall_status == "PASS":
            self.pre_ea_status_banner.setText(
                f"Complete — EAs Clipped: {summary.eas_clipped}  "
                f"Gaps Filled: {summary.gaps_assigned}  "
                f"Unresolved: {summary.unresolved_gaps}  |  Status: PASS"
            )
        elif summary.overall_status == "WARNING":
            self.pre_ea_status_banner.setText(
                f"Complete with warnings — "
                f"Unresolved Gaps: {summary.unresolved_gaps}  "
                f"EAs Outside Bgy: {summary.final_eas_outside_bgy}"
            )
        else:
            self.pre_ea_status_banner.setText(
                f"Processing finished with errors — {result.error_message}"
            )

        self.pre_ea_progress_bar.setValue(100)

        # Update layer combo with the newly generated permanent layer
        if result.output_layer and result.output_layer.isValid():
            self.pre_ea_ea_combo.blockSignals(True)
            self.pre_ea_ea_combo.setLayer(result.output_layer)
            self.pre_ea_ea_combo.blockSignals(False)

        # Switch to Summary tab
        right_tabs_widget = table.parent().parent().parent()
        if hasattr(right_tabs_widget, "setCurrentIndex"):
            right_tabs_widget.setCurrentIndex(1)

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 2 — Create Enumeration Areas
    # ─────────────────────────────────────────────────────────────────────────

    def _build_create_ea_tab(self):
        """Build the Create Enumeration Areas tab (Tab 2) and add it to main_tabs."""
        tab_widget = QWidget()
        tab_root_layout = QVBoxLayout(tab_widget)
        tab_root_layout.setContentsMargins(6, 6, 6, 6)
        tab_root_layout.setSpacing(6)
        self._build_create_ea_content(tab_root_layout)
        self.main_tabs.addTab(tab_widget, "Create Enumeration Areas")

    def _build_create_ea_content(self, root):
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── Main Pane Splitter ────────────────────────────────────────────
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setObjectName("mainSplitter")
        
        # Left Panel (Parameters Scroll Area)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)
        left_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)

        # 1. Inputs Section (QGroupBox)
        inputs_group = QGroupBox("Input Layers")
        inputs_layout = QVBoxLayout(inputs_group)
        inputs_layout.setContentsMargins(8, 8, 8, 8)
        inputs_layout.setSpacing(8)

        # Row 1: Dedicated Auto Arrange action button
        self.auto_arrange_btn = QPushButton("Auto Arrange")
        self.auto_arrange_btn.setToolTip("Auto-arrange project layer ordering, apply QML styles, and auto-detect matching layers.")
        self.auto_arrange_btn.clicked.connect(self.auto_arrange_and_detect_layers)
        inputs_layout.addWidget(self.auto_arrange_btn)

        # Row 2: Sub-row for Auto-detect Layers and Fill missing hhcount
        inputs_btn_layout = QHBoxLayout()
        self.detect_btn = QPushButton("Auto-detect Layers")
        self.detect_btn.setToolTip("Scan current QGIS project layers and auto-select matching layers.")
        self.detect_btn.clicked.connect(self.auto_detect_layers)
        inputs_btn_layout.addWidget(self.detect_btn)

        self.fill_missing_btn = QPushButton("Fill missing hh_count")
        self.fill_missing_btn.setToolTip("Compute and populate missing EA hh_count values from building points within each EA polygon.")
        self.fill_missing_btn.clicked.connect(self.fill_missing_hh_count)
        inputs_btn_layout.addWidget(self.fill_missing_btn)
        inputs_layout.addLayout(inputs_btn_layout)

        # Barangay Layer
        inputs_layout.addWidget(QLabel("Barangay Layer (Polygon)*"))
        self.bar_combo = QgsMapLayerComboBox(self)
        self.bar_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        inputs_layout.addWidget(self.bar_combo)
        self.bar_status_lbl = QLabel("No layer selected.")
        self.bar_status_lbl.setWordWrap(True)
        inputs_layout.addWidget(self.bar_status_lbl)

        # Building Points
        inputs_layout.addWidget(QLabel("Building Point Layer (Point)*"))
        self.bldg_combo = QgsMapLayerComboBox(self)
        self.bldg_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        inputs_layout.addWidget(self.bldg_combo)
        self.bldg_status_lbl = QLabel("No layer selected.")
        self.bldg_status_lbl.setWordWrap(True)
        inputs_layout.addWidget(self.bldg_status_lbl)

        # Previous EAs
        inputs_layout.addWidget(QLabel("Previous EA Layer (Polygon)*"))
        self.prev_ea_combo = QgsMapLayerComboBox(self)
        self.prev_ea_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        inputs_layout.addWidget(self.prev_ea_combo)
        self.prev_ea_status_lbl = QLabel("No layer selected.")
        self.prev_ea_status_lbl.setWordWrap(True)
        inputs_layout.addWidget(self.prev_ea_status_lbl)

        # Road (Optional)
        inputs_layout.addWidget(QLabel("Road Layer (Line, Optional)"))
        self.road_combo = QgsMapLayerComboBox(self)
        self.road_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.road_combo.setAllowEmptyLayer(True)
        self.road_combo.setLayer(None)
        inputs_layout.addWidget(self.road_combo)
        self.road_status_lbl = QLabel("Optional.")
        self.road_status_lbl.setWordWrap(True)
        inputs_layout.addWidget(self.road_status_lbl)

        # River (Optional)
        inputs_layout.addWidget(QLabel("River Layer (Line, Optional)"))
        self.river_combo = QgsMapLayerComboBox(self)
        self.river_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.river_combo.setAllowEmptyLayer(True)
        self.river_combo.setLayer(None)
        inputs_layout.addWidget(self.river_combo)
        self.river_status_lbl = QLabel("Optional.")
        self.river_status_lbl.setWordWrap(True)
        inputs_layout.addWidget(self.river_status_lbl)



        # Designated Output Folder
        inputs_layout.addWidget(QLabel("Designated Output Folder*"))
        self.output_folder_widget = QgsFileWidget()
        self.output_folder_widget.setStorageMode(QgsFileWidget.GetDirectory)
        self.output_folder_widget.setDialogTitle("Designate Output Folder for EA Delineation and Merging")
        inputs_layout.addWidget(self.output_folder_widget)
        self.output_folder_widget.fileChanged.connect(self.validate_layer_inputs)

        scroll_layout.addWidget(inputs_group)

        # 2. Parameters Section (Collapsible QGroupBox)
        self.params_group = QgsCollapsibleGroupBox("Delineation Thresholds Settings")
        if hasattr(self.params_group, "setCollapsed"):
            self.params_group.setCollapsed(True)
        params_layout = QVBoxLayout(self.params_group)
        params_layout.setSpacing(8)

        # Enable Household Count Thresholds checkbox
        self.enable_thresholds_chk = QCheckBox("Enable Custom Thresholds")
        self.enable_thresholds_chk.setChecked(False)
        self.enable_thresholds_chk.toggled.connect(self._toggle_thresholds)
        params_layout.addWidget(self.enable_thresholds_chk)

        # Min Household
        self.min_hh_label = QLabel("Minimum Household count per EA")
        params_layout.addWidget(self.min_hh_label)
        self.min_hh_spin = QSpinBox()
        self.min_hh_spin.setRange(1, 99999)
        self.min_hh_spin.setValue(99)
        params_layout.addWidget(self.min_hh_spin)

        # Max Household
        self.max_hh_label = QLabel("Maximum Household count per EA")
        params_layout.addWidget(self.max_hh_label)
        self.max_hh_spin = QSpinBox()
        self.max_hh_spin.setRange(1, 99999)
        self.max_hh_spin.setValue(300)
        params_layout.addWidget(self.max_hh_spin)

        # Snapping Tolerance
        self.tolerance_label = QLabel("Snapping Tolerance (meters) for road/river alignment")
        params_layout.addWidget(self.tolerance_label)
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.0, 999.0)
        self.tolerance_spin.setValue(15.0)
        params_layout.addWidget(self.tolerance_spin)

        # Apply initial disabled state to threshold & tolerance inputs
        self._toggle_thresholds(False)

        # Compactness optimization
        self.compact_chk = QCheckBox("Optimize for Compactness")
        self.compact_chk.setChecked(True)
        params_layout.addWidget(self.compact_chk)

        # Allow Candidate Merging
        self.allow_candidate_merge_chk = QCheckBox("Allow Merging Between Under-Threshold Candidate EAs")
        self.allow_candidate_merge_chk.setToolTip("When checked, under-threshold candidate EAs (< 100 HH) can merge with neighboring candidate EAs when no normal reference EA exists in the barangay.")
        self.allow_candidate_merge_chk.setChecked(True)
        params_layout.addWidget(self.allow_candidate_merge_chk)

        # Sliver Polygon enum
        params_layout.addWidget(QLabel("Sliver Polygon Area Threshold"))
        self.sliver_combo = QComboBox()
        self.sliver_combo.addItems([
            "Auto-detect (Script Chosen / Dynamic)",
            "Automatic (Conservative - 1e-11 deg / 1e-4 m²)",
            "Automatic (Standard - 1e-9 deg / 1e-2 m²)",
            "Automatic (Moderate - 1e-7 deg / 1 m²)",
            "Automatic (Aggressive - 1e-5 deg / 100 m²)",
            "Automatic (Ultra-Conservative - 1e-13 deg / 1e-6 m²)",
            "Automatic (Super Aggressive - 1e-4 deg / 1,000 m²)",
            "Automatic (Extremely Aggressive - 1e-3 deg / 10,000 m²)"
        ])
        params_layout.addWidget(self.sliver_combo)

        # Target CRS
        params_layout.addWidget(QLabel("Target CRS"))
        self.crs_widget = QgsProjectionSelectionWidget()
        self.crs_widget.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        params_layout.addWidget(self.crs_widget)

        scroll_layout.addWidget(self.params_group)

        # 3. Outputs Section (QGroupBox)
        outputs_group = QGroupBox("Output Preview")
        outputs_layout = QVBoxLayout(outputs_group)
        outputs_layout.setContentsMargins(10, 8, 10, 8)
        outputs_layout.setSpacing(6)

        # Permanent outputs
        perm_title = QLabel("<b>Permanent Output Layers (.gpkg):</b>")
        perm_title.setWordWrap(True)
        outputs_layout.addWidget(perm_title)

        self.out_delineated_lbl = QLabel("• Delineated EAs: <i>-</i>")
        self.out_delineated_lbl.setWordWrap(True)
        self.out_delineated_lbl.setFont(QFont("Segoe UI", 9))
        outputs_layout.addWidget(self.out_delineated_lbl)

        self.out_merged_lbl = QLabel("• Merged EAs: <i>-</i>")
        self.out_merged_lbl.setWordWrap(True)
        self.out_merged_lbl.setFont(QFont("Segoe UI", 9))
        outputs_layout.addWidget(self.out_merged_lbl)



        self.out_splitting_lines_lbl = QLabel("• Proposed Splitting Lines: <i>-</i>")
        self.out_splitting_lines_lbl.setWordWrap(True)
        self.out_splitting_lines_lbl.setFont(QFont("Segoe UI", 9))
        outputs_layout.addWidget(self.out_splitting_lines_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        outputs_layout.addWidget(sep)

        # Temporary scratch outputs
        temp_title = QLabel("<b>Temporary Scratch Layers:</b>")
        temp_title.setWordWrap(True)
        outputs_layout.addWidget(temp_title)

        self.out_delin_cand_lbl = QLabel("• Delineation Candidates: <span style='color:#7F8C8D;'>[Scratch]</span>")
        self.out_delin_cand_lbl.setWordWrap(True)
        self.out_delin_cand_lbl.setFont(QFont("Segoe UI", 9))
        outputs_layout.addWidget(self.out_delin_cand_lbl)

        self.out_merge_cand_lbl = QLabel("• Merge Candidates: <span style='color:#7F8C8D;'>[Scratch]</span>")
        self.out_merge_cand_lbl.setWordWrap(True)
        self.out_merge_cand_lbl.setFont(QFont("Segoe UI", 9))
        outputs_layout.addWidget(self.out_merge_cand_lbl)

        self.out_extracted_bldg_lbl = QLabel("• Extracted Buildings: <span style='color:#7F8C8D;'>[Scratch]</span>")
        self.out_extracted_bldg_lbl.setWordWrap(True)
        self.out_extracted_bldg_lbl.setFont(QFont("Segoe UI", 9))
        outputs_layout.addWidget(self.out_extracted_bldg_lbl)

        scroll_layout.addWidget(outputs_group)
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        
        left_widget.setMinimumWidth(390)
        main_splitter.addWidget(left_widget)

        # Right Panel (Tabs for Live Preview and Execution Logs)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(6)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("rightTabs")
        self.tab_widget.tabBar().setElideMode(Qt.ElideNone)
        self.tab_widget.tabBar().setUsesScrollButtons(True)

        # ── Live Preview Tab ──────────────────────────────────────────────
        preview_tab = QWidget()
        preview_tab_layout = QVBoxLayout(preview_tab)
        preview_tab_layout.setContentsMargins(8, 8, 8, 8)
        preview_tab_layout.setSpacing(8)

        # Dashboard KPI Cards
        self.kpi_layout = QHBoxLayout()
        
        # 1. Delineation Card
        self.kpi_delin_card = self._create_kpi_card("For Delineation", "0", "delin")
        self.kpi_layout.addWidget(self.kpi_delin_card)
        
        # 2. Merge Card
        self.kpi_merge_card = self._create_kpi_card("For Merging", "0", "merge")
        self.kpi_layout.addWidget(self.kpi_merge_card)
        
        preview_tab_layout.addLayout(self.kpi_layout)

        # Search Bar Filter
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter previews by Barangay name, Geocode or EA name...")
        self.search_edit.textChanged.connect(self.filter_previews)
        preview_tab_layout.addWidget(self.search_edit)

        # Sub Tabs for candidates tables
        self.preview_sub_tabs = QTabWidget()
        self.preview_sub_tabs.setObjectName("previewSubTabs")
        self.preview_sub_tabs.tabBar().setElideMode(Qt.ElideNone)
        self.preview_sub_tabs.tabBar().setUsesScrollButtons(True)

        # Table 1: Delineation Table
        self.delineation_table = self._create_preview_table()
        self.preview_sub_tabs.addTab(self.delineation_table, "Delineation Candidates")

        # Table 2: Merge Table
        self.merge_table = self._create_preview_table()
        self.preview_sub_tabs.addTab(self.merge_table, "Merge Candidates")

        preview_tab_layout.addWidget(self.preview_sub_tabs)
        
        # Refresh preview button
        self.refresh_btn = QPushButton("Refresh Live Candidates Preview")
        self.refresh_btn.setFixedHeight(30)
        self.refresh_btn.clicked.connect(self.generate_preview)
        preview_tab_layout.addWidget(self.refresh_btn)

        self.tab_widget.addTab(preview_tab, "Live Candidates Preview")

        # ── Execution Logs Tab ────────────────────────────────────────────
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(8, 8, 8, 8)
        logs_layout.setSpacing(8)

        # Console controls layout
        console_controls = QHBoxLayout()
        console_controls.addWidget(QLabel("Execution Logs:"))
        console_controls.addStretch()
        
        self.copy_logs_btn = QPushButton("Copy Logs")
        self.copy_logs_btn.setToolTip("Copy entire log console history to clipboard.")
        self.copy_logs_btn.clicked.connect(self.copy_logs_to_clipboard)
        console_controls.addWidget(self.copy_logs_btn)
        
        self.clear_logs_btn = QPushButton("Clear Console")
        self.clear_logs_btn.setToolTip("Clear all text from the console.")
        self.clear_logs_btn.clicked.connect(self.log_console_clear)
        console_controls.addWidget(self.clear_logs_btn)
        
        logs_layout.addLayout(console_controls)

        self.log_console = QTextEdit()
        self.log_console.setObjectName("logConsole")
        self.log_console.setReadOnly(True)
        logs_layout.addWidget(self.log_console)

        self.tab_widget.addTab(logs_tab, "Processing Progress && Logs")

        right_layout.addWidget(self.tab_widget)
        
        right_widget.setMinimumWidth(480)
        main_splitter.addWidget(right_widget)

        # ── Help / Description Panel ──────────────────────────────────────
        self.help_panel = QWidget()
        help_layout = QVBoxLayout(self.help_panel)
        help_layout.setContentsMargins(2, 2, 2, 2)
        help_layout.setSpacing(0)

        self.help_text = QTextBrowser()
        self.help_text.setOpenExternalLinks(True)
        self.help_text.setHtml(self.algo.shortHelpString())
        help_layout.addWidget(self.help_text)

        self.help_panel.setMinimumWidth(260)
        main_splitter.addWidget(self.help_panel)
        
        # Set proportional initial widths for the panels
        main_splitter.setSizes([390, 500, 260])

        root.addWidget(main_splitter, 1)

        # ── Bottom Bar (Progress, Run, Cancel & Status Banner) ───────────
        bottom_bar = QWidget()
        bottom_main_layout = QVBoxLayout(bottom_bar)
        bottom_main_layout.setContentsMargins(10, 4, 10, 6)
        bottom_main_layout.setSpacing(6)

        # Status Summary Banner above progress bar (Native QLabel without hardcoded stylesheet)
        self.status_banner = QLabel("Ready to run algorithm.")
        self.status_banner.setWordWrap(True)
        self.status_banner.setFont(QFont("Segoe UI", 9, QFont.Bold))
        bottom_main_layout.addWidget(self.status_banner)

        # Controls row (Progress bar, Cancel btn, Run btn)
        bottom_controls_layout = QHBoxLayout()
        bottom_controls_layout.setContentsMargins(0, 0, 0, 0)
        bottom_controls_layout.setSpacing(8)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(26)
        bottom_controls_layout.addWidget(self.progress_bar)

        # Actions
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.setFixedHeight(26)
        self.cancel_btn.setEnabled(False)
        bottom_controls_layout.addWidget(self.cancel_btn)

        self.run_btn = QPushButton("Run")
        self.run_btn.setMinimumWidth(120)
        self.run_btn.setFixedHeight(26)
        self.run_btn.clicked.connect(self.run_pipeline)
        bottom_controls_layout.addWidget(self.run_btn)

        bottom_main_layout.addLayout(bottom_controls_layout)
        root.addWidget(bottom_bar)

    def _safe_set_layer(self, combo, layer):
        if combo is None or layer is None:
            return
        try:
            from qgis.PyQt import sip
            if not sip.isdeleted(combo):
                combo.setLayer(layer)
        except (RuntimeError, AttributeError, TypeError):
            pass

    def _safe_get_layer(self, combo):
        if combo is None:
            return None
        try:
            from qgis.PyQt import sip
            if not sip.isdeleted(combo):
                return combo.currentLayer()
        except (RuntimeError, AttributeError, TypeError):
            return None
        return None

    def _toggle_thresholds(self, checked: bool):
        self.min_hh_label.setEnabled(checked)
        self.min_hh_spin.setEnabled(checked)
        self.max_hh_label.setEnabled(checked)
        self.max_hh_spin.setEnabled(checked)
        self.tolerance_label.setEnabled(checked)
        self.tolerance_spin.setEnabled(checked)

    def toggle_help(self):
        """Toggle the visibility of the description help panel."""
        is_visible = not self.help_panel.isVisible()
        self.help_panel.setVisible(is_visible)

        show_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "icons", "show_description.svg"))
        hide_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "icons", "hide_description.svg"))

        if is_visible:
            self.toggle_help_btn.setIcon(QIcon(hide_icon))
            self.toggle_help_btn.setToolTip("Hide Description Panel")
        else:
            self.toggle_help_btn.setIcon(QIcon(show_icon))
            self.toggle_help_btn.setToolTip("Show Description Panel")

    def _create_kpi_card(self, title, value, variant="stats"):
        card = QGroupBox(title)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)
        
        lbl_val = QLabel(value)
        lbl_val.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_val.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl_val)
        
        if variant == "delin":
            self.kpi_delin_val = lbl_val
        elif variant == "merge":
            self.kpi_merge_val = lbl_val
        else:
            self.kpi_stats_val = lbl_val
            
        return card

    def _file_picker_row(self):
        layout = QHBoxLayout()
        layout.setSpacing(6)
        
        edit = QLineEdit()
        edit.setPlaceholderText("[Temporary Scratch Layer]")
        edit.setObjectName("pathEdit")
        layout.addWidget(edit)
        
        btn = QPushButton("...")
        btn.setObjectName("browseBtn")
        btn.setFixedSize(30, 24)
        btn.clicked.connect(lambda: self._browse_file(edit))
        layout.addWidget(btn)
        
        return layout, edit

    def _extract_5digit_geocode(self):
        """Extract 5-digit geocode prefix from selected Barangay or EA layer."""
        layers = [self._safe_get_layer(self.bar_combo), self._safe_get_layer(self.prev_ea_combo)]
        for lyr in layers:
            if not lyr:
                continue
            name = lyr.name()
            digits = "".join([c for c in name if c.isdigit()])
            if len(digits) >= 5:
                return digits[:5]
            fields = [f.name().lower() for f in lyr.fields()]
            if "geocode" in fields:
                feat = next(lyr.getFeatures(), None)
                if feat:
                    gval = str(feat.attribute("geocode")).strip()
                    gdigits = "".join([c for c in gval if c.isdigit()])
                    if len(gdigits) >= 5:
                        return gdigits[:5]
        return None

    def _browse_file(self, line_edit):
        default_name = line_edit.placeholderText()
        if not default_name or default_name.startswith("["):
            default_name = ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output Layer", default_name, "GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson)"
        )
        if path:
            line_edit.setText(path)

    def _create_preview_table(self):
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Geocode", "Barangay", "EA Name", "Household Count", "Role / Status"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(150)
        return table

    # ── Live Candidate Preview Logic ────────────────────────────────────────

    def _setup_preview_connections(self):
        """Hook parameter modification signals up to preview auto-refresh and validators."""
        for combo in (
            getattr(self, 'bar_combo', None),
            getattr(self, 'bldg_combo', None),
            getattr(self, 'prev_ea_combo', None),
            getattr(self, 'road_combo', None),
            getattr(self, 'river_combo', None),
        ):
            if combo is not None:
                try:
                    combo.currentIndexChanged.connect(self.validate_layer_inputs)
                except (RuntimeError, TypeError):
                    pass

        for spin in (getattr(self, 'min_hh_spin', None), getattr(self, 'max_hh_spin', None)):
            if spin is not None:
                try:
                    spin.valueChanged.connect(self.trigger_auto_refresh)
                except (RuntimeError, TypeError):
                    pass

    def trigger_auto_refresh(self, *args, **kwargs):
        """Called when parameters are modified. Warns the user that the preview is out of sync."""
        self.kpi_delin_val.setText("...")
        self.kpi_merge_val.setText("...")
        self.delineation_table.setRowCount(0)
        self.merge_table.setRowCount(0)

    def _get_ea_name(self, feat, ean_str, fields):
        ea_fields = ["ea_name", "ea_no", "eano", "ea_number", "eaname"]
        for name in ea_fields:
            idx = fields.indexOf(name)
            if idx == -1:
                for i in range(fields.count()):
                    if fields.at(i).name().lower() == name:
                        idx = i
                        break
            if idx != -1:
                val = feat.attribute(idx)
                if val is not None:
                    val_str = str(val).strip()
                    if val_str.endswith(".0"):
                        val_str = val_str[:-2]
                    if val_str:
                        if not val_str.upper().startswith("EA "):
                            return f"EA {val_str}"
                        return val_str
        if ean_str:
            if len(ean_str) >= 6 and ean_str[-6:].isdigit():
                return f"EA {ean_str[-6:]}"
            elif len(ean_str) >= 3 and ean_str[-3:].isdigit():
                return f"EA {ean_str[-3:]}"
            else:
                return f"EA {ean_str}"
        return "EA Unknown"

    def fill_missing_hh_count(self):
        """Populate hh_count and bldg_count in the EA layer from building points inside each EA using delineation logic."""
        prev_ea_layer = self._safe_get_layer(self.prev_ea_combo)
        bldg_layer = self._safe_get_layer(self.bldg_combo)
        if not prev_ea_layer or not bldg_layer:
            QMessageBox.warning(
                self,
                "Missing Layers",
                "Please select both Previous EA and Building Point layers before filling missing hh_count values."
            )
            return

        # Resolve household field index in EA layer (strictly hh_count) and bldg_count field
        prev_fields = prev_ea_layer.fields()
        hh_field = None
        bldg_count_field = None
        for i in range(prev_fields.count()):
            name_lower = prev_fields.at(i).name().lower()
            if name_lower == "hh_count":
                hh_field = prev_fields.at(i).name()
            elif name_lower in ["bldg_count", "bldgcount"]:
                bldg_count_field = prev_fields.at(i).name()

        if not hh_field:
            QMessageBox.critical(
                self,
                "Field Not Found",
                "Previous EA layer does not contain 'hh_count' field."
            )
            return

        # Auto-create bldg_count field if it does not exist on EA layer
        if not bldg_count_field:
            prev_ea_layer.dataProvider().addAttributes([QgsField("bldg_count", QVariant.Int)])
            prev_ea_layer.updateFields()
            prev_fields = prev_ea_layer.fields()
            for i in range(prev_fields.count()):
                if prev_fields.at(i).name().lower() in ["bldg_count", "bldgcount"]:
                    bldg_count_field = prev_fields.at(i).name()
                    break

        # Use spatial index on EA polygons
        ea_index = QgsSpatialIndex(prev_ea_layer.getFeatures())
        ea_by_id = {feat.id(): feat for feat in prev_ea_layer.getFeatures()}

        # Map EA feature id -> total building count and total HH count from buildings inside it
        building_fields = bldg_layer.fields()
        bldg_hh_idx = -1
        for i in range(building_fields.count()):
            if building_fields.at(i).name().lower() in ["hhcount", "hh_count", "household", "household_count"]:
                bldg_hh_idx = i
                break
        if bldg_hh_idx == -1:
            QMessageBox.critical(
                self,
                "Field Not Found",
                "Building point layer does not contain 'hhcount' (or 'hh_count') field."
            )
            return

        bldg_counts = {feat_id: 0 for feat_id in ea_by_id.keys()}
        hh_updates = {feat_id: 0.0 for feat_id in ea_by_id.keys()}

        # Build a spatial lookup for buildings matching delineation Phase 2 logic
        for bldg_feat in bldg_layer.getFeatures():
            geom = bldg_feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            candidate_eas = ea_index.intersects(geom.boundingBox())
            for ea_id in candidate_eas:
                ea_feat = ea_by_id.get(ea_id)
                if not ea_feat:
                    continue
                ea_geom = ea_feat.geometry()
                if not (ea_geom.contains(geom) or ea_geom.intersects(geom)):
                    continue

                bldg_counts[ea_id] += 1

                # Delineation logic: fallback to 1.0 if null/empty/<=0/non-numeric
                pop_val = bldg_feat.attribute(bldg_hh_idx)
                if pop_val is None or (isinstance(pop_val, QVariant) and pop_val.isNull()) or str(pop_val).strip() == "":
                    pop_val_float = 1.0
                else:
                    try:
                        pop_val_float = float(pop_val)
                        if pop_val_float <= 0.0:
                            pop_val_float = 1.0
                    except (TypeError, ValueError):
                        pop_val_float = 1.0

                hh_updates[ea_id] += pop_val_float

        if sum(bldg_counts.values()) == 0:
            QMessageBox.warning(
                self,
                "No Building Matches",
                "No building points were found inside the EA polygons."
            )
            return

        # Check for base hhcount field (parent EA candidate baseline) and parent grouping field
        base_hh_field = None
        for i in range(prev_fields.count()):
            name_lower = prev_fields.at(i).name().lower()
            if name_lower in ["hhcount", "original_hhcount", "household", "household_count", "pop", "population", "new_hhcount", "hh_cnt"]:
                base_hh_field = prev_fields.at(i).name()
                break

        parent_code_field = None
        for i in range(prev_fields.count()):
            name_lower = prev_fields.at(i).name().lower()
            if name_lower in ["code", "parent_ean", "parent_code", "orig_code", "original_code", "orig_ean", "ean", "ea_code", "name"]:
                parent_code_field = prev_fields.at(i).name()
                break

        bgy_field = None
        for i in range(prev_fields.count()):
            name_lower = prev_fields.at(i).name().lower()
            if name_lower in ["barangay", "bgy", "brgy", "bgy_code", "barangay_code", "bgy_name", "barangay_name"]:
                bgy_field = prev_fields.at(i).name()
                break

        # Group all EA features by parent key to proportionally scale sub-EAs
        groups = {}
        for ea_id, feat in ea_by_id.items():
            base_hh = None
            if base_hh_field:
                val = feat.attribute(base_hh_field)
                try:
                    if val is not None and str(val).strip() not in ("", "NULL", "None"):
                        base_hh = float(val)
                except (TypeError, ValueError):
                    base_hh = None

            p_code = ""
            if parent_code_field:
                p_code = str(feat.attribute(parent_code_field) or "").strip()

            bgy_val = ""
            if bgy_field:
                bgy_val = str(feat.attribute(bgy_field) or "").strip()

            if p_code:
                group_key = f"{bgy_val}_{p_code}"
            elif base_hh is not None and base_hh > 0:
                group_key = f"{bgy_val}_{base_hh:.2f}"
            else:
                group_key = f"single_{ea_id}"

            if group_key not in groups:
                groups[group_key] = {"base_hh": base_hh, "ea_ids": []}
            elif groups[group_key]["base_hh"] is None and base_hh is not None:
                groups[group_key]["base_hh"] = base_hh
            groups[group_key]["ea_ids"].append(ea_id)

        # Apply proportional scaling (Solution 2 - Largest Remainder / Hare-Niemeyer method)
        # Guarantees that the sum of sub-EA hh_count strictly equals base hhcount
        final_hh_updates = {}
        for group in groups.values():
            ea_ids = group["ea_ids"]
            base_hh = group["base_hh"]
            raw_sum = sum(hh_updates.get(eid, 0.0) for eid in ea_ids)

            if base_hh is not None and base_hh > 0:
                target_total = int(round(base_hh))
                if raw_sum > 0:
                    quotas = [(hh_updates.get(eid, 0.0) * target_total) / raw_sum for eid in ea_ids]
                    int_parts = [int(math.floor(q)) for q in quotas]
                    remainder = target_total - sum(int_parts)

                    fractions = [(quotas[i] - int_parts[i], i) for i in range(len(ea_ids))]
                    fractions.sort(key=lambda x: x[0], reverse=True)

                    for r in range(min(remainder, len(ea_ids))):
                        int_parts[fractions[r][1]] += 1

                    for i, eid in enumerate(ea_ids):
                        final_hh_updates[eid] = float(int_parts[i])
                else:
                    quotas = [target_total / len(ea_ids)] * len(ea_ids)
                    int_parts = [int(math.floor(q)) for q in quotas]
                    remainder = target_total - sum(int_parts)
                    for r in range(min(remainder, len(ea_ids))):
                        int_parts[r] += 1
                    for i, eid in enumerate(ea_ids):
                        final_hh_updates[eid] = float(int_parts[i])
            else:
                for eid in ea_ids:
                    final_hh_updates[eid] = float(round(hh_updates.get(eid, 0.0)))

        # Write values back to the EA layer
        if not prev_ea_layer.isEditable():
            prev_ea_layer.startEditing()
        hh_field_idx = prev_fields.indexOf(hh_field)
        bldg_field_idx = prev_fields.indexOf(bldg_count_field) if bldg_count_field else -1

        updated_count = 0
        for ea_id in ea_by_id.keys():
            feat = prev_ea_layer.getFeature(ea_id)
            if feat.isValid():
                if ea_id in final_hh_updates and hh_field_idx != -1:
                    prev_ea_layer.changeAttributeValue(ea_id, hh_field_idx, final_hh_updates[ea_id])
                if bldg_field_idx != -1:
                    prev_ea_layer.changeAttributeValue(ea_id, bldg_field_idx, int(bldg_counts.get(ea_id, 0)))
                updated_count += 1

        if prev_ea_layer.commitChanges():
            QMessageBox.information(
                self,
                "Counts Updated",
                f"Updated hh_count and bldg_count for {updated_count} EA(s) from building points."
            )
            self.generate_preview()
        else:
            QMessageBox.critical(
                self,
                "Update Failed",
                "Failed to save hh_count and bldg_count updates to the EA layer. Check layer edit permissions."
            )

    fill_missing_hhcount = fill_missing_hh_count

    def _create_ea_refresh(self):
        """Reset and refresh Tab 2 (Create Enumeration Areas) inputs, processes, and results."""
        # 1. Reset layer combos
        for combo in [
            getattr(self, 'bar_combo', None),
            getattr(self, 'bldg_combo', None),
            getattr(self, 'prev_ea_combo', None),
            getattr(self, 'road_combo', None),
            getattr(self, 'river_combo', None),
        ]:
            if combo:
                self._safe_set_layer(combo, None)

        # 2. Reset parameters to default
        if hasattr(self, 'enable_thresholds_chk'):
            self.enable_thresholds_chk.setChecked(False)
        if hasattr(self, 'min_hh_spin'):
            self.min_hh_spin.setValue(99)
        if hasattr(self, 'max_hh_spin'):
            self.max_hh_spin.setValue(300)
        if hasattr(self, 'tolerance_spin'):
            self.tolerance_spin.setValue(15.0)
        if hasattr(self, 'compact_chk'):
            self.compact_chk.setChecked(True)
        if hasattr(self, 'allow_candidate_merge_chk'):
            self.allow_candidate_merge_chk.setChecked(True)
        if hasattr(self, 'sliver_combo'):
            self.sliver_combo.setCurrentIndex(0)
        if hasattr(self, 'crs_widget'):
            self.crs_widget.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        if hasattr(self, 'params_group') and hasattr(self.params_group, 'setCollapsed'):
            self.params_group.setCollapsed(True)

        # 3. Reset output folder, preview labels, line edits and search filter
        if hasattr(self, 'output_folder_widget'):
            self.output_folder_widget.setFilePath("")
        if hasattr(self, 'out_delineated_lbl'):
            self.out_delineated_lbl.setText("• Delineated EAs: <i>-</i>")
        if hasattr(self, 'out_merged_lbl'):
            self.out_merged_lbl.setText("• Merged EAs: <i>-</i>")
        if hasattr(self, 'out_splitting_lines_lbl'):
            self.out_splitting_lines_lbl.setText("• Splitting Lines: <i>-</i>")
        for edit in [
            getattr(self, 'delineated_edit', None),
            getattr(self, 'merged_edit', None),
            getattr(self, 'delin_cand_edit', None),
            getattr(self, 'merge_cand_edit', None),
            getattr(self, 'extracted_bldg_edit', None),
            getattr(self, 'search_edit', None),
        ]:
            if edit:
                edit.clear()

        # 4. Auto-detect layers from project
        self.auto_detect_layers()

        # 5. Reset process states
        if hasattr(self, 'progress_bar'):
            self.progress_bar.setValue(0)
        if hasattr(self, 'cancel_btn'):
            self.cancel_btn.setEnabled(False)
        if hasattr(self, 'run_btn'):
            self.run_btn.setEnabled(True)
        if hasattr(self, 'status_banner'):
            self.status_banner.setText("Ready to run algorithm.")

        # 6. Reset candidates, preview tables, KPI cards, logs
        self.all_delineation_candidates.clear()
        self.all_merge_candidates.clear()
        if hasattr(self, 'kpi_delin_val'):
            self.kpi_delin_val.setText("0")
        if hasattr(self, 'kpi_merge_val'):
            self.kpi_merge_val.setText("0")
        if hasattr(self, 'delineation_table'):
            self.delineation_table.setRowCount(0)
        if hasattr(self, 'merge_table'):
            self.merge_table.setRowCount(0)
        if hasattr(self, 'log_console'):
            self.log_console.clear()
        if hasattr(self, 'tab_widget'):
            self.tab_widget.setCurrentIndex(0)

        # 7. Auto-generate candidate preview if previous EA layer is detected
        if hasattr(self, 'prev_ea_combo') and self._safe_get_layer(self.prev_ea_combo):
            self.generate_preview()

    def auto_detect_layers(self):
        """Scan all loaded layers in QGIS project and automatically match inputs by name keywords.

        Uses QgsMapLayerComboBox.setLayer() (the correct PyQGIS API) instead of
        findText()/setCurrentIndex(), which is unreliable on proxy-model-backed combo boxes.
        Priority ordering within each geometry type ensures the most specific keyword match
        wins (e.g. gap/overlap before generic barangay/EA keywords for polygons).
        """
        layers = list(QgsProject.instance().mapLayers().values())

        barangay_keywords = ["barangay", "bgy", "brgy", "boundary", "admin"]
        building_keywords = ["building", "bldg", "point", "household", "hh", "structure"]
        pravea_keywords   = ["previous", "prev", "ea", "enumeration"]
        road_keywords     = ["road", "highway", "street", "way", "route"]
        river_keywords    = ["river", "stream", "water", "drainage", "creek"]

        # Candidates: first match per slot wins (order of iteration = layer panel order)
        candidates = {
            "bar":      None,
            "bldg":     None,
            "prev_ea":  None,
            "road":     None,
            "river":    None,
        }

        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            name_lower = layer.name().lower()
            geom = layer.geometryType()

            if geom == 2:  # Polygon
                if candidates["bar"] is None and any(k in name_lower for k in barangay_keywords) \
                        and not any(k in name_lower for k in pravea_keywords):
                    candidates["bar"] = layer
                elif candidates["prev_ea"] is None and any(k in name_lower for k in pravea_keywords):
                    candidates["prev_ea"] = layer

            elif geom == 0:  # Point
                if candidates["bldg"] is None and any(k in name_lower for k in building_keywords):
                    candidates["bldg"] = layer

            elif geom == 1:  # Line
                if candidates["river"] is None and any(k in name_lower for k in river_keywords):
                    candidates["river"] = layer
                elif candidates["road"] is None and any(k in name_lower for k in road_keywords):
                    candidates["road"] = layer

        # Apply detected layers using the correct QgsMapLayerComboBox API
        if candidates["bar"]:
            self._safe_set_layer(self.bar_combo, candidates["bar"])
        if candidates["bldg"]:
            self._safe_set_layer(self.bldg_combo, candidates["bldg"])
        if candidates["prev_ea"]:
            self._safe_set_layer(self.prev_ea_combo, candidates["prev_ea"])
        if candidates["road"]:
            self._safe_set_layer(self.road_combo, candidates["road"])
        if candidates["river"]:
            self._safe_set_layer(self.river_combo, candidates["river"])

        # Auto-detect designated output folder if not yet set
        if hasattr(self, 'output_folder_widget'):
            current_out = self.output_folder_widget.filePath().strip()
            if not current_out:
                ref_layer = candidates["prev_ea"] or candidates["bar"]
                if ref_layer:
                    src = getattr(ref_layer, 'source', lambda: '')() if hasattr(ref_layer, 'source') else ''
                    clean_src = src.split("|")[0].strip() if src else ""
                    if clean_src and os.path.exists(clean_src):
                        self.output_folder_widget.setFilePath(os.path.dirname(clean_src))

        self.validate_layer_inputs()

    def auto_arrange_and_detect_layers(self):
        """Auto-arrange project layer tree, apply QML styles, and auto-detect input layers."""
        try:
            from .auto_arrange import auto_arrange_layers
            res = auto_arrange_layers(iface=getattr(self, 'iface', None))
            self._pre_ea_auto_detect_layers()
            self.auto_detect_layers()
            self._ea_merge_auto_detect_ea_layer()
            if hasattr(self, 'log_console'):
                self.log_console.append(
                    f"<span style='color: #0969da; font-weight: bold;'>[INFO]</span> "
                    f"Auto Arrange completed: {res['total']} layers processed ({res['styled']} styled, {res['reordered']} reordered)."
                )
        except Exception as e:
            QgsMessageLog.logMessage(f"Auto Arrange error: {e}", "GEMMA", Qgis.Warning)
            self._pre_ea_auto_detect_layers()
            self.auto_detect_layers()
            self._ea_merge_auto_detect_ea_layer()

    def validate_layer_inputs(self):
        """Perform validation on selected layers and show dynamic status subtitles."""
        # 1. Barangay Layer
        bar_layer = self._safe_get_layer(self.bar_combo)
        if not bar_layer:
            self.bar_status_lbl.setText("Barangay Layer is required.")
        else:
            self.bar_status_lbl.setText(f"Active: {bar_layer.featureCount()} polygons loaded ({bar_layer.crs().authid()}).")

        # 2. Building Layer
        bldg_layer = self._safe_get_layer(self.bldg_combo)
        if not bldg_layer:
            self.bldg_status_lbl.setText("Building Point Layer is required.")
        else:
            fields = [f.name().lower() for f in bldg_layer.fields()]
            hh_found = any(f in fields for f in ["hhcount", "hh_count", "household", "household_count"])
            hh_msg = " (found hhcount)" if hh_found else " (no hhcount field)"
            self.bldg_status_lbl.setText(f"Active: {bldg_layer.featureCount()} points loaded{hh_msg}.")

        # 3. Previous EA Layer
        prev_ea_layer = self._safe_get_layer(self.prev_ea_combo)
        hh_found = False
        ean_found = False
        if not prev_ea_layer:
            self.prev_ea_status_lbl.setText("Previous EA Layer is required.")
        else:
            fields = [f.name().lower() for f in prev_ea_layer.fields()]
            hh_found = "hh_count" in fields
            ean_found = any(f in fields for f in ["ean", "ea_number", "ea_code", "id", "geocode"])

            if not hh_found:
                self.prev_ea_status_lbl.setText("Error: Missing 'hh_count' field.")
            elif not ean_found:
                self.prev_ea_status_lbl.setText("Error: Missing 'ean' or 'ea_number' geocode field.")
            else:
                self.prev_ea_status_lbl.setText(f"Active: {prev_ea_layer.featureCount()} EAs loaded successfully.")

        # Enable fill-missing button only when required layers are present
        self.fill_missing_btn.setEnabled(bool(prev_ea_layer and bldg_layer and hh_found))
        road_layer = self._safe_get_layer(self.road_combo)
        if not road_layer:
            self.road_status_lbl.setText("Optional: Road boundary snapping will be skipped.")
        else:
            self.road_status_lbl.setText(f"Active: {road_layer.featureCount()} line features loaded.")

        # 5. River Layer (Optional)
        river_layer = self._safe_get_layer(self.river_combo)
        if not river_layer:
            self.river_status_lbl.setText("Optional: River boundary snapping will be skipped.")
        else:
            self.river_status_lbl.setText(f"Active: {river_layer.featureCount()} line features loaded.")


            
        # Update output layer placeholders and preview labels using 5-digit geocode prefix
        geo5 = self._extract_5digit_geocode()
        if geo5:
            if hasattr(self, 'out_delineated_lbl'):
                self.out_delineated_lbl.setText(f"• Delineated EAs: <b>{geo5}_delineated_ea2026.gpkg</b>")
            if hasattr(self, 'out_merged_lbl'):
                self.out_merged_lbl.setText(f"• Merged EAs: <b>{geo5}_merged_ea2026.gpkg</b>")
            if hasattr(self, 'out_splitting_lines_lbl'):
                self.out_splitting_lines_lbl.setText(f"• Proposed Splitting Lines: <b>{geo5}_eadel_update.gpkg</b>")

            if hasattr(self, 'delineated_edit'):
                self.delineated_edit.setPlaceholderText(f"{geo5}_delineated_ea2026")
            if hasattr(self, 'merged_edit'):
                self.merged_edit.setPlaceholderText(f"{geo5}_merged_ea2026")
            if hasattr(self, 'delin_cand_edit'):
                self.delin_cand_edit.setPlaceholderText(f"{geo5}_delineation_candidates")
            if hasattr(self, 'merge_cand_edit'):
                self.merge_cand_edit.setPlaceholderText(f"{geo5}_merge_candidates")
            if hasattr(self, 'extracted_bldg_edit'):
                self.extracted_bldg_edit.setPlaceholderText(f"{geo5}_extracted_bldgpts")
        else:
            if hasattr(self, 'out_delineated_lbl'):
                self.out_delineated_lbl.setText("• Delineated EAs: <i>-</i>")
            if hasattr(self, 'out_merged_lbl'):
                self.out_merged_lbl.setText("• Merged EAs: <i>-</i>")
            if hasattr(self, 'out_splitting_lines_lbl'):
                self.out_splitting_lines_lbl.setText("• Proposed Splitting Lines: <i>-</i>")

            if hasattr(self, 'delineated_edit'):
                self.delineated_edit.setPlaceholderText("[Temporary Scratch Layer]")
            if hasattr(self, 'merged_edit'):
                self.merged_edit.setPlaceholderText("[Temporary Scratch Layer]")
            if hasattr(self, 'delin_cand_edit'):
                self.delin_cand_edit.setPlaceholderText("[Temporary Scratch Layer]")
            if hasattr(self, 'merge_cand_edit'):
                self.merge_cand_edit.setPlaceholderText("[Temporary Scratch Layer]")
            if hasattr(self, 'extracted_bldg_edit'):
                self.extracted_bldg_edit.setPlaceholderText("[Temporary Scratch Layer]")

        # Validate designated output folder
        has_output = bool(self.output_folder_widget.filePath().strip()) if hasattr(self, 'output_folder_widget') else False
        can_run = bool(bar_layer and bldg_layer and prev_ea_layer and hh_found and ean_found and has_output)
        if hasattr(self, 'run_btn'):
            self.run_btn.setEnabled(can_run)

        self.trigger_auto_refresh()

    def generate_preview(self):
        """Generates visual candidates table preview dynamically before execution."""
        if not hasattr(self, "delineation_table") or not hasattr(self, "merge_table"):
            return

        prev_ea_layer = self._safe_get_layer(self.prev_ea_combo)
        if not prev_ea_layer:
            self.kpi_delin_val.setText("0")
            self.kpi_merge_val.setText("0")
            self.delineation_table.setRowCount(0)
            self.merge_table.setRowCount(0)
            return

        # Visual feedback during preview calculation
        self.kpi_delin_val.setText("Scanning...")
        self.kpi_merge_val.setText("Scanning...")
        self.run_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.detect_btn.setEnabled(False)
        QCoreApplication.processEvents()

        self.all_delineation_candidates.clear()
        self.all_merge_candidates.clear()

        min_hh = self.min_hh_spin.value()
        max_hh = self.max_hh_spin.value()

        fields = prev_ea_layer.fields()

        # Resolve household field index case-insensitively with hh_count (computed count) taking priority
        hh_idx = -1
        for candidate in ["hh_count", "new_hhcount", "hhcount", "household", "household_count", "pop", "population"]:
            for i in range(fields.count()):
                if fields.at(i).name().lower() == candidate:
                    hh_idx = i
                    break
            if hh_idx != -1:
                break
                
        # Resolve EA ID field index
        ean_idx = -1
        for i in range(fields.count()):
            name_lower = fields.at(i).name().lower()
            if name_lower in ["ean", "ea_number", "ea_code", "id", "geocode"]:
                ean_idx = i
                break

        # Resolve Barangay name field index
        bgy_name_idx = -1
        for i in range(fields.count()):
            name_lower = fields.at(i).name().lower()
            if name_lower in ["barangay", "bgy", "brgy", "barangay_name", "bgy_name", "brgy_name", "barangay_n", "bgy_n", "brgy_n"]:
                bgy_name_idx = i
                break
        
        # Resolve eadel_indi and merge_indi field indices
        eadel_indi_idx = -1
        merge_indi_idx = -1
        for i in range(fields.count()):
            name_lower = fields.at(i).name().lower()
            if name_lower in ("eadel_indi", "indicator"):
                eadel_indi_idx = i
            elif name_lower == "merge_indi":
                merge_indi_idx = i
        
        if hh_idx == -1 or ean_idx == -1:
            self.kpi_delin_val.setText("0")
            self.kpi_merge_val.setText("0")
            self.run_btn.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.detect_btn.setEnabled(True)
            return

        total_hh = 0.0
        ea_count = 0

        # Loop with responsive chunking to prevent QGIS from hanging
        for idx, feat in enumerate(prev_ea_layer.getFeatures()):
            if idx > 0 and idx % 100 == 0:
                QCoreApplication.processEvents()

            ean_val = feat.attribute(ean_idx)
            ean_str = str(ean_val).strip() if ean_val is not None else ""
            if ean_str.endswith(".0"):
                ean_str = ean_str[:-2]

            ea_name_str = self._get_ea_name(feat, ean_str, fields)

            bgy_name_val = feat.attribute(bgy_name_idx) if bgy_name_idx != -1 else ""
            if bgy_name_val is None or bgy_name_val == NULL:
                bgy_name_str = "Unknown"
            else:
                bgy_name_str = str(bgy_name_val).strip()
                if bgy_name_str.endswith(".0"):
                    bgy_name_str = bgy_name_str[:-2]

            hh_val = feat.attribute(hh_idx)
            try:
                hh = float(hh_val) if hh_val is not None else 0.0
            except Exception:
                hh = 0.0

            total_hh += hh
            ea_count += 1

            # Classify candidates:
            #   HH >= max_hh  → Delineation candidate (over-populated EA)
            #   Explicit field indicator ("for delineation") → Delineation candidate
            #   HH <= min_hh  → Merge candidate (under-populated EA)
            #   Explicit field indicator ("for merging") → Merge candidate
            is_delin = (hh >= max_hh)
            if not is_delin and eadel_indi_idx != -1:
                val = feat.attribute(eadel_indi_idx)
                if val is not None and str(val).strip().lower() in ("for delineation", "for_delineation"):
                    is_delin = True

            is_merge = False
            if not is_delin and merge_indi_idx != -1:
                val = feat.attribute(merge_indi_idx)
                if val is not None and str(val).strip().lower() in ("for merging", "for_merging"):
                    is_merge = True

            # Default: under-populated EAs (HH <= min_hh) are merge candidates.
            if not is_delin and not is_merge:
                is_merge = (hh <= min_hh)

            if is_delin:
                self.all_delineation_candidates.append((ean_str, ea_name_str, bgy_name_str, hh, f"Delineation (>= {max_hh} HH)"))
            elif is_merge:
                self.all_merge_candidates.append((ean_str, ea_name_str, bgy_name_str, hh, f"Initiator (<= {min_hh} HH)"))

        # Update KPI Dashboard Stats
        self.kpi_delin_val.setText(str(len(self.all_delineation_candidates)))
        self.kpi_merge_val.setText(str(len(self.all_merge_candidates)))
        
        # Trigger initial preview populates
        self.filter_previews()

        # Re-enable controls
        has_out = bool(self.output_folder_widget.filePath().strip()) if hasattr(self, 'output_folder_widget') else False
        can_run = bool(prev_ea_layer and has_out)
        self.run_btn.setEnabled(can_run)
        self.refresh_btn.setEnabled(True)
        self.detect_btn.setEnabled(True)

    def filter_previews(self):
        """Filter table rows dynamically based on user search box input."""
        query = self.search_edit.text().strip().lower()
        
        filtered_delin = []
        for row in self.all_delineation_candidates:
            if not query or query in row[0].lower() or query in row[1].lower() or query in row[2].lower() or (len(row) > 4 and query in row[4].lower()):
                filtered_delin.append(row)
                
        filtered_merge = []
        for row in self.all_merge_candidates:
            if not query or query in row[0].lower() or query in row[1].lower() or query in row[2].lower() or (len(row) > 4 and query in row[4].lower()):
                filtered_merge.append(row)

        self._populate_table_rows(self.delineation_table, filtered_delin, is_delineation=True)
        self._populate_table_rows(self.merge_table, filtered_merge, is_delineation=False)

    def _populate_table_rows(self, table, candidates, is_delineation=True):
        table.setRowCount(0)
        show_records = candidates[:100]
        table.setRowCount(len(show_records))
        
        # Decide pastel colors based on theme
        bg_col = "#ffebe9" if is_delineation else "#dafbe1"
        fg_col = "#cf222e" if is_delineation else "#1a7f37"
        if getattr(self, "current_theme", "light") == "dark":
            bg_col = "#3d2121" if is_delineation else "#1e3f28"
            fg_col = "#ff6b6b" if is_delineation else "#2ecc71"

        for row_idx, record in enumerate(show_records):
            ean_str, ea_name_str, bgy_name_str, hh = record[:4]
            role_str = record[4] if len(record) > 4 else ("Delineation Candidate" if is_delineation else "Merge Candidate")
            
            item_ean = QTableWidgetItem(ean_str)
            item_bgy = QTableWidgetItem(bgy_name_str)
            item_name = QTableWidgetItem(ea_name_str)
            item_hh = QTableWidgetItem(f"{hh:.0f}")
            item_role = QTableWidgetItem(role_str)
            
            item_ean.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_bgy.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_hh.setTextAlignment(Qt.AlignCenter)
            item_role.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            
            for item in [item_ean, item_name, item_bgy, item_hh, item_role]:
                item.setBackground(QColor(bg_col))
                item.setForeground(QColor(fg_col))
            
            table.setItem(row_idx, 0, item_ean)
            table.setItem(row_idx, 1, item_bgy)
            table.setItem(row_idx, 2, item_name)
            table.setItem(row_idx, 3, item_hh)
            table.setItem(row_idx, 4, item_role)

    # ── Console Controls ───────────────────────────────────────────────────

    def log_console_clear(self):
        """Clear output console logs."""
        self.log_console.clear()

    def copy_logs_to_clipboard(self):
        """Copy all console texts to Clipboard without polluting console logs."""
        clipboard = QCoreApplication.instance().clipboard()
        clipboard.setText(self.log_console.toPlainText())
        self.copy_logs_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.copy_logs_btn.setText("Copy Logs"))





    # ── Pipeline Execution ──────────────────────────────────────────────────

    @staticmethod
    def _export_layer_to_gpkg(layer: QgsVectorLayer, file_path: str, layer_name: str) -> bool:
        """Export a vector layer to a permanent GeoPackage (.gpkg) file on disk."""
        if not layer or not layer.isValid():
            return False
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            from qgis import processing
            params = {
                "INPUT": layer,
                "OUTPUT": file_path,
                "LAYER_NAME": layer_name,
            }
            res = processing.run("native:savefeatures", params)
            if res and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                return True
        except Exception:
            pass

        try:
            from qgis.core import (
                QgsCoordinateTransformContext,
                QgsVectorFileWriter,
                QgsProject,
            )
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "GPKG"
            save_options.layerName = layer_name
            save_options.fileEncoding = "UTF-8"
            if os.path.exists(file_path):
                save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
            else:
                save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

            ctx = (
                QgsProject.instance().transformContext()
                if (QgsProject.instance() and hasattr(QgsProject.instance(), 'transformContext'))
                else QgsCoordinateTransformContext()
            )

            if hasattr(QgsVectorFileWriter, 'writeAsVectorFormatV3'):
                res = QgsVectorFileWriter.writeAsVectorFormatV3(layer, file_path, ctx, save_options)
                if res[0] == QgsVectorFileWriter.NoError:
                    return True

            if hasattr(QgsVectorFileWriter, 'writeAsVectorFormatV2'):
                res = QgsVectorFileWriter.writeAsVectorFormatV2(layer, file_path, ctx, save_options)
                if res[0] == QgsVectorFileWriter.NoError:
                    return True

            if hasattr(QgsVectorFileWriter, 'writeAsVectorFormat'):
                res = QgsVectorFileWriter.writeAsVectorFormat(layer, file_path, "UTF-8", layer.crs(), "GPKG")
                if res == QgsVectorFileWriter.NoError:
                    return True
        except Exception:
            pass

        return os.path.exists(file_path) and os.path.getsize(file_path) > 0

    def run_pipeline(self):
        """Execute processing algorithm directly using custom feedback."""
        bar_layer = self._safe_get_layer(self.bar_combo)
        bldg_layer = self._safe_get_layer(self.bldg_combo)
        prev_ea_layer = self._safe_get_layer(self.prev_ea_combo)
        road_layer = self._safe_get_layer(self.road_combo)
        river_layer = self._safe_get_layer(self.river_combo)

        if not bar_layer or not bldg_layer or not prev_ea_layer:
            self.log_console.append(
                "<span style='color:#cf222e; font-weight:bold;'>"
                "[ERROR] Please select all required inputs (Barangay, Building, Previous EA layers).</span>"
            )
            self.tab_widget.setCurrentIndex(1)
            return

        out_folder = self.output_folder_widget.filePath().strip() if hasattr(self, 'output_folder_widget') else ""
        if not out_folder:
            QMessageBox.warning(self, "Missing Output Folder", "Please designate an output folder before running.")
            if hasattr(self, 'run_btn'):
                self.run_btn.setEnabled(False)
            return

        os.makedirs(out_folder, exist_ok=True)
        geo5 = self._extract_5digit_geocode() or "00000"

        # Define permanent output layer file paths (.gpkg)
        delineated_file = os.path.normpath(os.path.join(out_folder, f"{geo5}_delineated_ea2026.gpkg")).replace("\\", "/")
        merged_file = os.path.normpath(os.path.join(out_folder, f"{geo5}_merged_ea2026.gpkg")).replace("\\", "/")

        # Prepare parameters: Execute algorithm in-memory first; permanent .gpkg files are created ONLY if features exist
        parameters = {
            'BARANGAY_INPUT': bar_layer,
            'BUILDING_INPUT': bldg_layer,
            'PREVIOUS_EA_INPUT': prev_ea_layer,
            'ROAD_INPUT': road_layer,
            'RIVER_INPUT': river_layer,
            'SNAP_TOLERANCE': self.tolerance_spin.value(),
            'ENABLE_THRESHOLDS': self.enable_thresholds_chk.isChecked(),
            'MIN_HOUSEHOLD': self.min_hh_spin.value(),
            'MAX_HOUSEHOLD': self.max_hh_spin.value(),
            'SPLIT_STRATEGY': 0,
            'SPLIT_TYPE': 0,
            'USE_COMPACTNESS': self.compact_chk.isChecked(),
            'ALLOW_CANDIDATE_MERGE': self.allow_candidate_merge_chk.isChecked(),
            'SLIVER_THRESHOLD': self.sliver_combo.currentIndex(),
            'TARGET_CRS': self.crs_widget.crs(),
            'PREVIEW_ONLY': False,
            
            # Temporary scratch sinks during processing execution
            'DELINEATED_OUTPUT': 'TEMPORARY_OUTPUT',
            'MERGED_OUTPUT': 'TEMPORARY_OUTPUT',
            'DELINEATION_CANDIDATE_OUTPUT': 'TEMPORARY_OUTPUT',
            'MERGE_CANDIDATE_OUTPUT': 'TEMPORARY_OUTPUT',
            'EXTRACTED_BUILDINGS_OUTPUT': 'TEMPORARY_OUTPUT',
        }

        # Clear UI state
        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.tab_widget.setCurrentIndex(1)
        self.status_banner.setText("⏳ Processing algorithm... Please wait.")

        self.log_console.append("<span style='color:#1a7f37; font-weight:bold;'>[START] Starting EA Delineation and Merging...</span>")
        self.log_console.append(f"<span style='color:#0969da; font-weight:bold;'>[INFO] Designated Output Folder: {out_folder}</span>")
        QCoreApplication.processEvents()

        # Instantiate feedback
        self.feedback = CustomProcessingFeedback(self.progress_bar, self.log_console, self.run_btn, self.cancel_btn)
        self.feedback.progressChanged.connect(lambda val: self.feedback.helper.set_val.emit(int(val)))
        context = QgsProcessingContext()

        # Execute using QGIS Processing framework
        from qgis import processing
        from qgis.core import QgsApplication
        
        alg_to_run = QgsApplication.processingRegistry().algorithmById(self.ALGORITHM_ID) or self.algo
        
        try:
            results = processing.runAndLoadResults(
                alg_to_run,
                parameters,
                context=context,
                feedback=self.feedback
            )
            
            if self.feedback.isCanceled():
                self.log_console.append("<span style='color:#d17a00; font-weight:bold;'>[CANCEL] Pipeline execution cancelled by user.</span>")
            else:
                # Rename and organize loaded layers into structured QGIS Layer Sub-Groups
                from qgis.core import QgsProject, QgsMapLayer

                root = QgsProject.instance().layerTreeRoot()
                main_group_name = f"{geo5}_EA_Outputs"
                main_group = root.findGroup(main_group_name)
                if not main_group:
                    main_group = root.insertGroup(0, main_group_name)

                # Create structured sub-groups inside main_group in exact order:
                # 1. Reference Layers
                # 2. Splitting Lines
                # 3. EAs
                # 4. Candidates
                reference_group = main_group.findGroup("Reference Layers")
                if not reference_group:
                    reference_group = main_group.insertGroup(0, "Reference Layers")

                splitting_lines_group = main_group.findGroup("Splitting Lines")
                if not splitting_lines_group:
                    splitting_lines_group = main_group.insertGroup(1, "Splitting Lines")

                eas_group = main_group.findGroup("EAs")
                if not eas_group:
                    eas_group = main_group.insertGroup(2, "EAs")

                candidates_group = main_group.findGroup("Candidates")
                if not candidates_group:
                    candidates_group = main_group.insertGroup(3, "Candidates")

                # Ensure existing groups are sorted in top-to-bottom order: Reference Layers -> Splitting Lines -> EAs -> Candidates
                ordered_subgroups = [
                    ("Reference Layers", reference_group),
                    ("Splitting Lines", splitting_lines_group),
                    ("EAs", eas_group),
                    ("Candidates", candidates_group)
                ]
                for target_idx, (g_name, g_node) in enumerate(ordered_subgroups):
                    children = main_group.children()
                    if g_node in children:
                        curr_idx = children.index(g_node)
                        if curr_idx != target_idx:
                            cloned = g_node.clone()
                            main_group.insertChildNode(target_idx, cloned)
                            main_group.removeChildNode(g_node)
                            if g_name == "Reference Layers":
                                reference_group = cloned
                            elif g_name == "Splitting Lines":
                                splitting_lines_group = cloned
                            elif g_name == "EAs":
                                eas_group = cloned
                            elif g_name == "Candidates":
                                candidates_group = cloned

                # Output layers in exact top-to-bottom order for each group
                # tuple: (out_key, target_name, target_group, qml_filename, is_permanent, file_path)
                output_mapping_ordered = [
                    ('EXTRACTED_BUILDINGS_OUTPUT', f"{geo5}_extracted_bldgpts", reference_group, "1. Base Layer Building Points.qml", False, None),
                    ('DELINEATED_OUTPUT', f"{geo5}_delineated_ea2026", eas_group, "ea_output.qml", True, delineated_file),
                    ('MERGED_OUTPUT', f"{geo5}_merged_ea2026", eas_group, "ea_output.qml", True, merged_file),
                    ('DELINEATION_CANDIDATE_OUTPUT', f"{geo5}_delineation_candidates", candidates_group, "delineation_candidates.qml", False, None),
                    ('MERGE_CANDIDATE_OUTPUT', f"{geo5}_merge_candidates", candidates_group, "merge_candidates.qml", False, None),
                ]

                from .helpers.style import apply_qml_to_layer

                if isinstance(results, dict):
                    for out_key, target_name, target_group, qml_filename, is_perm, f_path in output_mapping_ordered:
                        if out_key in results:
                            layer_ref = results[out_key]
                            layer = None
                            if isinstance(layer_ref, str):
                                layer = QgsProject.instance().mapLayer(layer_ref)
                            elif isinstance(layer_ref, QgsMapLayer):
                                layer = layer_ref
                            
                            if layer:
                                if layer.featureCount() == 0:
                                    # If 0 features, do NOT create a permanent file and do not keep on canvas
                                    QgsProject.instance().removeMapLayer(layer.id())
                                    if f_path and os.path.exists(f_path):
                                        try:
                                            os.remove(f_path)
                                        except Exception:
                                            pass
                                    self.log_console.append(
                                        f"<span style='color:#7F8C8D;'>[INFO] Output layer '{target_name}' has 0 features; skipping layer generation.</span>"
                                    )
                                    continue

                                if is_perm and f_path:
                                    # Export to permanent GeoPackage ONLY when layer has features (> 0)
                                    if self._export_layer_to_gpkg(layer, f_path, target_name):
                                        perm_layer = QgsVectorLayer(f"{f_path}|layername={target_name}", target_name, "ogr")
                                        if not perm_layer.isValid():
                                            perm_layer = QgsVectorLayer(f_path, target_name, "ogr")
                                        
                                        if perm_layer.isValid():
                                            QgsProject.instance().removeMapLayer(layer.id())
                                            QgsProject.instance().addMapLayer(perm_layer, False)
                                            apply_qml_to_layer(perm_layer, qml_filename)
                                            target_group.addLayer(perm_layer)
                                            self.log_console.append(
                                                f"<span style='color:#0969da; font-weight:bold;'>[INFO]</span> "
                                                f"Permanent GeoPackage layer (.gpkg) saved: {target_name} ({f_path})"
                                            )
                                            continue

                                layer.setName(target_name)
                                apply_qml_to_layer(layer, qml_filename)
                                lnode = root.findLayer(layer.id())
                                if lnode:
                                    if lnode.parent() != target_group:
                                        clone = lnode.clone()
                                        target_group.addChildNode(clone)
                                        lnode.parent().removeChildNode(lnode)
                        else:
                            # Not in results dictionary (0 features produced)
                            self.log_console.append(
                                f"<span style='color:#7F8C8D;'>[INFO] Output layer '{target_name}' has 0 features; skipping layer generation.</span>"
                            )
                            # Remove any dangling layer with target_name if loaded with 0 features
                            for lyr_id, lyr_obj in list(QgsProject.instance().mapLayers().items()):
                                if lyr_obj.name() == target_name and lyr_obj.featureCount() == 0:
                                    QgsProject.instance().removeMapLayer(lyr_id)

                # Group and persist any generated splitting line layers (ending with _eadel_update) into Splitting Lines
                has_splitting_lines = False
                for layer_id, proj_layer in list(QgsProject.instance().mapLayers().items()):
                    if proj_layer.name().endswith("_eadel_update"):
                        target_line_name = proj_layer.name()
                        line_gpkg_path = os.path.normpath(os.path.join(out_folder, f"{target_line_name}.gpkg")).replace("\\", "/")
                        if proj_layer.featureCount() == 0:
                            # If 0 features, do not create permanent file and remove from project
                            QgsProject.instance().removeMapLayer(layer_id)
                            if os.path.exists(line_gpkg_path):
                                try:
                                    os.remove(line_gpkg_path)
                                except Exception:
                                    pass
                            self.log_console.append(
                                f"<span style='color:#7F8C8D;'>[INFO] Splitting lines layer '{target_line_name}' has 0 features; skipping layer generation.</span>"
                            )
                        else:
                            has_splitting_lines = True
                            # Convert in-memory splitting line layer to permanent GeoPackage on disk ONLY when it has features
                            if not proj_layer.source().lower().endswith(".gpkg"):
                                if self._export_layer_to_gpkg(proj_layer, line_gpkg_path, target_line_name):
                                    perm_line_layer = QgsVectorLayer(f"{line_gpkg_path}|layername={target_line_name}", target_line_name, "ogr")
                                    if not perm_line_layer.isValid():
                                        perm_line_layer = QgsVectorLayer(line_gpkg_path, target_line_name, "ogr")
                                    if perm_line_layer.isValid():
                                        QgsProject.instance().removeMapLayer(layer_id)
                                        QgsProject.instance().addMapLayer(perm_line_layer, False)
                                        apply_qml_to_layer(perm_line_layer, "eadel_update_lines.qml")
                                        splitting_lines_group.addLayer(perm_line_layer)
                                        self.log_console.append(
                                            f"<span style='color:#0969da; font-weight:bold;'>[INFO]</span> "
                                            f"Permanent GeoPackage layer (.gpkg) saved: {target_line_name} ({line_gpkg_path})"
                                        )
                                        continue

                            lnode = root.findLayer(layer_id)
                            if lnode and lnode.parent() != splitting_lines_group:
                                clone = lnode.clone()
                                splitting_lines_group.addChildNode(clone)
                                lnode.parent().removeChildNode(lnode)

                # Clean up empty sub-groups if no layers were added to them
                for g_name, g_node in [
                    ("Reference Layers", reference_group),
                    ("Splitting Lines", splitting_lines_group),
                    ("EAs", eas_group),
                    ("Candidates", candidates_group),
                ]:
                    if g_node and len(g_node.children()) == 0:
                        main_group.removeChildNode(g_node)

                # Clean up main group if it contains no child nodes
                if len(main_group.children()) == 0:
                    root.removeChildNode(main_group)

                self.progress_bar.setValue(100)
                self.log_console.append("<span style='color:#1a7f37; font-weight:bold;'>[COMPLETE] Pipeline execution complete! Results loaded to map.</span>")

                # Update Status Banner above progress bar with clear result explanation
                delin_cnt = 0
                merged_cnt = 0
                merge_cand_cnt = 0
                if isinstance(results, dict):
                    d_ref = results.get('DELINEATED_OUTPUT')
                    m_ref = results.get('MERGED_OUTPUT')
                    mc_ref = results.get('MERGE_CANDIDATE_OUTPUT')
                    d_l = None
                    if isinstance(d_ref, str):
                        d_l = QgsProject.instance().mapLayer(d_ref)
                        delin_cnt = d_l.featureCount() if d_l else 0
                    elif isinstance(d_ref, QgsMapLayer):
                        d_l = d_ref
                        delin_cnt = d_l.featureCount()

                    forced_cnt = 0
                    if d_l:
                        sb_idx = d_l.fields().indexOf("split_by")
                        rem_idx = d_l.fields().indexOf("remarks")
                        for f in d_l.getFeatures():
                            sb_val = str(f.attribute(sb_idx)).lower() if sb_idx != -1 else ""
                            rem_val = str(f.attribute(rem_idx)).lower() if rem_idx != -1 else ""
                            if "forced" in sb_val or "forced" in rem_val:
                                forced_cnt += 1

                    if isinstance(m_ref, str):
                        m_l = QgsProject.instance().mapLayer(m_ref)
                        merged_cnt = m_l.featureCount() if m_l else 0
                    elif isinstance(m_ref, QgsMapLayer):
                        merged_cnt = m_ref.featureCount()

                    if isinstance(mc_ref, str):
                        mc_l = QgsProject.instance().mapLayer(mc_ref)
                        merge_cand_cnt = mc_l.featureCount() if mc_l else 0
                    elif isinstance(mc_ref, QgsMapLayer):
                        merge_cand_cnt = mc_ref.featureCount()

                if delin_cnt == 0 and merged_cnt == 0:
                    if merge_cand_cnt > 0:
                        if self.allow_candidate_merge_chk.isChecked():
                            banner_text = f"Notice: 0 Delineated | 0 Merged EAs — {merge_cand_cnt} merge candidate features identified."
                        else:
                            banner_text = f"Notice: 0 Delineated | 0 Merged EAs — {merge_cand_cnt} candidate EAs identified (candidate-to-candidate merging is disabled)."
                    else:
                        banner_text = "Notice: 0 Delineated | 0 Merged EAs — All starting EAs are within optimal threshold range (100–300 HH)."
                else:
                    split_detail = f" ({forced_cnt} via forced straight cut)" if forced_cnt > 0 else ""
                    banner_text = f"Success: Created {delin_cnt} Delineated EA(s){split_detail} and {merged_cnt} Merged EA(s)."

                self.status_banner.setText(banner_text)

        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.log_console.append(f"<span style='color:#cf222e; font-weight:bold;'>[FATAL] Error executing pipeline: {str(e)}</span>")
            self.log_console.append(f"<pre style='color:#cf222e; font-size:11px; font-family:Consolas, monospace;'>{tb_str}</pre>")
            self.status_banner.setText(f"Error: Pipeline execution failed — {str(e)}")
        
        finally:
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.feedback = None


    # ─────────────────────────────────────────────────────────────────────────
    # Tab 3 — Enumeration Area Merge
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ea_merge_tab(self):
        """Build the Enumeration Area Merge tab (Tab 3) and add it to main_tabs."""
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(6, 6, 6, 6)
        tab_layout.setSpacing(6)

        self._ea_merge_replacement_layers = []
        self._ea_merge_cancelled = False

        # ── Main Splitter: left (inputs+options) / right (summary+log) ────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("eaMergeSplitter")

        # ── LEFT PANEL ──────────────────────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)
        left_layout.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0)
        scroll_layout.setSpacing(10)

        # ── 1. Previous EA Layer Group ────────────────────────────────────
        ea_group = QGroupBox("Previous EA Layer")
        ea_layout = QVBoxLayout(ea_group)
        ea_layout.setContentsMargins(8, 8, 8, 8)
        ea_layout.setSpacing(6)

        self.ea_merge_detect_btn = QPushButton("Auto-detect Layers")
        self.ea_merge_detect_btn.setToolTip(
            "Scan project layers and auto-select Previous EA (*_ea*, *_ea2024, *_ea2026) layer."
        )
        self.ea_merge_detect_btn.clicked.connect(self._ea_merge_auto_detect_ea_layer)
        ea_layout.addWidget(self.ea_merge_detect_btn)

        ea_layout.addWidget(QLabel("Previous EA Layer (Polygon)*"))
        self.ea_merge_ea_combo = QgsMapLayerComboBox(self)
        self.ea_merge_ea_combo.setAllowEmptyLayer(True)
        self.ea_merge_ea_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        ea_layout.addWidget(self.ea_merge_ea_combo)

        self.ea_merge_ea_status_lbl = QLabel("No layer selected.")
        self.ea_merge_ea_status_lbl.setWordWrap(True)
        ea_layout.addWidget(self.ea_merge_ea_status_lbl)

        # Designated Output Folder
        ea_layout.addWidget(QLabel("Designated Output Folder*"))
        self.ea_merge_output_folder_widget = QgsFileWidget()
        self.ea_merge_output_folder_widget.setStorageMode(QgsFileWidget.GetDirectory)
        self.ea_merge_output_folder_widget.setDialogTitle("Designate Output Folder for Enumeration Area Merge")
        ea_layout.addWidget(self.ea_merge_output_folder_widget)
        self.ea_merge_output_folder_widget.fileChanged.connect(self._ea_merge_validate_inputs)

        scroll_layout.addWidget(ea_group)

        # ── 2. Replacement Polygon Layers (Multi Input) ───────────────────
        repl_group = QGroupBox("Replacement Polygon Layers — Multi Input")
        repl_layout = QVBoxLayout(repl_group)
        repl_layout.setContentsMargins(8, 8, 8, 8)
        repl_layout.setSpacing(6)

        repl_layout.addWidget(QLabel("Selected Replacement Layers (8-digit numeric names):"))

        self.ea_merge_layers_list = QListWidget()
        self.ea_merge_layers_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ea_merge_layers_list.setMinimumHeight(120)
        self.ea_merge_layers_list.setMaximumHeight(180)
        self.ea_merge_layers_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #BDC3C7;
                border-radius: 4px;
                background-color: white;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px 6px;
            }
        """)
        repl_layout.addWidget(self.ea_merge_layers_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.ea_merge_select_btn = QPushButton("Select Multiple Layers")
        self.ea_merge_select_btn.setToolTip("Open layer picker to select one or more 8-digit replacement polygon layers.")
        self.ea_merge_select_btn.clicked.connect(self._ea_merge_select_layers)
        btn_row.addWidget(self.ea_merge_select_btn)

        self.ea_merge_clear_btn = QPushButton("Clear")
        self.ea_merge_clear_btn.setToolTip("Clear selected replacement layers list.")
        self.ea_merge_clear_btn.clicked.connect(self._ea_merge_clear_layers)
        btn_row.addWidget(self.ea_merge_clear_btn)

        repl_layout.addLayout(btn_row)

        # Validation Checklist Indicators
        val_frame = QFrame()
        val_frame.setFrameShape(QFrame.StyledPanel)
        val_frame.setStyleSheet("background-color: #F8F9FA; border: 1px solid #E2E8F0; border-radius: 4px; padding: 4px;")
        val_layout = QVBoxLayout(val_frame)
        val_layout.setContentsMargins(6, 4, 6, 4)
        val_layout.setSpacing(2)

        val_title = QLabel("<b>Validation Checklist:</b>")
        val_layout.addWidget(val_title)

        self.ea_merge_val_poly_lbl = QLabel("• Polygon layers: -")
        self.ea_merge_val_poly_lbl.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        val_layout.addWidget(self.ea_merge_val_poly_lbl)

        self.ea_merge_val_name_lbl = QLabel("• 8-digit layer names: -")
        self.ea_merge_val_name_lbl.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        val_layout.addWidget(self.ea_merge_val_name_lbl)

        self.ea_merge_val_geom_lbl = QLabel("• Valid geometries: -")
        self.ea_merge_val_geom_lbl.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        val_layout.addWidget(self.ea_merge_val_geom_lbl)

        repl_layout.addWidget(val_frame)
        scroll_layout.addWidget(repl_group)

        # ── 3. Output Preview Group ───────────────────────────────────────
        out_group = QGroupBox("Output Preview")
        out_layout = QVBoxLayout(out_group)
        out_layout.setContentsMargins(8, 8, 8, 8)
        out_layout.setSpacing(4)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.addWidget(QLabel("Geographic Code:"), 0, 0)
        self.ea_merge_out_geocode_lbl = QLabel("-")
        self.ea_merge_out_geocode_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        grid.addWidget(self.ea_merge_out_geocode_lbl, 0, 1)

        grid.addWidget(QLabel("Output Layer:"), 1, 0)
        self.ea_merge_out_layer_lbl = QLabel("-")
        self.ea_merge_out_layer_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        grid.addWidget(self.ea_merge_out_layer_lbl, 1, 1)

        grid.addWidget(QLabel("Excel Output:"), 2, 0)
        self.ea_merge_out_excel_lbl = QLabel("-")
        self.ea_merge_out_excel_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold))
        grid.addWidget(self.ea_merge_out_excel_lbl, 2, 1)

        out_layout.addLayout(grid)
        scroll_layout.addWidget(out_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        left_widget.setMinimumWidth(330)
        splitter.addWidget(left_widget)

        # ── RIGHT PANEL ─────────────────────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(8)

        self.ea_merge_right_tabs = QTabWidget()
        self.ea_merge_right_tabs.setObjectName("eaMergeRightTabs")
        right_tabs = self.ea_merge_right_tabs

        # ── Summary Tab ─────────────────────────────────────────────────
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(8)

        summary_title = QLabel("Enumeration Area Merge Summary")
        summary_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        summary_layout.addWidget(summary_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        summary_layout.addWidget(sep)

        sum_grid = QGridLayout()
        sum_grid.setSpacing(4)
        sum_grid.setColumnStretch(1, 1)

        def _add_ea_merge_sum_row(label_text, row_idx):
            lbl = QLabel(label_text)
            val = QLabel("-")
            val.setFont(QFont("Segoe UI", 9, QFont.Bold))
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            sum_grid.addWidget(lbl, row_idx, 0)
            sum_grid.addWidget(val, row_idx, 1)
            return val

        self._ea_merge_sum_geocode_val = _add_ea_merge_sum_row("Geographic Code:", 0)
        self._ea_merge_sum_ea_input_val = _add_ea_merge_sum_row("Previous EA Layer:", 1)
        self._ea_merge_sum_repl_layers_val = _add_ea_merge_sum_row("Replacement Layers:", 2)
        self._ea_merge_sum_repl_feats_val = _add_ea_merge_sum_row("Replacement Features:", 3)
        self._ea_merge_sum_mod_eas_val = _add_ea_merge_sum_row("Modified EA Features:", 4)
        self._ea_merge_sum_final_eas_val = _add_ea_merge_sum_row("Final EA Features:", 5)
        self._ea_merge_sum_output_val = _add_ea_merge_sum_row("Output Layer:", 6)
        self._ea_merge_sum_excel_val = _add_ea_merge_sum_row("Excel Output:", 7)

        summary_layout.addLayout(sum_grid)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        summary_layout.addWidget(sep2)

        self._ea_merge_sum_status_lbl = QLabel("Status: READY")
        self._ea_merge_sum_status_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        summary_layout.addWidget(self._ea_merge_sum_status_lbl)
        summary_layout.addStretch()

        right_tabs.addTab(summary_tab, "Summary")

        # ── Log Tab ─────────────────────────────────────────────────────
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(6, 6, 6, 6)
        log_layout.setSpacing(4)

        log_controls = QHBoxLayout()
        log_controls.addWidget(QLabel("Processing Log:"))
        log_controls.addStretch()
        self.ea_merge_copy_log_btn = QPushButton("Copy Log")
        self.ea_merge_copy_log_btn.setToolTip("Copy processing log to clipboard.")
        self.ea_merge_copy_log_btn.clicked.connect(self._ea_merge_copy_log)
        log_controls.addWidget(self.ea_merge_copy_log_btn)
        self.ea_merge_clear_log_btn = QPushButton("Clear")
        self.ea_merge_clear_log_btn.setToolTip("Clear the processing log.")
        self.ea_merge_clear_log_btn.clicked.connect(lambda: self.ea_merge_log_console.clear())
        log_controls.addWidget(self.ea_merge_clear_log_btn)
        log_layout.addLayout(log_controls)

        self.ea_merge_log_console = QTextEdit()
        self.ea_merge_log_console.setObjectName("eaMergeLogConsole")
        self.ea_merge_log_console.setReadOnly(True)
        log_layout.addWidget(self.ea_merge_log_console)

        right_tabs.addTab(log_tab, "Processing Log")

        right_layout.addWidget(right_tabs)
        right_widget.setMinimumWidth(480)
        splitter.addWidget(right_widget)

        # ── Description Panel (third splitter pane) ──────────────────────
        self.ea_merge_desc_panel = QWidget()
        desc_panel_layout = QVBoxLayout(self.ea_merge_desc_panel)
        desc_panel_layout.setContentsMargins(4, 4, 4, 4)
        desc_panel_layout.setSpacing(0)

        self.ea_merge_desc_browser = QTextBrowser()
        self.ea_merge_desc_browser.setObjectName("eaMergeDescBrowser")
        self.ea_merge_desc_browser.setOpenExternalLinks(True)
        self.ea_merge_desc_browser.setHtml(self._ea_merge_help_html())
        desc_panel_layout.addWidget(self.ea_merge_desc_browser)

        self.ea_merge_desc_panel.setMinimumWidth(240)
        splitter.addWidget(self.ea_merge_desc_panel)
        splitter.setSizes([310, 640, 260])

        tab_layout.addWidget(splitter, 1)

        # ── Bottom Bar ───────────────────────────────────────────────────
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(10, 4, 10, 6)
        bottom_layout.setSpacing(4)

        self.ea_merge_status_banner = QLabel("Ready.")
        self.ea_merge_status_banner.setWordWrap(True)
        self.ea_merge_status_banner.setFont(QFont("Segoe UI", 9, QFont.Bold))
        bottom_layout.addWidget(self.ea_merge_status_banner)

        controls_row = QHBoxLayout()
        self.ea_merge_progress_bar = QProgressBar()
        self.ea_merge_progress_bar.setRange(0, 100)
        self.ea_merge_progress_bar.setValue(0)
        self.ea_merge_progress_bar.setFixedHeight(26)
        controls_row.addWidget(self.ea_merge_progress_bar)

        self.ea_merge_cancel_btn = QPushButton("Cancel")
        self.ea_merge_cancel_btn.setMinimumWidth(80)
        self.ea_merge_cancel_btn.setFixedHeight(26)
        self.ea_merge_cancel_btn.setEnabled(False)
        self.ea_merge_cancel_btn.clicked.connect(self._ea_merge_cancel)
        controls_row.addWidget(self.ea_merge_cancel_btn)

        self.ea_merge_run_btn = QPushButton("Run")
        self.ea_merge_run_btn.setMinimumWidth(120)
        self.ea_merge_run_btn.setFixedHeight(26)
        self.ea_merge_run_btn.clicked.connect(self._ea_merge_run)
        controls_row.addWidget(self.ea_merge_run_btn)

        bottom_layout.addLayout(controls_row)
        tab_layout.addWidget(bottom)

        # Connect signals
        self.ea_merge_ea_combo.currentIndexChanged.connect(self._ea_merge_validate_inputs)

        self.main_tabs.addTab(tab_widget, "Enumeration Area Merge")

    # ─────────────────────────────────────────────────────────────────────────
    # Tab 3 — Slots & Validation
    # ─────────────────────────────────────────────────────────────────────────

    def _ea_merge_toggle_description(self):
        """Toggle the visibility of the Enumeration Area Merge description panel."""
        if not hasattr(self, 'ea_merge_desc_panel'):
            return
        is_visible = not self.ea_merge_desc_panel.isVisible()
        self.ea_merge_desc_panel.setVisible(is_visible)

        show_icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "show_description.svg")
        )
        hide_icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "hide_description.svg")
        )
        if is_visible:
            icon = QIcon(hide_icon_path) if os.path.exists(hide_icon_path) else QIcon()
            self.toggle_desc_btn.setIcon(icon)
            self.toggle_desc_btn.setToolTip("Hide Description Panel")
        else:
            icon = QIcon(show_icon_path) if os.path.exists(show_icon_path) else QIcon()
            self.toggle_desc_btn.setIcon(icon)
            self.toggle_desc_btn.setToolTip("Show Description Panel")

    @staticmethod
    def _ea_merge_help_html() -> str:
        """Return the HTML description string for the Enumeration Area Merge description panel."""
        from .ea_merge_processor import EAMergeProcessor
        return EAMergeProcessor.short_help_string()

    def _ea_merge_refresh(self):
        """Reset and refresh Tab 3 (Enumeration Area Merge) inputs, processes, and results."""
        # 1. Reset Previous EA Layer selection & output folder
        if hasattr(self, 'ea_merge_ea_combo'):
            self._safe_set_layer(self.ea_merge_ea_combo, None)
        if hasattr(self, 'ea_merge_output_folder_widget'):
            self.ea_merge_output_folder_widget.setFilePath("")

        # 2. Reset replacement layers list
        self._ea_merge_replacement_layers = []
        if hasattr(self, 'ea_merge_layers_list'):
            self.ea_merge_layers_list.clear()

        # 3. Auto-detect EA layer from project
        self._ea_merge_auto_detect_ea_layer()

        # 4. Reset process states
        if hasattr(self, 'ea_merge_progress_bar'):
            self.ea_merge_progress_bar.setValue(0)
        if hasattr(self, 'ea_merge_cancel_btn'):
            self.ea_merge_cancel_btn.setEnabled(False)
        if hasattr(self, 'ea_merge_run_btn'):
            self.ea_merge_run_btn.setEnabled(True)
        if hasattr(self, 'ea_merge_status_banner'):
            self.ea_merge_status_banner.setText("Ready.")

        # 5. Reset output preview & summary info
        for attr in ['ea_merge_out_geocode_lbl', 'ea_merge_out_layer_lbl', 'ea_merge_out_excel_lbl']:
            lbl = getattr(self, attr, None)
            if lbl:
                lbl.setText("-")
        for attr in [
            '_ea_merge_sum_geocode_val', '_ea_merge_sum_ea_input_val', '_ea_merge_sum_repl_layers_val',
            '_ea_merge_sum_repl_feats_val', '_ea_merge_sum_mod_eas_val', '_ea_merge_sum_final_eas_val',
            '_ea_merge_sum_output_val', '_ea_merge_sum_excel_val'
        ]:
            val_lbl = getattr(self, attr, None)
            if val_lbl:
                val_lbl.setText("-")
        if hasattr(self, '_ea_merge_sum_status_lbl'):
            self._ea_merge_sum_status_lbl.setText("Status: READY")

        # 6. Clear logs & set active sub-tab
        if hasattr(self, 'ea_merge_log_console'):
            self.ea_merge_log_console.clear()
        if hasattr(self, 'ea_merge_right_tabs'):
            self.ea_merge_right_tabs.setCurrentIndex(0)

    def _ea_merge_auto_detect_ea_layer(self):
        """Auto-detect Previous EA layer from the QGIS project for Tab 3."""
        import re
        pat_8 = re.compile(r"^\d{8}$")

        layers = list(QgsProject.instance().mapLayers().values())

        ea_patterns = ["_ea2024", "_ea2026", "_ea2025", "_ea2023", "_ea2022", "_ea_preprocessed", "_ea", "previous", "prev", "enumeration"]
        non_ea_keywords = ["_bgy", "barangay", "brgy", "boundary", "road", "river", "bldg", "building", "point", "gap", "overlap"]

        ea_match = None

        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            if layer.geometryType() not in (2, QgsWkbTypes.PolygonGeometry):  # Polygon
                continue
            name_lower = layer.name().lower()
            if pat_8.match(layer.name()):
                continue
            if any(k in name_lower for k in non_ea_keywords) and not any(pat in name_lower for pat in ea_patterns):
                continue

            for pat in ea_patterns:
                if pat in name_lower:
                    ea_match = layer
                    break
            if ea_match:
                break

        self._safe_set_layer(self.ea_merge_ea_combo, ea_match)

        if ea_match and hasattr(self, 'ea_merge_output_folder_widget'):
            current_out = self.ea_merge_output_folder_widget.filePath().strip()
            if not current_out:
                src = getattr(ea_match, 'source', lambda: '')() if hasattr(ea_match, 'source') else ''
                clean_src = src.split("|")[0].strip() if src else ""
                if clean_src and os.path.exists(clean_src):
                    self.ea_merge_output_folder_widget.setFilePath(os.path.dirname(clean_src))

        self._ea_merge_validate_inputs()

    def _ea_merge_select_layers(self):
        """Open the multi-layer selection dialog for Tab 3 replacement polygon layers."""
        dlg = MultiLayerSelectDialog(self, selected_layers=self._ea_merge_replacement_layers)
        if dlg.exec_() == QDialog.Accepted:
            self._ea_merge_replacement_layers = dlg.selected_layers
            self._ea_merge_update_replacement_list()
            self._ea_merge_validate_inputs()

    def _ea_merge_clear_layers(self):
        """Clear all selected replacement polygon layers for Tab 3."""
        self._ea_merge_replacement_layers = []
        self._ea_merge_update_replacement_list()
        self._ea_merge_validate_inputs()

    def _ea_merge_update_replacement_list(self):
        """Refresh the QListWidget showing the selected replacement layers."""
        self.ea_merge_layers_list.clear()
        import re
        # Accept names starting with 8 digits (with optional _suffix)
        pat = re.compile(r"^\d{8}(_|$)")
        for layer in self._ea_merge_replacement_layers:
            if not layer:
                continue
            is_valid_name = bool(pat.match(layer.name()))
            badge = "✓" if is_valid_name else "✗ [INVALID NAME]"
            item_text = f"{badge}  {layer.name()}  ({layer.featureCount()} feats)"
            item = QListWidgetItem(item_text)
            if not is_valid_name:
                item.setForeground(QColor("#CF222E"))
            else:
                item.setForeground(QColor("#1A7F37"))
            self.ea_merge_layers_list.addItem(item)

    def _ea_merge_validate_inputs(self):
        """Validate EA Input Layer and Replacement Polygon Layers and update UI indicators."""
        # Use the module-level compiled regex and imported helpers — avoids
        # per-call re.compile() and repeated relative imports on every event.
        pat = _EA_MERGE_8DIGIT_RE

        ea_layer = self.ea_merge_ea_combo.currentLayer()
        repl_layers = self._ea_merge_replacement_layers

        # 1. EA Input Layer validation
        geo_code = None
        citymun = None
        if not ea_layer:
            self.ea_merge_ea_status_lbl.setText("<span style='color:#cf222e;'>Previous EA Layer is required.</span>")
        else:
            fc = ea_layer.featureCount()
            crs_str = ea_layer.crs().authid()
            self.ea_merge_ea_status_lbl.setText(f"Active: {fc} EA polygons ({crs_str}).")

            # Extract 5-digit geocode
            if _emg_field_index_ci is not None:
                geo_idx = _emg_field_index_ci(ea_layer, _EMG_GEOCODE_FIELDS)
                raw_geo = _emg_first_nonempty_value(ea_layer, geo_idx)
                if raw_geo:
                    digits = re.sub(r"\D", "", raw_geo)
                    if len(digits) >= 5:
                        geo_code = digits[:5]

                # Extract CityMun
                citymun_idx = _emg_field_index_ci(ea_layer, _EMG_CITYMUN_FIELDS)
                if citymun_idx != -1:
                    vals = _emg_unique_values(ea_layer, citymun_idx)
                    if len(vals) == 1:
                        citymun = vals[0]
            else:
                # Fallback: lazy import if module-level import failed
                from .ea_merge_processor import _field_index_ci, _first_nonempty_value, _GEOCODE_FIELDS, _CITYMUN_FIELDS, _unique_values
                geo_idx = _field_index_ci(ea_layer, _GEOCODE_FIELDS)
                raw_geo = _first_nonempty_value(ea_layer, geo_idx)
                if raw_geo:
                    digits = re.sub(r"\D", "", raw_geo)
                    if len(digits) >= 5:
                        geo_code = digits[:5]
                citymun_idx = _field_index_ci(ea_layer, _CITYMUN_FIELDS)
                if citymun_idx != -1:
                    vals = _unique_values(ea_layer, citymun_idx)
                    if len(vals) == 1:
                        citymun = vals[0]

        # 2. Replacement Layers validation
        all_poly = True
        all_8digits = True
        all_valid_geom = True
        has_repl = len(repl_layers) > 0

        if not has_repl:
            all_poly = False
            all_8digits = False
            all_valid_geom = False
        else:
            for lyr in repl_layers:
                if not lyr or lyr.geometryType() != QgsWkbTypes.PolygonGeometry:
                    all_poly = False
                if not lyr or not pat.match(lyr.name()):
                    all_8digits = False
                if not lyr or lyr.featureCount() == 0 or not lyr.crs().isValid():
                    all_valid_geom = False

        # Update checklist labels
        def _check_text(label_name, ok, active):
            if not active:
                return f"• {label_name}: <span style='color:#7F8C8D;'>-</span>"
            if ok:
                return f"• {label_name}: <span style='color:#1A7F37; font-weight:bold;'>✓ Valid</span>"
            return f"• {label_name}: <span style='color:#CF222E; font-weight:bold;'>✗ Failed</span>"

        self.ea_merge_val_poly_lbl.setText(_check_text("Polygon layers", all_poly, has_repl))
        self.ea_merge_val_name_lbl.setText(_check_text("8-digit layer names", all_8digits, has_repl))
        self.ea_merge_val_geom_lbl.setText(_check_text("Valid geometries", all_valid_geom, has_repl))

        # Update Output Preview
        if geo_code:
            self.ea_merge_out_geocode_lbl.setText(geo_code)
            self.ea_merge_out_layer_lbl.setText(f"{geo_code}_ea2026")
            if citymun:
                self.ea_merge_out_excel_lbl.setText(f"{geo_code}_earf_{citymun}.xlsx")
            else:
                self.ea_merge_out_excel_lbl.setText(f"{geo_code}_earf_Unknown.xlsx")
        else:
            self.ea_merge_out_geocode_lbl.setText("-")
            self.ea_merge_out_layer_lbl.setText("-")
            self.ea_merge_out_excel_lbl.setText("-")

        # Enable/Disable Run button
        has_output = bool(self.ea_merge_output_folder_widget.filePath().strip()) if hasattr(self, 'ea_merge_output_folder_widget') else False
        can_run = bool(ea_layer and has_repl and all_poly and all_8digits and geo_code and has_output)
        self.ea_merge_run_btn.setEnabled(can_run)

    def _ea_merge_cancel(self):
        """Request cancellation of the running EA Merge task."""
        self._ea_merge_cancelled = True
        self._ea_merge_append_log(
            "<span style='color:#d17a00; font-weight:bold;'>[CANCEL] Cancellation requested by user...</span>"
        )

    def _ea_merge_copy_log(self):
        """Copy the EA Merge processing log to clipboard."""
        clipboard = QCoreApplication.instance().clipboard()
        clipboard.setText(self.ea_merge_log_console.toPlainText())
        self.ea_merge_copy_log_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.ea_merge_copy_log_btn.setText("Copy Log"))

    def _ea_merge_append_log(self, html: str):
        """Append an HTML-formatted line to the EA Merge log console."""
        self.ea_merge_log_console.append(html)
        self.ea_merge_log_console.ensureCursorVisible()
        QCoreApplication.processEvents()

    def _ea_merge_format_log(self, msg: str) -> str:
        """Format a plain log message string into colored HTML."""
        msg_lower = msg.lower()
        if msg.startswith("[ERROR]"):
            return f"<span style='color:#cf222e; font-weight:bold;'>{msg}</span>"
        if msg.startswith("[WARNING]"):
            return f"<span style='color:#d17a00; font-weight:bold;'>{msg}</span>"
        if msg.startswith("[INFO]") and ("complete" in msg_lower or "pass" in msg_lower or "success" in msg_lower):
            return f"<span style='color:#1a7f37; font-weight:bold;'>{msg}</span>"
        return f"<span style='color:#0969da;'>{msg}</span>"

    def _ea_merge_run(self):
        """Validate inputs and launch the Enumeration Area Merge processor in a background thread."""
        ea_layer = self.ea_merge_ea_combo.currentLayer()
        repl_layers = self._ea_merge_replacement_layers

        if not ea_layer:
            self._ea_merge_append_log("<span style='color:#cf222e; font-weight:bold;'>[ERROR] Previous EA Layer is required.</span>")
            return
        if not repl_layers:
            self._ea_merge_append_log("<span style='color:#cf222e; font-weight:bold;'>[ERROR] At least one Replacement Polygon Layer is required.</span>")
            return

        # Guard: don't start a second run if one is already in flight
        if getattr(self, '_ea_merge_thread', None) and self._ea_merge_thread.isRunning():
            return

        # UI state — running
        self.ea_merge_run_btn.setEnabled(False)
        self.ea_merge_cancel_btn.setEnabled(True)
        self.ea_merge_progress_bar.setValue(0)
        self.ea_merge_log_console.clear()
        self.ea_merge_status_banner.setText("Processing Enumeration Area Merge...")

        # Switch to log tab so user sees progress
        right_tabs = self.ea_merge_log_console.parent().parent()
        if hasattr(right_tabs, "setCurrentIndex"):
            right_tabs.setCurrentIndex(1)  # Log tab

        self._ea_merge_cancelled = False

        def is_cancelled_fn():
            return self._ea_merge_cancelled

        # Determine designated output folder
        out_folder = self.ea_merge_output_folder_widget.filePath().strip() if hasattr(self, 'ea_merge_output_folder_widget') else ""
        if not out_folder:
            QMessageBox.warning(self, "Missing Output Folder", "Please designate an output folder before running.")
            self.ea_merge_run_btn.setEnabled(False)
            return

        self._ea_merge_append_log(
            f"<span style='color: #0969da; font-weight: bold;'>[INFO]</span> Designated Output Folder: {out_folder}"
        )

        # --- Create worker and thread ---
        from .ea_merge_processor import EAMergeProcessor

        self._ea_merge_worker = _EAMergeWorker()

        processor = EAMergeProcessor(
            ea_layer=ea_layer,
            replacement_layers=repl_layers,
            output_dir=out_folder,
            # Callbacks emit Qt signals — safe to call from the worker thread
            # because cross-thread signals are queued to the main event loop.
            feedback_callback=self._ea_merge_worker.feedback_signal.emit,
            progress_callback=self._ea_merge_worker.progress_signal.emit,
            is_cancelled_fn=is_cancelled_fn,
            # addMapLayer must be called on the main thread; _ea_merge_on_thread_finished
            # handles it after the worker signals finished.
            skip_add_to_project=True,
        )
        self._ea_merge_worker.set_processor(processor)

        self._ea_merge_thread = QThread()
        self._ea_merge_worker.moveToThread(self._ea_merge_thread)

        # Wire up signals
        self._ea_merge_thread.started.connect(self._ea_merge_worker.run)
        self._ea_merge_worker.feedback_signal.connect(
            lambda msg: self._ea_merge_append_log(self._ea_merge_format_log(msg))
        )
        self._ea_merge_worker.progress_signal.connect(self.ea_merge_progress_bar.setValue)
        self._ea_merge_worker.finished_signal.connect(self._ea_merge_on_thread_finished)
        # Clean up thread and worker objects when the thread exits
        self._ea_merge_thread.finished.connect(self._ea_merge_thread.deleteLater)
        self._ea_merge_worker.finished_signal.connect(self._ea_merge_thread.quit)

        self._ea_merge_thread.start()

    def _ea_merge_on_thread_finished(self, result):
        """Slot called on the main thread when the worker emits finished_signal.

        Adds the output layer to the QGIS project (must be done on the main
        thread) then delegates to the existing UI update handler.
        """
        # Add the output layer to the project here, on the main thread
        if result.success and result.output_layer is not None:
            try:
                proj = QgsProject.instance()
                if proj:
                    for old_lyr in list(proj.mapLayersByName(result.summary.output_layer_name)):
                        proj.removeMapLayer(old_lyr.id())
                    proj.addMapLayer(result.output_layer)
                    from .helpers.style import apply_qml_to_layer
                    apply_qml_to_layer(result.output_layer, "ea_output.qml")
                self._ea_merge_append_log(
                    self._ea_merge_format_log(
                        f"[INFO] Permanent GeoPackage layer (.gpkg) added to QGIS canvas: {result.summary.output_layer_name}"
                    )
                )
            except Exception as exc:
                self._ea_merge_append_log(
                    f"<span style='color:#d17a00; font-weight:bold;'>[WARNING] Could not add layer to project: {exc}</span>"
                )

        # Release references so the worker/thread can be garbage collected
        self._ea_merge_worker = None

        # Delegate to the existing UI update handler
        self._ea_merge_on_finished(result)

    def _ea_merge_on_finished(self, result):
        """Handle completion of the Enumeration Area Merge run and update UI."""
        self.ea_merge_run_btn.setEnabled(True)
        self.ea_merge_cancel_btn.setEnabled(False)

        summary = result.summary

        if not result.success:
            self.ea_merge_status_banner.setText(f"Error: {result.error_message}")
            self._ea_merge_sum_status_lbl.setText("<span style='color:#cf222e; font-weight:bold;'>Status: ERROR</span>")
            return

        # Populate summary tab
        self._ea_merge_sum_geocode_val.setText(summary.geographic_code)
        self._ea_merge_sum_ea_input_val.setText(summary.ea_input_layer_name)
        self._ea_merge_sum_repl_layers_val.setText(str(summary.replacement_layer_count))
        self._ea_merge_sum_repl_feats_val.setText(str(summary.replacement_feature_count))
        self._ea_merge_sum_mod_eas_val.setText(str(summary.modified_ea_count))
        self._ea_merge_sum_final_eas_val.setText(str(summary.final_ea_feature_count))
        self._ea_merge_sum_output_val.setText(summary.output_layer_name)
        self._ea_merge_sum_excel_val.setText(summary.excel_file_name if summary.excel_generated else "Failed")

        status_colors = {"PASS": "#1a7f37", "WARNING": "#d17a00", "ERROR": "#cf222e"}
        status_color = status_colors.get(summary.overall_status, "#333")
        self._ea_merge_sum_status_lbl.setText(
            f"<span style='color:{status_color}; font-weight:bold;'>Status: {summary.overall_status}</span>"
        )
        self._ea_merge_sum_status_lbl.setTextFormat(Qt.RichText)

        # Status banner
        self.ea_merge_status_banner.setText(
            f"Merge completed — Final EA Features: {summary.final_ea_feature_count} | Output: {summary.output_layer_name} | Status: PASS"
        )

        self.ea_merge_progress_bar.setValue(100)

        # Switch to Summary tab
        right_tabs = self.ea_merge_log_console.parent().parent()
        if hasattr(right_tabs, "setCurrentIndex"):
            right_tabs.setCurrentIndex(0)  # Summary tab


class MultiLayerSelectDialog(QDialog):
    """Modal dialog allowing selection of multiple polygon layers from the current QGIS project."""

    def __init__(self, parent=None, selected_layers=None):
        super().__init__(parent)
        self.setWindowTitle("Select Replacement Polygon Layers")
        self.setMinimumSize(450, 380)
        self.selected_layers = list(selected_layers or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        info_lbl = QLabel(
            "Select one or more polygon layers whose names begin with an 8-digit code\n"
            "(e.g. 01728011, 01728011_delineated_ea2026, 01728001_merged_ea2026)\n"
            "to use as replacement geometries:"
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        # Quick selection buttons
        btn_row = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(sel_all_btn)

        desel_all_btn = QPushButton("Deselect All")
        desel_all_btn.clicked.connect(self._deselect_all)
        btn_row.addWidget(desel_all_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self._populate_layers()
        layout.addWidget(self.list_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_layers(self):
        import re
        # Only show polygon layers whose name starts with 8 digits (optionally followed by _suffix)
        pat_8_prefix = re.compile(r"^\d{8}(_|$)")
        selected_ids = {lyr.id() for lyr in self.selected_layers if lyr}
        all_layers = list(QgsProject.instance().mapLayers().values())
        for layer in all_layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                continue
            if not pat_8_prefix.match(layer.name()):
                continue
            item = QListWidgetItem(self.list_widget)
            item.setText(f"{layer.name()} ({layer.featureCount()} features)")
            item.setData(Qt.UserRole, layer.id())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if layer.id() in selected_ids:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)

    def _select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)

    def _deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)

    def _on_accept(self):
        self.selected_layers = []
        project = QgsProject.instance()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                lid = item.data(Qt.UserRole)
                lyr = project.mapLayer(lid)
                if lyr:
                    self.selected_layers.append(lyr)
        self.accept()

