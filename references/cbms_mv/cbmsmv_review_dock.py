# -*- coding: utf-8 -*-
"""
2027 CBMS Form 2 Map Validation (CBMS MV) - Review & Fix Navigation Dock
-------------------------------------------------------------------------
Compact, dockable review panel providing the Check & Update Navigation Pattern.
Allows stepping through flagged validation errors directly on the QGIS canvas,
synchronizing with the main Geotagged Building Points layer via map_uuid,
and launching QGIS's native Edit Feature Form for direct attribute editing.
"""

import os
from typing import Optional, List, Dict, Any

from qgis.core import (
    NULL,
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsApplication,
    QgsField,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal, QVariant
from qgis.PyQt.QtGui import QFont, QColor, QIcon
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
    QMessageBox,
    QApplication,
)

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


class CbmsMvReviewDock(QDockWidget):
    """
    QGIS Dockable Review Panel for inspecting and fixing CBMS Map Validation errors.
    Provides a compact, clutter-free navigation controller that zooms/flashes features
    on the QGIS map canvas and opens the native QGIS Feature Form for editing.
    """

    dock_closed = pyqtSignal()

    def __init__(
        self,
        parent_dialog,
        val_id: str,
        check_name: str,
        error_layer: QgsVectorLayer,
        main_layer: Optional[QgsVectorLayer] = None,
        start_index: int = 0,
    ):
        super().__init__(
            f"CBMS Review: {val_id}",
            parent_dialog.iface.mainWindow() if parent_dialog and parent_dialog.iface else None,
        )
        self.setObjectName(f"CbmsMvReviewDock_{val_id}")
        self.parent_dialog = parent_dialog
        self.iface = parent_dialog.iface if parent_dialog else None
        self.val_id = val_id
        self.check_name = check_name
        self.error_layer = error_layer
        self.main_layer = main_layer
        self.current_index = 0
        self.error_features: List[Dict[str, Any]] = []

        self.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
            | Qt.BottomDockWidgetArea
            | Qt.TopDockWidgetArea
        )

        self._extract_error_features()
        self._init_ui()
        self._apply_styling()

        if self.error_features:
            self.jump_to_index(min(start_index, len(self.error_features) - 1))

    # -----------------------------------------------------------------------
    # Data Preparation
    # -----------------------------------------------------------------------
    def _extract_error_features(self):
        """Extract all features from the error layer into a navigable list."""
        self.error_features.clear()
        if not self.error_layer or not self.error_layer.isValid():
            return

        field_names_lower = {f.name().lower(): f.name() for f in self.error_layer.fields()}
        fid_col = field_names_lower.get("sf_fid") or field_names_lower.get("fid") or field_names_lower.get("df_fid")
        uuid_col = field_names_lower.get("sf_map_uuid") or field_names_lower.get("map_uuid") or field_names_lower.get("df_map_uuid")

        def _is_empty(v):
            if v is None or v == NULL:
                return True
            s = str(v).strip()
            return not s or s.lower() in ("null", "none")

        for feat in self.error_layer.getFeatures():
            raw_fid = feat[fid_col] if fid_col else None
            source_fid = raw_fid if (fid_col and not _is_empty(raw_fid)) else feat.id()
            uuid_val = feat[uuid_col] if uuid_col else None
            uuid_str = str(uuid_val).strip() if uuid_val is not None else ""
            self.error_features.append({
                "fid": source_fid,
                "error_fid": feat.id(),
                "map_uuid": uuid_str,
                "feature": feat,
            })

    # -----------------------------------------------------------------------
    # UI Layout Construction
    # -----------------------------------------------------------------------
    def _init_ui(self):
        """Assemble the compact navigation panel with native QGIS Feature Form launcher."""
        main_widget = QWidget(self)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. Header Card: Rule Title & Check Information
        header_frame = QFrame()
        header_frame.setObjectName("dockHeaderFrame")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(2)

        lbl_rule_id = QLabel(f"🔴  {self.val_id}")
        lbl_rule_id.setStyleSheet("font-size: 11.5px; font-weight: bold; color: #C53030;")
        lbl_rule_id.setFont(QFont("Consolas", 9, QFont.Bold))

        lbl_check_name = QLabel(self.check_name)
        lbl_check_name.setWordWrap(True)
        lbl_check_name.setStyleSheet("font-size: 10.5px; color: #4A5568;")

        header_layout.addWidget(lbl_rule_id)
        header_layout.addWidget(lbl_check_name)
        layout.addWidget(header_frame)

        # 2. Navigation Bar: [ ◀ Prev ]  ( 3 of 12 )  [ Next ▶ ]
        nav_frame = QFrame()
        nav_frame.setObjectName("dockNavFrame")
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_prev = QPushButton("◀  Previous")
        self.btn_prev.setObjectName("btnNavPrev")
        self.btn_prev.setToolTip("Navigate to previous error feature")
        self.btn_prev.clicked.connect(self._on_prev)

        self.lbl_counter = QLabel("0 of 0")
        self.lbl_counter.setAlignment(Qt.AlignCenter)
        self.lbl_counter.setStyleSheet("font-weight: bold; font-size: 11.5px; color: #1A365D;")

        self.btn_next = QPushButton("Next  ▶")
        self.btn_next.setObjectName("btnNavNext")
        self.btn_next.setToolTip("Navigate to next error feature")
        self.btn_next.clicked.connect(self._on_next)

        btn_row.addWidget(self.btn_prev)
        btn_row.addWidget(self.lbl_counter, stretch=1)
        btn_row.addWidget(self.btn_next)
        nav_layout.addLayout(btn_row)

        # Feature Dropdown Quick Jump
        combo_row = QHBoxLayout()
        combo_row.setSpacing(6)
        lbl_jump = QLabel("Jump:")
        lbl_jump.setStyleSheet("font-size: 10.5px; color: #718096;")
        self.feature_combo = QComboBox()
        self.feature_combo.setObjectName("featureCombo")

        self.feature_combo.blockSignals(True)
        for idx, item in enumerate(self.error_features):
            uuid_or_fid = item["map_uuid"] if item["map_uuid"] else f"FID #{item['fid']}"
            display = f"#{idx+1}: {uuid_or_fid}"
            self.feature_combo.addItem(display, idx)
        self.feature_combo.blockSignals(False)

        combo_row.addWidget(lbl_jump)
        combo_row.addWidget(self.feature_combo, stretch=1)
        nav_layout.addLayout(combo_row)

        # Active Feature Info
        self.lbl_feat_info = QLabel("Target: —")
        self.lbl_feat_info.setStyleSheet(
            "font-size: 10px; color: #2D3748; padding: 3px 6px; background-color: #EDF2F7; border-radius: 3px;"
        )
        self.lbl_feat_info.setFont(QFont("Consolas", 9))
        self.lbl_feat_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        nav_layout.addWidget(self.lbl_feat_info)

        layout.addWidget(nav_frame)

        # 3. Actions Frame: [ Edit ] [ Save ] [ Return ]
        action_frame = QFrame()
        action_frame.setObjectName("dockActionFrame")
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(6, 6, 6, 6)
        action_layout.setSpacing(6)

        # Edit Feature Form Button
        self.btn_edit_form = QPushButton("Edit")
        self.btn_edit_form.setObjectName("btnEditForm")
        self.btn_edit_form.setToolTip("Open QGIS native Edit Feature Form for this building point")
        self.btn_edit_form.clicked.connect(self._on_open_feature_form)

        # Delete Feature Button (sets status to 'deleted')
        self.btn_delete_feat = QPushButton("Delete")
        self.btn_delete_feat.setObjectName("btnDeleteFeat")
        self.btn_delete_feat.setToolTip("Mark this building point as 'deleted' in status column")
        self.btn_delete_feat.clicked.connect(self._on_delete_feature)

        # Save Layer Changes Button
        self.btn_save_layer = QPushButton("Save")
        self.btn_save_layer.setObjectName("btnSaveLayer")
        self.btn_save_layer.setToolTip("Save layer edits permanently to disk")
        self.btn_save_layer.clicked.connect(self._on_save_layer_changes)

        # Return Button
        self.btn_return = QPushButton("Return")
        self.btn_return.setObjectName("btnReturn")
        self.btn_return.setToolTip("Close review dock and return to validation results")
        self.btn_return.clicked.connect(self.close)

        action_layout.addWidget(self.btn_edit_form)
        action_layout.addWidget(self.btn_delete_feat)
        action_layout.addWidget(self.btn_save_layer)
        action_layout.addWidget(self.btn_return)
        layout.addWidget(action_frame)

        layout.addStretch()

        self.setWidget(main_widget)

        # Connect combo signal after full UI layout is constructed
        self.feature_combo.currentIndexChanged.connect(self._on_combo_selected)

    # -----------------------------------------------------------------------
    # Navigation & Canvas Sync
    # -----------------------------------------------------------------------
    def jump_to_index(self, index: int):
        """Jump to the error feature at the specified index, synchronizing QGIS canvas."""
        if not self.error_features or index < 0 or index >= len(self.error_features):
            return

        self.current_index = index
        total = len(self.error_features)
        self.lbl_counter.setText(f"Feature {index + 1} of {total}")

        self.btn_prev.setEnabled(index > 0)
        self.btn_next.setEnabled(index < total - 1)

        self.feature_combo.blockSignals(True)
        self.feature_combo.setCurrentIndex(index)
        self.feature_combo.blockSignals(False)

        current_item = self.error_features[index]
        current_fid = current_item["fid"]
        current_uuid = current_item["map_uuid"]

        # Locate feature on main layer and error layer
        main_feat = self._find_main_feature(fid=current_fid, map_uuid=current_uuid)
        err_feat = current_item["feature"]

        # Check if feature is marked deleted
        target_feat = main_feat if main_feat else err_feat
        is_del = False
        if target_feat:
            for fn in [f.name() for f in target_feat.fields()]:
                if fn.lower() in ("status", "sf_status"):
                    v = target_feat[fn]
                    if v is not None and str(v).strip().lower() == "deleted":
                        is_del = True
                        break

        # Update display banner prioritizing fid
        info_parts = [f"FID #{current_fid}"]
        if current_uuid:
            info_parts.append(f"UUID: {current_uuid}")
        if is_del:
            info_parts.append("🔴 [DELETED]")
            if hasattr(self, "btn_delete_feat"):
                self.btn_delete_feat.setText("Deleted")
                self.btn_delete_feat.setStyleSheet("""
                    QPushButton {
                        background-color: #FED7D7;
                        color: #9B2C2C;
                        font-weight: 600;
                        padding: 6px 10px;
                        border-radius: 4px;
                        border: 1px solid #FEB2B2;
                        font-size: 11px;
                    }
                """)
        else:
            if hasattr(self, "btn_delete_feat"):
                self.btn_delete_feat.setText("Delete")
                self.btn_delete_feat.setStyleSheet("""
                    QPushButton {
                        background-color: #FFF5F5;
                        color: #C53030;
                        font-weight: 600;
                        padding: 6px 10px;
                        border-radius: 4px;
                        border: 1px solid #FEB2B2;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #FED7D7;
                        color: #9B2C2C;
                    }
                """)
        self.lbl_feat_info.setText(" | ".join(info_parts))

        # Synchronize QGIS map canvas
        self._sync_map_canvas(main_feat, err_feat)

    def jump_to_fid(self, fid: Any, target_uuid: Optional[str] = None):
        """Find feature in error_features by fid and jump to it, with fallback to map_uuid."""
        fid_str = str(fid).strip()
        for idx, item in enumerate(self.error_features):
            if str(item["fid"]).strip() == fid_str or str(item.get("error_fid", "")).strip() == fid_str:
                self.jump_to_index(idx)
                return
        if target_uuid:
            clean = str(target_uuid).strip().lower()
            for idx, item in enumerate(self.error_features):
                if item["map_uuid"].lower() == clean:
                    self.jump_to_index(idx)
                    return
        if self.error_features:
            self.jump_to_index(0)

    def jump_to_uuid(self, map_uuid: str):
        """Find feature in error_features by map_uuid and jump to it."""
        clean = str(map_uuid).strip().lower()
        for idx, item in enumerate(self.error_features):
            if item["map_uuid"].lower() == clean:
                self.jump_to_index(idx)
                return

    def _on_prev(self):
        """Navigate to the previous error feature."""
        if self.current_index > 0:
            self.jump_to_index(self.current_index - 1)

    def _on_next(self):
        """Navigate to the next error feature."""
        if self.current_index < len(self.error_features) - 1:
            self.jump_to_index(self.current_index + 1)

    def _on_combo_selected(self, index: int):
        """Handle dropdown selection jump."""
        if index >= 0:
            self.jump_to_index(index)

    # -----------------------------------------------------------------------
    # Feature Resolution & Map Synchronization
    # -----------------------------------------------------------------------
    def _find_main_feature(self, fid: Any = None, map_uuid: Optional[str] = None) -> Optional[QgsFeature]:
        """
        Query the main building points layer for the feature prioritizing fid, then map_uuid.
        Guarantees correct target resolution even with duplicate map_uuids.
        """
        if not self.main_layer or not self.main_layer.isValid():
            return None

        # Clean fid to avoid checking string 'NULL' or None
        clean_fid = None
        if fid is not None and fid != NULL:
            s = str(fid).strip()
            if s and s.lower() not in ("null", "none"):
                clean_fid = int(s) if s.isdigit() else fid

        # 1. Primary: Locate by native QGIS internal feature ID ($id)
        if clean_fid is not None:
            try:
                feat = self.main_layer.getFeature(int(clean_fid))
                if feat.isValid():
                    # If map_uuid is also provided, confirm it matches as a safety check
                    if not map_uuid:
                        return feat
                    clean_u = str(map_uuid).strip()
                    m_flds = {f.name().lower(): f.name() for f in self.main_layer.fields()}
                    u_col = m_flds.get("map_uuid") or m_flds.get("sf_map_uuid")
                    if not u_col or str(feat[u_col] or "").strip() == clean_u:
                        return feat
            except Exception:
                pass

        # 2. Fallback: by map_uuid (if internal feature ID shifted)
        if map_uuid:
            clean_uuid = str(map_uuid).strip().replace("'", "''")
            if clean_uuid and clean_uuid.lower() not in ("null", "none"):
                req = QgsFeatureRequest().setFilterExpression(f'"map_uuid" = \'{clean_uuid}\'')
                for feat in self.main_layer.getFeatures(req):
                    return feat

        # 3. Fallback: Locate by fid attribute if 'fid' field exists in main_layer
        if clean_fid is not None and "fid" in [f.name().lower() for f in self.main_layer.fields()]:
            try:
                if isinstance(clean_fid, int):
                    expr = f'"fid" = {clean_fid}'
                else:
                    expr = f'"fid" = \'{str(clean_fid).replace(chr(39), chr(39)+chr(39))}\''
                req = QgsFeatureRequest().setFilterExpression(expr)
                for feat in self.main_layer.getFeatures(req):
                    return feat
            except Exception:
                pass

        return None

    def _sync_map_canvas(self, main_feat: Optional[QgsFeature], err_feat: QgsFeature):
        """Zoom to feature, flash it on the canvas, set main layer active, and enable editing."""
        if not self.iface:
            return

        canvas = self.iface.mapCanvas()

        # Target layer for zoom and editing
        target_layer = self.main_layer if (self.main_layer and self.main_layer.isValid()) else self.error_layer
        target_feat = main_feat if main_feat else err_feat

        if not target_layer or not target_layer.isValid() or not target_feat:
            return

        fid = target_feat.id()

        try:
            # Select target layer and feature
            self.iface.setActiveLayer(target_layer)
            target_layer.selectByIds([fid])

            # Ensure layer is editable for quick fixes
            if not target_layer.isEditable():
                target_layer.startEditing()

            # Zoom and flash on canvas
            if target_layer.isSpatial():
                canvas.zoomToFeatureIds(target_layer, [fid])
                canvas.flashFeatureIds(target_layer, [fid])
                canvas.refresh()
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Native QGIS Feature Form Launch & Disk Persistence
    # -----------------------------------------------------------------------
    def _on_open_feature_form(self):
        """Open QGIS native Edit Feature Form dialog for the active main feature."""
        if not self.error_features or self.current_index >= len(self.error_features):
            return

        current_item = self.error_features[self.current_index]
        current_fid = current_item["fid"]
        current_uuid = current_item["map_uuid"]

        # Target layer
        target_layer = self.main_layer if (self.main_layer and self.main_layer.isValid()) else self.error_layer
        if not target_layer or not target_layer.isValid():
            QMessageBox.warning(self, "No Layer", "Target layer is not available for editing.")
            return

        # Target feature: locate on main layer first, fallback to error layer
        target_feat = self._find_main_feature(fid=current_fid, map_uuid=current_uuid) if self.main_layer else current_item["feature"]
        if not target_feat:
            target_feat = current_item["feature"]

        if not target_feat or not target_feat.isValid():
            QMessageBox.warning(
                self,
                "Feature Not Found",
                f"Could not locate feature (FID: {current_fid}, UUID: {current_uuid}) in '{target_layer.name()}'.",
            )
            return

        if self.iface:
            # Set target layer as active in QGIS
            self.iface.setActiveLayer(target_layer)

            # Ensure layer is editable
            if not target_layer.isEditable():
                target_layer.startEditing()

            # Select and center
            target_layer.selectByIds([target_feat.id()])

            # Open native QGIS Feature Form dialog (modal=True waits for user input)
            accepted = self.iface.openFeatureForm(target_layer, target_feat, False, True)

            # Refresh canvas if edits were accepted
            if accepted and self.iface.mapCanvas():
                self.iface.mapCanvas().refresh()

    def _on_save_layer_changes(self):
        """Commit layer editing changes to the physical GeoJSON file on disk."""
        if not self.main_layer or not self.main_layer.isValid():
            return

        if not self.main_layer.isEditable():
            QMessageBox.information(self, "No Edits", "The layer has no pending edits to save.")
            return

        reply = QMessageBox.question(
            self,
            "Save Changes to Layer",
            f"Save all pending revisions permanently to '{self.main_layer.name()}' on disk?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            success = self.main_layer.commitChanges()
            if success:
                # Re-open editing buffer for seamless continued editing
                self.main_layer.startEditing()
                QMessageBox.information(self, "Saved", "Layer edits successfully saved to disk.")
            else:
                commit_errors = self.main_layer.commitErrors()
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Failed to commit edits to layer:\n{commit_errors}",
                )

    def _on_delete_feature(self):
        """Mark the active building point as 'deleted' in its status column."""
        if not self.error_features or self.current_index >= len(self.error_features):
            return

        current_item = self.error_features[self.current_index]
        current_fid = current_item["fid"]
        current_uuid = current_item["map_uuid"]
        err_feat = current_item["feature"]
        main_feat = self._find_main_feature(fid=current_fid, map_uuid=current_uuid) if self.main_layer else None

        target_feat = main_feat if main_feat else err_feat
        is_already_deleted = False
        if target_feat:
            for fn in [f.name() for f in target_feat.fields()]:
                if fn.lower() in ("status", "sf_status"):
                    v = target_feat[fn]
                    if v is not None and str(v).strip().lower() == "deleted":
                        is_already_deleted = True
                        break

        if is_already_deleted:
            reply = QMessageBox.question(
                self,
                "Restore Feature?",
                f"Feature FID #{current_fid} is currently marked as 'deleted'.\n\nDo you want to restore it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            new_status = ""
        else:
            new_status = "deleted"

        # Update main_layer
        if self.main_layer and self.main_layer.isValid() and main_feat:
            m_idx = -1
            for f in self.main_layer.fields():
                if f.name().lower() in ("status", "sf_status"):
                    m_idx = self.main_layer.fields().indexOf(f.name())
                    break
            if m_idx == -1:
                try:
                    self.main_layer.dataProvider().addAttributes([QgsField("status", QVariant.String)])
                    self.main_layer.updateFields()
                    m_idx = self.main_layer.fields().indexOf("status")
                except Exception:
                    pass
            if m_idx != -1:
                if not self.main_layer.isEditable():
                    self.main_layer.startEditing()
                self.main_layer.changeAttributeValue(main_feat.id(), m_idx, new_status)

        # Update error_layer
        if self.error_layer and self.error_layer.isValid() and err_feat:
            e_idx = -1
            for f in self.error_layer.fields():
                if f.name().lower() in ("status", "sf_status"):
                    e_idx = self.error_layer.fields().indexOf(f.name())
                    break
            if e_idx != -1:
                if not self.error_layer.isEditable():
                    self.error_layer.startEditing()
                self.error_layer.changeAttributeValue(err_feat.id(), e_idx, new_status)

        # Sync back to parent dialog table if open
        if self.parent_dialog and hasattr(self.parent_dialog, "_sync_feature_status"):
            self.parent_dialog._sync_feature_status(self.val_id, current_fid, current_uuid, new_status)

        # Refresh UI
        self.jump_to_index(self.current_index)
        if self.iface and self.iface.mapCanvas():
            self.iface.mapCanvas().refresh()

    # -----------------------------------------------------------------------
    # Dock Lifecycle & Close Event
    # -----------------------------------------------------------------------
    def closeEvent(self, event):
        """Handle dock widget closure: restore parent dialog and remove dock from QGIS."""
        if is_valid_qobject(self.parent_dialog):
            try:
                self.parent_dialog.show()
                self.parent_dialog.showNormal()
                self.parent_dialog.raise_()
                self.parent_dialog.activateWindow()
            except (RuntimeError, Exception):
                self.parent_dialog = None

        if self.iface and hasattr(self.iface, "removeDockWidget"):
            try:
                self.iface.removeDockWidget(self)
            except Exception:
                pass

        try:
            self.dock_closed.emit()
        except Exception:
            pass

        event.accept()

    # -----------------------------------------------------------------------
    # Styling
    # -----------------------------------------------------------------------
    def _apply_styling(self):
        """Apply modern, compact styling conforming to GEMMA plugin standards."""
        self.setStyleSheet("""
            QDockWidget {
                font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
                font-size: 11px;
                color: #2D3748;
            }
            #dockHeaderFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-left: 4px solid #E53E3E;
                border-radius: 5px;
            }
            #dockNavFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 5px;
            }
            #dockActionFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 5px;
            }
            #btnNavPrev, #btnNavNext {
                background-color: #EDF2F7;
                color: #2B6CB0;
                font-weight: 600;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid #CBD5E0;
                font-size: 11px;
            }
            #btnNavPrev:hover, #btnNavNext:hover {
                background-color: #E2E8F0;
                color: #1A365D;
            }
            #btnNavPrev:disabled, #btnNavNext:disabled {
                background-color: #F7FAFC;
                color: #A0AEC0;
                border-color: #E2E8F0;
            }
            #btnEditForm {
                background-color: #2B6CB0;
                color: #FFFFFF;
                font-weight: 600;
                padding: 6px 10px;
                border-radius: 4px;
                border: none;
                font-size: 11px;
            }
            #btnEditForm:hover {
                background-color: #2C5282;
            }
            #btnDeleteFeat {
                background-color: #FFF5F5;
                color: #C53030;
                font-weight: 600;
                padding: 6px 10px;
                border-radius: 4px;
                border: 1px solid #FEB2B2;
                font-size: 11px;
            }
            #btnDeleteFeat:hover {
                background-color: #FED7D7;
                color: #9B2C2C;
            }
            #btnSaveLayer {
                background-color: #27AE60;
                color: #FFFFFF;
                font-weight: 600;
                padding: 6px 10px;
                border-radius: 4px;
                border: none;
                font-size: 11px;
            }
            #btnSaveLayer:hover {
                background-color: #219653;
            }
            #btnReturn {
                background-color: #718096;
                color: #FFFFFF;
                font-weight: 600;
                padding: 6px 10px;
                border-radius: 4px;
                border: none;
                font-size: 11px;
            }
            #btnReturn:hover {
                background-color: #4A5568;
            }
            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E0;
                border-radius: 4px;
                padding: 3px 6px;
                color: #2D3748;
                font-size: 11px;
            }
            QComboBox:focus {
                border: 1.5px solid #3182CE;
            }
        """)
