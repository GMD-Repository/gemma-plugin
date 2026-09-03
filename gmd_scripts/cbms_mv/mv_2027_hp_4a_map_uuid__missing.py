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
from PyQt5.QtGui import QIcon
import processing
from .. import gmdhelpers


class mv_2027_hp_4b_geocode__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"
    OPEN_FOR_EDITING = "OPEN_FOR_EDITING"

    # Field in the geotagged layer that must never be NULL/missing.
    GEOCODE_FIELD = "ea_geocode"

    def name(self) -> str:
        return "mv_2027_hp_4b_geocode__missing"

    def displayName(self) -> str:
        return "mv_2027_hp_4b_geocode__missing"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with NULL or missing Geocodes. \n \n"
            "Every geotagged point should have a valid geocode in the geocode column.\n"
            "Flagged features can optionally be opened directly in edit mode for correction.\n"
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
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "mv_2027_hp_4b_geocode__missing",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.OPEN_FOR_EDITING,
                "Open output layer in edit mode after running",
                defaultValue=False,
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
        open_for_editing = self.parameterAsBoolean(parameters, self.OPEN_FOR_EDITING, context)

        # Filter features with NULL/missing ea_geocode
        temp_layer = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": geojson_data,
                "EXPRESSION": f'"{self.GEOCODE_FIELD}" IS NULL',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )["OUTPUT"]

        feedback.pushInfo(
            f"Flagged {temp_layer.featureCount()} feature(s) with missing/NULL "
            f"'{self.GEOCODE_FIELD}' values."
        )

        # Select & organize columns using select_mv
        final_output = gmdhelpers.select_mv(
            temp_layer,
            [self.GEOCODE_FIELD],
            context=context,
            feedback=feedback,
        )

        # Export flagged features to output sink
        result = gmdhelpers.export_features_to_sink(
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

        # Optionally load output layer in edit mode
        if open_for_editing:
            main_dest_id = result.get(self.OUTPUT)
            if main_dest_id:
                context.addLayerToLoadOnCompletion(
                    main_dest_id,
                    context.LayerDetails(
                        "mv_2027_hp_4b_geocode__missing [editable]",
                        QgsProject.instance(),
                    ),
                )

        return result

    def createInstance(self):
        return self.__class__()