# -*- coding: utf-8 -*-
"""
Create Enumeration Areas -- Custom Processing UI Dialog
-------------------------------------------------------
Provides a comprehensive custom user interface for the Create Enumeration Areas
processing algorithm. Adapts to dynamic light and dark themes (defaulting to white),
and features validation indicators, layer auto-detection, KPI cards, candidate table filters,
and a stylized console interface.
"""

import os
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsCoordinateTransform, QgsSpatialIndex, QgsFeature, QgsGeometry,
    QgsProcessingContext, QgsProcessingFeedback, QgsCoordinateReferenceSystem, NULL,
    QgsMapLayerProxyModel
)
from qgis.gui import QgsMapLayerComboBox, QgsProjectionSelectionWidget
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QSizePolicy, QSpacerItem, QWidget, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QLineEdit, QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTextEdit, QScrollArea, QSplitter, QGridLayout,
    QTextBrowser, QMessageBox, QGroupBox, QToolButton
)
from qgis.PyQt.QtGui import QFont, QPixmap, QColor, QIcon, QTextCursor
from qgis.PyQt.QtCore import Qt, QSize, QCoreApplication, QThread, QObject, pyqtSignal, QVariant, QTimer



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
    """Comprehensive Processing UI for Create Enumeration Areas."""

    ALGORITHM_ID = "gmd_pipeline:createea"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Enumeration Areas")
        icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "create_ea.svg")
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.setMinimumSize(1150, 650)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowTitleHint
        )
        
        self.feedback = None
        
        # Initialize algorithm instance for help text metadata
        from .algorithm import CreateEAAlgorithm
        self.algo = CreateEAAlgorithm()
        
        # Candidate lists storage for live search/filter
        self.all_delineation_candidates = []
        self.all_merge_candidates = []

        # Guard: auto-detect runs once when the dialog is first shown, not during construction
        self._initial_detect_done = False

        # Detect QGIS theme (light or dark) based on application palette brightness
        palette = self.palette()
        bg_color = palette.color(palette.Window)
        self.current_theme = "dark" if bg_color.lightness() < 128 else "light"

        self._build_ui()

        # Connect signals for live candidate previews and validators
        self._setup_preview_connections()


    # ── Lifecycle Overrides ──────────────────────────────────────────────────

    def showEvent(self, event):
        """Auto-detect project layers exactly once when the dialog is first shown.

        Using showEvent (rather than __init__) ensures detection fires when the
        dialog is actually visible — i.e. the moment the user opens the tool —
        and not during invisible construction or in response to subsequent
        project layer additions.
        """
        super().showEvent(event)
        if not self._initial_detect_done:
            self._initial_detect_done = True
            self.auto_detect_layers()

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ── Header Panel ──────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 4, 4, 4)
        header_layout.setSpacing(10)

        # Icon (Left Aligned)
        icon_label = QLabel()
        icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "icons", "create_ea.svg")
        )
        if os.path.exists(icon_path):
            pix = QIcon(icon_path).pixmap(36, 36)
            icon_label.setPixmap(pix)
        else:
            icon_label.setText("🗺")
            icon_label.setFont(QFont("Segoe UI Emoji", 20))
        icon_label.setFixedSize(36, 36)
        icon_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(icon_label, 0, Qt.AlignVCenter)

        # Title
        title = QLabel("Create Enumeration Areas")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        header_layout.addWidget(title, 0, Qt.AlignVCenter)

        header_layout.addStretch()

        # Description Toggle Icon Button (only icon, aligned in top header)
        show_icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "icons", "show_description.svg"))
        hide_icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "icons", "hide_description.svg"))

        self.toggle_help_btn = QToolButton()
        self.toggle_help_btn.setIcon(QIcon(hide_icon_path))
        self.toggle_help_btn.setIconSize(QSize(20, 20))
        self.toggle_help_btn.setFixedSize(28, 28)
        self.toggle_help_btn.setToolTip("Show / Hide Description Panel")
        self.toggle_help_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_help_btn.setStyleSheet("""
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
        self.toggle_help_btn.clicked.connect(self.toggle_help)
        header_layout.addWidget(self.toggle_help_btn, 0, Qt.AlignVCenter)

        root.addWidget(header)

        # ── Main Pane Splitter ────────────────────────────────────────────
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setObjectName("mainSplitter")
        
        # Left Panel (Parameters Scroll Area)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(8)

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

        # Action buttons sub-row inside Input Layers group box
        inputs_btn_layout = QHBoxLayout()
        self.detect_btn = QPushButton("Auto-detect Layers")
        self.detect_btn.setToolTip("Scan current QGIS project layers and auto-select matching layers.")
        self.detect_btn.clicked.connect(self.auto_detect_layers)
        inputs_btn_layout.addWidget(self.detect_btn)

        self.fill_missing_btn = QPushButton("Fill missing hhcount")
        self.fill_missing_btn.setToolTip("Compute and populate missing EA hhcount values from building points within each EA polygon.")
        self.fill_missing_btn.clicked.connect(self.fill_missing_hhcount)
        inputs_btn_layout.addWidget(self.fill_missing_btn)
        inputs_layout.addLayout(inputs_btn_layout)

        # Barangay Layer
        inputs_layout.addWidget(QLabel("Barangay Layer (Polygon)*"))
        self.bar_combo = QgsMapLayerComboBox()
        self.bar_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        inputs_layout.addWidget(self.bar_combo)
        self.bar_status_lbl = QLabel("No layer selected.")
        inputs_layout.addWidget(self.bar_status_lbl)

        # Building Points
        inputs_layout.addWidget(QLabel("Building Point Layer (Point)*"))
        self.bldg_combo = QgsMapLayerComboBox()
        self.bldg_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        inputs_layout.addWidget(self.bldg_combo)
        self.bldg_status_lbl = QLabel("No layer selected.")
        inputs_layout.addWidget(self.bldg_status_lbl)

        # Previous EAs
        inputs_layout.addWidget(QLabel("Previous EA Layer (Polygon)*"))
        self.prev_ea_combo = QgsMapLayerComboBox()
        self.prev_ea_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        inputs_layout.addWidget(self.prev_ea_combo)
        self.prev_ea_status_lbl = QLabel("No layer selected.")
        inputs_layout.addWidget(self.prev_ea_status_lbl)

        # Road (Optional)
        inputs_layout.addWidget(QLabel("Road Layer (Line, Optional)"))
        self.road_combo = QgsMapLayerComboBox()
        self.road_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.road_combo.setAllowEmptyLayer(True)
        self.road_combo.setLayer(None)
        inputs_layout.addWidget(self.road_combo)
        self.road_status_lbl = QLabel("Optional.")
        inputs_layout.addWidget(self.road_status_lbl)

        # River (Optional)
        inputs_layout.addWidget(QLabel("River Layer (Line, Optional)"))
        self.river_combo = QgsMapLayerComboBox()
        self.river_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.river_combo.setAllowEmptyLayer(True)
        self.river_combo.setLayer(None)
        inputs_layout.addWidget(self.river_combo)
        self.river_status_lbl = QLabel("Optional.")
        inputs_layout.addWidget(self.river_status_lbl)

        # Gap (Optional)
        inputs_layout.addWidget(QLabel("Gap Layer (Polygon, Optional)"))
        self.gap_combo = QgsMapLayerComboBox()
        self.gap_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.gap_combo.setAllowEmptyLayer(True)
        self.gap_combo.setLayer(None)
        inputs_layout.addWidget(self.gap_combo)
        self.gap_status_lbl = QLabel("Optional.")
        inputs_layout.addWidget(self.gap_status_lbl)

        # Overlap (Optional)
        inputs_layout.addWidget(QLabel("Overlap Layer (Polygon, Optional)"))
        self.overlap_combo = QgsMapLayerComboBox()
        self.overlap_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.overlap_combo.setAllowEmptyLayer(True)
        self.overlap_combo.setLayer(None)
        inputs_layout.addWidget(self.overlap_combo)
        self.overlap_status_lbl = QLabel("Optional.")
        inputs_layout.addWidget(self.overlap_status_lbl)

        scroll_layout.addWidget(inputs_group)

        # 2. Parameters Section (QGroupBox)
        params_group = QGroupBox("Delineation Thresholds Settings")
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(8)

        # Min Household
        params_layout.addWidget(QLabel("Minimum Household count per EA"))
        self.min_hh_spin = QSpinBox()
        self.min_hh_spin.setRange(1, 99999)
        self.min_hh_spin.setValue(100)
        params_layout.addWidget(self.min_hh_spin)

        # Max Household
        params_layout.addWidget(QLabel("Maximum Household count per EA"))
        self.max_hh_spin = QSpinBox()
        self.max_hh_spin.setRange(1, 99999)
        self.max_hh_spin.setValue(300)
        params_layout.addWidget(self.max_hh_spin)

        # Snapping Tolerance
        params_layout.addWidget(QLabel("Snapping Tolerance (meters) for road/river alignment"))
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setRange(0.0, 999.0)
        self.tolerance_spin.setValue(15.0)
        params_layout.addWidget(self.tolerance_spin)

        # Split Strategy enum
        params_layout.addWidget(QLabel("Split Strategy for Over-Populated EAs"))
        self.split_strategy_combo = QComboBox()
        self.split_strategy_combo.addItems([
            "Road + River Priority (Recommended - follow physical features)",
            "Strict Threshold (Reject road/river split if sub-EA < min_household)",
            "Keep Whole (Do not split over-populated EAs)"
        ])
        params_layout.addWidget(self.split_strategy_combo)

        # Split Method / Type enum
        params_layout.addWidget(QLabel("Delineation Split Method / Type"))
        self.split_type_combo = QComboBox()
        self.split_type_combo.addItems([
            "Auto (Road/River Priority -> Voronoi -> Forced Cut)",
            "Road & River Alignment Only (Follow linear features)",
            "Building Point Voronoi Only (Cluster building density)",
            "Forced Geometric Cut Only (Straight strip cuts)",
            "Keep Whole (No Splitting)"
        ])
        params_layout.addWidget(self.split_type_combo)

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

        scroll_layout.addWidget(params_group)

        # 3. Outputs Section (QGroupBox)
        outputs_group = QGroupBox("Output Layers")
        outputs_layout = QVBoxLayout(outputs_group)
        outputs_layout.setSpacing(8)

        # Delineated EAs Layer
        outputs_layout.addWidget(QLabel("Delineated EAs Layer"))
        self.delineated_path, self.delineated_edit = self._file_picker_row()
        outputs_layout.addLayout(self.delineated_path)

        # Merged EAs Layer
        outputs_layout.addWidget(QLabel("Merged EAs Layer"))
        self.merged_path, self.merged_edit = self._file_picker_row()
        outputs_layout.addLayout(self.merged_path)

        # Special EAs Layer (Gap/Overlap)
        outputs_layout.addWidget(QLabel("Special EAs Layer (Gap/Overlap)"))
        self.special_ea_path, self.special_ea_edit = self._file_picker_row()
        outputs_layout.addLayout(self.special_ea_path)

        # Candidate for Delineation Layer
        outputs_layout.addWidget(QLabel("Delineation Candidate Layer"))
        self.delin_cand_path, self.delin_cand_edit = self._file_picker_row()
        outputs_layout.addLayout(self.delin_cand_path)

        # Candidate for Merging Layer
        outputs_layout.addWidget(QLabel("Merge Candidate Layer"))
        self.merge_cand_path, self.merge_cand_edit = self._file_picker_row()
        outputs_layout.addLayout(self.merge_cand_path)

        # Extracted Building Points Layer
        outputs_layout.addWidget(QLabel("Extracted Building Points Layer"))
        self.extracted_bldg_path, self.extracted_bldg_edit = self._file_picker_row()
        outputs_layout.addLayout(self.extracted_bldg_path)

        scroll_layout.addWidget(outputs_group)
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        
        left_widget.setMinimumWidth(390)
        main_splitter.addWidget(left_widget)

        # Right Panel (Tabs for Live Preview and Execution Logs)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(8)

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
        help_layout.setContentsMargins(5, 5, 5, 5)
        help_layout.setSpacing(0)

        self.help_text = QTextBrowser()
        self.help_text.setOpenExternalLinks(True)
        self.help_text.setHtml(self.algo.shortHelpString())
        help_layout.addWidget(self.help_text)

        self.help_panel.setMinimumWidth(260)
        main_splitter.addWidget(self.help_panel)
        
        # Set proportional initial widths for the panels
        main_splitter.setSizes([390, 500, 260])

        root.addWidget(main_splitter)

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
        layers = [self.bar_combo.currentLayer(), self.prev_ea_combo.currentLayer()]
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
        self.bar_combo.currentIndexChanged.connect(self.validate_layer_inputs)
        self.bldg_combo.currentIndexChanged.connect(self.validate_layer_inputs)
        self.prev_ea_combo.currentIndexChanged.connect(self.validate_layer_inputs)
        self.road_combo.currentIndexChanged.connect(self.validate_layer_inputs)
        self.river_combo.currentIndexChanged.connect(self.validate_layer_inputs)
        self.gap_combo.currentIndexChanged.connect(self.validate_layer_inputs)
        self.overlap_combo.currentIndexChanged.connect(self.validate_layer_inputs)
        
        self.min_hh_spin.valueChanged.connect(self.trigger_auto_refresh)
        self.max_hh_spin.valueChanged.connect(self.trigger_auto_refresh)

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

    def fill_missing_hhcount(self):
        """Populate null/empty hhcount values in the EA layer from building points inside each EA."""
        prev_ea_layer = self.prev_ea_combo.currentLayer()
        bldg_layer = self.bldg_combo.currentLayer()
        if not prev_ea_layer or not bldg_layer:
            QMessageBox.warning(
                self,
                "Missing Layers",
                "Please select both Previous EA and Building Point layers before filling missing hhcount values."
            )
            return

        # Resolve household field index in EA layer
        prev_fields = prev_ea_layer.fields()
        hh_field = None
        for i in range(prev_fields.count()):
            name_lower = prev_fields.at(i).name().lower()
            if name_lower in ["hhcount", "hh_count", "household", "household_count"]:
                hh_field = prev_fields.at(i).name()
                break
        if not hh_field:
            QMessageBox.critical(
                self,
                "Field Not Found",
                "Previous EA layer does not contain a household field (hhcount / hh_count / household / household_count)."
            )
            return

        # Use spatial index on EA polygons
        ea_index = QgsSpatialIndex(prev_ea_layer.getFeatures())
        ea_by_id = {feat.id(): feat for feat in prev_ea_layer.getFeatures()}

        # Map EA feature id -> total HHcount from buildings inside it
        hh_updates = {}
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
                "Building point layer does not contain a household field (hhcount / hh_count / household / household_count)."
            )
            return

        # Track EA features that currently have empty/null hhcount
        missing_ea_ids = []
        for feat in prev_ea_layer.getFeatures():
            hh_val = feat.attribute(hh_field)
            if hh_val is None or (isinstance(hh_val, QVariant) and hh_val.isNull()) or str(hh_val).strip() == "":
                missing_ea_ids.append(feat.id())

        if not missing_ea_ids:
            QMessageBox.information(
                self,
                "No Missing hhcount",
                "No missing or empty hhcount values were detected on the selected Previous EA layer."
            )
            return

        # Build a spatial lookup for buildings
        for bldg_feat in bldg_layer.getFeatures():
            geom = bldg_feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            candidate_eas = ea_index.intersects(geom.boundingBox())
            for ea_id in candidate_eas:
                ea_feat = ea_by_id.get(ea_id)
                if not ea_feat:
                    continue
                if not ea_feat.geometry().contains(geom):
                    continue
                if ea_id not in missing_ea_ids:
                    continue

                hh_val = bldg_feat.attribute(bldg_hh_idx)
                try:
                    hh_val_float = float(hh_val) if hh_val is not None else 0.0
                except (TypeError, ValueError):
                    hh_val_float = 0.0
                hh_updates[ea_id] = hh_updates.get(ea_id, 0.0) + hh_val_float

        if not hh_updates:
            QMessageBox.warning(
                self,
                "No Building Matches",
                "No building points were found inside EA polygons with missing hhcount values."
            )
            return

        # Write values back to the EA layer
        if not prev_ea_layer.isEditable():
            prev_ea_layer.startEditing()
        updated_count = 0
        for ea_id, hh_total in hh_updates.items():
            feat = prev_ea_layer.getFeature(ea_id)
            if feat.isValid():
                prev_ea_layer.changeAttributeValue(ea_id, prev_fields.indexOf(hh_field), hh_total)
                updated_count += 1

        if prev_ea_layer.commitChanges():
            QMessageBox.information(
                self,
                "hhcount Updated",
                f"Updated hhcount for {updated_count} EA(s) from building points."
            )
            self.generate_preview()
        else:
            QMessageBox.critical(
                self,
                "Update Failed",
                "Failed to save hhcount updates to the EA layer. Check layer edit permissions."
            )

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
        gap_keywords      = ["gap", "gaps"]
        overlap_keywords  = ["overlap", "overlaps"]

        # Candidates: first match per slot wins (order of iteration = layer panel order)
        candidates = {
            "bar":      None,
            "bldg":     None,
            "prev_ea":  None,
            "road":     None,
            "river":    None,
            "gap":      None,
            "overlap":  None,
        }

        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            name_lower = layer.name().lower()
            geom = layer.geometryType()

            if geom == 2:  # Polygon
                if candidates["gap"] is None and any(k in name_lower for k in gap_keywords):
                    candidates["gap"] = layer
                elif candidates["overlap"] is None and any(k in name_lower for k in overlap_keywords):
                    candidates["overlap"] = layer
                elif candidates["bar"] is None and any(k in name_lower for k in barangay_keywords) \
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
            self.bar_combo.setLayer(candidates["bar"])
        if candidates["bldg"]:
            self.bldg_combo.setLayer(candidates["bldg"])
        if candidates["prev_ea"]:
            self.prev_ea_combo.setLayer(candidates["prev_ea"])
        if candidates["road"]:
            self.road_combo.setLayer(candidates["road"])
        if candidates["river"]:
            self.river_combo.setLayer(candidates["river"])
        if candidates["gap"]:
            self.gap_combo.setLayer(candidates["gap"])
        if candidates["overlap"]:
            self.overlap_combo.setLayer(candidates["overlap"])

        self.validate_layer_inputs()

    def validate_layer_inputs(self):
        """Perform validation on selected layers and show dynamic status subtitles."""
        # 1. Barangay Layer
        bar_layer = self.bar_combo.currentLayer()
        if not bar_layer:
            self.bar_status_lbl.setText("Barangay Layer is required.")
        else:
            self.bar_status_lbl.setText(f"Active: {bar_layer.featureCount()} polygons loaded ({bar_layer.crs().authid()}).")

        # 2. Building Layer
        bldg_layer = self.bldg_combo.currentLayer()
        if not bldg_layer:
            self.bldg_status_lbl.setText("Building Point Layer is required.")
        else:
            fields = [f.name().lower() for f in bldg_layer.fields()]
            hh_found = any(f in fields for f in ["hhcount", "hh_count", "household", "household_count"])
            hh_msg = " (found hhcount)" if hh_found else " (no hhcount field)"
            self.bldg_status_lbl.setText(f"Active: {bldg_layer.featureCount()} points loaded{hh_msg}.")

        # 3. Previous EA Layer
        prev_ea_layer = self.prev_ea_combo.currentLayer()
        hh_found = False
        ean_found = False
        if not prev_ea_layer:
            self.prev_ea_status_lbl.setText("Previous EA Layer is required.")
        else:
            fields = [f.name().lower() for f in prev_ea_layer.fields()]
            hh_found = any(f in fields for f in ["hhcount", "hh_count", "household", "household_count"])
            ean_found = any(f in fields for f in ["ean", "ea_number", "ea_code", "id", "geocode"])

            if not hh_found:
                self.prev_ea_status_lbl.setText("Error: Missing 'hhcount' or 'household' field.")
            elif not ean_found:
                self.prev_ea_status_lbl.setText("Error: Missing 'ean' or 'ea_number' geocode field.")
            else:
                self.prev_ea_status_lbl.setText(f"Active: {prev_ea_layer.featureCount()} EAs loaded successfully.")

        # Enable fill-missing button only when required layers are present
        self.fill_missing_btn.setEnabled(bool(prev_ea_layer and bldg_layer and hh_found))
        road_layer = self.road_combo.currentLayer()
        if not road_layer:
            self.road_status_lbl.setText("Optional: Road boundary snapping will be skipped.")
        else:
            self.road_status_lbl.setText(f"Active: {road_layer.featureCount()} line features loaded.")

        # 5. River Layer (Optional)
        river_layer = self.river_combo.currentLayer()
        if not river_layer:
            self.river_status_lbl.setText("Optional: River boundary snapping will be skipped.")
        else:
            self.river_status_lbl.setText(f"Active: {river_layer.featureCount()} line features loaded.")

        # 6. Gap Layer (Optional)
        gap_layer = self.gap_combo.currentLayer()
        if not gap_layer:
            self.gap_status_lbl.setText("Optional: Gap workflow will be skipped.")
        else:
            self.gap_status_lbl.setText(f"Active: {gap_layer.featureCount()} polygon features loaded.")

        # 7. Overlap Layer (Optional)
        overlap_layer = self.overlap_combo.currentLayer()
        if not overlap_layer:
            self.overlap_status_lbl.setText("Optional: Overlap workflow will be skipped.")
        else:
            self.overlap_status_lbl.setText(f"Active: {overlap_layer.featureCount()} polygon features loaded.")
            
        # Update output layer placeholders using 5-digit geocode prefix
        geo5 = self._extract_5digit_geocode()
        if geo5:
            self.delineated_edit.setPlaceholderText(f"{geo5}_delineated_ea2026")
            self.merged_edit.setPlaceholderText(f"{geo5}_merged_ea2026")
            self.special_ea_edit.setPlaceholderText(f"{geo5}_special_ea")
            self.delin_cand_edit.setPlaceholderText(f"{geo5}_delineation_candidates")
            self.merge_cand_edit.setPlaceholderText(f"{geo5}_merge_candidates")
            self.extracted_bldg_edit.setPlaceholderText(f"{geo5}_extracted_bldgpts")
        else:
            self.delineated_edit.setPlaceholderText("[Temporary Scratch Layer]")
            self.merged_edit.setPlaceholderText("[Temporary Scratch Layer]")
            self.special_ea_edit.setPlaceholderText("[Temporary Scratch Layer]")
            self.delin_cand_edit.setPlaceholderText("[Temporary Scratch Layer]")
            self.merge_cand_edit.setPlaceholderText("[Temporary Scratch Layer]")
            self.extracted_bldg_edit.setPlaceholderText("[Temporary Scratch Layer]")

        self.trigger_auto_refresh()

    def generate_preview(self):
        """Generates visual candidates table preview dynamically before execution."""
        if not hasattr(self, "delineation_table") or not hasattr(self, "merge_table"):
            return

        prev_ea_layer = self.prev_ea_combo.currentLayer()
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

        # Resolve household field index case-insensitively
        hh_idx = -1
        for i in range(fields.count()):
            name_lower = fields.at(i).name().lower()
            if name_lower in ["hhcount", "hh_count", "household", "household_count"]:
                hh_idx = i
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
            if name_lower == "eadel_indi":
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
            #   HH <= min_hh  → Merge candidate (under-populated EA)
            #   Explicit field indicator ("for merging") → Merge candidate
            is_delin = (hh >= max_hh)

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
        self.run_btn.setEnabled(True)
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

    def run_pipeline(self):
        """Execute processing algorithm directly using custom feedback."""
        bar_layer = self.bar_combo.currentLayer()
        bldg_layer = self.bldg_combo.currentLayer()
        prev_ea_layer = self.prev_ea_combo.currentLayer()
        road_layer = self.road_combo.currentLayer()
        river_layer = self.river_combo.currentLayer()
        gap_layer = self.gap_combo.currentLayer()
        overlap_layer = self.overlap_combo.currentLayer()

        if not bar_layer or not bldg_layer or not prev_ea_layer:
            self.log_console.append(
                "<span style='color:#cf222e; font-weight:bold;'>"
                "[ERROR] Please select all required inputs (Barangay, Building, Previous EA layers).</span>"
            )
            self.tab_widget.setCurrentIndex(1)
            return

        # Prepare parameters
        parameters = {
            'BARANGAY_INPUT': bar_layer,
            'BUILDING_INPUT': bldg_layer,
            'PREVIOUS_EA_INPUT': prev_ea_layer,
            'ROAD_INPUT': road_layer,
            'RIVER_INPUT': river_layer,
            'GAP_INPUT': gap_layer,
            'OVERLAP_INPUT': overlap_layer,
            'SNAP_TOLERANCE': self.tolerance_spin.value(),
            'MIN_HOUSEHOLD': self.min_hh_spin.value(),
            'MAX_HOUSEHOLD': self.max_hh_spin.value(),
            'SPLIT_STRATEGY': self.split_strategy_combo.currentIndex(),
            'SPLIT_TYPE': self.split_type_combo.currentIndex(),
            'USE_COMPACTNESS': self.compact_chk.isChecked(),
            'ALLOW_CANDIDATE_MERGE': self.allow_candidate_merge_chk.isChecked(),
            'SLIVER_THRESHOLD': self.sliver_combo.currentIndex(),
            'TARGET_CRS': self.crs_widget.crs(),
            'PREVIEW_ONLY': False,
            
            # Outputs
            'DELINEATED_OUTPUT': self.delineated_edit.text() or 'TEMPORARY_OUTPUT',
            'MERGED_OUTPUT': self.merged_edit.text() or 'TEMPORARY_OUTPUT',
            'SPECIAL_EA_OUTPUT': self.special_ea_edit.text() or 'TEMPORARY_OUTPUT',
            'DELINEATION_CANDIDATE_OUTPUT': self.delin_cand_edit.text() or 'TEMPORARY_OUTPUT',
            'MERGE_CANDIDATE_OUTPUT': self.merge_cand_edit.text() or 'TEMPORARY_OUTPUT',
            'EXTRACTED_BUILDINGS_OUTPUT': self.extracted_bldg_edit.text() or 'TEMPORARY_OUTPUT',
        }

        # Clear UI state
        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.tab_widget.setCurrentIndex(1)
        self.status_banner.setText("⏳ Processing algorithm... Please wait.")

        self.log_console.append("<span style='color:#1a7f37; font-weight:bold;'>[START] Starting Create Enumeration Areas...</span>")
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
                geo5 = self._extract_5digit_geocode() or "00000"
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
                output_mapping_ordered = [
                    ('EXTRACTED_BUILDINGS_OUTPUT', f"{geo5}_extracted_bldgpts", reference_group),
                    ('DELINEATED_OUTPUT', f"{geo5}_delineated_ea2026", eas_group),
                    ('MERGED_OUTPUT', f"{geo5}_merged_ea2026", eas_group),
                    ('SPECIAL_EA_OUTPUT', f"{geo5}_special_ea", eas_group),
                    ('DELINEATION_CANDIDATE_OUTPUT', f"{geo5}_delineation_candidates", candidates_group),
                    ('MERGE_CANDIDATE_OUTPUT', f"{geo5}_merge_candidates", candidates_group),
                ]

                if isinstance(results, dict):
                    for out_key, target_name, target_group in output_mapping_ordered:
                        if out_key in results:
                            layer_ref = results[out_key]
                            layer = None
                            if isinstance(layer_ref, str):
                                layer = QgsProject.instance().mapLayer(layer_ref)
                            elif isinstance(layer_ref, QgsMapLayer):
                                layer = layer_ref
                            
                            if layer:
                                layer.setName(target_name)
                                lnode = root.findLayer(layer.id())
                                if lnode:
                                    if lnode.parent() != target_group:
                                        clone = lnode.clone()
                                        target_group.addChildNode(clone)
                                        lnode.parent().removeChildNode(lnode)

                # Group any generated splitting line layers (ending with _eadel_update) into Splitting Lines
                has_splitting_lines = False
                for layer_id, proj_layer in QgsProject.instance().mapLayers().items():
                    if proj_layer.name().endswith("_eadel_update"):
                        has_splitting_lines = True
                        lnode = root.findLayer(layer_id)
                        if lnode and lnode.parent() != splitting_lines_group:
                            clone = lnode.clone()
                            splitting_lines_group.addChildNode(clone)
                            lnode.parent().removeChildNode(lnode)

                # Clean up empty Splitting Lines group if no splitting lines were generated
                if not has_splitting_lines and len(splitting_lines_group.children()) == 0:
                    main_group.removeChildNode(splitting_lines_group)

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
            self.log_console.append(f"<span style='color:#cf222e; font-weight:bold;'>[FATAL] Error executing pipeline: {str(e)}</span>")
            self.status_banner.setText(f"Error: Pipeline execution failed — {str(e)}")
        
        finally:
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.feedback = None
