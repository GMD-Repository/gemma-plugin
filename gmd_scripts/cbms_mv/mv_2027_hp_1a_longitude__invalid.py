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


class mv_2027_hp_1a_longitude__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self):
        return "mv_2027_hp_1a_longitude__invalid"

    def displayName(self):
        return "mv_2027_hp_1a_longitude__invalid"

    def group(self):
        return "2027 CBMS"

    def groupId(self):
        return "cbms_mv"

    def shortHelpString(self):
        return (
            "List of datafiles and geotagged points with the same coordinates but different map_uuid.\n \n"
            "Datafiles and geotagged points with the same coordinates should have the same map_uuid.\n"
        )

    def initAlgorithm(self, config=None):

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
                "mv_2027_hp_1a_longitude__invalid",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        geojson_data = gmdhelpers.load_cbms_geojson(self, parameters, self.INPUT_LAYER, context)
        json_data = gmdhelpers.load_cbms_json(self, parameters, self.INPUT_DATA, context, feedback)

        # 1. Add rounded coordinate join key (coord_key) to geojson_data using QGIS Field Calculator
        geojson_with_key = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": geojson_data,
                "FIELD_NAME": "coord_key",
                "FIELD_TYPE": 2,  # String
                "FIELD_LENGTH": 100,
                "FORMULA": 'to_string(round($x, 7)) + \'_\' + to_string(round($y, 7))',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 2. Add rounded coordinate join key (coord_key) to json_data table using QGIS Field Calculator (x_current, y_current)
        json_with_key = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": json_data,
                "FIELD_NAME": "coord_key",
                "FIELD_TYPE": 2,  # String
                "FIELD_LENGTH": 100,
                "FORMULA": 'to_string(round(to_real("x_current"), 7)) + \'_\' + to_string(round(to_real("y_current"), 7))',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 3. Join feature attributes using QGIS native Join Attributes Table on coord_key
        joined_layer = processing.run(
            "native:joinattributestable",
            {
                "INPUT": json_with_key,
                "FIELD": "coord_key",
                "INPUT_2": geojson_with_key,
                "FIELD_2": "coord_key",
                "FIELDS_TO_COPY": [],
                "METHOD": 1,
                "DISCARD_NONMATCHING": False,
                "PREFIX": "sf_",
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 4. Extract mismatched features where geotagged map_uuid != reference JSON map_uuid
        mismatched_layer = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": joined_layer,
                "EXPRESSION": '"map_uuid" != "sf_map_uuid"',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 5. Select & organize output columns using select_mv
        final_output = gmdhelpers.select_mv(
            mismatched_layer,
            ["x_current", "y_current", "sf_map_uuid", "sf_longitude", "sf_latitude"],
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