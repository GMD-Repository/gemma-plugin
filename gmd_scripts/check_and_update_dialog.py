import os
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QCheckBox, QTextEdit, QTabWidget, QWidget,
    QFrame, QMessageBox, QProgressBar, QAction, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsProject, QgsMapLayerProxyModel, QgsVectorLayer,
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingUtils,
    QgsRectangle, QgsPointXY, QgsFeatureRequest, QgsProcessingFeatureSourceDefinition,
    QgsFeature, QgsWkbTypes
)
from qgis.gui import QgsMapLayerComboBox
import processing


def resolve_processing_output_layer(output_value, context):
    """Return a QgsVectorLayer whether Processing returns a layer object or a layer id/path string."""
    if isinstance(output_value, QgsVectorLayer):
        return output_value
    return QgsProcessingUtils.mapLayerFromString(output_value, context)


class CheckAndUpdateDialog(QDialog):
    """
    Check and Update Dialog for Boundary Management.
    Organizes boundary update activities into 3 structured tabs:
    1. Georeferencing
    2. Geometry Check & Repair (Chronological Step 1 Scan -> Table -> Step 2 Repair -> Step 3 UPSERT)
    3. Updating Metadata (Placeholder)
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Check and Update — Boundary Management")
        self.resize(920, 740)
        self.last_error_layer = None
        self.last_repaired_layer = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Header Title
        title_label = QLabel("Check and Update — Boundary Management")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #2C3E50; padding: 2px 0;")
        main_layout.addWidget(title_label)

        sub_label = QLabel("Integrated workflow for raster georeferencing, geometry check & repair, and metadata updates.")
        sub_label.setWordWrap(True)
        sub_label.setStyleSheet("color: #7F8C8D; font-size: 11px; margin-bottom: 4px;")
        main_layout.addWidget(sub_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #BDC3C7;")
        main_layout.addWidget(line)

        # Tabbed Widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab {
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
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #2980B9;
                border-bottom: 3px solid #3498DB;
            }
            QTabBar::tab:hover:!selected {
                background-color: #D5D8DC;
            }
        """)

        # Create Tab Pages
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()

        self._build_georeferencing_tab()
        self._build_geometry_tab()
        self._build_metadata_tab()

        self.tabs.addTab(self.tab1, "Georeferencing")
        self.tabs.addTab(self.tab2, "Geometry Check & Repair")
        self.tabs.addTab(self.tab3, "Updating Metadata")

        main_layout.addWidget(self.tabs, stretch=1)

        # Bottom Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

    # ── Tab 1: Georeferencing UI ───────────────────────────────────────────────
    def _build_georeferencing_tab(self):
        layout = QVBoxLayout(self.tab1)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        group = QGroupBox("Raster Basemap Georeferencing")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        grp_layout = QVBoxLayout(group)
        grp_layout.setSpacing(12)

        desc = QLabel(
            "Georeference scanned maps, barangay sketches, or raster basemaps to true spatial coordinates.\n"
            "Clicking the button below directly opens QGIS's built-in Georeferencer tool."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #34495E;")
        grp_layout.addWidget(desc)

        georef_btn = QPushButton("Open QGIS Georeferencer")
        georef_btn.setIcon(QIcon(":/images/themes/default/mActionGeoref.svg"))
        georef_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 10px 20px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        georef_btn.clicked.connect(self._run_georeferencer)
        grp_layout.addWidget(georef_btn, alignment=Qt.AlignLeft)

        grp_layout.addStretch()
        layout.addWidget(group)
        layout.addStretch()

    def _run_georeferencer(self):
        """Invoke built-in QGIS Georeferencer action directly."""
        try:
            if hasattr(self.iface, 'actionGeoreferencer') and self.iface.actionGeoreferencer():
                self.iface.actionGeoreferencer().trigger()
                return

            main_win = self.iface.mainWindow()
            for obj_name in ['mActionGeoreferencer', 'mActionShowGeoreferencer', 'actionGeoreferencer']:
                action = main_win.findChild(QAction, obj_name)
                if action:
                    action.trigger()
                    return

            for action in main_win.findChildren(QAction):
                txt = action.text().replace('&', '').strip()
                if 'Georeferencer' in txt:
                    action.trigger()
                    return

            try:
                import qgis.utils
                if 'georeferencer-gdal' in qgis.utils.plugins:
                    qgis.utils.plugins['georeferencer-gdal'].run()
                    return
                elif 'georeferencer' in qgis.utils.plugins:
                    qgis.utils.plugins['georeferencer'].run()
                    return
            except Exception:
                pass

            QMessageBox.warning(
                self,
                "Georeferencer",
                "Georeferencer action could not be found. Please ensure the Georeferencer GDAL plugin is enabled in Plugins → Manage and Install Plugins."
            )
        except Exception as e:
            QMessageBox.warning(self, "Georeferencer", f"Could not launch Georeferencer: {e}")

    # ── Tab 2: Geometry Check & Repair UI ──────────────────────────────────────
    def _build_geometry_tab(self):
        layout = QVBoxLayout(self.tab2)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 1. Layer Selection Group
        layer_group = QGroupBox("Target Polygon Layer")
        layer_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        layer_layout = QHBoxLayout(layer_group)
        layer_label = QLabel("Select Layer:")
        layer_label.setWordWrap(True)
        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        layer_layout.addWidget(layer_label)
        layer_layout.addWidget(self.layer_combo, stretch=1)
        layout.addWidget(layer_group)

        # 2. Error Check Options Group
        opts_group = QGroupBox("Check Error Types")
        opts_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        opts_layout = QHBoxLayout(opts_group)
        self.chk_null = QCheckBox("Null")
        self.chk_null.setChecked(True)
        self.chk_empty = QCheckBox("Empty")
        self.chk_empty.setChecked(True)
        self.chk_invalid = QCheckBox("Invalid GEOS")
        self.chk_invalid.setChecked(True)
        self.chk_self = QCheckBox("Self-Intersections")
        self.chk_self.setChecked(True)
        self.chk_wrong = QCheckBox("Wrong Type")
        self.chk_wrong.setChecked(True)
        self.chk_dup = QCheckBox("Duplicates")
        self.chk_dup.setChecked(True)

        opts_layout.addWidget(self.chk_null)
        opts_layout.addWidget(self.chk_empty)
        opts_layout.addWidget(self.chk_invalid)
        opts_layout.addWidget(self.chk_self)
        opts_layout.addWidget(self.chk_wrong)
        opts_layout.addWidget(self.chk_dup)
        layout.addWidget(opts_group)

        # Chronological Step 1 Button: Scan Geometry Errors
        self.scan_btn = QPushButton("Step 1: Scan Geometry Errors")
        self.scan_btn.setIcon(QIcon(":/images/themes/default/mActionFilter.svg"))
        self.scan_btn.setStyleSheet("font-weight: bold; font-size: 12px; padding: 8px 16px; background-color: #27AE60; color: white;")
        self.scan_btn.clicked.connect(self._run_scan_errors)
        layout.addWidget(self.scan_btn)

        # Vertical Splitter for Error Table and Log
        splitter = QSplitter(Qt.Vertical)

        # 3. Detected Errors Results Table Group
        table_group = QGroupBox("Detected Geometry Errors (Double-click to zoom map | Multi-select rows to fix specific features)")
        table_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        table_layout = QVBoxLayout(table_group)
        table_layout.setContentsMargins(6, 6, 6, 6)
        table_layout.setSpacing(6)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["Source FID", "Layer", "Error Type", "Description", "Auto-fixable"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setStyleSheet("QTableWidget { background-color: #FFFFFF; font-size: 11px; }")
        self.results_table.itemDoubleClicked.connect(self._zoom_to_error_item)
        self.results_table.itemSelectionChanged.connect(self._update_repair_button_state)

        table_layout.addWidget(self.results_table)

        # Action Buttons Layout (Step 2 & Step 3)
        steps_btn_layout = QHBoxLayout()

        # Step 2 Button: Repair Polygon Geometries
        self.repair_btn = QPushButton("Step 2: Repair Polygon Geometries (All Errors)")
        self.repair_btn.setIcon(QIcon(":/images/themes/default/mActionToggleEditing.svg"))
        self.repair_btn.setStyleSheet("font-weight: bold; font-size: 12px; padding: 8px 16px; background-color: #E67E22; color: white;")
        self.repair_btn.clicked.connect(self._run_repair_geometries)
        steps_btn_layout.addWidget(self.repair_btn, stretch=1)

        # Step 3 Button: UPSERT Repaired Features to Layer
        self.upsert_btn = QPushButton("Step 3: UPSERT Repaired Features to Layer")
        self.upsert_btn.setIcon(QIcon(":/images/themes/default/mActionSaveAllEdits.svg"))
        self.upsert_btn.setStyleSheet("font-weight: bold; font-size: 12px; padding: 8px 16px; background-color: #2980B9; color: white;")
        self.upsert_btn.clicked.connect(self._run_upsert_repaired_geometries)
        self.upsert_btn.setEnabled(False)  # Enabled once Step 2 produces a repaired layer
        steps_btn_layout.addWidget(self.upsert_btn, stretch=1)

        table_layout.addLayout(steps_btn_layout)
        splitter.addWidget(table_group)

        # 4. Process Log Console Group
        log_group = QGroupBox("Process Log & Console Output")
        log_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 6, 6, 6)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #F8F9F9; font-family: Consolas, monospace; font-size: 11px;")
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_group)

        splitter.setSizes([340, 100])
        layout.addWidget(splitter, stretch=1)

    def _log(self, text):
        self.log_text.append(text)

    def _get_selected_fids_from_table(self):
        """Extract unique source_fid values from highlighted table rows."""
        selected_rows = sorted({item.row() for item in self.results_table.selectedItems()})
        fids = set()
        for row in selected_rows:
            fid_item = self.results_table.item(row, 0)
            if fid_item and fid_item.text().isdigit():
                fids.add(int(fid_item.text()))
        return fids

    def _update_repair_button_state(self):
        """Dynamically update repair button text based on table row selection."""
        fids = self._get_selected_fids_from_table()
        if fids:
            self.repair_btn.setText(f"Step 2: Repair Polygon Geometries ({len(fids)} Selected Feature(s))")
            self.repair_btn.setStyleSheet("font-weight: bold; font-size: 12px; padding: 8px 16px; background-color: #D35400; color: white;")
        else:
            self.repair_btn.setText("Step 2: Repair Polygon Geometries (All Errors)")
            self.repair_btn.setStyleSheet("font-weight: bold; font-size: 12px; padding: 8px 16px; background-color: #E67E22; color: white;")

    def _populate_error_table(self, error_layer):
        """Populate the interactive Results Table with features from the scanned error layer."""
        self.results_table.blockSignals(True)
        self.results_table.setRowCount(0)
        if error_layer is None or not error_layer.isValid():
            self.results_table.blockSignals(False)
            self._update_repair_button_state()
            return

        features = list(error_layer.getFeatures())
        self.results_table.setRowCount(len(features))

        for row, feat in enumerate(features):
            fid = feat.attribute('source_fid')
            lyr_name = feat.attribute('layer_name')
            err_type = feat.attribute('error_type')
            desc = feat.attribute('description')
            autofix = "Yes" if feat.attribute('is_autofixable') else "No (Manual)"

            item_fid = QTableWidgetItem(str(fid if fid is not None else ''))
            item_fid.setData(Qt.UserRole, feat.geometry())  # Store point geometry for map zoom
            item_fid.setTextAlignment(Qt.AlignCenter)

            item_lyr = QTableWidgetItem(str(lyr_name or ''))
            item_type = QTableWidgetItem(str(err_type or ''))
            item_type.setFont(self.font())
            item_type.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            item_desc = QTableWidgetItem(str(desc or ''))
            item_fix = QTableWidgetItem(autofix)
            item_fix.setTextAlignment(Qt.AlignCenter)
            if autofix.startswith("Yes"):
                item_fix.setForeground(QColor("#27AE60"))
            else:
                item_fix.setForeground(QColor("#C0392B"))

            self.results_table.setItem(row, 0, item_fid)
            self.results_table.setItem(row, 1, item_lyr)
            self.results_table.setItem(row, 2, item_type)
            self.results_table.setItem(row, 3, item_desc)
            self.results_table.setItem(row, 4, item_fix)

        self.results_table.blockSignals(False)
        self.results_table.resizeColumnsToContents()
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._update_repair_button_state()

    def _zoom_to_error_item(self, item):
        """Zoom map canvas to the double-clicked error location."""
        row = item.row()
        fid_item = self.results_table.item(row, 0)
        if not fid_item:
            return

        geom = fid_item.data(Qt.UserRole)
        if geom and not geom.isEmpty():
            try:
                canvas = self.iface.mapCanvas()
                bb = geom.boundingBox()
                if bb.isEmpty() or (bb.width() == 0 and bb.height() == 0):
                    pt = geom.asPoint()
                    scale = 200.0
                    extent = QgsRectangle(pt.x() - scale, pt.y() - scale, pt.x() + scale, pt.y() + scale)
                else:
                    bb.scale(1.5)
                    extent = bb
                canvas.setExtent(extent)
                canvas.refresh()
                self._log(f"Zoomed map canvas to error at row {row + 1} (FID {fid_item.text()}).")
            except Exception as e:
                self._log(f"Could not zoom to error point: {e}")

    def _run_scan_errors(self):
        layer = self.layer_combo.currentLayer()
        if not layer:
            return QMessageBox.warning(self, "No Layer", "Please select a valid polygon layer.")

        self._log(f"\n--- Starting Geometry Error Scan on '{layer.name()}' ---")
        params = {
            'INPUT': layer,
            'CHECK_NULL': self.chk_null.isChecked(),
            'CHECK_EMPTY': self.chk_empty.isChecked(),
            'CHECK_INVALID': self.chk_invalid.isChecked(),
            'CHECK_SELF_INTERSECT': self.chk_self.isChecked(),
            'CHECK_WRONG_TYPE': self.chk_wrong.isChecked(),
            'CHECK_DUPLICATE': self.chk_dup.isChecked(),
            'OUTPUT_ERRORS': 'TEMPORARY_OUTPUT'
        }

        try:
            res = processing.run("gmd_pipeline:scangeometryerrors", params)
            out_layer = resolve_processing_output_layer(res['OUTPUT_ERRORS'], QgsProcessingContext())
            if out_layer:
                out_layer.setName(f"Errors_{layer.name()}")
                QgsProject.instance().addMapLayer(out_layer)
                self.last_error_layer = out_layer
                cnt = out_layer.featureCount()

                # Populate interactive Results Table
                self._populate_error_table(out_layer)

                self._log(f"Scan complete. Found {cnt} error location(s). Loaded layer '{out_layer.name()}' into QGIS and error table.")
            else:
                self._log("Scan complete. No error layer returned.")
        except Exception as e:
            self._log(f"Scan failed: {e}")
            QMessageBox.critical(self, "Scan Error", f"Failed to run Scan Geometry Errors: {e}")

    def _run_repair_geometries(self):
        layer = self.layer_combo.currentLayer()
        if not layer:
            return QMessageBox.warning(self, "No Layer", "Please select a valid polygon layer.")

        selected_fids = self._get_selected_fids_from_table()

        if selected_fids:
            self._log(f"\n--- Starting Polygon Geometry Repair on '{layer.name()}' ({len(selected_fids)} Selected Feature FIDs: {sorted(list(selected_fids))}) ---")
            layer.selectByIds(list(selected_fids))
            input_param = QgsProcessingFeatureSourceDefinition(layer.id(), selectedFeaturesOnly=True)
        else:
            self._log(f"\n--- Starting Polygon Geometry Repair on '{layer.name()}' (All Errors / Features) ---")
            layer.removeSelection()
            input_param = layer

        params = {
            'INPUT': input_param,
            'REPAIR_MODE': 0,  # Auto-Detect & Repair All
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }

        try:
            res = processing.run("gmd_pipeline:repairpolygongeometries", params)
            out_layer = resolve_processing_output_layer(res['OUTPUT'], QgsProcessingContext())
            if out_layer:
                out_layer.setName(f"Repaired_{layer.name()}")
                QgsProject.instance().addMapLayer(out_layer)
                self.last_repaired_layer = out_layer
                cnt = out_layer.featureCount()

                # Enable Step 3 UPSERT button
                self.upsert_btn.setEnabled(True)
                self.upsert_btn.setText(f"Step 3: UPSERT Repaired Features ({cnt}) to Layer")

                self._log(f"Repair complete. Clean layer '{out_layer.name()}' created with {cnt} feature(s). Enabled Step 3 UPSERT button.")
            else:
                self._log("Repair complete. No output layer returned.")
        except Exception as e:
            self._log(f"Repair failed: {e}")
            QMessageBox.critical(self, "Repair Error", f"Failed to run Repair Polygon Geometries: {e}")

    def _run_upsert_repaired_geometries(self):
        """
        Step 3: UPSERT (Update/Insert) repaired features into a complete updated layer of the target polygon dataset.
        Replaces invalid geometries with clean repaired geometries while preserving all original valid features untouched.
        """
        target_layer = self.layer_combo.currentLayer()
        repaired_layer = self.last_repaired_layer

        if not target_layer or not target_layer.isValid():
            return QMessageBox.warning(self, "Upsert Error", "Target polygon layer is not valid.")
        if not repaired_layer or not repaired_layer.isValid():
            return QMessageBox.warning(self, "Upsert Error", "No repaired layer found. Please run Step 2: Repair Polygon Geometries first.")

        self._log(f"\n--- Starting Step 3: UPSERT Repaired Features into '{target_layer.name()}' ---")

        # Build mapping of repaired geometries by FID / source_fid
        repaired_map = {}
        for feat in repaired_layer.getFeatures():
            g = feat.geometry()
            if g and not g.isEmpty():
                repaired_map[feat.id()] = g
                try:
                    sfid = feat.attribute('source_fid')
                    if sfid is not None:
                        repaired_map[int(sfid)] = g
                except Exception:
                    pass

        # Create updated memory vector layer matching target_layer schema
        crs = target_layer.crs().authid()
        wkb_type = QgsWkbTypes.displayString(target_layer.wkbType())
        fields = target_layer.fields()

        updated_layer = QgsVectorLayer(f"{wkb_type}?crs={crs}", f"Updated_{target_layer.name()}", "memory")
        dp = updated_layer.dataProvider()
        dp.addAttributes(fields)
        updated_layer.updateFields()

        new_features = []
        updated_count = 0
        unchanged_count = 0

        for feat in target_layer.getFeatures():
            new_feat = QgsFeature(feat)
            fid = feat.id()
            if fid in repaired_map:
                new_feat.setGeometry(repaired_map[fid])
                updated_count += 1
            else:
                unchanged_count += 1
            new_features.append(new_feat)

        dp.addFeatures(new_features)
        updated_layer.updateExtents()

        QgsProject.instance().addMapLayer(updated_layer)
        self._log(f"UPSERT Complete! Complete updated layer '{updated_layer.name()}' loaded into QGIS.")
        self._log(f"  - Repaired Features Replaced: {updated_count}")
        self._log(f"  - Untouched Valid Features Preserved: {unchanged_count}")
        self._log(f"  - Total Features in Updated Layer: {updated_layer.featureCount()}")

    # ── Tab 3: Updating Metadata UI ───────────────────────────────────────────
    def _build_metadata_tab(self):
        layout = QVBoxLayout(self.tab3)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        group = QGroupBox("Updating Metadata")
        group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        grp_layout = QVBoxLayout(group)
        grp_layout.setSpacing(12)

        desc = QLabel(
            "Auto-populate LGU PSGC metadata, standard attribute fields, and administrative codes.\n"
            "This module is currently configured as a placeholder and will be customized in upcoming updates."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #34495E;")
        grp_layout.addWidget(desc)

        placeholder_btn = QPushButton("Update Metadata (Placeholder)")
        placeholder_btn.setEnabled(False)
        placeholder_btn.setStyleSheet("padding: 8px 16px; font-weight: bold;")
        grp_layout.addWidget(placeholder_btn, alignment=Qt.AlignLeft)

        grp_layout.addStretch()
        layout.addWidget(group)
        layout.addStretch()
