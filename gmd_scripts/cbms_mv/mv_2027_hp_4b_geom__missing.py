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
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFile,
    QgsVectorLayer,
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers




class mv_2027_hp_4b_geom__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4b_geom__missing"

    def displayName(self) -> str:
        return "mv_2027_hp_4b_geom__missing"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with empty geometry. \n \n"
            "Every geotagged point should have a geometry.\n"
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
                "mv_2027_hp_4b_geom__missing",
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

        fields = geojson_data.fields()

        def is_na(val: Any) -> bool:
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            return str(val).strip().lower() in ("", "null", "none", "nan", "na")

        long_name = "longitude"
        lat_name = "latitude"
        for field in fields:
            fname = field.name().lower()
            if fname == "longitude":
                long_name = field.name()
            elif fname == "latitude":
                lat_name = field.name()

        missing_features = []
        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break

            geom = f.geometry()
            geom_missing = geom is None or geom.isEmpty()

            long_val = f.attribute(long_name) if long_name in fields.names() else NULL
            lat_val = f.attribute(lat_name) if lat_name in fields.names() else NULL

            if is_na(long_val) or is_na(lat_val) or geom_missing:
                missing_features.append(f)

        return gmdhelpers.export_features_to_sink(
            self,
            parameters,
            self.OUTPUT,
            context,
            fields,
            geojson_data.wkbType(),
            geojson_data.sourceCrs(),
            missing_features,
            feedback,
        )


    def createInstance(self):
        return self.__class__()
