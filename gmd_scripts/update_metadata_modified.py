# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU General Public License as published by  *
# *   the Free Software Foundation; either version 2 of the License, or     *
# *   (at your option) any later version.                                   *
# *                                                                         *
# ***************************************************************************

import uuid
import os
import difflib
import inspect
from typing import Any, Optional

from PyQt5.QtCore import QVariant, Qt
from PyQt5.QtWidgets import (
    QComboBox,
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
    QMessageBox,
)
from PyQt5.QtGui import QFont, QColor
from qgis.core import (
    NULL,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterEnum,
    QgsProcessingParameterString,
    QgsProcessingParameterFile,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingUtils,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis import processing
from processing.gui.wrappers import WidgetWrapper


def normalize_barangay_name(name: str) -> str:
    """
    Standardizes Barangay names to ensure robust matching even with variations in
    spelling, prefixes, spacing, punctuation, and abbreviations (e.g. Sta. vs Santa, Brgy vs Barangay).
    """
    if not name:
        return ""
    # Lowercase and trim
    s = name.lower().strip()
    
    # Standardize common abbreviations
    s = s.replace("sta.", "santa").replace("sta ", "santa ").replace(" sta", " santa")
    s = s.replace("sto.", "santo").replace("sto ", "santo ").replace(" sto", " santo")
    
    # Strip common administrative terms
    for term in ["barangay", "brgy.", "brgy", "bgy.", "bgy"]:
        s = s.replace(term, "")
        
    # Convert Roman numerals at the end of the string to digits (e.g. "poblacion i" -> "poblacion 1")
    roman_map = {
        "xv": "15", "xiv": "14", "xiii": "13", "xii": "12", "xi": "11",
        "x": "10", "ix": "9", "viii": "8", "vii": "7", "vi": "6",
        "v": "5", "iv": "4", "iii": "3", "ii": "2", "i": "1"
    }
    
    words = s.split()
    if words:
        last_word = words[-1]
        if last_word in roman_map:
            words[-1] = roman_map[last_word]
            s = " ".join(words)
            
    # Remove all non-alphanumeric characters to eliminate spaces, dashes, dots, etc.
    s = "".join(c for c in s if c.isalnum())
    
    # Strip leading zeros from numeric strings (e.g. "01" -> "1")
    if s.isdigit():
        s = str(int(s))
        
    return s


class PsgcFilterWidgetWrapper(WidgetWrapper):
    """
    Custom widget wrapper for Region, Province, and City/Municipality parameters.
    It coordinates with other parameter widget wrappers in the dialog to implement
    cascading dropdowns.
    """

    def __init__(self, *args, **kwargs):
        self.combo = None
        self.table_wrapper = None
        self.input_wrapper = None
        self.region_wrapper = None
        self.province_wrapper = None
        self.city_mun_wrapper = None
        self._updating = False
        super().__init__(*args, **kwargs)

    def createWidget(self):
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self.on_index_changed)
        return self.combo

    def postInitialize(self, wrappers):
        super().postInitialize(wrappers)
        
        # Locate sibling wrappers in the dialog
        for w in wrappers:
            name = w.parameterDefinition().name()
            if name == "TABLE":
                self.table_wrapper = w
            elif name == "INPUT":
                self.input_wrapper = w
            elif name == "REGION":
                self.region_wrapper = w
            elif name == "PROVINCE":
                self.province_wrapper = w
            elif name == "CITY_MUN":
                self.city_mun_wrapper = w

        # Table wrapper will notify us when a new layer/table is selected
        if self.table_wrapper:
            self.table_wrapper.widgetValueHasChanged.connect(self.on_table_changed)

        # Re-detect when the INPUT (LGU boundary) layer changes
        if self.input_wrapper:
            try:
                self.input_wrapper.widgetValueHasChanged.connect(self._on_input_changed)
            except Exception:
                pass

        # Populate options initially, then auto-detect from loaded layers
        self.update_options()
        self.apply_auto_detect()

    def on_index_changed(self, idx):
        if self._updating:
            return
        self.widgetValueHasChanged.emit(self)
        
        # Cascade changes downwards
        name = self.parameterDefinition().name()
        if name == "REGION":
            if self.province_wrapper:
                self.province_wrapper.update_options()
            if self.city_mun_wrapper:
                self.city_mun_wrapper.update_options()
        elif name == "PROVINCE":
            if self.city_mun_wrapper:
                self.city_mun_wrapper.update_options()

    def on_table_changed(self, wrapper):
        self.update_options()
        self.apply_auto_detect()

    def _on_input_changed(self, wrapper):
        """Re-run auto-detection when the INPUT (LGU boundary) layer changes."""
        self.apply_auto_detect()

    def _extract_citymun_from_layers(self):
        """
        Reads the name of the currently selected INPUT (LGU boundary) layer
        and searches for a city/municipality name from the PSGC table within it.

        Matching strategy (in priority order):
          1. Exact substring match (normalized: lowercase, stripped of separators
             and common suffixes like '_bgy' / '_barangay').
          2. difflib fuzzy-match fallback (cutoff=0.75) for spelling variants.

        Returns a dict {"region": ..., "province": ..., "city_mun": ...}
        on success, or None if no match is found.
        """
        import re

        layer = self._get_selected_layer()
        if not layer:
            return None

        fields = layer.fields()

        def find_field(target):
            tn = target.lower().replace("_", "").replace("/", "").replace(" ", "")
            for f in fields:
                fn = f.name().lower().replace("_", "").replace("/", "").replace(" ", "")
                if fn == tn:
                    return f.name()
            return None

        reg_f     = find_field("region")
        prov_f    = find_field("province")
        citymun_f = (
            find_field("city_mun") or find_field("city/municipality")
            or find_field("municipality") or find_field("city")
            or find_field("citymun")
        )

        if not citymun_f:
            return None

        # Build index: normalized_city_mun -> {region, province, city_mun}
        citymun_index = {}
        for feat in layer.getFeatures():
            cm   = str(feat.attribute(citymun_f)).strip()
            reg  = str(feat.attribute(reg_f)).strip()  if reg_f  else ""
            prov = str(feat.attribute(prov_f)).strip() if prov_f else ""
            if not cm or cm == "NULL":
                continue
            norm_cm = re.sub(r'[^a-z0-9]', '', cm.lower())
            if norm_cm and norm_cm not in citymun_index:
                citymun_index[norm_cm] = {
                    "region":   reg,
                    "province": prov,
                    "city_mun": cm,
                }

        if not citymun_index:
            return None

        norm_keys = list(citymun_index.keys())

        def normalize_lname(raw_name):
            """Strip _bgy/_barangay suffix, replace separators, remove non-alnum."""
            s = re.sub(r'[_\-\s]+(bgy|barangay)$', '', raw_name, flags=re.IGNORECASE)
            s = re.sub(r'[_\-]+', ' ', s)
            return re.sub(r'[^a-z0-9]', '', s.lower())

        # Resolve the name of the selected INPUT (LGU boundary) layer only
        input_layer_name = ""
        if self.input_wrapper:
            try:
                input_val = self.input_wrapper.parameterValue()
                if input_val:
                    input_lyr = QgsProject.instance().mapLayer(str(input_val))
                    if input_lyr and input_lyr.isValid():
                        input_layer_name = input_lyr.name()
            except Exception:
                pass

        if not input_layer_name:
            return None

        norm_input = normalize_lname(input_layer_name)
        if not norm_input:
            return None

        # Priority 1: exact substring match
        for norm_cm, data in citymun_index.items():
            if norm_cm in norm_input or norm_input in norm_cm:
                return data

        # Priority 2: fuzzy fallback
        close = difflib.get_close_matches(norm_input, norm_keys, n=1, cutoff=0.75)
        if close:
            return citymun_index[close[0]]

        return None

    def apply_auto_detect(self):
        """
        Run auto-detection and pre-select Region -> Province -> City/Mun dropdowns
        based on city/mun names found in loaded QGIS project layer names.

        Only the REGION wrapper instance acts as the orchestrator so that the
        cascade fires exactly once (not once per dropdown wrapper).
        """
        if self.parameterDefinition().name() != "REGION":
            return

        detected = self._extract_citymun_from_layers()
        if not detected:
            return

        # 1. Set Region (suppress on_index_changed cascade; we control it manually)
        if self.region_wrapper and detected.get("region"):
            idx = self.region_wrapper.combo.findText(detected["region"])
            if idx != -1:
                self.region_wrapper._updating = True
                self.region_wrapper.combo.setCurrentIndex(idx)
                self.region_wrapper._updating = False

        # 2. Refresh Province list (now filtered by the selected region), then select
        if self.province_wrapper:
            self.province_wrapper.update_options()
            if detected.get("province"):
                idx = self.province_wrapper.combo.findText(detected["province"])
                if idx != -1:
                    self.province_wrapper._updating = True
                    self.province_wrapper.combo.setCurrentIndex(idx)
                    self.province_wrapper._updating = False

        # 3. Refresh City/Mun list (now filtered by the selected province), then select
        if self.city_mun_wrapper:
            self.city_mun_wrapper.update_options()
            if detected.get("city_mun"):
                idx = self.city_mun_wrapper.combo.findText(detected["city_mun"])
                if idx != -1:
                    self.city_mun_wrapper._updating = True
                    self.city_mun_wrapper.combo.setCurrentIndex(idx)
                    self.city_mun_wrapper._updating = False

    def _get_selected_layer(self):
        if not self.table_wrapper:
            return None
        layer_val = self.table_wrapper.parameterValue()
        if not layer_val:
            return None
            
        layer = QgsProject.instance().mapLayer(str(layer_val))
        if not layer or not layer.isValid():
            # Try parsing as path
            if os.path.exists(str(layer_val)):
                layer = QgsVectorLayer(str(layer_val), "temp_psgc", "ogr")
        return layer if (layer and layer.isValid()) else None

    def update_options(self):
        if self._updating:
            return
        self._updating = True
        
        try:
            name = self.parameterDefinition().name()
            layer = self._get_selected_layer()
            
            current_text = self.combo.currentText()
            self.combo.clear()
            
            if not layer:
                if name == "REGION":
                    self.combo.addItems(["All Regions"])
                elif name == "PROVINCE":
                    self.combo.addItems(["All Provinces"])
                elif name == "CITY_MUN":
                    self.combo.addItems(["All Cities/Municipalities"])
                self._updating = False
                return

            fields = layer.fields()
            
            def find_field(target_name):
                target_norm = target_name.lower().replace("_", "").replace("/", "").replace(" ", "")
                for field in fields:
                    name_norm = field.name().lower().replace("_", "").replace("/", "").replace(" ", "")
                    if name_norm == target_norm:
                        return field.name()
                return None
                
            reg_f = find_field("region")
            prov_f = find_field("province")
            citymun_f = find_field("city_mun") or find_field("city/municipality") or find_field("municipality") or find_field("city") or find_field("citymun")
            
            if name == "REGION":
                regions = ["All Regions"]
                if reg_f:
                    idx = fields.indexOf(reg_f)
                    unique_vals = sorted([str(v).strip() for v in layer.uniqueValues(idx) if v is not None and v != NULL and str(v).strip() != ""])
                    regions.extend(unique_vals)
                self.combo.addItems(regions)
                
            elif name == "PROVINCE":
                provinces = ["All Provinces"]
                selected_region = self.region_wrapper.combo.currentText() if self.region_wrapper else "All Regions"
                
                if prov_f:
                    if not reg_f or selected_region == "All Regions":
                        idx = fields.indexOf(prov_f)
                        unique_vals = sorted([str(v).strip() for v in layer.uniqueValues(idx) if v is not None and v != NULL and str(v).strip() != ""])
                        provinces.extend(unique_vals)
                    else:
                        idx_prov = fields.indexOf(prov_f)
                        idx_reg = fields.indexOf(reg_f)
                        unique_vals = set()
                        for feat in layer.getFeatures():
                            r_val = str(feat.attribute(idx_reg)).strip()
                            p_val = str(feat.attribute(idx_prov)).strip()
                            if r_val.lower() == selected_region.lower() and p_val and p_val != "NULL" and p_val != "":
                                unique_vals.add(p_val)
                        provinces.extend(sorted(list(unique_vals)))
                self.combo.addItems(provinces)
                
            elif name == "CITY_MUN":
                city_muns = ["All Cities/Municipalities"]
                selected_region = self.region_wrapper.combo.currentText() if self.region_wrapper else "All Regions"
                selected_province = self.province_wrapper.combo.currentText() if self.province_wrapper else "All Provinces"
                
                if citymun_f:
                    if (not reg_f or selected_region == "All Regions") and (not prov_f or selected_province == "All Provinces"):
                        idx = fields.indexOf(citymun_f)
                        unique_vals = sorted([str(v).strip() for v in layer.uniqueValues(idx) if v is not None and v != NULL and str(v).strip() != ""])
                        city_muns.extend(unique_vals)
                    else:
                        idx_city = fields.indexOf(citymun_f)
                        idx_prov = fields.indexOf(prov_f) if prov_f else -1
                        idx_reg = fields.indexOf(reg_f) if reg_f else -1
                        unique_vals = set()
                        for feat in layer.getFeatures():
                            c_val = str(feat.attribute(idx_city)).strip()
                            if not c_val or c_val == "NULL" or c_val == "":
                                continue
                            
                            if idx_reg != -1 and selected_region != "All Regions":
                                r_val = str(feat.attribute(idx_reg)).strip()
                                if r_val.lower() != selected_region.lower():
                                    continue
                            if idx_prov != -1 and selected_province != "All Provinces":
                                p_val = str(feat.attribute(idx_prov)).strip()
                                if p_val.lower() != selected_province.lower():
                                    continue
                                    
                            unique_vals.add(c_val)
                        city_muns.extend(sorted(list(unique_vals)))
                self.combo.addItems(city_muns)

            # Restore selection if possible, otherwise default to first item
            restore_idx = self.combo.findText(current_text)
            if restore_idx != -1:
                self.combo.setCurrentIndex(restore_idx)
            else:
                self.combo.setCurrentIndex(0)
                
        finally:
            self._updating = False

    def value(self):
        if self.combo:
            return self.combo.currentText()
        return ""

    def setValue(self, value):
        if self.combo:
            idx = self.combo.findText(str(value))
            if idx != -1:
                self.combo.setCurrentIndex(idx)


class TablePreviewWidgetWrapper(WidgetWrapper):
    """
    Custom widget wrapper that renders a live, color-coded QTableWidget preview
    of the resulting joined administrative data and matches statistics, 
    updating dynamically before the algorithm is run.
    """

    def __init__(self, *args, **kwargs):
        self.container = None
        self.header_label = None
        self.stats_label = None
        self.table = None
        self.refresh_btn = None
        
        self.input_wrapper = None
        self.input_field_wrapper = None
        self.table_wrapper = None
        self.region_wrapper = None
        self.province_wrapper = None
        self.city_mun_wrapper = None
        self.source_wrapper = None
        self.unmatched_layer = None  # temporary layer for unmatched features
        self._unmatched_features = []  # list of QgsFeature objects
        self.source_year_wrapper = None
        super().__init__(*args, **kwargs)

    def createWidget(self):
        self.container = QWidget()
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(6)
        
        # Header Layout to align title and toggle checkbox horizontally
        header_layout = QHBoxLayout()
        
        # Header Label with icon
        self.header_label = QLabel("Resulting Table Preview (Before Running)")
        header_font = QFont("Segoe UI", 10, QFont.Bold)
        self.header_label.setFont(header_font)
        self.header_label.setStyleSheet("color: #1f6feb; margin-top: 10px;")
        header_layout.addWidget(self.header_label)
        
        header_layout.addStretch()
        
        # On and Off Toggle checkbox
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
        
        # Stats/Matching summary label
        self.stats_label = QLabel("Please configure all input parameters to generate a preview.")
        self.stats_label.setStyleSheet("color: #555; font-style: italic;")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        
        # Table Widget setup
        self.table = QTableWidget()
        self.table.setColumnCount(13)
        self.table.setHorizontalHeaderLabels([
            "fid", "map_uuid", "geocode", "region", "province", "city_mun", 
            "barangay", "code", "remarks", "source", "hhcount", "bldgcount", "sy"
        ])
        
        # Table styling & layout constraints
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(180)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.table.setStyleSheet("""
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
        """)
        layout.addWidget(self.table)
        
        # Action button bar
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
        
        return self.container

    def on_toggle_changed(self, state):
        is_checked = (state == Qt.Checked)
        self.table.setVisible(is_checked)
        self.stats_label.setVisible(is_checked)
        self.refresh_btn.setVisible(is_checked)
        if is_checked:
            self.generate_preview()


    def postInitialize(self, wrappers):
        super().postInitialize(wrappers)
        
        # Locate all input wrappers in dialog
        for w in wrappers:
            name = w.parameterDefinition().name()
            if name == "INPUT":
                self.input_wrapper = w
            elif name == "INPUT_FIELD":
                self.input_field_wrapper = w
            elif name == "TABLE":
                self.table_wrapper = w
            elif name == "REGION":
                self.region_wrapper = w
            elif name == "PROVINCE":
                self.province_wrapper = w
            elif name == "CITY_MUN":
                self.city_mun_wrapper = w
            elif name == "SOURCE":
                self.source_wrapper = w
            elif name == "SOURCE_YEAR":
                self.source_year_wrapper = w

        # Connect sibling wrappers' value changed events to dynamically refresh preview
        for w in [self.input_wrapper, self.input_field_wrapper, self.table_wrapper, 
                  self.region_wrapper, self.province_wrapper, self.city_mun_wrapper,
                  self.source_wrapper, self.source_year_wrapper]:
            if w:
                try:
                    w.widgetValueHasChanged.connect(self.trigger_auto_refresh)
                except Exception:
                    pass

        # Trigger initial preview generation
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
            
        layer = QgsProject.instance().mapLayer(str(layer_val))
        if not layer or not layer.isValid():
            if os.path.exists(str(layer_val)):
                layer = QgsVectorLayer(str(layer_val), "temp_preview", "ogr")
        return layer if (layer and layer.isValid()) else None

    def _find_field_case_insensitive(self, fields, target_name):
        target_norm = target_name.lower().replace("_", "").replace("/", "").replace(" ", "")
        for field in fields:
            name_norm = field.name().lower().replace("_", "").replace("/", "").replace(" ", "")
            if name_norm == target_norm:
                return field.name()
        return None

    def _get_psgc_field_mapping(self, fields):
        mapping = {}
        for key, aliases in {
            "geocode": ["geocode", "code", "psgc", "psgc_code", "geocode_code"],
            "region": ["region", "reg"],
            "province": ["province", "prov"],
            "city_mun": ["city_mun", "city/municipality", "municipality", "city", "citymun"],
            "barangay": ["barangay", "bgy", "brgy"]
        }.items():
            for name in aliases:
                f = self._find_field_case_insensitive(fields, name)
                if f:
                    mapping[key] = f
                    break
        return mapping

    def generate_preview(self):
        if not self.table:
            return
            
        if hasattr(self, "toggle_checkbox") and not self.toggle_checkbox.isChecked():
            return
            
        self.table.setRowCount(0)
        # Reset unmatched feature list for this preview run
        self._unmatched_features = []
        
        # Get selected layer/field inputs
        lgu_layer = self._get_selected_layer(self.input_wrapper)
        table_layer = self._get_selected_layer(self.table_wrapper)
        field_val = self._get_wrapper_value(self.input_field_wrapper)
        
        if not lgu_layer:
            self.stats_label.setText("📋 <i>LGU Boundary layer is not selected.</i>")
            self.stats_label.setStyleSheet("color: #777; font-style: italic;")
            return
            
        if not field_val:
            self.stats_label.setText("📋 <i>LGU Join Field is not selected.</i>")
            self.stats_label.setStyleSheet("color: #777; font-style: italic;")
            return
            
        if not table_layer:
            self.stats_label.setText("📋 <i>PSGC table layer is not selected.</i>")
            self.stats_label.setStyleSheet("color: #777; font-style: italic;")
            return

        region_filter = str(self._get_wrapper_value(self.region_wrapper)).strip().lower()
        province_filter = str(self._get_wrapper_value(self.province_wrapper)).strip().lower()
        city_mun_filter = str(self._get_wrapper_value(self.city_mun_wrapper)).strip().lower()
        source_val = str(self._get_wrapper_value(self.source_wrapper))
        sy_val = str(self._get_wrapper_value(self.source_year_wrapper))
        
        # Standardize empty/all filters
        if region_filter == "all regions" or not region_filter:
            region_filter = ""
        if province_filter == "all provinces" or not province_filter:
            province_filter = ""
        if city_mun_filter == "all cities/municipalities" or not city_mun_filter:
            city_mun_filter = ""

        # Validate input join field
        if lgu_layer.fields().indexOf(field_val) == -1:
            self.stats_label.setText(f"Field '{field_val}' not found in LGU boundary layer.")
            self.stats_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
            return

        # Map fields in PSGC table
        psgc_fields = table_layer.fields()
        mapping = self._get_psgc_field_mapping(psgc_fields)
        
        required_cols = ["barangay", "geocode", "region", "province", "city_mun"]
        for col in required_cols:
            if col not in mapping or mapping[col] is None:
                self.stats_label.setText(
                    f"Missing column representing '{col}' in the PSGC table. "
                    "Ensure headers for Geocode, Region, Province, City/Municipality, and Barangay exist."
                )
                self.stats_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
                return

        # Detect geocode length system
        max_digits_len = 9
        for feat in table_layer.getFeatures():
            raw_code = feat.attribute(mapping["geocode"])
            if raw_code is not None and raw_code != NULL:
                s = str(raw_code).strip()
                if s.endswith(".0"):
                    s = s[:-2]
                s = "".join(c for c in s if c.isdigit())
                if len(s) > max_digits_len:
                    max_digits_len = len(s)
                    break

        # Filter and index PSGC spreadsheet rows
        psgc_lookup = {}
        normalized_psgc_keys = []
        
        actual_brgy_col = mapping["barangay"]
        actual_code_col = mapping["geocode"]
        actual_reg_col = mapping["region"]
        actual_prov_col = mapping["province"]
        actual_citymun_col = mapping["city_mun"]
        
        for feat in table_layer.getFeatures():
            reg_val = str(feat.attribute(actual_reg_col)).strip()
            prov_val = str(feat.attribute(actual_prov_col)).strip()
            citymun_val = str(feat.attribute(actual_citymun_col)).strip()
            brgy_val = str(feat.attribute(actual_brgy_col)).strip()
            
            raw_code = feat.attribute(actual_code_col)
            if raw_code is None or raw_code == NULL:
                code_val = ""
            else:
                code_val = str(raw_code).strip()
                if code_val.endswith(".0"):
                    code_val = code_val[:-2]
                code_val = "".join(c for c in code_val if c.isdigit())
                if code_val:
                    code_val = code_val.zfill(max_digits_len)
            
            if region_filter and reg_val.lower() != region_filter:
                continue
            if province_filter and prov_val.lower() != province_filter:
                continue
            if city_mun_filter and citymun_val.lower() != city_mun_filter:
                continue
                
            exact_key = brgy_val.lower().strip()
            norm_key = normalize_barangay_name(brgy_val)
            
            psgc_data = {
                "geocode": code_val,
                "region": reg_val,
                "province": prov_val,
                "city_mun": citymun_val,
                "barangay": brgy_val
            }
            
            if exact_key:
                psgc_lookup[exact_key] = psgc_data
            if norm_key:
                psgc_lookup[norm_key] = psgc_data
                if norm_key not in normalized_psgc_keys:
                    normalized_psgc_keys.append(norm_key)

        # Loop LGU layer features and calculate matches/populate preview rows
        matched_count = 0
        total_features = lgu_layer.featureCount()
        preview_rows = []
        
        for current, feature in enumerate(lgu_layer.getFeatures()):
            lgu_key_val = feature.attribute(field_val)
            lgu_key_str = str(lgu_key_val).strip() if lgu_key_val is not None and lgu_key_val != NULL else ""
            
            exact_key = lgu_key_str.lower().strip()
            norm_key = normalize_barangay_name(lgu_key_str)
            
            psgc_data = None
            if exact_key in psgc_lookup:
                psgc_data = psgc_lookup[exact_key]
            elif norm_key in psgc_lookup:
                psgc_data = psgc_lookup[norm_key]
            elif norm_key and normalized_psgc_keys:
                close_matches = difflib.get_close_matches(norm_key, normalized_psgc_keys, n=1, cutoff=0.75)
                if close_matches:
                    psgc_data = psgc_lookup[close_matches[0]]
                    
            if psgc_data:
                matched_count += 1
                geocode = psgc_data["geocode"]
                if geocode:
                    geocode = geocode[2:] + "000000"
                region = psgc_data["region"]
                province = psgc_data["province"]
                city_mun = psgc_data["city_mun"]
                barangay = psgc_data["barangay"]
            else:
                geocode = ""
                region = ""
                province = ""
                city_mun = ""
                barangay = ""
                # Record this feature as unmatched for later export
                self._unmatched_features.append(feature)
                
            fid_val = current + 1
            uuid_val = "Generating..."
            
            row_data = [
                str(fid_val),
                str(uuid_val),
                geocode,
                region,
                province,
                city_mun,
                barangay,
                "1003",
                "",
                source_val,
                "NULL",
                "NULL",
                sy_val
            ]
            
            if len(preview_rows) < 15:
                preview_rows.append(row_data)

        # Set rows count and fill elements
        self.table.setRowCount(len(preview_rows))
        for row_idx, row_data in enumerate(preview_rows):
            is_matched = bool(row_data[2])
            
            for col_idx, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                if col_idx in [0, 7, 10, 11]:
                    item.setTextAlignment(Qt.AlignCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                
                # Apply dynamic, rich styling to cells
                if not is_matched:
                    item.setBackground(QColor("#fff5f5"))
                    item.setForeground(QColor("#cb2431"))
                    if col_idx == 2:
                        item.setText("[No Match Found]")
                else:
                    if col_idx in [2, 3, 4, 5, 6]:
                        item.setBackground(QColor("#f0fff4"))
                        item.setForeground(QColor("#22863a"))
                
                self.table.setItem(row_idx, col_idx, item)

        # Update stats text color-coded dynamically
        match_pct = (matched_count / total_features * 100) if total_features else 0
        stats_text = (
            f"<b>Matching Summary:</b> {matched_count} out of {total_features} features matched "
            f"(<b>{match_pct:.1f}%</b> accuracy). "
            f"Showing preview of first {len(preview_rows)} features."
        )
        self.stats_label.setText(stats_text)
        if match_pct == 100:
            self.stats_label.setStyleSheet("color: #28a745; font-weight: bold; font-size: 11px;")
        elif match_pct >= 80:
            self.stats_label.setStyleSheet("color: #0366d6; font-weight: bold; font-size: 11px;")
        else:
            self.stats_label.setStyleSheet("color: #d93f0b; font-weight: bold; font-size: 11px;")

        # Store unmatched feature count for user reference (optional)
        self.unmatched_count = len(self._unmatched_features)

    def value(self):
        return "preview"

    def setValue(self, value):
        pass



class UpdateLguPsgcMetadataAlgorithm(QgsProcessingAlgorithm):
    """
    This algorithm enriches an LGU (Local Government Unit) boundary polygon layer 
    by joining and updating its attributes using a specific PSGC (Philippine Standard 
    Geographic Code) xlsx file or table.

    It performs a high-performance attribute join, dynamically expanding the 
    LGU layer's schema to include new columns from the PSGC spreadsheet. It 
    also updates the output layer's official QGIS Layer Metadata (Title, Abstract, etc.) 
    if specific metadata columns are present in the table.
    """

    # Constants used to refer to parameters and outputs.
    INPUT = "INPUT"
    INPUT_FIELD = "INPUT_FIELD"
    TABLE = "TABLE"
    REGION = "REGION"
    PROVINCE = "PROVINCE"
    CITY_MUN = "CITY_MUN"
    SOURCE = "SOURCE"
    SOURCE_YEAR = "SOURCE_YEAR"
    OUTPUT_DIR = "OUTPUT_DIR"
    OUTPUT = "OUTPUT"
    UNMATCHED = "UNMATCHED"

    def name(self) -> str:
        """
        Returns the algorithm name, used for identifying the algorithm.
        """
        return "update_lgu_with_psgc"

    def displayName(self) -> str:
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return "Update Metadata"

    def group(self) -> str:
        """
        Returns the name of the group this algorithm belongs to.
        """
        return "GMD Toolkits"

    def groupId(self) -> str:
        """
        Returns the unique ID of the group this algorithm belongs to.
        """
        return "gmdtoolkits"

    def shortHelpString(self) -> str:
        """
        Returns a helper string for the algorithm explaining its parameters.
        """
        return (
            "This algorithm enriches an input LGU boundary polygon layer using a specific PSGC xlsx table.\n\n"
            "Parameters:\n"
            "- LGU boundary layer (polygon): The spatial polygon layer whose attributes you wish to update.\n"
            "- LGU join field (from dropdown): The field in the LGU layer containing Barangay names to match.\n"
            "- PSGC xlsx file / table: A loaded spreadsheet containing PSGC geocodes and metadata.\n"
            "- Region filter (from dropdown): Populated automatically from unique Region values in the PSGC sheet.\n"
            "- Province filter (from dropdown): Automatically updates in real-time to list only the provinces belonging to your selected region.\n"
            "- City/Municipality filter (from dropdown): Automatically updates in real-time to list only the cities/municipalities in your selected province.\n"
            "- Output directory for permanent layer (folder): The directory where the final enriched layer will automatically be saved as a permanent GeoPackage file.\n\n"
            "Features:\n"
            "1. Scans the active QGIS project for any loaded layer with 'PSGC' in its name, extracting unique values "
            "to populate the Region, Province, and City/Municipality dropdown lists dynamically.\n"
            "2. Filters the PSGC table by selected region, province, and city/municipality beforehand.\n"
            "3. Performs a fast memory-based join matching the selected LGU field with the PSGC 'barangay' field.\n"
            "4. Generates 1-indexed feature IDs (fid) and unique Map UUIDs (map_uuid).\n"
            "5. Structurizes the output layer with a strict schema (geocode, region, province, city_mun, barangay, "
            "code, remarks, source, hhcount, bldgcount, sy).\n"
            "6. Automatically reprojects geometries and coordinates to WGS 84 (EPSG:4326) on-the-fly.\n"
            "7. Dynamically renames the loaded output layer in QGIS using the 5-digit code derived from the matched geocode followed by '_bgy' (e.g. '14000_bgy').\n"
            "8. Automatically saves a permanent copy of the updated LGU layer in the specified output directory as a GeoPackage with the same custom name (e.g., '14000_bgy.gpkg').\n"
            "Support Email: <b>gmd.support@psa.gov.ph</b>\n"
            "Author: CPA\n"
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        """
        Here we define the inputs and output of the algorithm.
        """
        # We add the input LGU boundary polygon layer.
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                "LGU boundary layer (polygon)",
                [QgsProcessing.SourceType.TypeVectorPolygon],
            )
        )

        # The join field in the LGU boundary polygon layer.
        self.addParameter(
            QgsProcessingParameterField(
                self.INPUT_FIELD,
                "LGU join field (from dropdown)",
                parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.Any,
            )
        )

        # We add the input PSGC xlsx file or table layer.
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.TABLE,
                "PSGC xlsx file / table",
                [QgsProcessing.SourceType.TypeVector],
            )
        )

        # Region filter parameter (String, but rendered as Dropdown via custom WidgetWrapper)
        region_param = QgsProcessingParameterString(
            self.REGION,
            "Region filter (from dropdown)",
            defaultValue="All Regions",
        )
        region_param.setMetadata({"widget_wrapper": {"class": PsgcFilterWidgetWrapper}})
        self.addParameter(region_param)

        # Province filter parameter (String, but rendered as Dropdown via custom WidgetWrapper)
        province_param = QgsProcessingParameterString(
            self.PROVINCE,
            "Province filter (from dropdown)",
            defaultValue="All Provinces",
        )
        province_param.setMetadata({"widget_wrapper": {"class": PsgcFilterWidgetWrapper}})
        self.addParameter(province_param)

        # City/Municipality filter parameter (String, but rendered as Dropdown via custom WidgetWrapper)
        city_mun_param = QgsProcessingParameterString(
            self.CITY_MUN,
            "City/Municipality filter (from dropdown)",
            defaultValue="All Cities/Municipalities",
        )
        city_mun_param.setMetadata({"widget_wrapper": {"class": PsgcFilterWidgetWrapper}})
        self.addParameter(city_mun_param)

        # Source input parameter (String)
        self.addParameter(
            QgsProcessingParameterString(
                self.SOURCE,
                "Source (manually typed)",
                defaultValue="LGU",
            )
        )

        # Source Year input parameter (String)
        self.addParameter(
            QgsProcessingParameterString(
                self.SOURCE_YEAR,
                "Source Year (manually typed)",
                defaultValue="2026",
            )
        )

        # Output directory for permanent layer parameter (Folder)
        self.addParameter(
            QgsProcessingParameterFile(
                self.OUTPUT_DIR,
                "Output directory for permanent layer",
                behavior=QgsProcessingParameterFile.Folder,
                defaultValue=r"C:\PSA-GIS\Quezon\Project 1MAP\2_Updating of Boundary\3_Map Archive\1_Processing",
                optional=True
            )
        )

        # Preview Parameter
        # Show in normal Processing dialog
        # Hide completely in Batch Processing dialog

        is_batch_dialog = False

        try:
            stack_text = "\n".join(
                [frame.function.lower() for frame in inspect.stack()]
            )

            if "batch" in stack_text:
                is_batch_dialog = True

        except Exception:
            pass

        if not is_batch_dialog:
            preview_param = QgsProcessingParameterString(
                "PREVIEW",
                "Result Preview",
                defaultValue="",
                optional=True,
            )

            preview_param.setMetadata({
                "widget_wrapper": {
                    "class": TablePreviewWidgetWrapper
                }
            })

            self.addParameter(preview_param)

        # The output enriched LGU polygon layer reprojected to EPSG:4326.
        self.addParameter(
            QgsProcessingParameterFeatureSink(self.OUTPUT, "Updated LGU layer (EPSG:4326)")
        )

        # Unmatched features temporary output layer.
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.UNMATCHED,
                "Unmatched LGU features (temporary)",
                optional=True
            )
        )

    def _find_field_case_insensitive(self, fields: QgsFields, target_name: str) -> Optional[str]:
        """
        Finds a field name in a QgsFields object by comparing normalized names case-insensitively.
        """
        target_norm = target_name.lower().replace("_", "").replace("/", "").replace(" ", "")
        for field in fields:
            name_norm = field.name().lower().replace("_", "").replace("/", "").replace(" ", "")
            if name_norm == target_norm:
                return field.name()
        return None

    def _get_psgc_field_mapping(self, fields: QgsFields) -> dict[str, str]:
        """
        Maps standard field keys (geocode, region, province, city_mun, barangay)
        to the actual field names found in the PSGC table.
        """
        mapping = {}
        
        # 1. Geocode
        for name in ["geocode", "code", "psgc", "psgc_code", "geocode_code"]:
            f = self._find_field_case_insensitive(fields, name)
            if f:
                mapping["geocode"] = f
                break
                
        # 2. Region
        for name in ["region", "reg"]:
            f = self._find_field_case_insensitive(fields, name)
            if f:
                mapping["region"] = f
                break
                
        # 3. Province
        for name in ["province", "prov"]:
            f = self._find_field_case_insensitive(fields, name)
            if f:
                mapping["province"] = f
                break
                
        # 4. City/Municipality
        for name in ["city_mun", "city/municipality", "municipality", "city", "citymun"]:
            f = self._find_field_case_insensitive(fields, name)
            if f:
                mapping["city_mun"] = f
                break
                
        # 5. Barangay
        for name in ["barangay", "bgy", "brgy"]:
            f = self._find_field_case_insensitive(fields, name)
            if f:
                mapping["barangay"] = f
                break
                
        return mapping

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        """
        Here is where the processing and feature join takes place.
        """
        # Retrieve parameter objects
        source = self.parameterAsSource(parameters, self.INPUT, context)
        table_source = self.parameterAsSource(parameters, self.TABLE, context)
        input_field = self.parameterAsString(parameters, self.INPUT_FIELD, context)
        
        # Retrieve selected string filters directly from the parameters
        region_filter = self.parameterAsString(parameters, self.REGION, context).strip().lower()
        province_filter = self.parameterAsString(parameters, self.PROVINCE, context).strip().lower()
        city_mun_filter = self.parameterAsString(parameters, self.CITY_MUN, context).strip().lower()
        source_meta_val = self.parameterAsString(parameters, self.SOURCE, context)
        sy_val = self.parameterAsString(parameters, self.SOURCE_YEAR, context)
        output_dir = self.parameterAsString(parameters, self.OUTPUT_DIR, context)
        
        # Map "All X" and empty filters to empty string (no filter)
        if region_filter == "all regions" or not region_filter:
            region_filter = ""
        if province_filter == "all provinces" or not province_filter:
            province_filter = ""
        if city_mun_filter == "all cities/municipalities" or not city_mun_filter:
            city_mun_filter = ""

        # Validate inputs
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        if table_source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.TABLE))

        # Check column mapping in PSGC fields
        psgc_fields = table_source.fields()
        mapping = self._get_psgc_field_mapping(psgc_fields)
        
        required_cols = ["barangay", "geocode", "region", "province", "city_mun"]
        for col in required_cols:
            if col not in mapping or mapping[col] is None:
                raise QgsProcessingException(
                    f"Could not find a column representing '{col}' in the PSGC table. "
                    f"Please make sure your Excel sheet contains columns for Geocode, Region, Province, City/Municipality, and Barangay."
                )

        # Index and filter the PSGC table
        feedback.pushInfo("Filtering and indexing PSGC spreadsheet records...")
        
        # Detect the geocode length system (9-digit vs 10-digit) by scanning the table
        max_digits_len = 9
        for feat in table_source.getFeatures():
            raw_code = feat.attribute(mapping["geocode"])
            if raw_code is not None and raw_code != NULL:
                s = str(raw_code).strip()
                if s.endswith(".0"):
                    s = s[:-2]
                s = "".join(c for c in s if c.isdigit())
                if len(s) > max_digits_len:
                    max_digits_len = len(s)
                    break  # Found 10-digit, stop early
        
        psgc_lookup = {}
        normalized_psgc_keys = []
        self.geocode_prefix = ""
        
        actual_brgy_col = mapping["barangay"]
        actual_code_col = mapping["geocode"]
        actual_reg_col = mapping["region"]
        actual_prov_col = mapping["province"]
        actual_citymun_col = mapping["city_mun"]
        
        filtered_count = 0
        total_table_count = table_source.featureCount()
        
        for feat in table_source.getFeatures():
            if feedback.isCanceled():
                break
                
            reg_val = str(feat.attribute(actual_reg_col)).strip()
            prov_val = str(feat.attribute(actual_prov_col)).strip()
            citymun_val = str(feat.attribute(actual_citymun_col)).strip()
            brgy_val = str(feat.attribute(actual_brgy_col)).strip()
            
            raw_code = feat.attribute(actual_code_col)
            if raw_code is None or raw_code == NULL:
                code_val = ""
            else:
                code_val = str(raw_code).strip()
                if code_val.endswith(".0"):
                    code_val = code_val[:-2]
                code_val = "".join(c for c in code_val if c.isdigit())
                if code_val:
                    code_val = code_val.zfill(max_digits_len)
            
            # Apply filters (case-insensitive, optional if not specified)
            if region_filter and reg_val.lower() != region_filter:
                continue
            if province_filter and prov_val.lower() != province_filter:
                continue
            if city_mun_filter and citymun_val.lower() != city_mun_filter:
                continue
                
            filtered_count += 1
            
            # Set the geocode prefix from the first matched filtered geocode
            if code_val and not self.geocode_prefix and len(code_val) >= 7:
                self.geocode_prefix = code_val[:7]
            
            # Store both exact trimmed key and normalized key to allow robust fallbacks
            exact_key = brgy_val.lower().strip()
            norm_key = normalize_barangay_name(brgy_val)
            
            psgc_data = {
                "geocode": code_val,
                "region": reg_val,
                "province": prov_val,
                "city_mun": citymun_val,
                "barangay": brgy_val
            }
            
            if exact_key:
                psgc_lookup[exact_key] = psgc_data
            if norm_key:
                psgc_lookup[norm_key] = psgc_data
                if norm_key not in normalized_psgc_keys:
                    normalized_psgc_keys.append(norm_key)
            
        feedback.pushInfo(
            f"Filtered PSGC table from {total_table_count} down to {filtered_count} records "
            f"matching Region: '{region_filter}', Province: '{province_filter}', City/Mun: '{city_mun_filter}'."
        )

        # Build output fields schema strictly according to requirements
        output_fields = QgsFields()
        output_fields.append(QgsField("fid", QVariant.Int))
        output_fields.append(QgsField("map_uuid", QVariant.String, len=36))
        output_fields.append(QgsField("geocode", QVariant.String, len=50))
        output_fields.append(QgsField("region", QVariant.String, len=100))
        output_fields.append(QgsField("province", QVariant.String, len=100))
        output_fields.append(QgsField("city_mun", QVariant.String, len=100))
        output_fields.append(QgsField("barangay", QVariant.String, len=100))
        output_fields.append(QgsField("code", QVariant.String, len=50))
        output_fields.append(QgsField("remarks", QVariant.String, len=255))
        output_fields.append(QgsField("source", QVariant.String, len=100))
        output_fields.append(QgsField("hhcount", QVariant.Int))
        output_fields.append(QgsField("bldgcount", QVariant.Int))
        output_fields.append(QgsField("sy", QVariant.String, len=10))

        # Define WGS 84 Target CRS
        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        
        # Check if reprojection is needed
        reproject = source.sourceCrs().authid() != "EPSG:4326"
        transform = None
        if reproject:
            transform = QgsCoordinateTransform(
                source.sourceCrs(),
                target_crs,
                context.transformContext()
            )
            feedback.pushInfo(f"Input CRS is {source.sourceCrs().authid()}. Enabling automatic reprojection to EPSG:4326...")
        else:
            feedback.pushInfo("Input CRS is already EPSG:4326. Reprojection is bypassed.")

        # Intercept output parameter if permanent directory is specified
        if output_dir:
            output_dir = output_dir.strip()
            if output_dir:
                custom_name = ""
                if hasattr(self, "geocode_prefix") and self.geocode_prefix:
                    custom_name = f"{self.geocode_prefix[2:]}_bgy"
                else:
                    custom_name = "Updated_LGU"
                
                # Ensure the folder exists
                if not os.path.exists(output_dir):
                    try:
                        os.makedirs(output_dir)
                        feedback.pushInfo(f"Created permanent output directory: {output_dir}")
                    except Exception as e:
                        feedback.pushInfo(f"Warning: Could not create output directory '{output_dir}': {str(e)}")
                
                output_file_path = os.path.join(output_dir, f"{custom_name}.gpkg")
                output_file_path = os.path.normpath(output_file_path).replace("\\", "/")
                
                # Delete existing file if it exists to prevent conflicts/appending
                if os.path.exists(output_file_path):
                    try:
                        os.remove(output_file_path)
                        feedback.pushInfo(f"Existing GeoPackage '{output_file_path}' deleted to prevent merge issues.")
                    except Exception as e:
                        feedback.pushInfo(f"Warning: Could not delete existing GeoPackage '{output_file_path}': {str(e)}")
                
                parameters[self.OUTPUT] = output_file_path
                feedback.pushInfo(f"Output layer will automatically be saved permanently to: {output_file_path}")

        # Create output sink with EPSG:4326
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            output_fields,
            source.wkbType(),
            target_crs,
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        # Store the destination ID for post-processing metadata updates
        self.dest_id = dest_id

        # Setup unmatched sink if parameter is specified
        unmatched_sink = None
        unmatched_dest_id = None
        unmatched_fields = QgsFields()
        if self.UNMATCHED in parameters and parameters[self.UNMATCHED] is not None:
            unmatched_fields = QgsFields(source.fields())
            
            # Columns to add if not present
            new_cols = [
                ("fid", QVariant.Int, 0),
                ("map_uuid", QVariant.String, 36),
                ("geocode", QVariant.String, 50),
                ("region", QVariant.String, 100),
                ("province", QVariant.String, 100),
                ("city_mun", QVariant.String, 100),
                ("barangay", QVariant.String, 100),
                ("code", QVariant.String, 50),
                ("remarks", QVariant.String, 255),
                ("source", QVariant.String, 100),
                ("hhcount", QVariant.Int, 0),
                ("bldgcount", QVariant.Int, 0),
                ("sy", QVariant.String, 10)
            ]
            
            for col_name, col_type, col_len in new_cols:
                if unmatched_fields.indexFromName(col_name) == -1:
                    if col_len > 0:
                        unmatched_fields.append(QgsField(col_name, col_type, len=col_len))
                    else:
                        unmatched_fields.append(QgsField(col_name, col_type))

            (unmatched_sink, unmatched_dest_id) = self.parameterAsSink(
                parameters,
                self.UNMATCHED,
                context,
                unmatched_fields,
                source.wkbType(),
                target_crs,
            )
            
        self.unmatched_dest_id = unmatched_dest_id

        # Loop over features and populate values
        total_features = source.featureCount()
        progress_step = 100.0 / total_features if total_features else 0
        features = source.getFeatures()
        matched_count = 0
        
        feedback.pushInfo("Processing and reprojecting LGU polygon boundaries...")
        for current, feature in enumerate(features):
            if feedback.isCanceled():
                break

            lgu_key_val = feature.attribute(input_field)
            lgu_key_str = str(lgu_key_val).strip() if lgu_key_val is not None and lgu_key_val != NULL else ""
            
            exact_key = lgu_key_str.lower().strip()
            norm_key = normalize_barangay_name(lgu_key_str)
            
            psgc_data = None
            if exact_key in psgc_lookup:
                psgc_data = psgc_lookup[exact_key]
            elif norm_key in psgc_lookup:
                psgc_data = psgc_lookup[norm_key]
            elif norm_key and normalized_psgc_keys:
                # 3rd Try Fallback: Fuzzy Match using difflib
                close_matches = difflib.get_close_matches(norm_key, normalized_psgc_keys, n=1, cutoff=0.75)
                if close_matches:
                    psgc_data = psgc_lookup[close_matches[0]]
                    feedback.pushDebugInfo(
                        f"Fuzzy matched LGU Barangay '{lgu_key_str}' to PSGC Barangay '{psgc_data['barangay']}' (normalized: '{close_matches[0]}')"
                    )

            if psgc_data:
                matched_count += 1
                geocode = psgc_data["geocode"]
                if geocode:
                    geocode = geocode[2:] + "000000"
                region = psgc_data["region"]
                province = psgc_data["province"]
                city_mun = psgc_data["city_mun"]
                barangay = psgc_data["barangay"]
                
                # Create fid and map_uuid
                fid_val = current + 1
                uuid_val = str(uuid.uuid4())
                
                # Prepare exact attribute list
                new_attributes = [
                    fid_val,        # fid
                    uuid_val,       # map_uuid
                    geocode,        # geocode
                    region,         # region
                    province,       # province
                    city_mun,       # city_mun
                    barangay,       # barangay
                    "1003",         # code
                    "",             # remarks
                    source_meta_val, # source
                    None,           # hhcount
                    None,           # bldgcount
                    sy_val          # sy
                ]

                # Re-project geometry on-the-fly
                new_feature = QgsFeature()
                geom = feature.geometry()
                if reproject and transform:
                    geom.transform(transform)
                new_feature.setGeometry(geom)
                new_feature.setAttributes(new_attributes)
                
                sink.addFeature(new_feature, QgsFeatureSink.Flag.FastInsert)
            else:
                if unmatched_sink is not None:
                    # Construct matching attribute list for unmatched_fields
                    unmatched_attrs = []
                    for fld in unmatched_fields:
                        orig_idx = source.fields().indexFromName(fld.name())
                        if orig_idx != -1:
                            unmatched_attrs.append(feature.attribute(orig_idx))
                        else:
                            # It is a new field!
                            fld_name = fld.name()
                            if fld_name == "fid":
                                unmatched_attrs.append(current + 1)
                            elif fld_name == "map_uuid":
                                unmatched_attrs.append(str(uuid.uuid4()))
                            elif fld_name == "code":
                                unmatched_attrs.append("1003")
                            elif fld_name == "source":
                                unmatched_attrs.append(source_meta_val)
                            elif fld_name == "sy":
                                unmatched_attrs.append(sy_val)
                            elif fld_name in ["hhcount", "bldgcount"]:
                                unmatched_attrs.append(None)
                            else:
                                unmatched_attrs.append("")

                    # Re-project geometry on-the-fly
                    new_feature = QgsFeature()
                    geom = feature.geometry()
                    if reproject and transform:
                        geom.transform(transform)
                    new_feature.setGeometry(geom)
                    new_feature.setAttributes(unmatched_attrs)
                    
                    unmatched_sink.addFeature(new_feature, QgsFeatureSink.Flag.FastInsert)

            feedback.setProgress(int(current * progress_step))

        feedback.pushInfo(
            f"Successfully processed {total_features} features. Matched {matched_count} LGU boundaries "
            f"with PSGC barangay records. Output layer reprojected to EPSG:4326."
        )
        
        ret = {self.OUTPUT: dest_id}
        if unmatched_dest_id is not None:
            ret[self.UNMATCHED] = unmatched_dest_id
        return ret

    def postProcessAlgorithm(
        self,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        """
        Runs on the main thread after processAlgorithm finishes. This is thread-safe for 
        modifying layer-level settings such as layer metadata in the active project.
        """
        layer = QgsProcessingUtils.mapLayerFromString(self.dest_id, context)

        # 1. Determine custom name from geocode prefix if available
        custom_name = ""
        if hasattr(self, "geocode_prefix") and self.geocode_prefix:
            custom_name = f"{self.geocode_prefix[2:]}_bgy"

        primary_name = ""
        if layer and layer.isValid():
            # Try to persist the updated metadata as sidecar default (.qmd file)
            try:
                layer.saveDefaultMetadata()
            except Exception as e:
                # Gracefully catch exceptions (e.g. for memory layers which have no physical sidecar path)
                feedback.pushDebugInfo(f"Note: Could not write sidecar .qmd metadata (expected for memory layers): {str(e)}")

            # Rename the layer using the geocode if not already determined
            if not custom_name:
                # Fallback to feature scan
                geocode_val = ""
                idx = layer.fields().indexOf("geocode")
                if idx != -1:
                    for feat in layer.getFeatures():
                        val = str(feat.attribute(idx)).strip()
                        if val and val != "NULL" and len(val) >= 7:
                            geocode_val = val[:7]
                            break
                if geocode_val:
                    custom_name = f"{geocode_val[2:]}_bgy"

            if custom_name:
                layer.setName(custom_name)
                primary_name = custom_name
            else:
                primary_name = layer.name()
        else:
            if custom_name:
                primary_name = custom_name
            else:
                primary_name = "Updated_LGU"

        # Apply name to QGIS load details for legend loading
        if custom_name and context.willLoadLayerOnCompletion(self.dest_id):
            details = context.layerToLoadOnCompletionDetails(self.dest_id)
            details.name = custom_name

        # Safeguard: Ensure the output layer is loaded in the layers panel
        # If QGIS is not scheduled to load it automatically, we load and add it manually
        if not context.willLoadLayerOnCompletion(self.dest_id):
            already_loaded = False
            target_source = self.dest_id.split("|")[0]
            for l in QgsProject.instance().mapLayers().values():
                if l.source().split("|")[0] == target_source:
                    already_loaded = True
                    if custom_name:
                        l.setName(custom_name)
                    break
            
            if not already_loaded:
                layer_name = custom_name if custom_name else "Updated_LGU"
                new_layer = QgsVectorLayer(self.dest_id, layer_name, "ogr")
                if new_layer and new_layer.isValid():
                    try:
                        new_layer.saveDefaultMetadata()
                    except Exception:
                        pass
                    QgsProject.instance().addMapLayer(new_layer)
                    feedback.pushInfo(f"Safeguard: Manually added output layer '{layer_name}' to the Layers Panel.")

        ret = {self.OUTPUT: self.dest_id}
        if hasattr(self, "unmatched_dest_id") and self.unmatched_dest_id is not None:
            ret[self.UNMATCHED] = self.unmatched_dest_id
            unmatched_layer = QgsProcessingUtils.mapLayerFromString(self.unmatched_dest_id, context)
            if unmatched_layer and unmatched_layer.isValid():
                unmatched_name = f"{primary_name}_unmatched"
                if context.willLoadLayerOnCompletion(self.unmatched_dest_id):
                    details = context.layerToLoadOnCompletionDetails(self.unmatched_dest_id)
                    details.name = unmatched_name
                unmatched_layer.setName(unmatched_name)
            else:
                if context.willLoadLayerOnCompletion(self.unmatched_dest_id):
                    details = context.layerToLoadOnCompletionDetails(self.unmatched_dest_id)
                    details.name = f"{primary_name}_unmatched"

        return ret

    def createInstance(self):
        return self.__class__()
