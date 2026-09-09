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
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers



class mv_2027_hp_4b_longitude__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4b_longitude__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4b_longitude__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points whose Longitude and Latitude values are far from their geometry. \n \n"
            "The geometry of each geotagged point must match its Longitude and Latitude column values.\n"
        )

    def initAlgorithm(self, config: Optional[Dict[str, Any]] = None):
        
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_DATA,
                "INPUT_DATA (.csv file)",
                behavior=QgsProcessingParameterFile.File,
                extension="csv",
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
                "mv_2027_hp_4b_longitude__invalid",
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
        json_data = gmdhelpers.load_cbms_csv(self, parameters, self.INPUT_DATA, context, feedback)

        layer_with_dist = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": geojson_data,
                "FIELD_NAME": "distance_m",
                "FIELD_TYPE": 0,  # Float / Double
                "FIELD_LENGTH": 0,
                "FIELD_PRECISION": 0,
                "FORMULA":  'CASE \r\n WHEN "sf_longitude" IS NOT NULL AND "sf_latitude" IS NOT NULL \r\n AND is_empty_or_null($geometry) = False\r\n THEN distance(\r\n transform(make_point("sf_longitude", "sf_latitude"), \'EPSG:4326\', \'EPSG:3857\'),\r\n transform($geometry, \'EPSG:4326\', \'EPSG:3857\')\r\n )\r\n ELSE NULL\r\nEND',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 2. Extract features where distance > 30m or missing position data
        filtered_layer = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": layer_with_dist,
                "EXPRESSION": '"distance_m" IS NULL OR "distance_m" > 50.0',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        final_output = gmdhelpers.select_mv(
            filtered_layer,
            ["sf_longitude", "sf_latitude", "distance_m"],
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
