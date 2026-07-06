

from typing import Any, Optional

from qgis.core import (
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterString,
    QgsProcessingParameterCrs,
    QgsProcessingParameterEnum,
    QgsFeature,
    QgsGeometry,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsSpatialIndex,
)
from qgis import processing

from PyQt5.QtCore import QVariant, Qt
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSizePolicy,
    QCheckBox,
    QTabWidget,
)
from PyQt5.QtGui import QFont, QColor
from processing.gui.wrappers import WidgetWrapper


class TablePreviewWidgetWrapper(WidgetWrapper):
    """
    Custom widget wrapper that renders a live, color-coded QTabWidget preview
    of the EAs that are candidates for delineation and merging,
    updating dynamically before the algorithm is run.
    """

    def __init__(self, *args, **kwargs):
        self.container = None
        self.header_label = None
        self.stats_label = None
        self.tabs = None
        self.delineation_table = None
        self.merge_table = None
        self.refresh_btn = None
        
        self.prev_ea_input_wrapper = None
        self.ea_id_field_wrapper = None
        self.household_field_wrapper = None
        self.min_household_wrapper = None
        self.max_household_wrapper = None
        super().__init__(*args, **kwargs)

    def createWidget(self):
        self.container = QWidget()
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(6)
        
        header_layout = QHBoxLayout()
        self.header_label = QLabel("Candidates Preview (Before Running)")
        header_font = QFont("Segoe UI", 10, QFont.Bold)
        self.header_label.setFont(header_font)
        self.header_label.setStyleSheet("color: #1f6feb; margin-top: 10px;")
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        
        self.toggle_checkbox = QCheckBox("Show Preview Table")
        self.toggle_checkbox.setChecked(False)
        self.toggle_checkbox.setStyleSheet("""
            QCheckBox {
                color: #24292f;
                font-weight: bold;
                font-size: 11px;
                margin-top: 10px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.toggle_checkbox.stateChanged.connect(self.on_toggle_changed)
        header_layout.addWidget(self.toggle_checkbox)
        layout.addLayout(header_layout)
        
        self.stats_label = QLabel("Please configure all input parameters to generate a preview.")
        self.stats_label.setStyleSheet("color: #555; font-style: italic;")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        
        # Instantiate Tab Widget
        self.tabs = QTabWidget()
        
        # Table 1: Delineation Table
        self.delineation_table = QTableWidget()
        self.delineation_table.setColumnCount(4)
        self.delineation_table.setHorizontalHeaderLabels([
            "Geocode", "Barangay", "EA Name", "Household Count"
        ])
        self.delineation_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.delineation_table.horizontalHeader().setStretchLastSection(True)
        self.delineation_table.verticalHeader().setVisible(False)
        self.delineation_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.delineation_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.delineation_table.setAlternatingRowColors(True)
        self.delineation_table.setMinimumHeight(150)
        self.delineation_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Table 2: Merge Table
        self.merge_table = QTableWidget()
        self.merge_table.setColumnCount(4)
        self.merge_table.setHorizontalHeaderLabels([
            "Geocode", "Barangay", "EA Name", "Household Count"
        ])
        self.merge_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.merge_table.horizontalHeader().setStretchLastSection(True)
        self.merge_table.verticalHeader().setVisible(False)
        self.merge_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.merge_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.merge_table.setAlternatingRowColors(True)
        self.merge_table.setMinimumHeight(150)
        self.merge_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        table_style = """
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f7f9fc;
                border: 1px solid #dcdcdc;
                gridline-color: #e8e8e8;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #f0f4f8;
                padding: 6px;
                border: 1px solid #e0e0e0;
                font-weight: bold;
                color: #333333;
            }
        """
        self.delineation_table.setStyleSheet(table_style)
        self.merge_table.setStyleSheet(table_style)
        
        # Apply tab widget styling (makes it look clean, flat and premium)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #dcdcdc;
                background: white;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #f0f4f8;
                border: 1px solid #dcdcdc;
                border-bottom-color: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                color: #555555;
            }
            QTabBar::tab:selected, QTabBar::tab:hover {
                background: white;
                color: #1f6feb;
                border-bottom-color: white;
            }
        """)
        
        self.tabs.addTab(self.delineation_table, "Delineation")
        self.tabs.addTab(self.merge_table, "Merging")
        
        layout.addWidget(self.tabs)
        
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Preview")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                border: none;
                padding: 6px 12px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
            QPushButton:pressed {
                background-color: #1f7730;
            }
        """)
        self.refresh_btn.clicked.connect(self.generate_preview)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Initially hide elements until checkbox is checked
        self.tabs.setVisible(False)
        self.stats_label.setVisible(False)
        self.refresh_btn.setVisible(False)
        
        return self.container

    def on_toggle_changed(self, state):
        is_checked = (state == Qt.Checked)
        self.tabs.setVisible(is_checked)
        self.stats_label.setVisible(is_checked)
        self.refresh_btn.setVisible(is_checked)
        if is_checked:
            self.generate_preview()

    def postInitialize(self, wrappers):
        super().postInitialize(wrappers)
        for w in wrappers:
            name = w.parameterDefinition().name()
            if name == "PREVIOUS_EA_INPUT":
                self.prev_ea_input_wrapper = w
            elif name == "EA_ID_FIELD":
                self.ea_id_field_wrapper = w
            elif name == "HOUSEHOLD_FIELD":
                self.household_field_wrapper = w
            elif name == "MIN_HOUSEHOLD":
                self.min_household_wrapper = w
            elif name == "MAX_HOUSEHOLD":
                self.max_household_wrapper = w

        for w in [self.prev_ea_input_wrapper, self.ea_id_field_wrapper,
                  self.household_field_wrapper, self.min_household_wrapper,
                  self.max_household_wrapper]:
            if w:
                try:
                    w.widgetValueHasChanged.connect(self.trigger_auto_refresh)
                except Exception:
                    pass
        self.trigger_auto_refresh()

    def trigger_auto_refresh(self, *args, **kwargs):
        try:
            self.generate_preview()
        except Exception:
            pass

    def _get_wrapper_value(self, wrapper):
        if not wrapper:
            return ""
        if hasattr(wrapper, "value"):
            try:
                val = wrapper.value()
                if val is not None:
                    return val
            except Exception:
                pass
        if hasattr(wrapper, "parameterValue"):
            try:
                val = wrapper.parameterValue()
                if val is not None:
                    return val
            except Exception:
                pass
        return ""

    def _get_selected_layer(self, wrapper):
        if not wrapper:
            return None
        layer_val = self._get_wrapper_value(wrapper)
        if not layer_val:
            return None
        from qgis.core import QgsProject, QgsVectorLayer
        import os
        layer = QgsProject.instance().mapLayer(str(layer_val))
        if not layer or not layer.isValid():
            if os.path.exists(str(layer_val)):
                layer = QgsVectorLayer(str(layer_val), "temp_preview", "ogr")
        return layer if (layer and layer.isValid()) else None

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

    def generate_preview(self):
        if not self.delineation_table or not self.merge_table:
            return
        if hasattr(self, "toggle_checkbox") and not self.toggle_checkbox.isChecked():
            return
            
        self.delineation_table.setRowCount(0)
        self.merge_table.setRowCount(0)
        
        prev_ea_layer = self._get_selected_layer(self.prev_ea_input_wrapper)
        
        try:
            min_hh = float(self._get_wrapper_value(self.min_household_wrapper) or 100)
        except Exception:
            min_hh = 100.0
            
        try:
            max_hh = float(self._get_wrapper_value(self.max_household_wrapper) or 300)
        except Exception:
            max_hh = 300.0
            
        if not prev_ea_layer:
            self.stats_label.setText("📋 <i>Previous EA Layer is not selected.</i>")
            self.stats_label.setStyleSheet("color: #777; font-style: italic;")
            return

        fields = prev_ea_layer.fields()
        
        # Resolve household field index case-insensitively
        hh_idx = -1
        for i in range(fields.count()):
            name_lower = fields.at(i).name().lower()
            if name_lower in ["hhcount", "hh_count", "household", "household_count"]:
                hh_idx = i
                break
                
        # Resolve EA ID field index case-insensitively
        ean_idx = -1
        for i in range(fields.count()):
            name_lower = fields.at(i).name().lower()
            if name_lower in ["ean", "ea_number", "ea_code", "id", "geocode"]:
                ean_idx = i
                break

        # Resolve Barangay name field index case-insensitively
        bgy_name_idx = -1
        for i in range(fields.count()):
            name_lower = fields.at(i).name().lower()
            if name_lower in ["barangay", "bgy", "brgy", "barangay_name", "bgy_name", "brgy_name", "barangay_n", "bgy_n", "brgy_n"]:
                bgy_name_idx = i
                break
        
        if hh_idx == -1:
            self.stats_label.setText("Field 'hhcount' or 'household' not found in Previous EA layer.")
            self.stats_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
            return
        if ean_idx == -1:
            self.stats_label.setText("Field 'ean' or 'ea_number' not found in Previous EA layer.")
            self.stats_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
            return

        from qgis.core import QgsSpatialIndex
        
        # Build candidate lookup
        delineation_candidates = []
        merge_candidates = []
        
        temp_ea_index = QgsSpatialIndex()
        temp_ea_by_id = {}
        
        for feat in prev_ea_layer.getFeatures():
            ean_val = feat.attribute(ean_idx)
            ean_str = str(ean_val).strip() if ean_val is not None else ""
            if ean_str.endswith(".0"):
                ean_str = ean_str[:-2]
                
            ea_name_str = self._get_ea_name(feat, ean_str, fields)
                
            bgy_name_val = feat.attribute(bgy_name_idx) if bgy_name_idx != -1 else ""
            if bgy_name_val is None or (isinstance(bgy_name_val, QVariant) and bgy_name_val.isNull()):
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
                
            if hh >= max_hh:
                delineation_candidates.append((ean_str, ea_name_str, bgy_name_str, hh, feat))
                temp_ea_index.insertFeature(feat)
                temp_ea_by_id[feat.id()] = (ean_str, ea_name_str, bgy_name_str, hh, feat)
            elif hh <= min_hh:
                merge_candidates.append((ean_str, ea_name_str, bgy_name_str, hh, feat))
                temp_ea_index.insertFeature(feat)
                temp_ea_by_id[feat.id()] = (ean_str, ea_name_str, bgy_name_str, hh, feat)

        # 1. Populate Delineation Table
        show_delin = delineation_candidates[:15]
        self.delineation_table.setRowCount(len(show_delin))
        for row_idx, (ean_str, ea_name_str, bgy_name_str, hh, feat) in enumerate(show_delin):
            item_ean = QTableWidgetItem(ean_str)
            item_name = QTableWidgetItem(ea_name_str)
            item_bgy = QTableWidgetItem(bgy_name_str)
            item_hh = QTableWidgetItem(f"{hh:.0f}")
            
            item_ean.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_bgy.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_hh.setTextAlignment(Qt.AlignCenter)
            
            for item in [item_ean, item_name, item_bgy, item_hh]:
                item.setBackground(QColor("#fff5f5"))
            item_ean.setForeground(QColor("#cb2431"))
            
            self.delineation_table.setItem(row_idx, 0, item_ean)
            self.delineation_table.setItem(row_idx, 1, item_bgy)
            self.delineation_table.setItem(row_idx, 2, item_name)
            self.delineation_table.setItem(row_idx, 3, item_hh)

        # 2. Populate Merge Table
        show_merge = merge_candidates[:15]
        self.merge_table.setRowCount(len(show_merge))
        for row_idx, (ean_str, ea_name_str, bgy_name_str, hh, feat) in enumerate(show_merge):
            item_ean = QTableWidgetItem(ean_str)
            item_bgy = QTableWidgetItem(bgy_name_str)
            item_name = QTableWidgetItem(ea_name_str)
            item_hh = QTableWidgetItem(f"{hh:.0f}")
            
            item_ean.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_bgy.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_hh.setTextAlignment(Qt.AlignCenter)
            
            for item in [item_ean, item_bgy, item_name, item_hh]:
                item.setBackground(QColor("#f0fff4"))
            item_ean.setForeground(QColor("#22863a"))
            
            self.merge_table.setItem(row_idx, 0, item_ean)
            self.merge_table.setItem(row_idx, 1, item_bgy)
            self.merge_table.setItem(row_idx, 2, item_name)
            self.merge_table.setItem(row_idx, 3, item_hh)

        stats_text = (
            f"<b>Candidates Summary:</b> Found <b>{len(delineation_candidates)}</b> delineation candidate(s) "
            f"and <b>{len(merge_candidates)}</b> merge candidate(s) in Previous EA Layer. "
            f"Showing preview of first 15 records per sheet."
        )
        self.stats_label.setText(stats_text)
        self.stats_label.setStyleSheet("color: #0366d6; font-weight: bold; font-size: 11px;")

    def value(self):
        return "preview"

    def setValue(self, value):
        pass


class EADMCandidatesAlgorithm(QgsProcessingAlgorithm):
    """
    EADM Candidates Pipeline: Consolidates scanning, delineation, and merging logic
    into a single standalone workflow.
    """

    # Constants used to refer to parameters and outputs
    BARANGAY_INPUT = "BARANGAY_INPUT"
    BUILDING_INPUT = "BUILDING_INPUT"
    PREVIOUS_EA_INPUT = "PREVIOUS_EA_INPUT"
    BARANGAY_ID_FIELD = "BARANGAY_ID_FIELD"
    EA_ID_FIELD = "EA_ID_FIELD"
    HOUSEHOLD_FIELD = "HOUSEHOLD_FIELD"
    MIN_HOUSEHOLD = "MIN_HOUSEHOLD"
    MAX_HOUSEHOLD = "MAX_HOUSEHOLD"
    USE_COMPACTNESS = "USE_COMPACTNESS"
    TARGET_CRS = "TARGET_CRS"
    OUTPUT = "OUTPUT"
    DELINEATED_OUTPUT = "DELINEATED_OUTPUT"
    MERGED_OUTPUT = "MERGED_OUTPUT"
    DELINEATION_CANDIDATE_OUTPUT = "DELINEATION_CANDIDATE_OUTPUT"
    MERGE_CANDIDATE_OUTPUT = "MERGE_CANDIDATE_OUTPUT"
    EXTRACTED_BUILDINGS_OUTPUT = "EXTRACTED_BUILDINGS_OUTPUT"
    SLIVER_THRESHOLD = "SLIVER_THRESHOLD"
    PREVIEW_ONLY = "PREVIEW_ONLY"
    PREVIEW = "PREVIEW"
    # New optional linear layer parameters
    ROAD_INPUT = "ROAD_INPUT"
    RIVER_INPUT = "RIVER_INPUT"
    SNAP_TOLERANCE = "SNAP_TOLERANCE"
    # Buffer tolerance (meters) for snapping splits to linear features
    LINE_BUFFER_TOLERANCE = 0.5

    def name(self) -> str:
        """Returns the algorithm name (unique identifier)."""
        return "eadmcandidates"

    def displayName(self) -> str:
        """Returns the translated algorithm name for display."""
        return "EADM Candidates Pipeline"

    def createInstance(self):
        return EADMCandidatesAlgorithm()

    def group(self) -> str:
        """Returns the name of the algorithm group."""
        return "1MAP"

    def groupId(self) -> str:
        """Returns the unique ID of the group."""
        return "eadelineation"

    def shortHelpString(self) -> str:
        """Returns a short description of the algorithm."""
        return (
            "<h3>Create Enumeration Areas</h3>"
            "<p>Delineates new Enumeration Areas (EAs) by spatially aggregating or splitting "
            "existing EA polygons to meet household-count thresholds, with optional alignment "
            "to road and river boundaries.</p>"

            "<h4>Inputs</h4>"
            "<b>Required</b>"
            "<ul>"
            "<li><b>Barangay Layer</b> (polygon) — Administrative barangay boundaries. "
            "Must contain a <i>geocode</i> field used to assign parent barangay codes to output EAs.</li>"
            "<li><b>Building Point Layer</b> (point) — Structure/building points with an "
            "<i>hhcount</i> field representing the household count per building. "
            "Used to calculate the total household load of each EA candidate.</li>"
            "<li><b>Previous EA Layer</b> (polygon) — Starting EA boundaries from the previous "
            "census round. Must contain a <i>geocode</i> field. "
            "Fields and region attributes from this layer are inherited by the output.</li>"
            "<li><b>Minimum / Maximum Household Count per EA</b> — Target range (default 100–300 HH). "
            "EAs below the minimum are merged with neighbours; EAs above the maximum are split.</li>"
            "<li><b>Optimize for Compactness</b> — When enabled, the clustering algorithm "
            "prefers spatially compact EA shapes over purely household-balanced splits.</li>"
            "<li><b>Sliver Polygon Area Threshold</b> — Controls how small a remnant polygon "
            "must be before it is discarded as a sliver. <i>Auto-detect</i> derives the threshold "
            "from the average nearest-neighbour spacing of building points.</li>"
            "<li><b>Target CRS</b> — Output coordinate reference system (default EPSG:4326).</li>"
            "</ul>"
            "<b>Optional</b>"
            "<ul>"
            "<li><b>Road Layer</b> (line) — Road network used to snap EA split boundaries "
            "to road centrelines, producing more survey-friendly EAs.</li>"
            "<li><b>River Layer</b> (line) — River/waterway network used in the same "
            "boundary-snapping process as the road layer.</li>"
            "<li><b>Snapping Tolerance (metres)</b> — Maximum distance a proposed split line "
            "is shifted to coincide with the nearest road or river segment (default 20 m).</li>"
            "</ul>"

            "<h4>Process</h4>"
            "<ol>"
            "<li>Auto-detects project layers by name pattern (_bgy, _ea, _bldgpts, road, river).</li>"
            "<li>Transforms building points to the barangay/EA CRS if they differ.</li>"
            "<li>Spatially joins building points to starting EAs and sums <i>hhcount</i> per EA.</li>"
            "<li>EAs within the target range are passed through unchanged.</li>"
            "<li>Over-populated EAs are split using weighted K-Means clustering on building points, "
            "optionally snapping split boundaries to road/river lines.</li>"
            "<li>Under-populated EAs are merged with the most suitable adjacent EA in the "
            "same barangay, guided by compactness scoring when enabled.</li>"
            "<li>Sliver polygons smaller than the chosen area threshold are dissolved into "
            "their largest neighbour.</li>"
            "<li>Each output EA inherits attributes from the previous EA layer and receives "
            "updated household count, building-count, and split-method fields.</li>"
            "</ol>"

            "<h4>Output</h4>"
            "<ul>"
            "<li><b>Output EA Layer</b> (polygon, named <i>&lt;5-digit geocode&gt;_ea2026</i>) — "
            "All fields from the previous EA layer are preserved. Additional/updated fields:</li>"
            "<ul>"
            "<li><i>hhcount</i> / <i>hh_count</i> — Total household count for the EA.</li>"
            "<li><i>bldg_count</i> — Number of building points within the EA.</li>"
            "<li><i>split_by</i> — Method used to split the EA (e.g. <i>road</i>, <i>river</i>, "
            "<i>kmeans</i>), or empty if unchanged/merged.</li>"
            "<li><i>new_ea</i> — Flag indicating whether the EA is newly created.</li>"
            "<li><i>correspondence_ea_geocode</i> — Geocode of the originating previous EA.</li>"
            "</ul>"
            "<li><b>Delineated EAs Layer</b> (optional polygon, named <i>&lt;5-digit geocode&gt;_delineated_ea2026</i>) — "
            "Contains all sub-polygons generated from delineation, fully covering the split candidate EAs (including parts internally merged to satisfy min_household).</li>"
            "<li><b>Merged EAs Layer</b> (optional polygon, named <i>&lt;5-digit geocode&gt;_merged_ea2026</i>) — "
            "Contains only EAs created by merging distinct starting EAs.</li>"
            "</ul>"
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        """Defines the inputs and outputs of the algorithm."""
        from qgis.core import QgsProject
        
        # Auto-detect layers in the current QGIS project
        default_bgy = None
        default_ea = None
        default_bldgpts = None
        default_road = None
        default_river = None
        
        from qgis.core import QgsMessageLog, Qgis
        try:
            layers = QgsProject.instance().mapLayers().values()
            QgsMessageLog.logMessage(f"Auto-detecting layers. Project has {len(layers)} layers.", "EA Creation", Qgis.Info)
            for layer in layers:
                name_lower = layer.name().lower()
                QgsMessageLog.logMessage(f"Checking layer: {layer.name()}", "EA Creation", Qgis.Info)
                if "_bgy" in name_lower and default_bgy is None:
                    default_bgy = layer
                    QgsMessageLog.logMessage(f"Selected {layer.name()} as Barangay default.", "EA Creation", Qgis.Info)
                elif "_ea" in name_lower and default_ea is None:
                    default_ea = layer
                    QgsMessageLog.logMessage(f"Selected {layer.name()} as EA default.", "EA Creation", Qgis.Info)
                elif ("_bldgpts" in name_lower or "_bldg_point" in name_lower or "_bldg_points" in name_lower) and default_bldgpts is None:
                    default_bldgpts = layer
                    QgsMessageLog.logMessage(f"Selected {layer.name()} as Building Points default.", "EA Creation", Qgis.Info)
                elif "road" in name_lower and default_road is None:
                    default_road = layer
                    QgsMessageLog.logMessage(f"Selected {layer.name()} as Road default.", "EA Creation", Qgis.Info)
                elif "river" in name_lower and default_river is None:
                    default_river = layer
                    QgsMessageLog.logMessage(f"Selected {layer.name()} as River default.", "EA Creation", Qgis.Info)
        except Exception as e:
            QgsMessageLog.logMessage(f"Error auto-detecting layers: {str(e)}", "EA Creation", Qgis.Critical)

        # Barangay polygon input
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BARANGAY_INPUT,
                "Barangay Layer",
                [QgsProcessing.SourceType.TypeVectorPolygon],
                defaultValue=default_bgy,
            )
        )
       
        # Building point input
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BUILDING_INPUT,
                "Building Point Layer",
                [QgsProcessing.SourceType.TypeVectorPoint],
                defaultValue=default_bldgpts,
            )
        )

        # Previous EA layer (required for region assignment)
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.PREVIOUS_EA_INPUT,
                "Previous EA Layer",
                [QgsProcessing.SourceType.TypeVectorPolygon],
                defaultValue=default_ea,
            )
        )
        
        # Optional Road layer
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ROAD_INPUT,
                "Road Layer (optional)",
                [QgsProcessing.SourceType.TypeVectorLine],
                defaultValue=default_road,
                optional=True,
            )
        )
        # Optional River layer
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.RIVER_INPUT,
                "River Layer (optional)",
                [QgsProcessing.SourceType.TypeVectorLine],
                defaultValue=default_river,
                optional=True,
            )
        )

        # Snapping Tolerance
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SNAP_TOLERANCE,
                "Snapping Tolerance (meters) for road/river alignment",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=20.0,
                minValue=0.0,
            )
        )

        # Hidden fields for Barangay ID, EA ID, and Household Count are hardcoded in processAlgorithm

        # Minimum household threshold
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MIN_HOUSEHOLD,
                "Minimum Household Count per EA",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=100,
                minValue=1,
            )
        )

        # Maximum household threshold
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_HOUSEHOLD,
                "Maximum Household Count per EA",
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=300,
                minValue=1,
            )
        )


        # Use compactness optimization
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.USE_COMPACTNESS,
                "Optimize for Compactness",
                defaultValue=True,
            )
        )

        # Sliver Polygon Area Threshold (options for automatic threshold chosen based on CRS units)
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SLIVER_THRESHOLD,
                "Sliver Polygon Area Threshold",
                options=[
                    "Auto-detect (Script Chosen / Dynamic)",
                    "Automatic (Conservative - 1e-11 deg / 1e-4 m²)",
                    "Automatic (Standard - 1e-9 deg / 1e-2 m²)",
                    "Automatic (Moderate - 1e-7 deg / 1 m²)",
                    "Automatic (Aggressive - 1e-5 deg / 100 m²)",
                    "Automatic (Ultra-Conservative - 1e-13 deg / 1e-6 m²)",
                    "Automatic (Super Aggressive - 1e-4 deg / 1,000 m²)",
                    "Automatic (Extremely Aggressive - 1e-3 deg / 10,000 m²)"
                ],
                defaultValue=0,
            )
        )

        # Target CRS (Defaulting to EPSG:4326)
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS,
                "Target CRS",
                defaultValue="EPSG:4326",
            )
        )

        # Preview Candidates Only checkbox
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PREVIEW_ONLY,
                "Preview Candidates Only (Exit early after creating candidate layers)",
                defaultValue=False,
            )
        )

        # Candidates Preview Table (using custom TablePreviewWidgetWrapper)
        preview_param = QgsProcessingParameterString(
            self.PREVIEW,
            "Candidates Preview Table",
            defaultValue="",
            optional=True,
        )
        preview_param.setMetadata({"widget_wrapper": {"class": TablePreviewWidgetWrapper}})
        self.addParameter(preview_param)

        # Output layer
#        self.addParameter(
#            QgsProcessingParameterFeatureSink(
#                self.OUTPUT,
#                "Output EA Layer",
#            )
#        )

        # Delineated output layer
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.DELINEATED_OUTPUT,
                "Delineated EAs Layer",
                optional=True,
            )
        )

        # Merged output layer
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.MERGED_OUTPUT,
                "Merged EAs Layer",
                optional=True,
            )
        )

        # Candidate for delineation output layer
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.DELINEATION_CANDIDATE_OUTPUT,
                "Candidate for Delineation Layer",
                type=QgsProcessing.SourceType.TypeVector,
                optional=True,
            )
        )

        # Candidate for merging output layer
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.MERGE_CANDIDATE_OUTPUT,
                "Candidate for Merging Layer",
                type=QgsProcessing.SourceType.TypeVector,
                optional=True,
            )
        )

        # Extracted building points output layer
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.EXTRACTED_BUILDINGS_OUTPUT,
                "Extracted Building Points Layer",
                type=QgsProcessing.SourceType.TypeVectorPoint,
                optional=True,
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        """Main processing logic for EA creation."""
        # Yield to GUI event loop to ensure QGIS remains responsive and Cancel click is registered
        from qgis.PyQt.QtCore import QCoreApplication, QThread
        def yield_to_ui(counter, interval=250):
            if counter % interval == 0:
                if QThread.currentThread() == QCoreApplication.instance().thread():
                    QCoreApplication.processEvents()

        import math
        import random
        from qgis.PyQt.QtCore import QVariant
        from qgis.core import (
            QgsFields,
            QgsField,
            QgsSpatialIndex,
            QgsFeature,
            QgsGeometry,
            QgsPointXY,
            QgsWkbTypes,
            QgsCoordinateTransform,
        )

        # ── Multi-step progress feedback ───────────────────────────────────────────────────────
        # Divides the overall QGIS progress bar into 9 labelled phases.
        # Each phase maps its own 0–100 % to a proportional slice of the total bar.
        _TOTAL_PHASES = 8
        _PHASE_LABELS = [
            "Phase 1/8: Initializing",
            "Phase 2/8: Scanning Candidates & Matching Buildings",
            "Phase 3/8: Indexing Roads & Rivers",
            "Phase 4/8: Loading EAs",
            "Phase 5/8: Splitting EAs",
            "Phase 6/8: Merging EAs",
            "Phase 7/8: Compliance Sweep",
            "Phase 8/8: Writing Output",
        ]
        from qgis.core import QgsProcessingMultiStepFeedback
        multi_feedback = QgsProcessingMultiStepFeedback(_TOTAL_PHASES, feedback)
        multi_feedback.setCurrentStep(0)
        multi_feedback.setProgressText(f"{_PHASE_LABELS[0]}...")
        feedback.pushInfo("Phase 1/8: Initializing — reading parameters...")
        # ──────────────────────────────────────────────────────────────────────────────────────

        # Retrieve input parameters
        barangay_source = self.parameterAsSource(
            parameters, self.BARANGAY_INPUT, context
        )
        if barangay_source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.BARANGAY_INPUT)
            )

        building_source = self.parameterAsSource(
            parameters, self.BUILDING_INPUT, context
        )
        if building_source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.BUILDING_INPUT)
            )

        previous_ea_source = self.parameterAsSource(
            parameters, self.PREVIOUS_EA_INPUT, context
        )
        if previous_ea_source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.PREVIOUS_EA_INPUT)
            )
        # Retrieve optional linear layers
        road_source = self.parameterAsSource(parameters, self.ROAD_INPUT, context)
        river_source = self.parameterAsSource(parameters, self.RIVER_INPUT, context)
        snap_tolerance_m = self.parameterAsDouble(parameters, self.SNAP_TOLERANCE, context)
        preview_only = self.parameterAsBoolean(parameters, self.PREVIEW_ONLY, context)

        # Resolve dynamic field names from Previous EA Layer case-insensitively
        ea_fields = previous_ea_source.fields()
        
        # 1. EA ID field
        ea_id_field = "ean"  # Default fallback
        for i in range(ea_fields.count()):
            name_lower = ea_fields.at(i).name().lower()
            if name_lower in ["ean", "ea_number", "ea_code", "id", "geocode"]:
                ea_id_field = ea_fields.at(i).name()
                break
                
        # 2. Household field
        household_field = "hhcount"  # Default fallback
        for i in range(ea_fields.count()):
            name_lower = ea_fields.at(i).name().lower()
            if name_lower in ["hhcount", "hh_count", "household", "household_count"]:
                household_field = ea_fields.at(i).name()
                break

        # Resolve household field in Building Point Layer (strictly "hhcount")
        bldg_fields = building_source.fields()
        bldg_hh_field = "hhcount"
        for i in range(bldg_fields.count()):
            if bldg_fields.at(i).name().lower() == "hhcount":
                bldg_hh_field = bldg_fields.at(i).name()
                break

        # 3. Barangay geocode field in EA layer
        barangay_id_field = "geocode"  # Default fallback
        for i in range(ea_fields.count()):
            name_lower = ea_fields.at(i).name().lower()
            if name_lower in ["geocode", "bgy_geocode", "brgy_geocode", "barangay_code"]:
                barangay_id_field = ea_fields.at(i).name()
                break

        # Resolve geocode field in Barangay Layer
        bar_fields = barangay_source.fields()
        bar_geocode_field = "geocode"
        for i in range(bar_fields.count()):
            name_lower = bar_fields.at(i).name().lower()
            if name_lower in ["geocode", "bgy_geocode", "brgy_geocode", "barangay_code"]:
                bar_geocode_field = bar_fields.at(i).name()
                break
        min_household = self.parameterAsInt(
            parameters, self.MIN_HOUSEHOLD, context
        )
        max_household = self.parameterAsInt(
            parameters, self.MAX_HOUSEHOLD, context
        )
        target_household = int((min_household + max_household) / 2)
        target_crs = self.parameterAsCrs(
            parameters, self.TARGET_CRS, context
        )

        # Build spatial index of active Barangays first to filter EAs early
        feedback.pushInfo("Building spatial index of Barangay Layer...")
        barangay_index = QgsSpatialIndex()
        barangay_by_id = {}
        active_barangay_geocodes = set()
        
        # We also need the index of the geocode field in the Barangay layer
        bar_geocode_idx = barangay_source.fields().indexOf(bar_geocode_field)
        
        for idx, feat in enumerate(barangay_source.getFeatures()):
            if feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            yield_to_ui(idx)
            barangay_index.insertFeature(feat)
            barangay_by_id[feat.id()] = feat
            
            if bar_geocode_idx != -1:
                val = feat.attribute(bar_geocode_idx)
                if val is not None:
                    val_str = str(val).strip()
                    if val_str.endswith(".0"):
                        val_str = val_str[:-2]
                    if val_str:
                        if len(val_str) > 9:
                            val_str = val_str[:9]
                        active_barangay_geocodes.add(val_str)

        # Helpers for parent barangay lookup
        _dc_geo_idx = previous_ea_source.fields().indexOf(barangay_id_field)
        if _dc_geo_idx == -1:
            _dc_geo_idx = previous_ea_source.fields().indexOf("geocode")

        def get_parent_barangay(ea_geom):
            candidates = barangay_index.intersects(ea_geom.boundingBox())
            max_overlap = -1
            parent_feat = None
            for cid in candidates:
                bar = barangay_by_id[cid]
                bar_geom = bar.geometry()
                if bar_geom.intersects(ea_geom):
                    overlap_area = bar_geom.intersection(ea_geom).area()
                    if overlap_area > max_overlap:
                        max_overlap = overlap_area
                        parent_feat = bar
            return parent_feat

        def resolve_ea_parent_barangay(ea_feat):
            if _dc_geo_idx != -1:
                val = ea_feat.attribute(_dc_geo_idx)
                if val is not None and not (isinstance(val, QVariant) and val.isNull()):
                    val_str = str(val).strip()
                    if val_str.endswith(".0"):
                        val_str = val_str[:-2]
                    if val_str:
                        return val_str
            # Fallback to spatial overlay
            parent_feat = get_parent_barangay(ea_feat.geometry())
            if parent_feat:
                val = parent_feat.attribute(barangay_id_field)
                if val is not None:
                    val_str = str(val).strip()
                    if val_str.endswith(".0"):
                        val_str = val_str[:-2]
                    return val_str
            return "Unknown"

        # Load and cache only previous EA features that reside within our active Barangays
        feedback.pushInfo("Caching relevant previous EA features in memory...")
        all_ea_features = []
        _ea_load_cnt = 0
        for feat in previous_ea_source.getFeatures():
            if feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                parent_bar = resolve_ea_parent_barangay(feat)
                if parent_bar and parent_bar != "Unknown" and parent_bar in active_barangay_geocodes:
                    all_ea_features.append(feat)
            _ea_load_cnt += 1
            yield_to_ui(_ea_load_cnt, 1000)

        # Extract 5-digit geocode prefix for output layer naming
        geocode_prefix = ""
        try:
            for feat in barangay_source.getFeatures():
                val = feat.attribute(barangay_id_field)
                if val is not None:
                    val_str = str(val).strip()
                    if val_str.endswith(".0"):
                        val_str = val_str[:-2]
                    digits = "".join([c for c in val_str if c.isdigit()])
                    if len(digits) >= 5:
                        geocode_prefix = digits[:5]
                        break
                    elif len(digits) > 0 and not geocode_prefix:
                        geocode_prefix = digits
        except Exception as e:
            feedback.pushInfo(f"Error extracting geocode prefix from Barangay layer: {str(e)}")

        if not geocode_prefix:
            try:
                # Try previous_ea_source just in case
                ea_geocode_field = "geocode"
                if previous_ea_source.fields().indexOf(ea_geocode_field) != -1:
                    for feat in all_ea_features:
                        val = feat.attribute(ea_geocode_field)
                        if val is not None:
                            val_str = str(val).strip()
                            if val_str.endswith(".0"):
                                val_str = val_str[:-2]
                            digits = "".join([c for c in val_str if c.isdigit()])
                            if len(digits) >= 5:
                                geocode_prefix = digits[:5]
                                break
            except Exception as e:
                feedback.pushInfo(f"Error extracting geocode prefix from Previous EA layer: {str(e)}")

        if not geocode_prefix:
            geocode_prefix = "00000"

        output_layer_name = f"{geocode_prefix}_ea2026"
        feedback.pushInfo(f"Calculated output layer name: {output_layer_name}")
        
        # Determine snapping tolerance and densification distance in target CRS map units
        if target_crs.isGeographic():
            # target CRS uses degrees (e.g. EPSG:4326)
            snap_tolerance = snap_tolerance_m / 111320.0
            densify_dist = 10.0 / 111320.0  # densify every 10 meters in degrees
        else:
            # target CRS uses meters or projected units
            snap_tolerance = snap_tolerance_m
            densify_dist = 10.0  # densify every 10 meters

        # Prepare CRS transformation for buildings if necessary
        source_crs = previous_ea_source.sourceCrs()
        building_crs = building_source.sourceCrs()
        transform = None
        if source_crs != building_crs:
            feedback.pushInfo(f"Transforming buildings from {building_crs.authid()} to {source_crs.authid()}...")
            transform = QgsCoordinateTransform(building_crs, source_crs, context.transformContext())

        # Retrieve sliver threshold option and dynamically determine area_threshold
        sliver_threshold_idx = self.parameterAsInt(
            parameters, self.SLIVER_THRESHOLD, context
        )
        is_geo = source_crs.isGeographic()
        if sliver_threshold_idx == 0:  # Auto-detect (Script Chosen / Dynamic)
            feedback.pushInfo("Calculating sliver threshold based on clustering/spacing of building points...")
            sample_pts = []
            bldg_count = building_source.featureCount()
            if bldg_count > 0:
                sample_step = max(1, bldg_count // 1000)
                cnt = 0
                for feat in building_source.getFeatures():
                    if cnt % sample_step == 0:
                        geom = feat.geometry()
                        if geom and not geom.isEmpty():
                            if transform:
                                geom_clone = QgsGeometry(geom)
                                geom_clone.transform(transform)
                                p = geom_clone.asPoint()
                            else:
                                p = geom.asPoint()
                            sample_pts.append(p)
                    cnt += 1
                    if len(sample_pts) >= 1000:
                        break
            
            if len(sample_pts) > 1:
                sample_index = QgsSpatialIndex()
                pt_geoms = {}
                for idx, pt in enumerate(sample_pts):
                    f = QgsFeature(idx)
                    f.setGeometry(QgsGeometry.fromPointXY(pt))
                    sample_index.insertFeature(f)
                    pt_geoms[idx] = pt
                
                distances = []
                for idx, pt in enumerate(sample_pts):
                    # nearestNeighbor returns the k-nearest feature IDs.
                    # The closest one will be the point itself (dist 0), so we request 2 neighbors.
                    neighbors = sample_index.nearestNeighbor(pt, 2)
                    for n_id in neighbors:
                        if n_id != idx:
                            n_pt = pt_geoms[n_id]
                            dist = pt.distance(n_pt)
                            if dist > 0: # ignore exact duplicates
                                distances.append(dist)
                            break
                
                if distances:
                    avg_nn_dist = sum(distances) / len(distances)
                    auto_threshold = 0.01 * (avg_nn_dist ** 2)
                    feedback.pushInfo(f"Average nearest neighbor building spacing: {avg_nn_dist:.6f}. Calculated raw threshold: {auto_threshold:.12f}")
                else:
                    auto_threshold = None
            else:
                auto_threshold = None
                
            if auto_threshold is not None:
                # Apply bounds safety checks based on CRS units
                if is_geo:
                    area_threshold = max(1e-13, min(auto_threshold, 1e-3))
                else:
                    area_threshold = max(1e-6, min(auto_threshold, 10000.0))
            else:
                # Fallback if building points are not clustered or insufficient points
                # Calculate the average area of the starting EAs provided in previous_ea_source
                total_ea_area = 0.0
                valid_ea_count = 0
                for feat in all_ea_features:
                    geom = feat.geometry()
                    if geom and not geom.isEmpty():
                        total_ea_area += geom.area()
                        valid_ea_count += 1
                
                if valid_ea_count > 0:
                    avg_ea_area = total_ea_area / valid_ea_count
                    # sliver threshold is 1e-7 of average EA area
                    auto_threshold = avg_ea_area * 1e-7
                    # bounds safety check
                    if is_geo:
                        area_threshold = max(1e-13, min(auto_threshold, 1e-9))
                    else:
                        area_threshold = max(1e-6, min(auto_threshold, 1.0))
                else:
                    # fallback if no valid features
                    area_threshold = 1e-11 if is_geo else 1e-4
        elif sliver_threshold_idx == 1:  # Automatic (Conservative)
            area_threshold = 1e-11 if is_geo else 1e-4
        elif sliver_threshold_idx == 2:  # Automatic (Standard)
            area_threshold = 1e-9 if is_geo else 1e-2
        elif sliver_threshold_idx == 3:  # Automatic (Moderate)
            area_threshold = 1e-7 if is_geo else 1.0
        elif sliver_threshold_idx == 4:  # Automatic (Aggressive)
            area_threshold = 1e-5 if is_geo else 100.0
        elif sliver_threshold_idx == 5:  # Automatic (Ultra-Conservative)
            area_threshold = 1e-13 if is_geo else 1e-6
        elif sliver_threshold_idx == 6:  # Automatic (Super Aggressive)
            area_threshold = 1e-4 if is_geo else 1000.0
        elif sliver_threshold_idx == 7:  # Automatic (Extremely Aggressive)
            area_threshold = 1e-3 if is_geo else 10000.0
        else:
            area_threshold = 1e-11 if is_geo else 1e-4

        feedback.pushInfo(f"Using automatically chosen sliver polygon area threshold: {area_threshold}")

        import os
        cpu_cores = os.cpu_count()
        num_cores = max(1, cpu_cores - 4) if cpu_cores else 4

        # Create output schema (inherits all fields from previous_ea_source)
        out_fields = QgsFields(previous_ea_source.fields())
        
        # Determine the name of the household field in the output.
        output_hh_field = "household"
        if household_field in [f.name() for f in out_fields]:
            output_hh_field = household_field
        else:
            out_fields.append(QgsField(output_hh_field, QVariant.Double))

        # Add split_by field if not already present
        if "split_by" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("split_by", QVariant.String))

        # Add new_ea field if not already present
        if "new_ea" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("new_ea", QVariant.String))

        # Add bldg_count field if not already present
        if "bldg_count" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("bldg_count", QVariant.Int))

        # Add hh_count field if not already present
        if "hh_count" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("hh_count", QVariant.Double))

        # Add hhcount field if not already present
        if "hhcount" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("hhcount", QVariant.Double))

        # Add bldgpoints_value field if not already present
        if "bldgpoints_value" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("bldgpoints_value", QVariant.Double))

        # Add correspondence_ea_geocode field if not already present
        if "correspondence_ea_geocode" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("correspondence_ea_geocode", QVariant.String))


        out_wkb_type = QgsWkbTypes.multiType(previous_ea_source.wkbType())

        sink = None
        dest_id = None
#        (sink, dest_id) = self.parameterAsSink(
#            parameters,
#            self.OUTPUT,
#            context,
#            out_fields,
#            out_wkb_type,
#            target_crs,
#        )
#
#        if sink is None:
#            raise QgsProcessingException(
#                self.invalidSinkError(parameters, self.OUTPUT)
#            )

        delineated_sink = None
        delineated_dest_id = None
        if self.DELINEATED_OUTPUT in parameters and parameters[self.DELINEATED_OUTPUT] is not None:
            (delineated_sink, delineated_dest_id) = self.parameterAsSink(
                parameters,
                self.DELINEATED_OUTPUT,
                context,
                out_fields,
                out_wkb_type,
                target_crs,
            )

        merged_sink = None
        merged_dest_id = None
        if self.MERGED_OUTPUT in parameters and parameters[self.MERGED_OUTPUT] is not None:
            (merged_sink, merged_dest_id) = self.parameterAsSink(
                parameters,
                self.MERGED_OUTPUT,
                context,
                out_fields,
                out_wkb_type,
                target_crs,
            )

        extracted_buildings_sink = None
        extracted_buildings_dest_id = None
        if self.EXTRACTED_BUILDINGS_OUTPUT in parameters and parameters[self.EXTRACTED_BUILDINGS_OUTPUT] is not None:
            bldg_out_fields = QgsFields(building_source.fields())
            if bldg_out_fields.indexOf("parent_ean") == -1:
                bldg_out_fields.append(QgsField("parent_ean", QVariant.String))
                
            bldgpts_idx = bldg_out_fields.indexOf("bldgpoints_value")
            if bldgpts_idx == -1:
                bldgpts_idx = bldg_out_fields.indexOf("bldgpts_val")
            if bldgpts_idx == -1:
                bldg_out_fields.append(QgsField("bldgpoints_value", QVariant.Double))
                
            pop_out_idx = bldg_out_fields.indexOf("pop")
            if pop_out_idx == -1:
                pop_out_idx = bldg_out_fields.indexOf(bldg_hh_field)
            if pop_out_idx == -1:
                bldg_out_fields.append(QgsField("pop", QVariant.Double))

            (extracted_buildings_sink, extracted_buildings_dest_id) = self.parameterAsSink(
                parameters,
                self.EXTRACTED_BUILDINGS_OUTPUT,
                context,
                bldg_out_fields,
                building_source.wkbType(),
                target_crs,
            )

        delin_candidate_sink = None
        delin_candidate_dest_id = None
        if self.DELINEATION_CANDIDATE_OUTPUT in parameters and parameters[self.DELINEATION_CANDIDATE_OUTPUT] is not None:
            delin_cand_fields = QgsFields(out_fields)
            for fname in [output_hh_field, "hh_count", "hhcount"]:
                if fname.lower() != household_field.lower():
                    idx = delin_cand_fields.indexOf(fname)
                    if idx != -1:
                        delin_cand_fields.remove(idx)
            if delin_cand_fields.indexOf("eadel_indi") == -1:
                delin_cand_fields.append(QgsField("eadel_indi", QVariant.String))
            (delin_candidate_sink, delin_candidate_dest_id) = self.parameterAsSink(
                parameters,
                self.DELINEATION_CANDIDATE_OUTPUT,
                context,
                delin_cand_fields,
                out_wkb_type,
                target_crs,
            )

        merge_partner_idx = -1
        merge_cand_fields = QgsFields(out_fields)

        merge_candidate_sink = None
        merge_candidate_dest_id = None
        if self.MERGE_CANDIDATE_OUTPUT in parameters and parameters[self.MERGE_CANDIDATE_OUTPUT] is not None:
            merge_cand_fields_filtered = QgsFields(merge_cand_fields)
            for fname in [output_hh_field, "hh_count", "hhcount"]:
                if fname.lower() != household_field.lower():
                    idx = merge_cand_fields_filtered.indexOf(fname)
                    if idx != -1:
                        merge_cand_fields_filtered.remove(idx)
            for fname in ["merge_partner", "split_by", "new_ea", "bldg_count", "bldgpoints_value", "bldgpts_val", "bldgpoint_value"]:
                idx = merge_cand_fields_filtered.indexOf(fname)
                if idx != -1:
                    merge_cand_fields_filtered.remove(idx)
            if merge_cand_fields_filtered.indexOf("merge_indi") == -1:
                merge_cand_fields_filtered.append(QgsField("merge_indi", QVariant.String))
            (merge_candidate_sink, merge_candidate_dest_id) = self.parameterAsSink(
                parameters,
                self.MERGE_CANDIDATE_OUTPUT,
                context,
                merge_cand_fields_filtered,
                out_wkb_type,
                target_crs,
            )

        outputs = {}
#        outputs = {self.OUTPUT: dest_id}
        if delineated_dest_id is not None:
            outputs[self.DELINEATED_OUTPUT] = delineated_dest_id
        if merged_dest_id is not None:
            outputs[self.MERGED_OUTPUT] = merged_dest_id
        if delin_candidate_dest_id is not None:
            outputs[self.DELINEATION_CANDIDATE_OUTPUT] = delin_candidate_dest_id
        if merge_candidate_dest_id is not None:
            outputs[self.MERGE_CANDIDATE_OUTPUT] = merge_candidate_dest_id
        if extracted_buildings_dest_id is not None:
            outputs[self.EXTRACTED_BUILDINGS_OUTPUT] = extracted_buildings_dest_id

#        try:
#            if context.willLoadLayerOnCompletion(dest_id):
#                details = context.layerToLoadOnCompletionDetails(dest_id)
#                details.name = output_layer_name
#                feedback.pushInfo(f"Set completion layer name to: {output_layer_name}")
#        except Exception as e:
#            feedback.pushInfo(f"Could not set output layer completion name: {str(e)}")

        try:
            if delineated_dest_id and context.willLoadLayerOnCompletion(delineated_dest_id):
                details = context.layerToLoadOnCompletionDetails(delineated_dest_id)
                details.name = f"{geocode_prefix}_delineated_ea2026"
                feedback.pushInfo(f"Set completion layer name to: {geocode_prefix}_delineated_ea2026")
        except Exception as e:
            feedback.pushInfo(f"Could not set delineated layer completion name: {str(e)}")

        try:
            if merged_dest_id and context.willLoadLayerOnCompletion(merged_dest_id):
                details = context.layerToLoadOnCompletionDetails(merged_dest_id)
                details.name = f"{geocode_prefix}_merged_ea2026"
                feedback.pushInfo(f"Set completion layer name to: {geocode_prefix}_merged_ea2026")
        except Exception as e:
            feedback.pushInfo(f"Could not set merged layer completion name: {str(e)}")

        try:
            if delin_candidate_dest_id and context.willLoadLayerOnCompletion(delin_candidate_dest_id):
                details = context.layerToLoadOnCompletionDetails(delin_candidate_dest_id)
                details.name = f"{geocode_prefix}_delineation_candidates_ea2026"
                feedback.pushInfo(f"Set completion layer name to: {geocode_prefix}_delineation_candidates_ea2026")
        except Exception as e:
            feedback.pushInfo(f"Could not set delineation candidate layer completion name: {str(e)}")

        try:
            if merge_candidate_dest_id and context.willLoadLayerOnCompletion(merge_candidate_dest_id):
                details = context.layerToLoadOnCompletionDetails(merge_candidate_dest_id)
                details.name = f"{geocode_prefix}_merge_candidates_ea2026"
                feedback.pushInfo(f"Set completion layer name to: {geocode_prefix}_merge_candidates_ea2026")
        except Exception as e:
            feedback.pushInfo(f"Could not set merge candidate layer completion name: {str(e)}")

        try:
            if extracted_buildings_dest_id and context.willLoadLayerOnCompletion(extracted_buildings_dest_id):
                details = context.layerToLoadOnCompletionDetails(extracted_buildings_dest_id)
                details.name = f"{geocode_prefix}_extracted_buildings_ea2026"
                feedback.pushInfo(f"Set completion layer name to: {geocode_prefix}_extracted_buildings_ea2026")
        except Exception as e:
            feedback.pushInfo(f"Could not set extracted buildings layer completion name: {str(e)}")

        # Transform target for output/candidates
        barangay_to_target = None
        if previous_ea_source.sourceCrs() != target_crs:
            feedback.pushInfo(f"Transforming output/candidates to {target_crs.authid()}...")
            barangay_to_target = QgsCoordinateTransform(
                previous_ea_source.sourceCrs(), target_crs, context.transformContext()
            )

        feedback.pushInfo(f"Previous EA Source CRS: {previous_ea_source.sourceCrs().authid()}")
        feedback.pushInfo(f"Target CRS: {target_crs.authid()}")
        feedback.pushInfo(f"Household Threshold: {min_household} - {max_household} HH (Target: {target_household} HH)")

        # Count features for progress calculation
        previous_ea_count = len(all_ea_features)
        barangay_count = barangay_source.featureCount()
        building_count = building_source.featureCount()
        
        feedback.pushInfo(f"Input Barangay Count: {barangay_count}")
        feedback.pushInfo(f"Input Previous EA Count: {previous_ea_count}")
        feedback.pushInfo(f"Input Building Count: {building_count}")
        multi_feedback.setProgress(100)  # Phase 1 complete

        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")

        # ── Phase 1.5: hhcount Imputation from Building Points ───────────────────────
        # Before classifying candidates, fill any null or zero hhcount in the EA layer
        # by summing the hhcount of all building points that fall within each EA polygon.
        # This ensures the preview and the full run use the same effective hhcount values.
        feedback.pushInfo(
            "Phase 1.5: Imputing null/zero hhcount from building points within each EA..."
        )

        # Build a lightweight spatial index of ALL building points
        _imp_bldg_index = QgsSpatialIndex()
        _imp_bldg_by_id = {}   # fid -> (QgsPointXY, pop_value)
        _imp_bldg_count = 0

        # Resolve building hhcount field (use same household_field as EA layer; fallback variants)
        _imp_bldg_hh_field = household_field
        _bldg_fields = building_source.fields()
        if _bldg_fields.indexOf(_imp_bldg_hh_field) == -1:
            for _candidate_name in ["hhcount", "hh_count", "household", "household_count", "pop", "population"]:
                if _bldg_fields.indexOf(_candidate_name) != -1:
                    _imp_bldg_hh_field = _candidate_name
                    break

        _imp_bldg_hh_idx = _bldg_fields.indexOf(_imp_bldg_hh_field)

        for _bfeat in building_source.getFeatures():
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            _bgeom = _bfeat.geometry()
            if not _bgeom or _bgeom.isEmpty():
                continue
            # Transform building point to EA CRS if needed
            if transform:
                _bgeom = QgsGeometry(_bgeom)
                _bgeom.transform(transform)
            _bpt = _bgeom.asPoint()
            _bpop_val = _bfeat.attribute(_imp_bldg_hh_idx) if _imp_bldg_hh_idx != -1 else None
            try:
                _bpop = float(_bpop_val) if _bpop_val is not None else 1.0
            except (TypeError, ValueError):
                _bpop = 1.0
            # Insert a point feature into the index
            _bindex_feat = QgsFeature(_bfeat.id())
            _bindex_feat.setGeometry(_bgeom)
            _imp_bldg_index.insertFeature(_bindex_feat)
            _imp_bldg_by_id[_bfeat.id()] = (_bpt, _bpop)
            _imp_bldg_count += 1
            yield_to_ui(_imp_bldg_count, 1000)

        feedback.pushInfo(f"  Indexed {_imp_bldg_count:,} building points for hhcount imputation.")

        # For each EA with null or zero hhcount, count buildings within it
        _dc_pop_idx_imp = previous_ea_source.fields().indexOf(household_field)
        imputed_hhcount = {}   # feat.id() -> imputed float hhcount

        for _ea_feat in previous_ea_source.getFeatures():
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            _ea_hh_val = _ea_feat.attribute(_dc_pop_idx_imp) if _dc_pop_idx_imp != -1 else None
            # Determine if imputation is needed
            _needs_imputation = False
            if _ea_hh_val is None or (isinstance(_ea_hh_val, QVariant) and _ea_hh_val.isNull()):
                _needs_imputation = True
            else:
                try:
                    if float(_ea_hh_val) == 0.0:
                        _needs_imputation = True
                except (TypeError, ValueError):
                    _needs_imputation = True

            if not _needs_imputation:
                continue

            _ea_geom = _ea_feat.geometry()
            if not _ea_geom or _ea_geom.isEmpty():
                continue  # Can't impute without a geometry

            # Sum hhcount of all building points within this EA
            _ea_bbox = _ea_geom.boundingBox()
            _nearby_bldg_ids = _imp_bldg_index.intersects(_ea_bbox)
            _total_bldg_hh = 0.0
            for _bid in _nearby_bldg_ids:
                if _bid not in _imp_bldg_by_id:
                    continue
                _bpt, _bpop = _imp_bldg_by_id[_bid]
                _bpt_geom = QgsGeometry.fromPointXY(_bpt)
                if _ea_geom.contains(_bpt_geom) or _ea_geom.intersects(_bpt_geom):
                    _total_bldg_hh += _bpop

            imputed_hhcount[_ea_feat.id()] = _total_bldg_hh
            feedback.pushInfo(
                f"  EA (FID={_ea_feat.id()}) had null/zero hhcount — imputed {_total_bldg_hh:.0f} HH "
                f"from {len(_nearby_bldg_ids)} nearby building point(s)."
            )

        feedback.pushInfo(
            f"  hhcount imputation complete: {len(imputed_hhcount)} EA(s) imputed from building points."
        )

        # ── Phase 2: Identifying and saving delineation and merge candidates ──────────
        multi_feedback.setCurrentStep(1)
        multi_feedback.setProgressText(f"{_PHASE_LABELS[1]}...")

        feedback.pushInfo("Phase 2/8: Identifying and saving delineation and merge candidates...")
        delineation_candidate_ids = set()
        merge_candidate_ids = set()
        delineation_candidate_hhdivthres = {}   # EAN -> hhdivthres (hhcount / max_household)
        delineation_candidates_by_geocode = {}  # geocode -> list of (EAN, hhdivthres) tuples
        delineation_candidate_bar_geocodes = set()

        _dc_pop_idx = previous_ea_source.fields().indexOf(household_field)
        if _dc_pop_idx == -1:
            raise QgsProcessingException("Error: The required 'hhcount' (or configured household) field does not exist in the input Previous EA layer.")

        _dc_geo_idx = previous_ea_source.fields().indexOf(barangay_id_field)
        if _dc_geo_idx == -1:
            _dc_geo_idx = previous_ea_source.fields().indexOf("geocode")

        total_ea_processed = 0
        total_delin_candidates = 0

        ea_to_target = None
        if previous_ea_source.sourceCrs() != target_crs:
            ea_to_target = QgsCoordinateTransform(
                previous_ea_source.sourceCrs(), target_crs, context.transformContext()
            )

        # Phase 2 scans ALL EAs in the source layer — identical to what the preview widget sees.
        # Only the later processing phases (Phases 5-9) use the barangay-filtered all_ea_features.
        # Use imputed_hhcount to override null/zero hhcount values resolved in Phase 1.5.
        for _dc_feat in previous_ea_source.getFeatures():
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            total_ea_processed += 1
            yield_to_ui(total_ea_processed)
            
            _dc_hh = 0.0
            _dc_val = _dc_feat.attribute(_dc_pop_idx)
            # Use Phase 1.5 imputed value if this EA had null/zero hhcount
            if _dc_feat.id() in imputed_hhcount:
                _dc_hh = imputed_hhcount[_dc_feat.id()]
            elif _dc_val is None or (isinstance(_dc_val, QVariant) and _dc_val.isNull()):
                _dc_hh = 0.0  # No geometry to impute from — treat as 0 HH (merge candidate)
            else:
                try:
                    _dc_hh = float(_dc_val)
                except (TypeError, ValueError):
                    _dc_hh = 0.0

            _dc_ean = _dc_feat.attribute(ea_id_field)
            _dc_ean_str = str(_dc_ean).strip() if _dc_ean is not None else ""

            if _dc_hh >= max_household:
                total_delin_candidates += 1
                _dc_hhdivthres = max_household / _dc_hh
                delineation_candidate_ids.add(_dc_feat.id())
                delineation_candidate_hhdivthres[_dc_feat.id()] = _dc_hhdivthres
                _dc_geo = ""
                if _dc_geo_idx != -1:
                    _dc_geo_val = _dc_feat.attribute(_dc_geo_idx)
                    _dc_geo = str(_dc_geo_val).strip() if _dc_geo_val is not None else ""
                delineation_candidates_by_geocode.setdefault(_dc_geo, []).append(
                    (_dc_ean_str, _dc_hhdivthres)
                )
                
                parent_bar = resolve_ea_parent_barangay(_dc_feat)
                if parent_bar and parent_bar != "Unknown":
                    delineation_candidate_bar_geocodes.add(parent_bar)
            elif _dc_hh <= min_household:
                merge_candidate_ids.add(_dc_feat.id())

        # Write to delineation candidate sink (both initiators and other EAs within their barangays)
        if delin_candidate_sink is not None:
            for feat in previous_ea_source.getFeatures():
                if multi_feedback.isCanceled():
                    raise QgsProcessingException("Algorithm cancelled by user.")
                parent_bar = resolve_ea_parent_barangay(feat)
                if parent_bar and parent_bar in delineation_candidate_bar_geocodes:
                    out_feat = QgsFeature(delin_cand_fields)
                    _dc_geom = feat.geometry()
                    if ea_to_target:
                        _dc_geom = QgsGeometry(_dc_geom)
                        _dc_geom.transform(ea_to_target)
                    out_feat.setGeometry(_dc_geom)
                    attrs = []
                    for f in delin_cand_fields:
                        orig_idx = feat.fields().indexOf(f.name())
                        if orig_idx != -1:
                            attrs.append(feat.attribute(orig_idx))
                        else:
                            attrs.append(None)
                    out_feat.setAttributes(attrs)
                    corr_ea_geo_idx = delin_cand_fields.indexOf("correspondence_ea_geocode")
                    if corr_ea_geo_idx != -1:
                        map_uuid_idx = delin_cand_fields.indexOf("map_uuid")
                        geocode_idx = delin_cand_fields.indexOf("geocode")
                        sy_idx = delin_cand_fields.indexOf("sy")
                        map_uuid_val = out_feat.attribute(map_uuid_idx) if map_uuid_idx != -1 else ""
                        geocode_val = out_feat.attribute(geocode_idx) if geocode_idx != -1 else ""
                        sy_val = out_feat.attribute(sy_idx) if sy_idx != -1 else ""
                        map_uuid_str = str(map_uuid_val) if map_uuid_val is not None else ""
                        geocode_str = str(geocode_val) if geocode_val is not None else ""
                        sy_str = str(sy_val) if sy_val is not None else ""
                        if map_uuid_str.endswith(".0"): map_uuid_str = map_uuid_str[:-2]
                        if geocode_str.endswith(".0"): geocode_str = geocode_str[:-2]
                        if sy_str.endswith(".0"): sy_str = sy_str[:-2]
                        out_feat.setAttribute(corr_ea_geo_idx, f"{map_uuid_str}:{geocode_str}:{sy_str}")
                    
                    eadel_indi_idx = delin_cand_fields.indexOf("eadel_indi")
                    if eadel_indi_idx != -1:
                        indi_val = "for delineation" if feat.id() in delineation_candidate_ids else "ea_reference"
                        out_feat.setAttribute(eadel_indi_idx, indi_val)
                        
                    delin_candidate_sink.addFeature(out_feat)

        feedback.pushInfo(
            f"Delineation Candidate Index: {len(delineation_candidate_ids)} EA(s) flagged "
            f"for delineation across {len(delineation_candidates_by_geocode)} barangay(s)."
        )
        # feedback.pushInfo(f"  {'EAN':<20} {'hhdivthres':>12}")
        # feedback.pushInfo(f"  {'-'*20} {'-'*12}")
        # for _dc_geo, _dc_entries in sorted(delineation_candidates_by_geocode.items()):
        #     feedback.pushInfo(f"  Geocode {_dc_geo}:")
        #     for _dc_ean_str, _dc_ratio in sorted(_dc_entries, key=lambda x: x[0]):
        #         feedback.pushInfo(f"    {_dc_ean_str:<20} {_dc_ratio:>12.4f}")

        self.total_ea_processed = total_ea_processed
        self.total_delin_candidates = total_delin_candidates

        # Barangay index and helpers are already created during Phase 1
        pass

        # Build a FULL spatial index of all EAs (not just candidates) so merge partners
        # can be any touching EA in the same barangay — matching the preview widget logic.
        feedback.pushInfo("Building full previous EA spatial index for merge partner lookup...")
        full_ea_index = QgsSpatialIndex()
        full_ea_by_id = {}
        for feat in previous_ea_source.getFeatures():
            full_ea_index.insertFeature(feat)
            full_ea_by_id[feat.id()] = feat

        # Find contiguous neighbors for merge candidates and write to merge candidate sink.
        # Iterate ALL EAs in the source — same scope as the preview widget.
        feedback.pushInfo("Identifying contiguous partners for Merge Candidates...")
        merge_candidates_by_geocode = {}
        adjacent_ea_ids = set()
        for feat in previous_ea_source.getFeatures():
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            _dc_val = feat.attribute(_dc_pop_idx)
            # Match preview widget: null or non-numeric hhcount = 0.0 (merge candidate)
            if _dc_val is None or (isinstance(_dc_val, QVariant) and _dc_val.isNull()):
                _dc_hh = 0.0
            else:
                try:
                    _dc_hh = float(_dc_val)
                except (TypeError, ValueError):
                    _dc_hh = 0.0

            if _dc_hh <= min_household:
                partners = []
                candidates = full_ea_index.intersects(geom.boundingBox())
                parent_bar_geo = resolve_ea_parent_barangay(feat)

                for cid in candidates:
                    if cid == feat.id():
                        continue
                    nb_feat = full_ea_by_id[cid]
                    if geom.touches(nb_feat.geometry()) or geom.intersects(nb_feat.geometry()):
                        nb_parent_bar_geo = resolve_ea_parent_barangay(nb_feat)
                        if parent_bar_geo and nb_parent_bar_geo and parent_bar_geo == nb_parent_bar_geo:
                            nb_ean = nb_feat.attribute(ea_id_field)
                            nb_ean_str = str(nb_ean).strip() if nb_ean is not None else ""
                            if nb_ean_str.endswith(".0"):
                                nb_ean_str = nb_ean_str[:-2]
                            if nb_ean_str:
                                adjacent_ea_ids.add(nb_feat.id())
                            
                            nb_hh_val = nb_feat.attribute(_dc_pop_idx)
                            try:
                                nb_hh = float(nb_hh_val) if nb_hh_val is not None else 0.0
                            except (TypeError, ValueError):
                                nb_hh = 0.0
                            if nb_hh < max_household:
                                if nb_ean_str:
                                    partners.append(nb_ean_str)
                
                _mc_ean = feat.attribute(ea_id_field)
                _mc_ean_str = str(_mc_ean).strip() if _mc_ean is not None else ""
                merge_candidates_by_geocode.setdefault(parent_bar_geo, []).append(
                    (_mc_ean_str, _dc_hh, partners)
                )

        # Write to merge_candidate_sink (both initiators and contiguous neighbor/partner EAs)
        if merge_candidate_sink is not None:
            merge_related_ids = merge_candidate_ids | adjacent_ea_ids
            for feat in previous_ea_source.getFeatures():
                if multi_feedback.isCanceled():
                    raise QgsProcessingException("Algorithm cancelled by user.")
                _ean = feat.attribute(ea_id_field)
                _ean_str = str(_ean).strip() if _ean is not None else ""
                if _ean_str.endswith(".0"):
                    _ean_str = _ean_str[:-2]
                if feat.id() in merge_related_ids:
                    # Resolve partners list if this is a merge initiator, otherwise empty list
                    partners = []
                    for _mc_entries in merge_candidates_by_geocode.values():
                        for _mc_ean_str, _mc_hh, _mc_partners in _mc_entries:
                            if _mc_ean_str == _ean_str:
                                partners = _mc_partners
                                break
                    
                    out_feat = QgsFeature(merge_cand_fields_filtered)
                    _dc_geom = feat.geometry()
                    if ea_to_target:
                        _dc_geom = QgsGeometry(_dc_geom)
                        _dc_geom.transform(ea_to_target)
                    out_feat.setGeometry(_dc_geom)
                    attrs = []
                    for f in merge_cand_fields_filtered:
                        orig_idx = feat.fields().indexOf(f.name())
                        if orig_idx != -1:
                            attrs.append(feat.attribute(orig_idx))
                        else:
                            attrs.append(None)
                    out_feat.setAttributes(attrs)
                    corr_ea_geo_idx = merge_cand_fields_filtered.indexOf("correspondence_ea_geocode")
                    if corr_ea_geo_idx != -1:
                        map_uuid_idx = merge_cand_fields_filtered.indexOf("map_uuid")
                        geocode_idx = merge_cand_fields_filtered.indexOf("geocode")
                        sy = merge_cand_fields_filtered.indexOf("sy")
                        map_uuid_val = out_feat.attribute(map_uuid_idx) if map_uuid_idx != -1 else ""
                        geocode_val = out_feat.attribute(geocode_idx) if geocode_idx != -1 else ""
                        sy_val = out_feat.attribute(sy) if sy != -1 else ""
                        map_uuid_str = str(map_uuid_val) if map_uuid_val is not None else ""
                        geocode_str = str(geocode_val) if geocode_val is not None else ""
                        sy_str = str(sy_val) if sy_val is not None else ""
                        if map_uuid_str.endswith(".0"): map_uuid_str = map_uuid_str[:-2]
                        if geocode_str.endswith(".0"): geocode_str = geocode_str[:-2]
                        if sy_str.endswith(".0"): sy_str = sy_str[:-2]
                        out_feat.setAttribute(corr_ea_geo_idx, f"{map_uuid_str}:{geocode_str}:{sy_str}")
                    filtered_partner_idx = merge_cand_fields_filtered.indexOf("merge_partner")
                    if filtered_partner_idx != -1:
                        out_feat.setAttribute(filtered_partner_idx, ",".join(sorted(partners)))
                    
                    merge_indi_idx = merge_cand_fields_filtered.indexOf("merge_indi")
                    if merge_indi_idx != -1:
                        indi_val = "for merging" if feat.id() in merge_candidate_ids else "merge_partner"
                        out_feat.setAttribute(merge_indi_idx, indi_val)
                        
                    merge_candidate_sink.addFeature(out_feat)

        # Build temporal previous EA index (candidates and adjacent EAs only) of the active Barangays for subsequent phases
        feedback.pushInfo("Building temporal previous EA index (candidates and adjacent EAs only)...")
        temp_ea_index = QgsSpatialIndex()
        temp_ea_by_id = {}
        for feat in all_ea_features:
            _ean = feat.attribute(ea_id_field)
            _ean_str = str(_ean).strip() if _ean is not None else ""
            if _ean_str.endswith(".0"):
                _ean_str = _ean_str[:-2]
            if feat.id() in delineation_candidate_ids or feat.id() in merge_candidate_ids or feat.id() in adjacent_ea_ids:
                temp_ea_index.insertFeature(feat)
                temp_ea_by_id[feat.id()] = feat

        ea_index = temp_ea_index
        ea_by_id = temp_ea_by_id

# Stream buildings on-the-fly and match to starting EAs using candidate spatial index memory
        feedback.pushInfo("Phase 2/8: Extracting candidate building points building points to EAs...")
        # Pre-cache EA geometries to enable internal GEOS prepared geometry acceleration
        ea_geometries = {fid: feat.geometry() for fid, feat in ea_by_id.items()}
        ea_id_to_buildings = {}
        
        # Combine bounding boxes of all candidate and adjacent EAs to perform a single query
        from qgis.core import QgsRectangle, QgsFeatureRequest
        combined_bbox = QgsRectangle()
        for parent_feat in ea_by_id.values():
            if parent_feat.geometry() and not parent_feat.geometry().isEmpty():
                combined_bbox.combineExtentWith(parent_feat.geometry().boundingBox())
                
        if bbox_transform and not combined_bbox.isEmpty():
            combined_bbox = bbox_transform.transformBoundingBox(combined_bbox)
            
        request = QgsFeatureRequest()
        if not combined_bbox.isEmpty():
            request.setFilterRect(combined_bbox)
            
        bldg_processed_count = 0
        bldg_matched_count = 0
        
        for idx, feat in enumerate(building_source.getFeatures(request)):
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
                
            if idx % 2000 == 0:
                yield_to_ui(idx, 100)
                multi_feedback.setProgressText(f"{_PHASE_LABELS[1]} [Processed {idx:,} building points]...")
                
            bldg_processed_count += 1
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                if transform:
                    geom_clone = QgsGeometry(geom)
                    geom_clone.transform(transform)
                    p = geom_clone.asPoint()
                else:
                    p = geom.asPoint()
                    
                pt_geom = QgsGeometry.fromPointXY(p)
                
                # Check spatial index intersection
                candidate_ids = ea_index.intersects(pt_geom.boundingBox())
                for parent_ea_id in candidate_ids:
                    parent_geom = ea_geometries[parent_ea_id]
                    if parent_geom.contains(pt_geom) or parent_geom.intersects(pt_geom):
                        pop_val = feat.attribute(bldg_hh_field)
                        if pop_val is None or (isinstance(pop_val, QVariant) and pop_val.isNull()) or str(pop_val).strip() == "":
                            pop_val = 1.0
                        else:
                            try:
                                pop_val = float(pop_val)
                                if pop_val <= 0.0:
                                    pop_val = 1.0
                            except (TypeError, ValueError):
                                pop_val = 1.0
                                
                        bldg_val = None
                        bldg_val_idx = feat.fields().indexOf("bldgpoints_value")
                        if bldg_val_idx == -1:
                            bldg_val_idx = feat.fields().indexOf("bldgpts_val")
                        if bldg_val_idx != -1:
                            b_val = feat.attribute(bldg_val_idx)
                            try:
                                bldg_val = float(b_val) if b_val is not None else None
                            except (TypeError, ValueError):
                                bldg_val = None
                                
                        ea_id_to_buildings.setdefault(parent_ea_id, []).append({
                            'point': p,
                            'pop': pop_val,
                            'bldgpoints_value': bldg_val,
                            'attributes': feat.attributes()
                        })
                        bldg_matched_count += 1
                        break
        
        feedback.pushInfo(f"Matched {bldg_matched_count} of {bldg_processed_count} building points.")
        multi_feedback.setProgress(100)  # Phase 4 complete

        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")

        

        multi_feedback.setProgress(100)  # Phase 2 complete

        if preview_only:
            if extracted_buildings_sink is not None:
                feedback.pushInfo("Writing matched building points to extracted buildings output layer...")
                bldg_out_fields = QgsFields(building_source.fields())
                if bldg_out_fields.indexOf("parent_ean") == -1:
                    bldg_out_fields.append(QgsField("parent_ean", QVariant.String))
                    
                bldgpts_idx = bldg_out_fields.indexOf("bldgpoints_value")
                if bldgpts_idx == -1:
                    bldgpts_idx = bldg_out_fields.indexOf("bldgpts_val")
                if bldgpts_idx == -1:
                    bldg_out_fields.append(QgsField("bldgpoints_value", QVariant.Double))
                    
                pop_out_idx = bldg_out_fields.indexOf("pop")
                if pop_out_idx == -1:
                    pop_out_idx = bldg_out_fields.indexOf(bldg_hh_field)
                if pop_out_idx == -1:
                    bldg_out_fields.append(QgsField("pop", QVariant.Double))
                    
                barangay_to_target = None
                if previous_ea_source.sourceCrs() != target_crs:
                    barangay_to_target = QgsCoordinateTransform(
                        previous_ea_source.sourceCrs(), target_crs, context.transformContext()
                    )
                    
                bldg_written_preview = 0
                for parent_ea_id, buildings in ea_id_to_buildings.items():
                    parent_feat = ea_by_id[parent_ea_id]
                    parent_ean_val = parent_feat.attribute(ea_id_field)
                    
                    for b in buildings:
                        b_feat = QgsFeature(bldg_out_fields)
                        b_geom = QgsGeometry.fromPointXY(b['point'])
                        if barangay_to_target:
                            b_geom.transform(barangay_to_target)
                        b_feat.setGeometry(b_geom)
                        
                        b_feat.setAttributes(b['attributes'])
                        attrs = b_feat.attributes()
                        needed = bldg_out_fields.count() - len(attrs)
                        if needed > 0:
                            attrs.extend([None] * needed)
                            b_feat.setAttributes(attrs)
                            
                        b_feat["parent_ean"] = str(parent_ean_val)
                        
                        if "pop" in [f.name() for f in bldg_out_fields]:
                            b_feat["pop"] = b['pop']
                        elif bldg_hh_field in [f.name() for f in bldg_out_fields]:
                            b_feat[bldg_hh_field] = b['pop']
                            
                        if "bldgpoints_value" in [f.name() for f in bldg_out_fields]:
                            b_feat["bldgpoints_value"] = b['bldgpoints_value']
                        elif "bldgpts_val" in [f.name() for f in bldg_out_fields]:
                            b_feat["bldgpts_val"] = b['bldgpoints_value']
                            
                        if extracted_buildings_sink.addFeature(b_feat, QgsFeatureSink.Flag.FastInsert):
                            bldg_written_preview += 1
                feedback.pushInfo(f"Successfully wrote {bldg_written_preview} building features to output in preview mode.")

            feedback.pushInfo("PREVIEW ONLY check is active — exiting early after creating candidate layers.")
            return outputs

        # ── Phase 3: Indexing Roads & Rivers ──────────────────────────────────────────────────────
        multi_feedback.setCurrentStep(2)
        multi_feedback.setProgressText(f"{_PHASE_LABELS[2]}...")
        feedback.pushInfo("Phase 3/8: Building spatial indexes (barangay, road, river, candidate EAs only)...")

        # Re-use candidate-only spatial index of starting EAs built in Phase 2
        feedback.pushInfo("Re-using candidate-only spatial index of starting EAs built in Phase 2...")
        ea_index = temp_ea_index
        ea_by_id = temp_ea_by_id

        # Build spatial indexes for optional road and river layers
        road_index = None
        road_geoms = {}
        if road_source is not None:
            feedback.pushInfo("Building spatial index of Road Layer...")
            road_index = QgsSpatialIndex()
            for idx, feat in enumerate(road_source.getFeatures()):
                if multi_feedback.isCanceled():
                    raise QgsProcessingException("Algorithm cancelled by user.")
                yield_to_ui(idx)
                road_index.insertFeature(feat)
                road_geoms[feat.id()] = feat.geometry()

        river_index = None
        river_geoms = {}
        if river_source is not None:
            feedback.pushInfo("Building spatial index of River Layer...")
            river_index = QgsSpatialIndex()
            for idx, feat in enumerate(river_source.getFeatures()):
                if multi_feedback.isCanceled():
                    raise QgsProcessingException("Algorithm cancelled by user.")
                yield_to_ui(idx)
                river_index.insertFeature(feat)
                river_geoms[feat.id()] = feat.geometry()

        multi_feedback.setProgress(100)  # Phase 3 complete

        # Helper to extract individual contiguous polygon parts from a QgsGeometry
        def get_polygons_from_geom(geom):
            polys = []
            if geom.isEmpty():
                return polys
            
            flat_type = QgsWkbTypes.flatType(geom.wkbType())
            
            if flat_type == QgsWkbTypes.Polygon:
                polys.append(geom)
            elif flat_type == QgsWkbTypes.MultiPolygon:
                for part in geom.constParts():
                    polys.append(QgsGeometry(part.clone()))
            elif flat_type == QgsWkbTypes.GeometryCollection or geom.isMultipart():
                try:
                    for part in geom.constParts():
                        part_geom = QgsGeometry(part.clone())
                        part_flat = QgsWkbTypes.flatType(part_geom.wkbType())
                        if part_flat == QgsWkbTypes.Polygon:
                            polys.append(part_geom)
                        elif part_flat == QgsWkbTypes.MultiPolygon:
                            for sub_part in part_geom.constParts():
                                polys.append(QgsGeometry(sub_part.clone()))
                        elif part_flat == QgsWkbTypes.GeometryCollection:
                            polys.extend(get_polygons_from_geom(part_geom))
                except Exception:
                    polys.append(geom)
            else:
                polys.append(geom)
                
            # Clean each polygon individually to prevent dissolving shared boundaries
            cleaned_polys = []
            for p in polys:
                cp = p.buffer(0.0, 3)
                if cp and not cp.isEmpty():
                    cleaned_polys.append(cp)
                else:
                    cleaned_polys.append(p)
            return cleaned_polys

        # Helper to allocate gaps/holes in the union of parts to their nearest parent part
        def allocate_gaps_to_parts(parts, parent_geom):
            if not parts:
                return parts
            
            # Compute union of parts
            parts_union = parts[0]['geom']
            for p in parts[1:]:
                parts_union = parts_union.combine(p['geom'])
                
            # Get gaps
            gaps = parent_geom.difference(parts_union).buffer(0.0, 3)
            if gaps.isEmpty():
                return parts
                
            # Extract individual polygons from gaps
            gap_polys = get_polygons_from_geom(gaps)
            for gap_poly in gap_polys:
                if gap_poly.isEmpty():
                    continue
                # Find the part that shares the longest boundary with this gap polygon
                best_part = None
                max_boundary_len = -1.0
                for p in parts:
                    shared = gap_poly.intersection(p['geom'])
                    if not shared.isEmpty():
                        boundary_len = shared.length()
                        if boundary_len > max_boundary_len:
                            max_boundary_len = boundary_len
                            best_part = p
                            
                # Fallback: assign to the nearest part by centroid distance
                if best_part is None:
                    gap_centroid = gap_poly.centroid().asPoint()
                    best_part = min(parts, key=lambda p: gap_centroid.distance(p['geom'].centroid().asPoint()))
                    
                # Combine gap polygon with the selected part
                combined = best_part['geom'].combine(gap_poly).buffer(0.0, 3)
                best_part['geom'] = combined
            return parts

        def collect_linear_features(ea_geom, index, geoms_dict):
            """Return road/river line geometries clipped strictly to the EA polygon boundary.

            The Previous EA Layer has higher priority than road/river layers: only the portions
            of road/river lines that lie *within* the EA polygon are returned. Segments extending
            beyond the EA boundary are discarded so they cannot influence splits or Voronoi
            snapping outside the EA shape.
            """
            if index is None or not geoms_dict:
                return []
            candidates = index.intersects(ea_geom.boundingBox())
            lines = []
            for fid in candidates:
                geom = geoms_dict.get(fid)
                if geom and not geom.isEmpty() and ea_geom.intersects(geom):
                    # Clip the line to the EA boundary — EA shape takes strict priority
                    clipped = geom.intersection(ea_geom)
                    if not clipped.isEmpty():
                        lines.append(clipped)
            return lines

        def merge_line_geometries(line_geoms):
            """Union a list of line geometries into a single geometry (or empty)."""
            if not line_geoms:
                return None
            merged = line_geoms[0]
            for lg in line_geoms[1:]:
                merged = merged.combine(lg)
            return merged

        # Pure Python weighted K-Means clustering algorithm
        def weighted_kmeans(points, weights, k_val, max_iters=30):
            n_pts = len(points)
            if n_pts <= k_val:
                return list(range(n_pts)), list(points)
                
            random.seed(42)
            total_w = sum(weights)
            # K-Means++ initialisation: seed the first centroid at the point nearest to the
            # weighted mean of all input points, then pick subsequent centroids with probability
            # proportional to squared distance from the nearest already-chosen centroid.
            # This replaces the previous "furthest from points[0]" seeding which was vulnerable
            # to outlier bias when a distant isolated building happened to be points[0].
            if total_w > 0:
                cx = sum(p[0] * w for p, w in zip(points, weights)) / total_w
                cy = sum(p[1] * w for p, w in zip(points, weights)) / total_w
                first_idx = min(range(n_pts),
                                key=lambda i: math.hypot(points[i][0] - cx, points[i][1] - cy))
                centroids = [points[first_idx]]
            else:
                centroids = [points[0]]

            for _ in range(1, k_val):
                sq_dists = []
                for pt in points:
                    min_d = min(math.hypot(pt[0] - c[0], pt[1] - c[1]) for c in centroids)
                    sq_dists.append(min_d * min_d)
                total_sq = sum(sq_dists)
                if total_sq == 0:
                    # All points coincide with existing centroids — pick any unused point
                    chosen = points[0]
                    for pt in points:
                        if pt not in centroids:
                            chosen = pt
                            break
                else:
                    r = random.random() * total_sq
                    cumulative = 0.0
                    chosen = points[-1]
                    for pt, sq_d in zip(points, sq_dists):
                        cumulative += sq_d
                        if cumulative >= r:
                            chosen = pt
                            break
                centroids.append(chosen)


            labels = [0] * n_pts
            for iter_idx in range(max_iters):
                # Assign step
                new_labels = []
                for pt in points:
                    min_dist = float('inf')
                    best_idx = 0
                    for i, c in enumerate(centroids):
                        d = math.hypot(pt[0] - c[0], pt[1] - c[1])
                        if d < min_dist:
                            min_dist = d
                            best_idx = i
                    new_labels.append(best_idx)
                    
                if new_labels == labels and iter_idx > 0:
                    break
                labels = new_labels
                
                # Update step
                sum_x = [0.0] * k_val
                sum_y = [0.0] * k_val
                sum_w = [0.0] * k_val
                for pt, w, l in zip(points, weights, labels):
                    sum_x[l] += pt[0] * w
                    sum_y[l] += pt[1] * w
                    sum_w[l] += w
                    
                centroids = []
                for i in range(k_val):
                    if sum_w[i] > 0:
                        centroids.append((sum_x[i] / sum_w[i], sum_y[i] / sum_w[i]))
                    else:
                        centroids.append(random.choice(points))
                        
            return labels, centroids

        # Pure K-Means + Voronoi split logic (extracted as helper)
        # Shared helper: merges any part below min_household into its best sibling until
        # all parts satisfy the minimum or only one remains (signalling a failed split).
        # Returns the cleaned list; callers must check len() >= 2 before accepting the split.
        def enforce_min_household(parts, fback, ea_geom=None):
            while len(parts) > 1:
                under = [i for i, p in enumerate(parts) if p['hh_count'] <= min_household]  # strictly above min_household required
                if not under:
                    break
                # Always fix the smallest part first
                under.sort(key=lambda i: parts[i]['hh_count'])
                up_idx = under[0]
                up = parts[up_idx]
                
                # Prefer the neighbour with the longest shared boundary
                best_idx = -1
                best_overlap = -1.0
                for j, nb in enumerate(parts):
                    if j == up_idx:
                        continue
                    # Rule: never merge into a delineation candidate
                    if is_delineation_candidate(nb):
                        continue
                    if up['geom'].intersects(nb['geom']) or up['geom'].touches(nb['geom']):
                        inter = up['geom'].intersection(nb['geom'])
                        overlap = inter.length() if not inter.isEmpty() else 0.0
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_idx = j
                
                # Fallback: nearest by centroid distance, preferring neighbours whose
                # combined count stays within max_household to avoid creating a new
                # over-threshold EA that would re-enter the split loop.
                if best_idx == -1:
                    up_centroid = up['geom'].centroid().asPoint()
                    best_dist = float('inf')
                    best_dist_over = float('inf')
                    best_idx_over = -1
                    for j, nb in enumerate(parts):
                        if j == up_idx:
                            continue
                        # Rule: never merge into a delineation candidate
                        if is_delineation_candidate(nb):
                            continue
                        dist = up_centroid.distance(nb['geom'].centroid().asPoint())
                        combined = up['hh_count'] + nb['hh_count']
                        if combined <= max_household:
                            if dist < best_dist:
                                best_dist = dist
                                best_idx = j
                        else:
                            if dist < best_dist_over:
                                best_dist_over = dist
                                best_idx_over = j
                    # Accept an over-threshold merge only as an absolute last resort
                    if best_idx == -1:
                        best_idx = best_idx_over

                if best_idx == -1:
                    break  # Only possible if parts has exactly 1 element, caught by while guard

                
                nb = parts[best_idx]
                raw_combined = nb['geom'].combine(up['geom']).buffer(0.0, 3)
                # Clip back to parent EA boundary if available, to strictly preserve EA shape.
                # buffer(0.0, 3) after intersection forces GEOS to resolve any GeometryCollection
                # (mixed points/lines/polygons) back into a clean Polygon/MultiPolygon.
                if ea_geom is not None:
                    clipped = raw_combined.intersection(ea_geom).buffer(0.0, 3)
                    nb['geom'] = clipped if not clipped.isEmpty() else raw_combined
                else:
                    nb['geom'] = raw_combined
                nb['buildings'].extend(up['buildings'])
                nb['hh_count'] += up['hh_count']
                nb['bldg_count'] = len(nb['buildings'])
                parts.pop(up_idx)
            return parts

        # Enforce sum(b['bldgpoints_value']) < hhdivthres for each individual part strictly within parent EA candidate boundaries
        def enforce_bldgpv_threshold(parts, hhdivthres, fback, ea_geom=None):
            while len(parts) > 1:
                # Find the part that has the highest sum of building bldgpoints_value
                parts_with_pv = []
                for idx, p in enumerate(parts):
                    pv = sum(b.get('bldgpoints_value', 0.0) for b in p['buildings'])
                    parts_with_pv.append((idx, pv))
                
                parts_with_pv.sort(key=lambda x: x[1], reverse=True)
                _max_bldgpv = parts_with_pv[0][1]
                
                # If even the maximum part is strictly less than hhdivthres, all parts comply.
                if _max_bldgpv < hhdivthres:
                    break
                    
                up_idx = parts_with_pv[0][0]
                up = parts[up_idx]
                
                # Merge this part with its best sibling (touching/centroid) strictly within the parent EA
                best_idx = -1
                best_overlap = -1.0
                for j, nb in enumerate(parts):
                    if j == up_idx:
                        continue
                    if up['geom'].intersects(nb['geom']) or up['geom'].touches(nb['geom']):
                        inter = up['geom'].intersection(nb['geom'])
                        overlap = inter.length() if not inter.isEmpty() else 0.0
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_idx = j
                            
                if best_idx == -1:
                    # Centroid fallback
                    up_centroid = up['geom'].centroid().asPoint()
                    best_dist = float('inf')
                    for j, nb in enumerate(parts):
                        if j == up_idx:
                            continue
                        dist = up_centroid.distance(nb['geom'].centroid().asPoint())
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = j
                            
                if best_idx == -1:
                    for j, nb in enumerate(parts):
                        if j != up_idx:
                            best_idx = j
                            break
                            
                if best_idx == -1:
                    break # Cannot merge further
                    
                # Combine up and best_idx parts
                nb = parts[best_idx]
                raw_combined = nb['geom'].combine(up['geom']).buffer(0.0, 3)
                if ea_geom is not None:
                    clipped = raw_combined.intersection(ea_geom).buffer(0.0, 3)
                    nb['geom'] = clipped if not clipped.isEmpty() else raw_combined
                else:
                    nb['geom'] = raw_combined
                    
                nb['buildings'].extend(up['buildings'])
                nb['hh_count'] += up['hh_count']
                nb['bldg_count'] = len(nb['buildings'])
                
                parts.pop(up_idx)
                
            return parts

        def split_ea_voronoi(ea_item, target_pop, fback, split_by='none'):
            if fback.isCanceled():
                return [ea_item]
            bldgs = ea_item.get('buildings', [])
            if not bldgs:
                fback.pushWarning(f"[EA {ea_item['original_code']}] DIAGNOSTIC: Split skipped — no building points matched to this EA.")
                return [ea_item]
                
            # Deduplicate building points by coordinates to prevent GEOS Voronoi failure on duplicate points
            coord_to_pt = {}
            for b in bldgs:
                pt = b['point']
                coord_to_pt[(pt.x(), pt.y())] = pt
            unique_pts = list(coord_to_pt.values())
            
            if len(unique_pts) < 2:
                fback.pushWarning(f"[EA {ea_item['original_code']}] DIAGNOSTIC: Split skipped — only {len(unique_pts)} unique building point(s). Need at least 2 unique locations to generate Voronoi.")
                ea_item['split_by'] = split_by
                return [ea_item]
                
            hh_cnt = sum(b['pop'] for b in bldgs)
            # Use max_household as the per-part target to produce the fewest equally-divided
            # parts that each stay within the 100–299 HH band. Recursive re-splitting handles
            # any parts that remain over max_household after the initial split.
            k_val = max(2, int(round(hh_cnt / float(max_household))))
            k_val = min(k_val, len(unique_pts))
            if k_val < 2:
                ea_item['split_by'] = split_by
                return [ea_item]
                
            # --- Outlier-robust K-Means pre-processing ---
            # Detect spatially isolated building locations that would skew K-Means centroids.
            # An outlier location is one whose nearest-neighbour distance (among all unique
            # building locations in this EA) exceeds OUTLIER_FACTOR × the median NN distance.
            # Outlier locations are excluded from K-Means input so the Voronoi boundary falls
            # along the natural gap between genuine sub-clusters rather than being pulled toward
            # isolated points.  Their associated buildings are still spatially assigned to the
            # correct Voronoi sub-part via the normal containment check after splitting.
            _OUTLIER_FACTOR = 3.0
            kmeans_pts = unique_pts  # default: use all unique locations

            if len(unique_pts) >= 6:
                _local_idx = QgsSpatialIndex()
                for _i_pt, _q_pt in enumerate(unique_pts):
                    _pf = QgsFeature(_i_pt)
                    _pf.setGeometry(QgsGeometry.fromPointXY(_q_pt))
                    _local_idx.insertFeature(_pf)

                _nn_dists = []
                for _i_pt, _q_pt in enumerate(unique_pts):
                    _neighbors = _local_idx.nearestNeighbor(_q_pt, 2)
                    _nn_d = float('inf')
                    for _n_id in _neighbors:
                        if _n_id != _i_pt:
                            _n_pt = unique_pts[_n_id]
                            _nn_d = math.hypot(_q_pt.x() - _n_pt.x(), _q_pt.y() - _n_pt.y())
                            break
                    _nn_dists.append(_nn_d)

                _sorted_d = sorted(d for d in _nn_dists if d < float('inf'))
                if _sorted_d:
                    _median_nn = _sorted_d[len(_sorted_d) // 2]
                    if _median_nn > 0:
                        _outlier_thr = _OUTLIER_FACTOR * _median_nn
                        _core = [q for q, d in zip(unique_pts, _nn_dists) if d <= _outlier_thr]
                        _n_outliers = sum(1 for d in _nn_dists if d > _outlier_thr)
                        if _n_outliers > 0 and len(_core) >= 2:
                            fback.pushInfo(
                                f"[EA {ea_item['original_code']}] Outlier filter: "
                                f"{_n_outliers} isolated building location(s) excluded from "
                                f"K-Means (NN dist > {_outlier_thr:.6f}, median={_median_nn:.6f}). "
                                f"Will be assigned via Voronoi containment after split."
                            )
                            kmeans_pts = _core

            # Re-clamp k_val to the (possibly reduced) point set
            k_val = min(k_val, len(kmeans_pts))
            if k_val < 2:
                # Not enough core points after outlier removal — revert to full set
                kmeans_pts = unique_pts
                k_val = min(max(2, int(round(hh_cnt / float(target_pop)))), len(unique_pts))
                if k_val < 2:
                    ea_item['split_by'] = split_by
                    return [ea_item]

            pts = [(pt.x(), pt.y()) for pt in kmeans_pts]
            pt_to_weight = {}
            for b in bldgs:
                pt_key = (b['point'].x(), b['point'].y())
                pt_to_weight[pt_key] = pt_to_weight.get(pt_key, 0.0) + b['pop']
            wts = [pt_to_weight.get((pt.x(), pt.y()), 1.0) for pt in kmeans_pts]

            # Cluster points
            labels, centroids = weighted_kmeans(pts, wts, k_val)

            
            # Construct Voronoi
            centroid_pts = [QgsPointXY(c[0], c[1]) for c in centroids]
            points_geom = QgsGeometry.fromMultiPointXY(centroid_pts)
            
            # Dynamic bounding box buffer based on CRS dimensions (geographic vs projected)
            bbox = ea_item['geom'].boundingBox()
            buffer_size = max(0.01, max(bbox.width(), bbox.height()) * 0.2)
            extent_geom = QgsGeometry.fromRect(bbox.buffered(buffer_size))
            
            voronoi_geom = points_geom.voronoiDiagram(extent_geom)
            if voronoi_geom.isEmpty():
                ea_item['split_by'] = split_by
                return [ea_item]
                
            cells = get_polygons_from_geom(voronoi_geom)
            if not cells:
                ea_item['split_by'] = split_by
                return [ea_item]
                
            # Densify and snap Voronoi cell boundaries to road/river lines if any are nearby
            road_lines = collect_linear_features(ea_item['geom'], road_index, road_geoms)
            river_lines = collect_linear_features(ea_item['geom'], river_index, river_geoms)
            all_lines = road_lines + river_lines
            if all_lines:
                from qgis.analysis import QgsGeometrySnapper
                # Build a spatial index for the clipped line segments inside the EA
                line_index = QgsSpatialIndex()
                line_map = {}
                for l_idx, line in enumerate(all_lines):
                    feat = QgsFeature(l_idx)
                    feat.setGeometry(line)
                    line_index.insertFeature(feat)
                    line_map[l_idx] = line
                    
                snapped_cells = []
                for cell_geom in cells:
                    # Query lines intersecting the cell bounding box buffered by tolerance
                    buffered_bbox = cell_geom.boundingBox().buffered(snap_tolerance)
                    candidate_line_ids = line_index.intersects(buffered_bbox)
                    
                    if not candidate_line_ids:
                        snapped_cells.append(cell_geom)
                        continue
                        
                    # Filter lines that are close to the cell
                    nearby_lines = [line_map[lid] for lid in candidate_line_ids]
                    
                    densified_cell = cell_geom.densifyByDistance(densify_dist)
                    snapped_cell = QgsGeometrySnapper.snapGeometry(
                        densified_cell,
                        snap_tolerance,
                        nearby_lines,
                        QgsGeometrySnapper.PreferClosest
                    )
                    clean_snapped_cell = snapped_cell.buffer(0.0, 3)
                    if clean_snapped_cell and not clean_snapped_cell.isEmpty():
                        snapped_cells.append(clean_snapped_cell)
                    else:
                        snapped_cells.append(cell_geom)
                cells = snapped_cells
                
            # Uses the automatically chosen area_threshold configured from parameters
            split_parts = []
            sliver_filtered_bldgs = 0  # Track buildings lost to sliver filtering
            for cell_geom in cells:
                intersected = ea_item['geom'].intersection(cell_geom)
                if not intersected.isEmpty():
                    polys = get_polygons_from_geom(intersected)
                    for poly in polys:
                        buildings_in_poly = []
                        for b in bldgs:
                            pt_geom = QgsGeometry.fromPointXY(b['point'])
                            if poly.contains(pt_geom) or poly.intersects(pt_geom):
                                buildings_in_poly.append(b)
                        sub_pop = sum(b['pop'] for b in buildings_in_poly)
                        split_parts.append({
                            'geom': poly,
                            'buildings': buildings_in_poly,
                            'hh_count': sub_pop,
                            'original_hhcount': ea_item.get('original_hhcount', 0),
                            'bldg_count': len(buildings_in_poly),
                            'bldgpoints_value': sub_pop / len(buildings_in_poly) if len(buildings_in_poly) > 0 else 0.0,
                            'attributes': list(ea_item['attributes']),
                            'original_id': ea_item['original_id'],
                            'original_code': ea_item['original_code'],
                            'is_new': True,
                            'from_split': True,
                            'split_by': split_by,
                            'parent_barangay': ea_item['parent_barangay']
                        })
                elif not intersected.isEmpty():
                    # Cell was rejected by area_threshold — check if it contained buildings
                    for b in bldgs:
                        pt_geom = QgsGeometry.fromPointXY(b['point'])
                        if intersected.contains(pt_geom) or intersected.intersects(pt_geom):
                            sliver_filtered_bldgs += 1
            
            if sliver_filtered_bldgs > 0:
                fback.pushWarning(
                    f"[EA {ea_item['original_code']}] DIAGNOSTIC: Sliver threshold ({area_threshold:.2e}) caused {sliver_filtered_bldgs} building(s) "
                    f"to be discarded in filtered-out cells. These buildings will be reassigned to surviving neighbours but may cause "
                    f"a surviving part to exceed max_household ({max_household}). Consider lowering the sliver threshold."
                )
                        
            # Clean up 0-household parts to ensure no resulting layer has 0 hh_count
            zero_parts = [p for p in split_parts if p['hh_count'] == 0]
            nonzero_parts = [p for p in split_parts if p['hh_count'] > 0]
            
            if not nonzero_parts:
                ea_item['split_by'] = split_by
                return [ea_item]
                
            progress = True
            while zero_parts and progress:
                progress = False
                remaining_zero = []
                for zp in zero_parts:
                    best_neighbor = None
                    best_overlap = -1.0
                    for np in nonzero_parts:
                        if zp['geom'].intersects(np['geom']) or zp['geom'].touches(np['geom']):
                            inter = zp['geom'].intersection(np['geom'])
                            overlap = inter.length() if not inter.isEmpty() else 0.0
                            if overlap > best_overlap:
                                best_overlap = overlap
                                best_neighbor = np
                    if best_neighbor is not None:
                        # Clip combined geometry back to parent EA boundary to maintain strict containment.
                        # buffer(0.0, 3) resolves any GeometryCollection from intersection() → clean polygon.
                        raw_combined = best_neighbor['geom'].combine(zp['geom']).buffer(0.0, 3)
                        clipped = raw_combined.intersection(ea_item['geom']).buffer(0.0, 3)
                        best_neighbor['geom'] = clipped if not clipped.isEmpty() else raw_combined
                        best_neighbor['buildings'].extend(zp['buildings'])
                        best_neighbor['bldg_count'] = len(best_neighbor['buildings'])
                        progress = True
                    else:
                        remaining_zero.append(zp)
                zero_parts = remaining_zero
                
            for zp in zero_parts:
                zp_centroid = zp['geom'].centroid().asPoint()
                best_neighbor = min(
                    nonzero_parts,
                    key=lambda np: zp_centroid.distance(np['geom'].centroid().asPoint())
                )
                # Clip combined geometry back to parent EA boundary to maintain strict containment.
                # buffer(0.0, 3) resolves any GeometryCollection from intersection() → clean polygon.
                raw_combined = best_neighbor['geom'].combine(zp['geom']).buffer(0.0, 3)
                clipped = raw_combined.intersection(ea_item['geom']).buffer(0.0, 3)
                best_neighbor['geom'] = clipped if not clipped.isEmpty() else raw_combined
                best_neighbor['buildings'].extend(zp['buildings'])
                best_neighbor['bldg_count'] = len(best_neighbor['buildings'])
                
            split_parts = nonzero_parts
            
            # Guarantee all parts meet min_household — merge violators into their best neighbour.
            # If this collapses everything to 1 part the split is treated as failed.
            split_parts = enforce_min_household(split_parts, fback, ea_geom=ea_item['geom'])
                        
            if len(split_parts) < 2:
                ea_item['split_by'] = split_by
                return [ea_item]
                
            orig_code_str = str(ea_item['original_code']).strip() if ea_item['original_code'] is not None else "000"
            digits = "".join([c for c in orig_code_str if c.isdigit()])
            orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)
            
            if orig_first3 != "000" and len(split_parts) > 0:
                split_parts.sort(key=lambda x: x['hh_count'], reverse=True)
                split_parts[0]['is_new'] = False

            parent_geom = ea_item['geom']
            for p in split_parts:
                clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
                if not clipped.isEmpty():
                    p['geom'] = clipped
            # Allocate gaps/holes to ensure strict partition with no holes/gaps
            split_parts = allocate_gaps_to_parts(split_parts, parent_geom)
            return split_parts

        # Spatial splitting of over-populated EAs using Building Point-Based Delineation (First Preference)
        # or K-Means/Voronoi and Forced Geometric fallbacks.
        def split_ea(ea_item, target_pop, fback):
            if fback.isCanceled():
                return [ea_item]
            bldgs = ea_item.get('buildings', [])
            if not bldgs:
                return [ea_item]
            road_lines = collect_linear_features(ea_item['geom'], road_index, road_geoms)
            river_lines = collect_linear_features(ea_item['geom'], river_index, river_geoms)
            all_lines = road_lines + river_lines
            line_geom = merge_line_geometries(all_lines)
            
            # Retrieve or compute hhdivthres for this EA
            _ea_ean = str(ea_item.get('original_code', '')).strip()
            _ea_id = ea_item.get('original_id')
            hhdivthres = delineation_candidate_hhdivthres.get(_ea_id)
            if hhdivthres is None:
                hhdivthres = max_household / ea_item['hh_count'] if ea_item['hh_count'] > 0.0 else 1.0
                
            # ── 1. First Preference: Building Point-Based Delineation ───────────────────
            # Process building points sequentially in their original sequence/layer order
            unassigned = list(bldgs)
            groups = []
            
            # Map index to building and insert into index
            unassigned_index = QgsSpatialIndex()
            bldg_id_map = {}
            for idx, b in enumerate(bldgs):
                feat = QgsFeature(idx)
                feat.setGeometry(QgsGeometry.fromPointXY(b['point']))
                unassigned_index.insertFeature(feat)
                bldg_id_map[idx] = b
                b['spatial_index_id'] = idx

            def remove_from_unassigned(bldg):
                unassigned.remove(bldg)
                feat = QgsFeature(bldg['spatial_index_id'])
                feat.setGeometry(QgsGeometry.fromPointXY(bldg['point']))
                unassigned_index.deleteFeature(feat)
                
            while unassigned:
                # Start a new group with the first unassigned point
                seed = unassigned[0]
                remove_from_unassigned(seed)
                
                current_group = [seed]
                running_total = seed.get('bldgpoints_value', 0.0)
                
                while True:
                    # Find the nearest unassigned building point to any point in the current group
                    best_bldg = None
                    best_group_pt = None
                    min_dist = float('inf')
                    
                    for g_bldg in current_group:
                        g_pt = QgsPointXY(g_bldg['point'].x(), g_bldg['point'].y())
                        nearest_ids = unassigned_index.nearestNeighbor(g_pt, 1)
                        if nearest_ids:
                            n_id = nearest_ids[0]
                            n_b = bldg_id_map[n_id]
                            n_pt = QgsPointXY(n_b['point'].x(), n_b['point'].y())
                            dist = g_pt.distance(n_pt)
                            if dist < min_dist:
                                min_dist = dist
                                best_bldg = n_b
                                best_group_pt = g_pt
                                
                    if best_bldg is None:
                        break
                        
                    # Rule 2: Physical Barrier Rule
                    is_separated = False
                    if line_geom and not line_geom.isEmpty():
                        b_pt = QgsPointXY(best_bldg['point'].x(), best_bldg['point'].y())
                        segment_geom = QgsGeometry.fromPolylineXY([best_group_pt, b_pt])
                        if segment_geom.intersects(line_geom):
                            is_separated = True
                            
                    if is_separated:
                        break # Barrier crossing, finalize group
                        
                    # Rule 3: Household Threshold Rule
                    next_val = best_bldg.get('bldgpoints_value', 0.0)
                    if running_total + next_val >= hhdivthres:
                        break # Exceeds or meets threshold, finalize group
                        
                    # Add to group
                    current_group.append(best_bldg)
                    remove_from_unassigned(best_bldg)
                    running_total += next_val
                    
                groups.append(current_group)
                
            # Convert groups to polygons using snapped Voronoi diagrams
            pt_to_coords = {}
            for b in bldgs:
                pt_to_coords[(b['point'].x(), b['point'].y())] = b['point']
            unique_pts = list(pt_to_coords.values())
            
            point_based_parts = []
            if len(groups) >= 2 and len(unique_pts) >= 2:
                # Construct Voronoi
                centroid_pts = [QgsPointXY(pt.x(), pt.y()) for pt in unique_pts]
                points_geom = QgsGeometry.fromMultiPointXY(centroid_pts)
                
                bbox = ea_item['geom'].boundingBox()
                buffer_size = max(0.01, max(bbox.width(), bbox.height()) * 0.2)
                extent_geom = QgsGeometry.fromRect(bbox.buffered(buffer_size))
                
                voronoi_geom = points_geom.voronoiDiagram(extent_geom)
                if not voronoi_geom.isEmpty():
                    cells = get_polygons_from_geom(voronoi_geom)
                    if cells:
                        # Densify and snap Voronoi cells to road/river barriers
                        if all_lines:
                            from qgis.analysis import QgsGeometrySnapper
                            # Build a spatial index for the clipped line segments inside the EA
                            line_index = QgsSpatialIndex()
                            line_map = {}
                            for l_idx, line in enumerate(all_lines):
                                feat = QgsFeature(l_idx)
                                feat.setGeometry(line)
                                line_index.insertFeature(feat)
                                line_map[l_idx] = line
                                
                            snapped_cells = []
                            for cell_geom in cells:
                                # Query lines intersecting the cell bounding box buffered by tolerance
                                buffered_bbox = cell_geom.boundingBox().buffered(snap_tolerance)
                                candidate_line_ids = line_index.intersects(buffered_bbox)
                                
                                if not candidate_line_ids:
                                    snapped_cells.append(cell_geom)
                                    continue
                                    
                                # Filter lines that are close to the cell
                                nearby_lines = [line_map[lid] for lid in candidate_line_ids]
                                
                                densified_cell = cell_geom.densifyByDistance(densify_dist)
                                snapped_cell = QgsGeometrySnapper.snapGeometry(
                                    densified_cell,
                                    snap_tolerance,
                                    nearby_lines,
                                    QgsGeometrySnapper.PreferClosest
                                )
                                clean_snapped_cell = snapped_cell.buffer(0.0, 3)
                                if clean_snapped_cell and not clean_snapped_cell.isEmpty():
                                    snapped_cells.append(clean_snapped_cell)
                                else:
                                    snapped_cells.append(cell_geom)
                            cells = snapped_cells
                            
                        # Map unique coords to cells
                        pt_to_cell = {}
                        for cell_geom in cells:
                            for pt in unique_pts:
                                pt_geom = QgsGeometry.fromPointXY(pt)
                                if cell_geom.contains(pt_geom) or cell_geom.intersects(pt_geom):
                                    pt_to_cell[(pt.x(), pt.y())] = cell_geom
                                    
                        # Create split parts
                        raw_parts = []
                        for g_idx, group in enumerate(groups):
                            group_cells = []
                            group_unique_coords = set()
                            for b in group:
                                coord = (b['point'].x(), b['point'].y())
                                if coord not in group_unique_coords:
                                    group_unique_coords.add(coord)
                                    cell = pt_to_cell.get(coord)
                                    if cell:
                                        group_cells.append(cell)
                                        
                            if not group_cells:
                                continue
                                
                            combined_geom = group_cells[0]
                            for cell in group_cells[1:]:
                                combined_geom = combined_geom.combine(cell)
                                
                            combined_geom = combined_geom.buffer(0.0, 3)
                            intersected = ea_item['geom'].intersection(combined_geom)
                            if not intersected.isEmpty():
                                polys = get_polygons_from_geom(intersected)
                                for poly in polys:
                                    buildings_in_poly = []
                                    for b in group:
                                        pt_geom = QgsGeometry.fromPointXY(b['point'])
                                        if poly.contains(pt_geom) or poly.intersects(pt_geom):
                                            buildings_in_poly.append(b)
                                            
                                    sub_pop = sum(b['pop'] for b in buildings_in_poly)
                                    split_by = 'point_based'
                                    if road_lines:
                                        split_by = 'road'
                                    if river_lines:
                                        split_by = 'river' if split_by == 'road' else split_by + '+river'
                                        
                                    raw_parts.append({
                                        'geom': poly,
                                        'buildings': buildings_in_poly,
                                        'hh_count': sub_pop,
                                        'original_hhcount': ea_item.get('original_hhcount', 0),
                                        'bldg_count': len(buildings_in_poly),
                                        'bldgpoints_value': sub_pop / len(buildings_in_poly) if len(buildings_in_poly) > 0 else 0.0,
                                        'attributes': list(ea_item['attributes']),
                                        'original_id': ea_item['original_id'],
                                        'original_code': ea_item['original_code'],
                                        'is_new': True,
                                        'from_split': True,
                                        'split_by': split_by,
                                        'parent_barangay': ea_item['parent_barangay']
                                    })
                                    
                        # Enforce min household (merging floor violators)
                        if len(raw_parts) >= 2:
                            point_based_parts = enforce_min_household(raw_parts, fback, ea_geom=ea_item['geom'])
                            
            if len(point_based_parts) >= 2:
                fback.pushInfo(f"[EA {ea_item['original_code']}] Point-based sequential split accepted: {len(point_based_parts)} parts created.")
                
                # Sort and keep parent code on largest
                orig_code_str = str(ea_item['original_code']).strip() if ea_item['original_code'] is not None else "000"
                digits = "".join([c for c in orig_code_str if c.isdigit()])
                orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)
                if orig_first3 != "000":
                    point_based_parts.sort(key=lambda x: x['hh_count'], reverse=True)
                    point_based_parts[0]['is_new'] = False
                    
                # Clip to parent boundary
                parent_geom = ea_item['geom']
                for p in point_based_parts:
                    clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
                    if not clipped.isEmpty():
                        p['geom'] = clipped
                # Allocate gaps/holes to ensure strict partition with no holes/gaps
                point_based_parts = allocate_gaps_to_parts(point_based_parts, parent_geom)
                return point_based_parts
                
            # ── 2. Fallbacks ──────────────────────────────────────────────────────────
            fback.pushInfo(f"[EA {ea_item['original_code']}] Point-based sequential split could not partition EA. Falling back to K-Means + Voronoi...")
            
            # Fallback 1: K-Means + Voronoi
            split_parts = split_ea_voronoi(ea_item, target_pop, fback, split_by='none')
            
            # Fallback 2: Forced Geometric strip split
            if len(split_parts) < 2:
                fback.pushInfo(f"[EA {ea_item['original_code']}] K-Means + Voronoi failed. Falling back to Forced Geometric split...")
                split_parts = force_geometric_split(ea_item, target_pop, fback)
                
            # Enforce total bldgpoints_value <= hhdivthres strictly within the parent EA area
            if len(split_parts) >= 2:
                split_parts = enforce_bldgpv_threshold(split_parts, hhdivthres, fback, ea_geom=ea_item['geom'])
                
            # Final guaranteed clip: ensure every part's geometry is strictly within the parent EA boundary
            parent_geom = ea_item['geom']
            for p in split_parts:
                clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
                if not clipped.isEmpty():
                    p['geom'] = clipped
                    
            return split_parts


        # Last-resort geometric strip split for EAs that resist Voronoi/K-Means splitting.
        # Divides the EA polygon into N equal-width strips (horizontal or vertical),
        # clips each against the parent EA, assigns buildings, and returns the parts.
        # This never gives up due to building point density or distribution issues.
        def force_geometric_split(ea_item, target_pop, fback):
            hh_cnt = ea_item['hh_count']
            bldgs = ea_item.get('buildings', [])
            
            bbox = ea_item['geom'].boundingBox()
            
            def make_strips(n, horizontal):
                """Return clipped polygon parts from n equal strips along the chosen axis."""
                strips = []
                for i in range(n):
                    if horizontal:
                        span = bbox.height() / n
                        y0 = bbox.yMinimum() + i * span
                        y1 = bbox.yMinimum() + (i + 1) * span
                        pts = [
                            QgsPointXY(bbox.xMinimum(), y0),
                            QgsPointXY(bbox.xMaximum(), y0),
                            QgsPointXY(bbox.xMaximum(), y1),
                            QgsPointXY(bbox.xMinimum(), y1),
                            QgsPointXY(bbox.xMinimum(), y0),
                        ]
                    else:
                        span = bbox.width() / n
                        x0 = bbox.xMinimum() + i * span
                        x1 = bbox.xMinimum() + (i + 1) * span
                        pts = [
                            QgsPointXY(x0, bbox.yMinimum()),
                            QgsPointXY(x1, bbox.yMinimum()),
                            QgsPointXY(x1, bbox.yMaximum()),
                            QgsPointXY(x0, bbox.yMaximum()),
                            QgsPointXY(x0, bbox.yMinimum()),
                        ]
                    strip_geom = QgsGeometry.fromPolygonXY([pts])
                    intersected = ea_item['geom'].intersection(strip_geom)
                    if not intersected.isEmpty():
                        strips.extend(get_polygons_from_geom(intersected))
                return strips
            
            # Prefer the orientation that cuts across the longer axis
            use_horizontal = bbox.height() >= bbox.width()
            
            # Start k at ceil(hh_cnt / target_pop) for balanced strips.
            # Retry with increasing k (up to ceil(hh_cnt / min_household)) when
            # enforce_min_household collapses parts back to 1 due to uneven distribution.
            k_start = max(2, math.ceil(hh_cnt / float(target_pop)))
            k_max   = k_start + 4
            
            accepted_parts = None
            accepted_k     = None
            accepted_orientation = use_horizontal
            
            for k_val in range(k_start, k_max + 1):
                strip_polys = make_strips(k_val, horizontal=use_horizontal)
                orientation = 'horizontal'
                if len(strip_polys) < 2:
                    strip_polys = make_strips(k_val, horizontal=not use_horizontal)
                    orientation = 'vertical'
                
                if len(strip_polys) < 2:
                    break  # Geometry cannot be further subdivided
                
                # Assign buildings to each strip
                parts = []
                for poly in strip_polys:
                    buildings_in_poly = []
                    for b in bldgs:
                        pt_geom = QgsGeometry.fromPointXY(b['point'])
                        if poly.contains(pt_geom) or poly.intersects(pt_geom):
                            buildings_in_poly.append(b)
                    sub_pop = sum(b['pop'] for b in buildings_in_poly)
                    parts.append({
                        'geom': poly,
                        'buildings': buildings_in_poly,
                        'hh_count': sub_pop,
                        'original_hhcount': ea_item.get('original_hhcount', 0),
                        'bldg_count': len(buildings_in_poly),
                        'bldgpoints_value': sub_pop / len(buildings_in_poly) if len(buildings_in_poly) > 0 else 0.0,
                        'attributes': list(ea_item['attributes']),
                        'original_id': ea_item['original_id'],
                        'original_code': ea_item['original_code'],
                        'is_new': True,
                        'from_split': True,
                        'split_by': 'forced_grid',
                        'parent_barangay': ea_item['parent_barangay']
                    })
                
                # Merge zero-household strips into their nearest populated neighbour
                zero_parts    = [p for p in parts if p['hh_count'] == 0]
                nonzero_parts = [p for p in parts if p['hh_count'] > 0]
                
                if not nonzero_parts:
                    continue  # All strips empty — try next k
                
                for zp in zero_parts:
                    zp_centroid = zp['geom'].centroid().asPoint()
                    best_nb = min(
                        nonzero_parts,
                        key=lambda np: zp_centroid.distance(np['geom'].centroid().asPoint())
                    )
                    # Clip combined geometry back to parent EA boundary to maintain strict containment
                    raw_combined = best_nb['geom'].combine(zp['geom']).buffer(0.0, 3)
                    clipped = raw_combined.intersection(ea_item['geom'])
                    best_nb['geom'] = clipped if not clipped.isEmpty() else raw_combined
                    best_nb['buildings'].extend(zp['buildings'])
                    best_nb['bldg_count'] = len(best_nb['buildings'])
                
                parts = enforce_min_household(nonzero_parts, fback, ea_geom=ea_item['geom'])
                
                if len(parts) < 2:
                    # enforce_min_household collapsed to 1 part — try more strips
                    continue
                
                # We have >= 2 parts. Check whether all are within [min, max].
                all_valid = all(p['hh_count'] <= max_household for p in parts)
                
                # Accept this k as the best result so far (prefer the first valid split)
                if accepted_parts is None or all_valid:
                    accepted_parts      = parts
                    accepted_k          = k_val
                    accepted_orientation = orientation
                
                if all_valid:
                    break  # Perfect: every part is within threshold, stop here
                # Otherwise keep trying a larger k to see if we can eliminate over-threshold parts
            
            if accepted_parts is None:
                fback.pushWarning(
                    f"[EA {ea_item['original_code']}] FORCED SPLIT: Could not produce >= 2 valid "
                    f"parts at any k ({k_start}–{k_max}). EA will remain over threshold."
                )
                return [ea_item]
            
            # Recursively re-split any sub-part that is still over max_household.
            # This handles the case where enforce_min_household merged a small strip
            # into a large one, pushing the large one above the max.
            final_parts = []
            for part in accepted_parts:
                if part['hh_count'] > max_household:
                    # Rule: EAs produced by a merge must never be delineated
                    if part.get('from_merge', False):
                        final_parts.append(part)
                        continue
                    sub_result = force_geometric_split(part, target_pop, fback)
                    if len(sub_result) > 1:
                        final_parts.extend(sub_result)
                    else:
                        final_parts.append(part)  # Cannot split further; compliance sweep will retry
                else:
                    final_parts.append(part)
            
            # Preserve original code on the most-populated part
            orig_code_str = str(ea_item['original_code']).strip() if ea_item['original_code'] is not None else "000"
            digits = "".join([c for c in orig_code_str if c.isdigit()])
            orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)
            if orig_first3 != "000" and len(final_parts) > 0:
                final_parts.sort(key=lambda x: x['hh_count'], reverse=True)
                final_parts[0]['is_new'] = False
                
            # Allocate gaps/holes to ensure strict partition with no holes/gaps
            final_parts = allocate_gaps_to_parts(final_parts, ea_item['geom'])

            # Final guaranteed clip: ensure every geometric strip part strictly follows
            # the shape of the parent EA polygon before returning.
            # buffer(0.0, 3) after intersection() resolves GeometryCollection → clean Polygon/MultiPolygon.
            parent_geom = ea_item['geom']
            for p in final_parts:
                clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
                if not clipped.isEmpty():
                    p['geom'] = clipped
            
            fback.pushWarning(
                f"[EA {ea_item['original_code']}] FORCED SPLIT: Applied {accepted_orientation} "
                f"strip split (k={accepted_k}) — EA (hh_count={hh_cnt}) → {len(final_parts)} part(s)."
            )
            return final_parts

        # ── Phase 4: Load previous EAs into memory ──────────────────────────────────────────────────
        multi_feedback.setCurrentStep(3)
        multi_feedback.setProgressText(f"{_PHASE_LABELS[3]} [0/{previous_ea_count:,}]...")
        # Load starting EAs directly from Previous EA layer
        feedback.pushInfo("Phase 4/8: Loading previous EAs into memory (caching only, no sink writing)...")
        
        # Find index of hhcount/household field in Previous EA Layer
        prev_ea_pop_idx = previous_ea_source.fields().indexOf(household_field)

        # Collect active EAs that are candidates or contiguous partners of merge candidates/0-pop EAs
        needed_ea_ids = set()
        active_barangays = set()
        
        # Build spatial index to find contiguous neighbors of merge candidates
        temp_index = QgsSpatialIndex()
        ea_by_id = {}
        for feat in all_ea_features:
            temp_index.insertFeature(feat)
            ea_by_id[feat.id()] = feat
            
        for feat in all_ea_features:
            _ean = feat.attribute(ea_id_field)
            _ean_str = str(_ean).strip() if _ean is not None else ""
            
            _orig_hhcount = 0.0
            if prev_ea_pop_idx != -1:
                val = feat.attribute(prev_ea_pop_idx)
                try:
                    _orig_hhcount = float(val) if val is not None else 0.0
                except (TypeError, ValueError):
                    _orig_hhcount = 0.0
                    
            is_delineation = feat.id() in delineation_candidate_ids
            is_merge = feat.id() in merge_candidate_ids or _orig_hhcount == 0.0
            
            if is_delineation:
                needed_ea_ids.add(feat.id())
                bar_geo = resolve_ea_parent_barangay(feat)
                if bar_geo:
                    active_barangays.add(bar_geo)
            elif is_merge:
                needed_ea_ids.add(feat.id())
                bar_geo = resolve_ea_parent_barangay(feat)
                if bar_geo:
                    active_barangays.add(bar_geo)
                # Find touch-neighbors in same barangay
                geom = feat.geometry()
                if geom and not geom.isEmpty():
                    candidates = temp_index.intersects(geom.boundingBox())
                    for cid in candidates:
                        if cid == feat.id():
                            continue
                        nb_feat = ea_by_id[cid]
                        if resolve_ea_parent_barangay(nb_feat) == bar_geo:
                            if geom.touches(nb_feat.geometry()) or geom.intersects(nb_feat.geometry()):
                                needed_ea_ids.add(cid)
                                
        feedback.pushInfo(f"Found {len(active_barangays)} active barangay(s) containing candidates.")
        feedback.pushInfo(f"Bypassing non-candidate/non-partner EAs. Loading only {len(needed_ea_ids)} EA(s) for processing.")

        eas = []
        _ea_load_count = 0
        _ea_load_last_pct = -1
        for feat in all_ea_features:
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            _ea_load_count += 1
            yield_to_ui(_ea_load_count, 100)
            if previous_ea_count > 0:
                _ea_pct = int(_ea_load_count / previous_ea_count * 100)
                if _ea_pct != _ea_load_last_pct:
                    multi_feedback.setProgress(_ea_pct)
                    multi_feedback.setProgressText(
                        f"{_PHASE_LABELS[3]} [{_ea_load_count:,}/{previous_ea_count:,}]..."
                    )
                    _ea_load_last_pct = _ea_pct
            
            if feat.id() not in needed_ea_ids:
                continue

            clean_geom = QgsGeometry(feat.geometry())
            assigned_bldgs = ea_id_to_buildings.get(feat.id(), [])
            _orig_hhcount = 0.0
            if prev_ea_pop_idx != -1:
                val = feat.attribute(prev_ea_pop_idx)
                try:
                    _orig_hhcount = float(val) if val is not None else 0.0
                except (TypeError, ValueError):
                    _orig_hhcount = 0.0
            else:
                _orig_hhcount = 0.0

            # Bypassing building matches for non-candidates EAs
            _ean = feat.attribute(ea_id_field)
            _ean_str = str(_ean).strip() if _ean is not None else ""
            is_candidate = (feat.id() in delineation_candidate_ids or feat.id() in merge_candidate_ids)

            if not is_candidate:
                _ea_hh_count = _orig_hhcount
            else:
                _ea_hh_count = sum(b['pop'] for b in assigned_bldgs)

            _bldg_pt_count = len(assigned_bldgs)
            _bldgpoints_value = _ea_hh_count / _bldg_pt_count if _bldg_pt_count > 0 else 0.0
            _total_bldg_val = sum(b.get('bldgpoints_value') if b.get('bldgpoints_value') is not None else b['pop'] for b in assigned_bldgs)
            for b in assigned_bldgs:
                val = b.get('bldgpoints_value')
                if val is None:
                    val = b['pop']
                b['bldgpoints_value'] = val / _total_bldg_val if _total_bldg_val > 0.0 else 0.0

            eas.append({
                'geom': clean_geom,
                'buildings': assigned_bldgs,
                'hh_count': _ea_hh_count,
                'original_hhcount': _orig_hhcount,
                'bldg_count': _bldg_pt_count,
                'bldgpoints_value': _bldgpoints_value,
                'attributes': feat.attributes(),
                'original_id': feat.id(),
                'original_code': feat.attribute(ea_id_field),
                'is_new': False,
                'split_by': 'none',
                'parent_barangay': bar_geo
            })

        # Calculate max original EA sequence number per parent barangay
        max_ea_number = {}
        for ea in eas:
            bar_geo = ea['parent_barangay']
            
            orig_code_str = str(ea['original_code']).strip() if ea['original_code'] is not None else "000"
            digits = "".join([c for c in orig_code_str if c.isdigit()])
            orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)
            
            if orig_first3.isdigit() and orig_first3 != "000":
                val = int(orig_first3)
                max_ea_number[bar_geo] = max(max_ea_number.get(bar_geo, 0), val)
            else:
                max_ea_number.setdefault(bar_geo, 0)

        # Update initial in-memory attributes for the Previous EA Layer to match building points
        for pop_fname in [household_field, "hhcount", "population", "household"]:
            pop_idx = previous_ea_source.fields().indexOf(pop_fname)
            if pop_idx != -1:
                for ea in eas:
                    ea['attributes'][pop_idx] = ea['hh_count']
        multi_feedback.setProgress(100)  # Phase 5 complete

        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")

        # Classification helpers
        # Always use the building-point-derived hh_count for split/merge decisions.
        # Using the old census original_hhcount would miss EAs that have grown above
        # max_household since the previous census round, leaving them over-threshold
        # in the output even though the building points clearly exceed the maximum.
        def get_classification_count(ea_item):
            return ea_item['hh_count']

        def is_delineation_candidate(ea_item):
            if ea_item.get('from_split', False) or ea_item.get('from_merge', False):
                return False
            return ea_item.get('original_id') in delineation_candidate_ids and ea_item['hh_count'] >= max_household

        def is_merge_candidate(ea_item):
            if ea_item.get('from_split', False):
                return ea_item['hh_count'] <= min_household
            if ea_item.get('from_merge', False):
                return False
            return (ea_item.get('original_id') in merge_candidate_ids) or (ea_item.get('original_id') in delineation_candidate_ids and ea_item['hh_count'] <= min_household)

        # Helper function to run the iterative splitting loop on a single Barangay's EAs
        def process_barangay_split(bar_code, bar_eas, fback):
            iteration = 0
            max_iterations = 5
            changed = True
            
            while changed and iteration < max_iterations:
                if fback.isCanceled():
                    break
                
                # Check split threshold compliance (any over-threshold candidate that needs split?)
                has_overs = False
                for ea in bar_eas:
                    if is_delineation_candidate(ea):
                        has_overs = True
                        break
                        
                if not has_overs:
                    break
                    
                # Classify EAs (find overs)
                overs = []
                for idx, ea in enumerate(bar_eas):
                    if is_delineation_candidate(ea):
                        overs.append(idx)
                        
                changed = False
                
                # Case A: Splitting
                if overs:
                    new_eas = []
                    for idx in range(len(bar_eas)):
                        if idx in overs:
                            ea = bar_eas[idx]
                            # Rule: EAs produced by a merge must never be delineated
                            if ea.get('from_merge', False):
                                new_eas.append(ea)
                            else:
                                split_parts = split_ea(ea, max_household, fback)
                                if len(split_parts) > 1:
                                    # ── bldgpoints_value validation ──────────────────────────────
                                    # Each part's bldgpoints_value must be < parent's hhdivthres
                                    # (max_household / parent_hhcount from Delineation Candidate Index).
                                    _ea_ean = str(ea.get('original_code', '')).strip()
                                    if _ea_ean in delineation_candidate_hhdivthres:
                                        _parent_hhdivthres = delineation_candidate_hhdivthres[_ea_ean]
                                        _max_bldgpv = max(
                                            sum(b.get('bldgpoints_value', 0.0) for b in p['buildings'])
                                            for p in split_parts
                                        )
                                        if _max_bldgpv >= _parent_hhdivthres:
                                            fback.pushWarning(
                                                f"[Barangay {bar_code}] [EA {ea['original_code']}] "
                                                f"bldgpoints_value validation: max part's bldgpoints_value ({_max_bldgpv:.4f}) "
                                                f">= hhdivthres ({_parent_hhdivthres:.4f}). "
                                                f"Enforcing {min_household + 1}–{max_household - 1} HH range on parts."
                                            )
                                            split_parts = enforce_min_household(split_parts, fback, ea_geom=ea['geom'])
                                            # Strictly enforce bldgpoints_value < hhdivthres by merging parts inside candidate boundaries
                                            split_parts = enforce_bldgpv_threshold(split_parts, _parent_hhdivthres, fback, ea_geom=ea['geom'])
                                    # ────────────────────────────────────────────────────────────
                                    new_eas.extend(split_parts)
                                    changed = True
                                    fback.pushInfo(f"[Barangay {bar_code}] Split over-populated EA (code={ea['original_code']}, pop={ea['hh_count']}) into {len(split_parts)} sub-polygons.")
                                else:
                                    new_eas.append(ea)
                        else:
                            new_eas.append(bar_eas[idx])
                    bar_eas = new_eas
                    if changed:
                        iteration += 1
                        continue
            
            # --- Diagnostic: report any over-threshold EAs that could not be resolved ---
            remaining_overs = [ea for ea in bar_eas if is_delineation_candidate(ea)]
            for ea in remaining_overs:
                unique_pt_count = len(set((b['point'].x(), b['point'].y()) for b in ea.get('buildings', [])))
                reason = []
                if unique_pt_count < 2:
                    reason.append(f"only {unique_pt_count} unique building point(s) — Voronoi cannot split")
                if unique_pt_count >= 2:
                    k_needed = max(2, int(round(ea['hh_count'] / float(target_household))))
                    if k_needed > unique_pt_count:
                        reason.append(f"k={k_needed} required but only {unique_pt_count} unique points available")
                if not reason:
                    reason.append("splitting consistently returned 1 part — check sliver threshold vs cell size")
                fback.pushWarning(
                    f"[Barangay {bar_code}] UNRESOLVED OVER-THRESHOLD: EA (code={ea['original_code']}, "
                    f"hh_count={ea['hh_count']}, bldg_count={ea.get('bldg_count',0)}, "
                    f"unique_pts={unique_pt_count}) after {iteration} iteration(s). "
                    f"Reason: {'; '.join(reason)}."
                )
                
            return bar_eas

        # Helper function to run the iterative merging loop on a single Barangay's EAs
        def process_barangay_merge(bar_code, bar_eas, fback):
            iteration = 0
            max_iterations = 5
            changed = True
            
            while changed and iteration < max_iterations:
                if fback.isCanceled():
                    break
                
                # Check merge threshold compliance
                has_unders = False
                for ea in bar_eas:
                    if is_merge_candidate(ea) or ea['hh_count'] == 0:
                        has_unders = True
                        break
                        
                if not has_unders:
                    break
                    
                changed = False
                
                # Case B: Merging
                merged_indices = set()
                new_eas = []
                
                for idx in range(len(bar_eas)):
                    if idx in merged_indices:
                        continue
                        
                    ea = bar_eas[idx]
                    
                    if ea['hh_count'] == 0:
                        # Force merge with any touching neighbor inside the same barangay to eliminate 0 hh_count
                        best_neighbor_idx = -1
                        best_neighbor_score = float('inf')
                        
                        for j in range(len(bar_eas)):
                            if idx == j or j in merged_indices:
                                continue
                                
                            neighbor = bar_eas[j]
                            if is_delineation_candidate(neighbor):
                                continue
                            # Skip neighbours whose original EAN was a delineation candidate
                            if neighbor.get('original_id') in delineation_candidate_ids:
                                continue
                            if ea['geom'].touches(neighbor['geom']) or ea['geom'].intersects(neighbor['geom']):
                                combined_hh = ea['hh_count'] + neighbor['hh_count']
                                score = combined_hh
                                if score < best_neighbor_score:
                                    best_neighbor_score = score
                                    best_neighbor_idx = j
                                    
                        if best_neighbor_idx != -1:
                            neighbor = bar_eas[best_neighbor_idx]
                            merged_geom = ea['geom'].combine(neighbor['geom'])
                            merged_geom = merged_geom.buffer(0.0, 3)
                            
                            merged_ea = {
                                'geom': merged_geom,
                                'buildings': ea.get('buildings', []) + neighbor.get('buildings', []),
                                'hh_count': ea['hh_count'] + neighbor['hh_count'],
                                'original_hhcount': ea.get('original_hhcount', 0) if ea['hh_count'] >= neighbor['hh_count'] else neighbor.get('original_hhcount', 0),
                                'bldg_count': ea.get('bldg_count', 0) + neighbor.get('bldg_count', 0),
                                'attributes': list(ea['attributes']) if ea['hh_count'] >= neighbor['hh_count'] else list(neighbor['attributes']),
                                'original_id': ea['original_id'] if ea['hh_count'] >= neighbor['hh_count'] else neighbor['original_id'],
                                'original_code': ea['original_code'] if ea['hh_count'] >= neighbor['hh_count'] else neighbor['original_code'],
                                'is_new': True,
                                'split_by': ea.get('split_by', 'none'),
                                'from_merge': True,
                                'parent_barangay': bar_code
                            }
                            
                            if best_neighbor_idx < idx:
                                try:
                                    new_eas.remove(neighbor)
                                except ValueError:
                                    pass
                                    
                            new_eas.append(merged_ea)
                            merged_indices.add(best_neighbor_idx)
                            merged_indices.add(idx)
                            changed = True
                            fback.pushInfo(f"[Barangay {bar_code}] Force-merged 0-household EA (code={ea['original_code']}) with adjacent neighbor (pop={neighbor['hh_count']}) -> Combined={merged_ea['hh_count']}")
                            continue
                            
                    # Skip merging if this EA was generated from a split AND is already at or above min_household.
                    # Under-populated split parts are still eligible for merging.
                    if ea.get('from_split', False) and ea['hh_count'] >= min_household:
                        new_eas.append(ea)
                        continue
                    
                    # Rule: delineation candidates must never be merged
                    if is_delineation_candidate(ea):
                        new_eas.append(ea)
                        continue
                        
                    if is_merge_candidate(ea):
                        best_neighbor_idx = -1
                        best_neighbor_score = float('inf')
                        
                        # Pass 0: Prioritize merging contiguous merge candidates (<= 100 HH)
                        for j in range(len(bar_eas)):
                            if idx == j or j in merged_indices:
                                continue
                            neighbor = bar_eas[j]
                            if is_merge_candidate(neighbor):
                                # Check contiguity
                                if ea['geom'].touches(neighbor['geom']) or ea['geom'].intersects(neighbor['geom']):
                                    combined_hh = ea['hh_count'] + neighbor['hh_count']
                                    if combined_hh < max_household:
                                        score = abs(combined_hh - (max_household - 1))
                                        if score < best_neighbor_score:
                                            best_neighbor_score = score
                                            best_neighbor_idx = j
                                            
                        # Pass 1: find the best adjacent non-split neighbor whose combined count is within threshold
                        if best_neighbor_idx == -1:
                            for j in range(len(bar_eas)):
                                if idx == j or j in merged_indices:
                                    continue
                                    
                                neighbor = bar_eas[j]
                                # Prefer non-split neighbours to avoid undoing valid splits
                                if neighbor.get('from_split', False):
                                    continue
                                if is_delineation_candidate(neighbor):
                                    continue
                                # Skip neighbours whose original EAN was a delineation candidate
                                if neighbor.get('original_id') in delineation_candidate_ids:
                                    continue
                                    
                                # Check contiguity
                                if ea['geom'].touches(neighbor['geom']) or ea['geom'].intersects(neighbor['geom']):
                                    combined_hh = ea['hh_count'] + neighbor['hh_count']
                                    if min_household <= combined_hh < max_household:
                                        score = abs(combined_hh - (max_household - 1))
                                        if score < best_neighbor_score:
                                            best_neighbor_score = score
                                            best_neighbor_idx = j
                        
                        # Pass 2: if no non-split neighbour found, allow from_split neighbours as fallback
                        if best_neighbor_idx == -1:
                            for j in range(len(bar_eas)):
                                if idx == j or j in merged_indices:
                                    continue
                                neighbor = bar_eas[j]
                                if is_delineation_candidate(neighbor):
                                    continue
                                # Skip neighbours whose original EAN was a delineation candidate
                                if neighbor.get('original_id') in delineation_candidate_ids:
                                    continue
                                if ea['geom'].touches(neighbor['geom']) or ea['geom'].intersects(neighbor['geom']):
                                    combined_hh = ea['hh_count'] + neighbor['hh_count']
                                    if min_household <= combined_hh < max_household:
                                        score = abs(combined_hh - (max_household - 1))
                                        if score < best_neighbor_score:
                                            best_neighbor_score = score
                                            best_neighbor_idx = j
                        
                        # Pass 3: if still no neighbour within strict threshold, allow any touching neighbour
                        # (combined must strictly be under max_household to prevent subsequent split)
                        if best_neighbor_idx == -1:
                            for j in range(len(bar_eas)):
                                if idx == j or j in merged_indices:
                                    continue
                                neighbor = bar_eas[j]
                                if is_delineation_candidate(neighbor):
                                    continue
                                # Skip neighbours whose original EAN was a delineation candidate
                                if neighbor.get('original_id') in delineation_candidate_ids:
                                    continue
                                if ea['geom'].touches(neighbor['geom']) or ea['geom'].intersects(neighbor['geom']):
                                    combined_hh = ea['hh_count'] + neighbor['hh_count']
                                    if combined_hh < max_household:
                                        score = abs(combined_hh - (max_household - 1))
                                        if score < best_neighbor_score:
                                            best_neighbor_score = score
                                            best_neighbor_idx = j
                        
                        # Pass 4: absolute fallback — nearest by centroid distance if nothing touches.
                        # Neighbors must keep the combined count strictly below max_household.
                        if best_neighbor_idx == -1:
                            up_centroid = ea['geom'].centroid().asPoint()
                            best_dist = float('inf')
                            for j in range(len(bar_eas)):
                                if idx == j or j in merged_indices:
                                    continue
                                if is_delineation_candidate(bar_eas[j]):
                                    continue
                                # Skip neighbours whose original EAN was a delineation candidate
                                if bar_eas[j].get('original_id') in delineation_candidate_ids:
                                    continue
                                dist = up_centroid.distance(bar_eas[j]['geom'].centroid().asPoint())
                                combined = ea['hh_count'] + bar_eas[j]['hh_count']
                                if combined < max_household:
                                    if dist < best_dist:
                                        best_dist = dist
                                        best_neighbor_idx = j
                            if best_neighbor_idx == -1:
                                # Truly no candidate — leave as-is
                                new_eas.append(ea)
                                continue

                        # --- Shared merge block (used by whichever Pass found the best neighbour) ---
                        if best_neighbor_idx != -1:
                            neighbor = bar_eas[best_neighbor_idx]
                            merged_geom = ea['geom'].combine(neighbor['geom'])
                            merged_geom = merged_geom.buffer(0.0, 3)

                            merged_ea = {
                                'geom': merged_geom,
                                'buildings': ea.get('buildings', []) + neighbor.get('buildings', []),
                                'hh_count': ea['hh_count'] + neighbor['hh_count'],
                                'original_hhcount': ea.get('original_hhcount', 0) if ea['hh_count'] >= neighbor['hh_count'] else neighbor.get('original_hhcount', 0),
                                'bldg_count': ea.get('bldg_count', 0) + neighbor.get('bldg_count', 0),
                                'attributes': list(ea['attributes']) if ea['hh_count'] >= neighbor['hh_count'] else list(neighbor['attributes']),
                                'original_id': ea['original_id'] if ea['hh_count'] >= neighbor['hh_count'] else neighbor['original_id'],
                                'original_code': ea['original_code'] if ea['hh_count'] >= neighbor['hh_count'] else neighbor['original_code'],
                                'is_new': True,
                                'split_by': ea.get('split_by', 'none'),
                                'from_merge': True,
                                'parent_barangay': bar_code
                            }

                            if best_neighbor_idx < idx:
                                try:
                                    new_eas.remove(neighbor)
                                except ValueError:
                                    pass

                            new_eas.append(merged_ea)
                            merged_indices.add(best_neighbor_idx)
                            merged_indices.add(idx)
                            changed = True
                            fback.pushInfo(f"[Barangay {bar_code}] Merged small EA (pop={ea['hh_count']}) with adjacent neighbor (pop={neighbor['hh_count']}) -> Combined={merged_ea['hh_count']}")
                        else:
                            new_eas.append(ea)
                    else:
                        new_eas.append(ea)

                bar_eas = new_eas
                if not changed:
                    break
                iteration += 1
                
            # --- Diagnostic: report any unresolved under-threshold EAs ---
            remaining_unders = [ea for ea in bar_eas if is_merge_candidate(ea)]
            for ea in remaining_unders:
                unique_pt_count = len(set((b['point'].x(), b['point'].y()) for b in ea.get('buildings', [])))
                fback.pushInfo(
                    f"[Barangay {bar_code}] UNRESOLVED UNDER-THRESHOLD: EA (code={ea['original_code']}, "
                    f"hh_count={ea['hh_count']}, bldg_count={ea.get('bldg_count',0)}, "
                    f"unique_pts={unique_pt_count}) — no valid merge neighbour found after {iteration} iteration(s)."
                )
                
            return bar_eas

        # --- Main Iterative Loop (Parallelized per Barangay) ---
        feedback.pushInfo("Phase 5/8: Iterative per-barangay splitting loop [SPLIT-FIRST]...")
        
        # Group starting EAs by parent barangay and sort by geocode for deterministic ordering
        barangay_groups = {}
        for ea in eas:
            bar = ea['parent_barangay']
            barangay_groups.setdefault(bar, []).append(ea)
        
        # Sort barangay keys by geocode value so processing and output follow geocode order
        sorted_bar_keys = sorted(
            barangay_groups.keys(),
            key=lambda k: str(k) if k is not None else ""
        )

        # Filter to only submit barangays that actually contain delineation candidates
        split_bar_keys = [
            bar_code for bar_code in sorted_bar_keys
            if any(is_delineation_candidate(ea) for ea in barangay_groups[bar_code])
        ]
            
        # ── Phase 6: Iterative per-barangay splitting loop ─────────────────────────────────────
        multi_feedback.setCurrentStep(4)
        multi_feedback.setProgressText(
            f"{_PHASE_LABELS[4]} [0/{len(split_bar_keys)} barangay(s)]..."
        )

        class ThreadFeedback:
            def __init__(self, parent_feedback):
                self.parent = parent_feedback
                self.logs = []
            def pushInfo(self, msg):
                self.logs.append(('info', msg))
            def pushWarning(self, msg):
                self.logs.append(('warning', msg))
            def isCanceled(self):
                return self.parent.isCanceled() if self.parent else False

        def process_barangay_split_wrapper(bar_code, bar_eas, parent_feedback):
            result = process_barangay_split(bar_code, bar_eas, parent_feedback)
            return result, []

        split_eas = []
        import concurrent.futures
        import time
        from qgis.PyQt.QtCore import QCoreApplication, QThread
        
        if split_bar_keys:
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
                # Submit tasks in geocode order so result collection preserves that order
                futures = {
                    executor.submit(process_barangay_split_wrapper, bar_code, barangay_groups[bar_code], feedback): bar_code 
                    for bar_code in split_bar_keys
                }
                
                # Polling loop to keep UI responsive and update progress
                _last_n_done = -1
                while not all(f.done() for f in futures.keys()):
                    if multi_feedback.isCanceled():
                        for f in futures.keys():
                            f.cancel()
                        raise QgsProcessingException("Algorithm cancelled by user.")
                    time.sleep(0.02)
                    if QThread.currentThread() == QCoreApplication.instance().thread():
                        QCoreApplication.processEvents()
                    
                    _n_done = sum(1 for f in futures.keys() if f.done())
                    if _n_done != _last_n_done:
                        _pct = int(_n_done / len(futures) * 100) if futures else 0
                        multi_feedback.setProgress(_pct)
                        multi_feedback.setProgressText(
                            f"{_PHASE_LABELS[4]} [{_n_done}/{len(futures)} barangay(s) done]..."
                        )
                        _last_n_done = _n_done

                # Collect results in geocode order (not completion order)
                ordered_futures = {bar_code: future for future, bar_code in futures.items()}
                for bar_code in sorted_bar_keys:
                    if bar_code in ordered_futures:
                        future = ordered_futures[bar_code]
                        if future.cancelled():
                            split_eas.extend(barangay_groups[bar_code])
                            continue
                        try:
                            result, logs = future.result()
                            split_eas.extend(result)
                            for log_type, msg in logs:
                                if log_type == 'info':
                                    feedback.pushInfo(msg)
                                elif log_type == 'warning':
                                    feedback.pushWarning(msg)
                        except Exception as e:
                            feedback.reportError(f"Error splitting Barangay {bar_code}: {str(e)}")
                    else:
                        split_eas.extend(barangay_groups[bar_code])
        else:
            # If no splits are needed, simply extend all EAs in their original order
            for bar_code in sorted_bar_keys:
                split_eas.extend(barangay_groups[bar_code])

        multi_feedback.setProgress(100)  # Phase 6 complete

        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")

        # ── Phase 7: Iterative per-barangay merging loop ─────────────────────────────────────
        feedback.pushInfo("Phase 6/8: Iterative per-barangay merging loop [PRIORITIZE CONTIGUOUS MERGES TO 299 HH]...")
        
        # Group split EAs by parent barangay
        barangay_split_groups = {}
        for ea in split_eas:
            bar = ea['parent_barangay']
            barangay_split_groups.setdefault(bar, []).append(ea)
            
        sorted_split_bar_keys = sorted(
            barangay_split_groups.keys(),
            key=lambda k: str(k) if k is not None else ""
        )

        # Filter to only submit barangays that actually contain EAs that are merge candidates or have 0 hh_count
        merge_bar_keys = [
            bar_code for bar_code in sorted_split_bar_keys
            if any(is_merge_candidate(ea) or ea['hh_count'] == 0 for ea in barangay_split_groups[bar_code])
        ]
        
        multi_feedback.setCurrentStep(5)
        multi_feedback.setProgressText(
            f"{_PHASE_LABELS[5]} [0/{len(merge_bar_keys)} barangay(s)]..."
        )
        
        def process_barangay_merge_wrapper(bar_code, bar_eas, parent_feedback):
            result = process_barangay_merge(bar_code, bar_eas, parent_feedback)
            return result, []
            
        final_merged_eas = []
        if merge_bar_keys:
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
                futures = {
                    executor.submit(process_barangay_merge_wrapper, bar_code, barangay_split_groups[bar_code], feedback): bar_code 
                    for bar_code in merge_bar_keys
                }
                
                _last_n_done = -1
                while not all(f.done() for f in futures.keys()):
                    if multi_feedback.isCanceled():
                        for f in futures.keys():
                            f.cancel()
                        raise QgsProcessingException("Algorithm cancelled by user.")
                    time.sleep(0.02)
                    if QThread.currentThread() == QCoreApplication.instance().thread():
                        QCoreApplication.processEvents()
                    
                    _n_done = sum(1 for f in futures.keys() if f.done())
                    if _n_done != _last_n_done:
                        _pct = int(_n_done / len(futures) * 100) if futures else 0
                        multi_feedback.setProgress(_pct)
                        multi_feedback.setProgressText(
                            f"{_PHASE_LABELS[5]} [{_n_done}/{len(futures)} barangay(s) done]..."
                        )
                        _last_n_done = _n_done

                ordered_futures = {bar_code: future for future, bar_code in futures.items()}
                for bar_code in sorted_split_bar_keys:
                    if bar_code in ordered_futures:
                        future = ordered_futures[bar_code]
                        if future.cancelled():
                            final_merged_eas.extend(barangay_split_groups[bar_code])
                            continue
                        try:
                            result, logs = future.result()
                            final_merged_eas.extend(result)
                            for log_type, msg in logs:
                                if log_type == 'info':
                                    feedback.pushInfo(msg)
                                elif log_type == 'warning':
                                    feedback.pushWarning(msg)
                        except Exception as e:
                            feedback.reportError(f"Error merging Barangay {bar_code}: {str(e)}")
                    else:
                        final_merged_eas.extend(barangay_split_groups[bar_code])
        else:
            for bar_code in sorted_split_bar_keys:
                final_merged_eas.extend(barangay_split_groups[bar_code])

        eas = final_merged_eas
        multi_feedback.setProgress(100)  # Phase 7 complete

        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")

        # ── Phase 7: Final Compliance Sweep ──────────────────────────────────────────────────
        multi_feedback.setCurrentStep(6)
        multi_feedback.setProgressText(f"{_PHASE_LABELS[6]}...")
        # --- Final Compliance Sweep ---
        # A global last-resort pass that enforces [min_household, max_household] on every EA
        # in the output list. Runs after per-barangay processing; handles any remaining
        # violations that the iterative loop could not resolve within its 25-iteration budget.
        feedback.pushInfo("Phase 7/8: Final compliance sweep...")
        # Temporary bypass to disable Phase 8
        compliance_changed = False
        compliance_pass = 0
        max_compliance_passes = 10
        feedback.pushInfo("TEMPORARY BYPASS: Skipping Phase 8 Final Compliance Sweep as requested.")

        while compliance_changed and compliance_pass < max_compliance_passes:
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            compliance_changed = False
            compliance_pass += 1
            
            _pct = int(compliance_pass / max_compliance_passes * 100)
            multi_feedback.setProgress(_pct)
            multi_feedback.setProgressText(
                f"{_PHASE_LABELS[6]} [pass {compliance_pass}/{max_compliance_passes}]..."
            )

            over_idx  = [i for i, ea in enumerate(eas) if is_delineation_candidate(ea)]
            under_idx = [i for i, ea in enumerate(eas) if is_merge_candidate(ea)]

            if not over_idx and not under_idx:
                break

            feedback.pushInfo(
                f"  Compliance pass {compliance_pass}: "
                f"{len(over_idx)} over-threshold, {len(under_idx)} under-threshold."
            )

            removed = set()
            added   = []

            # --- Fix over-threshold EAs via forced geometric split ---
            for i in over_idx:
                if i in removed:
                    continue
                ea = eas[i]
                # Rule: EAs produced by a merge must never be delineated
                if ea.get('from_merge', False):
                    continue
                parts = force_geometric_split(ea, max_household, feedback)
                if len(parts) > 1:
                    removed.add(i)
                    added.extend(parts)
                    compliance_changed = True
                    feedback.pushWarning(
                        f"[Final Sweep] Over-threshold EA (code={ea['original_code']}, "
                        f"pop={ea['hh_count']}) force-split into {len(parts)} part(s)."
                    )
                else:
                    feedback.pushWarning(
                        f"[Final Sweep] EA (code={ea['original_code']}, pop={ea['hh_count']}) "
                        f"cannot be split further — truly unresolvable."
                    )

            # --- Fix under-threshold EAs via forced merge with best barangay neighbour ---
            for i in under_idx:
                if i in removed:
                    continue
                ea = eas[i]
                bar = ea['parent_barangay']

                # Pass 1: touching neighbour in same barangay whose combined count is strictly
                # within (min_household, max_household) — i.e. > 100 and < 300
                best_j = -1
                best_score = float('inf')
                for j, nb in enumerate(eas):
                    if j == i or j in removed:
                        continue
                    if nb['parent_barangay'] != bar:
                        continue
                    if is_delineation_candidate(nb):
                        continue
                    if ea['geom'].touches(nb['geom']) or ea['geom'].intersects(nb['geom']):
                        combined = ea['hh_count'] + nb['hh_count']
                        if min_household < combined < max_household:  # strictly > 100 and < 300
                            score = abs(combined - (max_household - 1))
                            if score < best_score:
                                best_score = score
                                best_j = j

                # Pass 2: any touching neighbour in same barangay (must be under max)
                if best_j == -1:
                    for j, nb in enumerate(eas):
                        if j == i or j in removed:
                            continue
                        if nb['parent_barangay'] != bar:
                            continue
                        if is_delineation_candidate(nb):
                            continue
                        if ea['geom'].touches(nb['geom']) or ea['geom'].intersects(nb['geom']):
                            combined = ea['hh_count'] + nb['hh_count']
                            if combined < max_household:
                                score = abs(combined - (max_household - 1))
                                if score < best_score:
                                    best_score = score
                                    best_j = j

                # Pass 3: nearest centroid in same barangay (must be under max)
                if best_j == -1:
                    up_centroid = ea['geom'].centroid().asPoint()
                    best_dist = float('inf')
                    for j, nb in enumerate(eas):
                        if j == i or j in removed:
                            continue
                        if nb['parent_barangay'] != bar:
                            continue
                        if is_delineation_candidate(nb):
                            continue
                        combined = ea['hh_count'] + nb['hh_count']
                        if combined < max_household:
                            dist = up_centroid.distance(nb['geom'].centroid().asPoint())
                            if dist < best_dist:
                                best_dist = dist
                                best_j = j

                if best_j != -1:
                    nb = eas[best_j]
                    dominant = nb if nb['hh_count'] >= ea['hh_count'] else ea
                    merged_ea = {
                        'geom': ea['geom'].combine(nb['geom']).buffer(0.0, 3),
                        'buildings': ea.get('buildings', []) + nb.get('buildings', []),
                        'hh_count': ea['hh_count'] + nb['hh_count'],
                        'original_hhcount': dominant.get('original_hhcount', 0),
                        'bldg_count': ea.get('bldg_count', 0) + nb.get('bldg_count', 0),
                        'attributes': list(dominant['attributes']),
                        'original_id': dominant['original_id'],
                        'original_code': dominant['original_code'],
                        'is_new': True,
                        'from_split': False,
                        'split_by': ea.get('split_by', 'none'),
                        'from_merge': True,
                        'parent_barangay': bar
                    }
                    removed.add(i)
                    removed.add(best_j)
                    added.append(merged_ea)
                    compliance_changed = True
                    merged_hh = merged_ea['hh_count']
                    if merged_hh <= min_household or merged_hh > max_household:
                        feedback.pushWarning(
                            f"[Final Sweep] Merge result out of range: combined={merged_hh} HH "
                            f"(EA {ea['original_code']} + {nb['original_code']}). "
                            f"Expected strictly > {min_household} and <= {max_household}."
                        )
                    else:
                        feedback.pushInfo(
                            f"[Final Sweep] Under-threshold EA (code={ea['original_code']}, "
                            f"pop={ea['hh_count']}) merged with (code={nb['original_code']}, "
                            f"pop={nb['hh_count']}) → combined={merged_hh}."
                        )
                else:
                    feedback.pushWarning(
                        f"[Final Sweep] EA (code={ea['original_code']}, pop={ea['hh_count']}) "
                        f"has no merge partner in barangay {bar} — truly isolated."
                    )

            if removed or added:
                eas = [ea for i, ea in enumerate(eas) if i not in removed] + added

        remaining_violations = [ea for ea in eas if ea['hh_count'] < min_household or ea['hh_count'] > max_household]
        if remaining_violations:
            feedback.pushWarning(
                f"Final compliance sweep complete ({compliance_pass} pass(es)): "
                f"{len(remaining_violations)} EA(s) still violate thresholds and could not be resolved."
            )
        else:
            feedback.pushInfo(f"Final compliance sweep complete ({compliance_pass} pass(es)): all EAs are within threshold.")

        multi_feedback.setProgress(100)  # Phase 7 complete

        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")

        # --- Post-Processing: Spatial Barangay Sorting & Code Assignment ---
        feedback.pushInfo("Post-processing: Spatially sorting EAs within parent barangays and assigning new_ea codes...")
        
        # Group by parent barangay (cached parent_barangay is already propagated)
        barangay_to_final_eas = {}
        for ea in eas:
            bar = ea['parent_barangay']
            if bar not in barangay_to_final_eas:
                barangay_to_final_eas[bar] = []
            barangay_to_final_eas[bar].append(ea)

        # Sort spatially (West-to-East based on centroid X coordinate)
        def get_sort_key(ea_item):
            centroid = ea_item['geom'].centroid().asPoint()
            return (centroid.x(), centroid.y())

        # Iterate barangays in geocode order for deterministic, incremental code assignment
        for bar in sorted(barangay_to_final_eas.keys(), key=lambda k: str(k) if k is not None else ""):
            bar_eas = barangay_to_final_eas[bar]
            
            # Centroid-based geographic ordering shall only be performed for barangays that contain identified Candidates for Delineation.
            has_delin = any(ea.get('original_id') in delineation_candidate_ids for ea in barangay_groups.get(bar, []))
            if has_delin:
                bar_eas.sort(key=get_sort_key)
            else:
                def get_original_order_key(ea_item):
                    orig_id = ea_item.get('original_id', 99999999)
                    centroid = ea_item['geom'].centroid().asPoint()
                    return (orig_id, centroid.x())
                bar_eas.sort(key=get_original_order_key)

            new_ea_counter = 0
            for i, ea in enumerate(bar_eas):
                # Derive original EA suffix (XXX) from the "name" field if present, or fallback to the geocode
                orig_last3 = "000"
                name_idx = out_fields.indexOf("name")
                if name_idx != -1 and ea['attributes'][name_idx] is not None:
                    name_val = str(ea['attributes'][name_idx]).strip()
                    # Extract all consecutive digits from the name value
                    digits = "".join([c for c in name_val if c.isdigit()])
                    if len(digits) >= 3:
                        # Extract the first 3 digits of the numeric sequence (e.g., "001" from "001000")
                        orig_last3 = digits[:3]
                    elif len(digits) > 0:
                        orig_last3 = digits.zfill(3)
                
                # Fallback to geocode-based extraction if name field is missing, empty, or non-numeric
                if orig_last3 == "000" or not orig_last3.isdigit():
                    orig_code_str = str(ea['original_code']).strip() if ea['original_code'] is not None else "000"
                    if orig_code_str.endswith(".0"):
                        orig_code_str = orig_code_str[:-2]
                        
                    # Extract suffix: if it is a full geocode (length > 9), skip the 9-digit barangay code from the left.
                    # Otherwise, treat the entire string as the EA identifier.
                    if len(orig_code_str) > 9:
                        suffix = orig_code_str[9:]
                    else:
                        suffix = orig_code_str
                        
                    # Clean suffix and pad with zeros from the left to ensure exactly 3 digits
                    orig_last3 = suffix.zfill(3)
                    if len(orig_last3) > 3:
                        orig_last3 = orig_last3[-3:]
                        
                # Determine sequence number suffix YYY
                # If it is a newly generated/modified EA, number starting from max_ea_number + 1
                if ea.get('is_new', False):
                    seq_num = max_ea_number.get(bar, 0) + 1 + new_ea_counter
                    seq_str = f"{seq_num:03d}"
                    new_ea_counter += 1
                    ea['new_ea_code'] = seq_str + orig_last3
                else:
                    # If it is unchanged, retain the original EA code
                    orig_code_str = str(ea['original_code']).strip() if ea['original_code'] is not None else ""
                    if orig_code_str.endswith(".0"):
                        orig_code_str = orig_code_str[:-2]
                    ea['new_ea_code'] = orig_code_str
                
                # Cache sort index to preserve the conditional sorting sequence in output generation
                ea['sort_index'] = i

        # ── Phase 8: Output Generation ───────────────────────────────────────────────────────────
        multi_feedback.setCurrentStep(7)
        multi_feedback.setProgressText(f"{_PHASE_LABELS[7]} [0/{len(eas):,}]...")
        # --- Output Generation ---
        feedback.pushInfo("Phase 8/8: Writing output features...")
        
        # Sort output EAs by geocode (parent_barangay) then by sort_index to preserve the
        # conditional sorting sequence from code assignment.
        eas.sort(key=lambda ea: (
            str(ea.get('parent_barangay', '')) if ea.get('parent_barangay') is not None else '',
            ea.get('sort_index', 0)
        ))
        barangay_to_target = None
        if previous_ea_source.sourceCrs() != target_crs:
            feedback.pushInfo(f"Transforming output to {target_crs.authid()}...")
            barangay_to_target = QgsCoordinateTransform(
                previous_ea_source.sourceCrs(), target_crs, context.transformContext()
            )

        for i, ea in enumerate(eas):
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            yield_to_ui(i, 50)
                
            geom = QgsGeometry(ea['geom'])
            if barangay_to_target:
                geom.transform(barangay_to_target)

            # Resolve any GeometryCollection produced by intersection() into a clean MultiPolygon.
            # buffer(0.0, 3) forces GEOS to re-classify mixed geometry as polygon-only.
            geom = geom.buffer(0.0, 3)
            geom.convertToMultiType()

            # If the geometry is still not a polygon type (e.g. still a GeometryCollection),
            # extract only the polygon parts and reassemble as MultiPolygon.
            if geom.wkbType() not in (
                QgsWkbTypes.MultiPolygon, QgsWkbTypes.Polygon,
                QgsWkbTypes.MultiPolygon25D, QgsWkbTypes.Polygon25D
            ):
                poly_parts = [g for g in geom.asGeometryCollection()
                              if g.type() == QgsWkbTypes.PolygonGeometry and not g.isEmpty()]
                if not poly_parts:
                    feedback.pushWarning(
                        f"[Output] EA (code={ea.get('original_code', '?')}, "
                        f"pop={ea.get('hh_count', '?')}) has no polygon geometry after "
                        f"type resolution — skipping feature."
                    )
                    continue
                geom = QgsGeometry.collectGeometry(poly_parts).buffer(0.0, 3)
                geom.convertToMultiType()
            
            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(geom)
            
            # Pad the attributes list to match out_fields count
            attrs = list(ea['attributes'])
            needed = out_fields.count() - len(attrs)
            if needed > 0:
                attrs.extend([None] * needed)
            out_feat.setAttributes(attrs)
            
            # Unchanged Retain EAs shall retain their original household counts
            is_unchanged_retain = False
            if not ea.get('from_split', False) and not ea.get('from_merge', False):
                _ea_ean_str = str(ea.get('original_code', '')).strip()
                if _ea_id not in delineation_candidate_ids and _ea_id not in merge_candidate_ids:
                    is_unchanged_retain = True
            
            final_pop = ea['original_hhcount'] if is_unchanged_retain else ea['hh_count']

            pop_idx = out_fields.indexOf(output_hh_field)
            if pop_idx != -1:
                out_feat.setAttribute(pop_idx, final_pop)
                
            new_ea_idx = out_fields.indexOf("new_ea")
            if new_ea_idx != -1:
                out_feat.setAttribute(new_ea_idx, ea['new_ea_code'])
                
            bldg_count_idx = out_fields.indexOf("bldg_count")
            if bldg_count_idx != -1:
                out_feat.setAttribute(bldg_count_idx, ea.get('bldg_count', 0))

            hh_count_idx = out_fields.indexOf("hh_count")
            if hh_count_idx != -1:
                out_feat.setAttribute(hh_count_idx, final_pop)

            hhcount_idx = out_fields.indexOf("hhcount")
            if hhcount_idx != -1:
                out_feat.setAttribute(hhcount_idx, final_pop)

            bldgpts_val_idx = out_fields.indexOf("bldgpoints_value")
            if bldgpts_val_idx != -1:
                out_feat.setAttribute(bldgpts_val_idx, ea.get('bldgpoints_value', 0.0))
            
            split_by_idx = out_fields.indexOf("split_by")
            if split_by_idx != -1:
                out_feat.setAttribute(split_by_idx, ea.get('split_by', 'none'))

            # Add correspondence_ea_geocode (concatenated map_uuid, geocode, sy)
            corr_ea_geo_idx = out_fields.indexOf("correspondence_ea_geocode")
            if corr_ea_geo_idx != -1:
                map_uuid_idx = out_fields.indexOf("map_uuid")
                geocode_idx = out_fields.indexOf("geocode")
                sy_idx = out_fields.indexOf("sy")
                
                map_uuid_val = out_feat.attribute(map_uuid_idx) if map_uuid_idx != -1 else ""
                geocode_val = out_feat.attribute(geocode_idx) if geocode_idx != -1 else ""
                sy_val = out_feat.attribute(sy_idx) if sy_idx != -1 else ""
                
                map_uuid_str = str(map_uuid_val) if map_uuid_val is not None else ""
                geocode_str = str(geocode_val) if geocode_val is not None else ""
                sy_str = str(sy_val) if sy_val is not None else ""
                
                if map_uuid_str.endswith(".0"):
                    map_uuid_str = map_uuid_str[:-2]
                if geocode_str.endswith(".0"):
                    geocode_str = geocode_str[:-2]
                if sy_str.endswith(".0"):
                    sy_str = sy_str[:-2]
                
                concat_val = f"{map_uuid_str}:{geocode_str}:{sy_str}"
                out_feat.setAttribute(corr_ea_geo_idx, concat_val)
                
#            if not sink.addFeature(out_feat, QgsFeatureSink.Flag.FastInsert):
#                feedback.reportError(f"Failed to add EA {i} to sink.")

            # Add to delineated sink if it originated from a delineation candidate
            # (Use EAN lookup instead of from_split flag, which can be overwritten by Phase 8 merges)
            _ea_id = ea.get('original_id')
            _is_delineation_result = (
                ea.get('from_split', False)
                or _ea_id in delineation_candidate_ids
            )
            if _is_delineation_result:
                if delineated_sink is not None:
                    if not delineated_sink.addFeature(out_feat, QgsFeatureSink.Flag.FastInsert):
                        feedback.reportError(f"Failed to add EA {i} to delineated sink.")
            
            # Add to merged sink if it was merged (and not a delineation result)
            if ea.get('from_merge', False) and not _is_delineation_result:
                if merged_sink is not None:
                    if not merged_sink.addFeature(out_feat, QgsFeatureSink.Flag.FastInsert):
                        feedback.reportError(f"Failed to add EA {i} to merged sink.")

            # Add matched buildings to extracted buildings sink
            if extracted_buildings_sink is not None:
                bldg_out_fields = QgsFields(building_source.fields())
                if bldg_out_fields.indexOf("parent_ean") == -1:
                    bldg_out_fields.append(QgsField("parent_ean", QVariant.String))
                    
                bldgpts_idx = bldg_out_fields.indexOf("bldgpoints_value")
                if bldgpts_idx == -1:
                    bldgpts_idx = bldg_out_fields.indexOf("bldgpts_val")
                if bldgpts_idx == -1:
                    bldg_out_fields.append(QgsField("bldgpoints_value", QVariant.Double))
                    bldgpts_idx = bldg_out_fields.count() - 1
                    
                pop_out_idx = bldg_out_fields.indexOf("pop")
                if pop_out_idx == -1:
                    pop_out_idx = bldg_out_fields.indexOf(bldg_hh_field)
                if pop_out_idx == -1:
                    bldg_out_fields.append(QgsField("pop", QVariant.Double))
                    pop_out_idx = bldg_out_fields.count() - 1
                    
                parent_ean_idx = bldg_out_fields.indexOf("parent_ean")
                
                parent_ean_val = ea.get('new_ea_code', ea.get('original_code', ''))
                _is_target_ea = (
                    ea.get('from_split', False)
                    or ea.get('from_merge', False)
                    or _ea_orig_code in delineation_candidate_eans
                    or _ea_orig_code in merge_candidate_eans
                    or _ea_orig_code in adjacent_ea_eans
                )
                if _is_target_ea:
                    for b in ea.get('buildings', []):
                        b_feat = QgsFeature(bldg_out_fields)
                        b_geom = QgsGeometry.fromPointXY(b['point'])
                        if barangay_to_target:
                            b_geom.transform(barangay_to_target)
                        b_feat.setGeometry(b_geom)
                        
                        b_attrs = list(b['attributes']) if 'attributes' in b else []
                        needed = bldg_out_fields.count() - len(b_attrs)
                        if needed > 0:
                            b_attrs.extend([None] * needed)
                        elif len(b_attrs) > bldg_out_fields.count():
                            b_attrs = b_attrs[:bldg_out_fields.count()]
                        
                        if bldgpts_idx != -1:
                            b_attrs[bldgpts_idx] = b['bldgpoints_value']
                        if pop_out_idx != -1:
                            b_attrs[pop_out_idx] = b['pop']
                        if parent_ean_idx != -1:
                            b_attrs[parent_ean_idx] = str(parent_ean_val)
                        
                        b_feat.setAttributes(b_attrs)
                        if not extracted_buildings_sink.addFeature(b_feat, QgsFeatureSink.Flag.FastInsert):
                            feedback.reportWarning("Failed to add building point to extracted buildings sink.")

            _out_pct = int((i + 1) / max(len(eas), 1) * 100)
            multi_feedback.setProgress(_out_pct)
            if i % 100 == 0 or _out_pct == 100:
                multi_feedback.setProgressText(
                    f"{_PHASE_LABELS[7]} [{i + 1:,}/{len(eas):,}]..."
                )

        multi_feedback.setProgress(100)  # Phase 8 complete
        feedback.pushInfo("Successfully created and structured Enumeration Areas.")

        # Log total EAs processed and total delineation candidates identified at the end
        total_proc = getattr(self, 'total_ea_processed', 0)
        total_cand = getattr(self, 'total_delin_candidates', 0)
        feedback.pushInfo("--------------------------------------------------")
        feedback.pushInfo(f"Total number of EAs processed: {total_proc}")
        feedback.pushInfo(f"Total number of delineation candidates identified (hhcount >= {max_household}): {total_cand}")
        feedback.pushInfo("--------------------------------------------------")

        return outputs

    def createInstance(self):
        """Create a new instance of this algorithm."""
        return self.__class__()

