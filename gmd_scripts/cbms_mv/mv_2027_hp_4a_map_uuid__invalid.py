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
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers



class mv_2027_hp_4a_map_uuid__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4a_map_uuid__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4a_map_uuid__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with map_uuid not in the reference layer. \n \n"
            "The map_uuid should be retained unless the geotagged point is a new building or has a special BSN.\n"
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
                "mv_2027_hp_4a_map_uuid__invalid",
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
        
        base_layer_path = self.parameterAsFile(parameters, self.BASE_LAYER, context)
        ref_bldg_point = None

        if base_layer_path and os.path.exists(base_layer_path):
            bldg_point_sublayer = None
            tmp_layer = QgsVectorLayer(base_layer_path, "tmp_gpkg", "ogr")
            if tmp_layer and tmp_layer.isValid():
                for sub_item in tmp_layer.dataProvider().subLayers():
                    parts = sub_item.split("!!::!!") if "!!::!!" in sub_item else sub_item.split(":")
                    for part in parts:
                        if part.endswith("_bldg_point"):
                            bldg_point_sublayer = part
                            break
                    if bldg_point_sublayer:
                        break

            if bldg_point_sublayer:
                ref_bldg_point = QgsVectorLayer(
                    f"{base_layer_path}|layername={bldg_point_sublayer}",
                    bldg_point_sublayer,
                    "ogr",
                )

        if not ref_bldg_point or not ref_bldg_point.isValid():
            raise QgsProcessingException(
                f"Could not load reference building point layer ending with '_bldg_point' from '{base_layer_path}'"
            )

        regular_bldg = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": geojson_data,
                "EXPRESSION": 'to_int("bsn") > 0 AND to_int("bsn") < 55555',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        joined_layer = processing.run(
            "native:joinattributestable",
            {
                "INPUT": regular_bldg,
                "FIELD": "map_uuid",
                "INPUT_2": ref_bldg_point,
                "FIELD_2": "map_uuid",
                "FIELDS_TO_COPY": ["map_uuid"],
                "METHOD": 1,
                "DISCARD_NONMATCHING": False,
                "PREFIX": "ref_",
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        extracted_joined = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": joined_layer,
                "EXPRESSION": '"ref_map_uuid" IS NULL',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        final_output = gmdhelpers.select_mv(extracted_joined, ["ref_map_uuid", "ref_bsn_geoid"])

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