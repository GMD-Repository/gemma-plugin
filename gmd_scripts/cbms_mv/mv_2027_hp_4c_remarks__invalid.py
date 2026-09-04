import os
import json
import processing
from typing import Any, Optional, Dict, List

from PyQt5.QtCore import QVariant
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
    QgsProcessingParameterFile,
    QgsVectorLayer,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsProviderRegistry,
    QgsDistanceArea,
    QgsPointXY,
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers



class mv_2027_hp_4c_remarks__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4c_remarks__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4c_remarks__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with deletion or review remarks. \n \n"
            "Features with remarks value are flagged for review and/or deletion.\n"
        )

    def initAlgorithm(self, config: Optional[Dict[str, Any]] = None):
        
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_DATA,
                "INPUT_DATA (.json file)",
                behavior=QgsProcessingParameterFile.File,
                extension="json",
                optional=False,
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_LAYER,
                "INPUT_LAYER (.geojson file)",
                behavior=QgsProcessingParameterFile.File,
                extension="geojson",
                optional=False,
            )
        )

        self.addParameter(
            QgsProcessingParameterFile(
                self.BASE_LAYER,
                "BASE_LAYER (.gpkg file)",
                behavior=QgsProcessingParameterFile.File,
                extension="gpkg",
                optional=False,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "mv_2027_hp_4c_remarks__invalid",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

    def processAlgorithm(
        self,
        parameters: Dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> Dict[str, Any]:

        geojson_data = gmdhelpers.load_cbms_geojson(self, parameters, self.INPUT_LAYER, context)
        json_data = gmdhelpers.load_cbms_json(self, parameters, self.INPUT_DATA, context, feedback)

        features = gmdhelpers.filter_geometry_validity(geojson_data, feedback)
        fields = geojson_data.fields()

        # Helper to check if a remark is valid/non-empty (flagged for review/deletion)
        def is_valid_remark(val: Any) -> bool:
            if val is None or val == NULL:
                return False
            if isinstance(val, QVariant) and val.isNull():
                return False
            val_str = str(val).strip()
            return val_str != "" and val_str.lower() not in ("null", "none", "nan", "na", "n/a")

        flagged_features = [
            f for f in features
            if is_valid_remark(f["remarks"])
        ]

        # Add per-remarks count column and sort by remarks
        if flagged_features:
            flagged_features, fields = gmdhelpers.add_count(flagged_features, fields, "remarks")
            flagged_features = gmdhelpers.arrange(flagged_features, "remarks")

        feedback.pushInfo(
            f"Results: Flagged {len(flagged_features)} feature(s) with deletion or review remarks."
        )

        # Build a temporary layer from flagged features to select and organize columns
        temp_layer = QgsVectorLayer(
            f"Point?crs={geojson_data.sourceCrs().authid()}", "temp", "memory"
        )
        temp_layer_dp = temp_layer.dataProvider()
        temp_layer_dp.addAttributes(fields.toList())
        temp_layer.updateFields()
        temp_layer_dp.addFeatures(flagged_features)

        # Select & organize columns using select_mv (standard CBMS fields + remarks + count)
        final_output = gmdhelpers.select_mv(
            temp_layer,
            ["remarks", "n"],
            context=context,
            feedback=feedback,
        )

        return gmdhelpers.export_features_to_sink(
            self,
            parameters,
            self.OUTPUT,
            context,
            final_output.fields(),
            final_output.wkbType(),
            final_output.sourceCrs(),
            final_output.getFeatures(),
            feedback,
        )

    def createInstance(self):
        return self.__class__()
