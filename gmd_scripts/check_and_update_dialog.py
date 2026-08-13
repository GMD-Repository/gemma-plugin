import os
from qgis.PyQt.QtCore import Qt, QVariant, QTimer, QSettings, QPoint
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QCheckBox, QTextEdit, QTabWidget, QWidget,
    QFrame, QMessageBox, QProgressBar, QAction, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QSplitter,
    QApplication, QSpinBox, QComboBox, QDockWidget, QToolButton,
    QLineEdit, QFormLayout
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsProject, QgsMapLayerProxyModel, QgsVectorLayer, QgsMapLayer,
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingUtils, QgsProcessing,
    QgsRectangle, QgsPointXY, QgsFeatureRequest, QgsProcessingFeatureSourceDefinition,
    QgsFeature, QgsWkbTypes, QgsSnappingConfig, QgsTolerance, QgsGeometry, Qgis
)
from qgis.gui import QgsMapLayerComboBox, QgsFileWidget
import processing


def resolve_processing_output_layer(output_value, context):
    """Return a QgsVectorLayer whether Processing returns a layer object or a layer id/path string."""
    if isinstance(output_value, QgsVectorLayer):
        return output_value
    return QgsProcessingUtils.mapLayerFromString(output_value, context)


class DigitizeDockWidget(QDockWidget):
    """QGIS DockWidget for Gemma Digitize Navigation (dockable under Layers, Processing Toolbox, etc.)."""

    def __init__(self, parent_dialog, feature_name=""):
        super().__init__("Gemma Digitize Navigation", parent_dialog.iface.mainWindow())
        self.setObjectName("GemmaDigitizeNavigationDock")
        self.parent_dialog = parent_dialog
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        main_widget = QWidget(self)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Feature Dropdown Selector
        dropdown_layout = QHBoxLayout()
        dropdown_layout.setSpacing(6)

        title_lbl = QLabel("Feature:")
        title_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #2C3E50;")
        dropdown_layout.addWidget(title_lbl)

        self.feature_combo = QComboBox()
        self.feature_combo.setStyleSheet("""
            QComboBox {
                font-weight: bold;
                padding: 3px 6px;
                border: 1px solid #BDC3C7;
                border-radius: 4px;
                background-color: white;
                color: #2C3E50;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #BDC3C7;
                background-color: white;
                color: #2C3E50;
                selection-background-color: #2980B9;
                selection-color: white;
            }
            QComboBox QAbstractItemView::item {
                min-height: 22px;
                color: #2C3E50;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #2980B9;
                color: white;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #2980B9;
                color: white;
            }
        """)
        self.populate_feature_combo()
        self.feature_combo.currentIndexChanged.connect(self._on_feature_selected)
        dropdown_layout.addWidget(self.feature_combo, 1)

        layout.addLayout(dropdown_layout)

        # Navigation Buttons (Previous, Next, Save & Done, Return)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        prev_btn = QPushButton("Previous")
        prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #7F8C8D;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #616D6E; }
        """)
        prev_btn.clicked.connect(self._on_prev)

        next_btn = QPushButton("Next")
        next_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980B9;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1F618D; }
        """)
        next_btn.clicked.connect(self._on_next)

        save_done_btn = QPushButton("Save (Done)")
        save_done_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #219A52; }
        """)
        save_done_btn.clicked.connect(self._on_save_done)

        return_btn = QPushButton("Return")
        return_btn.setStyleSheet("""
            QPushButton {
                background-color: #16A085;
                color: white;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #117A65; }
        """)
        return_btn.clicked.connect(self._on_return)

        btn_layout.addWidget(prev_btn)
        btn_layout.addWidget(next_btn)
        btn_layout.addWidget(save_done_btn)
        btn_layout.addWidget(return_btn)

        layout.addLayout(btn_layout)
        self.setWidget(main_widget)

    def populate_feature_combo(self):
        """Populate the feature combo box from parent_dialog.adjust_feature_combo."""
        try:
            self.feature_combo.blockSignals(True)
            self.feature_combo.clear()
            p_combo = self.parent_dialog.adjust_feature_combo
            for i in range(p_combo.count()):
                txt = p_combo.itemText(i)
                data = p_combo.itemData(i)
                self.feature_combo.addItem(txt, data)
            if p_combo.currentIndex() >= 0:
                self.feature_combo.setCurrentIndex(p_combo.currentIndex())
        except Exception:
            pass
        finally:
            self.feature_combo.blockSignals(False)

    def sync_feature_index(self, index):
        """Sync current selected index without triggering signals."""
        try:
            self.feature_combo.blockSignals(True)
            if index >= 0 and index < self.feature_combo.count():
                self.feature_combo.setCurrentIndex(index)
        except Exception:
            pass
        finally:
            self.feature_combo.blockSignals(False)

    def _on_feature_selected(self, index):
        """User selected a feature from the dock dropdown -> switch and edit feature."""
        try:
            if index >= 0:
                self.parent_dialog.adjust_feature_combo.blockSignals(True)
                self.parent_dialog.adjust_feature_combo.setCurrentIndex(index)
                self.parent_dialog.adjust_feature_combo.blockSignals(False)
                self.parent_dialog._run_edit_layer()
        except Exception:
            pass

    def _on_prev(self):
        self.parent_dialog._run_prev_layer()

    def _on_next(self):
        self.parent_dialog._run_next_layer()

    def _on_save_done(self):
        self.parent_dialog._run_done_editing()

    def _on_return(self):
        if hasattr(self.parent_dialog.iface, 'removeDockWidget'):
            self.parent_dialog.iface.removeDockWidget(self)
        self.close()
        self.parent_dialog.showNormal()
        self.parent_dialog.raise_()
        self.parent_dialog.activateWindow()


class CheckAndUpdateDialog(QDialog):
    """
    Check and Update Dialog for Boundary Management.
    Organizes boundary update activities into structured tabs:
    1. Pre-Processing
    2. Geometry Check & Repair
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Check and Update — Boundary Management")
        self.resize(920, 740)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.last_error_layer = None
        self.last_repaired_layer = None
        self.active_edit_layer = None
        self.active_edit_fid = None
        self.feature_original_geometries = {}
        self.guard_guarding = False
        self.digitize_dock = None
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

        self._build_georeferencing_tab()
        self._build_geometry_tab()

        self.tabs.addTab(self.tab1, "Pre-Processing")
        self.tabs.addTab(self.tab2, "Geometry Check && Repair")

        main_layout.addWidget(self.tabs, stretch=1)

        # Bottom Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

    # ── Tab 1: Georeferencing & Boundary Setup UI ───────────────────────────────
    def _build_georeferencing_tab(self):
        layout = QVBoxLayout(self.tab1)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Step Progression Header Banner
        header_banner = QLabel("Georeferencing  ➔  Digitize  ➔  Update and Export")
        header_banner.setAlignment(Qt.AlignCenter)
        header_banner.setStyleSheet("""
            QLabel {
                background-color: #EBF5FB;
                color: #1F618D;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 12px;
                border: 1px solid #AED6F1;
                border-radius: 4px;
            }
        """)
        layout.addWidget(header_banner)

        # ── Georeferencing Section ───────────────────────────────────────────
        step1_group = QGroupBox("Georeferencing")
        step1_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        step1_layout = QVBoxLayout(step1_group)
        step1_layout.setSpacing(8)

        step1_desc = QLabel(
            "Georeference scanned maps, barangay sketches, or raster basemaps to true spatial coordinates.\n"
            "Clicking the button below opens QGIS's built-in Georeferencer tool pre-routed to C:\\PSA-GIS."
        )
        step1_desc.setWordWrap(True)
        step1_desc.setStyleSheet("font-size: 11px; color: #34495E;")
        step1_layout.addWidget(step1_desc)

        georef_btn = QPushButton("Open QGIS Georeferencer")
        georef_btn.setIcon(QIcon(":/images/themes/default/mActionGeoref.svg"))
        georef_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """)
        georef_btn.clicked.connect(self._run_georeferencer)
        step1_layout.addWidget(georef_btn, alignment=Qt.AlignLeft)
        layout.addWidget(step1_group)

        # ── Digitize Section ─────────────────────────────────────────────────
        step2_group = QGroupBox("Digitize")
        step2_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        step2_layout = QVBoxLayout(step2_group)
        step2_layout.setSpacing(8)

        step2_desc = QLabel(
            "Configure reference layer opacity and cycle through target editable layers for vertex digitizing."
        )
        step2_desc.setWordWrap(True)
        step2_desc.setStyleSheet("font-size: 11px; color: #34495E;")
        step2_layout.addWidget(step2_desc)

        # Row 1: PSA Reference Layer & Opacity
        ctrls_layout = QHBoxLayout()
        ctrls_layout.setSpacing(10)

        psa_label = QLabel("PSA Reference Layer:")
        psa_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.psa_layer_combo = QgsMapLayerComboBox()

        opacity_label = QLabel("Opacity:")
        opacity_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(0, 100)
        self.opacity_spin.setValue(25)
        self.opacity_spin.setSuffix("%")
        self.opacity_spin.setMinimumWidth(75)

        apply_btn = QPushButton("Apply")
        apply_btn.setIcon(QIcon(":/images/themes/default/mActionApply.svg"))
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #219A52;
            }
        """)
        apply_btn.clicked.connect(self._apply_layer_opacity)

        ctrls_layout.addWidget(psa_label)
        ctrls_layout.addWidget(self.psa_layer_combo, stretch=1)
        ctrls_layout.addWidget(opacity_label)
        ctrls_layout.addWidget(self.opacity_spin)
        ctrls_layout.addWidget(apply_btn)
        step2_layout.addLayout(ctrls_layout)

        # Row 2: Adjust Feature Selection & Edit/Previous/Next/Done Actions
        adjust_layout = QHBoxLayout()
        adjust_layout.setSpacing(10)

        adjust_label = QLabel("Adjust Feature:")
        adjust_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.adjust_feature_combo = QComboBox()

        edit_btn = QPushButton("Edit")
        edit_btn.setIcon(QIcon(":/images/themes/default/mActionToggleEditing.svg"))
        edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #E67E22;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #D35400;
            }
        """)
        edit_btn.clicked.connect(self._run_edit_layer)

        prev_btn = QPushButton("Previous")
        prev_btn.setIcon(QIcon(":/images/themes/default/mActionBack.svg"))
        prev_btn.setStyleSheet("""
            QPushButton {
                background-color: #7F8C8D;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #616D6E;
            }
        """)
        prev_btn.clicked.connect(self._run_prev_layer)

        next_btn = QPushButton("Next")
        next_btn.setIcon(QIcon(":/images/themes/default/mActionForward.svg"))
        next_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980B9;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1F618D;
            }
        """)
        next_btn.clicked.connect(self._run_next_layer)

        done_btn = QPushButton("Done")
        done_btn.setIcon(QIcon(":/images/themes/default/mActionFileSave.svg"))
        done_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-weight: bold;
                font-size: 11px;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #219A52;
            }
        """)
        done_btn.clicked.connect(self._run_done_editing)

        adjust_layout.addWidget(adjust_label)
        adjust_layout.addWidget(self.adjust_feature_combo, stretch=1)
        adjust_layout.addWidget(edit_btn)
        adjust_layout.addWidget(prev_btn)
        adjust_layout.addWidget(next_btn)
        adjust_layout.addWidget(done_btn)
        step2_layout.addLayout(adjust_layout)

        # Connect layer selection changes to populate features and update field dropdowns
        self.psa_layer_combo.layerChanged.connect(self._populate_adjust_features)
        self.psa_layer_combo.layerChanged.connect(self._on_update_lgu_layer_changed)

        # Auto-suggest layer ending with *_psa
        self._auto_suggest_psa_layer()

        # Populate Adjust Feature dropdown from selected PSA Reference Layer
        self._populate_adjust_features()

        layout.addWidget(step2_group)

        # ── Update and Export Section ─────────────────────────────────────────
        step3_group = QGroupBox("Update and Export")
        step3_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12px; }")
        step3_layout = QVBoxLayout(step3_group)
        step3_layout.setSpacing(8)

        step3_desc = QLabel(
            "Auto-populate PSGC metadata, standard 15-attribute schemas, and administrative codes for the selected boundary layer."
        )
        step3_desc.setWordWrap(True)
        step3_desc.setStyleSheet("font-size: 11px; color: #34495E;")
        step3_layout.addWidget(step3_desc)

        form_layout = QFormLayout()
        form_layout.setSpacing(6)

        # 1. LGU Geocode Field combo
        self.update_geocode_combo = QComboBox()
        form_layout.addRow("LGU Geocode Field:", self.update_geocode_combo)

        # 2. LGU Barangay Name Field combo
        self.update_barangay_combo = QComboBox()
        form_layout.addRow("LGU Barangay Name Field:", self.update_barangay_combo)

        step3_layout.addLayout(form_layout)

        # Populate initial fields from current PSA Reference Layer
        self._on_update_lgu_layer_changed()

        # Action Button: Save & Export Enriched Layer
        save_btn_layout = QHBoxLayout()
        self.save_export_btn = QPushButton("Update && Export (as GPKG)")
        self.save_export_btn.setIcon(QIcon(":/images/themes/default/mActionFileSave.svg"))
        self.save_export_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 18px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #219A52;
            }
        """)
        self.save_export_btn.clicked.connect(self._run_save_and_export_layer)
        save_btn_layout.addWidget(self.save_export_btn)
        save_btn_layout.addStretch()

        step3_layout.addLayout(save_btn_layout)
        layout.addWidget(step3_group)

        layout.addStretch()

    def _auto_suggest_psa_layer(self):
        """Auto-suggest and pre-select layer ending with '*_psa' in the PSA reference layer combo box."""
        try:
            for i in range(self.psa_layer_combo.count()):
                lyr = self.psa_layer_combo.layer(i)
                if lyr and lyr.isValid():
                    name_lower = lyr.name().strip().lower()
                    base_name, _ = os.path.splitext(name_lower)
                    if base_name.endswith('_psa') or name_lower.endswith('_psa'):
                        self.psa_layer_combo.setLayer(lyr)
                        break
        except Exception:
            pass

    def _populate_adjust_features(self):
        """Populate the Adjust Feature dropdown with barangay features from the selected PSA Reference Layer."""
        self.adjust_feature_combo.clear()
        self.adjust_features_map = {}
        layer = self.psa_layer_combo.currentLayer()
        if not layer or not layer.isValid() or not isinstance(layer, QgsVectorLayer):
            return

        # Search fields for barangay name column (case-insensitive)
        fields = layer.fields()
        target_field = None
        candidate_names = ['barangay', 'brgy_name', 'brgy', 'bgy_name', 'bgy', 'name', 'adm4_en', 'adm3_en']
        for name in candidate_names:
            idx = fields.indexOf(name)
            if idx != -1:
                target_field = fields.at(idx).name()
                break

        if not target_field:
            for f in fields:
                if f.type() == QVariant.String:
                    target_field = f.name()
                    break

        for feat in layer.getFeatures():
            fid = feat.id()
            brgy_val = str(feat[target_field]).strip() if target_field and feat[target_field] is not None else ""
            display_name = brgy_val if brgy_val else f"Feature {fid}"
            self.adjust_feature_combo.addItem(display_name, fid)
            self.adjust_features_map[fid] = feat

        if self.adjust_feature_combo.count() > 0:
            self.adjust_feature_combo.setCurrentIndex(0)

    def _apply_layer_opacity(self):
        """Set opacity (0-100%) for the selected layer in the PSA reference dropdown."""
        layer = self.psa_layer_combo.currentLayer()
        if not layer or not layer.isValid():
            return QMessageBox.warning(self, "No Layer Selected", "Please select a valid PSA reference layer.")

        val = self.opacity_spin.value()
        val = max(0, min(100, val))
        opacity_float = val / 100.0

        try:
            if hasattr(layer, 'setOpacity'):
                layer.setOpacity(opacity_float)
            elif hasattr(layer, 'renderer') and layer.renderer() and hasattr(layer.renderer(), 'setOpacity'):
                layer.renderer().setOpacity(opacity_float)

            layer.triggerRepaint()
            if hasattr(self.iface, 'mapCanvas') and self.iface.mapCanvas():
                self.iface.mapCanvas().refresh()
        except Exception as e:
            QMessageBox.critical(self, "Apply Opacity Error", f"Failed to set opacity for layer '{layer.name()}': {e}")

    def _run_edit_layer(self):
        """Select feature on layer, zoom canvas to bounding box, activate Vertex Tool, and minimize dialog."""
        layer = self.psa_layer_combo.currentLayer()
        if not layer or not layer.isValid() or not isinstance(layer, QgsVectorLayer):
            return QMessageBox.warning(self, "Edit Feature", "Please select a valid PSA Reference Layer.")

        fid = self.adjust_feature_combo.currentData()
        if fid is None:
            return QMessageBox.warning(self, "Edit Feature", "Please select a feature to edit.")

        feat = layer.getFeature(fid)
        if not feat.isValid():
            return QMessageBox.warning(self, "Edit Feature", f"Feature ID {fid} could not be retrieved.")

        feature_name = self.adjust_feature_combo.currentText()

        try:
            # 1. Set Active Layer in QGIS
            if hasattr(self.iface, 'setActiveLayer'):
                self.iface.setActiveLayer(layer)

            # 2. Force Read-Only flags off if set on Layer Properties
            try:
                if hasattr(layer, 'setReadOnly'):
                    layer.setReadOnly(False)
            except Exception:
                pass

            try:
                if hasattr(QgsMapLayer, 'FlagReadOnly'):
                    flags = layer.flags()
                    if flags & QgsMapLayer.FlagReadOnly:
                        layer.setFlags(flags & ~QgsMapLayer.FlagReadOnly)
            except Exception:
                pass

            try:
                layer.setCustomProperty("flags/readOnly", False)
                layer.setCustomProperty("readOnly", False)
            except Exception:
                pass

            # 3. Enable Editing Mode
            if not layer.isEditable():
                started = layer.startEditing()
                if not started:
                    # Fallback to main window toggle editing action
                    if hasattr(self.iface, 'actionToggleEditing') and self.iface.actionToggleEditing():
                        self.iface.actionToggleEditing().trigger()

            if not layer.isEditable():
                return QMessageBox.warning(
                    self,
                    "Editing Disabled",
                    f"Could not enable editing mode on layer '{layer.name()}'.\n"
                    f"Please check if the file format or provider is read-only."
                )

            # 4. Select Feature & Zoom to Bounding Box
            layer.selectByIds([fid])
            geom = feat.geometry()
            if hasattr(self.iface, 'mapCanvas') and self.iface.mapCanvas() and geom and not geom.isEmpty():
                canvas = self.iface.mapCanvas()
                bbox = geom.boundingBox()
                # Grow bounding box by 15% for optimal visual framing
                padding = max(bbox.width(), bbox.height()) * 0.15
                if padding > 0:
                    bbox.grow(padding)
                canvas.setExtent(bbox)
                canvas.refresh()

            # 5. Activate QGIS Vertex Tool
            def do_activate_vertex():
                if hasattr(self.iface, 'setActiveLayer'):
                    self.iface.setActiveLayer(layer)

                main_win = self.iface.mainWindow()
                action = None
                if hasattr(self.iface, 'actionVertexToolCurrentLayer') and self.iface.actionVertexToolCurrentLayer():
                    action = self.iface.actionVertexToolCurrentLayer()
                elif hasattr(self.iface, 'actionVertexTool') and self.iface.actionVertexTool():
                    action = self.iface.actionVertexTool()
                elif main_win:
                    action = (main_win.findChild(QAction, 'mActionVertexToolCurrentLayer') or
                              main_win.findChild(QAction, 'mActionVertexTool') or
                              main_win.findChild(QAction, 'mActionVertexToolAllLayers'))

                if action:
                    action.trigger()

            do_activate_vertex()
            QTimer.singleShot(150, do_activate_vertex)

            # 6. Cleanly toggle QGIS Topology Checker action once if not already active
            self._clean_toggle_topology_checker(layer)

            # 7. Configure Advanced Snapping for PSA Reference Layer (12px, Topological Editing, Self Snapping, Avoid Overlap)
            self._configure_layer_snapping(layer)

            # 8. Enable Feature Edit Guard (restricts editing to active feature ID only)
            self._setup_feature_edit_guard(layer, fid)

            # 9. Minimize Check and Update Dialog
            self.showMinimized()

            # 10. Show / Dock Gemma Digitize Navigation Dock Widget (Default area: Qt.LeftDockWidgetArea)
            if self.digitize_dock:
                self.digitize_dock.populate_feature_combo()
                self.digitize_dock.sync_feature_index(self.adjust_feature_combo.currentIndex())
                self.digitize_dock.show()
                self.digitize_dock.raise_()
            else:
                self.digitize_dock = DigitizeDockWidget(self, feature_name)
                if hasattr(self.iface, 'addDockWidget'):
                    self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.digitize_dock)
                self.digitize_dock.show()
        except Exception as e:
            QMessageBox.critical(self, "Edit Feature Error", f"Failed to activate editing on feature '{feature_name}': {e}")

    def _clean_toggle_topology_checker(self, layer=None):
        """Cleanly show/toggle the QGIS Topology Checker panel when clicking Edit, ensuring plugin is loaded on first click."""
        try:
            import qgis.utils

            # 1. Force enable and load C++ plugin if not loaded yet in session
            for p_name in ['topolplugin', 'topol', 'topologychecker']:
                try:
                    QSettings().setValue(f"Qgis/plugins/{p_name}/enabled", "true")
                except Exception:
                    pass

            if hasattr(self.iface, 'pluginManager') and self.iface.pluginManager():
                pm = self.iface.pluginManager()
                for p_name in ['topolplugin', 'topol']:
                    try:
                        if hasattr(pm, 'isPluginEnabled') and not pm.isPluginEnabled(p_name):
                            if hasattr(pm, 'setPluginEnabled'):
                                pm.setPluginEnabled(p_name, True)
                        if hasattr(pm, 'loadPlugin'):
                            pm.loadPlugin(p_name)
                        if hasattr(pm, 'startPlugin'):
                            pm.startPlugin(p_name)
                    except Exception:
                        pass

            # Force immediate Qt GUI event processing to initialize plugin UI synchronously
            QApplication.processEvents()

            main_win = self.iface.mainWindow()
            topol_dock = None

            # 2. Check if Topology Checker QDockWidget already exists in main window
            if main_win:
                for dock in main_win.findChildren(QDockWidget):
                    name = dock.objectName().lower()
                    title = dock.windowTitle().lower()
                    if 'topology' in title or 'topol' in title or 'topology' in name or 'topol' in name:
                        topol_dock = dock
                        dock.setVisible(True)
                        dock.show()
                        dock.raise_()
                        break

            # 3. Check if topol plugin instance is in qgis.utils.plugins
            if not topol_dock:
                topol_plugin = qgis.utils.plugins.get('topol') or qgis.utils.plugins.get('topolplugin')
                if topol_plugin:
                    topol_dock = getattr(topol_plugin, 'dockWidget', None) or getattr(topol_plugin, 'dock', None)
                    if topol_dock:
                        topol_dock.setVisible(True)
                        topol_dock.show()
                        topol_dock.raise_()
                    elif hasattr(topol_plugin, 'action') and topol_plugin.action:
                        topol_plugin.action.trigger()

            # 4. Search for Topology QAction in main window & vector menu
            if not topol_dock:
                topol_action = None
                if main_win:
                    for act in main_win.findChildren(QAction):
                        name = act.objectName().lower()
                        text = act.text().lower()
                        if name in ['mactiontoggletopol', 'mactiontopol'] or 'topology' in text or 'topol' in name:
                            topol_action = act
                            break

                if not topol_action and hasattr(self.iface, 'vectorMenu') and self.iface.vectorMenu():
                    for act in self.iface.vectorMenu().findChildren(QAction):
                        name = act.objectName().lower()
                        text = act.text().lower()
                        if 'topology' in text or 'topol' in name:
                            topol_action = act
                            break

                if topol_action:
                    topol_action.trigger()

            QApplication.processEvents()
        except Exception:
            pass





    def _configure_layer_snapping(self, layer):
        """Configure advanced snapping options for the PSA Reference Layer (12px tolerance, topological editing ON, self snapping ON, intersection snapping OFF, avoid overlap ON)."""
        if not layer or not layer.isValid() or not isinstance(layer, QgsVectorLayer):
            return

        try:
            prj = QgsProject.instance()

            # 1. Enable Topological Editing ONLY IF NOT ALREADY ENABLED
            try:
                if hasattr(prj, 'isTopologicalEditingEnabled'):
                    if not prj.isTopologicalEditingEnabled():
                        prj.setTopologicalEditingEnabled(True)
                elif hasattr(prj, 'setTopologicalEditingEnabled'):
                    prj.setTopologicalEditingEnabled(True)
            except Exception:
                pass

            # 2. Avoid Overlap on Active Layer
            try:
                if hasattr(prj, 'setAvoidIntersectionsMode') and hasattr(QgsProject, 'AvoidIntersectionsCurrentLayer'):
                    prj.setAvoidIntersectionsMode(QgsProject.AvoidIntersectionsCurrentLayer)
            except Exception:
                pass

            try:
                if hasattr(prj, 'setAvoidIntersectionsLayers'):
                    prj.setAvoidIntersectionsLayers([layer])
            except Exception:
                pass

            # 3. Configure QgsSnappingConfig
            snapping_cfg = prj.snappingConfig()
            snapping_cfg.setEnabled(True)

            # Set Mode to Advanced Configuration
            if hasattr(QgsSnappingConfig, 'AdvancedConfiguration'):
                snapping_cfg.setMode(QgsSnappingConfig.AdvancedConfiguration)

            # Enable Self Snapping & DISABLE Intersection Snapping
            if hasattr(snapping_cfg, 'setSelfSnappingEnabled'):
                snapping_cfg.setSelfSnappingEnabled(True)

            if hasattr(snapping_cfg, 'setIntersectionSnappingEnabled'):
                snapping_cfg.setIntersectionSnappingEnabled(False)

            # 4. Set Individual Layer Settings (Enabled = True, 12.0 Pixels, VertexAndSegment)
            snap_type = getattr(QgsSnappingConfig, 'VertexAndSegment', None)
            if snap_type is None and hasattr(QgsSnappingConfig, 'Vertex'):
                snap_type = QgsSnappingConfig.Vertex

            unit_pixels = getattr(QgsTolerance, 'Pixels', None)

            try:
                indiv_map = snapping_cfg.individualLayerSettings()
                if not isinstance(indiv_map, dict):
                    indiv_map = {}

                indiv_setting = indiv_map.get(layer)
                if not indiv_setting:
                    try:
                        indiv_setting = snapping_cfg.individualLayerSettings(layer)
                    except Exception:
                        indiv_setting = None

                if not indiv_setting:
                    indiv_setting = QgsSnappingConfig.IndividualLayerSettings()

                # Explicitly enable layer snapping checkbox in Advanced Configuration table
                indiv_setting.setEnabled(True)
                indiv_setting.setTolerance(12.0)
                if unit_pixels is not None:
                    indiv_setting.setUnits(unit_pixels)

                # Set snapping type using modern setTypeFlag or fallback with warning suppression
                type_set = False
                if hasattr(indiv_setting, 'setTypeFlag'):
                    try:
                        if hasattr(QgsSnappingConfig, 'SnappingTypeFlagVertex') and hasattr(QgsSnappingConfig, 'SnappingTypeFlagSegment'):
                            indiv_setting.setTypeFlag(QgsSnappingConfig.SnappingTypeFlagVertex | QgsSnappingConfig.SnappingTypeFlagSegment)
                            type_set = True
                        elif snap_type is not None:
                            indiv_setting.setTypeFlag(snap_type)
                            type_set = True
                    except Exception:
                        pass

                if not type_set and snap_type is not None and hasattr(indiv_setting, 'setType'):
                    try:
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", category=DeprecationWarning)
                            indiv_setting.setType(snap_type)
                    except Exception:
                        pass

                indiv_map[layer] = indiv_setting
                snapping_cfg.setIndividualLayerSettings(indiv_map)
                snapping_cfg.setIndividualLayerSettings(layer, indiv_setting)
            except Exception:
                pass

            prj.setSnappingConfig(snapping_cfg)

            # 5. Sync Snapping Toolbar QActions in QGIS Main Window
            main_win = self.iface.mainWindow()
            if main_win:
                for act in main_win.findChildren(QAction):
                    obj_name = act.objectName().lower()
                    txt = act.text().lower()
                    tooltip = act.toolTip().lower()

                    # Enable Topological Editing action on toolbar ONLY if not checked
                    if 'topologicalediting' in obj_name or 'topological editing' in tooltip or 'topological editing' in txt:
                        if hasattr(act, 'setChecked') and not act.isChecked():
                            act.setChecked(True)

                    # Enable Self-Snapping action on toolbar ONLY if not checked
                    if 'selfsnapping' in obj_name or 'self-snapping' in tooltip or 'self snapping' in tooltip or 'self snapping' in txt:
                        if hasattr(act, 'setChecked') and not act.isChecked():
                            act.setChecked(True)

                    # Disable Intersection Snapping action on toolbar
                    if 'intersectionsnapping' in obj_name or 'intersection snapping' in tooltip or 'snapping on intersection' in tooltip or 'intersection' in txt:
                        if hasattr(act, 'setChecked') and act.isChecked():
                            act.setChecked(False)
        except Exception:
            pass

    def _setup_feature_edit_guard(self, layer, fid):
        """Enable Feature Edit Guard to restrict vertex edits to the active feature ID only."""
        try:
            self._remove_feature_edit_guard()

            self.active_edit_layer = layer
            self.active_edit_fid = fid
            self.guard_guarding = False

            # Snapshot current feature geometries
            self.feature_original_geometries = {}
            for f in layer.getFeatures():
                if f.isValid() and f.geometry():
                    self.feature_original_geometries[f.id()] = QgsGeometry(f.geometry())

            if hasattr(layer, 'geometryChanged'):
                layer.geometryChanged.connect(self._on_layer_geometry_changed)
        except Exception:
            pass

    def _remove_feature_edit_guard(self):
        """Disconnect and reset Feature Edit Guard."""
        try:
            if self.active_edit_layer and hasattr(self.active_edit_layer, 'geometryChanged'):
                try:
                    self.active_edit_layer.geometryChanged.disconnect(self._on_layer_geometry_changed)
                except Exception:
                    pass
        except Exception:
            pass

        self.active_edit_layer = None
        self.active_edit_fid = None
        self.feature_original_geometries = {}
        self.guard_guarding = False

    def _on_layer_geometry_changed(self, fid, new_geom):
        """Signal handler enforcing single-feature editing lock by silently reverting edits to neighbor features."""
        if self.guard_guarding or self.active_edit_fid is None or not self.active_edit_layer:
            return

        if fid != self.active_edit_fid:
            self.guard_guarding = True
            try:
                old_geom = self.feature_original_geometries.get(fid)
                if old_geom and not old_geom.isEmpty():
                    self.active_edit_layer.changeGeometry(fid, old_geom)
            except Exception:
                pass
            finally:
                self.guard_guarding = False
        else:
            # Target feature was edited, update stored snapshot
            self.feature_original_geometries[fid] = QgsGeometry(new_geom)

    def _run_done_editing(self):
        """Prompt user to Save, Discard, or Cancel edits on the PSA Reference Layer, then stop editing and restore dialog."""
        self._remove_feature_edit_guard()

        if self.digitize_dock:
            try:
                if hasattr(self.iface, 'removeDockWidget'):
                    self.iface.removeDockWidget(self.digitize_dock)
                self.digitize_dock.close()
            except Exception:
                pass
            self.digitize_dock = None

        layer = self.psa_layer_combo.currentLayer()
        if not layer or not layer.isValid() or not isinstance(layer, QgsVectorLayer):
            self.showNormal()
            self.raise_()
            self.activateWindow()
            return

        committed = False
        action_taken = "none"

        if layer.isEditable():
            if layer.isModified():
                res = QMessageBox.question(
                    self,
                    "Stop Editing",
                    f"Do you want to save changes to layer '{layer.name()}'?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Save
                )

                if res == QMessageBox.Save:
                    committed = layer.commitChanges()
                    action_taken = "saved"
                elif res == QMessageBox.Discard:
                    layer.rollBack()
                    action_taken = "discarded"
                else:
                    # Cancel pressed: Abort stopping editing mode, keep window minimized
                    return
            else:
                committed = layer.commitChanges()
                action_taken = "stopped"

            layer.removeSelection()

        # Clear canvas MessageBar
        if hasattr(self.iface, 'messageBar') and self.iface.messageBar():
            self.iface.messageBar().clearWidgets()

        # Restore Check & Update dialog window
        self.showNormal()
        self.raise_()
        self.activateWindow()

        if action_taken == "saved":
            QMessageBox.information(self, "Editing Complete", f"Successfully saved changes and closed editing mode for '{layer.name()}'.")
        elif action_taken == "discarded":
            QMessageBox.information(self, "Editing Complete", f"Discarded revisions and closed editing mode for '{layer.name()}'.")
        else:
            QMessageBox.information(self, "Editing Complete", f"Closed editing mode for '{layer.name()}'.")

    def _trigger_topol_validate(self):
        """Cleanly trigger the 'Validate All' button on the QGIS Topology Checker dock panel."""
        try:
            import qgis.utils

            # Force immediate Qt GUI event processing so feature change/geometry updates are processed
            QApplication.processEvents()

            main_win = self.iface.mainWindow()
            topol_dock = None
            if main_win:
                for d in main_win.findChildren(QDockWidget):
                    name = d.objectName().lower()
                    title = d.windowTitle().lower()
                    if 'topology' in title or 'topol' in title or 'topology' in name or 'topol' in name:
                        topol_dock = d
                        break

            topol_plugin = qgis.utils.plugins.get('topol') or qgis.utils.plugins.get('topolplugin')
            if not topol_dock and topol_plugin:
                topol_dock = getattr(topol_plugin, 'dockWidget', None) or getattr(topol_plugin, 'dock', None)

            # 1. Search for Validate All button in dock widget and click it
            if topol_dock:
                buttons = topol_dock.findChildren(QToolButton) + topol_dock.findChildren(QPushButton)
                for btn in buttons:
                    txt = btn.text().lower()
                    obj = btn.objectName().lower()
                    tooltip = btn.toolTip().lower()
                    if ('validate all' in txt or 'validateall' in obj or 'validate all' in tooltip or
                        'validate' in txt or 'validate' in tooltip or 'validate' in obj or
                        ('all' in txt and 'validate' in tooltip) or 'validateext' in obj):
                        if hasattr(btn, 'click'):
                            btn.click()
                            return

            # 2. Fall back to calling validateAll methods on dock or plugin object
            if topol_dock and hasattr(topol_dock, 'validateAll'):
                topol_dock.validateAll()
                return

            if topol_plugin:
                if hasattr(topol_plugin, 'validateAll'):
                    topol_plugin.validateAll()
                elif hasattr(topol_plugin, 'validate'):
                    topol_plugin.validate()
        except Exception:
            pass

    def _run_prev_layer(self):
        """Move to the previous feature in the Adjust Feature list, trigger Edit action, and validate topology."""
        count = self.adjust_feature_combo.count()
        if count == 0:
            return QMessageBox.warning(self, "Previous Feature", "No features found in the selected PSA Reference Layer.")

        curr_idx = self.adjust_feature_combo.currentIndex()
        prev_idx = (curr_idx - 1) % count
        self.adjust_feature_combo.setCurrentIndex(prev_idx)
        self._run_edit_layer()
        self._trigger_topol_validate()

    def _run_next_layer(self):
        """Advance to the next feature in the Adjust Feature list, trigger Edit action, and validate topology."""
        count = self.adjust_feature_combo.count()
        if count == 0:
            return QMessageBox.warning(self, "Next Feature", "No features found in the selected PSA Reference Layer.")

        curr_idx = self.adjust_feature_combo.currentIndex()
        next_idx = (curr_idx + 1) % count
        self.adjust_feature_combo.setCurrentIndex(next_idx)
        self._run_edit_layer()
        self._trigger_topol_validate()

    def _run_georeferencer(self):
        """Invoke built-in QGIS Georeferencer action directly and auto-trigger Open Raster at C:\\PSA-GIS."""
        try:
            settings = QSettings()
            default_dir = r"C:\PSA-GIS"

            # Create default directory C:\PSA-GIS if it does not exist on disk
            if not os.path.exists(default_dir):
                try:
                    os.makedirs(default_dir, exist_ok=True)
                except Exception:
                    pass

            # Retrieve remembered directory or fall back to C:\PSA-GIS
            last_dir = settings.value("gmd_pipeline/last_georef_dir", default_dir)
            if not last_dir or not os.path.exists(str(last_dir)):
                last_dir = default_dir

            # Route QGIS native raster file chooser dialog to default/remembered folder
            settings.setValue("/UI/lastRasterFileFilterDir", str(last_dir))
            settings.setValue("/UI/lastRasterFileDir", str(last_dir))

            # Preset Transformation Settings for Georeferencer across all QGIS configuration keys
            proj_crs = QgsProject.instance().crs()
            target_crs = proj_crs.authid() if (proj_crs and proj_crs.isValid() and proj_crs.authid()) else "EPSG:4326"

            prefixes = [
                "/Plugin-Georeferencer/",
                "/georeferencer/",
                "/Plugin-Georeferencer-GDAL/",
                "/QGIS/georeferencer/",
                "Plugin-Georeferencer/",
                "georeferencer/"
            ]

            for p in prefixes:
                # 2 = Polynomial 1 in QGIS Georeferencer (0=Linear, 1=Helmert, 2=Polynomial 1)
                settings.setValue(p + "transformType", 2)
                settings.setValue(p + "transformationType", 2)
                settings.setValue(p + "transform_type", 2)

                # 0 = Nearest Neighbour
                settings.setValue(p + "resamplingMethod", 0)
                settings.setValue(p + "resampling", 0)

                # Target CRS
                settings.setValue(p + "targetSRS", str(target_crs))
                settings.setValue(p + "targetCRS", str(target_crs))
                settings.setValue(p + "targetCrs", str(target_crs))
                settings.setValue(p + "projection", str(target_crs))

                # Compression: "LZW" / index 1
                settings.setValue(p + "compression", "LZW")
                settings.setValue(p + "compressionMethod", "LZW")

                # Load in QGIS when done
                settings.setValue(p + "loadInQGIS", True)
                settings.setValue(p + "loadInProject", True)

            triggered = False
            if hasattr(self.iface, 'actionGeoreferencer') and self.iface.actionGeoreferencer():
                self.iface.actionGeoreferencer().trigger()
                triggered = True
            else:
                main_win = self.iface.mainWindow()
                for obj_name in ['mActionGeoreferencer', 'mActionShowGeoreferencer', 'actionGeoreferencer']:
                    action = main_win.findChild(QAction, obj_name)
                    if action:
                        action.trigger()
                        triggered = True
                        break

                if not triggered:
                    for action in main_win.findChildren(QAction):
                        txt = action.text().replace('&', '').strip()
                        if 'Georeferencer' in txt:
                            action.trigger()
                            triggered = True
                            break

                if not triggered:
                    try:
                        import qgis.utils
                        if 'georeferencer-gdal' in qgis.utils.plugins:
                            qgis.utils.plugins['georeferencer-gdal'].run()
                            triggered = True
                        elif 'georeferencer' in qgis.utils.plugins:
                            qgis.utils.plugins['georeferencer'].run()
                            triggered = True
                    except Exception:
                        pass

            if triggered:
                # Auto-trigger "Open Raster", minimize Check & Update dialog, auto-populate Transformation Settings, and auto-restore when done
                def _trigger_open_raster():
                    current_dir = settings.value("/UI/lastRasterFileFilterDir", last_dir)
                    if current_dir and os.path.exists(str(current_dir)):
                        settings.setValue("gmd_pipeline/last_georef_dir", str(current_dir))

                    georef_win = None
                    for widget in QApplication.topLevelWidgets():
                        if "Georeferencer" in widget.windowTitle():
                            georef_win = widget
                            # Find Open Raster action in Georeferencer window
                            for action in widget.findChildren(QAction):
                                txt = action.text().replace('&', '').strip().lower()
                                name = action.objectName().lower()
                                tooltip = action.toolTip().lower()
                                if 'open raster' in txt or 'openraster' in name or 'open raster' in tooltip or 'add raster' in txt:
                                    action.trigger()
                                    break
                            else:
                                # Fallback: search for Open Raster buttons
                                for btn in widget.findChildren(QPushButton):
                                    txt = btn.text().replace('&', '').strip().lower()
                                    tooltip = btn.toolTip().lower()
                                    if 'open raster' in txt or 'open raster' in tooltip:
                                        btn.click()
                                        break
                            break

                    # Automatically minimize Check & Update dialog to keep screen clear
                    self.showMinimized()

                    # Auto-fill Transformation Settings dialog and normalize output file path to Windows backslashes
                    def _auto_fill_transformation_dialog():
                        from qgis.PyQt.QtWidgets import QComboBox, QCheckBox, QLineEdit
                        for widget in QApplication.topLevelWidgets():
                            title = widget.windowTitle().lower()
                            if "transformation" in title or "setting" in title:
                                # Normalize path in file line edits (convert C:/... to C:\...)
                                for line_edit in widget.findChildren(QLineEdit):
                                    txt = line_edit.text()
                                    if txt and ("/" in txt or ".tif" in txt or "_modified" in txt):
                                        normalized = os.path.normpath(txt).replace('/', '\\')
                                        if normalized != txt:
                                            line_edit.setText(normalized)

                                for combo in widget.findChildren(QComboBox):
                                    items = [combo.itemText(i) for i in range(combo.count())]
                                    for i, item in enumerate(items):
                                        if "polynomial 1" in item.lower():
                                            combo.setCurrentIndex(i)
                                            break
                                        elif "nearest" in item.lower():
                                            combo.setCurrentIndex(i)
                                            break
                                        elif "lzw" in item.lower():
                                            combo.setCurrentIndex(i)
                                            break
                                for chk in widget.findChildren(QCheckBox):
                                    txt = chk.text().lower()
                                    if "load in" in txt or "load in project" in txt or "load in qgis" in txt:
                                        chk.setChecked(True)

                    for delay in [300, 600, 1000, 1500, 2500, 4000, 6000]:
                        QTimer.singleShot(delay, _auto_fill_transformation_dialog)

                    # Auto-restore Check & Update dialog when Georeferencer window is closed
                    if georef_win:
                        def _check_georef_closed():
                            try:
                                if not georef_win.isVisible():
                                    self.showNormal()
                                    self.raise_()
                                    self.activateWindow()
                                else:
                                    QTimer.singleShot(600, _check_georef_closed)
                            except Exception:
                                self.showNormal()
                                self.raise_()
                                self.activateWindow()

                        QTimer.singleShot(1000, _check_georef_closed)

                QTimer.singleShot(350, _trigger_open_raster)
                return

            QMessageBox.warning(
                self,
                "Georeferencer",
                "Georeferencer action could not be found. Please ensure the Georeferencer GDAL plugin is enabled in Plugins → Manage and Install Plugins."
            )
        except Exception as e:
            QMessageBox.warning(self, "Georeferencer", f"Could not launch Georeferencer: {e}")

    def _on_update_lgu_layer_changed(self):
        """Populate geocode and barangay field dropdowns based on currently selected PSA Reference Layer."""
        if not hasattr(self, "update_geocode_combo") or not hasattr(self, "update_barangay_combo"):
            return
        layer = self.psa_layer_combo.currentLayer()
        self.update_geocode_combo.clear()
        self.update_barangay_combo.clear()

        if not layer or not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            return

        fields = [f.name() for f in layer.fields()]
        self.update_geocode_combo.addItems(fields)
        self.update_barangay_combo.addItems(fields)

        # Auto-suggest geocode field
        geo_idx = -1
        for candidate in ["geocode", "psgc", "code", "lgu_code", "psgc_code", "geo_code"]:
            for i, f in enumerate(fields):
                if candidate in f.lower().replace("_", ""):
                    geo_idx = i
                    break
            if geo_idx != -1:
                break
        if geo_idx != -1:
            self.update_geocode_combo.setCurrentIndex(geo_idx)

        # Auto-suggest barangay field
        bgy_idx = -1
        for candidate in ["barangay", "lgu_bgy_name", "bgy_name", "brgy_name", "brgy", "bgy"]:
            for i, f in enumerate(fields):
                if candidate in f.lower().replace("_", ""):
                    bgy_idx = i
                    break
            if bgy_idx != -1:
                break
        if bgy_idx != -1:
            self.update_barangay_combo.setCurrentIndex(bgy_idx)

    def _run_save_and_export_layer(self):
        """Pass parameters from embedded controls directly to Update Metadata (by Geocode) algorithm."""
        lgu_layer = self.psa_layer_combo.currentLayer()
        if not lgu_layer or not lgu_layer.isValid():
            QMessageBox.warning(self, "Invalid Layer", "Please select a valid PSA Reference / LGU Boundary Layer.")
            return

        geocode_field = self.update_geocode_combo.currentText()
        barangay_field = self.update_barangay_combo.currentText()

        # Resolve output directory: Layer folder on disk -> QGIS project folder -> User Documents
        source_path = lgu_layer.source().split("|")[0]
        out_dir = ""
        if os.path.isfile(source_path) or os.path.isdir(source_path):
            out_dir = os.path.dirname(source_path) if os.path.isfile(source_path) else source_path

        if not out_dir or not os.path.isdir(out_dir):
            proj_file = QgsProject.instance().fileName()
            if proj_file and os.path.isfile(proj_file):
                out_dir = os.path.dirname(proj_file)
            elif QgsProject.instance().homePath() and os.path.isdir(QgsProject.instance().homePath()):
                out_dir = QgsProject.instance().homePath()
            else:
                out_dir = os.path.expanduser("~/Documents")

        params = {
            "INPUT": lgu_layer,
            "GEOCODE_FIELD": geocode_field,
            "BARANGAY_FIELD": barangay_field,
            "SOURCE": "LGU",
            "SOURCE_YEAR": "2026",
            "OUTPUT_DIR": out_dir,
            "OPEN_OUTPUT": True,
            "OUTPUT": os.path.join(out_dir, "Updated_LGU.gpkg"),
        }

        # Provide immediate visual feedback to user
        orig_text = self.save_export_btn.text()
        self.save_export_btn.setEnabled(False)
        self.save_export_btn.setText("Updating & Exporting... Please wait...")
        self.save_export_btn.setStyleSheet("""
            QPushButton {
                background-color: #7F8C8D;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 18px;
                border-radius: 4px;
            }
        """)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            result = processing.runAndLoadResults("gmd_pipeline:update_lgu_by_geocode", params)
            out_path = result.get("OUTPUT", out_dir) if isinstance(result, dict) else out_dir
            QApplication.restoreOverrideCursor()
            QMessageBox.information(
                self,
                "Save & Export Successful",
                f"Successfully updated LGU boundary layer attributes and saved output!\n\nDestination: {out_path}"
            )
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Export Error", f"Could not save and export updated layer: {e}")
        finally:
            QApplication.restoreOverrideCursor()
            self.save_export_btn.setEnabled(True)
            self.save_export_btn.setText(orig_text)
            self.save_export_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27AE60;
                    color: white;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 8px 18px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #219A52;
                }
            """)

    # ── Tab 2: Geometry Check & Repair UI ──────────────────────────────────────
    def _build_geometry_tab(self):
        from .deprecated.geom_repair_toolkit import CheckerTab, HelpInfoTab

        layout = QVBoxLayout(self.tab2)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        toolkit_tabs = QTabWidget()
        self.geom_toolkit_checker = CheckerTab()
        self.geom_toolkit_help = HelpInfoTab()

        toolkit_tabs.addTab(self.geom_toolkit_checker, "Geometry Fixer")
        toolkit_tabs.addTab(self.geom_toolkit_help, "Help and Information")

        layout.addWidget(toolkit_tabs, stretch=1)

