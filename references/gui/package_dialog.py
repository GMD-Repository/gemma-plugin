"""
    PackageDialog class for exporting QGIS projects to QField.

    Note: This plugin is designed to facilitate the export of QGIS projects to QField.
    Plugin Name: AuQCBMS 
    Plugin Version: 1.0.2
    Copyright (C) 2024 GMDev Team. All rights reserved.

    ------------------------------------------

    Modified Version: QField 4.11.0
Copyright (C) 2024 QField Team.
"""

import os
import subprocess
import json
import traceback
import shutil  # Add this import at the top of your file
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from libqfieldsync.layer import LayerSource, SyncAction
from libqfieldsync.offline_converter import ExportType, OfflineConverter, PackagingCanceledError
import sys
from qgis import utils
# TODO this try/catch was added due to module structure changes in QFS 4.8.0. Remove this as enough time has passed since March 2024.
try:
    from libqfieldsync.offliners import QgisCoreOffliner
except ModuleNotFoundError:
    from qgis.PyQt.QtCore import QCoreApplication, QTimer
    from qgis.PyQt.QtWidgets import QMessageBox

    QMessageBox.warning(
        None,
        QCoreApplication.translate("AuQCBMS", "Please restart QGIS"),
        QCoreApplication.translate(
            "AuQCBMS", "To finalize the AuQCBMS upgrade, please restart QGIS."
        ),
    )
from libqfieldsync.project import ProjectConfiguration
from libqfieldsync.project_checker import ProjectChecker
from libqfieldsync.utils.file_utils import fileparts
from libqfieldsync.utils.qgis import get_project_title
from qgis.core import Qgis, QgsApplication, QgsProject, QgsLayerTreeGroup, QgsLayerTreeLayer, QgsVectorLayer, QgsRasterLayer, QgsVectorFileWriter, QgsTask, QgsTaskManager, QgsSnappingConfig, QgsTolerance, QgsGeometry, QgsFeatureRequest, QgsCoordinateTransform
from qgis.PyQt.QtCore import QDir, Qt, QUrl, QTimer, QEvent
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox, QLabel, QListWidget, QListWidgetItem, QWidget, QHBoxLayout, QPushButton, QComboBox, QGridLayout, QGroupBox, QSizePolicy, QScrollArea, QFrame, QVBoxLayout, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QTreeWidget, QTreeWidgetItem, QTabWidget, QLineEdit, QInputDialog, QFileDialog
from qgis.PyQt.uic import loadUiType
from .checker_feedback_table import CheckerFeedbackTable
from ..core.preferences import Preferences
from .dirs_to_copy_widget import DirsToCopyWidget
from .project_configuration_dialog import ProjectConfigurationDialog
import processing
from ..utils.qt_utils import make_folder_selector
from ..utils.style_utils import (
    get_qml_styles_dir,
    get_available_qml_display_names,
    auto_detect_qml_for_layer,
    apply_qml_to_layer,
    apply_embedded_qml_styles,
)
from tempfile import TemporaryDirectory
import re
from qgis.utils import iface
from qgis.gui import QgsFileWidget
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QFileDialog

DialogUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/package_dialog.ui")
)


class MultiSelectDialog(QDialog):
    def __init__(self, title, label_text, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        self.setMinimumHeight(240)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel(label_text)
        layout.addWidget(self.label)
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_widget.addItems(items)
        layout.addWidget(self.list_widget)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
    def selected_items(self):
        return [item.text() for item in self.list_widget.selectedItems()]


class LayerGroupsTreeWidget(QTreeWidget):
    def dragMoveEvent(self, event):
        selected_items = self.selectedItems()
        if not selected_items:
            event.ignore()
            return
            
        old_parent = selected_items[0].parent()
        if old_parent is None:
            event.ignore()
            return
            
        drop_target = self.itemAt(event.pos())
        if not drop_target:
            event.ignore()
            return
            
        target_parent = drop_target if drop_target.parent() is None else drop_target.parent()
        if target_parent != old_parent:
            event.ignore()
            return
            
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        selected_items = self.selectedItems()
        if not selected_items:
            event.ignore()
            return
            
        old_parent = selected_items[0].parent()
        if old_parent is None:
            event.ignore()
            return
            
        drop_target = self.itemAt(event.pos())
        if not drop_target:
            event.ignore()
            return
            
        target_parent = drop_target if drop_target.parent() is None else drop_target.parent()
        if target_parent != old_parent:
            event.ignore()
            return
            
        self._dragged_combos = {}
        for item in selected_items:
            combo = self.itemWidget(item, 1)
            self._dragged_combos[item.text(0)] = combo.currentText() if combo else ""
            
        super().dropEvent(event)
        QTimer.singleShot(0, self._restore_missing_combos)
        
    def _restore_missing_combos(self):
        for i in range(self.topLevelItemCount()):
            group_item = self.topLevelItem(i)
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                if self.itemWidget(layer_item, 1) is None:
                    preset = getattr(self, '_dragged_combos', {}).get(layer_item.text(0), "")
                    # PackageDialog is the parent widget or accessible via tree parent
                    dlg = self.parent()
                    while dlg and not hasattr(dlg, '_create_qml_combo_for_layer'):
                        dlg = dlg.parent()
                    if dlg:
                        dlg._create_qml_combo_for_layer(layer_item, layer_item.text(0), preset_qml=preset)


class PackageDialog(QDialog, DialogUi):
    def _normalized_layer_name(self, name):
        """Strip trailing count labels like ' [123]' from a layer display name."""
        if not name:
            return ""
        return re.sub(r"\s*\[\d+\]\s*$", "", name).strip()

    def _ensure_ea_update_not_offline_and_writable(self):
        """Keep _ea_update layers writable and out of OFFLINE sync action."""
        project = QgsProject.instance()

        for layer in project.mapLayers().values():
            layer_name = self._normalized_layer_name(layer.name()).lower()
            if not layer_name.endswith('_ea_update'):
                continue

            try:
                if isinstance(layer, QgsVectorLayer):
                    layer.setReadOnly(False)
                project.writeEntry("ReadOnlyLayers", layer.id(), "False")
            except Exception:
                pass

            try:
                layer_source = LayerSource(layer)
                available_actions = [a for a, _ in layer_source.available_actions]
                if layer_source.action == SyncAction.OFFLINE:
                    candidate = None
                    if hasattr(SyncAction, "COPY") and SyncAction.COPY in available_actions:
                        candidate = SyncAction.COPY
                    else:
                        for action in available_actions:
                            if action not in (SyncAction.OFFLINE, SyncAction.REMOVE):
                                candidate = action
                                break
                    if candidate is not None:
                        layer_source.action = candidate
                        layer_source.apply()
            except Exception:
                pass

    def filter_geocode_by_citymun(self):
        """Filter geocode_dropdown based on selected citymun_dropdown value."""
        selected_citymun = self.citymun_dropdown.currentText()
        if selected_citymun.lower() == "all":
            self.populate_geocode_dropdown()
            return
        citymun_prefix = selected_citymun.split('_')[0]

        # Get the layer
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == sel_name:
                    selected_layer = lyr
                    break

        self.geocode_dropdown.clear()
        desired = '_ea' if self.output_dropdown.currentText() == self.tr('EA Level') else '_bgy'
        if selected_layer and selected_layer.name().endswith(desired):
            geocode_index = selected_layer.fields().indexOf('geocode')
            geocode_name_index = selected_layer.fields().indexOf('barangay')
            if geocode_name_index == -1:
                geocode_name_index = selected_layer.fields().indexOf('Barangay')
            if geocode_index != -1 and geocode_name_index != -1:
                filtered_values = [
                    f"{feature.attributes()[geocode_index]}_{feature.attributes()[geocode_name_index]}"
                    for feature in selected_layer.getFeatures()
                    if str(feature.attributes()[geocode_index])[:5] == citymun_prefix
                ]
                self.geocode_dropdown.addItems(sorted(filtered_values))
                print(f"Filtered geocode values for citymun {selected_citymun}: {filtered_values}")
            else:
                print("Missing geocode or barangay field.")

    def _get_active_project_layers(self):
        """Return a list of layer names currently in the QGIS project."""
        project = QgsProject.instance()
        return [layer.name() for layer in project.mapLayers().values()]

    def _get_already_grouped_layers(self):
        """Return a set of layer names that are checked in any group."""
        assigned = set()
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            group_item = self.layer_groups_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                if layer_item.checkState(0) == Qt.Checked:
                    assigned.add(layer_item.text(0))
        return assigned

    def _update_layer_visibility(self):
        # Build mapping of layer_name -> first group item where it is checked
        checked_layers = {}
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            group_item = self.layer_groups_tree.topLevelItem(i)
            # If the group itself is unchecked, its checked layers shouldn't claim/hide layers in other groups
            if group_item.checkState(0) == Qt.Unchecked:
                continue
                
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                if layer_item.checkState(0) == Qt.Checked:
                    layer_name = layer_item.text(0)
                    if layer_name not in checked_layers:
                        checked_layers[layer_name] = group_item

        # Update visibility across all groups
        self.layer_groups_tree.blockSignals(True)
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            group_item = self.layer_groups_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                layer_name = layer_item.text(0)
                # If layer is checked somewhere else in an active (checked) group, hide it here
                if layer_name in checked_layers and checked_layers[layer_name] != group_item:
                    layer_item.setHidden(True)
                    if layer_item.checkState(0) == Qt.Checked:
                        layer_item.setCheckState(0, Qt.Unchecked)
                else:
                    layer_item.setHidden(False)
        self.layer_groups_tree.blockSignals(False)

    def _on_tree_item_changed(self, item, column):
        self._update_layer_visibility()

    def _create_qml_combo_for_layer(self, layer_item, layer_name, preset_qml=""):
        """Create a QComboBox for QML style selection and set it on column 1.

        If *preset_qml* is provided it takes priority; otherwise auto-detect.
        """
        available = get_available_qml_display_names()
        combo = QComboBox()
        combo.addItem(self.tr("(None)"))
        combo.addItems(available)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        saved_role = layer_item.data(1, Qt.UserRole)
        if saved_role:
            preset_qml = saved_role

        # Determine which value to select
        if preset_qml and preset_qml in available:
            combo.setCurrentText(preset_qml)
        else:
            detected = auto_detect_qml_for_layer(layer_name, available)
            if detected:
                combo.setCurrentText(detected)

        layer_item.setData(1, Qt.UserRole, combo.currentText())
        combo.currentTextChanged.connect(lambda text, lname=layer_name: self._on_qml_combo_changed(lname, text))

        self.layer_groups_tree.setItemWidget(layer_item, 1, combo)
        return combo

    def _on_qml_combo_changed(self, layer_name, new_text):
        """Sync QML style combo box for a specific layer across all groups."""
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            group_item = self.layer_groups_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                if layer_item.text(0) == layer_name:
                    layer_item.setData(1, Qt.UserRole, new_text)
                    combo = self.layer_groups_tree.itemWidget(layer_item, 1)
                    if combo and combo.currentText() != new_text:
                        combo.blockSignals(True)
                        combo.setCurrentText(new_text)
                        combo.blockSignals(False)

    def _refresh_all_qml_combos(self):
        """Rebuild QML combo choices for every layer item without losing selection."""
        available = get_available_qml_display_names()
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            group_item = self.layer_groups_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                combo = self.layer_groups_tree.itemWidget(layer_item, 1)
                if combo:
                    old_value = combo.currentText()
                    combo.blockSignals(True)
                    combo.clear()
                    combo.addItem(self.tr("(None)"))
                    combo.addItems(available)
                    if old_value in available:
                        combo.setCurrentText(old_value)
                    elif old_value == self.tr("(None)"):
                        combo.setCurrentText(self.tr("(None)"))
                    combo.blockSignals(False)

    def _on_add_layer_group(self):
        group_name = self.group_name_input.text().strip()
        if not group_name:
            QMessageBox.warning(self, self.tr("Warning"), self.tr("Please enter a group name."))
            return

        # Check if group already exists
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            if self.layer_groups_tree.topLevelItem(i).text(0) == group_name:
                QMessageBox.warning(self, self.tr("Warning"), self.tr("Group already exists."))
                return

        # Create new group item
        group_item = QTreeWidgetItem(self.layer_groups_tree)
        group_item.setText(0, group_name)
        group_item.setFlags(group_item.flags() | Qt.ItemIsUserCheckable)
        group_item.setCheckState(0, Qt.Checked)

        # Populate with ALL active layers
        active_layers = self._get_active_project_layers()
        
        available = get_available_qml_display_names()
        def layer_sort_key(lname):
            detected = auto_detect_qml_for_layer(lname, available)
            return (0, detected) if detected else (1, lname)
        active_layers.sort(key=layer_sort_key)
        
        self.layer_groups_tree.blockSignals(True)
        for layer_name in active_layers:
            layer_item = QTreeWidgetItem(group_item)
            layer_item.setText(0, layer_name)
            layer_item.setFlags(layer_item.flags() | Qt.ItemIsUserCheckable)
            layer_item.setCheckState(0, Qt.Unchecked)
            self._create_qml_combo_for_layer(layer_item, layer_name)
        self.layer_groups_tree.blockSignals(False)

        self.layer_groups_tree.expandItem(group_item)
        self.group_name_input.clear()
        self._update_layer_visibility()

    def _on_delete_layer_group(self):
        selected_items = self.layer_groups_tree.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            if item.parent() is None: # Top level item (Group)
                index = self.layer_groups_tree.indexOfTopLevelItem(item)
                self.layer_groups_tree.takeTopLevelItem(index)
                
        self._update_layer_visibility()


    def _on_move_item_up(self):
        selected_items = self.layer_groups_tree.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        parent = item.parent()
        
        if parent:
            index = parent.indexOfChild(item)
            if index > 0:
                combo = self.layer_groups_tree.itemWidget(item, 1)
                selected_text = combo.currentText() if combo else None
                parent.takeChild(index)
                parent.insertChild(index - 1, item)
                if selected_text:
                    self._create_qml_combo_for_layer(item, item.text(0), preset_qml=selected_text)
                self.layer_groups_tree.setCurrentItem(item)
        else:
            index = self.layer_groups_tree.indexOfTopLevelItem(item)
            if index > 0:
                self.layer_groups_tree.takeTopLevelItem(index)
                self.layer_groups_tree.insertTopLevelItem(index - 1, item)
                self.layer_groups_tree.setCurrentItem(item)
                
    def _on_move_item_down(self):
        selected_items = self.layer_groups_tree.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        parent = item.parent()
        
        if parent:
            index = parent.indexOfChild(item)
            if index < parent.childCount() - 1:
                combo = self.layer_groups_tree.itemWidget(item, 1)
                selected_text = combo.currentText() if combo else None
                parent.takeChild(index)
                parent.insertChild(index + 1, item)
                if selected_text:
                    self._create_qml_combo_for_layer(item, item.text(0), preset_qml=selected_text)
                self.layer_groups_tree.setCurrentItem(item)
        else:
            index = self.layer_groups_tree.indexOfTopLevelItem(item)
            if index < self.layer_groups_tree.topLevelItemCount() - 1:
                self.layer_groups_tree.takeTopLevelItem(index)
                self.layer_groups_tree.insertTopLevelItem(index + 1, item)
                self.layer_groups_tree.setCurrentItem(item)

    def _on_save_groups_preset(self):
        # Ask for a preset name
        preset_name, ok = QInputDialog.getText(self, self.tr("Save Preset"), self.tr("Enter preset name:"))
        if not ok or not preset_name.strip():
            return
        preset_name = preset_name.strip()

        preset_data = {}
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            group_item = self.layer_groups_tree.topLevelItem(i)
            group_name = group_item.text(0)
            all_layers_in_group = []
            checked_layers = []
            qml_styles = {}
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                layer_name = layer_item.text(0)
                all_layers_in_group.append(layer_name)
                if layer_item.checkState(0) == Qt.Checked:
                    checked_layers.append(layer_name)
                # Save QML assignment for every layer (checked or not)
                combo = self.layer_groups_tree.itemWidget(layer_item, 1)
                if combo and combo.currentText() != self.tr("(None)"):
                    qml_styles[layer_name] = combo.currentText()
            preset_data[group_name] = {
                "all_layers": all_layers_in_group,
                "checked_layers": checked_layers,
                "group_checked": group_item.checkState(0) == Qt.Checked,
                "qml_styles": qml_styles,
            }
            
        settings = QSettings()
        all_presets_json = settings.value("qfieldmod/layer_groups_presets_dict", "{}")
        try:
            all_presets = json.loads(all_presets_json)
        except Exception:
            all_presets = {}
            
        all_presets[preset_name] = preset_data
        settings.setValue("qfieldmod/layer_groups_presets_dict", json.dumps(all_presets))
        QMessageBox.information(self, self.tr("Success"), self.tr(f"Preset '{preset_name}' saved successfully."))

    def _on_load_groups_preset(self):
        settings = QSettings()
        all_presets_json = settings.value("qfieldmod/layer_groups_presets_dict", "{}")
        try:
            all_presets = json.loads(all_presets_json)
        except Exception:
            all_presets = {}
            
        if not all_presets:
            QMessageBox.information(self, self.tr("Info"), self.tr("No presets found."))
            return
            
        preset_name, ok = QInputDialog.getItem(self, self.tr("Load Preset"), self.tr("Select preset:"), list(all_presets.keys()), 0, False)
        if not ok or not preset_name:
            return
            
        preset_data = all_presets.get(preset_name, {})
            
        self.layer_groups_tree.clear()
        self.layer_groups_tree.blockSignals(True)
        
        active_layers_set = set(self._get_active_project_layers())
        
        for group_name, data in preset_data.items():
            group_item = QTreeWidgetItem(self.layer_groups_tree)
            group_item.setText(0, group_name)
            group_item.setFlags(group_item.flags() | Qt.ItemIsUserCheckable)
            
            if isinstance(data, dict):
                group_checked = data.get("group_checked", True)
                checked_layers = data.get("checked_layers", [])
                saved_qml_styles = data.get("qml_styles", {})
                all_layers_in_group = data.get("all_layers", [])
            else:
                group_checked = True
                checked_layers = data
                saved_qml_styles = {}
                all_layers_in_group = []
                
            group_item.setCheckState(0, Qt.Checked if group_checked else Qt.Unchecked)
            
            # If all_layers is missing (e.g. older preset fallback), sort active_layers_set based on QML matching
            if not all_layers_in_group:
                all_layers_in_group = list(active_layers_set)
                available = get_available_qml_display_names()
                def layer_sort_key(lname):
                    detected = auto_detect_qml_for_layer(lname, available)
                    return (0, detected) if detected else (1, lname)
                all_layers_in_group.sort(key=layer_sort_key)
                
            # Create items in saved order
            for layer_name in all_layers_in_group:
                if layer_name not in active_layers_set:
                    continue
                layer_item = QTreeWidgetItem(group_item)
                layer_item.setText(0, layer_name)
                layer_item.setFlags(layer_item.flags() | Qt.ItemIsUserCheckable)
                if layer_name in checked_layers:
                    layer_item.setCheckState(0, Qt.Checked)
                else:
                    layer_item.setCheckState(0, Qt.Unchecked)
                preset_qml = saved_qml_styles.get(layer_name, "")
                self._create_qml_combo_for_layer(layer_item, layer_name, preset_qml=preset_qml)
                
            # Append any newly added active layers that aren't in the preset group
            for layer_name in active_layers_set:
                if layer_name not in all_layers_in_group:
                    layer_item = QTreeWidgetItem(group_item)
                    layer_item.setText(0, layer_name)
                    layer_item.setFlags(layer_item.flags() | Qt.ItemIsUserCheckable)
                    layer_item.setCheckState(0, Qt.Unchecked)
                    self._create_qml_combo_for_layer(layer_item, layer_name)
                    
            self.layer_groups_tree.expandItem(group_item)
            
        self.layer_groups_tree.blockSignals(False)
        self._update_layer_visibility()

    def _on_delete_groups_preset(self):
        settings = QSettings()
        all_presets_json = settings.value("qfieldmod/layer_groups_presets_dict", "{}")
        try:
            all_presets = json.loads(all_presets_json)
        except Exception:
            all_presets = {}
            
        if not all_presets:
            QMessageBox.information(self, self.tr("Info"), self.tr("No presets found to delete."))
            return
            
        dialog = MultiSelectDialog(
            self.tr("Delete Presets"),
            self.tr("Select preset(s) to delete (Hold Shift/Ctrl for multiple selection):"),
            list(all_presets.keys()),
            self
        )
        if dialog.exec_() == QDialog.Accepted:
            selected = dialog.selected_items()
            if not selected:
                return
            
            presets_str = ", ".join(selected)
            reply = QMessageBox.question(self, self.tr("Confirm Delete"), 
                                         self.tr(f"Are you sure you want to delete the selected preset(s)?\n\n{presets_str}"),
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                                         
            if reply == QMessageBox.Yes:
                for name in selected:
                    all_presets.pop(name, None)
                settings.setValue("qfieldmod/layer_groups_presets_dict", json.dumps(all_presets))
                QMessageBox.information(self, self.tr("Success"), self.tr("Selected preset(s) deleted successfully."))

    def _on_apply_layer_groups(self):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        
        # First, flatten the tree: move all layers back to the root
        all_layers = root.findLayers()
        for layer_node in all_layers:
            if layer_node.parent() != root:
                cloned = layer_node.clone()
                root.insertChildNode(0, cloned)
                layer_node.parent().removeChildNode(layer_node)
                
        # Then, remove all old groups
        for group in root.findGroups():
            root.removeChildNode(group)

        styled_count = 0
        styled_layers = set()
        
        for i in range(self.layer_groups_tree.topLevelItemCount()):
            group_item = self.layer_groups_tree.topLevelItem(i)
            
            # Apply styles to ALL layers in the tree, even if unchecked or in unchecked group
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                layer_name = layer_item.text(0)
                if layer_name not in styled_layers:
                    combo = self.layer_groups_tree.itemWidget(layer_item, 1)
                    if combo:
                        qml_name = combo.currentText()
                        if qml_name and qml_name != self.tr("(None)"):
                            qgis_layer = project.mapLayersByName(layer_name)
                            if qgis_layer:
                                if apply_qml_to_layer(qgis_layer[0], qml_name):
                                    styled_count += 1
                                    styled_layers.add(layer_name)
            
            # If the group name is unchecked, skip applying grouping to QGIS
            if group_item.checkState(0) == Qt.Unchecked:
                continue
                
            group_name = group_item.text(0)
            
            # Check if group exists, else create
            qgis_group = root.findGroup(group_name)
            if not qgis_group:
                qgis_group = root.addGroup(group_name)
                
            # Move checked layers into this group
            for j in range(group_item.childCount()):
                layer_item = group_item.child(j)
                if layer_item.checkState(0) == Qt.Checked:
                    layer_name = layer_item.text(0)
                    # Find layer in root
                    layer_tree_layer = root.findLayer(project.mapLayersByName(layer_name)[0].id()) if project.mapLayersByName(layer_name) else None
                    
                    if layer_tree_layer:
                        # Clone the layer node
                        cloned_layer = layer_tree_layer.clone()
                        # Add to the new group
                        qgis_group.insertChildNode(0, cloned_layer)
                        # Remove original
                        layer_tree_layer.parent().removeChildNode(layer_tree_layer)

        msg = self.tr("Groups applied to QGIS Layers Panel.")
        if styled_count:
            msg += "\n" + self.tr(f"{styled_count} layer(s) styled with QML.")
        QMessageBox.information(self, self.tr("Success"), msg)

    def _on_import_qml_styles(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Select QML Styles"), "", "QML Files (*.qml)"
        )
        if not files:
            return

        dest_folder = get_qml_styles_dir()
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)

        copied = 0
        for fpath in files:
            fname = os.path.basename(fpath)
            shutil.copy2(fpath, os.path.join(dest_folder, fname))
            copied += 1

        if copied:
            self._refresh_all_qml_combos()
            QMessageBox.information(
                self, self.tr("Success"),
                self.tr(f"{copied} QML file(s) imported successfully.")
            )
    def update_button_box_visibility(self):
        """Update visibility of the button box based on current tab and page."""
        if hasattr(self, 'main_tab_widget') and hasattr(self, 'button_box'):
            if self.main_tab_widget.currentIndex() == 0:
                self.button_box.setVisible(False)
            else:
                if hasattr(self, 'stackedWidget') and hasattr(self, 'packagePage'):
                    if self.stackedWidget.currentWidget() == self.packagePage:
                        self.button_box.setVisible(True)
                    else:
                        self.button_box.setVisible(False)
                else:
                    self.button_box.setVisible(True)

    def _on_tab_changed(self, index):
        self.update_button_box_visibility()

    def __init__(self, iface, project, offline_editing, parent=None):
        """Constructor."""
        super(PackageDialog, self).__init__(parent=parent)
        self.setupUi(self)

        # Add Help button to upper right
        self.help_button = QPushButton(self.tr("Help"))
        self.help_button.clicked.connect(self.show_help)
        _help_layout = QHBoxLayout()
        _help_layout.addStretch()
        _help_layout.addWidget(self.help_button)
        self.verticalLayout_3.insertLayout(0, _help_layout)

        # Wrap the stackedWidget in a QScrollArea so the dialog is scrollable.
        # The button_box (Export/Reset/Close) stays outside, always visible.
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.NoFrame)
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for _i in range(self.verticalLayout_3.count()):
            _item = self.verticalLayout_3.itemAt(_i)
            if _item and _item.widget() is self.stackedWidget:
                self.verticalLayout_3.takeAt(_i)
                break
        _scroll.setWidget(self.stackedWidget)
        
        # Create a QTabWidget to hold the existing UI and the new tab
        self.main_tab_widget = QTabWidget()
        
        # First tab for additional features (Prepare Project Layers)
        self.tab_additional = QWidget()
        self.tab_additional_layout = QVBoxLayout(self.tab_additional)
        
        group_controls_layout = QHBoxLayout()
        self.group_name_input = QLineEdit()
        self.group_name_input.setPlaceholderText(self.tr("Enter group name..."))
        
        self.add_group_btn = QPushButton("+")
        self.add_group_btn.setFixedWidth(40)
        self.add_group_btn.setStyleSheet("color: green; font-weight: bold; font-size: 16px;")
        
        self.delete_group_btn = QPushButton("-")
        self.delete_group_btn.setFixedWidth(40)
        self.delete_group_btn.setStyleSheet("color: red; font-weight: bold; font-size: 16px;")
        
        self.move_up_btn = QPushButton("↑")
        self.move_up_btn.setFixedWidth(30)
        self.move_up_btn.setStyleSheet("color: blue; font-weight: bold; font-size: 16px;")
        
        self.move_down_btn = QPushButton("↓")
        self.move_down_btn.setFixedWidth(30)
        self.move_down_btn.setStyleSheet("color: blue; font-weight: bold; font-size: 16px;")
        
        group_controls_layout.addWidget(self.group_name_input)
        group_controls_layout.addWidget(self.add_group_btn)
        group_controls_layout.addWidget(self.delete_group_btn)
        group_controls_layout.addWidget(self.move_up_btn)
        group_controls_layout.addWidget(self.move_down_btn)
        self.tab_additional_layout.addLayout(group_controls_layout)
        
        self.layer_groups_tree = LayerGroupsTreeWidget(self)
        self.layer_groups_tree.setColumnCount(2)
        self.layer_groups_tree.setHeaderLabels([self.tr("Layer"), self.tr("QML Style")])
        self.layer_groups_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.layer_groups_tree.setDragEnabled(True)
        self.layer_groups_tree.setAcceptDrops(True)
        self.layer_groups_tree.setDragDropMode(QTreeWidget.InternalMove)
        # Set column sizing: column 0 stretches, column 1 fixed width
        header = self.layer_groups_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 220)
        self.tab_additional_layout.addWidget(self.layer_groups_tree)
        preset_buttons_layout = QHBoxLayout()
        self.save_preset_btn = QPushButton(self.tr("Save Preset"))
        self.load_preset_btn = QPushButton(self.tr("Load Preset"))
        self.delete_preset_btn = QPushButton(self.tr("Delete Preset"))
        preset_buttons_layout.addWidget(self.save_preset_btn)
        preset_buttons_layout.addWidget(self.load_preset_btn)
        preset_buttons_layout.addWidget(self.delete_preset_btn)
        self.tab_additional_layout.addLayout(preset_buttons_layout)

        self.apply_groups_btn = QPushButton(self.tr("Apply Groups to QGIS Layers Panel"))
        self.tab_additional_layout.addWidget(self.apply_groups_btn)

        self.import_qml_btn = QPushButton(self.tr("Import QML Style(s)..."))
        self.tab_additional_layout.addWidget(self.import_qml_btn)
        
        # Connect signals for groups
        self.add_group_btn.clicked.connect(self._on_add_layer_group)
        self.delete_group_btn.clicked.connect(self._on_delete_layer_group)
        self.move_up_btn.clicked.connect(self._on_move_item_up)
        self.move_down_btn.clicked.connect(self._on_move_item_down)
        self.apply_groups_btn.clicked.connect(self._on_apply_layer_groups)
        self.save_preset_btn.clicked.connect(self._on_save_groups_preset)
        self.load_preset_btn.clicked.connect(self._on_load_groups_preset)
        self.delete_preset_btn.clicked.connect(self._on_delete_groups_preset)
        self.import_qml_btn.clicked.connect(self._on_import_qml_styles)
        self.layer_groups_tree.itemChanged.connect(self._on_tree_item_changed)
        self.main_tab_widget.addTab(self.tab_additional, self.tr("Prepare Project Layers"))

        # Second tab for the existing UI
        self.tab_main = QWidget()
        self.tab_main_layout = QVBoxLayout(self.tab_main)
        self.tab_main_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_main_layout.addWidget(_scroll)
        self.main_tab_widget.addTab(self.tab_main, self.tr("Export Options"))
        
        self.main_tab_widget.currentChanged.connect(self._on_tab_changed)
        
        self.verticalLayout_3.insertWidget(_i, self.main_tab_widget)
        self.setMinimumHeight(500)
        self.resize(500, 720)
        self.setSizeGripEnabled(True)
        
        # Call it once to set initial visibility state
        self.update_button_box_visibility()

        # ensure output dropdown contains the expected options
        # (combo box named in the .ui file as "output_dropdown")
        self.output_dropdown.clear()
        self.output_dropdown.addItems([
            self.tr("Barangay Level"),
            self.tr("EA Level"),
        ])
        # only repopulate layers when output level changes; renaming happens on Filter click
        self.output_dropdown.currentTextChanged.connect(self.populate_layers_dropdown)
        self.output_dropdown.currentTextChanged.connect(self._update_ui_for_output_level)

        self.iface = iface
        self.offliner = QgisCoreOffliner(offline_editing=offline_editing)
        self.project = project
        self.qfield_preferences = Preferences()
        self.dirsToCopyWidget = DirsToCopyWidget()
        self.__project_configuration = ProjectConfiguration(self.project)
        self.run_button.clicked.connect(self.run)

        self.next_geocode.clicked.connect(self.next_geo)
        self.run_batch.clicked.connect(self.batch)
      
        self.run_clip.clicked.connect(self.run_raster)
        self.run_clip.setEnabled(False)
        self.group_dropdown.currentIndexChanged.connect(self.populate_layers_dropdown)
        self.group_dropdown.currentIndexChanged.connect(self.validate_group_selection)
        
        # When layer changes, populate the top-level tree filter
        self.layer_dropdown.currentIndexChanged.connect(self.populate_geocode_dropdown)
        self.layer_dropdown.currentIndexChanged.connect(self._populate_filter_tree)
        
        # We will disconnect the old dropdowns to avoid side-effects
        # self.citymun_dropdown.currentIndexChanged.connect(...)
        # self.bgy_dropdown.currentIndexChanged.connect(...)

        settings = QSettings()
        saved_raster_path = settings.value('raster_file_path', '', type=str)  # Default to empty string if no saved path

        if saved_raster_path:
            # Set the path to the file widget if a path is saved
            self.select_rasterlayer.setFilePath(saved_raster_path)
            print(f"Loaded saved raster file path: {saved_raster_path}")

        self.select_rasterlayer.setStorageMode(QgsFileWidget.StorageMode.GetFile)  # Set to select a file
        self.select_rasterlayer.setDialogTitle("Select Raster Layer")  # Set dialog title
        self.select_rasterlayer.setFilter(" Raster Layer (*_img.gpkg);;GeoPackage files (*.gpkg)")

        # Connect the fileChanged signal to a slot that updates the path in the settings
        self.select_rasterlayer.fileChanged.connect(self.update_raster_path)

        # EA geocode multi-select list (visible only in EA Level)
        self._ea_list_label = QLabel(self.tr("Select EAs to Process"))
        self._ea_list_widget = QTreeWidget()
        self._ea_list_widget.setHeaderHidden(True)
        self._ea_list_widget.setMinimumHeight(140)
        self._ea_list_widget.itemExpanded.connect(lambda: self._adjust_widget_height_to_content(self._ea_list_widget))
        self._ea_list_widget.itemCollapsed.connect(lambda: self._adjust_widget_height_to_content(self._ea_list_widget))
        self._ea_select_all_btn = QPushButton(self.tr("Select All"))
        self._ea_deselect_all_btn = QPushButton(self.tr("Deselect All"))
        _ea_btn_container = QWidget()
        _ea_btn_layout = QHBoxLayout(_ea_btn_container)
        _ea_btn_layout.setContentsMargins(0, 0, 0, 0)
        _ea_btn_layout.addWidget(self._ea_select_all_btn)
        _ea_btn_layout.addWidget(self._ea_deselect_all_btn)
        self._ea_btn_container = _ea_btn_container
        self._ea_select_all_btn.clicked.connect(self._ea_select_all)
        self._ea_deselect_all_btn.clicked.connect(self._ea_deselect_all)
        self.gridLayout.addWidget(self._ea_list_label, 34, 0, 1, 2)
        self.gridLayout.addWidget(self._ea_list_widget, 35, 0, 1, 2)
        self.gridLayout.addWidget(self._ea_btn_container, 36, 0, 1, 2)
        self._ea_list_label.setVisible(False)
        self._ea_list_widget.setVisible(False)
        self._ea_btn_container.setVisible(False)
        self.layer_dropdown.currentIndexChanged.connect(self._populate_ea_list)

        # EA Layer Assignment panel (visible only in EA Level)
        self._ea_layer_panel = self._build_ea_layer_panel()
        self.gridLayout.addWidget(self._ea_layer_panel, 37, 0, 1, 2)
        self._ea_layer_panel.setVisible(False)
        self.layer_dropdown.currentIndexChanged.connect(self._auto_detect_ea_layers)

        # Combined City/Municipality and Barangay Tree Filter
        self._filter_tree_label = QLabel(self.tr("Select City/Municipality"))
        
        # Search bar for tree
        self._filter_tree_search_bar = QLineEdit()
        self._filter_tree_search_bar.setPlaceholderText(self.tr("Search City/Municipality..."))
        self._filter_tree_search_bar.textChanged.connect(self._on_tree_search_changed)
        
        self._filter_tree_widget = QTreeWidget()
        self._filter_tree_widget.setHeaderHidden(True)
        self._filter_tree_widget.setMinimumHeight(150)
        self._filter_tree_widget.itemExpanded.connect(lambda: self._adjust_widget_height_to_content(self._filter_tree_widget))
        self._filter_tree_widget.itemCollapsed.connect(lambda: self._adjust_widget_height_to_content(self._filter_tree_widget))
        self._filter_tree_widget.setSelectionMode(QTreeWidget.ExtendedSelection)
        self._last_clicked_tree_item = None
        self._filter_tree_select_all_btn = QPushButton(self.tr("Select All"))
        self._filter_tree_deselect_all_btn = QPushButton(self.tr("Deselect All"))
        _filter_tree_btn_container = QWidget()
        _filter_tree_btn_layout = QHBoxLayout(_filter_tree_btn_container)
        _filter_tree_btn_layout.setContentsMargins(0, 0, 0, 0)
        _filter_tree_btn_layout.addWidget(self._filter_tree_select_all_btn)
        _filter_tree_btn_layout.addWidget(self._filter_tree_deselect_all_btn)
        self._filter_tree_btn_container = _filter_tree_btn_container
        self._filter_tree_select_all_btn.clicked.connect(self._filter_tree_select_all)
        self._filter_tree_deselect_all_btn.clicked.connect(self._filter_tree_deselect_all)
        self.gridLayout.addWidget(self._filter_tree_label, 30, 0, 1, 2)
        self.gridLayout.addWidget(self._filter_tree_search_bar, 31, 0, 1, 2)
        self.gridLayout.addWidget(self._filter_tree_widget, 32, 0, 1, 2)
        self.gridLayout.addWidget(self._filter_tree_btn_container, 33, 0, 1, 2)
        self._filter_tree_label.setVisible(False)
        self._filter_tree_search_bar.setVisible(False)
        self._filter_tree_widget.setVisible(False)
        self._filter_tree_btn_container.setVisible(False)
        self._filter_tree_widget.itemChanged.connect(self._on_filter_tree_item_changed)
        self._filter_tree_widget.itemClicked.connect(self._on_filter_tree_item_clicked)
        self._filter_tree_widget.installEventFilter(self)

        # BGY geocode multi-select list (visible only in Barangay Level)
        self._bgy_list_label = QLabel(self.tr("Select BGYs to Process"))
        self._bgy_list_widget = QListWidget()
        self._bgy_list_widget.setMinimumHeight(140)
        self._bgy_select_all_btn = QPushButton(self.tr("Select All"))
        self._bgy_deselect_all_btn = QPushButton(self.tr("Deselect All"))
        _bgy_btn_container = QWidget()
        _bgy_btn_layout = QHBoxLayout(_bgy_btn_container)
        _bgy_btn_layout.setContentsMargins(0, 0, 0, 0)
        _bgy_btn_layout.addWidget(self._bgy_select_all_btn)
        _bgy_btn_layout.addWidget(self._bgy_deselect_all_btn)
        self._bgy_btn_container = _bgy_btn_container
        self._bgy_select_all_btn.clicked.connect(self._bgy_select_all)
        self._bgy_deselect_all_btn.clicked.connect(self._bgy_deselect_all)
        self.gridLayout.addWidget(self._bgy_list_label, 38, 0, 1, 2)
        self.gridLayout.addWidget(self._bgy_list_widget, 39, 0, 1, 2)
        self.gridLayout.addWidget(self._bgy_btn_container, 40, 0, 1, 2)
        self._bgy_list_label.setVisible(False)
        self._bgy_list_widget.setVisible(False)
        self._bgy_btn_container.setVisible(False)
        # Note: population is now triggered by _bgy_name_list_widget selection
        # Connect BGY list item model to update Export button when selections change
        self._bgy_list_widget.itemChanged.connect(self._on_bgy_item_changed)

        # BGY Layer Assignment panel (visible only in Barangay Level)
        self._bgy_layer_panel = self._build_bgy_layer_panel()
        self.gridLayout.addWidget(self._bgy_layer_panel, 41, 0, 1, 2)
        self._bgy_layer_panel.setVisible(False)
        self.layer_dropdown.currentIndexChanged.connect(self._auto_detect_bgy_layers)

        # Raster Configuration panel (replaces old Raster Process group box)
        self._raster_config_panel = self._build_raster_config_panel()
        self.gridLayout.addWidget(self._raster_config_panel, 42, 0, 1, 2)
        self._raster_config_panel.setVisible(False)

        # Hide the old Raster Process group box and Clip button from the .ui file
        self.gridGroupBox.setVisible(False)
        self.run_clip.setVisible(False)

        # Individual Layer Export panel (visible in both EA and BGY levels)
        self._individual_export_panel = self._build_individual_export_panel()
        self.gridLayout.addWidget(self._individual_export_panel, 43, 0, 1, 2)
        self._individual_export_panel.setVisible(False)
        self.layer_dropdown.currentIndexChanged.connect(self._refresh_individual_export_list)

        self.project_lbl.setText(get_project_title(self.project))
        self.button_box.button(QDialogButtonBox.Save).setText(self.tr("Export"))
        self.button_box.button(QDialogButtonBox.Save).clicked.connect(
            self.package_project
        )
        self.button_box.button(QDialogButtonBox.Save).setEnabled(False)
        self.button_box.button(QDialogButtonBox.Reset).clicked.connect(
            self.reset_filter
        )

        self.devices = None
        self.project_checker = ProjectChecker(QgsProject.instance())
        self.setup_gui()

         # Initialize variables
        self.layers = {}

        self.offliner.warning.connect(self.show_warning)

        # Load groups on dialog initialization
        self.load_layer_groups()
        # Apply initial UI state based on the default output level.
        self._update_ui_for_output_level()

        # Flag to control batch mode
        self.is_batch_mode = False
        # Flag to handle batch cancellation
        self.batch_cancel_requested = False
        # Track enabled-state snapshot while batch is running.
        self._batch_prev_enabled_states = {}

    def _set_batch_ui_locked(self, locked):
        """Disable interactive controls during batch and restore them afterwards."""
        controls = {
            "run_button": self.run_button,
            "next_geocode": self.next_geocode,
            "run_batch": self.run_batch,
            "run_clip": self.run_clip,
            "manualDir_btn": self.manualDir_btn,
            "group_dropdown": self.group_dropdown,
            "layer_dropdown": self.layer_dropdown,
            "geocode_dropdown": self.geocode_dropdown,
            "citymun_dropdown": self.citymun_dropdown,
            "bgy_dropdown": self.bgy_dropdown,
            "output_dropdown": self.output_dropdown,
            "save_button": self.button_box.button(QDialogButtonBox.Save),
            "reset_button": self.button_box.button(QDialogButtonBox.Reset),
            "select_rasterlayer": self.select_rasterlayer,
        }

        if locked:
            self._batch_prev_enabled_states = {}
            for key, widget in controls.items():
                if widget is None:
                    continue
                try:
                    self._batch_prev_enabled_states[key] = widget.isEnabled()
                    widget.setEnabled(False)
                except Exception:
                    continue
            return

        for key, widget in controls.items():
            if widget is None:
                continue
            if key not in self._batch_prev_enabled_states:
                continue
            try:
                widget.setEnabled(self._batch_prev_enabled_states[key])
            except Exception:
                continue
        self._batch_prev_enabled_states = {}

    def _update_lists_from_filter_tree(self):
        if self.output_dropdown.currentText() == self.tr("EA Level"):
            self._populate_ea_list()
        else:
            self._populate_bgy_list()

    def _adjust_widget_height_to_content(self, widget, min_height=80, max_height=250):
        if not widget:
            return
        
        if isinstance(widget, QTreeWidget):
            count = 0
            def count_visible(item):
                nonlocal count
                if item.isHidden():
                    return
                count += 1
                if item.isExpanded():
                    for i in range(item.childCount()):
                        count_visible(item.child(i))
                        
            for i in range(widget.topLevelItemCount()):
                count_visible(widget.topLevelItem(i))
                
            row_height = widget.sizeHintForRow(0)
            if row_height <= 0:
                row_height = 22 # fallback row height
                
            header_height = widget.header().height() if not widget.isHeaderHidden() else 0
            frame_width = widget.frameWidth() * 2
            calculated_height = (count * row_height) + header_height + frame_width + 6
            
        elif isinstance(widget, QListWidget):
            count = 0
            for i in range(widget.count()):
                if not widget.item(i).isHidden():
                    count += 1
            row_height = widget.sizeHintForRow(0)
            if row_height <= 0:
                row_height = 22 # fallback row height
            frame_width = widget.frameWidth() * 2
            calculated_height = (count * row_height) + frame_width + 6
        else:
            return

        target_height = max(min_height, min(calculated_height, max_height))
        widget.setFixedHeight(target_height)

    def _on_tree_search_changed(self, text):
        search_str = text.lower()
        for i in range(self._filter_tree_widget.topLevelItemCount()):
            parent_item = self._filter_tree_widget.topLevelItem(i)
            if search_str in parent_item.text(0).lower():
                parent_item.setHidden(False)
            else:
                parent_item.setHidden(True)
        self._adjust_widget_height_to_content(self._filter_tree_widget)

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            if hasattr(self, '_filter_tree_widget') and source is self._filter_tree_widget:
                selected_items = self._filter_tree_widget.selectedItems()
                if selected_items:
                    first_item_state = selected_items[0].checkState(0)
                    new_state = Qt.Unchecked if first_item_state == Qt.Checked else Qt.Checked
                    
                    self._filter_tree_widget.blockSignals(True)
                    for item in selected_items:
                        item.setCheckState(0, new_state)
                    self._filter_tree_widget.blockSignals(False)
                    self._update_lists_from_filter_tree()
                    return True # Event handled
            elif hasattr(self, 'layer_groups_tree') and source is self.layer_groups_tree:
                selected_items = self.layer_groups_tree.selectedItems()
                if selected_items:
                    first_item_state = selected_items[0].checkState(0)
                    new_state = Qt.Unchecked if first_item_state == Qt.Checked else Qt.Checked
                    
                    self.layer_groups_tree.blockSignals(True)
                    for item in selected_items:
                        item.setCheckState(0, new_state)
                    self.layer_groups_tree.blockSignals(False)
                    self._update_layer_visibility()
                    return True # Event handled
        
        return super(PackageDialog, self).eventFilter(source, event)

    def _update_ui_for_output_level(self):
        """Show/hide controls based on the selected output level."""
        is_ea = self.output_dropdown.currentText() == self.tr("EA Level")
        is_bgy = self.output_dropdown.currentText() == self.tr("Barangay Level")

        # Controls hidden in EA Level and Barangay Level (handled by batch Export)
        _hide = is_ea or is_bgy
        self.label.setVisible(not _hide)          # "Select Base Layer" (group label)
        self.group_dropdown.setVisible(not _hide)
        self.label_5.setVisible(not _hide)        # "Select Barangay Geocode"
        self.geocode_dropdown.setVisible(not _hide)
        self.run_button.setVisible(not _hide)     # Filter button
        self.next_geocode.setVisible(not _hide)   # Next Geocode button
        self.run_batch.setVisible(not _hide)      # Batch button
        self.run_clip.setVisible(False)            # Clip button removed (batch-only)

        # Old Dropdowns are now completely hidden to avoid confusion
        self.label_7.setVisible(False)
        self.citymun_dropdown.setVisible(False)
        self.label_9.setVisible(False)
        self.bgy_dropdown.setVisible(False)

        # Update layer dropdown label
        if is_ea:
            self.label_3.setText(self.tr("Select EA Layer"))
        elif is_bgy:
            self.label_3.setText(self.tr("Select Barangay Layer"))
        else:
            self.label_3.setText(self.tr("Select Layer"))

        # For EA Level, enable Export as soon as an EA layer is loaded;
        # for Barangay Level, enable Export when BGYs are selected.
        if is_ea and self.layer_dropdown.count() > 0:
            self.button_box.button(QDialogButtonBox.Save).setEnabled(True)
        elif is_bgy:
            # Enable Export if at least one BGY is checked
            num_checked = sum(
                1 for i in range(self._bgy_list_widget.count())
                if self._bgy_list_widget.item(i).checkState() == Qt.Checked
            )
            self.button_box.button(QDialogButtonBox.Save).setEnabled(num_checked > 0)
        else:
            self.button_box.button(QDialogButtonBox.Save).setEnabled(False)

        # EA geocode list widget
        if hasattr(self, '_ea_list_label'):
            self._ea_list_label.setVisible(is_ea)
            self._ea_list_widget.setVisible(is_ea)
            self._ea_btn_container.setVisible(is_ea)

        # EA Layer Assignment panel
        if hasattr(self, '_ea_layer_panel'):
            self._ea_layer_panel.setVisible(is_ea)
            if is_ea:
                self._auto_detect_ea_layers()
                
        # Tree filter widget
        if hasattr(self, '_filter_tree_label'):
            self._filter_tree_label.setVisible(is_bgy or is_ea)
            self._filter_tree_search_bar.setVisible(is_bgy or is_ea)
            self._filter_tree_widget.setVisible(is_bgy or is_ea)
            self._filter_tree_btn_container.setVisible(is_bgy or is_ea)

        # BGY geocode list widget
        if hasattr(self, '_bgy_list_label'):
            self._bgy_list_label.setVisible(is_bgy)
            self._bgy_list_widget.setVisible(is_bgy)
            self._bgy_btn_container.setVisible(is_bgy)

        # BGY Layer Assignment panel
        if hasattr(self, '_bgy_layer_panel'):
            self._bgy_layer_panel.setVisible(is_bgy)
            if is_bgy:
                self._auto_detect_bgy_layers()

        # Individual Layer Export panel
        if hasattr(self, '_individual_export_panel'):
            self._individual_export_panel.setVisible(is_ea or is_bgy)
            if is_ea or is_bgy:
                self._refresh_individual_export_list()

        # Raster Configuration panel (replaces old Raster Process group box)
        if hasattr(self, '_raster_config_panel'):
            self._raster_config_panel.setVisible(is_ea or is_bgy)

    def showEvent(self, event):
        super(PackageDialog, self).showEvent(event)
        self.button_box.button(QDialogButtonBox.Save).setText(self.tr("Export"))

    def next_geo(self):
        # Check if "Base Layers" group is selected
        if self.group_dropdown.currentText() != "Base Layers":
            QMessageBox.warning(self, "Group Selection", "Please select the Base Layers group.")
            return
        
        current_index = self.geocode_dropdown.currentIndex()
        total_items = self.geocode_dropdown.count()

        if current_index < total_items - 1:
            self.geocode_dropdown.setCurrentIndex(current_index + 1)
        else:
            QMessageBox.information(self, "End of List", "You have reached the end of the geocode list.")

    def validate_group_selection(self):
        """Enable/disable next_geo and run_batch buttons based on group selection."""
        selected_group = self.group_dropdown.currentData() or self.group_dropdown.currentText()
        is_base_layers = str(selected_group).strip().lower() == "base layers"
        self.next_geocode.setEnabled(is_base_layers)
        self.run_batch.setEnabled(is_base_layers)

    def batch(self):
        """Run filter, clip, and export from the selected geocode onward.

        Do not reset the dropdown inside the loop (reset once after processing all items),
        otherwise the remaining geocodes are cleared and iteration stops.
        """
        if self.is_batch_mode:
            QMessageBox.information(self, "Batch Run", "Batch processing is already running.")
            return

        count = self.geocode_dropdown.count()
        if count == 0:
            QMessageBox.information(self, "Batch Run", "No geocodes available to process.")
            return

        start_index = self.geocode_dropdown.currentIndex()
        if start_index < 0:
            start_index = 0
        
        # Set batch mode flag to prevent dialog from closing during processing
        self.is_batch_mode = True
        self._set_batch_ui_locked(True)

        geocodes = [
            self.geocode_dropdown.itemText(i)
            for i in range(start_index, count)
        ]
        last_geocode_processed = None
        processed_count = 0
        errors = []

        try:
            for code in geocodes:
                try:
                    # Check if cancel was requested
                    if self.batch_cancel_requested:
                        break

                    # Select the geocode so other methods read the correct currentText
                    idx = self.geocode_dropdown.findText(code)
                    if idx != -1:
                        self.geocode_dropdown.setCurrentIndex(idx)

                    # Filtering
                    self.run()

                    # Raster clip (wait for worker to finish)
                    self.run_raster()
                    if hasattr(self, 'worker') and getattr(self, 'worker') is not None:
                        try:
                            # wait with a timeout to avoid indefinite blocking
                            self.worker.wait(300000)
                            # Ensure queued finished-signal UI updates (including
                            # raster layer registration) are processed before export.
                            QApplication.processEvents()
                        except Exception:
                            pass

                    # Export
                    self.package_project()

                    # Allow the event loop to process (UI updates, signals)
                    try:
                        QApplication.processEvents()
                    except Exception:
                        pass

                    last_geocode_processed = code
                    processed_count += 1

                except Exception as e:
                    errors.append(f"{code}: {e}")

            # Reset once after all iterations
            try:
                self.reset_filter()
            except Exception:
                pass
        finally:
            # Check if batch was cancelled before resetting flags
            was_cancelled = self.batch_cancel_requested

            # Exit batch mode
            self.is_batch_mode = False
            self.batch_cancel_requested = False
            self._set_batch_ui_locked(False)

        # Determine message based on cancellation status
        if was_cancelled:
            summary = f"Batch Run Cancelled\n\nProcessed: {processed_count}\nLast processed: {last_geocode_processed or 'none'}"
        else:
            summary = f"Total geocodes processed: {processed_count}\nLast processed: {last_geocode_processed or 'none'}"
        
        # Store results for display
        self.batch_summary = summary
        
        # Defer message box and dialog close to allow batch to complete fully
        QTimer.singleShot(100, self._show_batch_completion_and_close)

    def _show_batch_completion_and_close(self):
        """Helper method to show batch completion message and close dialog."""
        QMessageBox.information(None, "Batch Run Completed", self.batch_summary)

        # After an EA batch, OfflineConverter has left all project layers in
        # offline mode (datasources repointed to export .gpkg files).  Reload
        # the original project to restore layer states so that interacting with
        # layers afterwards doesn't crash QGIS.
        if getattr(self, "_reload_project_after_ea_batch", False):
            self._reload_project_after_ea_batch = False
            try:
                project_file = QgsProject.instance().fileName()
                if project_file and os.path.exists(project_file):
                    QgsProject.instance().read(project_file)
            except Exception:
                pass

        self.accept()

    def reject(self):
        """Override reject to handle batch cancellation."""
        if self.is_batch_mode:
            self.batch_cancel_requested = True
        else:
            super().reject()


    def _on_raster_type_changed(self, index):
        if not hasattr(self, 'select_rasterlayer'):
            return
        if index == 0:
            self.select_rasterlayer.setFilter(self.tr("Raster Layer (*_img.gpkg);;GeoPackage files (*.gpkg)"))
            if hasattr(self, 'raster_subtitle_label'):
                self.raster_subtitle_label.setText(self.tr("Acceptable filename: *_img.gpkg"))
        elif index == 1:
            self.select_rasterlayer.setFilter(self.tr("Raster Layer (*_img.mbtiles);;MBTiles files (*.mbtiles)"))
            if hasattr(self, 'raster_subtitle_label'):
                self.raster_subtitle_label.setText(self.tr("Acceptable filename: *_img.mbtiles"))
        elif index == 2:
            self.select_rasterlayer.setFilter(self.tr("Raster Layer (*_img.gpkg *_img.mbtiles);;GeoPackage files (*.gpkg);;MBTiles files (*.mbtiles)"))
            if hasattr(self, 'raster_subtitle_label'):
                self.raster_subtitle_label.setText(self.tr("Acceptable filenames: *_img.gpkg or *_img.mbtiles"))

    def update_raster_path(self, new_path):
        settings = QSettings()
        is_ea = self.output_dropdown.currentText() == self.tr("EA Level")
        is_bgy = self.output_dropdown.currentText() == self.tr("Barangay Level")
        
        if is_ea or is_bgy:
            settings.setValue("satellite_dir_path", new_path)
            print(f"Updated satellite directory path: {new_path}")
        else:
            settings.setValue("raster_file_path", new_path)
            print(f"Updated raster file path: {new_path}")
        
    def update_progress(self, sent, total):
        progress = float(sent) / total * 100
        self.progress_bar.setValue(progress)

    def setup_gui(self):
        """Populate gui and connect signals of the push dialog"""
        # Restore the last manually selected export directory if available
        try:
            manual_export_dir = self.qfield_preferences.value("exportDirectoryManual")
        except NameError:
            manual_export_dir = None
        if manual_export_dir:
            export_dirname = manual_export_dir
        else:
            try:
                export_dirname = self.qfield_preferences.value("exportDirectoryProject")
            except NameError:
                export_dirname = None
            
            # Extract parent directory from the subfolder path created during export
            # This ensures we always show the directory the user selected, not the export subfolder
            if export_dirname:
                parent_path = str(Path(export_dirname).parent)
                # Use parent if it's different from current (i.e., current is a subfolder)
                if os.path.isdir(parent_path) and parent_path != export_dirname:
                    export_dirname = parent_path
            
            if not export_dirname:
                export_dirname = os.path.join(
                    self.qfield_preferences.value("exportDirectory"),
                    fileparts(QgsProject.instance().fileName())[1],
                )

        self.manualDir.setText(QDir.toNativeSeparators(str(export_dirname)))
        # Connect folder selector and save selection to preferences
        def select_folder():
            make_folder_selector(self.manualDir)()
            try:
                self.qfield_preferences.set_value("exportDirectoryManual", self.manualDir.text())
            except NameError:
                if hasattr(self.qfield_preferences, "register_setting"):
                    self.qfield_preferences.register_setting("exportDirectoryManual", self.manualDir.text())
                else:
                    pass
        self.manualDir_btn.clicked.connect(select_folder)
        self.update_info_visibility()

        self.nextButton.clicked.connect(lambda: self.show_package_page())
        self.nextButton.setVisible(False)
        self.update_button_box_visibility()


        self.dirsToCopyWidget.set_path(QgsProject().instance().homePath())
        self.dirsToCopyWidget.refresh_tree()

        feedback = None
        if os.path.exists(self.project.fileName()):
            feedback = self.project_checker.check(ExportType.Cable)

        if feedback and feedback.count > 0:
            has_errors = len(feedback.error_feedbacks) > 0

            feedback_table = CheckerFeedbackTable(feedback)
            self.feedbackTableWrapperLayout.addWidget(feedback_table)
            self.stackedWidget.setCurrentWidget(self.projectCompatibilityPage)
            self.nextButton.setVisible(True)
            self.nextButton.setEnabled(not has_errors)
        else:
            self.show_package_page()

    def get_export_folder_from_dialog(self):
        """Get the export folder according to the inputs in the selected"""
        # manual
        return self.manualDir.text()

    def show_package_page(self):
        self.nextButton.setVisible(False)
        self.stackedWidget.setCurrentWidget(self.packagePage)
        self.update_button_box_visibility()


    def package_project(self):
        # EA Level uses a dedicated batch export that iterates all EA features.
        if self.output_dropdown.currentText() == self.tr("EA Level"):
            self.run_ea_batch_export()
            return
        
        # BGY Level uses a dedicated batch export that iterates all BGY features.
        if self.output_dropdown.currentText() == self.tr("Barangay Level"):
            self.run_bgy_batch_export()
            return

        self.button_box.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)

        # Use existing UI elements: manualDir for export folder path
        export_folder = Path(self.manualDir.text())

        selected_geocode = self.geocode_dropdown.currentText()
        # derive code prefix based on selected output level
        prefix = selected_geocode.split('_', 1)[0] if selected_geocode else ''
        if self.output_dropdown.currentText() == self.tr("EA Level"):
            code_digits = prefix[:14]
        else:
            code_digits = prefix[:8]
        barangay_name = selected_geocode.split('_', 1)[1] if '_' in selected_geocode else ""
        subfolder_name = f"{code_digits}_{barangay_name}"

        # Create subfolder with format: "8-digit-code_barangay-name".
        # If it already exists, clear its contents in a lock-safe way so files
        # are overwritten without failing on temporarily locked rasters.
        subfolder_path = export_folder / subfolder_name
        if subfolder_path.exists():
            subfolder_abs = os.path.normcase(os.path.abspath(str(subfolder_path)))
            raster_base_name = f"{code_digits}_img.tif"
            keep_raster_abs = os.path.normcase(
                os.path.abspath(
                    getattr(
                        self,
                        "final_raster_path",
                        str(subfolder_path / raster_base_name),
                    )
                )
            )

            # Release QGIS locks for rasters currently loaded from this folder.
            project = QgsProject.instance()
            for lyr in list(project.mapLayers().values()):
                try:
                    src = lyr.source() if hasattr(lyr, "source") else ""
                    if not src or not isinstance(lyr, QgsRasterLayer):
                        continue
                    src_abs = os.path.normcase(os.path.abspath(src))
                    # Keep the current clipped raster layer in the project so
                    # OfflineConverter can package it into the exported qgz.
                    if src_abs.startswith(subfolder_abs) and src_abs != keep_raster_abs:
                        project.removeMapLayer(lyr.id())
                except Exception:
                    continue

            try:
                QApplication.processEvents()
            except Exception:
                pass

            # Remove old files/folders; skip locked files instead of crashing.
            for item in subfolder_path.iterdir():
                try:
                    # Keep the clipped raster and its sidecar files so they are
                    # still available for OfflineConverter packaging.
                    if item.is_file() and (
                        item.name == raster_base_name
                        or item.name.startswith(raster_base_name + ".")
                    ):
                        continue

                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        removed = False
                        for _ in range(5):
                            try:
                                item.unlink()
                                removed = True
                                break
                            except PermissionError:
                                QApplication.processEvents()
                                time.sleep(0.2)
                        if not removed and item.exists():
                            QgsApplication.instance().messageLog().logMessage(
                                f"Could not remove locked file before export: {item}",
                                "qfieldmod",
                                Qgis.Warning,
                            )
                except Exception as e:
                    QgsApplication.instance().messageLog().logMessage(
                        f"Could not clear export item '{item}': {e}",
                        "qfieldmod",
                        Qgis.Warning,
                    )
        subfolder_path.mkdir(parents=True, exist_ok=True)

        # Create project file path inside the subfolder
        packaged_project_file = subfolder_path / f"{code_digits}.qgz"

        area_of_interest = (
            self.__project_configuration.area_of_interest
            if self.__project_configuration.area_of_interest
            else self.iface.mapCanvas().extent().asWktPolygon()
        )
        area_of_interest_crs = (
            self.__project_configuration.area_of_interest_crs
            if self.__project_configuration.area_of_interest_crs
            else QgsProject.instance().crs().authid()
        )

        # Only update exportDirectoryProject (for internal use), never manualDir or exportDirectoryManual
        self.qfield_preferences.set_value(
            "exportDirectoryProject", str(subfolder_path)
        )
        self.dirsToCopyWidget.save_settings()
        self._ensure_ea_update_not_offline_and_writable()

        # In batch mode, old generated rasters from previous iterations may
        # still be loaded and get copied again. Keep only the current raster.
        try:
            keep_sources = set()
            if hasattr(self, 'temp_raster_path') and self.temp_raster_path:
                keep_sources.add(os.path.normcase(os.path.abspath(self.temp_raster_path)))

            project = QgsProject.instance()
            for lyr in list(project.mapLayers().values()):
                if not isinstance(lyr, QgsRasterLayer):
                    continue
                src = lyr.source() or ""
                if not src:
                    continue
                src_abs = os.path.normcase(os.path.abspath(src))
                src_name = os.path.basename(src_abs).lower()
                lyr_name = (lyr.name() or "").lower()
                is_generated_img = src_name.endswith('_img.tif') or lyr_name.endswith('_img') or lyr_name.endswith('_img.tif')
                if is_generated_img and src_abs not in keep_sources:
                    project.removeMapLayer(lyr.id())
        except Exception:
            pass

        # Safety net: in batch mode, if raster completion signal has not yet
        # materialized the current raster layer in project, add/update it now.
        try:
            desired_raster_name = f"{code_digits}_img"
            current_raster_path = None
            if hasattr(self, 'temp_raster_path') and self.temp_raster_path and os.path.exists(self.temp_raster_path):
                current_raster_path = self.temp_raster_path
            elif hasattr(self, 'final_raster_path') and self.final_raster_path and os.path.exists(self.final_raster_path):
                current_raster_path = self.final_raster_path

            if current_raster_path:
                current_abs = os.path.normcase(os.path.abspath(current_raster_path))
                found_current = False
                for lyr in QgsProject.instance().mapLayers().values():
                    if not isinstance(lyr, QgsRasterLayer):
                        continue
                    src = lyr.source() or ""
                    if src and os.path.normcase(os.path.abspath(src)) == current_abs:
                        lyr.setName(desired_raster_name)
                        found_current = True
                        break

                if not found_current:
                    raster_layer = QgsRasterLayer(current_raster_path, desired_raster_name)
                    if raster_layer.isValid():
                        QgsProject.instance().addMapLayer(raster_layer, False)
                        QgsProject.instance().layerTreeRoot().addLayer(raster_layer)
                        self.clipped_raster_layer = raster_layer
        except Exception:
            pass

        def _build_converter(offliner_instance):
            converter = OfflineConverter(
                self.project,
                packaged_project_file,
                area_of_interest,
                area_of_interest_crs,
                self.qfield_preferences.value("attachmentDirs"),
                offliner_instance,
                ExportType.Cable,
                dirs_to_copy=self.dirsToCopyWidget.dirs_to_copy(),
                export_title=code_digits,
            )
            converter.total_progress_updated.connect(self.update_total)
            converter.task_progress_updated.connect(self.update_task)
            converter.warning.connect(
                lambda title, body: QMessageBox.warning(None, title, body)
            )
            return converter

        def _rewrite_packaged_project_raster_source():
            """Ensure packaged project references the local exported raster file."""
            raster_filename = f"{code_digits}_img.tif"
            raster_layer_name = f"{code_digits}_img"
            target_ds = raster_filename

            def _rewrite_qgs_text(text):
                # Prefer XML-aware rewrite to avoid brittle text substitutions.
                try:
                    root = ET.fromstring(text)
                    changed = False

                    for ml in root.findall('.//maplayer'):
                        name_el = ml.find('layername')
                        ds_el = ml.find('datasource')
                        layer_name = (name_el.text or '').lower() if name_el is not None else ''
                        ds_text = (ds_el.text or '') if ds_el is not None else ''

                        should_rewrite = raster_filename.lower() in ds_text.lower() or layer_name.endswith('_img')
                        if should_rewrite and ds_el is not None:
                            ds_el.text = target_ds
                            changed = True

                        src_attr = ml.attrib.get('source', '')
                        if src_attr and should_rewrite:
                            ml.attrib['source'] = target_ds
                            changed = True

                    for lt in root.findall('.//layer-tree-layer'):
                        src_attr = lt.attrib.get('source', '')
                        name_attr = (lt.attrib.get('name', '') or '').lower()
                        if raster_filename.lower() in src_attr.lower() or name_attr.endswith('_img'):
                            lt.attrib['source'] = target_ds
                            changed = True

                    if changed:
                        return ET.tostring(root, encoding='unicode')
                except Exception:
                    pass

                # Fallback regex rewrite.
                out = re.sub(
                    rf"(<datasource>)[^<]*{re.escape(raster_filename)}(</datasource>)",
                    rf"\\1{target_ds}\\2",
                    text,
                    flags=re.IGNORECASE,
                )
                out = re.sub(
                    rf"(source=\")[^\"]*{re.escape(raster_filename)}(\")",
                    rf"\\1{target_ds}\\2",
                    out,
                    flags=re.IGNORECASE,
                )

                # Fallback by layer block name (handles unusual XML formatting).
                out = re.sub(
                    rf"(<maplayer[^>]*>.*?<layername>\s*{re.escape(raster_layer_name)}(?:\.tif)?\s*</layername>.*?<datasource>)[^<]*(</datasource>)",
                    rf"\\1{target_ds}\\2",
                    out,
                    flags=re.IGNORECASE | re.DOTALL,
                )

                out = re.sub(
                    rf"(<layer-tree-layer[^>]*\bname=\"{re.escape(raster_layer_name)}(?:\.tif)?\"[^>]*\bsource=\")[^\"]*(\")",
                    rf"\\1{target_ds}\\2",
                    out,
                    flags=re.IGNORECASE | re.DOTALL,
                )

                return out

            project_path = str(packaged_project_file)
            if not os.path.exists(project_path):
                return

            if project_path.lower().endswith('.qgz'):
                tmp_qgz = project_path + '.tmp'
                with zipfile.ZipFile(project_path, 'r') as zin:
                    names = zin.namelist()
                    qgs_name = next((n for n in names if n.lower().endswith('.qgs')), None)
                    if not qgs_name:
                        return
                    qgs_text = zin.read(qgs_name).decode('utf-8', errors='ignore')
                    rewritten = _rewrite_qgs_text(qgs_text)

                    with zipfile.ZipFile(tmp_qgz, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
                        for name in names:
                            if name == qgs_name:
                                zout.writestr(name, rewritten.encode('utf-8'))
                            else:
                                zout.writestr(name, zin.read(name))

                os.replace(tmp_qgz, project_path)
            else:
                with open(project_path, 'r', encoding='utf-8', errors='ignore') as f:
                    qgs_text = f.read()
                rewritten = _rewrite_qgs_text(qgs_text)
                with open(project_path, 'w', encoding='utf-8') as f:
                    f.write(rewritten)

        def _validate_packaged_project_sources():
            """Validate local file references in packaged qgs/qgz and report missing ones."""
            project_path = str(packaged_project_file)
            if not os.path.exists(project_path):
                return

            qgs_text = ""
            if project_path.lower().endswith('.qgz'):
                with zipfile.ZipFile(project_path, 'r') as zin:
                    names = zin.namelist()
                    qgs_name = next((n for n in names if n.lower().endswith('.qgs')), None)
                    if not qgs_name:
                        return
                    qgs_text = zin.read(qgs_name).decode('utf-8', errors='ignore')
            else:
                with open(project_path, 'r', encoding='utf-8', errors='ignore') as f:
                    qgs_text = f.read()

            refs = []
            refs.extend(re.findall(r"<datasource>([^<]+)</datasource>", qgs_text, flags=re.IGNORECASE))
            refs.extend(re.findall(r"\ssource=\"([^\"]+)\"", qgs_text, flags=re.IGNORECASE))

            def resolve_local_path(ref):
                if not ref:
                    return None
                value = ref.strip()
                if not value:
                    return None

                # Keep only path part when provider params are appended.
                value = value.split('|', 1)[0]

                low = value.lower()
                # Skip non-file/provider URIs.
                if low.startswith((
                    'dbname=', 'host=', 'http://', 'https://', 'wms:', 'wmts:',
                    'xyz:', 'postgres', 'point(', 'linestring(', 'polygon('
                )):
                    return None

                if low.startswith('file://'):
                    value = QUrl(value).toLocalFile() or value

                # Normalize relative refs against export subfolder.
                if not os.path.isabs(value):
                    value = os.path.join(str(subfolder_path), value.lstrip('./\\'))

                return os.path.abspath(value)

            missing = []
            seen = set()
            for ref in refs:
                candidate = resolve_local_path(ref)
                if not candidate:
                    continue
                if candidate in seen:
                    continue
                seen.add(candidate)
                if not os.path.exists(candidate):
                    missing.append(candidate)

            if missing:
                preview = "\n".join(missing[:5])
                if len(missing) > 5:
                    preview += f"\n... and {len(missing) - 5} more"
                self.iface.messageBar().pushWarning(
                    "Export Validation",
                    f"Packaged project has missing referenced files:\n{preview}",
                )
            else:
                QgsApplication.instance().messageLog().logMessage(
                    f"Packaged project validation passed: {project_path}",
                    "qfieldmod",
                    Qgis.Info,
                )

        def _convert_with_same_file_guard():
            try:
                self._offline_convertor.convert()
            except shutil.SameFileError as e:
                src = getattr(e, "filename", None)
                dst = getattr(e, "filename2", None)

                # If converter reports SameFileError for different paths,
                # force overwrite by replacing destination.
                if src and dst:
                    src_abs = os.path.normcase(os.path.abspath(src))
                    dst_abs = os.path.normcase(os.path.abspath(dst))
                    if src_abs != dst_abs:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        if os.path.exists(dst):
                            os.remove(dst)
                        shutil.copy2(src, dst)
                        return

                # True same-path copy (src == dst): nothing to overwrite.
                # Keep export silent and continue.
                QgsApplication.instance().messageLog().logMessage(
                    f"Ignoring same-path copy during export: {e}",
                    "qfieldmod",
                    Qgis.Info,
                )

        self._offline_convertor = _build_converter(self.offliner)

        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            # Make the satellite raster visible in the layer panel right before
            # OfflineConverter snapshots the project state into the QGZ.
            _root = QgsProject.instance().layerTreeRoot()
            for _rl in list(QgsProject.instance().mapLayers().values()):
                if isinstance(_rl, QgsRasterLayer) and self._normalized_layer_name(_rl.name()).lower().endswith("_img"):
                    _rn = _root.findLayer(_rl.id())
                    if _rn:
                        _rn.setItemVisibilityChecked(True)
            try:
                _convert_with_same_file_guard()
            except IndexError as e:
                # Workaround for a libqfieldsync bug where offline layer progress
                # can desync and trigger `offline_layer_names` index errors.
                QgsApplication.instance().messageLog().logMessage(
                    f"Offline export retry (offline editing disabled) after IndexError: {e}",
                    "qfieldmod",
                    Qgis.Warning,
                )
                self.iface.messageBar().pushWarning(
                    "Export Warning",
                    "Offline editing failed for a layer. Retrying export with offline editing disabled.",
                )
                fallback_offliner = QgisCoreOffliner(offline_editing=False)
                fallback_offliner.warning.connect(self.show_warning)
                self._offline_convertor = _build_converter(fallback_offliner)
                _convert_with_same_file_guard()
            
            # Robust raster export: always remove old raster layers with the same path, always add raster from export folder
            if hasattr(self, 'temp_raster_path') and hasattr(self, 'final_raster_path'):
                if os.path.exists(self.temp_raster_path):
                    try:
                        os.makedirs(os.path.dirname(self.final_raster_path), exist_ok=True)
                        if os.path.exists(self.final_raster_path):
                            os.remove(self.final_raster_path)
                        shutil.move(self.temp_raster_path, self.final_raster_path)
                        print(f"Moved raster from temp to subfolder: {self.final_raster_path}")
                        # Remove any previous raster layers with the same path
                        for lyr in QgsProject.instance().mapLayers().values():
                            if isinstance(lyr, QgsRasterLayer) and lyr.source() == self.final_raster_path:
                                QgsProject.instance().removeMapLayer(lyr.id())
                        # Add the raster to the project and update reference
                        clipped_raster_layer = QgsRasterLayer(self.final_raster_path, f"{code_digits}_img")
                        if clipped_raster_layer.isValid():
                            QgsProject.instance().addMapLayer(clipped_raster_layer, False)
                            QgsProject.instance().layerTreeRoot().addLayer(clipped_raster_layer)
                            self.clipped_raster_layer = clipped_raster_layer
                            print(f"Raster layer added to project: {self.final_raster_path}")
                        else:
                            print(f"Warning: Could not load raster layer: {self.final_raster_path}")
                    except Exception as e:
                        print(f"Warning: Could not move raster to subfolder: {str(e)}")

            # Ensure exported project points to the raster inside the export
            # folder, not to a temporary path.
            try:
                _rewrite_packaged_project_raster_source()
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not rewrite packaged raster datasource: {e}",
                    "qfieldmod",
                    Qgis.Warning,
                )

            # Rename any *_ea_update.gpkg in the export folder to use an
            # 8-digit prefix and patch the QGZ to match.
            try:
                ea_prefix = re.sub(r"\D", "", (selected_geocode.split('_', 1)[0] if selected_geocode else ""))[:8]
                if len(ea_prefix) < 8:
                    folder_prefix = re.sub(r"\D", "", subfolder_path.name.split('_', 1)[0])[:8]
                    if len(folder_prefix) == 8:
                        ea_prefix = folder_prefix
                if len(ea_prefix) < 8:
                    for _img in subfolder_path.glob('*_img.tif'):
                        img_prefix = re.sub(r"\D", "", _img.stem.replace('_img', ''))[:8]
                        if len(img_prefix) == 8:
                            ea_prefix = img_prefix
                            break
                if len(ea_prefix) < 8:
                    fallback = re.sub(r"\D", "", str(code_digits))[:8]
                    ea_prefix = fallback.ljust(8, '0')

                ea_new_name = f"{ea_prefix}_ea_update.gpkg"
                _proj_path = str(packaged_project_file)
                _ea_found = list(Path(subfolder_path).rglob('*_ea_update.gpkg'))
                for _ea_old_path in _ea_found:
                    _ea_old_name = _ea_old_path.name
                    if _ea_old_name == ea_new_name:
                        continue
                    _ea_new_path = _ea_old_path.parent / ea_new_name
                    try:
                        if _ea_new_path.exists():
                            _ea_new_path.unlink()
                        _ea_old_path.rename(_ea_new_path)
                    except Exception as e:
                        QgsApplication.instance().messageLog().logMessage(
                            f"Could not rename ea_update file '{_ea_old_name}': {e}",
                            "qfieldmod", Qgis.Warning)
                        continue
                    if os.path.exists(_proj_path):
                        if _proj_path.lower().endswith('.qgz'):
                            _tmp = _proj_path + '.tmp_ea'
                            try:
                                with zipfile.ZipFile(_proj_path, 'r') as _zin:
                                    _names = _zin.namelist()
                                    _qgs = next((n for n in _names if n.lower().endswith('.qgs')), None)
                                    if _qgs:
                                        _txt = _zin.read(_qgs).decode('utf-8', errors='ignore').replace(_ea_old_name, ea_new_name)
                                        with zipfile.ZipFile(_tmp, 'w', compression=zipfile.ZIP_DEFLATED) as _zout:
                                            for _n in _names:
                                                _zout.writestr(_n, _txt.encode('utf-8') if _n == _qgs else _zin.read(_n))
                                os.replace(_tmp, _proj_path)
                            except Exception as e:
                                QgsApplication.instance().messageLog().logMessage(
                                    f"Could not patch qgz for ea_update rename: {e}", "qfieldmod", Qgis.Warning)
                                if os.path.exists(_tmp):
                                    os.remove(_tmp)
                        else:
                            try:
                                with open(_proj_path, 'r', encoding='utf-8', errors='ignore') as _f:
                                    _txt = _f.read().replace(_ea_old_name, ea_new_name)
                                with open(_proj_path, 'w', encoding='utf-8') as _f:
                                    _f.write(_txt)
                            except Exception as e:
                                QgsApplication.instance().messageLog().logMessage(
                                    f"Could not patch qgs for ea_update rename: {e}", "qfieldmod", Qgis.Warning)
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"ea_update rename block failed: {e}", "qfieldmod", Qgis.Warning)

            # Final check before reporting success: warn immediately if the
            # packaged project still references missing local files.
            try:
                _validate_packaged_project_sources()
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not validate packaged project sources: {e}",
                    "qfieldmod",
                    Qgis.Warning,
                )



            self.do_post_offline_convert_action(True)
        except PackagingCanceledError:
            # packaging was canceled by user, we do nothing.
            return
        except Exception as e:
            QgsApplication.instance().messageLog().logMessage(
                "Packaging failed with exception:\n{}\n{}".format(e, traceback.format_exc()),
                "qfieldmod",
                Qgis.Critical,
            )
            self.iface.messageBar().pushWarning("Export Error", str(e))
            self.do_post_offline_convert_action(False)
            raise
        finally:
            QApplication.restoreOverrideCursor()
            self._offline_convertor = None

        # Keep dialog open after export so user can continue working.
        # Batch mode still closes via _show_batch_completion_and_close().

        self.progress_group.setEnabled(True)
        # Recompute button states after export; these can remain disabled
        # depending on prior UI transitions.
        self.validate_group_selection()
        # Keep single-run workflow responsive right after export.
        if not self.is_batch_mode:
            self.next_geocode.setEnabled(True)
            self.run_batch.setEnabled(True)
        

    # ------------------------------------------------------------------
    # EA Level helpers
    # ------------------------------------------------------------------

    def _clip_raster_sync(self, raster_file, selected_layer, code_digits, parent_export_path, convert_to_mbtiles=True, output_suffix="_img"):
        """Clip *raster_file* to *selected_layer* on the main thread.

        Returns (success: bool, message: str).  ``message`` is the output
        raster path on success, or an error string on failure.
        Source raster is a GeoPackage (*_img.gpkg); output is a GeoTIFF.
        When *convert_to_mbtiles* is True the TIF is further converted to
        MBTiles via gdal_translate; otherwise the TIF is kept as-is.
        All QGIS processing calls stay on the main thread to avoid the
        Windows access-violation crash caused by running them in a QThread.
        """
        try:
            self.update_total(0, 100, f"Clipping raster for {code_digits}...")
            self.update_task(0, 100)
            QApplication.processEvents()

            if not raster_file or not os.path.exists(raster_file):
                return False, "Invalid raster file."

            if not isinstance(selected_layer, QgsVectorLayer):
                return False, "Invalid vector layer."

            self.update_total(30, 100, "Creating buffer mask...")
            self.update_task(30, 100)
            QApplication.processEvents()

            buffer_distance = 0.001000
            buffer_output = os.path.join(tempfile.gettempdir(), f"{code_digits}_buffered_mask.gpkg")
            buffer_result = processing.run("native:buffer", {
                "INPUT": selected_layer,
                "DISTANCE": buffer_distance,
                "SEGMENTS": 5,
                "DISSOLVE": True,
                "OUTPUT": buffer_output,
            })
            if not buffer_result or not os.path.exists(buffer_output):
                return False, "Buffer creation failed."

            self.update_total(60, 100, "Clipping raster...")
            self.update_task(60, 100)
            QApplication.processEvents()

            os.makedirs(parent_export_path, exist_ok=True)
            output_raster = os.path.join(parent_export_path, f"{code_digits}{output_suffix}.tif")

            clip_result = processing.run("gdal:cliprasterbymasklayer", {
                "INPUT": raster_file,
                "MASK": buffer_output,
                "SOURCE_CRS": None,
                "TARGET_CRS": None,
                "NODATA": None,
                "ALPHA_BAND": False,
                "CROP_TO_CUTLINE": True,
                "KEEP_RESOLUTION": True,
                "SET_RESOLUTION": False,
                "X_RESOLUTION": None,
                "Y_RESOLUTION": None,
                "MULTITHREADING": False,
                "OPTIONS": "",
                "DATA_TYPE": 0,
                "EXTRA": "",
                "OUTPUT": output_raster,
            })
            if not clip_result or not os.path.exists(output_raster):
                return False, "Clipped output file was not created."

            self.update_total(90, 100, "Building pyramids...")
            self.update_task(90, 100)
            QApplication.processEvents()

            processing.run("gdal:overviews", {
                "INPUT": output_raster,
                "FORMAT": 0,
                "LEVELS": "8,16,32,64,128",
                "RESAMPLING": None,
            })

            # Convert .tif → .mbtiles using QGIS-bundled gdal_translate
            if convert_to_mbtiles:
                self.update_total(95, 100, "Converting to MBTiles...")
                self.update_task(95, 100)
                QApplication.processEvents()

                mbtiles_output = output_raster[:-4] + ".mbtiles"
                try:
                    gdal_translate_exe = os.path.join(
                        QgsApplication.prefixPath(), "bin", "gdal_translate.exe"
                    )
                    if not os.path.exists(gdal_translate_exe):
                        gdal_translate_exe = "gdal_translate"
                    subprocess.run(
                        [
                            gdal_translate_exe,
                            "-of", "MBTiles",
                            "-co", "TILE_FORMAT=JPEG",
                            output_raster,
                            mbtiles_output,
                        ],
                        check=True,
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    try:
                        os.remove(output_raster)
                    except Exception:
                        pass
                    output_raster = mbtiles_output
                except Exception as _conv_err:
                    # Clean up intermediate .tif before surfacing the error
                    try:
                        os.remove(output_raster)
                    except Exception:
                        pass
                    return False, f"MBTiles conversion failed: {_conv_err}"

            self.update_total(100, 100, f"Raster ready for {code_digits}")
            self.update_task(100, 100)
            QApplication.processEvents()

            return True, output_raster

        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # EA Layer assignment panel helpers
    # ------------------------------------------------------------------

    def _build_ea_layer_panel(self):
        """Create the layer assignment group box with dropdowns for each layer role."""
        panel = QGroupBox(self.tr("Layer Assignment"))
        grid = QGridLayout(panel)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setVerticalSpacing(4)

        # Column header for Visible
        vis_header = QLabel(self.tr("Visible"))
        vis_header.setToolTip(self.tr("Whether this layer is visible in the packaged project"))
        vis_header.setStyleSheet("font-weight: bold; font-size: 11px;")
        vis_header.setAlignment(Qt.AlignCenter)
        grid.addWidget(vis_header, 0, 2)

        # (attribute_name, label, required)
        self._ea_layer_roles = [
            ("_ea_combo_bgy",        self.tr("Barangay layer (*_bgy)"),         True),
            ("_ea_combo_bldg",       self.tr("Building points (*_bldg_point)"),  True),
            ("_ea_combo_landmark",   self.tr("Landmark layer (*_landmark)"),     True),
            ("_ea_combo_block",      self.tr("Block layer (*_block)"),           False),
            ("_ea_combo_road",       self.tr("Road layer (*_road)"),             False),
            ("_ea_combo_river",      self.tr("River layer (*_river)"),           False),
            ("_ea_combo_bridge",     self.tr("Bridge layer (*_bridge)"),         False),
            ("_ea_combo_railroad",   self.tr("Railroad layer (*_railroad)"),     False),
        ]

        for row, (attr, label, required) in enumerate(self._ea_layer_roles):
            grid_row = row + 1  # offset by 1 for the header row
            lbl = QLabel(label)
            if not required:
                lbl.setStyleSheet("color: gray;")
            combo = QComboBox()
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            setattr(self, attr, combo)
            grid.addWidget(lbl, grid_row, 0)
            grid.addWidget(combo, grid_row, 1)

            # Visible checkbox
            vis_chk = QCheckBox()
            vis_chk.setChecked(True)
            vis_chk.setToolTip(self.tr("Show/hide this layer in the packaged project"))
            vis_chk.setStyleSheet("margin-left: 12px;")
            setattr(self, attr + "_visible", vis_chk)
            grid.addWidget(vis_chk, grid_row, 2, Qt.AlignCenter)

        return panel

    def _build_bgy_layer_panel(self):
        """Create the BGY layer assignment group box with dropdowns for each layer role."""
        panel = QGroupBox(self.tr("Layer Assignment"))
        grid = QGridLayout(panel)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setVerticalSpacing(4)

        # Column header for Visible
        vis_header = QLabel(self.tr("Visible"))
        vis_header.setToolTip(self.tr("Whether this layer is visible in the packaged project"))
        vis_header.setStyleSheet("font-weight: bold; font-size: 11px;")
        vis_header.setAlignment(Qt.AlignCenter)
        grid.addWidget(vis_header, 0, 2)

        # (attribute_name, label, required)
        self._bgy_layer_roles = [
            ("_bgy_combo_ea",        self.tr("EA layer (*_ea)"),                 True),
            ("_bgy_combo_bldg",      self.tr("Building points (*_bldg_point)"),  True),
            ("_bgy_combo_landmark",  self.tr("Landmark layer (*_landmark)"),     True),
            ("_bgy_combo_block",     self.tr("Block layer (*_block)"),           False),
            ("_bgy_combo_road",      self.tr("Road layer (*_road)"),             False),
            ("_bgy_combo_river",     self.tr("River layer (*_river)"),           False),
            ("_bgy_combo_bridge",    self.tr("Bridge layer (*_bridge)"),         False),
            ("_bgy_combo_railroad",  self.tr("Railroad layer (*_railroad)"),     False),
        ]

        for row, (attr, label, required) in enumerate(self._bgy_layer_roles):
            grid_row = row + 1  # offset by 1 for the header row
            lbl = QLabel(label)
            if not required:
                lbl.setStyleSheet("color: gray;")
            combo = QComboBox()
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            setattr(self, attr, combo)
            grid.addWidget(lbl, grid_row, 0)
            grid.addWidget(combo, grid_row, 1)

            # Visible checkbox
            vis_chk = QCheckBox()
            vis_chk.setChecked(True)
            vis_chk.setToolTip(self.tr("Show/hide this layer in the packaged project"))
            vis_chk.setStyleSheet("margin-left: 12px;")
            setattr(self, attr + "_visible", vis_chk)
            grid.addWidget(vis_chk, grid_row, 2, Qt.AlignCenter)

        return panel

    def _build_raster_config_panel(self):
        """Create the raster configuration panel with satellite image and additional mbtiles selectors."""
        panel = QGroupBox(self.tr("Raster Configuration"))
        grid = QGridLayout(panel)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setVerticalSpacing(4)

        # Column header for Visible
        vis_header = QLabel(self.tr("Visible"))
        vis_header.setToolTip(self.tr("Whether this raster layer is visible in the packaged project"))
        vis_header.setStyleSheet("font-weight: bold; font-size: 11px;")
        vis_header.setAlignment(Qt.AlignCenter)
        grid.addWidget(vis_header, 0, 2)

        # --- Row 1: Satellite Image Format dropdown ---
        format_label = QLabel(self.tr("Satellite Image Format"))
        grid.addWidget(format_label, 1, 0)

        self._raster_type_combo = QComboBox()
        self._raster_type_combo.addItems([
            self.tr("GeoPackage (*_img.gpkg)"),
            self.tr("MBTiles (*_img.mbtiles)"),
            self.tr("Both GPKG and MBTiles")
        ])
        settings = QSettings()
        saved_format = settings.value("raster_satellite_format", 0, type=int)
        self._raster_type_combo.setCurrentIndex(saved_format)
        grid.addWidget(self._raster_type_combo, 1, 1)

        # --- Row 2: Satellite Image directory ---
        self._raster_satellite_dir_label = QLabel(self.tr("Satellite Image Directory"))
        self._raster_satellite_dir_label.setToolTip(self.tr("Directory containing satellite image files"))
        grid.addWidget(self._raster_satellite_dir_label, 2, 0)

        self._raster_satellite_dir = QgsFileWidget()
        self._raster_satellite_dir.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self._raster_satellite_dir.setDialogTitle(self.tr("Select Satellite Image Directory"))
        self._raster_satellite_dir.setFilter("")
        saved_sat_dir = settings.value("satellite_dir_path", "", type=str)
        if saved_sat_dir:
            self._raster_satellite_dir.setFilePath(saved_sat_dir)
        self._raster_satellite_dir.fileChanged.connect(
            lambda path: QSettings().setValue("satellite_dir_path", path)
        )
        grid.addWidget(self._raster_satellite_dir, 2, 1)

        self._raster_satellite_visible = QCheckBox()
        self._raster_satellite_visible.setChecked(True)
        self._raster_satellite_visible.setToolTip(self.tr("Show/hide the satellite raster in the packaged project"))
        self._raster_satellite_visible.setStyleSheet("margin-left: 12px;")
        grid.addWidget(self._raster_satellite_visible, 2, 2, Qt.AlignCenter)

        # --- Row 3: Convert to MBTiles checkbox ---
        self._raster_convert_mbtiles = QCheckBox(self.tr("Convert satellite to MBTiles"))
        saved_convert = settings.value("raster_convert_mbtiles", True, type=bool)
        self._raster_convert_mbtiles.setChecked(saved_convert)
        self._raster_convert_mbtiles.setToolTip(self.tr(
            "Convert the clipped satellite .tif to .mbtiles format. Uncheck to keep as .tif."
        ))
        self._raster_convert_mbtiles.stateChanged.connect(
            lambda state: QSettings().setValue("raster_convert_mbtiles", state == Qt.Checked)
        )
        grid.addWidget(self._raster_convert_mbtiles, 3, 0, 1, 2)

        # --- Row 4: Additional raster (.mbtiles) directory ---
        self._raster_additional_dir_label = QLabel(self.tr("Additional Raster Directory (.mbtiles)"))
        self._raster_additional_dir_label.setToolTip(self.tr("Directory containing {pppmm}.mbtiles files"))
        self._raster_additional_dir_label.setStyleSheet("color: gray;")
        grid.addWidget(self._raster_additional_dir_label, 4, 0)

        self._raster_additional_dir = QgsFileWidget()
        self._raster_additional_dir.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self._raster_additional_dir.setDialogTitle(self.tr("Select Additional Raster Directory"))
        self._raster_additional_dir.setFilter("")
        saved_add_dir = settings.value("additional_raster_dir_path", "", type=str)
        if saved_add_dir:
            self._raster_additional_dir.setFilePath(saved_add_dir)
        self._raster_additional_dir.fileChanged.connect(
            lambda path: QSettings().setValue("additional_raster_dir_path", path)
        )
        grid.addWidget(self._raster_additional_dir, 4, 1)

        self._raster_additional_visible = QCheckBox()
        self._raster_additional_visible.setChecked(True)
        self._raster_additional_visible.setToolTip(self.tr("Show/hide the additional raster in the packaged project"))
        self._raster_additional_visible.setStyleSheet("margin-left: 12px;")
        grid.addWidget(self._raster_additional_visible, 4, 2, Qt.AlignCenter)

        # Connect format dropdown index change to handle dynamic showing/hiding
        self._raster_type_combo.currentIndexChanged.connect(self._on_satellite_format_changed)
        self._raster_type_combo.currentIndexChanged.connect(
            lambda index: QSettings().setValue("raster_satellite_format", index)
        )
        # Initialize dynamic flow state
        self._on_satellite_format_changed(saved_format)

        return panel

    def _on_satellite_format_changed(self, index):
        """Show/hide options based on the chosen format selection."""
        # Check if elements are fully initialized before trying to modify visibility
        has_sat = hasattr(self, '_raster_satellite_dir') and hasattr(self, '_raster_satellite_dir_label') and hasattr(self, '_raster_satellite_visible')
        has_convert = hasattr(self, '_raster_convert_mbtiles')
        has_add = hasattr(self, '_raster_additional_dir') and hasattr(self, '_raster_additional_dir_label') and hasattr(self, '_raster_additional_visible')

        if index == 0:  # GeoPackage
            # Show Satellite Image Directory
            if has_sat:
                self._raster_satellite_dir_label.setVisible(True)
                self._raster_satellite_dir.setVisible(True)
                self._raster_satellite_visible.setVisible(True)
            # Show and enable Convert to MBTiles option
            if has_convert:
                self._raster_convert_mbtiles.setVisible(True)
                self._raster_convert_mbtiles.setEnabled(True)
                saved_convert = QSettings().value("raster_convert_mbtiles", True, type=bool)
                self._raster_convert_mbtiles.setChecked(saved_convert)
                self._raster_convert_mbtiles.setToolTip(self.tr(
                    "Convert the clipped satellite .tif to .mbtiles format. Uncheck to keep as .tif."
                ))
            # Hide Additional Raster Directory
            if has_add:
                self._raster_additional_dir_label.setVisible(False)
                self._raster_additional_dir.setVisible(False)
                self._raster_additional_visible.setVisible(False)

        elif index == 1:  # MBTiles
            # Show Satellite Image Directory
            if has_sat:
                self._raster_satellite_dir_label.setVisible(True)
                self._raster_satellite_dir.setVisible(True)
                self._raster_satellite_visible.setVisible(True)
            # Hide Convert to MBTiles option (output is automatically MBTiles)
            if has_convert:
                self._raster_convert_mbtiles.setChecked(True)
                self._raster_convert_mbtiles.setVisible(False)
            # Hide Additional Raster Directory
            if has_add:
                self._raster_additional_dir_label.setVisible(False)
                self._raster_additional_dir.setVisible(False)
                self._raster_additional_visible.setVisible(False)

        elif index == 2:  # Both GPKG and MBTiles
            # Show Satellite Image Directory
            if has_sat:
                self._raster_satellite_dir_label.setVisible(True)
                self._raster_satellite_dir.setVisible(True)
                self._raster_satellite_visible.setVisible(True)
            # Show and enable Convert to MBTiles option
            if has_convert:
                self._raster_convert_mbtiles.setVisible(True)
                self._raster_convert_mbtiles.setEnabled(True)
                saved_convert = QSettings().value("raster_convert_mbtiles", True, type=bool)
                self._raster_convert_mbtiles.setChecked(saved_convert)
                self._raster_convert_mbtiles.setToolTip(self.tr(
                    "Convert the clipped satellite .tif to .mbtiles format. Uncheck to keep as .tif."
                ))
            # Show Additional Raster Directory
            if has_add:
                self._raster_additional_dir_label.setVisible(True)
                self._raster_additional_dir.setVisible(True)
                self._raster_additional_visible.setVisible(True)

    def _auto_detect_ea_layers(self):
        """Populate each layer assignment combo with auto-detected best match."""
        if not hasattr(self, '_ea_layer_roles'):
            return
        if self.output_dropdown.currentText() != self.tr("EA Level"):
            return

        suffix_map = {
            "_ea_combo_bgy":      ("_bgy",),
            "_ea_combo_bldg":     ("_bldg_point", "_bldgpts", "_bldg_points"),
            "_ea_combo_landmark": ("_landmark",),
            "_ea_combo_block":    ("_block",),
            "_ea_combo_road":     ("_road",),
            "_ea_combo_river":    ("_river",),
            "_ea_combo_bridge":   ("_bridge",),
            "_ea_combo_railroad": ("_railroad",),
        }

        all_vector_layers = sorted([
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and lyr.isValid()
        ], key=lambda l: l.name())

        for attr, suffixes in suffix_map.items():
            combo = getattr(self, attr, None)
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(self.tr("— None —"), None)

            matched_id = None
            for lyr in all_vector_layers:
                lname = self._normalized_layer_name(lyr.name()).lower()
                combo.addItem(lyr.name(), lyr.id())
                if matched_id is None and any(lname.endswith(s) for s in suffixes):
                    matched_id = lyr.id()

            if matched_id:
                idx = combo.findData(matched_id)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _get_ea_assigned_layer(self, attr):
        """Return the QgsVectorLayer assigned to a combo, or None."""
        combo = getattr(self, attr, None)
        if combo is None:
            return None
        layer_id = combo.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def _auto_detect_bgy_layers(self):
        """Populate each BGY layer assignment combo with auto-detected best match."""
        if not hasattr(self, '_bgy_layer_roles'):
            return
        if self.output_dropdown.currentText() != self.tr("Barangay Level"):
            return

        suffix_map = {
            "_bgy_combo_ea":      ("_ea",),
            "_bgy_combo_bldg":    ("_bldg_point", "_bldgpts", "_bldg_points"),
            "_bgy_combo_landmark": ("_landmark",),
            "_bgy_combo_block":   ("_block",),
            "_bgy_combo_road":    ("_road",),
            "_bgy_combo_river":   ("_river",),
            "_bgy_combo_bridge":  ("_bridge",),
            "_bgy_combo_railroad": ("_railroad",),
        }

        all_vector_layers = sorted([
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and lyr.isValid()
        ], key=lambda l: l.name())

        for attr, suffixes in suffix_map.items():
            combo = getattr(self, attr, None)
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(self.tr("— None —"), None)

            matched_id = None
            for lyr in all_vector_layers:
                lname = self._normalized_layer_name(lyr.name()).lower()
                combo.addItem(lyr.name(), lyr.id())
                if matched_id is None and any(lname.endswith(s) for s in suffixes):
                    matched_id = lyr.id()

            if matched_id:
                idx = combo.findData(matched_id)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _get_bgy_assigned_layer(self, attr):
        """Return the QgsVectorLayer assigned to a BGY combo, or None."""
        combo = getattr(self, attr, None)
        if combo is None:
            return None
        layer_id = combo.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def _build_individual_export_panel(self):
        """Create the individual export layer list panel with checkboxes and formats."""
        panel = QGroupBox(self.tr("Individual Export Layers"))
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Simplified description
        label = QLabel(self.tr(
            "Select layers to export as separate files alongside the packaged project."
        ))
        label.setWordWrap(True)
        label.setStyleSheet("color: #555; font-size: 11px; margin-bottom: 2px;")
        layout.addWidget(label)

        # --- Toolbar row with Select All / Deselect All buttons ---
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        toolbar_layout.addWidget(QLabel(self.tr("Export:")))
        self._export_select_all_btn = QPushButton(self.tr("All"))
        self._export_deselect_all_btn = QPushButton(self.tr("None"))
        self._export_select_all_btn.setFixedHeight(22)
        self._export_deselect_all_btn.setFixedHeight(22)
        self._export_select_all_btn.setToolTip(self.tr("Check all layers for individual file export"))
        self._export_deselect_all_btn.setToolTip(self.tr("Uncheck all layers for individual file export"))
        self._export_select_all_btn.clicked.connect(lambda: self._toggle_export_table_column(0, True))
        self._export_deselect_all_btn.clicked.connect(lambda: self._toggle_export_table_column(0, False))
        toolbar_layout.addWidget(self._export_select_all_btn)
        toolbar_layout.addWidget(self._export_deselect_all_btn)

        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        # --- Table ---
        self._export_table = QTableWidget(0, 3)
        self._export_table.setHorizontalHeaderLabels([
            self.tr("Export"), self.tr("Layer"), self.tr("Format")
        ])
        header = self._export_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self._export_table.setColumnWidth(0, 50)
        self._export_table.setColumnWidth(2, 80)
        self._export_table.verticalHeader().setVisible(False)
        self._export_table.setSelectionMode(QTableWidget.NoSelection)
        self._export_table.setAlternatingRowColors(True)
        self._export_table.setMinimumHeight(150)

        # Tooltips on column headers
        self._export_table.horizontalHeaderItem(0).setToolTip(
            self.tr("Check to export this layer as a separate file"))
        self._export_table.horizontalHeaderItem(1).setToolTip(
            self.tr("Output file name (based on geocode + layer suffix)"))
        self._export_table.horizontalHeaderItem(2).setToolTip(
            self.tr("Output file format for the exported layer"))

        layout.addWidget(self._export_table)
        return panel

    def _toggle_export_table_column(self, column, checked):
        """Toggle all checkboxes in the given column of the export table."""
        if not hasattr(self, '_export_table'):
            return
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self._export_table.rowCount()):
            item = self._export_table.item(row, column)
            if item and (item.flags() & Qt.ItemIsUserCheckable):
                item.setCheckState(state)

    def _refresh_individual_export_list(self):
        """Populate the individual export table with current vector layers."""
        if not hasattr(self, '_export_table'):
            return
            
        self._export_table.setRowCount(0)
        
        all_vector_layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and lyr.isValid()
        ]
        
        # Sort checked layers to the top, then alphabetically
        def sort_key(lyr):
            lname_lower = self._normalized_layer_name(lyr.name()).lower()
            is_checked = "pppmmbbbeeeeee" in lname_lower or "_bldg" in lname_lower or "bldg" in lname_lower
            return (not is_checked, lyr.name().lower())
            
        all_vector_layers.sort(key=sort_key)
        
        for lyr in all_vector_layers:
            row = self._export_table.rowCount()
            self._export_table.insertRow(row)
            
            lname_norm = self._normalized_layer_name(lyr.name())
            lname_lower = lname_norm.lower()

            # --- Col 0: Export checkbox ---
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            if "pppmmbbbeeeeee" in lname_lower or "_bldg" in lname_lower or "bldg" in lname_lower:
                chk_item.setCheckState(Qt.Checked)
            else:
                chk_item.setCheckState(Qt.Unchecked)
            chk_item.setData(Qt.UserRole, lyr.id())
            chk_item.setToolTip(self.tr("Export this layer as a separate file"))
            self._export_table.setItem(row, 0, chk_item)
            
            # --- Col 1: Output name (with original name in tooltip) ---
            orig_name = lname_norm
            suffix = orig_name
            for placeholder in ("pppmmbbbeeeeee", "pppmmbbb", "pppmm"):
                if placeholder in orig_name.lower():
                    idx = orig_name.lower().find(placeholder)
                    part_after = orig_name[idx + len(placeholder):]
                    
                    # Apply suffix transformation rule:
                    # - If part_after contains '_', keep from the first '_' onwards
                    # - Otherwise, discard it
                    if "_" in part_after:
                        u_idx = part_after.find("_")
                        suffix = part_after[u_idx:]
                    else:
                        suffix = ""
                    break
            
            display_text = f"{{geocode}}{suffix}"
            
            name_item = QTableWidgetItem(display_text)
            name_item.setFlags(Qt.ItemIsEnabled)
            name_item.setToolTip(self.tr("Source: {}").format(lyr.name()))
            self._export_table.setItem(row, 1, name_item)
            
            # --- Col 2: Format dropdown ---
            combo = QComboBox()
            combo.addItems([".shp", ".gpkg", ".geojson"])
            if "bldg" in lname_lower:
                combo.setCurrentText(".geojson")
            else:
                combo.setCurrentText(".shp")
            combo.setToolTip(self.tr("Output format for this layer"))
            self._export_table.setCellWidget(row, 2, combo)

    # ------------------------------------------------------------------

    def _populate_ea_list(self):
        """Fill the EA multi-select list with all distinct ea_geocode values."""
        if not hasattr(self, '_ea_list_widget'):
            return
        if self.output_dropdown.currentText() != self.tr("EA Level"):
            return
        
        self._ea_list_widget.blockSignals(True)
        self._ea_list_widget.clear()
        
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
            
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if lyr.name() == sel_name:
                        selected_layer = lyr
                        break
                except Exception:
                    continue
                    
        if selected_layer is None:
            self._ea_list_widget.blockSignals(False)
            return
            
        ea_geocode_index = selected_layer.fields().indexOf("ea_geocode")
        if ea_geocode_index == -1:
            self._ea_list_widget.blockSignals(False)
            return
            
        barangay_index = selected_layer.fields().indexOf('barangay')
        if barangay_index == -1:
            barangay_index = selected_layer.fields().indexOf('Barangay')
            
        checked_bgy_prefixes = set(self._get_checked_bgy_names())
        
        geocodes = set()
        bgy_names = {}
        request = QgsFeatureRequest()
        request.setFlags(QgsFeatureRequest.NoGeometry)
        attribs = [ea_geocode_index]
        if barangay_index != -1:
            attribs.append(barangay_index)
        request.setSubsetOfAttributes(attribs)
        for f in selected_layer.getFeatures(request):
            code = str(f.attributes()[ea_geocode_index])
            if code is None:
                continue
            code_5 = code[:5]
            if checked_bgy_prefixes and code_5 not in checked_bgy_prefixes:
                continue
            geocodes.add(code)
            
            if len(code) >= 8 and barangay_index != -1:
                bname = str(f.attributes()[barangay_index])
                if bname:
                    bgy_names[code[:8]] = bname
            
        # Group by barangay (first 8 characters)
        bgy_groups = {}
        for code in geocodes:
            if len(code) >= 8:
                bgy = code[:8]
                if bgy not in bgy_groups:
                    bgy_groups[bgy] = set()
                bgy_groups[bgy].add(code)
            
        for bgy in sorted(bgy_groups.keys()):
            parent_item = QTreeWidgetItem(self._ea_list_widget)
            bname = bgy_names.get(bgy, "")
            display_text = f"{bgy}_{bname}" if bname else bgy
            parent_item.setText(0, display_text)
            parent_item.setFlags(parent_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            parent_item.setCheckState(0, Qt.Checked)
            
            for code in sorted(bgy_groups[bgy]):
                child_item = QTreeWidgetItem(parent_item)
                child_item.setText(0, code)
                child_item.setFlags(child_item.flags() | Qt.ItemIsUserCheckable)
                child_item.setCheckState(0, Qt.Checked)
                
            parent_item.setExpanded(False)
            
        self._ea_list_widget.blockSignals(False)
        self._adjust_widget_height_to_content(self._ea_list_widget)

    def _ea_select_all(self):
        self._ea_list_widget.blockSignals(True)
        for i in range(self._ea_list_widget.topLevelItemCount()):
            parent = self._ea_list_widget.topLevelItem(i)
            parent.setCheckState(0, Qt.Checked)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, Qt.Checked)
        self._ea_list_widget.blockSignals(False)

    def _ea_deselect_all(self):
        self._ea_list_widget.blockSignals(True)
        for i in range(self._ea_list_widget.topLevelItemCount()):
            parent = self._ea_list_widget.topLevelItem(i)
            parent.setCheckState(0, Qt.Unchecked)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, Qt.Unchecked)
        self._ea_list_widget.blockSignals(False)

    def _get_checked_ea_geocodes(self):
        checked = []
        for i in range(self._ea_list_widget.topLevelItemCount()):
            parent = self._ea_list_widget.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.Checked:
                    checked.append(child.text(0))
        return checked

    def _populate_filter_tree(self):
        """Fill the Tree filter with City/Municipalities as parents and Barangays as children."""
        if not hasattr(self, '_filter_tree_widget'):
            return
            
        output_level = self.output_dropdown.currentText()
        if output_level not in [self.tr("Barangay Level"), self.tr("EA Level")]:
            return
            
        self._filter_tree_widget.blockSignals(True)
        self._filter_tree_widget.clear()
        
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
            
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if lyr.name() == sel_name:
                        selected_layer = lyr
                        break
                except Exception:
                    continue

        desired = '_ea' if output_level == self.tr('EA Level') else '_bgy'
        if selected_layer and selected_layer.name().endswith(desired):
            geocode_index = selected_layer.fields().indexOf('geocode')
            citymun_index = selected_layer.fields().indexOf('city_mun')
            if citymun_index == -1:
                citymun_index = selected_layer.fields().indexOf('City_mun')
            barangay_index = selected_layer.fields().indexOf('barangay')
            if barangay_index == -1:
                barangay_index = selected_layer.fields().indexOf('Barangay')

            if geocode_index != -1 and citymun_index != -1 and barangay_index != -1:
                # Group barangays by citymun
                # citymun_dict[citymun_name] = set of (geocode_prefix, barangay_name)
                citymun_dict = {}
                request = QgsFeatureRequest()
                request.setFlags(QgsFeatureRequest.NoGeometry)
                request.setSubsetOfAttributes([geocode_index, citymun_index, barangay_index])
                for feature in selected_layer.getFeatures(request):
                    code = str(feature.attributes()[geocode_index])
                    city_name = str(feature.attributes()[citymun_index])
                    bgy_name = str(feature.attributes()[barangay_index])
                    if not code or not city_name or not bgy_name:
                        continue
                        
                    city_key = f"{code[:5]}_{city_name}"
                    bgy_val = f"{code[:8]}_{bgy_name}"
                    
                    if city_key not in citymun_dict:
                        citymun_dict[city_key] = set()
                    citymun_dict[city_key].add(bgy_val)
                
                # Build tree items
                for city_key in sorted(citymun_dict.keys()):
                    parent_item = QTreeWidgetItem(self._filter_tree_widget)
                    parent_item.setText(0, city_key)
                    parent_item.setFlags(parent_item.flags() | Qt.ItemIsUserCheckable)
                    parent_item.setCheckState(0, Qt.Checked)
                    
        self._filter_tree_widget.blockSignals(False)
        self._adjust_widget_height_to_content(self._filter_tree_widget)
        self._update_lists_from_filter_tree()

    def _on_filter_tree_item_changed(self, item, column):
        # We use Qt.ItemIsAutoTristate, so checking/unchecking parents automatically cascades to children.
        # We just need to trigger the final list population.
        self._update_lists_from_filter_tree()

    def _on_filter_tree_item_clicked(self, item, column):
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers & Qt.ShiftModifier and getattr(self, '_last_clicked_tree_item', None):
            # Flatten tree
            all_items = []
            for i in range(self._filter_tree_widget.topLevelItemCount()):
                top = self._filter_tree_widget.topLevelItem(i)
                all_items.append(top)
                for j in range(top.childCount()):
                    all_items.append(top.child(j))
                    
            try:
                start_idx = all_items.index(self._last_clicked_tree_item)
                end_idx = all_items.index(item)
                
                if start_idx > end_idx:
                    start_idx, end_idx = end_idx, start_idx
                    
                target_state = item.checkState(0)
                
                self._filter_tree_widget.blockSignals(True)
                for i in range(start_idx, end_idx + 1):
                    all_items[i].setCheckState(0, target_state)
                self._filter_tree_widget.blockSignals(False)
                self._update_lists_from_filter_tree()
            except ValueError:
                pass
                
        self._last_clicked_tree_item = item

    def _filter_tree_select_all(self):
        self._filter_tree_widget.blockSignals(True)
        for i in range(self._filter_tree_widget.topLevelItemCount()):
            item = self._filter_tree_widget.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)
        self._filter_tree_widget.blockSignals(False)
        self._update_lists_from_filter_tree()

    def _filter_tree_deselect_all(self):
        self._filter_tree_widget.blockSignals(True)
        for i in range(self._filter_tree_widget.topLevelItemCount()):
            item = self._filter_tree_widget.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)
        self._filter_tree_widget.blockSignals(False)
        self._update_lists_from_filter_tree()

    def _get_checked_bgy_names(self):
        checked_bgy_prefixes = []
        for i in range(self._filter_tree_widget.topLevelItemCount()):
            parent_item = self._filter_tree_widget.topLevelItem(i)
            if parent_item.checkState(0) == Qt.Checked:
                # extract the 5-digit prefix
                checked_bgy_prefixes.append(parent_item.text(0).split('_')[0])
        return checked_bgy_prefixes

    def _populate_bgy_list(self):
        """Fill the BGY multi-select list with geocode values filtered by selected barangay names."""
        if not hasattr(self, '_bgy_list_widget'):
            return
        if self.output_dropdown.currentText() != self.tr("Barangay Level"):
            return
            
        self._bgy_list_widget.blockSignals(True)
        self._bgy_list_widget.clear()
        
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if lyr.name() == sel_name:
                        selected_layer = lyr
                        break
                except Exception:
                    continue
                    
        if selected_layer is None:
            self._bgy_list_widget.blockSignals(False)
            self._on_bgy_item_changed()
            return
            
        geocode_index = selected_layer.fields().indexOf("geocode")
        if geocode_index == -1:
            self._bgy_list_widget.blockSignals(False)
            self._on_bgy_item_changed()
            return
            
        barangay_index = selected_layer.fields().indexOf('barangay')
        if barangay_index == -1:
            barangay_index = selected_layer.fields().indexOf('Barangay')

        checked_bgy_prefixes = set(self._get_checked_bgy_names())

        # Extract first 8 characters (pppmmbbb) and get unique values
        geocodes = set()
        bgy_names = {}
        request = QgsFeatureRequest()
        request.setFlags(QgsFeatureRequest.NoGeometry)
        attribs = [geocode_index]
        if barangay_index != -1:
            attribs.append(barangay_index)
        request.setSubsetOfAttributes(attribs)
        for f in selected_layer.getFeatures(request):
            code = str(f.attributes()[geocode_index])
            if code is None:
                continue
            code_8 = code[:8]
            code_5 = code[:5]
            if checked_bgy_prefixes and code_5 not in checked_bgy_prefixes:
                continue
            geocodes.add(code_8)
            
            if len(code_8) >= 8 and barangay_index != -1:
                bname = str(f.attributes()[barangay_index])
                if bname:
                    bgy_names[code_8] = bname
            
        for geocode in sorted(geocodes):
            bname = bgy_names.get(geocode, "")
            display_text = f"{geocode}_{bname}" if bname else geocode
            item = QListWidgetItem(display_text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self._bgy_list_widget.addItem(item)
            
        self._bgy_list_widget.blockSignals(False)
        self._adjust_widget_height_to_content(self._bgy_list_widget)
        self._on_bgy_item_changed()

    def _bgy_select_all(self):
        for i in range(self._bgy_list_widget.count()):
            self._bgy_list_widget.item(i).setCheckState(Qt.Checked)

    def _bgy_deselect_all(self):
        for i in range(self._bgy_list_widget.count()):
            self._bgy_list_widget.item(i).setCheckState(Qt.Unchecked)

    def _get_checked_bgy_geocodes(self):
        return [
            self._bgy_list_widget.item(i).text().split('_')[0]
            for i in range(self._bgy_list_widget.count())
            if self._bgy_list_widget.item(i).checkState() == Qt.Checked
        ]

    def _on_bgy_item_changed(self):
        """Update Export button state when BGY items are checked/unchecked."""
        if self.output_dropdown.currentText() != self.tr("Barangay Level"):
            return
        num_checked = sum(
            1 for i in range(self._bgy_list_widget.count())
            if self._bgy_list_widget.item(i).checkState() == Qt.Checked
        )
        self.button_box.button(QDialogButtonBox.Save).setEnabled(num_checked > 0)

    # ------------------------------------------------------------------
    # EA Level batch export
    # ------------------------------------------------------------------

    def run_ea_batch_export(self):
        """Iterate through every feature of the EA layer and package each one.

        Steps per EA geocode:
          1. Filter project layers to that EA (ea_geocode field).
          2. Clip the satellite raster to that EA's geometry.
          3. Package the filtered project as a QField .qgz into
             ``{ExportDir}/{ea_geocode}/``.
        """
        # --- Validate inputs ---
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
        if selected_layer is None:
            QMessageBox.warning(self, "Selection Error", "Please select a valid EA layer.")
            return

        ea_geocode_index = selected_layer.fields().indexOf("ea_geocode")
        if ea_geocode_index == -1:
            QMessageBox.warning(
                self, "Field Error",
                "The selected EA layer must have an 'ea_geocode' field.",
            )
            return

        satellite_dir = self._raster_satellite_dir.filePath()
        if not satellite_dir or not os.path.isdir(satellite_dir):
            QMessageBox.warning(
                self, "Directory Error",
                "Please select a valid satellite image directory before exporting.",
            )
            return

        # Validate required layer assignments
        missing_required = []
        for attr, label, required in getattr(self, "_ea_layer_roles", []):
            if required and self._get_ea_assigned_layer(attr) is None:
                missing_required.append(label)
        if missing_required:
            QMessageBox.warning(
                self, "Missing Required Layers",
                "The following required layers are not assigned:\n\n"
                + "\n".join(f"  • {l}" for l in missing_required)
                + "\n\nPlease assign them in the Layer Assignment panel.",
            )
            return

        # Use the checked items from the EA list widget
        geocodes = self._get_checked_ea_geocodes()
        if not geocodes:
            QMessageBox.warning(self, "No Selection", "Please check at least one EA geocode to process.")
            return

        export_folder = Path(self.manualDir.text())

        # Lock the UI during the batch run
        self.is_batch_mode = True
        self.batch_cancel_requested = False
        self._set_batch_ui_locked(True)
        self.button_box.button(QDialogButtonBox.Save).setEnabled(False)

        # Disable the QGIS layer tree so the user cannot double-click / drag
        # layers while OfflineConverter is rebuilding them.  Interacting with
        # a layer whose C++ object is being recreated causes an access violation.
        try:
            self.iface.layerTreeView().setEnabled(False)
        except Exception:
            pass

        processed_count = 0
        errors = []
        total_geocodes = len(geocodes)

        # Initialise the total (batch) progress bar for EA count tracking.
        # OfflineConverter's per-layer progress will be redirected to
        # layerProgressBar via the _ea_batch_total flag in update_total().
        self._ea_batch_total = total_geocodes
        self.totalProgressBar.setMaximum(total_geocodes)
        self.totalProgressBar.setValue(0)

        try:
            for ea_index, ea_geocode in enumerate(geocodes):
                if self.batch_cancel_requested:
                    break
                try:
                    self.statusLabel.setText(
                        f"EA {ea_index + 1}/{total_geocodes}: {ea_geocode} — filtering layers..."
                    )
                    QApplication.processEvents()

                    # Re-fetch the EA layer by ID each iteration — OfflineConverter
                    # can delete and recreate layer C++ objects, so any reference
                    # obtained before the loop becomes a dangling pointer after the
                    # first export.
                    current_ea_layer = QgsProject.instance().mapLayer(selected_data)
                    if current_ea_layer is None or not current_ea_layer.isValid():
                        raise RuntimeError(
                            "EA layer is no longer available in the project. "
                            "Re-open the dialog and try again."
                        )

                    # 1. Filter all project layers to this EA
                    self._filter_ea_layers(current_ea_layer, ea_geocode)
                    QApplication.processEvents()

                    # 2. Resolve satellite image for this EA geocode
                    # Source: {satellite_dir}/{pppmm}_img.<ext> based on format selection
                    pppmm = ea_geocode[:5]
                    
                    format_idx = self._raster_type_combo.currentIndex() if hasattr(self, '_raster_type_combo') else 0
                    raster_file = None
                    if format_idx == 0:
                        raster_file = os.path.join(satellite_dir, f"{pppmm}_img.gpkg")
                    elif format_idx == 1:
                        raster_file = os.path.join(satellite_dir, f"{pppmm}_img.mbtiles")
                    else:
                        # Try GPKG first, then MBTiles
                        gpkg_path = os.path.join(satellite_dir, f"{pppmm}_img.gpkg")
                        mbtiles_path = os.path.join(satellite_dir, f"{pppmm}_img.mbtiles")
                        if os.path.exists(gpkg_path):
                            raster_file = gpkg_path
                        elif os.path.exists(mbtiles_path):
                            raster_file = mbtiles_path
                        else:
                            raster_file = gpkg_path  # Default for error reporting
                    
                    if not raster_file or not os.path.exists(raster_file):
                        ext_str = "_img.gpkg" if format_idx == 0 else ("_img.mbtiles" if format_idx == 1 else "_img.gpkg or _img.mbtiles")
                        QgsApplication.instance().messageLog().logMessage(
                            f"No satellite image found for {ea_geocode}: {raster_file}",
                            "qfieldmod", Qgis.Warning,
                        )
                        errors.append(f"{ea_geocode}: Missing satellite image ({pppmm}{ext_str}) — skipped")
                        continue

                    self.statusLabel.setText(
                        f"EA {ea_index + 1}/{total_geocodes}: {ea_geocode} — clipping satellite image..."
                    )
                    QApplication.processEvents()

                    # 3. Clip the satellite raster to this EA's geometry (main thread)
                    subfolder_path = str(export_folder / ea_geocode)
                    # temp/final paths will be resolved from the actual clip output
                    # (_clip_raster_sync returns .mbtiles on success or .tif as fallback)
                    self.temp_raster_path = None
                    self.final_raster_path = None

                    clip_ok, clip_msg = self._clip_raster_sync(
                        raster_file, current_ea_layer, ea_geocode, tempfile.gettempdir(),
                        convert_to_mbtiles=self._raster_convert_mbtiles.isChecked()
                    )
                    QApplication.processEvents()

                    if not clip_ok:
                        raise RuntimeError(f"Raster clipping failed: {clip_msg}")

                    # Derive correct extension from actual output (.mbtiles or .tif)
                    actual_ext = os.path.splitext(clip_msg)[1]  # e.g. ".mbtiles"
                    self.temp_raster_path = clip_msg
                    self.final_raster_path = os.path.join(
                        subfolder_path, f"{ea_geocode}_img{actual_ext}"
                    )

                    # 3b. Clip additional raster (.mbtiles) if configured
                    self._additional_raster_temp_path = None
                    self._additional_raster_final_path = None
                    add_dir = self._raster_additional_dir.filePath() if hasattr(self, '_raster_additional_dir') else ""
                    if add_dir and os.path.isdir(add_dir):
                        add_src = os.path.join(add_dir, f"{pppmm}.mbtiles")
                        if os.path.exists(add_src):
                            self.statusLabel.setText(
                                f"EA {ea_index + 1}/{total_geocodes}: {ea_geocode} — clipping additional raster..."
                            )
                            QApplication.processEvents()

                            add_clip_ok, add_clip_msg = self._clip_raster_sync(
                                add_src, current_ea_layer, ea_geocode, tempfile.gettempdir(),
                                convert_to_mbtiles=True, output_suffix="_img_new"
                            )
                            if add_clip_ok:
                                self._additional_raster_temp_path = add_clip_msg
                                self._additional_raster_final_path = os.path.join(
                                    subfolder_path, f"{ea_geocode}_img_new.mbtiles"
                                )
                            else:
                                QgsApplication.instance().messageLog().logMessage(
                                    f"Additional raster clip failed for {ea_geocode}: {add_clip_msg}",
                                    "qfieldmod", Qgis.Warning,
                                )

                    self.statusLabel.setText(
                        f"EA {ea_index + 1}/{total_geocodes}: {ea_geocode} — packaging..."
                    )
                    QApplication.processEvents()

                    # 4. Package the project for this EA
                    self._package_ea_single(ea_geocode, export_folder)
                    QApplication.processEvents()

                    processed_count += 1
                    self.totalProgressBar.setValue(processed_count)
                    self.statusLabel.setText(
                        f"EA {processed_count}/{total_geocodes} done — last: {ea_geocode}"
                    )
                    QApplication.processEvents()

                except Exception as e:
                    errors.append(f"{ea_geocode}: {e}")

            # Reset layer filters after all iterations
            try:
                self.reset_filter()
            except Exception:
                pass

        finally:
            was_cancelled = self.batch_cancel_requested
            self.is_batch_mode = False
            self.batch_cancel_requested = False
            self._ea_batch_total = 0  # Restore update_total to normal mode
            self._set_batch_ui_locked(False)
            try:
                self.iface.layerTreeView().setEnabled(True)
            except Exception:
                pass

        # Summary
        if was_cancelled:
            summary = (
                f"EA Export Cancelled\n\n"
                f"Processed: {processed_count} of {len(geocodes)}"
            )
        else:
            summary = (
                f"EA Export Complete\n\n"
                f"Total packaged: {processed_count} of {len(geocodes)}"
            )
        if errors:
            preview = "\n".join(errors[:5])
            if len(errors) > 5:
                preview += f"\n...and {len(errors) - 5} more"
            summary += f"\n\nErrors:\n{preview}"

        self.batch_summary = summary
        self._reload_project_after_ea_batch = True
        QTimer.singleShot(100, self._show_batch_completion_and_close)

    def _filter_ea_layers(self, ea_layer, ea_geocode):
        """Apply subset filters for ``ea_geocode`` using the user-assigned layers.

        Layers are NOT renamed — original names are preserved.
        Optional linear layers (_road, _river, _bridge, _railroad) are spatially
        clipped to the bgy layer extent so only features in the area are exported.
        """
        # --- Assigned layers from the panel ---
        bgy_layer      = self._get_ea_assigned_layer("_ea_combo_bgy")
        bldg_layer     = self._get_ea_assigned_layer("_ea_combo_bldg")
        landmark_layer = self._get_ea_assigned_layer("_ea_combo_landmark")
        block_layer    = self._get_ea_assigned_layer("_ea_combo_block")
        road_layer     = self._get_ea_assigned_layer("_ea_combo_road")
        river_layer    = self._get_ea_assigned_layer("_ea_combo_river")
        bridge_layer   = self._get_ea_assigned_layer("_ea_combo_bridge")
        railroad_layer = self._get_ea_assigned_layer("_ea_combo_railroad")

        # --- Apply subset filters (no renaming) ---
        bgy_prefix = ea_geocode[:8]   # first 8 chars = pppmmbbb

        # EA layer: exact match on ea_geocode
        if isinstance(ea_layer, QgsVectorLayer) and ea_layer.isValid():
            ea_layer.setSubsetString(f"ea_geocode = '{ea_geocode}'")

        # Barangay layer: match first 8 chars of geocode column (geocode stores pppmmbbb000000)
        for lyr in (bgy_layer, landmark_layer):
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            lyr.setSubsetString(f"substr(\"geocode\", 1, 8) = '{bgy_prefix}'")

        # Building points layer: prefer ea_geocode column (exact match),
        # fall back to first 14 chars of bsn_geoid column.
        # Block layer: same logic.
        for lyr in (bldg_layer, block_layer):
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            fields = lyr.fields()
            if fields.indexOf("ea_geocode") != -1:
                lyr.setSubsetString(f"\"ea_geocode\" = '{ea_geocode}'")
            elif fields.indexOf("bsn_geoid") != -1:
                lyr.setSubsetString(f"substr(\"bsn_geoid\", 1, 14) = '{ea_geocode}'")
            else:
                # Last resort: geocode prefix match
                lyr.setSubsetString(f"substr(\"geocode\", 1, 8) = '{bgy_prefix}'")

        # ea_update: keep unfiltered
        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            if self._normalized_layer_name(lyr.name()).lower().endswith("_ea_update"):
                lyr.setSubsetString("")

        # Optional linear layers: select by location against the bgy layer
        linear_layers = [l for l in (road_layer, river_layer, bridge_layer, railroad_layer) if l]
        if linear_layers and bgy_layer and bgy_layer.isValid():
            # Build the union geometry directly from the filtered bgy features.
            # Using qgis:selectbylocation with a subset-filtered layer as the
            # INTERSECT input is unreliable — some QGIS versions evaluate
            # against the full unfiltered dataset, causing zero matches.
            bgy_geoms = [
                f.geometry()
                for f in bgy_layer.getFeatures()
                if f.geometry() and not f.geometry().isNull()
            ]
            bgy_union = QgsGeometry.unaryUnion(bgy_geoms) if bgy_geoms else None

            if bgy_union and not bgy_union.isEmpty():
                bgy_crs = bgy_layer.crs()
                bgy_bbox = bgy_union.boundingBox()
                for lyr in linear_layers:
                    if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                        continue
                    try:
                        lyr_crs = lyr.crs()
                        # Transform to the linear layer's CRS if needed
                        if bgy_crs != lyr_crs:
                            xform = QgsCoordinateTransform(
                                bgy_crs, lyr_crs, QgsProject.instance()
                            )
                            lyr_union = QgsGeometry(bgy_union)
                            lyr_union.transform(xform)
                            lyr_bbox = xform.transformBoundingBox(bgy_bbox)
                        else:
                            lyr_union = bgy_union
                            lyr_bbox = bgy_bbox

                        # Bounding-box pre-filter (fast), then exact intersection check
                        request = QgsFeatureRequest().setFilterRect(lyr_bbox)

                        # Determine the actual primary key field name — it varies
                        # by format (GeoPackage: fid, Shapefile: may differ, etc.)
                        pk_indices = lyr.dataProvider().pkAttributeIndexes()
                        if pk_indices:
                            pk_field = lyr.fields().at(pk_indices[0]).name()
                            candidate_ids = [
                                str(f.attribute(pk_indices[0]))
                                for f in lyr.getFeatures(request)
                                if f.geometry() and not f.geometry().isNull()
                                and f.geometry().intersects(lyr_union)
                            ]
                        else:
                            pk_field = "fid"
                            candidate_ids = [
                                str(f.id())
                                for f in lyr.getFeatures(request)
                                if f.geometry() and not f.geometry().isNull()
                                and f.geometry().intersects(lyr_union)
                            ]

                        if candidate_ids:
                            lyr.setSubsetString(f'"{pk_field}" IN ({",".join(candidate_ids)})')
                        else:
                            lyr.setSubsetString("1=0")
                    except Exception as e:
                        QgsApplication.instance().messageLog().logMessage(
                            f"Could not spatially filter {lyr.name()}: {e}",
                            "qfieldmod", Qgis.Warning,
                        )
            else:
                # bgy features empty after filter — leave linear layers unfiltered
                for lyr in linear_layers:
                    lyr.setSubsetString("")
        elif linear_layers:
            # No bgy layer assigned — leave linear layers unfiltered
            for lyr in linear_layers:
                lyr.setSubsetString("")

        self._ensure_ea_update_not_offline_and_writable()

        # Set initial map canvas extent to the EA layer (filtered to this geocode)
        # so QField opens zoomed to the individual EA boundary.
        try:
            if ea_layer and ea_layer.isValid():
                # updateExtents() forces QGIS to recalculate the layer extent
                # based on the active subset filter set earlier in this method.
                # Without it, extent() returns the stale cached full-layer extent.
                ea_layer.updateExtents()
                extent = ea_layer.extent()
                if not extent.isEmpty():
                    # Add a small buffer so features aren't at the very edge.
                    extent = extent.buffered(extent.width() * 0.1 or 0.001)
                    self.iface.mapCanvas().setExtent(extent)
                    self.iface.mapCanvas().refresh()
        except Exception as _e:
            QgsApplication.instance().messageLog().logMessage(
                f"Could not zoom canvas to EA extent: {_e}", "qfieldmod", Qgis.Warning,
            )

        # Apply snapping config so it is saved into the exported QGZ.
        try:
            self.auto_snap_layer()
        except Exception as _e:
            QgsApplication.instance().messageLog().logMessage(
                f"Could not apply snapping for EA export: {_e}", "qfieldmod", Qgis.Warning,
            )

        QgsProject.instance().write()

    def _export_individual_layers(self, code_digits, subfolder_path, packaged_project_file):
        """Generic method to export selected layers individually and update the QGZ project."""
        if not hasattr(self, '_export_table'):
            return
            
        project_path = str(packaged_project_file)
        if not os.path.exists(project_path):
            return

        export_configs = []
        for row in range(self._export_table.rowCount()):
            chk_item = self._export_table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.Checked:
                layer_id = chk_item.data(Qt.UserRole)
                name_item = self._export_table.item(row, 1)
                layer_name = name_item.text() if name_item else ""
                combo = self._export_table.cellWidget(row, 2)
                target_ext = combo.currentText() if combo else ".shp"
                
                # Suffix is everything after the {geocode} placeholder
                suffix = ""
                placeholder = "{geocode}"
                if placeholder in layer_name:
                    idx = layer_name.find(placeholder)
                    suffix = layer_name[idx + len(placeholder):]
                
                # Replace spaces with underscores for clean filename/layername on disk,
                # but keep the suffix format clean.
                clean_suffix = suffix.replace(" ", "_")
                target_filename = f"{code_digits}{clean_suffix}{target_ext}"
                target_name = f"{code_digits}{clean_suffix}"
                
                export_configs.append({
                    "layer_id": layer_id,
                    "layer_name": layer_name,
                    "target_ext": target_ext,
                    "target_filename": target_filename,
                    "target_name": target_name
                })
        
        # Collect layer visibility preferences from the Layer Assignment panel.
        # Each role combo has a companion _visible checkbox (e.g. _ea_combo_bgy_visible).
        # Maps layer_id -> bool (True = visible, False = hidden)
        visibility_map = {}
        is_ea = self.output_dropdown.currentText() == self.tr("EA Level")
        layer_roles = getattr(self, '_ea_layer_roles', []) if is_ea else getattr(self, '_bgy_layer_roles', [])
        for attr, _label, _req in layer_roles:
            combo = getattr(self, attr, None)
            vis_chk = getattr(self, attr + "_visible", None)
            if combo and vis_chk:
                layer_id = combo.currentData()
                if layer_id:
                    visibility_map[layer_id] = vis_chk.isChecked()

        has_visibility_changes = any(not v for v in visibility_map.values())

        if not export_configs and not has_visibility_changes:
            return

        qgs_text_cached = None
        qgs_name_in_zip = None
        if project_path.lower().endswith(".qgz"):
            try:
                with zipfile.ZipFile(project_path, "r") as zin:
                    all_names = zin.namelist()
                    qgs_name_in_zip = next((n for n in all_names if n.lower().endswith(".qgs")), None)
                    if not qgs_name_in_zip: return
                    qgs_text_cached = zin.read(qgs_name_in_zip).decode("utf-8", errors="ignore")
            except Exception:
                return
        else:
            try:
                with open(project_path, "r", encoding="utf-8", errors="ignore") as f:
                    qgs_text_cached = f.read()
            except Exception:
                return

        try:
            root_xml = ET.fromstring(qgs_text_cached)
        except Exception:
            return

        changed_xml = False
        files_to_delete = set()
        # Track which XML maplayer IDs have already been claimed by a config,
        # so that when two configs share the same display name (e.g. both
        # "{geocode}" but different formats) the name-based fallback does not
        # match the same XML element twice.
        processed_ml_ids = set()
        
        for config in export_configs:
            original_ds = None
            ds_el_to_update = None
            matched_xml_id = None
            
            # --- 1. Try matching by layer ID (exact or substring) ---
            for ml in root_xml.findall(".//maplayer"):
                id_el = ml.find("id")
                if id_el is not None:
                    xml_id = id_el.text or ""
                    if xml_id in processed_ml_ids:
                        continue
                    if xml_id == config["layer_id"] or config["layer_id"] in xml_id:
                        ds_el = ml.find("datasource")
                        if ds_el is not None:
                            original_ds = (ds_el.text or "").strip()
                            ds_el_to_update = ds_el
                            matched_xml_id = xml_id
                        break
                    
            # --- 2. Fallback: match by layer name (skip already-claimed) ---
            if not original_ds:
                resolved_name = config["layer_name"].replace("{geocode}", code_digits)
                orig_layer = QgsProject.instance().mapLayer(config["layer_id"])
                orig_name = orig_layer.name() if orig_layer else ""
                orig_name_norm = self._normalized_layer_name(orig_name) if orig_name else ""
                
                for ml in root_xml.findall(".//maplayer"):
                    id_el = ml.find("id")
                    xml_id = (id_el.text or "") if id_el is not None else ""
                    if xml_id in processed_ml_ids:
                        continue
                    name_el = ml.find("layername")
                    if name_el is not None:
                        current_name = (name_el.text or "").strip()
                        if current_name in (resolved_name, orig_name, orig_name_norm):
                            ds_el = ml.find("datasource")
                            if ds_el is not None:
                                original_ds = (ds_el.text or "").strip()
                                ds_el_to_update = ds_el
                                matched_xml_id = xml_id
                            break

            # --- 3. Fallback: match by datasource content (placeholder names) ---
            # This is the most reliable strategy because it does not depend on
            # layer IDs (which OfflineConverter may regenerate) or layer names
            # (which _rename_and_regroup_layers may have already changed).
            if not original_ds:
                _DS_PLACEHOLDERS = ("pppmmbbbeeeeee", "pppmmbbb", "pppmm")
                for ml in root_xml.findall(".//maplayer"):
                    id_el = ml.find("id")
                    xml_id = (id_el.text or "") if id_el is not None else ""
                    if xml_id in processed_ml_ids:
                        continue
                    ds_el = ml.find("datasource")
                    if ds_el is not None:
                        ds_val = (ds_el.text or "").strip()
                        if any(ph in ds_val.lower() for ph in _DS_PLACEHOLDERS):
                            original_ds = ds_val
                            ds_el_to_update = ds_el
                            matched_xml_id = xml_id
                            break

            if not original_ds:
                continue

            pipe_pos = original_ds.find("|")
            file_part = original_ds[:pipe_pos].strip() if pipe_pos != -1 else original_ds
            uri_extras = original_ds[pipe_pos:] if pipe_pos != -1 else ""
            
            qgz_dir = str(subfolder_path)
            if not os.path.isabs(file_part):
                file_part = os.path.normpath(os.path.join(qgz_dir, file_part))
                
            use_original = False
            if file_part.lower().endswith(('.shp', '.geojson')):
                use_original = True
                
            temp_lyr = None
            if use_original:
                temp_lyr = QgsProject.instance().mapLayer(config["layer_id"])
                
            # If we don't have the original layer, we must read from the file.
            # So the file must exist on disk.
            if (not temp_lyr or not temp_lyr.isValid()) and not os.path.exists(file_part):
                continue

            target_path = os.path.join(qgz_dir, config["target_filename"])
            
            if not temp_lyr or not temp_lyr.isValid():
                full_uri = file_part + uri_extras
                temp_lyr = QgsVectorLayer(full_uri, "temp_export", "ogr")
                
            if not temp_lyr.isValid():
                continue

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.fileEncoding = "UTF-8"
            
            if config["target_ext"] == ".geojson":
                options.driverName = "GeoJSON"
            elif config["target_ext"] == ".shp":
                options.driverName = "ESRI Shapefile"
            elif config["target_ext"] == ".gpkg":
                options.driverName = "GPKG"
                options.layerName = config["target_name"]
            
            write_error = QgsVectorFileWriter.NoError
            try:
                result = QgsVectorFileWriter.writeAsVectorFormatV2(
                    temp_lyr, target_path,
                    QgsProject.instance().transformContext(), options,
                )
                write_error = result[0]
            except Exception:
                write_error = QgsVectorFileWriter.ErrCreateDataSource
            finally:
                del temp_lyr

            if write_error == QgsVectorFileWriter.NoError:
                if config["target_ext"] == ".gpkg":
                    new_ds = f"{config['target_filename']}|layername={config['target_name']}"
                else:
                    new_ds = f"{config['target_filename']}"
                ds_el_to_update.text = new_ds
                changed_xml = True
                
                # Mark this XML maplayer as claimed and config as applied
                if matched_xml_id:
                    processed_ml_ids.add(matched_xml_id)
                config["_applied"] = True
                
                # Rename the layer in the QGZ XML using the matched ID
                if matched_xml_id:
                    for ml in root_xml.findall(".//maplayer"):
                        id_el = ml.find("id")
                        if id_el is not None and id_el.text == matched_xml_id:
                            layername_el = ml.find("layername")
                            if layername_el is not None:
                                layername_el.text = config["target_name"]
                            title_el = ml.find("title")
                            if title_el is not None:
                                title_el.text = config["target_name"]
                            break
                
                # Rename in layer-tree-layer using matched ID
                renamed_ltl = False
                if matched_xml_id:
                    for ltl in root_xml.findall(".//layer-tree-layer"):
                        ltl_id = ltl.get("id", "")
                        if ltl_id == matched_xml_id:
                            ltl.set("name", config["target_name"])
                            renamed_ltl = True
                            break
                
                if not renamed_ltl:
                    # Fallback: try original ID or name
                    for ltl in root_xml.findall(".//layer-tree-layer"):
                        ltl_id = ltl.get("id", "")
                        if ltl_id == config["layer_id"] or config["layer_id"] in ltl_id:
                            ltl.set("name", config["target_name"])
                            renamed_ltl = True
                            break
                
                if not renamed_ltl:
                    resolved_name = config["layer_name"].replace("{geocode}", code_digits)
                    for ltl in root_xml.findall(".//layer-tree-layer"):
                        if ltl.get("name", "") == resolved_name:
                            ltl.set("name", config["target_name"])
                            break
                
                # Mark original file for deletion if it's in the export dir, is not the target, and is a single-layer file type
                qgz_dir_norm = os.path.normcase(qgz_dir)
                file_part_norm = os.path.normcase(file_part)
                target_path_norm = os.path.normcase(target_path)
                if file_part_norm.startswith(qgz_dir_norm) and file_part_norm != target_path_norm:
                    if file_part_norm.endswith(('.shp', '.geojson')):
                        files_to_delete.add(file_part)

        # ---------------------------------------------------------------
        # FINAL SWEEP: catch any maplayers whose datasource was NOT
        # updated by the main loop (e.g. OfflineConverter regenerated
        # the layer ID so neither ID-match nor name-match succeeded).
        # We detect them by checking if the datasource still references
        # a placeholder template file (pppmmbbbeeeeee / pppmmbbb / pppmm).
        # ---------------------------------------------------------------
        _PLACEHOLDERS = ("pppmmbbbeeeeee", "pppmmbbb", "pppmm")
        remaining_configs = [c for c in export_configs if c.get("_applied") is not True]
        
        if remaining_configs:
            for ml in root_xml.findall(".//maplayer"):
                ds_el = ml.find("datasource")
                if ds_el is None:
                    continue
                ds_text = (ds_el.text or "").strip().lower()
                if not ds_text:
                    continue

                # Check if datasource still references a template name
                has_placeholder = any(ph in ds_text for ph in _PLACEHOLDERS)
                if not has_placeholder:
                    continue

                id_el = ml.find("id")
                xml_id = (id_el.text or "") if id_el is not None else ""
                if xml_id in processed_ml_ids:
                    continue

                # Find the best matching unapplied config for this maplayer
                matched_config = None
                for cfg in remaining_configs:
                    if cfg.get("_applied"):
                        continue
                    matched_config = cfg
                    break

                if not matched_config:
                    break

                # Write the export file from the original project layer
                qgz_dir = str(subfolder_path)
                target_path = os.path.join(qgz_dir, matched_config["target_filename"])

                orig_lyr = QgsProject.instance().mapLayer(matched_config["layer_id"])
                if not orig_lyr or not orig_lyr.isValid():
                    continue

                options = QgsVectorFileWriter.SaveVectorOptions()
                options.fileEncoding = "UTF-8"
                if matched_config["target_ext"] == ".geojson":
                    options.driverName = "GeoJSON"
                elif matched_config["target_ext"] == ".shp":
                    options.driverName = "ESRI Shapefile"
                elif matched_config["target_ext"] == ".gpkg":
                    options.driverName = "GPKG"
                    options.layerName = matched_config["target_name"]

                write_ok = False
                try:
                    result = QgsVectorFileWriter.writeAsVectorFormatV2(
                        orig_lyr, target_path,
                        QgsProject.instance().transformContext(), options,
                    )
                    write_ok = (result[0] == QgsVectorFileWriter.NoError)
                except Exception:
                    pass

                if not write_ok:
                    continue

                # Update datasource in XML
                if matched_config["target_ext"] == ".gpkg":
                    ds_el.text = f"{matched_config['target_filename']}|layername={matched_config['target_name']}"
                else:
                    ds_el.text = matched_config["target_filename"]
                changed_xml = True

                # Rename layername / title
                layername_el = ml.find("layername")
                if layername_el is not None:
                    layername_el.text = matched_config["target_name"]
                title_el = ml.find("title")
                if title_el is not None:
                    title_el.text = matched_config["target_name"]

                # Rename layer-tree-layer
                if xml_id:
                    for ltl in root_xml.findall(".//layer-tree-layer"):
                        if ltl.get("id", "") == xml_id:
                            ltl.set("name", matched_config["target_name"])
                            break

                if xml_id:
                    processed_ml_ids.add(xml_id)
                matched_config["_applied"] = True

        # Patch layer visibility in the layer-tree XML based on user selection
        for ltl in root_xml.findall(".//layer-tree-layer"):
            ltl_id = ltl.get("id", "")
            matched_key = None
            if ltl_id in visibility_map:
                matched_key = ltl_id
            else:
                for k in visibility_map:
                    if k in ltl_id:
                        matched_key = k
                        break
            if matched_key is not None:
                new_checked = "Qt::Checked" if visibility_map[matched_key] else "Qt::Unchecked"
                if ltl.get("checked", "") != new_checked:
                    ltl.set("checked", new_checked)
                    changed_xml = True

        if changed_xml:
            patched_text = ET.tostring(root_xml, encoding="unicode")
            if project_path.lower().endswith(".qgz"):
                tmp_path = project_path + ".gentmp"
                try:
                    with zipfile.ZipFile(project_path, "r") as zin:
                        all_names = zin.namelist()
                        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                            for name in all_names:
                                zout.writestr(
                                    name,
                                    patched_text.encode("utf-8") if name == qgs_name_in_zip else zin.read(name),
                                )
                    os.replace(tmp_path, project_path)
                except Exception:
                    pass
            else:
                try:
                    with open(project_path, "w", encoding="utf-8") as f:
                        f.write(patched_text)
                except Exception:
                    pass

        # Build a set of datasources still in use so we never delete a
        # file that a maplayer still references (can happen when two layers
        # share the same source but only one was re-exported).
        still_referenced = set()
        for ml in root_xml.findall(".//maplayer"):
            ds_el = ml.find("datasource")
            if ds_el is not None:
                ds_text = (ds_el.text or "").strip()
                pipe_pos = ds_text.find("|")
                fp = ds_text[:pipe_pos].strip() if pipe_pos != -1 else ds_text
                if not os.path.isabs(fp):
                    fp = os.path.normpath(os.path.join(str(subfolder_path), fp))
                still_referenced.add(os.path.normcase(fp))

        # Clean up old copied shapefiles/geojsons that were re-exported
        for f in files_to_delete:
            # Skip deletion if any maplayer still references this file
            if os.path.normcase(f) in still_referenced:
                continue
            if f.lower().endswith('.shp'):
                src_stem = os.path.splitext(f)[0]
                sidecar_exts = [".shp", ".dbf", ".shx", ".prj", ".cpg",
                                ".qix", ".sbn", ".sbx", ".atx", ".fbn", ".fbx",
                                ".ain", ".aih", ".ixs", ".mxs", ".shp.xml"]
                import time
                for ext in sidecar_exts:
                    try:
                        sidecar = src_stem + ext
                        if os.path.exists(sidecar):
                            # Handle potential windows file lock
                            try:
                                os.remove(sidecar)
                            except PermissionError:
                                time.sleep(0.5)
                                try:
                                    os.remove(sidecar)
                                except Exception:
                                    pass
                    except Exception:
                        pass
            else:
                try:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except PermissionError:
                            time.sleep(0.5)
                            os.remove(f)
                except Exception:
                    pass

    def _copy_additional_raster_and_patch_visibility(self, code_digits, subfolder_path, packaged_project_file):
        """Patch raster layer visibility in the packaged project.

        The additional raster is now loaded into the QGIS project before
        OfflineConverter runs, so the maplayer XML is generated automatically.
        This method only patches the checked/unchecked state in the QGZ for
        both the satellite raster and the additional raster.
        """
        project_path = str(packaged_project_file)
        if not os.path.exists(project_path):
            return

        sat_visible = self._raster_satellite_visible.isChecked() if hasattr(self, '_raster_satellite_visible') else True
        add_visible = self._raster_additional_visible.isChecked() if hasattr(self, '_raster_additional_visible') else True

        # Read the project XML
        qgs_text = None
        qgs_name_in_zip = None
        if project_path.lower().endswith(".qgz"):
            try:
                with zipfile.ZipFile(project_path, "r") as zin:
                    all_names = zin.namelist()
                    qgs_name_in_zip = next((n for n in all_names if n.lower().endswith(".qgs")), None)
                    if not qgs_name_in_zip:
                        return
                    qgs_text = zin.read(qgs_name_in_zip).decode("utf-8", errors="ignore")
            except Exception:
                return
        else:
            try:
                with open(project_path, "r", encoding="utf-8", errors="ignore") as f:
                    qgs_text = f.read()
            except Exception:
                return

        try:
            root_xml = ET.fromstring(qgs_text)
        except Exception:
            return

        changed_xml = False

        for ltl in root_xml.findall(".//layer-tree-layer"):
            ltl_name = ltl.get("name", "").lower()
            if ltl_name.endswith("_img_new"):
                # Additional raster
                new_checked = "Qt::Checked" if add_visible else "Qt::Unchecked"
                if ltl.get("checked", "") != new_checked:
                    ltl.set("checked", new_checked)
                    changed_xml = True
            elif ltl_name.endswith("_img"):
                # Satellite raster
                new_checked = "Qt::Checked" if sat_visible else "Qt::Unchecked"
                if ltl.get("checked", "") != new_checked:
                    ltl.set("checked", new_checked)
                    changed_xml = True

        # --- Write back if changed ---
        if changed_xml:
            patched_text = ET.tostring(root_xml, encoding="unicode")
            if project_path.lower().endswith(".qgz"):
                tmp_path = project_path + ".rastertmp"
                try:
                    with zipfile.ZipFile(project_path, "r") as zin:
                        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                            for name in zin.namelist():
                                zout.writestr(
                                    name,
                                    patched_text.encode("utf-8") if name == qgs_name_in_zip else zin.read(name),
                                )
                    os.replace(tmp_path, project_path)
                except Exception:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
            else:
                try:
                    with open(project_path, "w", encoding="utf-8") as f:
                        f.write(patched_text)
                except Exception:
                    pass


    def _package_ea_single(self, ea_geocode, export_folder):
        """Run OfflineConverter to package the project for one EA geocode.

        The output is written to ``{export_folder}/{ea_geocode}/{ea_geocode}.qgz``.
        """
        code_digits = str(ea_geocode)
        subfolder_path = export_folder / code_digits
        packaged_project_file = subfolder_path / f"{code_digits}.qgz"
        _actual_final = getattr(self, "final_raster_path", None)
        raster_base_name = (
            os.path.basename(_actual_final)
            if _actual_final
            else f"{code_digits}_img.tif"
        )

        # --- Clear / create export subfolder ---------------------------------
        if subfolder_path.exists():
            subfolder_abs = os.path.normcase(os.path.abspath(str(subfolder_path)))
            keep_raster_abs = os.path.normcase(
                os.path.abspath(
                    getattr(self, "final_raster_path", str(subfolder_path / raster_base_name))
                )
            )
            project = QgsProject.instance()
            for lyr in list(project.mapLayers().values()):
                try:
                    src = lyr.source() if hasattr(lyr, "source") else ""
                    if not src or not isinstance(lyr, QgsRasterLayer):
                        continue
                    src_abs = os.path.normcase(os.path.abspath(src))
                    if src_abs.startswith(subfolder_abs) and src_abs != keep_raster_abs:
                        project.removeMapLayer(lyr.id())
                except Exception:
                    continue
            try:
                QApplication.processEvents()
            except Exception:
                pass
            for item in subfolder_path.iterdir():
                try:
                    if item.is_file() and (
                        item.name == raster_base_name
                        or item.name.startswith(raster_base_name + ".")
                    ):
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        for _ in range(5):
                            try:
                                item.unlink()
                                break
                            except PermissionError:
                                QApplication.processEvents()
                                time.sleep(0.2)
                except Exception:
                    pass
        subfolder_path.mkdir(parents=True, exist_ok=True)

        self.qfield_preferences.set_value("exportDirectoryProject", str(subfolder_path))
        self.dirsToCopyWidget.save_settings()
        self._ensure_ea_update_not_offline_and_writable()

        # Remove stale generated rasters from previous iterations
        try:
            keep_sources = set()
            if hasattr(self, "temp_raster_path") and self.temp_raster_path:
                keep_sources.add(os.path.normcase(os.path.abspath(self.temp_raster_path)))
            project = QgsProject.instance()
            for lyr in list(project.mapLayers().values()):
                if not isinstance(lyr, QgsRasterLayer):
                    continue
                src = lyr.source() or ""
                if not src:
                    continue
                src_abs = os.path.normcase(os.path.abspath(src))
                src_name = os.path.basename(src_abs).lower()
                lyr_name = (lyr.name() or "").lower()
                if (
                    src_name.endswith("_img.tif")
                    or src_name.endswith("_img.mbtiles")
                    or lyr_name.endswith("_img")
                ) and src_abs not in keep_sources:
                    project.removeMapLayer(lyr.id())
        except Exception:
            pass

        # Ensure the current clipped raster is registered in the project
        try:
            desired_raster_name = f"{code_digits}_img"
            current_raster_path = None
            if hasattr(self, "temp_raster_path") and self.temp_raster_path and os.path.exists(self.temp_raster_path):
                current_raster_path = self.temp_raster_path
            elif hasattr(self, "final_raster_path") and self.final_raster_path and os.path.exists(self.final_raster_path):
                current_raster_path = self.final_raster_path
            if current_raster_path:
                current_abs = os.path.normcase(os.path.abspath(current_raster_path))
                found_current = False
                for lyr in QgsProject.instance().mapLayers().values():
                    if not isinstance(lyr, QgsRasterLayer):
                        continue
                    src = lyr.source() or ""
                    if src and os.path.normcase(os.path.abspath(src)) == current_abs:
                        lyr.setName(desired_raster_name)
                        found_current = True
                        break
                if not found_current:
                    raster_layer = QgsRasterLayer(current_raster_path, desired_raster_name)
                    if raster_layer.isValid():
                        QgsProject.instance().addMapLayer(raster_layer, False)
                        QgsProject.instance().layerTreeRoot().addLayer(raster_layer)
                        self.clipped_raster_layer = raster_layer
        except Exception:
            pass

        # EA Level: derive area_of_interest directly from the EA layer's
        # filtered extent so QField opens zoomed to the individual EA boundary.
        # Reading from the canvas is unreliable — compute it from the features.
        area_of_interest_crs = QgsProject.instance().crs().authid()
        area_of_interest = None
        try:
            _ea_lid = self.layer_dropdown.currentData()
            _ea_lyr = QgsProject.instance().mapLayer(_ea_lid) if _ea_lid else None
            if isinstance(_ea_lyr, QgsVectorLayer) and _ea_lyr.isValid():
                # Build the union of all filtered EA features so the AOI polygon
                # tightly wraps the individual EA boundary.
                _ea_geoms = [
                    f.geometry()
                    for f in _ea_lyr.getFeatures()
                    if f.geometry() and not f.geometry().isNull()
                ]
                if _ea_geoms:
                    _ea_union = QgsGeometry.unaryUnion(_ea_geoms)
                    if _ea_union and not _ea_union.isEmpty():
                        # Buffer 10 % so features aren't clipped at the very edge.
                        _bbox = _ea_union.boundingBox()
                        _buf = _bbox.width() * 0.1 or 0.001
                        _ea_union = _ea_union.buffer(_buf, 5)
                        area_of_interest = _ea_union.asWkt()
        except Exception as _aoi_err:
            QgsApplication.instance().messageLog().logMessage(
                f"Could not compute EA area_of_interest from layer: {_aoi_err}",
                "qfieldmod", Qgis.Warning,
            )
        if not area_of_interest:
            # Fallback to canvas extent if geometry union failed.
            area_of_interest = self.iface.mapCanvas().extent().asWktPolygon()

        def _build_converter(offliner_instance):
            converter = OfflineConverter(
                self.project,
                packaged_project_file,
                area_of_interest,
                area_of_interest_crs,
                self.qfield_preferences.value("attachmentDirs"),
                offliner_instance,
                ExportType.Cable,
                dirs_to_copy={},  # EA Level: no extra directories to copy
                export_title=code_digits,
            )
            converter.total_progress_updated.connect(self.update_total)
            converter.task_progress_updated.connect(self.update_task)
            converter.warning.connect(
                lambda title, body: QMessageBox.warning(None, title, body)
            )
            return converter

        def _rewrite_raster_source():
            _actual = getattr(self, "final_raster_path", None)
            raster_filename = os.path.basename(_actual) if _actual else f"{code_digits}_img.tif"
            target_ds = raster_filename

            # Also handle additional raster (_img_new)
            _add_actual = getattr(self, '_additional_raster_final_path', None)
            add_raster_filename = os.path.basename(_add_actual) if _add_actual else None

            project_path = str(packaged_project_file)
            if not os.path.exists(project_path):
                return
            if project_path.lower().endswith(".qgz"):
                tmp_qgz = project_path + ".tmp"
                with zipfile.ZipFile(project_path, "r") as zin:
                    names = zin.namelist()
                    qgs_name = next((n for n in names if n.lower().endswith(".qgs")), None)
                    if not qgs_name:
                        return
                    qgs_text = zin.read(qgs_name).decode("utf-8", errors="ignore")
                    try:
                        root_xml = ET.fromstring(qgs_text)
                        changed = False
                        for ml in root_xml.findall(".//maplayer"):
                            name_el = ml.find("layername")
                            ds_el = ml.find("datasource")
                            layer_name = (name_el.text or "").lower() if name_el is not None else ""
                            ds_text = (ds_el.text or "") if ds_el is not None else ""
                            if ds_el is not None:
                                # Satellite raster (_img)
                                if (
                                    raster_filename.lower() in ds_text.lower()
                                    or (layer_name.endswith("_img") and not layer_name.endswith("_img_new"))
                                ):
                                    ds_el.text = target_ds
                                    changed = True
                                # Additional raster (_img_new)
                                elif add_raster_filename and (
                                    add_raster_filename.lower() in ds_text.lower()
                                    or layer_name.endswith("_img_new")
                                ):
                                    ds_el.text = add_raster_filename
                                    changed = True
                        rewritten = ET.tostring(root_xml, encoding="unicode") if changed else qgs_text
                    except Exception:
                        rewritten = re.sub(
                            rf"(<datasource>)[^<]*{re.escape(raster_filename)}(</datasource>)",
                            rf"\1{target_ds}\2",
                            qgs_text,
                            flags=re.IGNORECASE,
                        )
                    with zipfile.ZipFile(tmp_qgz, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                        for name in names:
                            zout.writestr(
                                name,
                                rewritten.encode("utf-8") if name == qgs_name else zin.read(name),
                            )
                os.replace(tmp_qgz, project_path)
            else:
                with open(project_path, "r", encoding="utf-8", errors="ignore") as f:
                    qgs_text = f.read()
                rewritten = re.sub(
                    rf"(<datasource>)[^<]*{re.escape(raster_filename)}(</datasource>)",
                    rf"\1{target_ds}\2",
                    qgs_text,
                    flags=re.IGNORECASE,
                )
                with open(project_path, "w", encoding="utf-8") as f:
                    f.write(rewritten)

        # Build layer rename map: original display name → {ea_geocode}_suffix
        # Must be captured NOW, before _convert() recreates the C++ layer objects.
        _role_suffixes = {
            "_ea_combo_bgy":      "_bgy",
            "_ea_combo_bldg":     "_bldgpts",
            "_ea_combo_landmark": "_landmark",
            "_ea_combo_block":    "_block",
            "_ea_combo_road":     "_road",
            "_ea_combo_river":    "_river",
            "_ea_combo_bridge":   "_bridge",
            "_ea_combo_railroad": "_railroad",
        }
        layer_rename_map = {}
        for _attr, _suffix in _role_suffixes.items():
            _lyr = self._get_ea_assigned_layer(_attr)
            if _lyr and _lyr.isValid():
                layer_rename_map[self._normalized_layer_name(_lyr.name())] = f"{code_digits}{_suffix}"
        # Also rename the EA layer itself
        _ea_lid = self.layer_dropdown.currentData()
        if _ea_lid:
            _ea_lyr = QgsProject.instance().mapLayer(_ea_lid)
            if _ea_lyr and _ea_lyr.isValid():
                layer_rename_map[self._normalized_layer_name(_ea_lyr.name())] = f"{code_digits}_ea"

        # Rename the Form 2 Geotagging template layer (pppmmbbbeeeeee) to the EA geocode
        _FORM2_TEMPLATE_NAME = "pppmmbbbeeeeee"
        for _lyr in QgsProject.instance().mapLayers().values():
            if self._normalized_layer_name(_lyr.name()) == _FORM2_TEMPLATE_NAME:
                layer_rename_map[_FORM2_TEMPLATE_NAME] = code_digits
                break

        # Add all layers containing placeholders to layer_rename_map (handles copy layers, custom layers, etc.)
        for _lyr in QgsProject.instance().mapLayers().values():
            orig_name = self._normalized_layer_name(_lyr.name())
            new_name = orig_name
            for placeholder in ("pppmmbbbeeeeee", "pppmmbbb", "pppmm"):
                if placeholder in orig_name.lower():
                    idx = orig_name.lower().find(placeholder)
                    part_after = orig_name[idx + len(placeholder):]
                    
                    # Apply suffix transformation rule
                    if "_" in part_after:
                        u_idx = part_after.find("_")
                        suffix = part_after[u_idx:]
                    else:
                        suffix = ""
                    
                    new_name = orig_name[:idx] + code_digits + suffix
                    break
            if new_name != orig_name:
                layer_rename_map[orig_name] = new_name

        bldg_new_name = f"{code_digits}_bldgpts"

        def _rename_and_regroup_layers():
            """Rename exported layers in the packaged QGZ."""
            project_path = str(packaged_project_file)
            if not layer_rename_map or not os.path.exists(project_path):
                return

            def _patch(text):
                try:
                    root = ET.fromstring(text)
                    changed = False

                    # Rename <layername> (and <title>) in every maplayer
                    for ml in root.findall(".//maplayer"):
                        for tag in ("layername", "title"):
                            el = ml.find(tag)
                            if el is not None and el.text and el.text.strip() in layer_rename_map:
                                el.text = layer_rename_map[el.text.strip()]
                                changed = True

                    # Rename name= attribute on every layer-tree-layer
                    for ltl in root.findall(".//layer-tree-layer"):
                        old = ltl.get("name", "")
                        if old in layer_rename_map:
                            ltl.set("name", layer_rename_map[old])
                            changed = True

                    if changed:
                        return ET.tostring(root, encoding="unicode")
                    return text
                except Exception as e:
                    QgsApplication.instance().messageLog().logMessage(
                        f"Layer rename patch error: {e}", "qfieldmod", Qgis.Warning,
                    )
                    return text

            if project_path.lower().endswith(".qgz"):
                tmp = project_path + ".renametmp"
                with zipfile.ZipFile(project_path, "r") as zin:
                    names = zin.namelist()
                    qgs_name = next((n for n in names if n.lower().endswith(".qgs")), None)
                    if not qgs_name:
                        return
                    qgs_text = zin.read(qgs_name).decode("utf-8", errors="ignore")
                    patched = _patch(qgs_text)
                    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                        for name in names:
                            zout.writestr(
                                name,
                                patched.encode("utf-8") if name == qgs_name else zin.read(name),
                            )
                os.replace(tmp, project_path)
            else:
                with open(project_path, "r", encoding="utf-8", errors="ignore") as f:
                    qgs_text = f.read()
                patched = _patch(qgs_text)
                with open(project_path, "w", encoding="utf-8") as f:
                    f.write(patched)



        def _convert():
            try:
                self._offline_convertor.convert()
            except shutil.SameFileError as e:
                src = getattr(e, "filename", None)
                dst = getattr(e, "filename2", None)
                if src and dst:
                    src_abs = os.path.normcase(os.path.abspath(src))
                    dst_abs = os.path.normcase(os.path.abspath(dst))
                    if src_abs != dst_abs:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        if os.path.exists(dst):
                            os.remove(dst)
                        shutil.copy2(src, dst)
                        return
                QgsApplication.instance().messageLog().logMessage(
                    f"Ignoring same-path copy during EA export: {e}", "qfieldmod", Qgis.Info,
                )

        self._offline_convertor = _build_converter(self.offliner)
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            # Make the satellite raster visible in the layer panel right before
            # OfflineConverter snapshots the project state into the QGZ.
            _root = QgsProject.instance().layerTreeRoot()
            _sat_visible = self._raster_satellite_visible.isChecked() if hasattr(self, '_raster_satellite_visible') else True
            for _rl in list(QgsProject.instance().mapLayers().values()):
                if isinstance(_rl, QgsRasterLayer) and self._normalized_layer_name(_rl.name()).lower().endswith("_img"):
                    _rn = _root.findLayer(_rl.id())
                    if _rn:
                        _rn.setItemVisibilityChecked(_sat_visible)

            # Load the additional raster (.mbtiles) into the project so
            # OfflineConverter includes it with full rendering XML.
            _add_temp = getattr(self, '_additional_raster_temp_path', None)
            _add_visible = self._raster_additional_visible.isChecked() if hasattr(self, '_raster_additional_visible') else True
            if _add_temp and os.path.exists(_add_temp):
                _add_rl = QgsRasterLayer(_add_temp, f"{code_digits}_img_new")
                if _add_rl.isValid():
                    QgsProject.instance().addMapLayer(_add_rl, False)
                    _add_node = _root.addLayer(_add_rl)
                    if _add_node:
                        _add_node.setItemVisibilityChecked(_add_visible)

            # Set canvas extent to the filtered EA feature right before convert()
            # so the QGZ stores the correct initial view for QField.
            # zoom_to_layer() uses selectAll()+zoomToSelected() which respects
            # the active subset filter and is more reliable than extent().
            try:
                self.zoom_to_layer(code_digits)
            except Exception:
                pass
            try:
                _convert()
            except IndexError as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"EA export retry after IndexError: {e}", "qfieldmod", Qgis.Warning,
                )
                fallback_offliner = QgisCoreOffliner(offline_editing=False)
                fallback_offliner.warning.connect(self.show_warning)
                self._offline_convertor = _build_converter(fallback_offliner)
                _convert()

            # Move temp raster into the export subfolder
            if hasattr(self, "temp_raster_path") and hasattr(self, "final_raster_path"):
                if os.path.exists(self.temp_raster_path):
                    try:
                        os.makedirs(os.path.dirname(self.final_raster_path), exist_ok=True)
                        if os.path.exists(self.final_raster_path):
                            os.remove(self.final_raster_path)
                        shutil.move(self.temp_raster_path, self.final_raster_path)
                        for lyr in QgsProject.instance().mapLayers().values():
                            if isinstance(lyr, QgsRasterLayer) and lyr.source() == self.final_raster_path:
                                QgsProject.instance().removeMapLayer(lyr.id())
                        clipped_raster_layer = QgsRasterLayer(
                            self.final_raster_path, f"{code_digits}_img"
                        )
                        if clipped_raster_layer.isValid():
                            QgsProject.instance().addMapLayer(clipped_raster_layer, False)
                            QgsProject.instance().layerTreeRoot().addLayer(clipped_raster_layer)
                            self.clipped_raster_layer = clipped_raster_layer
                    except Exception as e:
                        QgsApplication.instance().messageLog().logMessage(
                            f"Could not move raster for {code_digits}: {e}",
                            "qfieldmod", Qgis.Warning,
                        )

            # Move additional raster into the export subfolder
            _add_temp = getattr(self, '_additional_raster_temp_path', None)
            _add_final = getattr(self, '_additional_raster_final_path', None)
            if _add_temp and _add_final and os.path.exists(_add_temp):
                try:
                    os.makedirs(os.path.dirname(_add_final), exist_ok=True)
                    if os.path.exists(_add_final):
                        os.remove(_add_final)
                    shutil.move(_add_temp, _add_final)
                    # Remove old _img_new layers from project, then re-add
                    # so the layer is available for the next iteration.
                    for lyr in list(QgsProject.instance().mapLayers().values()):
                        if isinstance(lyr, QgsRasterLayer) and self._normalized_layer_name(lyr.name()).lower().endswith("_img_new"):
                            QgsProject.instance().removeMapLayer(lyr.id())
                    _new_rl = QgsRasterLayer(_add_final, f"{code_digits}_img_new")
                    if _new_rl.isValid():
                        QgsProject.instance().addMapLayer(_new_rl, False)
                        QgsProject.instance().layerTreeRoot().addLayer(_new_rl)
                except Exception as e:
                    QgsApplication.instance().messageLog().logMessage(
                        f"Could not move additional raster for {code_digits}: {e}",
                        "qfieldmod", Qgis.Warning,
                    )

            try:
                _rewrite_raster_source()
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not rewrite raster source for {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )

            try:
                _rename_and_regroup_layers()
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not rename/regroup layers for {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )

            try:
                self._export_individual_layers(code_digits, subfolder_path, packaged_project_file)
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not export individual layers for {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )

            # Copy additional raster (.mbtiles) and patch visibility for both rasters
            try:
                self._copy_additional_raster_and_patch_visibility(code_digits, subfolder_path, packaged_project_file)
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not copy additional raster for {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )


            self.do_post_offline_convert_action(True)
        except PackagingCanceledError:
            return
        except Exception as e:
            QgsApplication.instance().messageLog().logMessage(
                f"EA packaging failed for {code_digits}: {e}\n{traceback.format_exc()}",
                "qfieldmod", Qgis.Critical,
            )
            raise
        finally:
            QApplication.restoreOverrideCursor()
            self._offline_convertor = None

    # ------------------------------------------------------------------

    def do_post_offline_convert_action(self, is_success):
        """
        Show an information label that the project has been copied
        with a nice link to open the result folder.
        """
        if is_success:
            export_folder = self.get_export_folder_from_dialog()
            result_message = self.tr(
                "Finished creating the project at {result_folder}. Please copy this folder to "
                "your QField device."
            ).format(
                result_folder='<a href="{folder}">{display_folder}</a>'.format(
                    folder=QUrl.fromLocalFile(export_folder).toString(),
                    display_folder=QDir.toNativeSeparators(export_folder),
                )
            )
            status = Qgis.Success
        else:
            result_message = self.tr(
                "Failed to package project. See message log (Python Error) for more details."
            )
            status = Qgis.Warning

        self.iface.messageBar().pushMessage(result_message, status, 0)


    def update_info_visibility(self):
        """
        Show the info label if there are unconfigured layers
        """
        localizedDataPathLayers = []
        for layer in list(self.project.mapLayers().values()):
            layer_source = LayerSource(layer)

            if layer_source.is_localized_path:
                localizedDataPathLayers.append(
                    "- {} ({})".format(layer.name(), layer_source.filename)
                )

        if localizedDataPathLayers:
            if len(localizedDataPathLayers) == 1:
                self.infoLocalizedLayersLabel.setText(
                    self.tr("The layer stored in a localized data path is:\n{}").format(
                        "\n".join(localizedDataPathLayers)
                    )
                )
            else:
                self.infoLocalizedLayersLabel.setText(
                    self.tr(
                        "The layers stored in a localized data path are:\n{}"
                    ).format("\n".join(localizedDataPathLayers))
                )
            self.infoLocalizedLayersLabel.setVisible(True)
            self.infoLocalizedPresentLabel.setVisible(True)
        else:
            self.infoLocalizedLayersLabel.setVisible(False)
            self.infoLocalizedPresentLabel.setVisible(False)
        self.infoGroupBox.setVisible(len(localizedDataPathLayers) > 0)

    def show_settings(self):
        if Qgis.QGIS_VERSION_INT >= 31500:
            self.iface.showProjectPropertiesDialog("QField")
        else:
            dlg = ProjectConfigurationDialog(self.iface.mainWindow())
            dlg.exec_()
        self.update_info_visibility()

    def update_total(self, current, layer_count, message):
        if getattr(self, "_ea_batch_total", 0) > 0 or getattr(self, "_bgy_batch_total", 0) > 0:
            # Batch mode (EA or BGY): OfflineConverter's per-layer "total" progress goes
            # to the layer bar, while the total bar tracks batch progress.
            self.layerProgressBar.setMaximum(layer_count)
            self.layerProgressBar.setValue(current)
            # Don't overwrite the batch status label during OfflineConverter runs
        else:
            self.totalProgressBar.setMaximum(layer_count)
            self.totalProgressBar.setValue(current)
            self.statusLabel.setText(message)

    def update_task(self, progress, max_progress):
        self.layerProgressBar.setMaximum(max_progress)
        self.layerProgressBar.setValue(progress)

    def show_warning(self, _, message):
        # Most messages from the offline editing plugin are not important enough to show in the message bar.
        # In case we find important ones in the future, we need to filter them.
        QgsApplication.instance().messageLog().logMessage(message, "qfieldmod")



    # Custom code
    def run(self):
        try:
            # Initialize progress
            self.update_total(0, 100, "Starting process...")
            self.update_task(0, 100)

            # Resolve selected layer from combo data (we store layer ids)
            selected_layer = None
            selected_data = self.layer_dropdown.currentData()
            if isinstance(selected_data, str):
                selected_layer = QgsProject.instance().mapLayer(selected_data)

            # Fallback: resolve by displayed name if needed
            if selected_layer is None:
                selected_name = self.layer_dropdown.currentText()
                if selected_name:
                    for lyr in QgsProject.instance().mapLayers().values():
                        try:
                            if lyr.name() == selected_name:
                                selected_layer = lyr
                                break
                        except Exception:
                            continue

            selected_geocode = self.geocode_dropdown.currentText()

            # If still no valid layer, warn and stop to avoid crashes when
            # calling methods on None.
            if not selected_layer:
                QMessageBox.warning(self, "Selection Error", "Please select a valid layer.")
                return

            # Initial validation (10%)
            self.update_total(10, 100, "Validating inputs...")
            self.update_task(10, 100)

            if not isinstance(selected_layer, (QgsVectorLayer, QgsRasterLayer)):
                QMessageBox.warning(self, "Selection Error", "Please select a valid layer.")
                return

            if not selected_geocode:
                QMessageBox.warning(self, "Selection Error", "Please select a valid geocode.")
                return

            # Determine prefix based on selected output level (8 or 14 digits)
            base_pref = selected_geocode.split('_', 1)[0] if selected_geocode else ''
            if self.output_dropdown.currentText() == self.tr("EA Level"):
                prefix = base_pref[:14]
            else:
                prefix = base_pref[:8]

            # Layer name validation (20%)
            self.update_total(20, 100, "Checking layer names...")
            self.update_task(20, 100)
            
            print(f"Selected layer: {selected_layer.name()}")
            required = '_ea' if self.output_dropdown.currentText() == self.tr("EA Level") else '_bgy'
            if not selected_layer.name().endswith(required):
                QMessageBox.warning(self, "Layer Error", f"The selected layer must have the suffix '{required}'.")
                return

            # Load layer mapping (30%)
            self.update_total(30, 100, "Loading layer mappings...")
            self.update_task(30, 100)

            self.layers = {
                layer.id(): layer for layer in QgsProject.instance().mapLayers().values()
                if layer.name().endswith((
                    '_bgy', '_ea', '_ea_update', '_block',
                    '_bldgpts', '_bldg_point', '_bldg_points',
                    '_landmark', '_road', '_river', '_bridge', '_railroad'
                ))
            }

            # Process CBMS Form 8 group (60%)
            self.update_total(60, 100, "Processing...")
            self.update_task(60, 100)

            # project = QgsProject.instance()
            # root = project.layerTreeRoot()
            # cbms_group = root.findGroup('CBMS Form 8')
            # if cbms_group is None:
            #     cbms_group = root.addGroup('CBMS Form 8')

            # Process layers (80%)
            self.update_total(80, 100, "Processing layers...")
            self.update_task(80, 100)

            # Rename layers in Base Layers and For Verification groups to reflect current prefix
            root = QgsProject.instance().layerTreeRoot()
            groups = [child for child in root.children() if isinstance(child, QgsLayerTreeGroup)]
            for group in groups:
                if 'Base Layers' in group.name():  # Check for "Base Layers" group
                    for layer in group.findLayers():
                        layer_name = self._normalized_layer_name(layer.layer().name()).lower()
                        # `prefix` was determined earlier from the selected geocode/output level
                        if layer_name.endswith('_bgy'):
                            new_name = f"{prefix}_bgy"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_ea'):
                            new_name = f"{prefix}_ea"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_block'):
                            new_name = f"{prefix}_block"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_bldgpts'):
                            new_name = f"{prefix}_bldgpts"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_bldg_point'):
                            new_name = f"{prefix}_bldgpts"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_bldg_points'):
                            new_name = f"{prefix}_bldgpts"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_landmark'):
                            new_name = f"{prefix}_landmark"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_road'):
                            new_name = f"{prefix}_road"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_river'):
                            new_name = f"{prefix}_river"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_bridge'):
                            new_name = f"{prefix}_bridge"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_railroad'):
                            new_name = f"{prefix}_railroad"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")
                        elif layer_name.endswith('_ea_update'):
                            new_name = f"{prefix}_ea_update"
                            layer.layer().setName(new_name)
                            print(f"Renamed base layer '{layer.layer().name()}' to '{new_name}'")

                elif 'For Verification' in group.name():  # Check for "For Verification" group
                    for layer in group.findLayers():
                        layer_name = self._normalized_layer_name(layer.layer().name()).lower()
                        if layer_name.endswith('_ea_update'):
                            new_name = f"{prefix}_ea_update"
                            layer.layer().setName(new_name)
                            print(f"Renamed verification layer '{layer.layer().name()}' to '{new_name}'")

            # Call the instance method to filter layers
            self.filter_layers(self.layers, selected_geocode)
            self._ensure_ea_update_not_offline_and_writable()

            project = QgsProject.instance()
            project.write()  # Save the project
            print("Project auto-saved.")

            # Complete (100%)
            self.update_total(100, 100, "Filtering complete")
            self.update_task(100, 100)

        except Exception as e:
            # Handle any unexpected exceptions
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")
            print(f"Exception: {e}")  # Print the exception for debugging

    # ------------------------------------------------------------------
    # BGY Level batch export
    # ------------------------------------------------------------------

    def run_bgy_batch_export(self):
        """Iterate through every Barangay geocode and package each one.

        Steps per BGY geocode (first 8 digits of geocode):
          1. Filter project layers to that BGY (geocode field first 8 chars).
          2. Clip the satellite raster to that BGY's geometry.
          3. Package the filtered project as a QField .qgz into
             ``{ExportDir}/{bgy_geocode}/{bgy_geocode}.qgz``.
        """
        # --- Validate inputs ---
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
        if selected_layer is None:
            QMessageBox.warning(self, "Selection Error", "Please select a valid Barangay layer.")
            return

        geocode_index = selected_layer.fields().indexOf("geocode")
        if geocode_index == -1:
            QMessageBox.warning(
                self, "Field Error",
                "The selected Barangay layer must have a 'geocode' field.",
            )
            return

        satellite_dir = self._raster_satellite_dir.filePath()
        if not satellite_dir or not os.path.isdir(satellite_dir):
            QMessageBox.warning(
                self, "Directory Error",
                "Please select a valid satellite image directory before exporting.",
            )
            return

        # Validate required layer assignments
        missing_required = []
        for attr, label, required in getattr(self, "_bgy_layer_roles", []):
            if required and self._get_bgy_assigned_layer(attr) is None:
                missing_required.append(label)
        if missing_required:
            QMessageBox.warning(
                self, "Missing Required Layers",
                "The following required layers are not assigned:\n\n"
                + "\n".join(f"  • {l}" for l in missing_required)
                + "\n\nPlease assign them in the Layer Assignment panel.",
            )
            return

        # Use the checked items from the BGY list widget
        geocodes = self._get_checked_bgy_geocodes()
        if not geocodes:
            QMessageBox.warning(self, "No Selection", "Please check at least one BGY geocode to process.")
            return

        export_folder = Path(self.manualDir.text())

        # Lock the UI during the batch run
        self.is_batch_mode = True
        self.batch_cancel_requested = False
        self._set_batch_ui_locked(True)
        self.button_box.button(QDialogButtonBox.Save).setEnabled(False)

        # Disable the QGIS layer tree so the user cannot double-click / drag
        # layers while OfflineConverter is rebuilding them.
        try:
            self.iface.layerTreeView().setEnabled(False)
        except Exception:
            pass

        processed_count = 0
        errors = []
        total_geocodes = len(geocodes)

        # Initialize the total (batch) progress bar for BGY count tracking.
        self._bgy_batch_total = total_geocodes
        self.totalProgressBar.setMaximum(total_geocodes)
        self.totalProgressBar.setValue(0)

        try:
            for bgy_index, bgy_geocode in enumerate(geocodes):
                if self.batch_cancel_requested:
                    break
                try:
                    self.statusLabel.setText(
                        f"BGY {bgy_index + 1}/{total_geocodes}: {bgy_geocode} — filtering layers..."
                    )
                    QApplication.processEvents()

                    # Re-fetch the BGY layer by ID each iteration
                    current_bgy_layer = QgsProject.instance().mapLayer(selected_data)
                    if current_bgy_layer is None or not current_bgy_layer.isValid():
                        raise RuntimeError(
                            "BGY layer is no longer available in the project. "
                            "Re-open the dialog and try again."
                        )

                    # 1. Filter all project layers to this BGY
                    self._filter_bgy_layers(current_bgy_layer, bgy_geocode)
                    QApplication.processEvents()

                    # 2. Resolve satellite image for this BGY geocode
                    # Source: {satellite_dir}/{pppmm}_img.<ext> based on format selection
                    pppmm = bgy_geocode[:5]
                    
                    format_idx = self._raster_type_combo.currentIndex() if hasattr(self, '_raster_type_combo') else 0
                    raster_file = None
                    if format_idx == 0:
                        raster_file = os.path.join(satellite_dir, f"{pppmm}_img.gpkg")
                    elif format_idx == 1:
                        raster_file = os.path.join(satellite_dir, f"{pppmm}_img.mbtiles")
                    else:
                        # Try GPKG first, then MBTiles
                        gpkg_path = os.path.join(satellite_dir, f"{pppmm}_img.gpkg")
                        mbtiles_path = os.path.join(satellite_dir, f"{pppmm}_img.mbtiles")
                        if os.path.exists(gpkg_path):
                            raster_file = gpkg_path
                        elif os.path.exists(mbtiles_path):
                            raster_file = mbtiles_path
                        else:
                            raster_file = gpkg_path  # Default for error reporting
                    
                    if not raster_file or not os.path.exists(raster_file):
                        ext_str = "_img.gpkg" if format_idx == 0 else ("_img.mbtiles" if format_idx == 1 else "_img.gpkg or _img.mbtiles")
                        QgsApplication.instance().messageLog().logMessage(
                            f"No satellite image found for {bgy_geocode}: {raster_file}",
                            "qfieldmod", Qgis.Warning,
                        )
                        errors.append(f"{bgy_geocode}: Missing satellite image ({pppmm}{ext_str}) — skipped")
                        continue

                    self.statusLabel.setText(
                        f"BGY {bgy_index + 1}/{total_geocodes}: {bgy_geocode} — clipping satellite image..."
                    )
                    QApplication.processEvents()

                    # 3. Clip the satellite raster to this BGY's geometry (main thread)
                    subfolder_path = str(export_folder / bgy_geocode)
                    self.temp_raster_path = None
                    self.final_raster_path = None

                    clip_ok, clip_msg = self._clip_raster_sync(
                        raster_file, current_bgy_layer, bgy_geocode, tempfile.gettempdir(),
                        convert_to_mbtiles=self._raster_convert_mbtiles.isChecked()
                    )
                    QApplication.processEvents()

                    if not clip_ok:
                        raise RuntimeError(f"Raster clipping failed: {clip_msg}")

                    # Derive correct extension from actual output (.mbtiles or .tif)
                    actual_ext = os.path.splitext(clip_msg)[1]  # e.g. ".mbtiles"
                    self.temp_raster_path = clip_msg
                    self.final_raster_path = os.path.join(
                        subfolder_path, f"{bgy_geocode}_img{actual_ext}"
                    )

                    # 3b. Clip additional raster (.mbtiles) if configured
                    self._additional_raster_temp_path = None
                    self._additional_raster_final_path = None
                    add_dir = self._raster_additional_dir.filePath() if hasattr(self, '_raster_additional_dir') else ""
                    if add_dir and os.path.isdir(add_dir):
                        add_src = os.path.join(add_dir, f"{pppmm}.mbtiles")
                        if os.path.exists(add_src):
                            self.statusLabel.setText(
                                f"BGY {bgy_index + 1}/{total_geocodes}: {bgy_geocode} — clipping additional raster..."
                            )
                            QApplication.processEvents()

                            add_clip_ok, add_clip_msg = self._clip_raster_sync(
                                add_src, current_bgy_layer, bgy_geocode, tempfile.gettempdir(),
                                convert_to_mbtiles=True, output_suffix="_img_new"
                            )
                            if add_clip_ok:
                                self._additional_raster_temp_path = add_clip_msg
                                self._additional_raster_final_path = os.path.join(
                                    subfolder_path, f"{bgy_geocode}_img_new.mbtiles"
                                )
                            else:
                                QgsApplication.instance().messageLog().logMessage(
                                    f"Additional raster clip failed for BGY {bgy_geocode}: {add_clip_msg}",
                                    "qfieldmod", Qgis.Warning,
                                )

                    self.statusLabel.setText(
                        f"BGY {bgy_index + 1}/{total_geocodes}: {bgy_geocode} — packaging..."
                    )
                    QApplication.processEvents()

                    # 4. Package the project for this BGY
                    self._package_bgy_single(bgy_geocode, export_folder)
                    QApplication.processEvents()

                    processed_count += 1
                    self.totalProgressBar.setValue(processed_count)
                    self.statusLabel.setText(
                        f"BGY {processed_count}/{total_geocodes} done — last: {bgy_geocode}"
                    )
                    QApplication.processEvents()

                except Exception as e:
                    errors.append(f"{bgy_geocode}: {e}")

            # Reset layer filters after all iterations
            try:
                self.reset_filter()
            except Exception:
                pass

        finally:
            was_cancelled = self.batch_cancel_requested
            self.is_batch_mode = False
            self.batch_cancel_requested = False
            self._bgy_batch_total = 0  # Restore update_total to normal mode
            self._set_batch_ui_locked(False)
            try:
                self.iface.layerTreeView().setEnabled(True)
            except Exception:
                pass

        # Summary
        if was_cancelled:
            summary = (
                f"BGY Export Cancelled\n\n"
                f"Processed: {processed_count} of {len(geocodes)}"
            )
        else:
            summary = (
                f"BGY Export Complete\n\n"
                f"Total packaged: {processed_count} of {len(geocodes)}"
            )
        if errors:
            preview = "\n".join(errors[:5])
            if len(errors) > 5:
                preview += f"\n...and {len(errors) - 5} more"
            summary += f"\n\nErrors:\n{preview}"

        self.batch_summary = summary
        QTimer.singleShot(100, self._show_batch_completion_and_close)

    def _filter_bgy_layers(self, bgy_layer, bgy_geocode):
        """Apply subset filters for first 8 chars of ``bgy_geocode`` using the user-assigned layers.

        Layers are NOT renamed — original names are preserved.
        Optional linear layers (_road, _river, _bridge, _railroad) are spatially
        clipped to the bgy layer extent so only features in the area are exported.
        """
        # --- Assigned layers from the panel ---
        ea_layer        = self._get_bgy_assigned_layer("_bgy_combo_ea")
        bldg_layer      = self._get_bgy_assigned_layer("_bgy_combo_bldg")
        landmark_layer  = self._get_bgy_assigned_layer("_bgy_combo_landmark")
        block_layer     = self._get_bgy_assigned_layer("_bgy_combo_block")
        road_layer      = self._get_bgy_assigned_layer("_bgy_combo_road")
        river_layer     = self._get_bgy_assigned_layer("_bgy_combo_river")
        bridge_layer    = self._get_bgy_assigned_layer("_bgy_combo_bridge")
        railroad_layer  = self._get_bgy_assigned_layer("_bgy_combo_railroad")

        # --- Apply subset filters (no renaming) ---
        bgy_prefix = bgy_geocode[:8]   # first 8 chars = pppmmbbb

        # BGY layer: match first 8 chars of geocode column
        if isinstance(bgy_layer, QgsVectorLayer) and bgy_layer.isValid():
            bgy_layer.setSubsetString(f"substr(\"geocode\", 1, 8) = '{bgy_prefix}'")

        # EA layer: match first 8 chars of geocode column
        if isinstance(ea_layer, QgsVectorLayer) and ea_layer.isValid():
            ea_layer.setSubsetString(f"substr(\"geocode\", 1, 8) = '{bgy_prefix}'")

        # Landmark layer: match first 8 chars of geocode column
        if isinstance(landmark_layer, QgsVectorLayer) and landmark_layer.isValid():
            landmark_layer.setSubsetString(f"substr(\"geocode\", 1, 8) = '{bgy_prefix}'")

        # Building points layer: prefer geocode column (first 8 chars),
        # fall back to first 8 chars of bsn_geoid column.
        # Block layer: same logic.
        for lyr in (bldg_layer, block_layer):
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            fields = lyr.fields()
            if fields.indexOf("geocode") != -1:
                lyr.setSubsetString(f"substr(\"geocode\", 1, 8) = '{bgy_prefix}'")
            elif fields.indexOf("bsn_geoid") != -1:
                lyr.setSubsetString(f"substr(\"bsn_geoid\", 1, 8) = '{bgy_prefix}'")
            else:
                # Last resort: no filter
                lyr.setSubsetString("")

        # ea_update: keep unfiltered
        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                continue
            if self._normalized_layer_name(lyr.name()).lower().endswith("_ea_update"):
                lyr.setSubsetString("")

        # Optional linear layers: select by location against the bgy layer
        linear_layers = [l for l in (road_layer, river_layer, bridge_layer, railroad_layer) if l]
        if linear_layers and bgy_layer and bgy_layer.isValid():
            # Build the union geometry directly from the filtered bgy features.
            bgy_geoms = [
                f.geometry()
                for f in bgy_layer.getFeatures()
                if f.geometry() and not f.geometry().isNull()
            ]
            bgy_union = QgsGeometry.unaryUnion(bgy_geoms) if bgy_geoms else None

            if bgy_union and not bgy_union.isEmpty():
                bgy_crs = bgy_layer.crs()
                bgy_bbox = bgy_union.boundingBox()
                for lyr in linear_layers:
                    if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                        continue
                    try:
                        lyr_crs = lyr.crs()
                        # Transform to the linear layer's CRS if needed
                        if bgy_crs != lyr_crs:
                            xform = QgsCoordinateTransform(
                                bgy_crs, lyr_crs, QgsProject.instance()
                            )
                            lyr_union = QgsGeometry(bgy_union)
                            lyr_union.transform(xform)
                            lyr_bbox = xform.transformBoundingBox(bgy_bbox)
                        else:
                            lyr_union = bgy_union
                            lyr_bbox = bgy_bbox

                        # Bounding-box pre-filter (fast), then exact intersection check
                        request = QgsFeatureRequest().setFilterRect(lyr_bbox)

                        # Determine the actual primary key field name
                        pk_indices = lyr.dataProvider().pkAttributeIndexes()
                        if pk_indices:
                            pk_field = lyr.fields().at(pk_indices[0]).name()
                            candidate_ids = [
                                str(f.attribute(pk_indices[0]))
                                for f in lyr.getFeatures(request)
                                if f.geometry() and not f.geometry().isNull()
                                and f.geometry().intersects(lyr_union)
                            ]
                        else:
                            pk_field = "fid"
                            candidate_ids = [
                                str(f.id())
                                for f in lyr.getFeatures(request)
                                if f.geometry() and not f.geometry().isNull()
                                and f.geometry().intersects(lyr_union)
                            ]

                        if candidate_ids:
                            lyr.setSubsetString(f'"{pk_field}" IN ({",".join(candidate_ids)})')
                        else:
                            lyr.setSubsetString("1=0")
                    except Exception as e:
                        QgsApplication.instance().messageLog().logMessage(
                            f"Could not spatially filter {lyr.name()}: {e}",
                            "qfieldmod", Qgis.Warning,
                        )
            else:
                # bgy features empty after filter — leave linear layers unfiltered
                for lyr in linear_layers:
                    lyr.setSubsetString("")
        elif linear_layers:
            # No bgy layer assigned — leave linear layers unfiltered
            for lyr in linear_layers:
                lyr.setSubsetString("")

        self._ensure_ea_update_not_offline_and_writable()

        # Set initial map canvas extent to the BGY layer (filtered to this geocode)
        # so QField opens zoomed to the individual BGY boundary.
        try:
            if bgy_layer and bgy_layer.isValid():
                # updateExtents() forces QGIS to recalculate the layer extent
                # based on the active subset filter set earlier in this method.
                bgy_layer.updateExtents()
                extent = bgy_layer.extent()
                if not extent.isEmpty():
                    # Add a small buffer so features aren't at the very edge.
                    extent = extent.buffered(extent.width() * 0.1 or 0.001)
                    self.iface.mapCanvas().setExtent(extent)
                    self.iface.mapCanvas().refresh()
        except Exception as _e:
            QgsApplication.instance().messageLog().logMessage(
                f"Could not zoom canvas to BGY extent: {_e}", "qfieldmod", Qgis.Warning,
            )

        # Apply snapping config so it is saved into the exported QGZ.
        try:
            self.auto_snap_layer()
        except Exception as _e:
            QgsApplication.instance().messageLog().logMessage(
                f"Could not apply snapping for BGY export: {_e}", "qfieldmod", Qgis.Warning,
            )

        QgsProject.instance().write()

    def _package_bgy_single(self, bgy_geocode, export_folder):
        """Run OfflineConverter to package the project for one BGY geocode.

        The output is written to ``{export_folder}/{bgy_geocode}/{bgy_geocode}.qgz``.
        """
        code_digits = str(bgy_geocode)
        subfolder_path = export_folder / code_digits
        packaged_project_file = subfolder_path / f"{code_digits}.qgz"
        _actual_final = getattr(self, "final_raster_path", None)
        raster_base_name = (
            os.path.basename(_actual_final)
            if _actual_final
            else f"{code_digits}_img.tif"
        )

        # --- Clear / create export subfolder ---------------------------------
        if subfolder_path.exists():
            subfolder_abs = os.path.normcase(os.path.abspath(str(subfolder_path)))
            keep_raster_abs = os.path.normcase(
                os.path.abspath(
                    getattr(self, "final_raster_path", str(subfolder_path / raster_base_name))
                )
            )
            project = QgsProject.instance()
            for lyr in list(project.mapLayers().values()):
                try:
                    src = lyr.source() if hasattr(lyr, "source") else ""
                    if not src or not isinstance(lyr, QgsRasterLayer):
                        continue
                    src_abs = os.path.normcase(os.path.abspath(src))
                    if src_abs.startswith(subfolder_abs) and src_abs != keep_raster_abs:
                        project.removeMapLayer(lyr.id())
                except Exception:
                    continue
            try:
                QApplication.processEvents()
            except Exception:
                pass
            for item in subfolder_path.iterdir():
                try:
                    if item.is_file() and (
                        item.name == raster_base_name
                        or item.name.startswith(raster_base_name + ".")
                    ):
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        for _ in range(5):
                            try:
                                item.unlink()
                                break
                            except PermissionError:
                                QApplication.processEvents()
                                time.sleep(0.2)
                except Exception:
                    pass
        subfolder_path.mkdir(parents=True, exist_ok=True)

        self.qfield_preferences.set_value("exportDirectoryProject", str(subfolder_path))
        self.dirsToCopyWidget.save_settings()
        self._ensure_ea_update_not_offline_and_writable()

        # Remove stale generated rasters from previous iterations
        try:
            keep_sources = set()
            if hasattr(self, "temp_raster_path") and self.temp_raster_path:
                keep_sources.add(os.path.normcase(os.path.abspath(self.temp_raster_path)))
            project = QgsProject.instance()
            for lyr in list(project.mapLayers().values()):
                if not isinstance(lyr, QgsRasterLayer):
                    continue
                src = lyr.source() or ""
                if not src:
                    continue
                src_abs = os.path.normcase(os.path.abspath(src))
                src_name = os.path.basename(src_abs).lower()
                lyr_name = (lyr.name() or "").lower()
                if (
                    src_name.endswith("_img.tif")
                    or src_name.endswith("_img.mbtiles")
                    or lyr_name.endswith("_img")
                ) and src_abs not in keep_sources:
                    project.removeMapLayer(lyr.id())
        except Exception:
            pass

        # Ensure the current clipped raster is registered in the project
        try:
            desired_raster_name = f"{code_digits}_img"
            current_raster_path = None
            if hasattr(self, "temp_raster_path") and self.temp_raster_path and os.path.exists(self.temp_raster_path):
                current_raster_path = self.temp_raster_path
            elif hasattr(self, "final_raster_path") and self.final_raster_path and os.path.exists(self.final_raster_path):
                current_raster_path = self.final_raster_path

            if current_raster_path:
                # Check if already in project
                found = False
                for lyr in QgsProject.instance().mapLayers().values():
                    try:
                        if isinstance(lyr, QgsRasterLayer):
                            src = lyr.source() or ""
                            src_norm = os.path.normcase(os.path.abspath(src))
                            curr_norm = os.path.normcase(os.path.abspath(current_raster_path))
                            if src_norm == curr_norm:
                                found = True
                                break
                    except Exception:
                        pass

                if not found:
                    # Register the raster layer at the BOTTOM of the layer tree
                    rlayer = QgsRasterLayer(current_raster_path, desired_raster_name)
                    if rlayer.isValid():
                        QgsProject.instance().addMapLayer(rlayer, False)
                        _root_tree = QgsProject.instance().layerTreeRoot()
                        _root_tree.addChildNode(QgsLayerTreeLayer(rlayer))
        except Exception as e:
            QgsApplication.instance().messageLog().logMessage(
                f"Could not register raster layer: {e}", "qfieldmod", Qgis.Warning,
            )

        # --- Build OfflineConverter with full parameters (matching EA export) ---
        area_of_interest_crs = QgsProject.instance().crs().authid()
        area_of_interest = None
        try:
            _bgy_lid = self.layer_dropdown.currentData()
            _bgy_lyr = QgsProject.instance().mapLayer(_bgy_lid) if _bgy_lid else None
            if isinstance(_bgy_lyr, QgsVectorLayer) and _bgy_lyr.isValid():
                _bgy_geoms = [
                    f.geometry()
                    for f in _bgy_lyr.getFeatures()
                    if f.geometry() and not f.geometry().isNull()
                ]
                if _bgy_geoms:
                    _bgy_union = QgsGeometry.unaryUnion(_bgy_geoms)
                    if _bgy_union and not _bgy_union.isEmpty():
                        _bbox = _bgy_union.boundingBox()
                        _buf = _bbox.width() * 0.1 or 0.001
                        _bgy_union = _bgy_union.buffer(_buf, 5)
                        area_of_interest = _bgy_union.asWkt()
        except Exception as _aoi_err:
            QgsApplication.instance().messageLog().logMessage(
                f"Could not compute BGY area_of_interest from layer: {_aoi_err}",
                "qfieldmod", Qgis.Warning,
            )
        if not area_of_interest:
            area_of_interest = self.iface.mapCanvas().extent().asWktPolygon()

        def _build_converter(offliner_instance):
            converter = OfflineConverter(
                self.project,
                packaged_project_file,
                area_of_interest,
                area_of_interest_crs,
                self.qfield_preferences.value("attachmentDirs"),
                offliner_instance,
                ExportType.Cable,
                dirs_to_copy={},
                export_title=code_digits,
            )
            converter.total_progress_updated.connect(self.update_total)
            converter.task_progress_updated.connect(self.update_task)
            converter.warning.connect(
                lambda title, body: QMessageBox.warning(None, title, body)
            )
            return converter

        def _rewrite_raster_source():
            _actual = getattr(self, "final_raster_path", None)
            raster_filename = os.path.basename(_actual) if _actual else f"{code_digits}_img.tif"
            target_ds = raster_filename

            # Also handle additional raster (_img_new)
            _add_actual = getattr(self, '_additional_raster_final_path', None)
            add_raster_filename = os.path.basename(_add_actual) if _add_actual else None

            project_path = str(packaged_project_file)
            if not os.path.exists(project_path):
                return
            if project_path.lower().endswith(".qgz"):
                tmp_qgz = project_path + ".tmp"
                with zipfile.ZipFile(project_path, "r") as zin:
                    names = zin.namelist()
                    qgs_name = next((n for n in names if n.lower().endswith(".qgs")), None)
                    if not qgs_name:
                        return
                    qgs_text = zin.read(qgs_name).decode("utf-8", errors="ignore")
                    try:
                        root_xml = ET.fromstring(qgs_text)
                        changed = False
                        for ml in root_xml.findall(".//maplayer"):
                            name_el = ml.find("layername")
                            ds_el = ml.find("datasource")
                            layer_name = (name_el.text or "").lower() if name_el is not None else ""
                            ds_text = (ds_el.text or "") if ds_el is not None else ""
                            if ds_el is not None:
                                # Satellite raster (_img)
                                if (
                                    raster_filename.lower() in ds_text.lower()
                                    or (layer_name.endswith("_img") and not layer_name.endswith("_img_new"))
                                ):
                                    ds_el.text = target_ds
                                    changed = True
                                # Additional raster (_img_new)
                                elif add_raster_filename and (
                                    add_raster_filename.lower() in ds_text.lower()
                                    or layer_name.endswith("_img_new")
                                ):
                                    ds_el.text = add_raster_filename
                                    changed = True
                        
                        # Move raster layer to the bottom of the layer tree
                        layer_tree = root_xml.find("layer-tree-group")
                        if layer_tree is not None:
                            raster_node = None
                            raster_parent = None
                            # Search recursively: the raster might be inside a nested group
                            def _find_raster_node(parent):
                                for child in list(parent):
                                    if child.tag == "layer-tree-layer":
                                        name = child.get("name", "")
                                        if name == f"{code_digits}_img" or name.endswith("_img"):
                                            return parent, child
                                    elif child.tag == "layer-tree-group":
                                        result = _find_raster_node(child)
                                        if result:
                                            return result
                                return None
                            
                            result = _find_raster_node(layer_tree)
                            if result:
                                raster_parent, raster_node = result
                                raster_parent.remove(raster_node)
                                # Always append to the ROOT layer-tree-group (bottom)
                                layer_tree.append(raster_node)
                                changed = True
                                
                        rewritten = ET.tostring(root_xml, encoding="unicode") if changed else qgs_text
                    except Exception:
                        rewritten = re.sub(
                            rf"(<datasource>)[^<]*{re.escape(raster_filename)}(</datasource>)",
                            rf"\1{target_ds}\2",
                            qgs_text,
                            flags=re.IGNORECASE,
                        )
                    with zipfile.ZipFile(tmp_qgz, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                        for name in names:
                            zout.writestr(
                                name,
                                rewritten.encode("utf-8") if name == qgs_name else zin.read(name),
                            )
                os.replace(tmp_qgz, project_path)
            else:
                with open(project_path, "r", encoding="utf-8", errors="ignore") as f:
                    qgs_text = f.read()
                rewritten = re.sub(
                    rf"(<datasource>)[^<]*{re.escape(raster_filename)}(</datasource>)",
                    rf"\1{target_ds}\2",
                    qgs_text,
                    flags=re.IGNORECASE,
                )
                with open(project_path, "w", encoding="utf-8") as f:
                    f.write(rewritten)

        # Build layer rename map: original display name -> {bgy_geocode}_suffix
        _role_suffixes = {
            "_bgy_combo_ea":       "_ea",
            "_bgy_combo_bldg":     "_bldgpts",
            "_bgy_combo_landmark": "_landmark",
            "_bgy_combo_block":    "_block",
            "_bgy_combo_road":     "_road",
            "_bgy_combo_river":    "_river",
            "_bgy_combo_bridge":   "_bridge",
            "_bgy_combo_railroad": "_railroad",
        }
        layer_rename_map = {}
        for _attr, _suffix in _role_suffixes.items():
            _lyr = self._get_bgy_assigned_layer(_attr)
            if _lyr and _lyr.isValid():
                layer_rename_map[self._normalized_layer_name(_lyr.name())] = f"{code_digits}{_suffix}"
        # Also rename the BGY layer itself
        _bgy_lid = self.layer_dropdown.currentData()
        if _bgy_lid:
            _bgy_lyr = QgsProject.instance().mapLayer(_bgy_lid)
            if _bgy_lyr and _bgy_lyr.isValid():
                layer_rename_map[self._normalized_layer_name(_bgy_lyr.name())] = f"{code_digits}_bgy"

        # Rename the Form 2 Geotagging template layer (pppmmbbbeeeeee) to the BGY geocode
        _FORM2_TEMPLATE_NAME = "pppmmbbbeeeeee"
        for _lyr in QgsProject.instance().mapLayers().values():
            if self._normalized_layer_name(_lyr.name()) == _FORM2_TEMPLATE_NAME:
                layer_rename_map[_FORM2_TEMPLATE_NAME] = code_digits
                break

        # Add all layers containing placeholders to layer_rename_map (handles copy layers, custom layers, etc.)
        for _lyr in QgsProject.instance().mapLayers().values():
            orig_name = self._normalized_layer_name(_lyr.name())
            new_name = orig_name
            for placeholder in ("pppmmbbbeeeeee", "pppmmbbb", "pppmm"):
                if placeholder in orig_name.lower():
                    idx = orig_name.lower().find(placeholder)
                    part_after = orig_name[idx + len(placeholder):]
                    
                    # Apply suffix transformation rule
                    if "_" in part_after:
                        u_idx = part_after.find("_")
                        suffix = part_after[u_idx:]
                    else:
                        suffix = ""
                    
                    new_name = orig_name[:idx] + code_digits + suffix
                    break
            if new_name != orig_name:
                layer_rename_map[orig_name] = new_name

        bldg_new_name = f"{code_digits}_bldgpts"

        def _rename_and_regroup_layers():
            project_path = str(packaged_project_file)
            if not layer_rename_map or not os.path.exists(project_path):
                return

            def _patch(text):
                try:
                    root = ET.fromstring(text)
                    changed = False
                    for ml in root.findall(".//maplayer"):
                        for tag in ("layername", "title"):
                            el = ml.find(tag)
                            if el is not None and el.text and el.text.strip() in layer_rename_map:
                                el.text = layer_rename_map[el.text.strip()]
                                changed = True
                    for ltl in root.findall(".//layer-tree-layer"):
                        old = ltl.get("name", "")
                        if old in layer_rename_map:
                            ltl.set("name", layer_rename_map[old])
                            changed = True
                    if changed:
                        return ET.tostring(root, encoding="unicode")
                    return text
                except Exception as e:
                    QgsApplication.instance().messageLog().logMessage(
                        f"BGY layer rename patch error: {e}", "qfieldmod", Qgis.Warning,
                    )
                    return text

            if project_path.lower().endswith(".qgz"):
                tmp = project_path + ".renametmp"
                with zipfile.ZipFile(project_path, "r") as zin:
                    names = zin.namelist()
                    qgs_name = next((n for n in names if n.lower().endswith(".qgs")), None)
                    if not qgs_name:
                        return
                    qgs_text = zin.read(qgs_name).decode("utf-8", errors="ignore")
                    patched = _patch(qgs_text)
                    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                        for name in names:
                            zout.writestr(
                                name,
                                patched.encode("utf-8") if name == qgs_name else zin.read(name),
                            )
                os.replace(tmp, project_path)
            else:
                with open(project_path, "r", encoding="utf-8", errors="ignore") as f:
                    qgs_text = f.read()
                patched = _patch(qgs_text)
                with open(project_path, "w", encoding="utf-8") as f:
                    f.write(patched)



        def _convert():
            try:
                self._offline_convertor.convert()
            except shutil.SameFileError as e:
                src = getattr(e, "filename", None)
                dst = getattr(e, "filename2", None)
                if src and dst:
                    src_abs = os.path.normcase(os.path.abspath(src))
                    dst_abs = os.path.normcase(os.path.abspath(dst))
                    if src_abs != dst_abs:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        if os.path.exists(dst):
                            os.remove(dst)
                        shutil.copy2(src, dst)
                        return
                QgsApplication.instance().messageLog().logMessage(
                    f"Ignoring same-path copy during BGY export: {e}", "qfieldmod", Qgis.Info,
                )

        self._offline_convertor = _build_converter(self.offliner)
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            _root = QgsProject.instance().layerTreeRoot()
            _sat_visible = self._raster_satellite_visible.isChecked() if hasattr(self, '_raster_satellite_visible') else True
            for _rl in list(QgsProject.instance().mapLayers().values()):
                if isinstance(_rl, QgsRasterLayer) and self._normalized_layer_name(_rl.name()).lower().endswith("_img"):
                    _rn = _root.findLayer(_rl.id())
                    if _rn:
                        _rn.setItemVisibilityChecked(_sat_visible)

            # Load the additional raster (.mbtiles) into the project so
            # OfflineConverter includes it with full rendering XML.
            _add_temp = getattr(self, '_additional_raster_temp_path', None)
            _add_visible = self._raster_additional_visible.isChecked() if hasattr(self, '_raster_additional_visible') else True
            if _add_temp and os.path.exists(_add_temp):
                _add_rl = QgsRasterLayer(_add_temp, f"{code_digits}_img_new")
                if _add_rl.isValid():
                    QgsProject.instance().addMapLayer(_add_rl, False)
                    _add_node = _root.addLayer(_add_rl)
                    if _add_node:
                        _add_node.setItemVisibilityChecked(_add_visible)

            try:
                self.zoom_to_layer(code_digits)
            except Exception:
                pass
            try:
                _convert()
            except IndexError as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"BGY export retry after IndexError: {e}", "qfieldmod", Qgis.Warning,
                )
                fallback_offliner = QgisCoreOffliner(offline_editing=False)
                fallback_offliner.warning.connect(self.show_warning)
                self._offline_convertor = _build_converter(fallback_offliner)
                _convert()

            # Move temp raster into the export subfolder
            if hasattr(self, "temp_raster_path") and hasattr(self, "final_raster_path"):
                if self.temp_raster_path and os.path.exists(self.temp_raster_path):
                    try:
                        os.makedirs(os.path.dirname(self.final_raster_path), exist_ok=True)
                        if os.path.exists(self.final_raster_path):
                            os.remove(self.final_raster_path)
                        shutil.move(self.temp_raster_path, self.final_raster_path)
                        for lyr in QgsProject.instance().mapLayers().values():
                            if isinstance(lyr, QgsRasterLayer) and lyr.source() == self.final_raster_path:
                                QgsProject.instance().removeMapLayer(lyr.id())
                        clipped_raster_layer = QgsRasterLayer(
                            self.final_raster_path, f"{code_digits}_img"
                        )
                        if clipped_raster_layer.isValid():
                            QgsProject.instance().addMapLayer(clipped_raster_layer, False)
                            # Add to the bottom of the layer tree (as the last layer) so it doesn't cover vectors
                            QgsProject.instance().layerTreeRoot().addChildNode(QgsLayerTreeLayer(clipped_raster_layer))
                            self.clipped_raster_layer = clipped_raster_layer
                    except Exception as e:
                        QgsApplication.instance().messageLog().logMessage(
                            f"Could not move raster for BGY {code_digits}: {e}",
                            "qfieldmod", Qgis.Warning,
                        )

            # Move additional raster into the export subfolder
            _add_temp = getattr(self, '_additional_raster_temp_path', None)
            _add_final = getattr(self, '_additional_raster_final_path', None)
            if _add_temp and _add_final and os.path.exists(_add_temp):
                try:
                    os.makedirs(os.path.dirname(_add_final), exist_ok=True)
                    if os.path.exists(_add_final):
                        os.remove(_add_final)
                    shutil.move(_add_temp, _add_final)
                    # Remove old _img_new layers from project, then re-add
                    for lyr in list(QgsProject.instance().mapLayers().values()):
                        if isinstance(lyr, QgsRasterLayer) and self._normalized_layer_name(lyr.name()).lower().endswith("_img_new"):
                            QgsProject.instance().removeMapLayer(lyr.id())
                    _new_rl = QgsRasterLayer(_add_final, f"{code_digits}_img_new")
                    if _new_rl.isValid():
                        QgsProject.instance().addMapLayer(_new_rl, False)
                        QgsProject.instance().layerTreeRoot().addLayer(_new_rl)
                except Exception as e:
                    QgsApplication.instance().messageLog().logMessage(
                        f"Could not move additional raster for BGY {code_digits}: {e}",
                        "qfieldmod", Qgis.Warning,
                    )

            try:
                _rewrite_raster_source()
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not rewrite raster source for BGY {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )
            try:
                _rename_and_regroup_layers()
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not rename/regroup layers for BGY {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )
            try:
                self._export_individual_layers(code_digits, subfolder_path, packaged_project_file)
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not export individual layers for BGY {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )

            # Copy additional raster (.mbtiles) and patch visibility for both rasters
            try:
                self._copy_additional_raster_and_patch_visibility(code_digits, subfolder_path, packaged_project_file)
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Could not copy additional raster for BGY {code_digits}: {e}",
                    "qfieldmod", Qgis.Warning,
                )

            self.do_post_offline_convert_action(True)
        except PackagingCanceledError:
            return
        except Exception as e:
            QgsApplication.instance().messageLog().logMessage(
                f"BGY packaging failed for {code_digits}: {e}\n{traceback.format_exc()}",
                "qfieldmod", Qgis.Critical,
            )
            raise
        finally:
            QApplication.restoreOverrideCursor()
            self._offline_convertor = None

    def save_raster_path(self, file_path):
        """Save the file path when the user selects a raster."""
        if file_path:
            self.saved_raster_file = file_path  # Save the selected raster file path
            print(f"Raster file selected: {self.saved_raster_file}")


    def run_raster(self):
        """Clips a raster layer using a buffered mask vector layer and builds pyramids on the result."""
        
        selected_geocode = self.geocode_dropdown.currentText()
        raster_file = self._raster_satellite_dir.filePath()

        # Resolve selected layer safely (we store layer ids in the combo)
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
        # fallback: resolve by displayed name
        if selected_layer is None:
            selected_name = self.layer_dropdown.currentText()
            if selected_name:
                for lyr in QgsProject.instance().mapLayers().values():
                    try:
                        if lyr.name() == selected_name:
                            selected_layer = lyr
                            break
                    except Exception:
                        continue

        # Get the export folder path and temporary location for raster
        export_folder = Path(self.manualDir.text())
        # decide prefix length by output level
        prefix = selected_geocode.split('_', 1)[0] if selected_geocode else ''
        if self.output_dropdown.currentText() == self.tr("EA Level"):
            code_digits = prefix[:14]
        else:
            code_digits = prefix[:8]
        barangay_name = selected_geocode.split('_', 1)[1] if '_' in selected_geocode else ""
        subfolder_name = f"{code_digits}_{barangay_name}"
        subfolder_path = str(export_folder / subfolder_name)
        
        # Save raster to temp folder to avoid OfflineConverter conflicts
        temp_raster_dir = tempfile.gettempdir()
        
        # Store these for later use in package_project
        self.temp_raster_dir = temp_raster_dir
        self.temp_raster_path = os.path.join(temp_raster_dir, f"{code_digits}_img.tif")
        self.final_raster_path = os.path.join(str(subfolder_path), f"{code_digits}_img.tif")

        # Create and configure worker (pass code_digits so worker doesn't need to recompute)
        self.worker = RasterClipWorker(raster_file, selected_layer, selected_geocode, temp_raster_dir, subfolder_path, code_digits)
        
        # Connect signals
        self.worker.progress.connect(self.update_total)
        self.worker.task_progress.connect(self.update_task)
        self.worker.finished.connect(self.raster_process_complete)

        # Disable UI elements
        self.run_clip.setEnabled(False)
        self.button_box.setEnabled(False)

        # Start worker
        self.worker.start()

    def raster_process_complete(self, success, result):
        """Handle completion of raster processing."""
        if success:
            output_raster = result
            export_folder = Path(self.manualDir.text())
            selected_code = self.geocode_dropdown.currentText()
            prefix = selected_code.split('_', 1)[0] if selected_code else ''
            if self.output_dropdown.currentText() == self.tr("EA Level"):
                code_digits = prefix[:14]
            else:
                code_digits = prefix[:8]
            barangay_name = selected_code.split('_', 1)[1] if '_' in selected_code else ""
            subfolder_name = f"{code_digits}_{barangay_name}"
            subfolder_path = str(export_folder / subfolder_name)
            final_raster_path = os.path.join(subfolder_path, f"{code_digits}_img.tif")
            os.makedirs(subfolder_path, exist_ok=True)

            # Keep raster in temp until packaging. This avoids SameFileError
            # inside OfflineConverter and allows full export/copy of all files.
            self.temp_raster_path = output_raster
            self.final_raster_path = final_raster_path
            active_raster_path = output_raster

            # Remove old generated image rasters so only the current one is exported.
            for lyr in QgsProject.instance().mapLayers().values():
                if not isinstance(lyr, QgsRasterLayer):
                    continue
                src = lyr.source() or ""
                src_abs = os.path.normcase(os.path.abspath(src)) if src else ""
                src_name = os.path.basename(src_abs).lower() if src_abs else ""
                lyr_name = (lyr.name() or "").lower()
                is_generated_img = src_name.endswith('_img.tif') or lyr_name.endswith('_img') or lyr_name.endswith('_img.tif')
                if is_generated_img:
                    QgsProject.instance().removeMapLayer(lyr.id())

            # Add the raster to the project so user can see it in layers panel
            clipped_raster_layer = QgsRasterLayer(active_raster_path, f"{code_digits}_img")
            if clipped_raster_layer.isValid():
                QgsProject.instance().addMapLayer(clipped_raster_layer, False)
                root = QgsProject.instance().layerTreeRoot()
                root.addLayer(clipped_raster_layer)
                self.clipped_raster_layer = clipped_raster_layer
                iface.messageBar().pushInfo("Process Complete", f"Raster clipped and staged for export:\n{active_raster_path}")
            else:
                iface.messageBar().pushInfo("Layer Error", "Failed to load clipped raster layer.")
        else:
            iface.messageBar().pushInfo("Error", f"Process failed: {result}")

        # Re-enable UI elements
        self.run_clip.setEnabled(True)
        self.button_box.setEnabled(True)
  
    def reset_filter(self):
        self.zoom_to_mun()
        # put group selector back to Base Layers
        idx = self.group_dropdown.findText('Base Layers')
        if idx != -1:
            self.group_dropdown.setCurrentIndex(idx)
        # Get the currently selected geocode from the geocode_dropdown widget
        selected_geocode = self.geocode_dropdown.currentText()
        # choose default prefix according to output level
        level = self.output_dropdown.currentText().lower()
        if "ea" in level:
            default_prefix = 'pppmmbbb'
        else:
            # fallback to barangay-level default
            default_prefix = 'pppmm'

        print("Resetting filters...")  # Debugging line
        self.layer_dropdown.clear()      # Clear the layer dropdown
        self.geocode_dropdown.clear()    # Clear the geocode dropdown
        self.infoLocalizedLayersLabel.setVisible(False)  # Hide any info labels
        self.infoLocalizedPresentLabel.setVisible(False)
        self.infoGroupBox.setVisible(False)

        # Get the current QGIS project instance
        project = QgsProject.instance()

        # Reset filters on vector layers matching specific suffixes (excluding raster images)
        target_suffixes = (
            '_bldg_point', '_bldgpts', '_bldg_points', '_bridge', '_railroad',
            '_landmark', '_ea_update', '_bgy', '_ea', '_block', '_road', '_river'
        )
        for layer in list(project.mapLayers().values()):
            layer_name = self._normalized_layer_name(layer.name())
            if layer_name.endswith(target_suffixes):
                if layer.isValid():
                    print("Resetting filter on layer:", layer.name())
                    layer.setSubsetString("")  # Clear the subset string to reset the filter
                    # Restore default layer tree label/count behavior on reset.
                    try:
                        tree_layer = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
                        if tree_layer is not None:
                            tree_layer.setCustomProperty("showFeatureCount", False)
                            tree_layer.setName(layer_name)
                    except Exception:
                        pass

        # Remove raster layers whose names end with '_img' and delete the corresponding files
        for layer in list(project.mapLayers().values()):
            if isinstance(layer, QgsRasterLayer) and layer.name().endswith('_img'):
                file_path = layer.source()
                print("Removing raster layer:", layer.name(), "with file:", file_path)
                project.removeMapLayer(layer.id())
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print("Deleted file:", file_path)
                    except Exception as e:
                        print("Error deleting file:", file_path, e)
                else:
                    print("File does not exist:", file_path)

        # Modify this section to check for layers inside the "Base Layers"  group
        root = QgsProject.instance().layerTreeRoot()
        for group in root.children():
            if isinstance(group, QgsLayerTreeGroup):
                if group.name() == 'Base Layers':  
                    for layer in group.findLayers():
                        layer_name = self._normalized_layer_name(layer.layer().name()).lower()
                        # determine base prefix (up to underscore) then trim by output level
                        base_pref = selected_geocode.split('_', 1)[0] if selected_geocode else default_prefix
                        if self.output_dropdown.currentText() == self.tr("EA Level"):
                            prefix = base_pref[:14]
                        else:
                            prefix = base_pref[:8]
                        if layer_name.endswith('_bgy'):
                            new_name = f"{prefix}_bgy"
                        elif layer_name.endswith('_ea_update'):
                            new_name = f"{prefix}_ea_update"
                        elif layer_name.endswith('_ea'):
                            new_name = f"{prefix}_ea"
                        elif layer_name.endswith('_block'):
                            new_name = f"{prefix}_block"
                        elif layer_name.endswith('_bldgpts'):
                            new_name = f"{prefix}_bldgpts"
                        elif layer_name.endswith('_bldg_point'):
                            new_name = f"{prefix}_bldgpts"
                        elif layer_name.endswith('_bldg_points'):
                            new_name = f"{prefix}_bldgpts"
                        elif layer_name.endswith('_landmark'):
                            new_name = f"{prefix}_landmark"
                        elif layer_name.endswith('_road'):
                            new_name = f"{prefix}_road"
                        elif layer_name.endswith('_river'):
                            new_name = f"{prefix}_river"
                        elif layer_name.endswith('_bridge'):
                            new_name = f"{prefix}_bridge"
                        elif layer_name.endswith('_railroad'):
                            new_name = f"{prefix}_railroad"
                        else:
                            continue
                        layer.layer().setName(new_name)
                        print(f"Renamed base layer to '{new_name}'")

                elif group.name() == 'For Verification':  
                    for layer in group.findLayers():
                        layer_name = self._normalized_layer_name(layer.layer().name()).lower()
                        # determine prefix according to output level
                        base_pref = selected_geocode.split('_', 1)[0] if selected_geocode else default_prefix
                        if self.output_dropdown.currentText() == self.tr("EA Level"):
                            prefix = base_pref[:14]
                        else:
                            prefix = base_pref[:8]
                        if layer_name.endswith('_ea_update'):
                            new_name = f"{prefix}_ea_update"
                        else:
                            continue
                        layer.layer().setName(new_name)
                        print(f"Renamed verification layer to '{new_name}'")

        # switch back to Base Layers group, then rename layers so they reflect the default prefix
        idx = self.group_dropdown.findText('Base Layers')
        if idx != -1:
            self.group_dropdown.setCurrentIndex(idx)
        self.rename_layers_by_output_level()

        # Optionally, repopulate the dropdowns if needed
        self.populate_layers_dropdown()
        self.populate_geocode_dropdown()
        self.populate_citymun_dropdown()
        self.populate_bgy_dropdown()

        # Disable the Save button and other UI elements as needed
        self.button_box.button(QDialogButtonBox.Save).setEnabled(False)
        self.run_clip.setEnabled(False)
        self.zoom_to_mun()
        project = QgsProject.instance()
        # Set project title using selected geocode or default prefix, trimmed by output level
        base_pref = selected_geocode.split('_', 1)[0] if selected_geocode else default_prefix
        if self.output_dropdown.currentText() == self.tr("EA Level"):
            title_prefix = base_pref[:14]
        else:
            title_prefix = base_pref[:8]
        project.setTitle(title_prefix)
        project.write()

   
    def rename_layers_by_output_level(self):
        """Rename existing project layers according to the current
        geocode and output level formatting (8 vs 14 digits).

        When no geocode is selected (e.g. immediately after a reset) fall
        back to a generic default prefix so the layer tree still reflects
        the chosen output level.
        """
        selected_geocode = self.geocode_dropdown.currentText()
        if selected_geocode:
            base_pref = selected_geocode.split('_', 1)[0]
        else:
            # no geocode, choose default prefix per level
            if self.output_dropdown.currentText() == self.tr("EA Level"):
                base_pref = 'pppmmbbb'
            else:
                base_pref = 'pppmm'

        if self.output_dropdown.currentText() == self.tr("EA Level"):
            prefix = base_pref[:14]
        else:
            prefix = base_pref[:8]

        for layer in QgsProject.instance().mapLayers().values():
            name = self._normalized_layer_name(layer.name()).lower()
            for sfx in (
                '_bgy', '_ea', '_ea_update', '_block',
                '_bldgpts', '_bldg_point', '_bldg_points',
                '_landmark', '_road', '_river', '_bridge', '_railroad'
            ):
                if name.endswith(sfx):
                    layer.setName(prefix + sfx)
                    break

    def filter_layers(self, layers, selected_geocode):
        # determine prefix length from user choice; use only the part before the underscore
        if selected_geocode:
            base_pref = selected_geocode.split('_', 1)[0]
            if self.output_dropdown.currentText() == self.tr("EA Level"):
                prefix = base_pref[:14]
            else:
                prefix = base_pref[:8]
        else:
            prefix = ''

        # Loop through each layer in the dictionary and apply relevant filters
        updated_layers = []
        for layer_key, layer in layers.items():
            if layer is not None and layer.isValid():
                # Apply filters based on suffixes
                layer_name = self._normalized_layer_name(layer.name())
                if layer_name.endswith('_bgy'):
                    layer.setSubsetString(f"geocode LIKE '{prefix}%'")
                    updated_layers.append(layer)
                elif layer_name.endswith('_ea'):
                    layer.setSubsetString(f"geocode LIKE '{prefix}%'")
                    updated_layers.append(layer)
                elif layer_name.endswith('_bldgpts'):
                    layer.setSubsetString(f"geocode LIKE '{prefix}%'")
                    updated_layers.append(layer)
                elif layer_name.endswith('_bldg_point'):
                    layer.setSubsetString(f"geocode LIKE '{prefix}%'")
                    updated_layers.append(layer)
                elif layer_name.endswith('_bldg_points'):
                    layer.setSubsetString(f"geocode LIKE '{prefix}%'")
                    updated_layers.append(layer)
                elif layer_name.endswith('_landmark'):
                    layer.setSubsetString(f"geocode LIKE '{prefix}%'")
                    updated_layers.append(layer)
                elif layer_name.endswith('_ea_update'):
                    # Keep _ea_update unfiltered.
                    layer.setSubsetString("")
                    updated_layers.append(layer)
                elif layer_name.endswith('_block'):
                    layer.setSubsetString(f"geocode LIKE '{prefix}%'")
                    updated_layers.append(layer)
                elif layer_name.endswith(('_road', '_river', '_bridge', '_railroad')):
                    # No subset filter — show all features for these reference layers
                    updated_layers.append(layer)
                else:
                    QMessageBox.warning(None, "Unsupported Layer", f"Layer '{layer.name()}' does not match any known suffixes.")
            else:
                QMessageBox.warning(None, "Layer Invalid", f"The layer '{layer_key}' is not valid or does not exist.")

        # Force layer tree and map canvas refresh so filtered features are shown immediately.
        for lyr in updated_layers:
            try:
                tree_layer = QgsProject.instance().layerTreeRoot().findLayer(lyr.id())
                if tree_layer is not None:
                    tree_layer.setCustomProperty("showFeatureCount", False)
                    tree_layer.setName(self._normalized_layer_name(lyr.name()))
                lyr.triggerRepaint()
                self.iface.layerTreeView().refreshLayerSymbology(lyr.id())
            except Exception:
                pass

        try:
            self.iface.mapCanvas().refreshAllLayers()
            self.iface.mapCanvas().refresh()
        except Exception:
            pass

        # Call select_by_location after filtering layers
        self.select_by_location()
        self.button_box.button(QDialogButtonBox.Save).setEnabled(True)
        self.run_clip.setEnabled(True)
        self.zoom_to_layer(prefix)
        self.auto_snap_layer()
        self.update_value_relations()
        self.set_read_only_for_selected_layers()

    
    def zoom_to_layer(self, geocode):
        is_ea_level = "ea level" in self.output_dropdown.currentText().lower()
        preferred_suffix = "_ea" if is_ea_level else "_bgy"
        fallback_suffix  = "_bgy" if is_ea_level else None
        target_layer = None

        root = QgsProject.instance().layerTreeRoot()
        base_group = root.findGroup("Base Layers")

        for suffix in ([preferred_suffix] + ([fallback_suffix] if fallback_suffix else [])):
            # First search inside Base Layers group to avoid picking up
            # unfiltered layers from other groups (e.g. For Verification).
            if base_group:
                for tree_layer in base_group.findLayers():
                    lyr = tree_layer.layer()
                    if lyr and isinstance(lyr, QgsVectorLayer):
                        lname = self._normalized_layer_name(lyr.name()).lower()
                        if lname.endswith(suffix):
                            target_layer = lyr
                            break
            # Fallback: search all layers if not found in Base Layers.
            if not target_layer:
                for lyr in QgsProject.instance().mapLayers().values():
                    if isinstance(lyr, QgsVectorLayer):
                        lname = self._normalized_layer_name(lyr.name()).lower()
                        if lname.endswith(suffix):
                            target_layer = lyr
                            break
            if target_layer:
                break

        if target_layer:
            target_layer.selectAll()
            iface.mapCanvas().zoomToSelected(target_layer)
            target_layer.removeSelection()
            print(f"Zoomed to filtered layer: {target_layer.name()} with geocode = {geocode}")
        else:
            print(f"No layer found ending with '{preferred_suffix}'")

    def zoom_to_mun(self):
        # Retrieve all layers in the project
        layers = QgsProject.instance().mapLayers().values()

        # Iterate through each layer
        for layer in layers:
            # Check if the layer's name ends with 'river'
            if self._normalized_layer_name(layer.name()).endswith('_river'):
                # Get the extent of the layer
                extent = layer.extent()
                # Set the map canvas to the layer's extent
                iface.mapCanvas().setExtent(extent)
                iface.mapCanvas().refresh()
                print(f"Zoomed to the extent of the layer: {layer.name()}")
                break
        else:
            print("No layer found with a name ending with 'river'.")


    def load_layer_groups(self):
        # Populate the group dropdown with layer groups in the project
        self.group_dropdown.clear()
        root = QgsProject.instance().layerTreeRoot()
        groups = [child for child in root.children() if isinstance(child, QgsLayerTreeGroup)]
        for group in groups:
            # Store only the group name (string) as combo data to avoid holding
            # references to C++ objects that may become invalid after project
            # modifications. Resolve the group fresh when needed.
            self.group_dropdown.addItem(group.name(), group.name())
        
        # If 'Base Layers' exists choose it by default
        idx = self.group_dropdown.findText('Base Layers')
        if idx != -1:
            self.group_dropdown.setCurrentIndex(idx)
        
        # Validate group selection after loading groups
        self.validate_group_selection()





    def populate_layers_dropdown(self):
        """Populate the layer dropdown based on the selected group or output level."""
        self.layer_dropdown.blockSignals(True)
        try:
            # For EA Level: scan all project layers for _ea suffix (no group filter needed).
            if self.output_dropdown.currentText() == self.tr("EA Level"):
                self.layer_dropdown.clear()
                for layer_obj in sorted(
                    QgsProject.instance().mapLayers().values(),
                    key=lambda l: l.name(),
                ):
                    if self._normalized_layer_name(layer_obj.name()).lower().endswith("_ea"):
                        self.layer_dropdown.addItem(layer_obj.name(), layer_obj.id())
                if self.layer_dropdown.count() > 0:
                    self.layer_dropdown.setCurrentIndex(0)
                    self.button_box.button(QDialogButtonBox.Save).setEnabled(True)
                return

            # For BGY Level: scan all project layers for _bgy suffix (no group filter needed).
            if self.output_dropdown.currentText() == self.tr("Barangay Level"):
                self.layer_dropdown.clear()
                for layer_obj in sorted(
                    QgsProject.instance().mapLayers().values(),
                    key=lambda l: l.name(),
                ):
                    if self._normalized_layer_name(layer_obj.name()).lower().endswith("_bgy"):
                        self.layer_dropdown.addItem(layer_obj.name(), layer_obj.id())
                if self.layer_dropdown.count() > 0:
                    self.layer_dropdown.setCurrentIndex(0)
                return

            # --- Barangay Level: filter by group (existing behaviour) ---
            # Show/hide the Barangay filter row based on output level.
            is_ea = "ea" in self.output_dropdown.currentText().lower()
            self.label_9.setVisible(is_ea)
            self.bgy_dropdown.setVisible(is_ea)

            selected_group_name = self.group_dropdown.currentData()
            if not selected_group_name:
                return

            # Resolve the group from the project layer tree by name each time to
            # ensure we have a valid, up-to-date `QgsLayerTreeGroup` instance.
            root = QgsProject.instance().layerTreeRoot()
            selected_group = root.findGroup(selected_group_name)
            if selected_group is None:
                return

            # Populate the layer dropdown with layers in the selected group,
            # filtering by the current output level suffix.
            self.layer_dropdown.clear()
            layers = [layer for layer in selected_group.findLayers()]
            desired = '_ea' if self.output_dropdown.currentText() == self.tr('EA Level') else '_bgy'
            matching = []

            for layer in layers:
                layer_obj = layer.layer()
                name = layer_obj.name() if layer_obj is not None else layer.name()
                if not name.lower().endswith(desired):
                    continue
                layer_id = layer_obj.id() if layer_obj is not None else None
                self.layer_dropdown.addItem(name, layer_id)
                matching.append(layer)

            # auto-select first matching layer
            if matching:
                first_layer = matching[0].layer()
                first_name = first_layer.name() if first_layer is not None else matching[0].name()
                idx = self.layer_dropdown.findText(first_name)
                if idx != -1:
                    self.layer_dropdown.setCurrentIndex(idx)

            # Clear geocode dropdown
            self.geocode_dropdown.clear()
        finally:
            self.layer_dropdown.blockSignals(False)
            self.layer_dropdown.currentIndexChanged.emit(self.layer_dropdown.currentIndex())

    def populate_geocode_dropdown(self):
        """Populate the geocode dropdown based on the selected layer."""
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)

        # fallback by name
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if lyr.name() == sel_name:
                        selected_layer = lyr
                        break
                except Exception:
                    continue

        self.geocode_dropdown.clear()
        # only pull geocodes when the selected layer matches the desired suffix
        desired = '_ea' if self.output_dropdown.currentText() == self.tr('EA Level') else '_bgy'
        if selected_layer and selected_layer.name().endswith(desired):
            geocode_index = selected_layer.fields().indexOf('geocode')
            geocode_name_index = selected_layer.fields().indexOf('barangay')
            if geocode_name_index == -1:
                geocode_name_index = selected_layer.fields().indexOf('Barangay')

            if geocode_index != -1 and geocode_name_index != -1:
                formatted_values = [
                    f"{feature.attributes()[geocode_index]}_{feature.attributes()[geocode_name_index]}"
                    for feature in selected_layer.getFeatures()
                ]
                self.geocode_dropdown.addItems(sorted(formatted_values))
                print(f"Geocode and names for layer: {selected_layer.name()}")
            else:
                missing_fields = []
                if geocode_index == -1:
                    missing_fields.append('geocode')
                if geocode_name_index == -1:
                    missing_fields.append('barangay or Barangay')
                print(f"Missing field(s) {', '.join(missing_fields)} in layer: {selected_layer.name()}")
                QMessageBox.warning(self, "Missing Fields", f"Missing field(s): {', '.join(missing_fields)} in layer: {selected_layer.name()}")
                
    def populate_citymun_dropdown(self):
        """Populate the citymun dropdown based on the selected layer."""
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)

        # fallback by name
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if lyr.name() == sel_name:
                        selected_layer = lyr
                        break
                except Exception:
                    continue

        self.citymun_dropdown.blockSignals(True)
        try:
            self.citymun_dropdown.clear()
            self.citymun_dropdown.addItem("All")

            desired = '_ea' if self.output_dropdown.currentText() == self.tr('EA Level') else '_bgy'
            if selected_layer and selected_layer.name().endswith(desired):
                geocode_index = selected_layer.fields().indexOf('geocode')
                geocode_name_index = selected_layer.fields().indexOf('city_mun')
                if geocode_name_index == -1:
                    geocode_name_index = selected_layer.fields().indexOf('City_mun')

                if geocode_index != -1 and geocode_name_index != -1:
                    formatted_values = set(
                        f"{str(feature.attributes()[geocode_index])[:5]}_{feature.attributes()[geocode_name_index]}"
                        for feature in selected_layer.getFeatures()
                    )
                    self.citymun_dropdown.addItems(sorted(formatted_values))
                    print(f"City/Municipality dropdown unique values: {formatted_values}")
                else:
                    missing_fields = []
                    if geocode_index == -1:
                        missing_fields.append('geocode')
                    if geocode_name_index == -1:
                        missing_fields.append('city_mun or City_mun')
                    print(f"Missing field(s) {', '.join(missing_fields)} in layer: {selected_layer.name()}")
                    QMessageBox.warning(self, "Missing Fields", f"Missing field(s): {', '.join(missing_fields)} in layer: {selected_layer.name()}")
        finally:
            self.citymun_dropdown.blockSignals(False)

    def populate_bgy_dropdown(self):
        """Populate the barangay dropdown based on the selected layer.

        Values use the first eight digits of the geocode followed by the
        barangay name, separated by an underscore.  An "All" entry is added
        at the top to allow de‑selection.
        """
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)

        # fallback by name
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                try:
                    if lyr.name() == sel_name:
                        selected_layer = lyr
                        break
                except Exception:
                    continue

        self.bgy_dropdown.blockSignals(True)
        try:
            self.bgy_dropdown.clear()
            self.bgy_dropdown.addItem("All")

            # Keep Barangay Level fixed to the default "All" entry only.
            if self.output_dropdown.currentText() != self.tr('EA Level'):
                self.bgy_dropdown.setCurrentIndex(0)
                return

            # EA level uses the _ea layer and follows the existing population logic.
            desired = '_ea' if self.output_dropdown.currentText() == self.tr('EA Level') else '_bgy'

            # determine citymun filter prefix (first 5 digits) if one is selected
            citymun_text = self.citymun_dropdown.currentText()
            citymun_prefix = None
            if citymun_text and citymun_text.lower() != "all":
                citymun_prefix = citymun_text.split('_')[0]

            if selected_layer and selected_layer.name().endswith(desired):
                geocode_index = selected_layer.fields().indexOf('geocode')
                barangay_index = selected_layer.fields().indexOf('barangay')
                if barangay_index == -1:
                    barangay_index = selected_layer.fields().indexOf('Barangay')

                if geocode_index != -1 and barangay_index != -1:
                    formatted_values = set()
                    for feature in selected_layer.getFeatures():
                        code = str(feature.attributes()[geocode_index])
                        if citymun_prefix and code[:5] != citymun_prefix:
                            continue
                        formatted_values.add(f"{code[:8]}_{feature.attributes()[barangay_index]}")

                    self.bgy_dropdown.addItems(sorted(formatted_values))
                    print(f"Barangay dropdown unique values: {formatted_values}")
                else:
                    missing_fields = []
                    if geocode_index == -1:
                        missing_fields.append('geocode')
                    if barangay_index == -1:
                        missing_fields.append('barangay or Barangay')
                    print(f"Missing field(s) {', '.join(missing_fields)} in layer: {selected_layer.name()}")
                    QMessageBox.warning(self, "Missing Fields", f"Missing field(s): {', '.join(missing_fields)} in layer: {selected_layer.name()}")
        finally:
            self.bgy_dropdown.blockSignals(False)

        # no additional default handling needed; Barangay Level returns above.

    def filter_geocode_by_bgy(self):
        """Filter the geocode dropdown when a barangay value is selected."""
        selected_bgy = self.bgy_dropdown.currentText()
        if selected_bgy.lower() == "all":
            self.populate_geocode_dropdown()
            return
        bgy_prefix = selected_bgy.split('_')[0]

        # resolve the layer exactly like the other filter method
        selected_layer = None
        selected_data = self.layer_dropdown.currentData()
        if isinstance(selected_data, str):
            selected_layer = QgsProject.instance().mapLayer(selected_data)
        if selected_layer is None and self.layer_dropdown.currentText():
            sel_name = self.layer_dropdown.currentText()
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == sel_name:
                    selected_layer = lyr
                    break

        self.geocode_dropdown.clear()
        desired = '_ea' if self.output_dropdown.currentText() == self.tr('EA Level') else '_bgy'
        if selected_layer and selected_layer.name().endswith(desired):
            geocode_index = selected_layer.fields().indexOf('geocode')
            geocode_name_index = selected_layer.fields().indexOf('barangay')
            if geocode_name_index == -1:
                geocode_name_index = selected_layer.fields().indexOf('Barangay')
            if geocode_index != -1 and geocode_name_index != -1:
                filtered_values = [
                    f"{feature.attributes()[geocode_index]}_{feature.attributes()[geocode_name_index]}"
                    for feature in selected_layer.getFeatures()
                    if str(feature.attributes()[geocode_index])[:8] == bgy_prefix
                ]
                self.geocode_dropdown.addItems(sorted(filtered_values))
                print(f"Filtered geocode values for barangay {selected_bgy}: {filtered_values}")
            else:
                print("Missing geocode or barangay field.")

    def select_by_location(self):
        # Get the layer named with the suffix '_road', '_block', '_river'
        input_layers = [
            layer for layer in QgsProject.instance().mapLayers().values()
            if layer.name().endswith(('_road', '_block', '_river'))
        ]
        
        # Get all layers that end with '_bgy'
        overlay_layers = [
            layer for layer in QgsProject.instance().mapLayers().values()
            if layer.name().endswith('_bgy')
        ]
        
        # Check if input_layers and overlay_layers are found
        if not input_layers:
            print("No input layers found with '_road', '_block', or '_river' suffix.")
            return
        
        if not overlay_layers:
            print("No overlay layers found with '_bgy' suffix.")
            return
        
        # Define the list of predicates
        predicates = [0]  # 'intersects', 'within', 'crosses', 'equals'

        # Run Select by Location for each input layer and each overlay layer with each predicate
        for input_layer in input_layers:
            for overlay_layer in overlay_layers:
                for predicate in predicates:
                    result = processing.run("qgis:selectbylocation", {
                        'INPUT': input_layer,
                        'PREDICATE': predicate,
                        'INTERSECT': overlay_layer,
                        'METHOD': 0  # 0 for "Create new selection"
                    })
                    print(f"Selection done for {input_layer.name()} with predicate: {predicate} and overlay: {overlay_layer.name()}")
                    
                    # Check if any features were selected
                    selected_count = input_layer.selectedFeatureCount()
                    print(f"Number of selected features in {input_layer.name()}: {selected_count}")
        
        print("Selection by location completed.")

    def reload_plugin(self, plugin_name):
        """Reload a specified QGIS plugin."""
        # Try to initially load the selected plugin if not loaded yet
        if plugin_name not in utils.plugins:
            try:
                utils.loadPlugin(plugin_name)
                utils.startPlugin(plugin_name)
                utils.updateAvailablePlugins()
                print(f"Plugin '{plugin_name}' loaded successfully.")
            except Exception as e:
                print(f"Failed to load plugin '{plugin_name}': {str(e)}")
                return
        
        try:
            # Unload the plugin
            utils.unloadPlugin(plugin_name)

            # Remove submodules left by qgis.utils.unloadPlugin
            for key in list(sys.modules.keys()):
                if plugin_name in key:
                    if hasattr(sys.modules[key], 'qCleanupResources'):
                        sys.modules[key].qCleanupResources()
                    del sys.modules[key]

            # Reload the plugin
            utils.loadPlugin(plugin_name)
            utils.startPlugin(plugin_name)
            print(f"Plugin '{plugin_name}' reloaded successfully.")

        except Exception as e:
            print(f"Failed to reload plugin '{plugin_name}': {str(e)}")
            QMessageBox.critical(None, "Error", f"Failed to reload plugin '{plugin_name}': {str(e)}")



    def auto_snap_layer(self):
        """
        Enables snapping for layers with names ending in _SF, _GP, or _bldgpts.
        Snapping is configured to snap to both vertices and segments with a tolerance of 10 pixels.
        """
        project = QgsProject.instance()
        snapping_config = project.snappingConfig()

        # Loop through all layers in the project
        for layer in project.mapLayers().values():
            layer_name = layer.name()
            if layer_name.endswith('_SF') or layer_name.endswith('_GP') or layer_name.endswith('_bldgpts'):
                # Create individual snapping settings for this layer
                settings = QgsSnappingConfig.IndividualLayerSettings()
                settings.setEnabled(True)
                # Set snapping mode to snap to both vertices and segments
                settings.setType(QgsSnappingConfig.Vertex)
                # Set the tolerance to 10 pixels (adjust if needed)
                settings.setTolerance(10)
                settings.setUnits(QgsTolerance.Pixels)

                # Apply these settings to the layer
                snapping_config.setIndividualLayerSettings(layer, settings)

        # Enable snapping for the project and update the project configuration
        snapping_config.setEnabled(True)
        project.setSnappingConfig(snapping_config)
        project.write()
        print("Auto-snapping configured for layers ending with _SF, _GP or _bldgpts.")

   
    def update_value_relations(self):
        """
        Automatically update ValueRelation widget configurations for all layers
        whose names end with '_SF' or '_GP' based on predefined mappings.
        """
        # Predefined mappings for source layers ending with _SF and _GP respectively
        mapping_sf = {
            "UPDT_1NAME": "SF_RefData",
            "UPDT_ADDRE": "SF_RefData",
            "UPDT_INSTY": "SF_RefData",
            "UPDT_SECTO": "SF_RefData",
            "UPDT_SPECT": "SF_RefData",
            "SPECTYPE": "2024 POPCEN-CBMS SF Specific Types",
            "OTHER_USE": "2024 POPCEN-CBMS SF Specific Types"
        }
        
        mapping_gp = {
            "UPDT_1NAME": "GP_RefData",
            "UPDT_ADDRE": "GP_RefData",
            "UPDT_SECTO": "GP_RefData",
            "UPDT_STATU": "GP_RefData",
            "UPDT_SDATE": "GP_RefData",
            "UPDT_CDATE": "GP_RefData",
            "UPDT_INSTY": "GP_RefData",
            "UPDT_FUND": "GP_RefData",
            "TYPE_OCCU": "BCCB", 
            "GP_INSFUND": "2024 POPCEN-CBMS GP Fund",
            "UPDT_BUDGE": "GP_RefData"
        }
        
        # Get all project layers
        project_layers = list(QgsProject.instance().mapLayers().values())
        
        # Create a lookup dictionary for project layers by name
        layers_by_name = {layer.name(): layer for layer in project_layers}
        
        processed_layer_count = 0

        # Iterate over each layer in the project
        for source_layer in project_layers:
            layer_name = source_layer.name()
            if not (layer_name.endswith("_SF") or layer_name.endswith("_GP")):
                continue  # Skip layers not ending with _SF or _GP
            
            # Select the appropriate mapping based on the layer's suffix
            current_mapping = mapping_sf if layer_name.endswith("_SF") else mapping_gp
            
            print(f"Processing layer: {layer_name}")
            
            # Iterate through the fields of the source layer
            for field in source_layer.fields():
                field_index = source_layer.fields().lookupField(field.name())
                widget_setup = source_layer.editorWidgetSetup(field_index)
                
                # Process only fields with a ValueRelation widget
                if widget_setup.type() != "ValueRelation":
                    continue
                
                # Update only if the field name exists in the mapping
                if field.name() in current_mapping:
                    desired_target_name = current_mapping[field.name()]
                    if desired_target_name in layers_by_name:
                        new_target_layer_id = layers_by_name[desired_target_name].id()
                    else:
                        print(f"  - Desired target layer '{desired_target_name}' not found in project for field '{field.name()}'.")
                        continue
                else:
                    continue
                
                # Update the widget configuration with the new target layer ID
                config = widget_setup.config()
                config["Layer"] = new_target_layer_id
                source_layer.setEditorWidgetSetup(field_index, widget_setup.__class__(widget_setup.type(), config))
                print(f"  - Updated field '{field.name()}' to target layer '{desired_target_name}'.")
            
            processed_layer_count += 1

        if processed_layer_count == 0:
            print("No layers with names ending with '_SF' or '_GP' were found.")
        else:
            print("All applicable ValueRelation fields updated for processed layers.")


    def set_read_only_for_selected_layers(self):
        project = QgsProject.instance()
        
        # Define target suffixes
        target_suffixes = ("_bldgpts", "_landmark", "_bgy", "_ea", "_block", "_road", "_river", "_river")

        modified = False  # Track if any changes were made

        for layer in project.mapLayers().values():
            if layer.name().endswith(target_suffixes) and isinstance(layer, QgsVectorLayer):  
                # Check if read-only is already set in project metadata
                key = f"ReadOnlyLayers/{layer.id()}"
                read_only_status, found = project.readEntry("ReadOnlyLayers", layer.id(), "False")

                if not found or read_only_status != "True":  # Only update if not already set
                    layer.setReadOnly(True)  # Set the layer as read-only
                    project.writeEntry("ReadOnlyLayers", layer.id(), "True")  # Store status
                    modified = True  # Mark project as modified
                    print(f"Set read-only: {layer.name()}")

        # Save project only if changes were made
        if modified:
            project.write()
            print("Project saved with updated read-only settings.")
        else:
            print("No changes needed. Read-only settings already applied.")

    def show_help(self):
        from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton
        from qgis.PyQt.QtCore import QByteArray, QBuffer, QIODevice

        def widget_to_base64(widget):
            if not widget: return ""
            pixmap = widget.grab()
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.WriteOnly)
            pixmap.save(buffer, "PNG")
            return byte_array.toBase64().data().decode("utf-8")

        try:
            group_name_img = f'<img src="data:image/png;base64,{widget_to_base64(self.group_name_input)}" style="vertical-align: middle; max-height: 28px;">'
            add_group_img = f'<img src="data:image/png;base64,{widget_to_base64(self.add_group_btn)}" style="vertical-align: middle;">'
            delete_group_img = f'<img src="data:image/png;base64,{widget_to_base64(self.delete_group_btn)}" style="vertical-align: middle;">'
            up_img = f'<img src="data:image/png;base64,{widget_to_base64(self.move_up_btn)}" style="vertical-align: middle;">'
            down_img = f'<img src="data:image/png;base64,{widget_to_base64(self.move_down_btn)}" style="vertical-align: middle;">'
            save_preset_img = f'<img src="data:image/png;base64,{widget_to_base64(self.save_preset_btn)}" style="vertical-align: middle;">'
            load_preset_img = f'<img src="data:image/png;base64,{widget_to_base64(self.load_preset_btn)}" style="vertical-align: middle;">'
            delete_preset_img = f'<img src="data:image/png;base64,{widget_to_base64(self.delete_preset_btn)}" style="vertical-align: middle;">'
            apply_groups_img = f'<img src="data:image/png;base64,{widget_to_base64(self.apply_groups_btn)}" style="vertical-align: middle;">'
            import_qml_img = f'<img src="data:image/png;base64,{widget_to_base64(self.import_qml_btn)}" style="vertical-align: middle;">'

            if hasattr(self, 'run_button') and self.run_button:
                filter_img = f'<img src="data:image/png;base64,{widget_to_base64(self.run_button)}" style="vertical-align: middle;">'
            else:
                filter_img = "<b>[Filter]</b>"
            if hasattr(self, 'run_clip') and self.run_clip:
                clip_img = f'<img src="data:image/png;base64,{widget_to_base64(self.run_clip)}" style="vertical-align: middle;">'
            else:
                clip_img = "<b>[Clip]</b>"
            if hasattr(self, 'next_geocode') and self.next_geocode:
                next_img = f'<img src="data:image/png;base64,{widget_to_base64(self.next_geocode)}" style="vertical-align: middle;">'
            else:
                next_img = "<b>[Next Geocode]</b>"
            if hasattr(self, 'run_batch') and self.run_batch:
                batch_img = f'<img src="data:image/png;base64,{widget_to_base64(self.run_batch)}" style="vertical-align: middle;">'
            else:
                batch_img = "<b>[Batch]</b>" 
            export_img = f'<img src="data:image/png;base64,{widget_to_base64(self.button_box.button(QDialogButtonBox.Save))}" style="vertical-align: middle;">'
            
            reset_btn = self.button_box.button(QDialogButtonBox.Reset)
            if reset_btn:
                reset_img = f'<img src="data:image/png;base64,{widget_to_base64(reset_btn)}" style="vertical-align: middle;">'
            else:
                reset_img = "<b>[Reset]</b>"
            dir_btn_img = f'<img src="data:image/png;base64,{widget_to_base64(self.manualDir_btn)}" style="vertical-align: middle;">'
            tree_select_all_img = f'<img src="data:image/png;base64,{widget_to_base64(self._filter_tree_select_all_btn)}" style="vertical-align: middle;">'
            tree_deselect_all_img = f'<img src="data:image/png;base64,{widget_to_base64(self._filter_tree_deselect_all_btn)}" style="vertical-align: middle;">'
            export_all_img = f'<img src="data:image/png;base64,{widget_to_base64(self._export_select_all_btn)}" style="vertical-align: middle;">'
            export_none_img = f'<img src="data:image/png;base64,{widget_to_base64(self._export_deselect_all_btn)}" style="vertical-align: middle;">'
        except Exception:
            group_name_img = "<b>[Enter group name...]</b>"
            add_group_img = "<b>[+]</b>"
            delete_group_img = "<b>[-]</b>"
            up_img = "<b>[↑]</b>"
            down_img = "<b>[↓]</b>"
            save_preset_img = "<b>[Save Preset]</b>"
            load_preset_img = "<b>[Load Preset]</b>"
            delete_preset_img = "<b>[Delete Preset]</b>"
            apply_groups_img = "<b>[Apply Groups]</b>"
            import_qml_img = "<b>[Import QML]</b>"
            filter_img = "<b>[Filter]</b>"
            clip_img = "<b>[Clip]</b>"
            next_img = "<b>[Next Geocode]</b>"
            batch_img = "<b>[Batch]</b>"
            export_img = "<b>[Export]</b>"
            reset_img = "<b>[Reset]</b>"
            dir_btn_img = "<b>[...]</b>"
            tree_select_all_img = "<b>[Select All]</b>"
            tree_deselect_all_img = "<b>[Deselect All]</b>"
            export_all_img = "<b>[All]</b>"
            export_none_img = "<b>[None]</b>"

        help_text = f"""
        <html>
        <head>
        <style>
            body {{ font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; margin: 10px; }}
            h2 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
            h3 {{ color: #2980b9; margin-top: 20px; }}
            ul {{ margin-top: 5px; margin-bottom: 15px; padding-left: 20px; }}
            li {{ margin-bottom: 15px; }}
            b {{ color: #333; }}
        </style>
        </head>
        <body>
        <h2>QField Package Tool - Help & Overview</h2>
        
        <p>This tool allows you to prepare and package your QGIS project for offline use in QField. Here is an overview of all the features and buttons available in the dialog.</p>

        <h3>1. Prepare Project Layers</h3>
        <p>This tab allows you to organize your layers into specific groups and style them automatically using QML files. Grouping layers here will rearrange them directly in your QGIS project's Layers panel.</p>
        <ul>
        <li>{group_name_img} <br><b>Enter Group Name:</b> Type the name of the new group you want to create here.</li>
        <li>{add_group_img} <b>Add Group:</b> Creates a new group using the text from the input field.</li>
        <li>{delete_group_img} <b>Delete Group:</b> Removes the currently selected group or layer from the hierarchy.</li>
        <li>{up_img} <b>Move Up:</b> Moves the selected item up in the list hierarchy.</li>
        <li>{down_img} <b>Move Down:</b> Moves the selected item down in the list hierarchy.</li>
        <li>{save_preset_img} <br><b>Save Preset:</b> Saves your current group structure and QML assignments so you can reuse them later.</li>
        <li>{load_preset_img} <br><b>Load Preset:</b> Loads a previously saved layer grouping preset.</li>
        <li>{delete_preset_img} <br><b>Delete Preset:</b> Deletes a saved layer grouping preset.</li>
        <li>{apply_groups_img} <br><b>Apply Groups to QGIS Layers Panel:</b> Updates your actual QGIS project with the groups and layer structure defined in the table above.</li>
        <li>{import_qml_img} <br><b>Import QML Style(s)...:</b> Opens a file browser to import custom QML styles which can be assigned to your layers in the table.</li>
        </ul>

        <h3>2. Export Options - Process Settings</h3>
        <ul>
        <li><b>Export Directory:</b> Destination folder for your packaged QField projects. Click the {dir_btn_img} button to browse.</li>
        <li><b>Select Output Level:</b> Choose to export for an EA (Enumeration Area) or for an entire Barangay.</li>
        <li><b>Select City/Municipality and Barangay:</b> A geographical filter tree to target specific regions.</li>
        <li>{tree_select_all_img} {tree_deselect_all_img} <br><b>Select All / Deselect All:</b> Quickly check or uncheck all items in the City/Municipality tree above.</li>
        <li><b>Select BGYs/EAs to Process:</b> The resulting list of specific areas that will be packaged.</li>
        </ul>
        
        <h3>3. Export Options - Layer Assignment & Raster Configuration</h3>
        <ul>
        <li><b>Layer Assignment:</b> Use the dropdowns to assign specific QGIS layers (like Barangay, Building points, Roads) to be included in your package.</li>
        <li><b>Visible Checkboxes:</b> Check the 'Visible' box next to any vector or raster layer to ensure it is turned on by default when the project is opened in QField.</li>
        <li><b>Satellite Image Directory:</b> Select the folder containing your primary background satellite imagery. Click the {dir_btn_img} button to browse.</li>
        <li><b>Additional Raster Directory:</b> Select a folder containing additional MBTiles basemaps to overlay in QField.</li>
        <li><b>Convert satellite to MBTiles:</b> If enabled, converts the primary satellite image into the highly optimized MBTiles format.</li>
        </ul>
        
        <h3>4. Export Options - Individual Export Layers & Progress</h3>
        <ul>
        <li><b>Individual Export Layers:</b> Select specific layers from the table to export as separate files (e.g. .geojson or .shp) alongside the packaged project.</li>
        <li>{export_all_img} {export_none_img} <br><b>Export All / None:</b> Quickly check or uncheck all layers in the individual export table.</li>
        <li><b>Progress:</b> Shows the 'Total' packaging progress and the current 'Layer' progress.</li>
        <li>{export_img} <br><b>Export:</b> Exports the currently active geographical area into a QField project folder.</li>
        </ul>
        </body>
        </html>
        """
        
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Help - Features Overview"))
        dlg.resize(650, 700)
        
        layout = QVBoxLayout(dlg)
        
        browser = QTextBrowser(dlg)
        browser.setOpenExternalLinks(True)
        browser.setHtml(help_text)
        layout.addWidget(browser)
        
        btn = QPushButton(self.tr("Close"), dlg)
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        
        dlg.exec_()


class RasterClipWorker(QThread):
    """Worker thread for raster clipping operations."""
    progress = pyqtSignal(int, int, str)  # total progress
    task_progress = pyqtSignal(int, int)  # task progress
    finished = pyqtSignal(bool, str)  # success status and message

    def __init__(self, raster_file, selected_layer, selected_geocode, parent_export_path, subfolder_path, code_digits):
        super().__init__()
        self.raster_file = raster_file
        self.selected_layer = selected_layer
        self.selected_geocode = selected_geocode
        self.parent_export_path = parent_export_path
        self.subfolder_path = subfolder_path
        self.code_digits = code_digits
        
    def run(self):
        try:
            self.progress.emit(0, 100, "Starting process...")
            self.task_progress.emit(0, 100)

            if not self.selected_geocode:
                self.finished.emit(False, "No geocode selected.")
                return

            self.progress.emit(10, 100, "Geocode selected")
            self.task_progress.emit(10, 100)

            if not self.raster_file or not os.path.exists(self.raster_file):
                self.finished.emit(False, "Invalid raster file selected.")
                return

            self.progress.emit(20, 100, "Raster file verified")
            self.task_progress.emit(20, 100)

            raster_layer = QgsRasterLayer(self.raster_file, os.path.basename(self.raster_file))
            if not raster_layer.isValid():
                self.finished.emit(False, "Failed to load the raster layer.")
                return

            self.progress.emit(30, 100, "Raster layer loaded")
            self.task_progress.emit(30, 100)

            if not isinstance(self.selected_layer, QgsVectorLayer):
                self.finished.emit(False, "Invalid vector layer.")
                return

            self.progress.emit(40, 100, "Vector layer validated")
            self.task_progress.emit(40, 100)

            # Create buffer
            buffer_distance = 0.001000
            buffer_output = os.path.join(os.path.dirname(self.raster_file), "buffered_mask.gpkg")
            buffer_params = {
                'INPUT': self.selected_layer,
                'DISTANCE': buffer_distance,
                'SEGMENTS': 5,
                'DISSOLVE': True,
                'OUTPUT': buffer_output
            }
            
            try:
                buffer_result = processing.run("native:buffer", buffer_params)
                if not buffer_result or not os.path.exists(buffer_output):
                    self.finished.emit(False, "Failed to create buffer.")
                    return
            except Exception as e:
                self.finished.emit(False, f"Buffer creation error: {str(e)}")
                return

            self.progress.emit(60, 100, "Buffer created")
            self.task_progress.emit(60, 100)

            # Ensure parent output directory exists
            try:
                os.makedirs(self.parent_export_path, exist_ok=True)
            except Exception as e:
                self.finished.emit(False, f"Failed to create output directory: {str(e)}")
                return

            output_raster = os.path.join(self.parent_export_path, f"{self.code_digits}_img.tif")

            # Clip raster
            try:
                params = {
                    'INPUT': raster_layer,
                    'MASK': buffer_output,
                    'OUTPUT': output_raster
                }

                result = processing.run("gdal:cliprasterbymasklayer", params)
                
                if result and os.path.exists(output_raster):
                    # Build pyramids
                    self.progress.emit(90, 100, "Building pyramids...")
                    self.task_progress.emit(90, 100)
                    
                    pyramid_params = {
                        'INPUT': output_raster,
                        'FORMAT': 0,
                        'LEVELS': '8,16,32,64,128',
                        'RESAMPLING': None
                    }
                    processing.run("gdal:overviews", pyramid_params)
                    
                    self.progress.emit(100, 100, "Process complete")
                    self.task_progress.emit(100, 100)
                    self.finished.emit(True, output_raster)
                else:
                    self.finished.emit(False, "Failed to clip raster. Output file not created.")
            except Exception as e:
                self.finished.emit(False, f"Clip error: {str(e)}")

        except Exception as e:
            self.finished.emit(False, str(e))









