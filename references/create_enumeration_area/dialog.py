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
    QTextBrowser, QMessageBox
)
from qgis.PyQt.QtGui import QFont, QPixmap, QColor, QIcon, QTextCursor
from qgis.PyQt.QtCore import Qt, QSize, QCoreApplication, QThread, QObject, pyqtSignal, QVariant

# ── Theme Palettes (Defaulting to White/Light Theme) ──────────────────────
THEME_PALETTES = {
    "light": {
        "bg": "#f8f9fa",            # Soft off-white
        "header": "#ffffff",        # Pure white header
        "accent": "#0969da",        # GitHub/Vercel style blue accent
        "accent2": "#1a7f37",       # Success green
        "text": "#24292f",          # Charcoal dark text
        "subtext": "#57606a",       # Slate gray subtext
        "divider": "#d0d7de",       # Light gray divider borders
        "card": "#ffffff",          # Card white background
        "run_hover": "#1f883d",     # Darker green hover
        "input_bg": "#ffffff",      # White background for inputs
        "table_bg": "#ffffff",
        "table_header_bg": "#f6f8fa",
        "console_bg": "#0f1419",    # Keep logs console dark for contrast/readability
        "console_text": "#3bf1a1",
        "kpi_delin_bg": "#ffebe9",  # Pastel red
        "kpi_delin_border": "#ffc1c0",
        "kpi_merge_bg": "#dafbe1",  # Pastel green
        "kpi_merge_border": "#a6e9b9",
        "kpi_stats_bg": "#ddf4ff",  # Pastel blue
        "kpi_stats_border": "#b2e3ff"
    },
    "dark": {
        "bg": "#0d1b2a",            # Navy background
        "header": "#1a3a5c",        # Dark blue header
        "accent": "#2980b9",        # Accent blue
        "accent2": "#1abc9c",       # Teal accent
        "text": "#ecf0f1",          # Off-white text
        "subtext": "#95a5a6",       # Muted gray text
        "divider": "#2c3e50",       # Dark slate border divider
        "card": "#152638",          # Card dark blue background
        "run_hover": "#16a085",
        "input_bg": "#1f354d",
        "table_bg": "#070e17",
        "table_header_bg": "#152638",
        "console_bg": "#050b14",
        "console_text": "#00ff00",
        "kpi_delin_bg": "#3d2121",  # Dark red
        "kpi_delin_border": "#5c1e1e",
        "kpi_merge_bg": "#1e3f28",  # Dark green
        "kpi_merge_border": "#135422",
        "kpi_stats_bg": "#102c46",  # Dark blue
        "kpi_stats_border": "#0d3b66"
    }
}


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
        # Clean processing text and print with styled labels
        badge = "<span style='color: #0969da; font-weight: bold;'>[INFO]</span>"
        if "success" in info.lower() or "complete" in info.lower() or "done" in info.lower():
            badge = "<span style='color: #1a7f37; font-weight: bold;'>[SUCCESS]</span>"
        elif "warning" in info.lower() or "skip" in info.lower():
            badge = "<span style='color: #d17a00; font-weight: bold;'>[WARNING]</span>"

        self.helper.append_html.emit(f"{badge} {info}")
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

    ALGORITHM_ID = "eadelineation:createea"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Enumeration Areas")
        self.setMinimumSize(1150, 650)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowTitleHint
        )
        
        self.feedback = None
        self.current_theme = "light"
        
        # Initialize algorithm instance for help text metadata
        from .algorithm import CreateEAAlgorithm
        self.algo = CreateEAAlgorithm()
        
        # Candidate lists storage for live search/filter
        self.all_delineation_candidates = []
        self.all_merge_candidates = []
        
        self._build_ui()
        self._apply_theme()
        
        # Connect signals for live candidate previews and validators
        self._setup_preview_connections()
        self.auto_detect_layers()

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header Panel ──────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(85)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 10)
        header_layout.setSpacing(15)

        # Icon
        icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pix)
        else:
            icon_label.setText("🗺")
            icon_label.setFont(QFont("Segoe UI Emoji", 24))
        icon_label.setFixedSize(50, 50)
        icon_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(icon_label)

        # Title/Subtitle info
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("Create Enumeration Areas")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_col.addWidget(title)

        tagline = QLabel("GMD Pipeline  ·  1MAP Group  ·  v1.0.0")
        tagline.setObjectName("tagline")
        tagline.setFont(QFont("Segoe UI", 8))
        title_col.addWidget(tagline)
        header_layout.addLayout(title_col)
        
        header_layout.addStretch()

        # Theme selection
        theme_lbl = QLabel("Theme:")
        theme_lbl.setFont(QFont("Segoe UI", 9))
        header_layout.addWidget(theme_lbl)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light Mode", "Dark Mode", "Sync QGIS"])
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        header_layout.addWidget(self.theme_combo)

        root.addWidget(header)

        # ── Divider ───────────────────────────────────────────────────────
        root.addWidget(self._divider())

        # ── Main Pane Splitter ────────────────────────────────────────────
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setObjectName("mainSplitter")
        
        # Left Panel (Parameters Scroll Area)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(15, 15, 10, 15)
        left_layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 10, 0)
        scroll_layout.setSpacing(12)

        # 1. Inputs Section
        inputs_header_layout = QHBoxLayout()
        inputs_header_layout.addWidget(self._section_label("Input Layers"))
        inputs_header_layout.addStretch()
        
        # Auto-detect layers button
        self.detect_btn = QPushButton("🔍 Auto-detect Layers")
        self.detect_btn.setObjectName("detectBtn")
        self.detect_btn.setToolTip("Scan current QGIS project layers and auto-select matching layers.")
        self.detect_btn.clicked.connect(self.auto_detect_layers)
        inputs_header_layout.addWidget(self.detect_btn)

        # Fill missing hhcount from building points
        self.fill_missing_btn = QPushButton("🧮 Fill missing hhcount")
        self.fill_missing_btn.setObjectName("fillMissingBtn")
        self.fill_missing_btn.setToolTip("Compute and populate missing EA hhcount values from building points within each EA polygon.")
        self.fill_missing_btn.clicked.connect(self.fill_missing_hhcount)
        inputs_header_layout.addWidget(self.fill_missing_btn)
        
        scroll_layout.addLayout(inputs_header_layout)
        
        inputs_card = QFrame()
        inputs_card.setObjectName("formCard")
        inputs_layout = QVBoxLayout(inputs_card)
        inputs_layout.setSpacing(8)

        # Barangay Layer
        inputs_layout.addWidget(QLabel("Barangay Layer (Polygon)*"))
        self.bar_combo = QgsMapLayerComboBox()
        self.bar_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        inputs_layout.addWidget(self.bar_combo)
        self.bar_status_lbl = QLabel("No layer selected.")
        self.bar_status_lbl.setObjectName("statusLbl")
        inputs_layout.addWidget(self.bar_status_lbl)

        # Building Points
        inputs_layout.addWidget(QLabel("Building Point Layer (Point)*"))
        self.bldg_combo = QgsMapLayerComboBox()
        self.bldg_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        inputs_layout.addWidget(self.bldg_combo)
        self.bldg_status_lbl = QLabel("No layer selected.")
        self.bldg_status_lbl.setObjectName("statusLbl")
        inputs_layout.addWidget(self.bldg_status_lbl)

        # Previous EAs
        inputs_layout.addWidget(QLabel("Previous EA Layer (Polygon)*"))
        self.prev_ea_combo = QgsMapLayerComboBox()
        self.prev_ea_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        inputs_layout.addWidget(self.prev_ea_combo)
        self.prev_ea_status_lbl = QLabel("No layer selected.")
        self.prev_ea_status_lbl.setObjectName("statusLbl")
        inputs_layout.addWidget(self.prev_ea_status_lbl)

        # Road (Optional)
        inputs_layout.addWidget(QLabel("Road Layer (Line, Optional)"))
        self.road_combo = QgsMapLayerComboBox()
        self.road_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.road_combo.setAllowEmptyLayer(True)
        inputs_layout.addWidget(self.road_combo)
        self.road_status_lbl = QLabel("Optional.")
        self.road_status_lbl.setObjectName("statusLbl")
        inputs_layout.addWidget(self.road_status_lbl)

        # River (Optional)
        inputs_layout.addWidget(QLabel("River Layer (Line, Optional)"))
        self.river_combo = QgsMapLayerComboBox()
        self.river_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.river_combo.setAllowEmptyLayer(True)
        inputs_layout.addWidget(self.river_combo)
        self.river_status_lbl = QLabel("Optional.")
        self.river_status_lbl.setObjectName("statusLbl")
        inputs_layout.addWidget(self.river_status_lbl)

        scroll_layout.addWidget(inputs_card)

        # 2. Parameters Section
        params_card = QFrame()
        params_card.setObjectName("formCard")
        params_layout = QVBoxLayout(params_card)
        params_layout.setSpacing(10)

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
        self.tolerance_spin.setValue(20.0)
        params_layout.addWidget(self.tolerance_spin)

        # Compactness optimization
        self.compact_chk = QCheckBox("Optimize for Compactness")
        self.compact_chk.setChecked(True)
        params_layout.addWidget(self.compact_chk)

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

        scroll_layout.addWidget(self._create_collapsible_section("Delineation Thresholds Settings", params_card))

        # 3. Outputs Section
        outputs_card = QFrame()
        outputs_card.setObjectName("formCard")
        outputs_layout = QVBoxLayout(outputs_card)
        outputs_layout.setSpacing(10)

        # Delineated EAs Layer
        outputs_layout.addWidget(QLabel("Delineated EAs Layer"))
        self.delineated_path, self.delineated_edit = self._file_picker_row()
        outputs_layout.addLayout(self.delineated_path)

        # Merged EAs Layer
        outputs_layout.addWidget(QLabel("Merged EAs Layer"))
        self.merged_path, self.merged_edit = self._file_picker_row()
        outputs_layout.addLayout(self.merged_path)

        # Candidate for Delineation Layer
        outputs_layout.addWidget(QLabel("Delineation Candidate Layer"))
        self.delin_cand_path, self.delin_cand_edit = self._file_picker_row()
        outputs_layout.addLayout(self.delin_cand_path)

        # Candidate for Merging Layer
        outputs_layout.addWidget(QLabel("Merge Candidate Layer"))
        self.merge_cand_path, self.merge_cand_edit = self._file_picker_row()
        outputs_layout.addLayout(self.merge_cand_path)

        scroll_layout.addWidget(self._create_collapsible_section("Output Layers", outputs_card))
        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll)
        
        left_widget.setMinimumWidth(390)
        main_splitter.addWidget(left_widget)

        # Right Panel (Tabs for Live Preview and Execution Logs)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 15, 15, 15)
        right_layout.setSpacing(12)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("rightTabs")

        # ── Live Preview Tab ──────────────────────────────────────────────
        preview_tab = QWidget()
        preview_tab_layout = QVBoxLayout(preview_tab)
        preview_tab_layout.setContentsMargins(10, 10, 10, 10)
        preview_tab_layout.setSpacing(10)

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
        self.search_edit.setPlaceholderText("🔍 Filter previews by Barangay name, Geocode or EA name...")
        self.search_edit.textChanged.connect(self.filter_previews)
        preview_tab_layout.addWidget(self.search_edit)

        # Sub Tabs for candidates tables
        self.preview_sub_tabs = QTabWidget()
        self.preview_sub_tabs.setObjectName("previewSubTabs")

        # Table 1: Delineation Table
        self.delineation_table = self._create_preview_table()
        self.preview_sub_tabs.addTab(self.delineation_table, "Delineation Candidates")

        # Table 2: Merge Table
        self.merge_table = self._create_preview_table()
        self.preview_sub_tabs.addTab(self.merge_table, "Merge Candidates")

        preview_tab_layout.addWidget(self.preview_sub_tabs)
        
        # Refresh preview button
        self.refresh_btn = QPushButton("Refresh Live Candidates Preview")
        self.refresh_btn.setObjectName("refreshBtn")
        self.refresh_btn.setFixedHeight(30)
        self.refresh_btn.clicked.connect(self.generate_preview)
        preview_tab_layout.addWidget(self.refresh_btn)

        self.tab_widget.addTab(preview_tab, "Live Candidates Preview")

        # ── Execution Logs Tab ────────────────────────────────────────────
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(10, 10, 10, 10)
        logs_layout.setSpacing(10)

        # Console controls layout
        console_controls = QHBoxLayout()
        console_controls.addWidget(QLabel("Execution Logs:"))
        console_controls.addStretch()
        
        self.copy_logs_btn = QPushButton("📋 Copy Logs")
        self.copy_logs_btn.setToolTip("Copy entire log console history to clipboard.")
        self.copy_logs_btn.clicked.connect(self.copy_logs_to_clipboard)
        console_controls.addWidget(self.copy_logs_btn)
        
        self.clear_logs_btn = QPushButton("🗑 Clear Console")
        self.clear_logs_btn.setToolTip("Clear all text from the console.")
        self.clear_logs_btn.clicked.connect(self.log_console_clear)
        console_controls.addWidget(self.clear_logs_btn)
        
        logs_layout.addLayout(console_controls)

        self.log_console = QTextEdit()
        self.log_console.setObjectName("logConsole")
        self.log_console.setReadOnly(True)
        logs_layout.addWidget(self.log_console)

        self.tab_widget.addTab(logs_tab, "Processing Progress & Logs")

        right_layout.addWidget(self.tab_widget)
        
        right_widget.setMinimumWidth(500)
        main_splitter.addWidget(right_widget)

        # ── Help / Description Panel ──────────────────────────────────────
        self.help_panel = QWidget()
        self.help_panel.setObjectName("helpPanel")
        help_layout = QVBoxLayout(self.help_panel)
        help_layout.setContentsMargins(10, 15, 15, 15)
        help_layout.setSpacing(10)

        help_title = QLabel("Description")
        help_title.setObjectName("sectionLabel")
        help_layout.addWidget(help_title)

        self.help_text = QTextBrowser()
        self.help_text.setObjectName("helpText")
        self.help_text.setOpenExternalLinks(True)
        self.help_text.setHtml(self.algo.shortHelpString())
        help_layout.addWidget(self.help_text)

        self.help_panel.setMinimumWidth(280)
        main_splitter.addWidget(self.help_panel)
        
        # Set proportional initial widths for the panels
        main_splitter.setSizes([390, 500, 300])

        root.addWidget(main_splitter)

        # ── Bottom Bar (Progress, Run, Cancel) ────────────────────────────
        bottom_bar = QWidget()
        bottom_bar.setObjectName("bottomBar")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 0, 20, 0)
        bottom_layout.setSpacing(15)

        # Help Toggle Button
        self.help_btn = QPushButton("ℹ Hide Description")
        self.help_btn.setObjectName("helpBtn")
        self.help_btn.setFixedSize(160, 36)
        self.help_btn.clicked.connect(self.toggle_help)
        bottom_layout.addWidget(self.help_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)  # Limit height to make it sleek and compact
        bottom_layout.addWidget(self.progress_bar)

        # Actions
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setFixedSize(100, 36)
        self.cancel_btn.setEnabled(False)
        bottom_layout.addWidget(self.cancel_btn)

        self.run_btn = QPushButton("Run ▶")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.setFixedSize(160, 36)
        self.run_btn.clicked.connect(self.run_pipeline)
        bottom_layout.addWidget(self.run_btn)

        root.addWidget(self._divider())
        root.addWidget(bottom_bar)

    def toggle_help(self):
        """Toggle the visibility of the description help panel."""
        visible = self.help_panel.isVisible()
        self.help_panel.setVisible(not visible)
        if not visible:
            self.help_btn.setText("ℹ Hide Description")
        else:
            self.help_btn.setText("ℹ Show Description")

    def _divider(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("divider")
        line.setFixedHeight(1)
        return line

    def _section_label(self, text):
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))
        return lbl

    def _create_collapsible_section(self, title, card_widget):
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        btn = QPushButton(f"▼  {title.upper()}")
        btn.setObjectName("sectionToggle")
        btn.setCursor(Qt.PointingHandCursor)
        
        def toggle():
            visible = card_widget.isVisible()
            card_widget.setVisible(not visible)
            if visible:
                btn.setText(f"▶  {title.upper()}")
            else:
                btn.setText(f"▼  {title.upper()}")

        btn.clicked.connect(toggle)
        
        container_layout.addWidget(btn)
        container_layout.addWidget(card_widget)
        return container

    def _create_kpi_card(self, title, value, variant="stats"):
        card = QFrame()
        card.setObjectName("kpiCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(4)
        
        lbl_title = QLabel(title)
        lbl_title.setObjectName("kpiTitle")
        card_layout.addWidget(lbl_title)
        
        lbl_val = QLabel(value)
        lbl_val.setObjectName("kpiVal")
        lbl_val.setFont(QFont("Segoe UI", 16, QFont.Bold))
        card_layout.addWidget(lbl_val)
        
        # Store widgets reference for dynamic updates
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

    def _browse_file(self, line_edit):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Output Layer", "", "GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson)"
        )
        if path:
            line_edit.setText(path)

    def _create_preview_table(self):
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Geocode", "Barangay", "EA Name", "Household Count"])
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
        """Scan all loaded layers in QGIS project and automatically match inputs by name keywords."""
        layers = QgsProject.instance().mapLayers().values()
        
        barangay_keywords = ["barangay", "bgy", "brgy", "boundary", "admin"]
        building_keywords = ["building", "bldg", "point", "household", "hh", "structure"]
        pravea_keywords = ["previous", "prev", "ea", "enumeration"]
        road_keywords = ["road", "highway", "street", "way", "route"]
        river_keywords = ["river", "stream", "water", "drainage", "creek"]
        
        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            name_lower = layer.name().lower()
            
            # Barangay Layer (Polygon)
            if layer.geometryType() == 2:  # Polygon
                if any(k in name_lower for k in barangay_keywords) and not any(k in name_lower for k in pravea_keywords):
                    idx = self.bar_combo.findText(layer.name())
                    if idx != -1:
                        self.bar_combo.setCurrentIndex(idx)
                elif any(k in name_lower for k in pravea_keywords):
                    idx = self.prev_ea_combo.findText(layer.name())
                    if idx != -1:
                        self.prev_ea_combo.setCurrentIndex(idx)
                        
            # Building Points (Point)
            elif layer.geometryType() == 0:  # Point
                if any(k in name_lower for k in building_keywords):
                    idx = self.bldg_combo.findText(layer.name())
                    if idx != -1:
                        self.bldg_combo.setCurrentIndex(idx)
                        
            # Road/River (Line)
            elif layer.geometryType() == 1:  # Line
                if any(k in name_lower for k in river_keywords):
                    idx = self.river_combo.findText(layer.name())
                    if idx != -1:
                        self.river_combo.setCurrentIndex(idx)
                elif any(k in name_lower for k in road_keywords):
                    idx = self.road_combo.findText(layer.name())
                    if idx != -1:
                        self.road_combo.setCurrentIndex(idx)
                        
        self.validate_layer_inputs()

    def validate_layer_inputs(self):
        """Perform validation on selected layers and show dynamic status subtitles."""
        # 1. Barangay Layer
        bar_layer = self.bar_combo.currentLayer()
        if not bar_layer:
            self.bar_status_lbl.setText("🔴 Barangay Layer is required.")
            self.bar_status_lbl.setStyleSheet("color: #cf222e; font-style: italic;")
        else:
            self.bar_status_lbl.setText(f"🟢 Active: {bar_layer.featureCount()} polygons loaded ({bar_layer.crs().authid()}).")
            self.bar_status_lbl.setStyleSheet("color: #1a7f37;")

        # 2. Building Layer
        bldg_layer = self.bldg_combo.currentLayer()
        if not bldg_layer:
            self.bldg_status_lbl.setText("🔴 Building Point Layer is required.")
            self.bldg_status_lbl.setStyleSheet("color: #cf222e; font-style: italic;")
        else:
            fields = [f.name().lower() for f in bldg_layer.fields()]
            hh_found = any(f in fields for f in ["hhcount", "hh_count", "household", "household_count"])
            hh_msg = " (found hhcount)" if hh_found else " (no hhcount field)"
            self.bldg_status_lbl.setText(f"🟢 Active: {bldg_layer.featureCount()} points loaded{hh_msg}.")
            self.bldg_status_lbl.setStyleSheet("color: #1a7f37;")

        # 3. Previous EA Layer
        prev_ea_layer = self.prev_ea_combo.currentLayer()
        hh_found = False
        ean_found = False
        if not prev_ea_layer:
            self.prev_ea_status_lbl.setText("🔴 Previous EA Layer is required.")
            self.prev_ea_status_lbl.setStyleSheet("color: #cf222e; font-style: italic;")
        else:
            fields = [f.name().lower() for f in prev_ea_layer.fields()]
            hh_found = any(f in fields for f in ["hhcount", "hh_count", "household", "household_count"])
            ean_found = any(f in fields for f in ["ean", "ea_number", "ea_code", "id", "geocode"])

            if not hh_found:
                self.prev_ea_status_lbl.setText("🔴 Error: Missing 'hhcount' or 'household' field.")
                self.prev_ea_status_lbl.setStyleSheet("color: #cf222e; font-weight: bold;")
            elif not ean_found:
                self.prev_ea_status_lbl.setText("🔴 Error: Missing 'ean' or 'ea_number' geocode field.")
                self.prev_ea_status_lbl.setStyleSheet("color: #cf222e; font-weight: bold;")
            else:
                self.prev_ea_status_lbl.setText(f"🟢 Active: {prev_ea_layer.featureCount()} EAs loaded successfully.")
                self.prev_ea_status_lbl.setStyleSheet("color: #1a7f37;")

        # Enable fill-missing button only when required layers are present
        self.fill_missing_btn.setEnabled(bool(prev_ea_layer and bldg_layer and hh_found))
        road_layer = self.road_combo.currentLayer()
        if not road_layer:
            self.road_status_lbl.setText("🟡 Optional: Road boundary snapping will be skipped.")
            self.road_status_lbl.setStyleSheet("color: #d17a00; font-style: italic;")
        else:
            self.road_status_lbl.setText(f"🟢 Active: {road_layer.featureCount()} line features loaded.")
            self.road_status_lbl.setStyleSheet("color: #1a7f37;")

        # 5. River Layer (Optional)
        river_layer = self.river_combo.currentLayer()
        if not river_layer:
            self.river_status_lbl.setText("🟡 Optional: River boundary snapping will be skipped.")
            self.river_status_lbl.setStyleSheet("color: #d17a00; font-style: italic;")
        else:
            self.river_status_lbl.setText(f"🟢 Active: {river_layer.featureCount()} line features loaded.")
            self.river_status_lbl.setStyleSheet("color: #1a7f37;")
            
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

            if hh >= max_hh:
                self.all_delineation_candidates.append((ean_str, ea_name_str, bgy_name_str, hh))
            elif hh <= min_hh:
                self.all_merge_candidates.append((ean_str, ea_name_str, bgy_name_str, hh))

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
            if not query or query in row[0].lower() or query in row[1].lower() or query in row[2].lower():
                filtered_delin.append(row)
                
        filtered_merge = []
        for row in self.all_merge_candidates:
            if not query or query in row[0].lower() or query in row[1].lower() or query in row[2].lower():
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
        if self.current_theme == "dark":
            bg_col = "#3d2121" if is_delineation else "#1e3f28"
            fg_col = "#ff6b6b" if is_delineation else "#2ecc71"

        for row_idx, (ean_str, ea_name_str, bgy_name_str, hh) in enumerate(show_records):
            item_ean = QTableWidgetItem(ean_str)
            item_bgy = QTableWidgetItem(bgy_name_str)
            item_name = QTableWidgetItem(ea_name_str)
            item_hh = QTableWidgetItem(f"{hh:.0f}")
            
            item_ean.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_bgy.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_hh.setTextAlignment(Qt.AlignCenter)
            
            for item in [item_ean, item_name, item_bgy, item_hh]:
                item.setBackground(QColor(bg_col))
                item.setForeground(QColor(fg_col))
            
            table.setItem(row_idx, 0, item_ean)
            table.setItem(row_idx, 1, item_bgy)
            table.setItem(row_idx, 2, item_name)
            table.setItem(row_idx, 3, item_hh)

    # ── Console Controls ───────────────────────────────────────────────────

    def log_console_clear(self):
        """Clear output console logs."""
        self.log_console.clear()

    def copy_logs_to_clipboard(self):
        """Copy all console texts to Clipboard."""
        clipboard = QCoreApplication.instance().clipboard()
        clipboard.setText(self.log_console.toPlainText())
        self.log_console.append("<span style='color: #3498db; font-style: italic;'>[SYSTEM] Logs copied to clipboard.</span>")

    # ── Theme System ───────────────────────────────────────────────────────

    def _on_theme_changed(self, index):
        """Slot for Theme combo selection changes."""
        selection = self.theme_combo.currentText()
        if "Light" in selection:
            self.current_theme = "light"
        elif "Dark" in selection:
            self.current_theme = "dark"
        else:
            # Sync with QGIS system theme
            is_dark = self._is_qgis_dark_mode()
            self.current_theme = "dark" if is_dark else "light"
            
        self._apply_theme()
        
        # Trigger validation updates to refresh table highlights
        self.validate_layer_inputs()

    def _is_qgis_dark_mode(self):
        try:
            # Check the lightness of the main window's background color
            bg_color = self.parent().palette().window().color()
            return bg_color.lightness() < 128
        except Exception:
            return False

    def _apply_theme(self):
        """Inject customized QSS stylesheet based on selected theme variables."""
        p = THEME_PALETTES[self.current_theme]
        
        # Style KPI card widgets manually first to override stylesheet inheritance conflicts
        for lbl in [self.kpi_delin_card, self.kpi_merge_card]:
            lbl.setStyleSheet(f"""
                QFrame#kpiCard {{
                    border: 1px solid {p['divider']};
                    border-radius: 6px;
                }}
            """)
        
        # Custom backgrounds for KPI Cards
        self.kpi_delin_card.setStyleSheet(f"QFrame#kpiCard {{ background-color: {p['kpi_delin_bg']}; border: 1px solid {p['kpi_delin_border']}; }}")
        self.kpi_merge_card.setStyleSheet(f"QFrame#kpiCard {{ background-color: {p['kpi_merge_bg']}; border: 1px solid {p['kpi_merge_border']}; }}")
        
        # Style values inside KPI cards
        self.kpi_delin_val.setStyleSheet(f"color: {p['text']}; font-size: 16pt; font-weight: bold;")
        self.kpi_merge_val.setStyleSheet(f"color: {p['text']}; font-size: 16pt; font-weight: bold;")

        stylesheet_content = f"""
            QDialog {{
                background-color: {p['bg']};
                color: {p['text']};
                font-family: "Segoe UI", -apple-system, sans-serif;
            }}

            /* Header */
            QWidget#header {{
                background-color: {p['header']};
                border-bottom: 1px solid {p['divider']};
            }}
            QLabel#title   {{ color: {p['text']}; }}
            QLabel#tagline {{ color: {p['subtext']}; }}

            /* Splitter */
            QSplitter::handle {{
                background-color: {p['divider']};
            }}

            /* Labels */
            QLabel {{
                color: {p['text']};
                font-size: 9pt;
            }}
            QLabel#sectionLabel {{
                color: {p['accent']};
                letter-spacing: 0.5px;
                margin-top: 6px;
                margin-bottom: 2px;
            }}
            QLabel#statusLbl {{
                font-size: 8pt;
                font-style: italic;
            }}

            /* Group Cards */
            QFrame#formCard {{
                background-color: {p['card']};
                border: 1px solid {p['divider']};
                border-radius: 6px;
                padding: 10px;
            }}

            /* KPI Cards Info */
            QLabel#kpiTitle {{
                font-size: 8pt;
                font-weight: bold;
                text-transform: uppercase;
                color: {p['subtext']};
            }}

            /* Scrollbars */
            QScrollBar:vertical {{
                background-color: {p['bg']};
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {p['divider']};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            /* Console Output */
            QTextEdit#logConsole {{
                background-color: {p['console_bg']};
                color: {p['console_text']};
                font-family: "Consolas", "Courier New", monospace;
                font-size: 9pt;
                border: 1px solid {p['divider']};
                border-radius: 4px;
            }}

            /* Inputs */
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
                background-color: {p['input_bg']};
                color: {p['text']};
                border: 1px solid {p['divider']};
                border-radius: 4px;
                padding: 5px 7px;
                font-size: 9pt;
            }}
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{
                border-color: {p['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
                background: transparent;
            }}
            QComboBox QAbstractItemView {{
                background-color: {p['card']};
                color: {p['text']};
                selection-background-color: {p['accent']};
            }}

            /* Buttons */
            QPushButton {{
                background-color: {p['card']};
                color: {p['text']};
                border: 1px solid {p['divider']};
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 9pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {p['header']};
                border-color: {p['accent']};
            }}
            
            QPushButton#sectionToggle {{
                background-color: transparent;
                color: {p['accent']};
                border: none;
                border-radius: 0px;
                padding: 6px 0px 2px 0px;
                font-size: 8pt;
                font-weight: bold;
                letter-spacing: 0.5px;
                text-align: left;
            }}
            QPushButton#sectionToggle:hover {{
                background-color: transparent;
                border: none;
                color: {p['run_hover']};
            }}

            QPushButton#browseBtn {{
                background-color: {p['header']};
                padding: 2px 8px;
            }}

            QPushButton#refreshBtn, QPushButton#detectBtn {{
                color: {p['accent']};
                border: 1px solid {p['accent']};
            }}
            QPushButton#refreshBtn:hover, QPushButton#detectBtn:hover {{
                background-color: {p['accent']};
                color: #ffffff;
            }}

            QPushButton#cancelBtn {{
                border-color: {p['divider']};
            }}
            QPushButton#cancelBtn:hover:enabled {{
                background-color: #cf222e;
                color: #ffffff;
                border-color: #cf222e;
            }}

            QPushButton#runBtn {{
                background-color: {p['accent']};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 10pt;
            }}
            QPushButton#runBtn:hover:enabled {{
                background-color: {p['run_hover']};
            }}
            QPushButton#runBtn:disabled {{
                background-color: {p['divider']};
                color: {p['subtext']};
            }}

            /* Tabs */
            QTabWidget::pane {{
                border: 1px solid {p['divider']};
                background-color: {p['bg']};
                border-radius: 6px;
            }}
            QTabBar::tab {{
                background-color: {p['header']};
                border: 1px solid {p['divider']};
                border-bottom: none;
                padding: 6px 15px;
                color: {p['subtext']};
                font-weight: bold;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected, QTabBar::tab:hover {{
                background-color: {p['bg']};
                color: {p['accent']};
                border-color: {p['divider']};
            }}

            /* Help / Description Panel */
            QWidget#helpPanel {{
                background-color: {p['bg']};
            }}
            QTextBrowser#helpText {{
                background-color: {p['card']};
                color: {p['text']};
                border: 1px solid {p['divider']};
                border-radius: 6px;
                padding: 10px;
                font-size: 9pt;
            }}

            /* Tables */
            QTableWidget {{
                background-color: {p['table_bg']};
                border: 1px solid {p['divider']};
                gridline-color: {p['divider']};
                border-radius: 4px;
            }}
            QHeaderView::section {{
                background-color: {p['table_header_bg']};
                color: {p['text']};
                padding: 6px;
                border: 1px solid {p['divider']};
                font-weight: bold;
            }}

            /* Progress Bar */
            QProgressBar {{
                border: 1px solid {p['divider']};
                border-radius: 4px;
                text-align: center;
                color: {p['text']};
                font-weight: bold;
                background-color: {p['card']};
                height: 22px;
            }}
            QProgressBar::chunk {{
                background-color: {p['accent']};
                border-radius: 2px;
            }}
        """
        self.setStyleSheet(stylesheet_content)

        # Apply stylesheet to HTML content of the description panel
        help_doc_css = f"""
            h3 {{
                color: {p['accent']};
                font-size: 12pt;
                margin-top: 0px;
                margin-bottom: 8px;
                font-weight: bold;
            }}
            h4 {{
                color: {p['text']};
                font-size: 10pt;
                margin-top: 14px;
                margin-bottom: 4px;
                font-weight: bold;
                border-bottom: 1px solid {p['divider']};
                padding-bottom: 2px;
            }}
            p, li {{
                color: {p['text']};
                font-size: 9pt;
                line-height: 1.4;
            }}
            ul, ol {{
                margin-left: 18px;
                padding-left: 0px;
            }}
            li {{
                margin-bottom: 4px;
            }}
            b {{
                color: {p['text']};
            }}
        """
        self.help_text.document().setDefaultStyleSheet(help_doc_css)
        self.help_text.setHtml(self.algo.shortHelpString())

    # ── Pipeline Execution ──────────────────────────────────────────────────

    def run_pipeline(self):
        """Execute processing algorithm directly using custom feedback."""
        bar_layer = self.bar_combo.currentLayer()
        bldg_layer = self.bldg_combo.currentLayer()
        prev_ea_layer = self.prev_ea_combo.currentLayer()
        road_layer = self.road_combo.currentLayer()
        river_layer = self.river_combo.currentLayer()

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
            'SNAP_TOLERANCE': self.tolerance_spin.value(),
            'MIN_HOUSEHOLD': self.min_hh_spin.value(),
            'MAX_HOUSEHOLD': self.max_hh_spin.value(),
            'USE_COMPACTNESS': self.compact_chk.isChecked(),
            'SLIVER_THRESHOLD': self.sliver_combo.currentIndex(),
            'TARGET_CRS': self.crs_widget.crs(),
            'PREVIEW_ONLY': False,
            
            # Outputs
            'DELINEATED_OUTPUT': self.delineated_edit.text() or 'TEMPORARY_OUTPUT',
            'MERGED_OUTPUT': self.merged_edit.text() or 'TEMPORARY_OUTPUT',
            'DELINEATION_CANDIDATE_OUTPUT': self.delin_cand_edit.text() or 'TEMPORARY_OUTPUT',
            'MERGE_CANDIDATE_OUTPUT': self.merge_cand_edit.text() or 'TEMPORARY_OUTPUT',
        }

        # Clear UI state
        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.tab_widget.setCurrentIndex(1)

        self.log_console.append("<span style='color:#1a7f37; font-weight:bold;'>[START] Starting Create Enumeration Areas...</span>")
        QCoreApplication.processEvents()

        # Instantiate feedback
        self.feedback = CustomProcessingFeedback(self.progress_bar, self.log_console, self.run_btn, self.cancel_btn)
        self.feedback.progressChanged.connect(lambda val: self.feedback.helper.set_val.emit(int(val)))
        context = QgsProcessingContext()

        # Execute using QGIS Processing framework
        from qgis import processing
        
        try:
            results = processing.runAndLoadResults(
                self.ALGORITHM_ID,
                parameters,
                context=context,
                feedback=self.feedback
            )
            
            if self.feedback.isCanceled():
                self.log_console.append("<span style='color:#d17a00; font-weight:bold;'>[CANCEL] Pipeline execution cancelled by user.</span>")
            else:
                self.progress_bar.setValue(100)
                self.log_console.append("<span style='color:#1a7f37; font-weight:bold;'>[COMPLETE] Pipeline execution complete! Results loaded to map.</span>")

        except Exception as e:
            self.log_console.append(f"<span style='color:#cf222e; font-weight:bold;'>[FATAL] Error executing pipeline: {str(e)}</span>")
        
        finally:
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.feedback = None
