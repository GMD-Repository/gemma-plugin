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



class mv_2027_hp_1a_map_uuid__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_1a_map_uuid__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_1a_map_uuid__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of datafiles and geotagged points with the same map_uuid but different coordinates. \n \n"
            "Datafiles and geotagged points with the same map_uuid should have the same coordinates.\n"
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
                "mv_2027_hp_1a_map_uuid__invalid",
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

        # ---------------------------------------------------------------------
        # 2. dplyr::inner_join(..., by = "map_uuid", multiple = "first")
        #    Tool: native:joinattributestable
        # ---------------------------------------------------------------------
        joined_layer = processing.run(
            "native:joinattributestable",
            {
                "INPUT": geojson_data,
                "FIELD": "map_uuid",
                "INPUT_2": json_data,
                "FIELD_2": "map_uuid",
                "FIELDS_TO_COPY": ["longitude_df", "latitude_df"],
                "METHOD": 1,                      # multiple = "first"
                "DISCARD_NONMATCHING": True,       # INNER JOIN
                "PREFIX": "",
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # ---------------------------------------------------------------------
        # 3. dplyr::filter(longitude != longitude_df | latitude != latitude_df | is.na(...))
        #    Tool: native:extractbyexpression
        # ---------------------------------------------------------------------
        filter_expr = (
            '"longitude" IS NULL OR "latitude" IS NULL OR '
            '"longitude_df" IS NULL OR "latitude_df" IS NULL OR '
            'round(to_real("longitude"), 7) != round(to_real("longitude_df"), 7) OR '
            'round(to_real("latitude"), 7) != round(to_real("latitude_df"), 7)'
        )

        filtered_layer = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": joined_layer,
                "EXPRESSION": filter_expr,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # ---------------------------------------------------------------------
        # 4. select_mv(longitude, latitude, longitude_df, latitude_df)
        # ---------------------------------------------------------------------
        final_output = gmdhelpers.select_mv(
            filtered_layer,
            ["longitude", "latitude", "longitude_df", "latitude_df"],
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
