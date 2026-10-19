# -*- coding: utf-8 -*-
"""
Split EA Dialog
----------------
Modal pop-up panel for splitting EA polygons (delineated_ea) using proposed cut lines (eadel_update).
Directly updates the selected polygon layer in-place with the split features,
and recalculates 'hh_count' (from est_hhcount of building points) and 'bldg_count' within each split polygon.
"""

import os
import sys
import math
from typing import Optional, Dict, Any, List, Tuple

from qgis.PyQt.QtCore import Qt, QObject, pyqtSignal, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QFrame,
    QMessageBox,
    QApplication,
)
from qgis.PyQt.QtGui import QFont
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingFeedback,
    QgsField,
    QgsMapLayerProxyModel,
    QgsSpatialIndex,
    NULL,
)

from .helpers.constants import create_qgs_field
from qgis.gui import QgsMapLayerComboBox

try:
    import processing
except ImportError:
    processing = None


class SplitEADialog(QDialog):
    """Pop-up dialog to split EA polygons with proposed cut lines and update layer & counts in-place."""

    def __init__(
        self,
        parent=None,
        default_output_dir: str = "",
        default_geocode: str = "",
        default_bldg_layer: Optional[QgsVectorLayer] = None,
        default_min_hh: int = 99,
        default_poly_layer: Optional[QgsVectorLayer] = None,
        default_line_layer: Optional[QgsVectorLayer] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Run Delineation - Split EA Polygons")
        self.setMinimumSize(560, 680)
        self.resize(620, 720)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )

        self.default_output_dir = default_output_dir or ""
        self.default_geocode = default_geocode or ""
        self.default_bldg_layer = default_bldg_layer
        self.default_min_hh = int(default_min_hh or 99)
        self.default_poly_layer = default_poly_layer
        self.default_line_layer = default_line_layer

        self._prev_poly_layer = None
        self._prev_line_layer = None
        self._poly_user_toggled = False
        self._line_user_toggled = False
        self._bldg_user_selected = False
        self._is_syncing_layers = False

        self._init_ui()
        self._auto_detect_layers()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # ── Header Description ─────────────────────────────────────────────
        header_lbl = QLabel(
            "<b>Split EA Polygons:</b> Select the input EA polygon layer (delineated_ea), proposed cut lines layer (eadel_update), and building point layer. "
            "Running the split will bisect the candidate EAs, update the polygon layer in-place, and recalculate "
            "<b>hh_count</b> (from <i>est_hhcount</i>) and <b>bldg_count</b> for each split EA."
        )
        header_lbl.setWordWrap(True)
        main_layout.addWidget(header_lbl)

        # ── 1. Input Layers Group ──────────────────────────────────────────
        inputs_group = QGroupBox("Input Layers")
        inputs_layout = QVBoxLayout(inputs_group)
        inputs_layout.setContentsMargins(10, 10, 10, 10)
        inputs_layout.setSpacing(4)

        # EA Polygon Layer (delineated_ea)
        inputs_layout.addWidget(QLabel("Target EA Polygon Layer (delineated_ea)*:"))
        self.poly_combo = QgsMapLayerComboBox(self)
        self.poly_combo.setMinimumHeight(28)
        self.poly_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.poly_combo.layerChanged.connect(self._on_layer_selection_changed)
        inputs_layout.addWidget(self.poly_combo)

        poly_sel_row = QHBoxLayout()
        self.poly_selected_chk = QCheckBox("Selected features only (0 selected)")
        self.poly_selected_chk.setMinimumHeight(22)
        self.poly_selected_chk.setToolTip("When checked, only the selected/highlighted polygon features in this layer will be split.")
        self.poly_selected_chk.toggled.connect(self._on_poly_chk_toggled)
        poly_sel_row.addWidget(self.poly_selected_chk)
        poly_sel_row.addStretch()
        inputs_layout.addLayout(poly_sel_row)

        self.poly_status_lbl = QLabel("No polygon layer selected.")
        self.poly_status_lbl.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        inputs_layout.addWidget(self.poly_status_lbl)

        inputs_layout.addSpacing(4)

        # Proposed Cut Lines Layer (eadel_update)
        inputs_layout.addWidget(QLabel("Proposed Cut Lines Layer (eadel_update)*:"))
        self.line_combo = QgsMapLayerComboBox(self)
        self.line_combo.setMinimumHeight(28)
        self.line_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.line_combo.layerChanged.connect(self._on_layer_selection_changed)
        inputs_layout.addWidget(self.line_combo)

        line_sel_row = QHBoxLayout()
        self.line_selected_chk = QCheckBox("Selected features only (0 selected)")
        self.line_selected_chk.setMinimumHeight(22)
        self.line_selected_chk.setToolTip("When checked, only the selected/highlighted cut lines in this layer will be used for splitting.")
        self.line_selected_chk.toggled.connect(self._on_line_chk_toggled)
        line_sel_row.addWidget(self.line_selected_chk)
        line_sel_row.addStretch()
        inputs_layout.addLayout(line_sel_row)

        self.line_status_lbl = QLabel("No line layer selected.")
        self.line_status_lbl.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        inputs_layout.addWidget(self.line_status_lbl)

        inputs_layout.addSpacing(4)

        # Building Points Layer
        inputs_layout.addWidget(QLabel("Building Point Layer (Point)*:"))
        self.bldg_combo = QgsMapLayerComboBox(self)
        self.bldg_combo.setMinimumHeight(28)
        self.bldg_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.bldg_combo.layerChanged.connect(self._on_bldg_layer_changed)
        inputs_layout.addWidget(self.bldg_combo)

        self.bldg_status_lbl = QLabel("No building point layer selected.")
        self.bldg_status_lbl.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        inputs_layout.addWidget(self.bldg_status_lbl)

        main_layout.addWidget(inputs_group)

        # ── 2. Settings Group ──────────────────────────────────────────────
        settings_group = QGroupBox("Splitting Options")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setContentsMargins(10, 10, 10, 10)
        settings_layout.setSpacing(6)

        # Minimum Household Threshold
        min_hh_layout = QHBoxLayout()
        min_hh_layout.addWidget(QLabel("Minimum Household Threshold per EA:"))
        self.min_hh_spin = QSpinBox()
        self.min_hh_spin.setMinimumHeight(26)
        self.min_hh_spin.setRange(1, 99999)
        self.min_hh_spin.setValue(self.default_min_hh)
        self.min_hh_spin.setToolTip(
            "Minimum household count required per EA. If any resulting split part falls below this threshold, the split for that EA is prevented to avoid creating under-threshold EAs."
        )
        min_hh_layout.addWidget(self.min_hh_spin)
        min_hh_layout.addStretch()
        settings_layout.addLayout(min_hh_layout)

        # Line extension tolerance
        tol_layout = QHBoxLayout()
        tol_layout.addWidget(QLabel("Line Endpoint Extension (meters):"))
        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setMinimumHeight(26)
        self.tolerance_spin.setRange(0.0, 50.0)
        self.tolerance_spin.setValue(0.0)
        self.tolerance_spin.setSingleStep(0.5)
        self.tolerance_spin.setToolTip(
            "Optional line endpoint extension distance in meters. Default is 0.0 (strictly cuts where line ends without extending)."
        )
        tol_layout.addWidget(self.tolerance_spin)
        tol_layout.addStretch()
        settings_layout.addLayout(tol_layout)

        main_layout.addWidget(settings_group)

        # ── 3. Execution Logs & Status ─────────────────────────────────────
        self.status_banner = QLabel("Ready to execute split.")
        self.status_banner.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.status_banner.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(self.status_banner)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        main_layout.addWidget(self.progress_bar)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(90)
        self.log_console.setMaximumHeight(140)
        self.log_console.setFont(QFont("Consolas", 8))
        main_layout.addWidget(self.log_console)

        # ── 4. Bottom Action Buttons ───────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.close_btn = QPushButton("Close")
        self.close_btn.setMinimumWidth(80)
        self.close_btn.setMinimumHeight(28)
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.close_btn)

        btn_layout.addStretch()

        self.run_btn = QPushButton("Run Split")
        self.run_btn.setMinimumWidth(130)
        self.run_btn.setMinimumHeight(28)
        self.run_btn.setStyleSheet("font-weight: bold; background-color: #27ae60; color: white;")
        self.run_btn.clicked.connect(self.run_split)
        btn_layout.addWidget(self.run_btn)

        main_layout.addLayout(btn_layout)

    def _find_best_layer(self, geom_type: int, keyword: str) -> Optional[QgsVectorLayer]:
        """Find the best matching vector layer for a given geometry type and keyword ('delineated_ea', 'eadel_update')."""
        project = QgsProject.instance()
        all_layers = list(project.mapLayers().values())
        best_layer = None
        best_score = -1
        geo = (self.default_geocode or "").strip().lower()

        for lyr in all_layers:
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            if lyr.geometryType() != geom_type:
                continue

            name = lyr.name().lower()
            score = 0

            if keyword == "delineated_ea":
                if geo and geo in name and "delineated_ea" in name:
                    score = 100
                elif "delineated_ea" in name:
                    score = 80
                elif geo and geo in name and "delineation_ea" in name:
                    score = 60
                elif "delineation_ea" in name:
                    score = 50
                elif geo and geo in name and "delineation_candidates" in name:
                    score = 20
                elif "delineation_candidates" in name:
                    score = 10
            elif keyword == "eadel_update":
                if geo and geo in name and "eadel_update" in name:
                    score = 100
                elif "eadel_update" in name:
                    score = 80
                elif geo and geo in name and "splitting_lines" in name:
                    score = 60
                elif "splitting_lines" in name:
                    score = 50

            if score > best_score:
                best_score = score
                best_layer = lyr

        return best_layer if best_score > 0 else None

    def _extract_geocode_from_layer(self, layer: Optional[QgsVectorLayer]) -> str:
        """Extract numeric geocode prefix or token from layer name."""
        if not layer or not layer.isValid():
            return ""
        name = layer.name().lower()
        parts = name.split("_")
        for part in parts:
            digits = "".join(c for c in part if c.isdigit())
            if len(digits) in (5, 9, 10):
                return digits
        digits_all = "".join(c for c in name if c.isdigit())
        if len(digits_all) >= 5:
            return digits_all[:5]
        return ""

    def _bldg_layer_matches_poly(self, bldg_layer: Optional[QgsVectorLayer], poly_layer: Optional[QgsVectorLayer]) -> bool:
        """Check if building point layer matches the target polygon layer geocode."""
        if not bldg_layer or not bldg_layer.isValid() or not poly_layer or not poly_layer.isValid():
            return False
        poly_geo = self._extract_geocode_from_layer(poly_layer)
        if not poly_geo:
            return True
        bldg_name = bldg_layer.name().lower()
        return poly_geo in bldg_name

    def _find_best_bldg_layer(self, ref_poly_layer: Optional[QgsVectorLayer] = None) -> Optional[QgsVectorLayer]:
        """Find the best matching building points vector layer in QgsProject."""
        project = QgsProject.instance()
        all_layers = list(project.mapLayers().values())
        best_layer = None
        best_score = -1

        target_poly = ref_poly_layer or (self.poly_combo.currentLayer() if hasattr(self, "poly_combo") else self.default_poly_layer)
        geo = (self.default_geocode or "").strip().lower()
        if not geo and target_poly and target_poly.isValid():
            geo = self._extract_geocode_from_layer(target_poly)

        for lyr in all_layers:
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            if lyr.geometryType() != QgsWkbTypes.PointGeometry:
                continue

            name = lyr.name().lower()
            feat_count = lyr.featureCount()
            score = 0
            if geo and geo in name and ("bldgpts" in name or "extracted_bldgpts" in name or "bldg_point" in name or "bldgpoint" in name or "bldg_points" in name or "building_point" in name or "building_points" in name):
                score = 110
            elif "bldgpts" in name or "extracted_bldgpts" in name:
                score = 90
            elif geo and geo in name and ("geotagged" in name or "structure" in name):
                score = 85
            elif "bldg_point" in name or "bldgpoint" in name or "bldg_points" in name or "building_point" in name or "building_points" in name or "geotagged" in name:
                score = 75
            elif "bldg" in name or "building" in name:
                score = 60
            elif any(f.name().lower() in ("est_hhcount", "est_hh", "hh_count", "hhcount") for f in lyr.fields()):
                score = 50

            # Bonus for layers with est_hhcount field
            if any(f.name().lower() in ("est_hhcount", "est_hh_count", "est_hh", "esthhcount") for f in lyr.fields()):
                score += 20

            # Heavily prioritize layers that actually contain features over empty placeholder layers
            if feat_count > 0:
                score += 30
            else:
                score -= 60

            if score > best_score:
                best_score = score
                best_layer = lyr

        if not best_layer or best_score <= 0:
            cands = [
                l for l in all_layers
                if isinstance(l, QgsVectorLayer) and l.isValid()
                and l.geometryType() == QgsWkbTypes.PointGeometry and l.featureCount() > 0
            ]
            if cands:
                best_layer = max(cands, key=lambda l: l.featureCount())

        return best_layer

    def _auto_detect_layers(self):
        """Auto-detect matching delineated_ea, eadel_update, and building point layers."""
        poly_candidate = self.default_poly_layer if (self.default_poly_layer and self.default_poly_layer.isValid()) else None
        line_candidate = self.default_line_layer if (self.default_line_layer and self.default_line_layer.isValid()) else None
        bldg_candidate = self.default_bldg_layer if (self.default_bldg_layer and self.default_bldg_layer.isValid() and self.default_bldg_layer.featureCount() > 0) else None

        # Prioritize delineated_ea polygon layer
        if not poly_candidate:
            poly_candidate = self._find_best_layer(QgsWkbTypes.PolygonGeometry, "delineated_ea")
            if not poly_candidate:
                for lyr in QgsProject.instance().mapLayers().values():
                    if isinstance(lyr, QgsVectorLayer) and lyr.isValid() and lyr.geometryType() == QgsWkbTypes.PolygonGeometry:
                        name = lyr.name().lower()
                        if "ea" in name and "barangay" not in name:
                            poly_candidate = lyr
                            break

        # Prioritize eadel_update cut line layer
        if not line_candidate:
            line_candidate = self._find_best_layer(QgsWkbTypes.LineGeometry, "eadel_update")
            if not line_candidate:
                for lyr in QgsProject.instance().mapLayers().values():
                    if isinstance(lyr, QgsVectorLayer) and lyr.isValid() and lyr.geometryType() == QgsWkbTypes.LineGeometry:
                        line_candidate = lyr
                        break

        # Set polygon and line candidates first so UI and comboboxes are initialized
        if poly_candidate:
            self.poly_combo.setLayer(poly_candidate)
        if line_candidate:
            self.line_combo.setLayer(line_candidate)

        # Detect building points using poly_candidate to determine matching input
        if not bldg_candidate or bldg_candidate.featureCount() == 0:
            bldg_candidate = self._find_best_bldg_layer(ref_poly_layer=poly_candidate)

        if bldg_candidate:
            self._is_syncing_layers = True
            try:
                self.bldg_combo.setLayer(bldg_candidate)
            finally:
                self._is_syncing_layers = False

        self._on_layer_selection_changed()

    def closeEvent(self, event):
        self._disconnect_selection_signals()
        super().closeEvent(event)

    def _disconnect_selection_signals(self):
        if self._prev_poly_layer and hasattr(self._prev_poly_layer, "selectionChanged"):
            try:
                self._prev_poly_layer.selectionChanged.disconnect(self._update_poly_selection_ui)
            except Exception:
                pass
        if self._prev_line_layer and hasattr(self._prev_line_layer, "selectionChanged"):
            try:
                self._prev_line_layer.selectionChanged.disconnect(self._update_line_selection_ui)
            except Exception:
                pass

    def _on_poly_chk_toggled(self, checked: bool):
        self._poly_user_toggled = True

    def _on_line_chk_toggled(self, checked: bool):
        self._line_user_toggled = True

    def _update_poly_selection_ui(self):
        """Update polygon selection checkbox state and label."""
        poly_layer = self.poly_combo.currentLayer()
        if poly_layer and poly_layer.isValid() and hasattr(poly_layer, "selectedFeatureCount"):
            try:
                count = int(poly_layer.selectedFeatureCount())
            except (ValueError, TypeError):
                count = 0
            self.poly_selected_chk.setText(f"Selected features only ({count} selected)")
            if count > 0:
                self.poly_selected_chk.setEnabled(True)
                if not self._poly_user_toggled:
                    self.poly_selected_chk.setChecked(True)
            else:
                self.poly_selected_chk.setChecked(False)
                self.poly_selected_chk.setEnabled(False)
                self._poly_user_toggled = False
        else:
            self.poly_selected_chk.setText("Selected features only (0 selected)")
            self.poly_selected_chk.setChecked(False)
            self.poly_selected_chk.setEnabled(False)
            self._poly_user_toggled = False

    def _update_line_selection_ui(self):
        """Update cut lines selection checkbox state and label."""
        line_layer = self.line_combo.currentLayer()
        if line_layer and line_layer.isValid() and hasattr(line_layer, "selectedFeatureCount"):
            try:
                count = int(line_layer.selectedFeatureCount())
            except (ValueError, TypeError):
                count = 0
            self.line_selected_chk.setText(f"Selected features only ({count} selected)")
            if count > 0:
                self.line_selected_chk.setEnabled(True)
                if not self._line_user_toggled:
                    self.line_selected_chk.setChecked(True)
            else:
                self.line_selected_chk.setChecked(False)
                self.line_selected_chk.setEnabled(False)
                self._line_user_toggled = False
        else:
            self.line_selected_chk.setText("Selected features only (0 selected)")
            self.line_selected_chk.setChecked(False)
            self.line_selected_chk.setEnabled(False)
            self._line_user_toggled = False

    def _on_bldg_layer_changed(self):
        """Handle building layer combobox change."""
        if not getattr(self, "_is_syncing_layers", False):
            self._bldg_user_selected = True
        self._on_layer_selection_changed()

    def _on_layer_selection_changed(self):
        """Update layer info labels and dynamic selection listeners when layers change."""
        poly_layer = self.poly_combo.currentLayer()
        if self._prev_poly_layer != poly_layer:
            if self._prev_poly_layer and hasattr(self._prev_poly_layer, "selectionChanged"):
                try:
                    self._prev_poly_layer.selectionChanged.disconnect(self._update_poly_selection_ui)
                except Exception:
                    pass
            self._prev_poly_layer = poly_layer
            self._poly_user_toggled = False
            if poly_layer and hasattr(poly_layer, "selectionChanged"):
                try:
                    poly_layer.selectionChanged.connect(self._update_poly_selection_ui)
                except Exception:
                    pass

            # Dynamically determine / synchronize building layer with the selected input polygon layer
            if poly_layer and poly_layer.isValid():
                curr_bldg = self.bldg_combo.currentLayer()
                if not getattr(self, "_bldg_user_selected", False) or not self._bldg_layer_matches_poly(curr_bldg, poly_layer):
                    best_bldg = self._find_best_bldg_layer(ref_poly_layer=poly_layer)
                    if best_bldg and best_bldg != curr_bldg:
                        self._is_syncing_layers = True
                        try:
                            self.bldg_combo.setLayer(best_bldg)
                        finally:
                            self._is_syncing_layers = False

        line_layer = self.line_combo.currentLayer()
        if self._prev_line_layer != line_layer:
            if self._prev_line_layer and hasattr(self._prev_line_layer, "selectionChanged"):
                try:
                    self._prev_line_layer.selectionChanged.disconnect(self._update_line_selection_ui)
                except Exception:
                    pass
            self._prev_line_layer = line_layer
            self._line_user_toggled = False
            if line_layer and hasattr(line_layer, "selectionChanged"):
                try:
                    line_layer.selectionChanged.connect(self._update_line_selection_ui)
                except Exception:
                    pass

        self._update_poly_selection_ui()
        self._update_line_selection_ui()

        if poly_layer and poly_layer.isValid():
            self.poly_status_lbl.setText(
                f"Target to update: <b>{poly_layer.name()}</b> ({poly_layer.featureCount()} polygon features)"
            )
            self.poly_status_lbl.setStyleSheet("color: #27ae60; font-size: 11px;")
        else:
            self.poly_status_lbl.setText("No valid polygon layer selected.")
            self.poly_status_lbl.setStyleSheet("color: #e74c3c; font-size: 11px;")

        if line_layer and line_layer.isValid():
            self.line_status_lbl.setText(
                f"Selected cut lines: <b>{line_layer.name()}</b> ({line_layer.featureCount()} line features)"
            )
            self.line_status_lbl.setStyleSheet("color: #27ae60; font-size: 11px;")
        else:
            self.line_status_lbl.setText("No valid line layer selected.")
            self.line_status_lbl.setStyleSheet("color: #e74c3c; font-size: 11px;")

        bldg_layer = self.bldg_combo.currentLayer()
        if bldg_layer and bldg_layer.isValid():
            cnt = bldg_layer.featureCount()
            if cnt > 0:
                self.bldg_status_lbl.setText(
                    f"Selected building points: <b>{bldg_layer.name()}</b> ({cnt} point features)"
                )
                self.bldg_status_lbl.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.bldg_status_lbl.setText(
                    f"Warning: <b>{bldg_layer.name()}</b> contains 0 features. Building/household counts will be 0."
                )
                self.bldg_status_lbl.setStyleSheet("color: #e67e22; font-size: 11px;")
        else:
            self.bldg_status_lbl.setText("Optional / No building point layer selected.")
            self.bldg_status_lbl.setStyleSheet("color: #7F8C8D; font-size: 11px;")

    def _log(self, message: str, level: str = "INFO"):
        """Append formatted message to log console."""
        colors = {
            "INFO": "#2980b9",
            "SUCCESS": "#27ae60",
            "WARNING": "#e67e22",
            "ERROR": "#c0392b",
        }
        color = colors.get(level, "#333333")
        self.log_console.append(f"<span style='color:{color}; font-weight:bold;'>[{level}]</span> {message}")
        if hasattr(QApplication, "processEvents"):
            QApplication.processEvents()

    def _extend_line_endpoints(self, line_geom: QgsGeometry, extend_dist: float) -> QgsGeometry:
        """Extend line endpoints outwards by extend_dist to eliminate boundary undershoots."""
        if extend_dist <= 0.0 or not line_geom or line_geom.isEmpty():
            return line_geom

        if line_geom.isMultipart():
            lines = line_geom.asMultiPolyline()
            extended_multi = []
            for polyline in lines:
                if len(polyline) < 2:
                    extended_multi.append(polyline)
                    continue
                new_poly = list(polyline)
                # Extend start point
                p0, p1 = new_poly[0], new_poly[1]
                dx, dy = p0.x() - p1.x(), p0.y() - p1.y()
                dist = math.hypot(dx, dy)
                if dist > 1e-9:
                    new_p0 = QgsPointXY(p0.x() + (dx / dist) * extend_dist, p0.y() + (dy / dist) * extend_dist)
                    new_poly[0] = new_p0

                # Extend end point
                pn, pn_prev = new_poly[-1], new_poly[-2]
                dx, dy = pn.x() - pn_prev.x(), pn.y() - pn_prev.y()
                dist = math.hypot(dx, dy)
                if dist > 1e-9:
                    new_pn = QgsPointXY(pn.x() + (dx / dist) * extend_dist, pn.y() + (dy / dist) * extend_dist)
                    new_poly[-1] = new_pn

                extended_multi.append(new_poly)
            return QgsGeometry.fromMultiPolylineXY(extended_multi)
        else:
            polyline = line_geom.asPolyline()
            if len(polyline) < 2:
                return line_geom
            new_poly = list(polyline)
            # Extend start point
            p0, p1 = new_poly[0], new_poly[1]
            dx, dy = p0.x() - p1.x(), p0.y() - p1.y()
            dist = math.hypot(dx, dy)
            if dist > 1e-9:
                new_p0 = QgsPointXY(p0.x() + (dx / dist) * extend_dist, p0.y() + (dy / dist) * extend_dist)
                new_poly[0] = new_p0

            # Extend end point
            pn, pn_prev = new_poly[-1], new_poly[-2]
            dx, dy = pn.x() - pn_prev.x(), pn.y() - pn_prev.y()
            dist = math.hypot(dx, dy)
            if dist > 1e-9:
                new_pn = QgsPointXY(pn.x() + (dx / dist) * extend_dist, pn.y() + (dy / dist) * extend_dist)
                new_poly[-1] = new_pn

            return QgsGeometry.fromPolylineXY(new_poly)

    def _extract_polygon_rings(self, poly_geom: QgsGeometry) -> List[List[QgsPointXY]]:
        """Extract linear rings from Polygon or MultiPolygon geometry as lists of QgsPointXY."""
        rings = []
        if not poly_geom or poly_geom.isEmpty():
            return rings
        try:
            if poly_geom.isMultipart():
                for poly in poly_geom.asMultiPolygon():
                    for r in poly:
                        if r and isinstance(r[0], QgsPointXY):
                            rings.append(r)
                        elif r and isinstance(r[0], (list, tuple)):
                            for sub_r in r:
                                if sub_r and isinstance(sub_r[0], QgsPointXY):
                                    rings.append(sub_r)
            else:
                for r in poly_geom.asPolygon():
                    if r and isinstance(r[0], QgsPointXY):
                        rings.append(r)
                    elif r and isinstance(r[0], (list, tuple)):
                        for sub_r in r:
                            if sub_r and isinstance(sub_r[0], QgsPointXY):
                                rings.append(sub_r)
        except Exception:
            pass
        return rings

    def _find_boundary_exit_point(
        self,
        p0: QgsPointXY,
        dir_x: float,
        dir_y: float,
        rings: List[List[QgsPointXY]],
    ) -> Optional[Tuple[float, QgsPointXY]]:
        """Find the closest boundary intersection along the ray p0 + t*(dir_x, dir_y) for t > 0."""
        best_t = None
        best_pt = None

        for ring in rings:
            n = len(ring)
            if n < 2:
                continue
            for i in range(n - 1):
                a = ring[i]
                b = ring[i + 1]
                wx = b.x() - a.x()
                wy = b.y() - a.y()

                cross = dir_x * wy - dir_y * wx
                if abs(cross) < 1e-12:
                    continue

                dx0 = a.x() - p0.x()
                dy0 = a.y() - p0.y()

                t = (dx0 * wy - dy0 * wx) / cross
                u = (dx0 * dir_y - dy0 * dir_x) / cross

                if t > 1e-7 and -1e-7 <= u <= 1.0 + 1e-7:
                    if best_t is None or t < best_t:
                        best_t = t
                        best_pt = QgsPointXY(p0.x() + t * dir_x, p0.y() + t * dir_y)

        if best_t is not None:
            return best_t, best_pt
        return None

    def _extend_line_to_traverse_polygon(
        self,
        line_geom: QgsGeometry,
        poly_geom: QgsGeometry,
        extend_dist_map_units: float = 0.001,
        extend_tol: Optional[float] = None,
    ) -> QgsGeometry:
        """Extend cut line endpoints outward just enough to traverse through the target polygon boundary.

        Finds the nearest boundary exit point along each endpoint ray and extends ONLY by
        extend_dist_map_units beyond that exit point, completely preventing excessive
        overshoot across other concave arms, lobes, or disconnected EA parts.
        """
        if extend_tol is not None:
            extend_dist_map_units = extend_tol
        if not line_geom or line_geom.isEmpty():
            return line_geom
        if not poly_geom or poly_geom.isEmpty():
            return self._extend_line_endpoints(line_geom, extend_dist_map_units)

        rings = self._extract_polygon_rings(poly_geom)
        if not rings:
            return self._extend_line_endpoints(line_geom, extend_dist_map_units)

        def extend_segment_coords(pts: List[QgsPointXY]) -> List[QgsPointXY]:
            if len(pts) < 2:
                return pts
            if pts[0] == pts[-1] and len(pts) > 2:
                # Closed loop already traverses
                return pts

            new_pts = list(pts)

            # 1. Extend start point p0 outward away from p1
            p0, p1 = new_pts[0], new_pts[1]
            dx0, dy0 = p0.x() - p1.x(), p0.y() - p1.y()
            dist0 = math.hypot(dx0, dy0)
            if dist0 > 1e-12:
                dir0_x, dir0_y = dx0 / dist0, dy0 / dist0
                exit0 = self._find_boundary_exit_point(p0, dir0_x, dir0_y, rings)
                if exit0 is not None:
                    _, pt_exit0 = exit0
                    new_p0 = QgsPointXY(
                        pt_exit0.x() + dir0_x * extend_dist_map_units,
                        pt_exit0.y() + dir0_y * extend_dist_map_units,
                    )
                else:
                    new_p0 = QgsPointXY(
                        p0.x() + dir0_x * extend_dist_map_units,
                        p0.y() + dir0_y * extend_dist_map_units,
                    )
                new_pts[0] = new_p0

            # 2. Extend end point pn outward away from pn_prev
            pn, pn_prev = new_pts[-1], new_pts[-2]
            dxn, dyn = pn.x() - pn_prev.x(), pn.y() - pn_prev.y()
            distn = math.hypot(dxn, dyn)
            if distn > 1e-12:
                dirn_x, dirn_y = dxn / distn, dyn / distn
                exitn = self._find_boundary_exit_point(pn, dirn_x, dirn_y, rings)
                if exitn is not None:
                    _, pt_exitn = exitn
                    new_pn = QgsPointXY(
                        pt_exitn.x() + dirn_x * extend_dist_map_units,
                        pt_exitn.y() + dirn_y * extend_dist_map_units,
                    )
                else:
                    new_pn = QgsPointXY(
                        pn.x() + dirn_x * extend_dist_map_units,
                        pn.y() + dirn_y * extend_dist_map_units,
                    )
                new_pts[-1] = new_pn

            return new_pts

        if line_geom.isMultipart():
            extended_multi = []
            for polyline in line_geom.asMultiPolyline():
                extended_multi.append(extend_segment_coords(polyline))
            return QgsGeometry.fromMultiPolylineXY(extended_multi)
        else:
            polyline = line_geom.asPolyline()
            return QgsGeometry.fromPolylineXY(extend_segment_coords(polyline))

    def _prepare_extended_cut_lines(self, line_layer: QgsVectorLayer, extend_dist: float) -> QgsVectorLayer:
        """Create memory layer containing extended cut lines."""
        crs_auth = line_layer.crs().authid() if line_layer.crs().isValid() else "EPSG:4326"
        temp_lines = QgsVectorLayer(f"LineString?crs={crs_auth}", "temp_extended_lines", "memory")
        dp = temp_lines.dataProvider()
        dp.addAttributes(line_layer.fields())
        temp_lines.updateFields()

        feats = []
        for feat in line_layer.getFeatures():
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                ext_geom = self._extend_line_endpoints(geom, extend_dist)
                new_feat = QgsFeature(feat)
                new_feat.setGeometry(ext_geom)
                feats.append(new_feat)

        dp.addFeatures(feats)
        temp_lines.updateExtents()
        return temp_lines

    def _resolve_bldg_hh_field(self, bldg_layer: QgsVectorLayer) -> Tuple[int, str]:
        """Find the index and name of the household count field in building point layer."""
        fields = bldg_layer.fields()
        candidate_names = [
            "est_hhcount",
            "est_hh_count",
            "est_hh",
            "est_hhcnt",
            "esthhcount",
            "hh_count",
            "hhcount",
            "total_hh",
            "hh_total",
            "household",
            "households",
            "bldg_hh",
            "num_hh",
            "no_hh",
            "pop",
            "population",
        ]
        for cname in candidate_names:
            for idx in range(fields.count()):
                if fields.at(idx).name().lower().strip() == cname:
                    return idx, fields.at(idx).name()
        # Fallback substring check
        for idx in range(fields.count()):
            fname = fields.at(idx).name().lower().strip()
            if "hh" in fname or "household" in fname:
                return idx, fields.at(idx).name()
        return -1, ""

    def _resolve_bldg_ea_geocode_field(self, bldg_layer: QgsVectorLayer) -> Tuple[int, str]:
        """Find the index and name of the ea_geocode field in building point layer strictly."""
        fields = bldg_layer.fields()
        for idx in range(fields.count()):
            if fields.at(idx).name().lower() == "ea_geocode":
                return idx, fields.at(idx).name()
        return -1, ""

    def _resolve_ea_geocode_field(self, poly_layer: QgsVectorLayer) -> Tuple[int, str]:
        """Find the index and name of the geocode field in EA layer strictly."""
        fields = poly_layer.fields()
        for idx in range(fields.count()):
            if fields.at(idx).name().lower() == "geocode":
                return idx, fields.at(idx).name()
        return -1, ""

    def _extract_8digit_code(self, val: Any) -> str:
        """Extract standardized 8-digit numeric code from a geocode string/int."""
        if val is None or val == NULL or str(val).strip() in ("", "NULL", "None", "nan"):
            return ""
        if isinstance(val, QVariant) and val.isNull():
            return ""
        val_str = str(val).strip()
        if val_str.endswith(".0"):
            val_str = val_str[:-2]
        digits = "".join([c for c in val_str if c.isdigit()])
        if len(digits) >= 8:
            return digits[:8]
        elif len(digits) > 0:
            return digits.zfill(8)
        return val_str[:8] if len(val_str) >= 8 else val_str

    def _extract_parent_code_and_prefix(self, feat: QgsFeature, fields: Any = None) -> Tuple[str, str]:
        """Extract standardized 6-digit code and 3-digit prefix from parent feature.
        Prioritizes the authoritative 14-digit PSGC geocode (digits[-6:]) if present.
        """
        candidate_fields = [
            "geocode", "ea_geocode", "geo_code",
            "ean", "new_ean", "code", "ea_code", "ea_number", "id", "name"
        ]
        for fname in candidate_fields:
            try:
                raw_val = feat.attribute(fname)
                if raw_val is not None and raw_val != NULL:
                    s = str(raw_val).strip()
                    if s.endswith(".0"):
                        s = s[:-2]
                    if s and s.lower() not in ("null", "none", "nan", "false"):
                        digits = "".join([c for c in s if c.isdigit()])
                        if len(digits) >= 6:
                            code_6 = digits[-6:]
                            prefix_3 = code_6[:3]
                            return code_6, prefix_3
                        elif len(digits) == 3:
                            return digits + "000", digits
                        elif digits:
                            code_6 = digits.zfill(6)
                            return code_6, code_6[:3]
            except Exception:
                pass

        if fields is not None:
            for fname in candidate_fields:
                idx = -1
                if hasattr(fields, "indexOf"):
                    idx = fields.indexOf(fname)
                elif hasattr(fields, "lookupField"):
                    idx = fields.lookupField(fname)
                elif hasattr(fields, "indexFromName"):
                    idx = fields.indexFromName(fname)
                elif isinstance(fields, (list, tuple)):
                    for i, f in enumerate(fields):
                        if hasattr(f, "name") and f.name().lower() == fname:
                            idx = i
                            break
                if idx != -1:
                    raw_val = feat.attribute(idx)
                    if raw_val is not None and raw_val != NULL:
                        s = str(raw_val).strip()
                        if s.endswith(".0"):
                            s = s[:-2]
                        if s and s.lower() not in ("null", "none", "nan", "false"):
                            digits = "".join([c for c in s if c.isdigit()])
                            if len(digits) >= 6:
                                code_6 = digits[-6:]
                                prefix_3 = code_6[:3]
                                return code_6, prefix_3
                            elif len(digits) == 3:
                                return digits + "000", digits
                            elif digits:
                                code_6 = digits.zfill(6)
                                return code_6, code_6[:3]

        return "001000", "001"

    def _extract_barangay_key(self, feat: QgsFeature, fields: Any = None) -> str:
        """Extract standardized barangay identifier for barangay-level sequence isolation.
        Prioritizes the authoritative 14-digit PSGC geocode (digits[:8]) if present.
        """
        candidate_fields = [
            "geocode", "ea_geocode", "geo_code",
            "bgy_code", "brgy_code", "bgy_geocode", "barangay_geocode",
            "barangay_code", "bgy_c", "brgy_c", "psgc", "psgc_code",
            "adm4_pcode", "barangay", "bgy", "brgy",
            "bgy_name", "barangay_name", "code"
        ]
        for fname in candidate_fields:
            try:
                raw_val = feat.attribute(fname)
                if raw_val is not None and raw_val != NULL:
                    s = str(raw_val).strip()
                    if s.endswith(".0"):
                        s = s[:-2]
                    if s and s.lower() not in ("null", "none", "nan", "false"):
                        digits = "".join([c for c in s if c.isdigit()])
                        if len(digits) >= 12:
                            return digits[:8]
                        elif len(digits) in (8, 9, 10):
                            return digits
                        elif digits and len(digits) >= 8:
                            return digits[:8]
                        elif digits and fname in ("bgy_code", "brgy_code", "bgy_c", "brgy_c"):
                            return digits
                        return s.upper()
            except Exception:
                pass

        if fields is not None:
            for fname in candidate_fields:
                idx = -1
                if hasattr(fields, "indexOf"):
                    idx = fields.indexOf(fname)
                elif hasattr(fields, "lookupField"):
                    idx = fields.lookupField(fname)
                elif hasattr(fields, "indexFromName"):
                    idx = fields.indexFromName(fname)
                elif isinstance(fields, (list, tuple)):
                    for i, f in enumerate(fields):
                        if hasattr(f, "name") and f.name().lower() == fname:
                            idx = i
                            break
                if idx != -1:
                    try:
                        raw_val = feat.attribute(idx)
                        if raw_val is not None and raw_val != NULL:
                            s = str(raw_val).strip()
                            if s.endswith(".0"):
                                s = s[:-2]
                            if s and s.lower() not in ("null", "none", "nan", "false"):
                                digits = "".join([c for c in s if c.isdigit()])
                                if len(digits) >= 12:
                                    return digits[:8]
                                elif len(digits) in (8, 9, 10):
                                    return digits
                                elif digits and len(digits) >= 8:
                                    return digits[:8]
                                elif digits and fname in ("bgy_code", "brgy_code", "bgy_c", "brgy_c"):
                                    return digits
                                return s.upper()
                    except Exception:
                        pass

        return "_ALL_"

    def _warn_user(self, title: str, message: str) -> None:
        """Display warning message in interactive mode, or log cleanly in test environment."""
        self._log(f"{title}: {message}", "WARNING")
        if "unittest" not in sys.modules and not os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("QGIS_UNIT_TEST"):
            try:
                QMessageBox.warning(self, title, message)
            except Exception:
                pass

    def _confirm_proceed(self, title: str, message: str) -> bool:
        """Prompt confirmation from user in interactive mode, defaulting to proceed in test mode."""
        self._log(f"Notice: {title} - {message}", "WARNING")
        if "unittest" not in sys.modules and not os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("QGIS_UNIT_TEST"):
            try:
                reply = QMessageBox.warning(
                    self,
                    title,
                    message,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                return reply == QMessageBox.Yes
            except Exception:
                return True
        return True

    def run_split(self):
        """Execute polygon splitting pipeline and directly update target polygon layer and counts in-place."""
        poly_layer = self.poly_combo.currentLayer()
        line_layer = self.line_combo.currentLayer()
        bldg_layer = self.bldg_combo.currentLayer()

        # Ensure target EA polygon layer is delineated_ea if available in project
        if not poly_layer or not poly_layer.isValid() or "delineated_ea" not in poly_layer.name().lower():
            delineated_poly = self._find_best_layer(QgsWkbTypes.PolygonGeometry, "delineated_ea")
            if delineated_poly and delineated_poly.isValid():
                poly_layer = delineated_poly
                self.poly_combo.setLayer(poly_layer)

        # Ensure cut lines layer is eadel_update if available in project
        if not line_layer or not line_layer.isValid() or "eadel_update" not in line_layer.name().lower():
            eadel_line = self._find_best_layer(QgsWkbTypes.LineGeometry, "eadel_update")
            if eadel_line and eadel_line.isValid():
                line_layer = eadel_line
                self.line_combo.setLayer(line_layer)

        # Ensure building point layer is auto-resolved if not set or empty
        if not bldg_layer or not bldg_layer.isValid() or bldg_layer.featureCount() == 0:
            auto_bldg = self._find_best_bldg_layer(ref_poly_layer=poly_layer)
            if auto_bldg and auto_bldg.isValid():
                bldg_layer = auto_bldg
                self._is_syncing_layers = True
                try:
                    self.bldg_combo.setLayer(bldg_layer)
                finally:
                    self._is_syncing_layers = False

        if not poly_layer or not poly_layer.isValid():
            self._warn_user("Invalid Input", "Please select a valid EA polygon layer (delineated_ea).")
            return
        if not line_layer or not line_layer.isValid():
            self._warn_user("Invalid Input", "Please select a valid cut lines layer (eadel_update).")
            return
        if not bldg_layer or not bldg_layer.isValid():
            if not self._confirm_proceed(
                "No Building Point Layer Selected",
                "No Building Point Layer (e.g. extracted_bldgpts, bldgpts, or geotagged building points) was selected.\n\n"
                "Without building points, hh_count and bldg_count will not be calculated for split EAs.\n\n"
                "Do you want to proceed anyway?",
            ):
                return

        in_poly_count = poly_layer.featureCount()
        in_line_count = line_layer.featureCount()
        in_bldg_count = bldg_layer.featureCount() if bldg_layer and bldg_layer.isValid() else 0

        if in_poly_count == 0:
            self._warn_user("Empty Input", "The selected polygon layer contains 0 features.")
            return
        if in_line_count == 0:
            self._warn_user("Empty Input", "The selected cut lines layer contains 0 features.")
            return
        if bldg_layer and bldg_layer.isValid() and in_bldg_count == 0:
            if not self._confirm_proceed(
                "Empty Building Layer",
                f"The selected building point layer '{bldg_layer.name()}' contains 0 features.\n\n"
                "Without building points, hh_count and bldg_count will be 0.\n\n"
                "Do you want to proceed anyway?",
            ):
                return

        use_selected_poly = self.poly_selected_chk.isChecked() and (poly_layer.selectedFeatureCount() > 0)
        selected_poly_ids = set(poly_layer.selectedFeatureIds()) if use_selected_poly else set()
        if self.poly_selected_chk.isChecked() and poly_layer.selectedFeatureCount() == 0:
            self._warn_user(
                "No Polygons Selected",
                "The 'Selected features only' option is checked for the polygon layer, but no polygon features are currently selected in QGIS.",
            )
            return

        use_selected_lines = self.line_selected_chk.isChecked() and (line_layer.selectedFeatureCount() > 0)
        if self.line_selected_chk.isChecked() and line_layer.selectedFeatureCount() == 0:
            self._warn_user(
                "No Cut Lines Selected",
                "The 'Selected features only' option is checked for cut lines, but no cut line features are currently selected in QGIS.",
            )
            return

        poly_crs = poly_layer.crs()
        line_crs = line_layer.crs()

        xform_line_to_poly = None
        if poly_crs.isValid() and line_crs.isValid() and poly_crs.authid() != line_crs.authid():
            try:
                xform_line_to_poly = QgsCoordinateTransform(line_crs, poly_crs, QgsProject.instance())
            except Exception:
                xform_line_to_poly = None

        raw_line_feats = line_layer.selectedFeatures() if use_selected_lines else list(line_layer.getFeatures())
        selected_line_feats = []
        for lf in raw_line_feats:
            if not lf or not lf.hasGeometry() or lf.geometry().isEmpty():
                continue
            geom = QgsGeometry(lf.geometry())
            if xform_line_to_poly:
                try:
                    geom.transform(xform_line_to_poly)
                except Exception:
                    pass
            new_lf = QgsFeature(lf)
            new_lf.setGeometry(geom)
            selected_line_feats.append(new_lf)

        if self.line_selected_chk.isChecked() and len(selected_line_feats) == 0:
            QMessageBox.warning(
                self,
                "No Cut Lines Selected",
                "The 'Selected features only' option is checked for cut lines, but no cut line features are currently selected in QGIS.",
            )
            return

        self.run_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress_bar.setValue(10)
        self.log_console.clear()
        self.status_banner.setText("Executing polygon split...")
        self.status_banner.setStyleSheet("color: #2980b9; font-weight: bold;")

        self._log(f"Starting EA polygon split pipeline...")
        if use_selected_poly:
            self._log(f"Target polygon layer: '{poly_layer.name()}' — Splitting {len(selected_poly_ids)} SELECTED feature(s) of {in_poly_count} total")
        else:
            self._log(f"Target polygon layer: '{poly_layer.name()}' ({in_poly_count} features)")

        if use_selected_lines:
            self._log(f"Input cut lines layer: '{line_layer.name()}' — Using {len(selected_line_feats)} SELECTED line(s) of {in_line_count} total")
        else:
            self._log(f"Input cut lines layer: '{line_layer.name()}' ({in_line_count} features)")

        if bldg_layer and bldg_layer.isValid():
            self._log(f"Building points layer: '{bldg_layer.name()}' ({bldg_layer.featureCount()} features)")

        try:
            extend_tol = self.tolerance_spin.value()
            crs_auth = poly_crs.authid() if poly_crs.isValid() else "EPSG:4326"

            is_geographic = poly_crs.isGeographic() if poly_crs.isValid() else False
            if is_geographic:
                extend_dist_map_units = max(extend_tol / 111320.0, 0.00001)
            else:
                extend_dist_map_units = max(extend_tol, 0.5)

            self.progress_bar.setValue(20)
            self._log("Indexing proposed cut lines and matching to EA polygons...")

            line_spatial_index = QgsSpatialIndex()
            for lf in selected_line_feats:
                if lf and lf.hasGeometry() and not lf.geometry().isEmpty():
                    line_spatial_index.addFeature(lf)
            line_lookup = {f.id(): f for f in selected_line_feats}

            # Building points spatial index & lookup for household estimation
            bldg_to_poly_xform = None
            if bldg_layer and poly_layer:
                b_crs = bldg_layer.crs()
                p_crs = poly_layer.crs()
                if b_crs.isValid() and p_crs.isValid() and b_crs.authid() != p_crs.authid():
                    try:
                        bldg_to_poly_xform = QgsCoordinateTransform(b_crs, p_crs, QgsProject.instance())
                    except Exception as e:
                        self._log(f"Notice: Failed to initialize coordinate transform from '{b_crs.authid()}' to '{p_crs.authid()}': {e}", "WARNING")
                        bldg_to_poly_xform = None

            bldg_spatial_index = None
            bldg_lookup = {}
            bldg_hh_idx, bldg_hh_name = -1, ""
            bldg_ea_geo_idx, bldg_ea_geo_name = -1, ""

            if bldg_layer and bldg_layer.isValid() and bldg_layer.featureCount() > 0:
                bldg_hh_idx, bldg_hh_name = self._resolve_bldg_hh_field(bldg_layer)
                bldg_ea_geo_idx, bldg_ea_geo_name = self._resolve_bldg_ea_geocode_field(bldg_layer)
                crs_info = f" [reprojecting from {bldg_layer.crs().authid()} to {poly_layer.crs().authid()}]" if bldg_to_poly_xform else ""
                self._log(
                    f"Computing building & household counts using '{bldg_layer.name()}' "
                    f"(household field: '{bldg_hh_name or 'none [fallback 1/point]'}'{crs_info})..."
                )
                bldg_spatial_index = QgsSpatialIndex()
                for bf in bldg_layer.getFeatures():
                    if bf and bf.hasGeometry() and not bf.geometry().isEmpty():
                        bg = QgsGeometry(bf.geometry())
                        if bldg_to_poly_xform and bldg_to_poly_xform.isValid():
                            try:
                                bg.transform(bldg_to_poly_xform)
                            except Exception:
                                pass
                        feat_clone = QgsFeature(bf)
                        feat_clone.setGeometry(bg)
                        bldg_spatial_index.addFeature(feat_clone)
                        bldg_lookup[feat_clone.id()] = feat_clone
                        bldg_lookup[bf.id()] = feat_clone

            # Resolve EA layer geocode field strictly
            ea_geo_idx, ea_geo_name = self._resolve_ea_geocode_field(poly_layer)

            def _calculate_geom_counts(geom, target_8digit_code=None):
                """Count total building points and sum est_hhcount for all building points spatially inside geom."""
                inside_bldg_count = 0
                inside_hh_float = 0.0
                if bldg_spatial_index and geom and not geom.isEmpty():
                    candidate_ids = bldg_spatial_index.intersects(geom.boundingBox())

                    # Ensure geometry is valid for spatial containment check
                    chk_geom = geom
                    if hasattr(geom, "isGeosValid"):
                        try:
                            if not geom.isGeosValid() and hasattr(geom, "makeValid"):
                                chk_geom = geom.makeValid()
                        except Exception:
                            chk_geom = geom

                    for bid in candidate_ids:
                        bfeat = bldg_lookup.get(bid)
                        if not bfeat:
                            continue
                        bgeom = bfeat.geometry()
                        if not bgeom or bgeom.isEmpty():
                            continue
                        if chk_geom.contains(bgeom) or chk_geom.intersects(bgeom):
                            # Resolve household float for point from est_hhcount
                            if bldg_hh_idx != -1:
                                raw_val = bfeat.attribute(bldg_hh_idx)
                                if raw_val is not None and raw_val != NULL:
                                    try:
                                        pt_hh = float(raw_val)
                                    except (ValueError, TypeError):
                                        pt_hh = 1.0
                                else:
                                    pt_hh = 1.0
                            else:
                                pt_hh = 1.0

                            inside_bldg_count += 1
                            inside_hh_float += max(0.0, pt_hh)

                return inside_bldg_count, int(math.ceil(inside_hh_float))

            exploded_features = []
            parent_split_groups = []

            for p_idx, poly_feat in enumerate(poly_layer.getFeatures()):
                poly_geom = poly_feat.geometry()
                if not poly_geom or poly_geom.isEmpty():
                    continue

                parent_code_6, orig_prefix = self._extract_parent_code_and_prefix(poly_feat, poly_layer.fields())

                if use_selected_poly and poly_feat.id() not in selected_poly_ids:
                    # Unselected polygon -> preserve whole and untouched
                    exploded_features.append(poly_feat)
                    parent_split_groups.append({"parent": poly_feat, "parts": [poly_geom]})
                    continue

                # Informational notice if parent household count is below 2 * min_hh_threshold (do not block split)
                min_hh_threshold = self.min_hh_spin.value() if hasattr(self, "min_hh_spin") else 99
                if bldg_spatial_index:
                    parent_8digit = ""
                    if ea_geo_idx != -1:
                        raw_ea_geo = poly_feat.attribute(ea_geo_idx)
                        parent_8digit = self._extract_8digit_code(raw_ea_geo)

                    parent_bldg_cnt, parent_hh_cnt = _calculate_geom_counts(poly_geom, target_8digit_code=parent_8digit)
                    if parent_hh_cnt < 2 * min_hh_threshold:
                        self._log(
                            f"Notice: Parent EA '{parent_code_6}' total household count ({parent_hh_cnt}) "
                            f"is below twice the reference threshold ({min_hh_threshold * 2} HH). Proceeding with split based on cut lines.",
                            "INFO",
                        )

                # Find cut lines that intersect this specific polygon
                if use_selected_lines:
                    candidate_lines = selected_line_feats
                else:
                    cand_line_ids = line_spatial_index.intersects(poly_geom.boundingBox())
                    candidate_lines = [line_lookup[lid] for lid in cand_line_ids if lid in line_lookup]

                matching_lines = []
                for lfeat in candidate_lines:
                    if lfeat and lfeat.geometry() and not lfeat.geometry().isEmpty():
                        lg = lfeat.geometry()
                        if poly_geom.intersects(lg):
                            matching_lines.append(lfeat)

                if not matching_lines:
                    # No cut lines intersect this EA -> preserve whole
                    if use_selected_poly:
                        self._log(
                            f"Selected polygon '{poly_feat.attribute('ean') or poly_feat.id()}' did not intersect any of the {len(selected_line_feats)} cut line(s).",
                            "WARNING",
                        )
                    exploded_features.append(poly_feat)
                    parent_split_groups.append({"parent": poly_feat, "parts": [poly_geom]})
                    continue

                # Create single polygon layer for isolated split (MultiPolygon supports both Polygon and MultiPolygon)
                single_poly_layer = QgsVectorLayer(f"MultiPolygon?crs={crs_auth}", "single_poly", "memory")
                dp_poly = single_poly_layer.dataProvider()
                dp_poly.addAttributes(poly_layer.fields())
                single_poly_layer.updateFields()
                pf_copy = QgsFeature(poly_layer.fields())
                pf_copy.setGeometry(poly_geom)
                for fld in poly_layer.fields():
                    val = poly_feat.attribute(fld.name())
                    if val is not None and val != NULL:
                        pf_copy.setAttribute(fld.name(), val)
                dp_poly.addFeatures([pf_copy])
                single_poly_layer.updateExtents()

                # Create lines layer for matching cut lines only (MultiLineString supports both single & multipart)
                single_lines_layer = QgsVectorLayer(f"MultiLineString?crs={crs_auth}", "single_lines", "memory")
                dp_lines = single_lines_layer.dataProvider()
                dp_lines.addAttributes(line_layer.fields())
                single_lines_layer.updateFields()

                prepared_line_feats = []
                for lf in matching_lines:
                    lg = lf.geometry()
                    if extend_tol > 0.0:
                        lg = self._extend_line_endpoints(lg, extend_dist_map_units)
                    new_lf = QgsFeature(line_layer.fields())
                    new_lf.setGeometry(lg)
                    prepared_line_feats.append(new_lf)
                dp_lines.addFeatures(prepared_line_feats)
                single_lines_layer.updateExtents()

                child_geoms = []

                # Attempt 1: Run native:splitwithlines on this single polygon
                if processing:
                    try:
                        split_res = processing.run(
                            "native:splitwithlines",
                            {
                                "INPUT": single_poly_layer,
                                "LINES": single_lines_layer,
                                "OUTPUT": "TEMPORARY_OUTPUT",
                            },
                        )
                        raw_split = split_res.get("OUTPUT")

                        single_res = processing.run(
                            "native:multiparttosingleparts",
                            {
                                "INPUT": raw_split,
                                "OUTPUT": "TEMPORARY_OUTPUT",
                            },
                        )
                        exploded = single_res.get("OUTPUT")

                        if exploded and isinstance(exploded, QgsVectorLayer) and exploded.featureCount() > 0:
                            for sub_feat in exploded.getFeatures():
                                if sub_feat.geometry() and not sub_feat.geometry().isEmpty():
                                    child_geoms.append(sub_feat.geometry())
                    except Exception as e:
                        self._log(f"Split algorithm notice: {str(e)}", "INFO")

                # Attempt 2: Planar Polygonization fallback (combines polygon boundary + cut lines)
                if len(child_geoms) <= 1 and processing:
                    try:
                        boundary_res = processing.run(
                            "native:boundary",
                            {
                                "INPUT": single_poly_layer,
                                "OUTPUT": "TEMPORARY_OUTPUT",
                            },
                        )
                        boundary_lyr = boundary_res.get("OUTPUT")
                        merged_lines_res = processing.run(
                            "native:mergevectorlayers",
                            {
                                "LAYERS": [boundary_lyr, single_lines_layer],
                                "OUTPUT": "TEMPORARY_OUTPUT",
                            },
                        )
                        merged_lines_lyr = merged_lines_res.get("OUTPUT")
                        polygonized_res = processing.run(
                            "native:polygonize",
                            {
                                "INPUT": merged_lines_lyr,
                                "OUTPUT": "TEMPORARY_OUTPUT",
                            },
                        )
                        poly_output = polygonized_res.get("OUTPUT")
                        if poly_output and isinstance(poly_output, QgsVectorLayer) and poly_output.featureCount() > 1:
                            cand_parts = []
                            for p_feat in poly_output.getFeatures():
                                pg = p_feat.geometry()
                                if pg and not pg.isEmpty():
                                    pt_surface = pg.pointOnSurface()
                                    if poly_geom.contains(pt_surface) or poly_geom.intersects(pt_surface):
                                        cand_parts.append(pg)
                            if len(cand_parts) > 1:
                                child_geoms = cand_parts
                    except Exception as e:
                        self._log(f"Planar polygonization notice: {str(e)}", "INFO")

                # Attempt 3: Iterative QgsGeometry.splitGeometry across all matching lines
                if len(child_geoms) <= 1:
                    # Deconstruct polygon into constituent parts to handle both single and multi-polygons
                    if poly_geom.isMultipart():
                        raw_parts = [QgsGeometry.fromPolygonXY(p) for p in poly_geom.asMultiPolygon()]
                    else:
                        raw_parts = [QgsGeometry(poly_geom)]

                    current_pieces = list(raw_parts)
                    for lf in prepared_line_feats:
                        lg = lf.geometry()
                        if not lg or lg.isEmpty():
                            continue
                        polylines = lg.asMultiPolyline() if lg.isMultipart() else [lg.asPolyline()]
                        for pline in polylines:
                            if len(pline) < 2:
                                continue
                            next_pieces = []
                            for piece in current_pieces:
                                working_piece = QgsGeometry(piece)
                                # Try topological=True then topological=False
                                res, new_subgeoms, _ = working_piece.splitGeometry(pline, True)
                                if res != 0 or not new_subgeoms:
                                    working_piece = QgsGeometry(piece)
                                    res, new_subgeoms, _ = working_piece.splitGeometry(pline, False)
                                if res == 0 and new_subgeoms:
                                    next_pieces.append(working_piece)
                                    next_pieces.extend(new_subgeoms)
                                else:
                                    next_pieces.append(piece)
                            current_pieces = next_pieces
                    if len(current_pieces) > 1:
                        child_geoms = current_pieces

                if len(child_geoms) > 1:
                    for cg in child_geoms:
                        sub_feat_full = QgsFeature(poly_layer.fields())
                        sub_feat_full.setGeometry(cg)
                        for fld in poly_layer.fields():
                            fname = fld.name()
                            val = poly_feat.attribute(fname)
                            if val is not None and val != NULL:
                                sub_feat_full.setAttribute(fname, val)
                        exploded_features.append(sub_feat_full)
                else:
                    child_geoms = [poly_geom]
                    exploded_features.append(poly_feat)

                parent_split_groups.append({"parent": poly_feat, "parts": child_geoms})

            self.progress_bar.setValue(60)

            # 4. Strict Post-Split Verification Checks
            self._log("Verifying split results and geometry integrity...")
            out_poly_count = len(exploded_features)
            delta_count = out_poly_count - in_poly_count

            # Calculate total areas for conservation check
            total_in_area = sum(f.geometry().area() for f in poly_layer.getFeatures() if f.geometry())
            total_out_area = sum(f.geometry().area() for f in exploded_features if f.geometry())
            area_diff = abs(total_out_area - total_in_area)
            rel_area_diff = (area_diff / total_in_area) if total_in_area > 0 else 0.0

            self._log(f"Initial polygon count: {in_poly_count}")
            self._log(f"Resulting polygon count: {out_poly_count} (Delta: +{delta_count} new features)")
            self._log(f"Area conservation difference: {area_diff:.6f} sq units (Relative: {rel_area_diff:.6%})")

            is_truly_split = delta_count > 0 and rel_area_diff < 0.001

            if is_truly_split:
                self._log(
                    f"CONFIRMED: Polygons successfully split into {out_poly_count} discrete features!",
                    "SUCCESS",
                )
            elif delta_count == 0:
                self._log(
                    "WARNING: Output polygon count equals input count. Cut lines did not intersect/bisect any polygon boundary.",
                    "WARNING",
                )
            else:
                self._log(
                    f"NOTICE: Split produced {out_poly_count} features.",
                    "INFO",
                )

            self.progress_bar.setValue(75)

            # 5. Ensure poly_layer has hh_count, bldg_count, bldg_points, new_ean, and ea_type fields
            if poly_layer.isEditable():
                poly_layer.commitChanges()

            poly_fields = poly_layer.fields()
            poly_field_names_lower = [poly_fields.at(i).name().lower() for i in range(poly_fields.count())]
            fields_to_add = []
            if "hh_count" not in poly_field_names_lower:
                fields_to_add.append(create_qgs_field("hh_count", QVariant.Int))
            if "bldg_count" not in poly_field_names_lower:
                fields_to_add.append(create_qgs_field("bldg_count", QVariant.Int))
            if "bldg_points" not in poly_field_names_lower:
                fields_to_add.append(create_qgs_field("bldg_points", QVariant.Int))
            if "new_ean" not in poly_field_names_lower:
                fields_to_add.append(create_qgs_field("new_ean", QVariant.String))
            if not any(f in poly_field_names_lower for f in ("ea_type", "eatype", "type")):
                fields_to_add.append(create_qgs_field("ea_type", QVariant.String))

            if fields_to_add:
                poly_layer.dataProvider().addAttributes(fields_to_add)
                poly_layer.updateFields()
                poly_fields = poly_layer.fields()
                poly_field_names_lower = [poly_fields.at(i).name().lower() for i in range(poly_fields.count())]

            # 6. Build new features, assign recalculated counts, and format new_ean according to delineation rules
            total_hh_sum = 0
            total_bldg_sum = 0
            new_features = []

            # Scan layer to identify existing highest EA sequence per barangay
            max_seq_by_bgy = {}
            for feat in poly_layer.getFeatures():
                bgy_key = self._extract_barangay_key(feat, poly_layer.fields())
                code_6, prefix_3 = self._extract_parent_code_and_prefix(feat, poly_layer.fields())
                try:
                    s_val = int(prefix_3)
                    if s_val > max_seq_by_bgy.get(bgy_key, 0):
                        max_seq_by_bgy[bgy_key] = s_val
                except ValueError:
                    pass

            for group in parent_split_groups:
                parent_feat = group["parent"]
                parts = group["parts"]
                parent_code_6, orig_prefix = self._extract_parent_code_and_prefix(parent_feat, poly_layer.fields())
                bgy_key = self._extract_barangay_key(parent_feat, poly_layer.fields())

                def _safe_parent_attr(pf, name, default=None):
                    if not pf:
                        return default
                    try:
                        flds = pf.fields()
                        if flds:
                            idx = -1
                            if hasattr(flds, "indexOf"):
                                idx = flds.indexOf(name)
                            elif hasattr(flds, "lookupField"):
                                idx = flds.lookupField(name)
                            elif hasattr(flds, "indexFromName"):
                                idx = flds.indexFromName(name)
                            if idx != -1:
                                val = pf.attribute(idx)
                                return val if val is not None and val != NULL else default
                        val = pf.attribute(name)
                        return val if val is not None and val != NULL else default
                    except Exception:
                        return default

                # Calculate counts for each child part
                part_data = []
                parent_8digit = ""
                if ea_geo_idx != -1:
                    raw_ea_geo = parent_feat.attribute(ea_geo_idx)
                    parent_8digit = self._extract_8digit_code(raw_ea_geo)

                for p_geom in parts:
                    inside_bldg_count, inside_hh_count = _calculate_geom_counts(p_geom, target_8digit_code=parent_8digit)
                    # When an EA is untouched (len(parts) == 1) and spatial points are not present (inside_hh_count == 0),
                    # strictly preserve the parent feature's existing hh_count and bldg_count.
                    if len(parts) == 1 and inside_hh_count == 0:
                        orig_hh = _safe_parent_attr(parent_feat, "hh_count", None)
                        if orig_hh is None:
                            orig_hh = _safe_parent_attr(parent_feat, "hhcount", 0)
                        if orig_hh:
                            try:
                                inside_hh_count = int(float(orig_hh))
                            except Exception:
                                pass
                    if len(parts) == 1 and inside_bldg_count == 0:
                        orig_bldg = _safe_parent_attr(parent_feat, "bldg_count", None)
                        if orig_bldg is None:
                            orig_bldg = _safe_parent_attr(parent_feat, "bldgcount", 0)
                        if orig_bldg:
                            try:
                                inside_bldg_count = int(float(orig_bldg))
                            except Exception:
                                pass

                    area_val = p_geom.area() if p_geom else 0.0
                    part_data.append({
                        "geom": p_geom,
                        "hh_count": inside_hh_count,
                        "bldg_count": inside_bldg_count,
                        "area": area_val,
                    })

                # ── Dissolve 0-HH sub-polygon slices (e.g. road/boundary slivers) into adjacent populated siblings ──
                if bldg_spatial_index:
                    nonzero_parts = [p for p in part_data if p["hh_count"] > 0]
                    zero_parts = [p for p in part_data if p["hh_count"] == 0]

                    if zero_parts and nonzero_parts:
                        # Only dissolve 0-HH sliver slices if at least 2 populated sub-EAs remain (e.g. 3 slices -> 2 slices).
                        # If len(nonzero_parts) < 2, dissolving would collapse the split into a single un-split EA!
                        if len(nonzero_parts) >= 2:
                            for zp in zero_parts:
                                best_neighbor = None
                                max_shared_len = -1.0
                                zp_geom = zp["geom"]

                                for np in nonzero_parts:
                                    np_geom = np["geom"]
                                    shared = np_geom.intersection(zp_geom)
                                    s_len = shared.length() if shared and not shared.isEmpty() else 0.0
                                    if s_len > max_shared_len:
                                        max_shared_len = s_len
                                        best_neighbor = np

                                # If no shared boundary (e.g. sliver), fallback to nearest centroid
                                if not best_neighbor or max_shared_len <= 0.0:
                                    zp_c = zp_geom.centroid().asPoint()
                                    best_neighbor = min(
                                        nonzero_parts,
                                        key=lambda np: zp_c.distance(np["geom"].centroid().asPoint())
                                    )

                                # Dissolve zero-household slice into best_neighbor
                                raw_combined = best_neighbor["geom"].combine(zp_geom)
                                best_neighbor["geom"] = raw_combined.makeValid() if hasattr(raw_combined, 'makeValid') else raw_combined
                                best_neighbor["area"] = best_neighbor["geom"].area()
                                best_neighbor["bldg_count"] += zp["bldg_count"]

                                self._log(
                                    f"Notice: Dissolved empty slice (0 HH, {zp['area']:.1f} m²) into adjacent "
                                    f"sibling sub-EA to prevent 0 hh_count emergence.",
                                    "INFO",
                                )

                            part_data = nonzero_parts
                        else:
                            self._log(
                                f"Notice: EA '{parent_code_6}' split into {len(part_data)} sub-EAs using 'eadel_update' "
                                f"(preserving sub-EA with 0 HH).",
                                "INFO",
                            )

                    elif not nonzero_parts and len(part_data) > 1:
                        # If ALL parts have 0 households, preserve the split! Do not reject it!
                        self._log(
                            f"Notice: EA '{parent_code_6}' split into {len(part_data)} sub-EAs using 'eadel_update' "
                            f"(0 HH detected from building points). Preserving all split parts.",
                            "INFO",
                        )

                # ── Process sub-EAs and log threshold notice without rejecting split ──
                if len(part_data) > 1:
                    part_data.sort(key=lambda item: (item["hh_count"], item["area"]), reverse=True)
                    min_hh_threshold = self.min_hh_spin.value() if hasattr(self, "min_hh_spin") else 99
                    if bldg_spatial_index:
                        under_threshold = [p for p in part_data if p["hh_count"] < min_hh_threshold]
                        if under_threshold:
                            min_hh_found = min(p["hh_count"] for p in part_data)
                            self._log(
                                f"Notice: EA '{parent_code_6}' split into {len(part_data)} sub-EAs using 'eadel_update' "
                                f"(HH counts: {[p['hh_count'] for p in part_data]}). "
                                f"Sub-EA has {min_hh_found} households (below reference threshold of {min_hh_threshold} HH).",
                                "WARNING",
                            )
                        else:
                            self._log(
                                f"Success: EA '{parent_code_6}' successfully split into {len(part_data)} sub-EAs using 'eadel_update' "
                                f"(HH counts: {[p['hh_count'] for p in part_data]}).",
                                "SUCCESS",
                            )

                for idx, p_item in enumerate(part_data):
                    inside_hh_count = p_item["hh_count"]
                    inside_bldg_count = p_item["bldg_count"]
                    p_geom = p_item["geom"]

                    total_hh_sum += inside_hh_count
                    total_bldg_sum += inside_bldg_count

                    # Determine new_ean based on standard PSA Delineation Rules enclosed within Barangay:
                    if len(part_data) > 1:
                        if orig_prefix == "000" or parent_code_6 in ("000000", "000", "0"):
                            # Special Rule for parent EA 000000:
                            # 1st largest -> 001000, 2nd largest -> 002000, 3rd -> 003000, etc.
                            seq_num = idx + 1
                            assigned_new_ean = f"{seq_num:03d}000"
                        else:
                            # Standard Delineation Rule enclosed within Barangay:
                            # 1. Largest hh_count sub-EA retains mother EA: parent_code + "000" (e.g., 002000)
                            # 2. Succeeding sub-EAs get [Next Sequential EA in Barangay][Mother EA Prefix]
                            #    e.g., in a barangay with 3 EAs (001000, 002000, 003000), Part 2 of EA 002000 becomes 004002.
                            if idx == 0:
                                assigned_new_ean = f"{orig_prefix}000"
                            else:
                                curr_seq = max_seq_by_bgy.get(bgy_key, 0) + 1
                                max_seq_by_bgy[bgy_key] = curr_seq
                                assigned_new_ean = f"{curr_seq:03d}{orig_prefix}"
                    else:
                        # Retained un-split polygon
                        existing_new_ean = _safe_parent_attr(parent_feat, "new_ean")
                        if existing_new_ean and str(existing_new_ean).strip().upper() not in ("", "NULL", "NONE"):
                            assigned_new_ean = str(existing_new_ean).strip()
                        else:
                            assigned_new_ean = parent_code_6

                    new_feat = QgsFeature(poly_fields)
                    new_feat.setGeometry(p_geom)
                    for fld in poly_fields:
                        fname = fld.name()
                        fname_lower = fname.lower()
                        if fname_lower in ("fid", "ogc_fid") and fld.type() in (QVariant.Int, QVariant.LongLong):
                            continue

                        is_hh_field = fname_lower in ("hh_count", "hh_cnt")
                        is_bldg_field = fname_lower in ("bldg_count", "bldg_points", "bldg_point", "bldg_cnt", "bldgpts_cnt")

                        # Only hh_count and bldg_count / bldg_points are updated based on building points
                        # Baseline fields (hhcount, bldgcount, bldgpoint, code, etc.) are strictly preserved
                        if is_hh_field and bldg_spatial_index:
                            new_feat.setAttribute(fname, inside_hh_count)
                        elif is_bldg_field and bldg_spatial_index:
                            new_feat.setAttribute(fname, inside_bldg_count)
                        elif fname_lower == "new_ean":
                            new_feat.setAttribute(fname, assigned_new_ean)
                        elif fname_lower in ("ea_type", "eatype", "type"):
                            if len(part_data) > 1:
                                new_feat.setAttribute(fname, "DELINEATED")
                            else:
                                val = _safe_parent_attr(parent_feat, fname)
                                new_feat.setAttribute(fname, val if val is not None and str(val).strip() not in ("", "None", "NULL") else "RETAINED")
                        elif fname_lower in ("remarks", "remark", "delin_remarks", "delin_remark"):
                            if len(part_data) > 1:
                                new_feat.setAttribute(fname, f"Delineated from EA {parent_code_6}")
                            else:
                                val = _safe_parent_attr(parent_feat, fname, "")
                                new_feat.setAttribute(fname, val if val is not None else "")
                        elif fname_lower in ("geocode", "ea_geocode", "geo_code"):
                            if len(part_data) > 1:
                                # Strictly preserve the original 8-digit code of the geocode starting from the left (do NOT recode)
                                val = _safe_parent_attr(parent_feat, fname)
                                val_str = str(val).strip() if val is not None else ""
                                if val_str.endswith(".0"):
                                    val_str = val_str[:-2]
                                digits_val = "".join([c for c in val_str if c.isdigit()])
                                if len(digits_val) >= 8:
                                    # Copy the first 8 digits starting from the left verbatim from parent
                                    parent_left_8 = digits_val[:8]
                                    new_feat.setAttribute(fname, f"{parent_left_8}{assigned_new_ean}")
                                elif len(bgy_key) in (8, 9, 10) and bgy_key != "_ALL_":
                                    new_feat.setAttribute(fname, f"{bgy_key}{assigned_new_ean}")
                                elif val is not None:
                                    new_feat.setAttribute(fname, val)
                            else:
                                val = _safe_parent_attr(parent_feat, fname)
                                if val is not None:
                                    new_feat.setAttribute(fname, val)
                        else:
                            val = _safe_parent_attr(parent_feat, fname)
                            if val is not None:
                                new_feat.setAttribute(fname, val)

                    new_features.append(new_feat)

            # 6b. Explicit Post-Split Recalculation Pass:
            # Ensure delineated_ea computes the total est_hhcount from building points into hh_count,
            # and computes the total count of building points into bldg_points and bldg_count within each polygon.
            if bldg_spatial_index:
                total_hh_sum = 0
                total_bldg_sum = 0
                for feat in new_features:
                    f_geom = feat.geometry()
                    if f_geom and not f_geom.isEmpty():
                        b_cnt, hh_cnt = _calculate_geom_counts(f_geom)
                        is_delineated = str(feat.attribute("ea_type") or "").upper() == "DELINEATED"
                        if b_cnt > 0 or hh_cnt > 0 or is_delineated:
                            for fld in poly_fields:
                                fn_lower = fld.name().lower()
                                if fn_lower in ("hh_count", "hh_cnt"):
                                    feat.setAttribute(fld.name(), hh_cnt)
                                elif fn_lower in ("bldg_count", "bldg_points", "bldg_point", "bldg_cnt", "bldgpts_cnt"):
                                    feat.setAttribute(fld.name(), b_cnt)
                        # Accumulate total sums
                        f_hh = feat.attribute("hh_count")
                        f_bldg = feat.attribute("bldg_count") or feat.attribute("bldg_points")
                        try:
                            total_hh_sum += int(float(f_hh)) if f_hh is not None and f_hh != NULL else hh_cnt
                        except Exception:
                            total_hh_sum += hh_cnt
                        try:
                            total_bldg_sum += int(float(f_bldg)) if f_bldg is not None and f_bldg != NULL else b_cnt
                        except Exception:
                            total_bldg_sum += b_cnt

            out_poly_count = len(new_features)
            delta_count = out_poly_count - in_poly_count
            is_truly_split = delta_count > 0

            self.progress_bar.setValue(85)

            # 7. Directly update the target polygon layer in-place
            self._log(f"Updating '{poly_layer.name()}' in-place with {out_poly_count} split features...")

            all_fids = [f.id() for f in poly_layer.getFeatures()]
            dp = poly_layer.dataProvider()

            is_edited = False
            try:
                if not poly_layer.isEditable():
                    poly_layer.startEditing()
                poly_layer.deleteFeatures(all_fids)
                poly_layer.addFeatures(new_features)
                is_edited = poly_layer.commitChanges()
            except Exception:
                is_edited = False

            if not is_edited:
                # Rollback if layer was left in edit mode with uncommitted changes
                if poly_layer.isEditable():
                    poly_layer.rollBack()
                # Fallback to direct provider edit
                dp.deleteFeatures(all_fids)
                dp.addFeatures(new_features)

            poly_layer.updateExtents()
            poly_layer.triggerRepaint()

            # Refresh QGIS Map Canvas so layer labels (e.g. '(X HH)') immediately update on screen
            if hasattr(self, "iface") and self.iface:
                try:
                    if hasattr(self.iface, "mapCanvas") and self.iface.mapCanvas():
                        self.iface.mapCanvas().refresh()
                except Exception:
                    pass

            # Highlight newly delineated child features on canvas
            delineated_fids = [
                f.id() for f in poly_layer.getFeatures()
                if str(f.attribute("ea_type") or "").upper() == "DELINEATED"
            ]
            if delineated_fids:
                try:
                    poly_layer.selectByIds(delineated_fids)
                except Exception:
                    pass

            if bldg_spatial_index:
                self._log(
                    f"Recalculated counts across {out_poly_count} split polygons: "
                    f"Total HH = {total_hh_sum:,}, Total Buildings = {total_bldg_sum:,}.",
                    "SUCCESS",
                )

            self._log(f"Successfully updated '{poly_layer.name()}' with {out_poly_count} features.", "SUCCESS")
            self.progress_bar.setValue(100)

            # Update status banner
            if is_truly_split:
                count_info = f" | Total HH: {total_hh_sum:,}" if bldg_spatial_index else ""
                self.status_banner.setText(
                    f"PASS: Updated '{poly_layer.name()}' — {out_poly_count} features (+{delta_count}){count_info}"
                )
                self.status_banner.setStyleSheet("color: #27ae60; font-weight: bold;")
            else:
                self.status_banner.setText(
                    f"Completed — '{poly_layer.name()}' has {out_poly_count} features"
                )
                self.status_banner.setStyleSheet("color: #e67e22; font-weight: bold;")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._log(f"Error during polygon splitting: {str(e)}", "ERROR")
            self.status_banner.setText(f"Error: {str(e)}")
            self.status_banner.setStyleSheet("color: #c0392b; font-weight: bold;")
            if "unittest" not in sys.modules and not os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("QGIS_UNIT_TEST"):
                try:
                    QMessageBox.critical(self, "Split Error", f"An error occurred during splitting:\n{str(e)}")
                except Exception:
                    pass

        finally:
            self.run_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
