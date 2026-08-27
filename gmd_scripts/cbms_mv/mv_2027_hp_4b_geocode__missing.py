import os
import json
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
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsVectorLayer,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsProject,
)
# pyrefly: ignore [missing-import]
from PyQt5.QtGui import QIcon
from .. import gmdhelpers


class mv_2027_hp_4b_geocode__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self):
        return "mv_2027_hp_4b_geocode__missing"

    def displayName(self):
        return "mv_2027_hp_4b_geocode__missing"

    def group(self):
        return "2027 CBMS"

    def groupId(self):
        return "cbms_mv"

    def shortHelpString(self):
        return (
            "List of geotagged points with NULL Geocodes. \n \n"
            "Every geotagged point should not have NULL values in the Geocode column.\n"
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
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "mv_2027_hp_4b_geocode__missing",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ERRORS,
                "Error Summary (remarks count)",
                QgsProcessing.TypeVector,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.OPEN_FOR_EDITING,
                "Open output layer in edit mode after running",
                defaultValue=False,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        geojson_data = gmdhelpers.load_cbms_geojson(self, parameters, self.INPUT_LAYER, context)
        json_data = gmdhelpers.load_cbms_json(self, parameters, self.INPUT_DATA, context, feedback)

        # Resolve geocode column name case-insensitively
        geocode_field = "geocode"
        for field in geojson_data.fields():
            if field.name().lower() in ("geocode", "bsn_geoid", "geo_code"):
                geocode_field = field.name()
                break

        # Filter features where geocode is NULL / empty / missing
        features = [
            f for f in geojson_data.getFeatures()
            if f.attribute(geocode_field) is None
            or f.attribute(geocode_field) == NULL
            or str(f.attribute(geocode_field)).strip() in ("", "NULL", "None", "nan", "NA")
        ]

        return gmdhelpers.export_features_to_sink(
            self,
            parameters,
            self.OUTPUT,
            context,
            geojson_data.fields(),
            geojson_data.wkbType(),
            geojson_data.sourceCrs(),
            features,
            feedback,
        )

    def createInstance(self):
        return self.__class__()


