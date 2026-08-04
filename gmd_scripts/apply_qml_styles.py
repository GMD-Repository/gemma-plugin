import os
import json
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingFeedback,
    QgsProcessingContext,
    QgsProject,
    QgsMapLayer
)


class ApplyQmlStylesAlgorithm(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm for 'Apply Groups & Styles'.
    Reads a JSON layout config file (or raw in-memory JSON string / auto-detects styles for project layers),
    applies QML symbology & labeling definitions, and organizes layers into QGIS Layer Tree groups in exact order.
    Runs on Main Thread (FlagNoThreading) for safety with UI and Layer Tree operations.
    """

    CONFIG_FILE = 'CONFIG_FILE'
    CUSTOM_QML_FOLDER = 'CUSTOM_QML_FOLDER'
    ORGANIZE_GROUPS = 'ORGANIZE_GROUPS'
    OUTPUT_REPORT = 'OUTPUT_REPORT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ApplyQmlStylesAlgorithm()

    def name(self):
        return 'applyqmlstyles'

    def displayName(self):
        return self.tr('Apply Groups & Styles')

    def group(self):
        return self.tr('GMD Toolkits')

    def groupId(self):
        return 'gmdtoolkits'

    def flags(self):
        # Must run on main thread because it modifies map layer styles & layer tree nodes directly
        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'style.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return self.tr(
            "Applies layer styling definitions and organizes Layer Tree groups in exact order.\n\n"
            "1. Select a Layout & Style Config File (.json) OR pass an in-memory JSON string.\n"
            "2. The algorithm automatically locates target project layers, applies QML symbology/labeling styles, "
            "and places layers into Layer Tree Groups preserving exact top-to-bottom order.\n"
            "3. If no JSON config is provided, it automatically scans project layers and applies matching plugin QML styles."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.CONFIG_FILE,
                self.tr('Layout & Style Config File (.json) or JSON Data'),
                behavior=QgsProcessingParameterFile.File,
                fileFilter='JSON files (*.json);;All files (*.*)',
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.CUSTOM_QML_FOLDER,
                self.tr('Custom QML Styles Directory (Optional)'),
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ORGANIZE_GROUPS,
                self.tr('Organize Layers into Layer Tree Groups'),
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters, context: QgsProcessingContext, feedback: QgsProcessingFeedback):
        config_param = self.parameterAsString(parameters, self.CONFIG_FILE, context).strip()
        custom_folder = self.parameterAsString(parameters, self.CUSTOM_QML_FOLDER, context).strip()
        organize_groups = self.parameterAsBoolean(parameters, self.ORGANIZE_GROUPS, context)

        project = context.project() or QgsProject.instance()
        project_layers = list(project.mapLayers().values())

        feedback.pushInfo(self.tr("=== APPLY GROUPS & STYLES ==="))
        feedback.pushInfo(self.tr(f"Active project map layers: {len(project_layers)}"))

        # Import plugin style utilities safely
        available_qmls = []
        try:
            from ..references.package_qfield.utils.style_utils import (
                get_available_qml_display_names,
                auto_detect_qml_for_layer,
                get_qml_file_path
            )
            available_qmls = get_available_qml_display_names()
        except Exception as e:
            feedback.pushInfo(self.tr(f"Notice: Style utils module import status ({e})"))

        # Dual-mode parsing: File path OR raw in-memory JSON string
        json_layout = None
        if config_param:
            if os.path.isfile(config_param):
                try:
                    with open(config_param, 'r', encoding='utf-8') as f:
                        json_layout = json.load(f)
                    feedback.pushInfo(self.tr(f"Loaded Config File: {os.path.basename(config_param)}"))
                except Exception as e:
                    feedback.reportError(self.tr(f"Failed to parse JSON config file: {e}"))
            else:
                try:
                    json_layout = json.loads(config_param)
                    feedback.pushInfo(self.tr("Loaded in-memory JSON layout data."))
                except Exception as e:
                    feedback.reportError(self.tr(f"Failed to parse in-memory JSON string: {e}"))

        # Parse JSON layout config maintaining exact group and layer order
        # Format of ordered_groups: [ {"group": "Group 1", "layers": [{"name": "layer1", "qml": "style.qml"}]} ]
        ordered_groups = []
        json_mapping = {}  # layer_name_lower -> {"qml": ..., "group": ...}

        if json_layout:
            if isinstance(json_layout, list):
                for grp_item in json_layout:
                    grp_name = grp_item.get("group", "")
                    layers_list = []
                    for lyr_item in grp_item.get("layers", []):
                        lname = lyr_item.get("name", "")
                        qml_name = lyr_item.get("qml", "")
                        if lname:
                            json_mapping[lname.lower()] = {"qml": qml_name, "group": grp_name}
                            layers_list.append({"name": lname, "qml": qml_name})
                    if grp_name:
                        ordered_groups.append({"group": grp_name, "layers": layers_list})

            elif isinstance(json_layout, dict):
                for grp_name, lyr_list in json_layout.items():
                    layers_list = []
                    if isinstance(lyr_list, list):
                        for item in lyr_list:
                            if isinstance(item, dict):
                                lname = item.get("name", "")
                                qml_name = item.get("qml", "")
                                if lname:
                                    json_mapping[lname.lower()] = {"qml": qml_name, "group": grp_name}
                                    layers_list.append({"name": lname, "qml": qml_name})
                            elif isinstance(item, str):
                                json_mapping[item.lower()] = {"qml": "", "group": grp_name}
                                layers_list.append({"name": item, "qml": ""})
                    if grp_name:
                        ordered_groups.append({"group": grp_name, "layers": layers_list})

        styled_results = []
        applied_count = 0

        # Step 1: Process and Apply QML Styles to Project Layers
        for idx, layer in enumerate(project_layers):
            if feedback.isCanceled():
                break

            layer_name = layer.name()
            lname_lower = layer_name.lower()
            matched_qml = ""
            status = "No Match"

            # 1. Match from JSON config if provided
            if json_mapping and lname_lower in json_mapping:
                matched_qml = json_mapping[lname_lower].get("qml", "")

            # 2. Match from custom folder if specified
            if not matched_qml and custom_folder and os.path.isdir(custom_folder):
                cand = os.path.join(custom_folder, f"{layer_name}.qml")
                if os.path.isfile(cand):
                    matched_qml = f"{layer_name}.qml"

            # 3. Auto-detect from plugin style repository if no direct match
            if not matched_qml and available_qmls:
                try:
                    from ..references.package_qfield.utils.style_utils import auto_detect_qml_for_layer
                    matched_qml = auto_detect_qml_for_layer(layer_name, available_qmls)
                except Exception:
                    pass

            # Apply QML style safely using PyQGIS Core
            if matched_qml and matched_qml != "(None)":
                qpath = ""
                if custom_folder:
                    cand = os.path.join(custom_folder, matched_qml)
                    if os.path.isfile(cand):
                        qpath = cand

                if not qpath:
                    try:
                        from ..references.package_qfield.utils.style_utils import get_qml_file_path
                        qpath = get_qml_file_path(matched_qml)
                    except Exception:
                        pass

                if qpath and os.path.isfile(qpath):
                    categories = QgsMapLayer.Symbology | QgsMapLayer.Labeling
                    res = layer.loadNamedStyle(qpath, categories)
                    success = bool(res[1]) if isinstance(res, tuple) else bool(res)

                    if success:
                        applied_count += 1
                        status = "Applied Successfully"
                        layer.triggerRepaint()
                    else:
                        status = "Failed to Load QML"
                else:
                    status = f"QML File Not Found ({matched_qml})"

            styled_results.append((layer_name, matched_qml or "(None)", status))
            feedback.pushInfo(self.tr(f"[{idx + 1}/{len(project_layers)}] Layer: '{layer_name}' => QML Style: '{matched_qml or '(None)'}' [{status}]"))

        # Helper: Find map layer by exact or clean name
        def find_layer_by_name(target_name):
            for lyr in project_layers:
                if lyr.name().lower() == target_name.lower():
                    return lyr
            return None

        # Step 2: Organize Layer Tree Groups in Exact Order
        if organize_groups and project:
            try:
                root = project.layerTreeRoot()

                if ordered_groups:
                    # Grouping based on ordered JSON array
                    for grp_idx, grp_info in enumerate(ordered_groups):
                        grp_name = grp_info["group"]
                        grp_node = root.findGroup(grp_name)
                        if not grp_node:
                            grp_node = root.insertGroup(grp_idx, grp_name)
                        else:
                            # Reorder group to correct index if needed
                            curr_children = list(root.children())
                            if grp_node in curr_children and curr_children.index(grp_node) != grp_idx:
                                clone_grp = grp_node.clone()
                                root.insertChildNode(grp_idx, clone_grp)
                                root.removeChildNode(grp_node)
                                grp_node = clone_grp

                        # Move child layers into group in exact order
                        for lyr_idx, lyr_info in enumerate(grp_info.get("layers", [])):
                            lyr_obj = find_layer_by_name(lyr_info["name"])
                            if lyr_obj:
                                node = root.findLayer(lyr_obj.id())
                                if node:
                                    clone = node.clone()
                                    grp_node.insertChildNode(lyr_idx, clone)
                                    if node.parent():
                                        node.parent().removeChildNode(node)
                else:
                    # Grouping based on default keyword rules
                    group_rules = [
                        ("Geotagged Building Point", ["bldgpts", "bldg_point", "building point", "geotagged"]),
                        ("Reference Building Point", ["ref_bldg", "reference"]),
                        ("Base Layers", ["bgy", "brgy", "barangay", "ea", "road", "river", "block"]),
                        ("Verification Layers", ["verify", "verification"])
                    ]

                    for grp_idx, (grp_name, keywords) in enumerate(group_rules):
                        matched_layers = []
                        for layer in project_layers:
                            lname_lower = layer.name().lower()
                            if any(kw in lname_lower for kw in keywords):
                                matched_layers.append(layer)

                        if matched_layers:
                            grp_node = root.findGroup(grp_name)
                            if not grp_node:
                                grp_node = root.insertGroup(grp_idx, grp_name)

                            for lyr_idx, lyr in enumerate(matched_layers):
                                node = root.findLayer(lyr.id())
                                if node:
                                    clone = node.clone()
                                    grp_node.insertChildNode(lyr_idx, clone)
                                    if node.parent():
                                        node.parent().removeChildNode(node)

                feedback.pushInfo(self.tr("Layer Tree groups successfully updated in exact order."))
            except Exception as e:
                feedback.reportError(self.tr(f"Layer Tree grouping notice: {e}"))

        # Final Summary Log
        summary_msg = f"\n=== SUMMARY OF LAYER GROUPS & STYLES ===\n"
        for lname, qml, stat in styled_results:
            summary_msg += f" • Layer: {lname:<35} | QML: {qml:<30} | Status: {stat}\n"
        summary_msg += f"Total: {applied_count}/{len(project_layers)} styles applied successfully."

        feedback.pushInfo(summary_msg)

        return {self.OUTPUT_REPORT: summary_msg}
