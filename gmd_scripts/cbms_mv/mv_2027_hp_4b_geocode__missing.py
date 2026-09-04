from typing import Any, Optional, Dict

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


class mv_2027_hp_4b_geocode__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

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
            "List of geotagged points with NULL Geocodes. \n \n"
            "Every geotagged point should have a valid geocode in the geocode column.\n"
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

        # Resolve geocode column name case-insensitively
        geocode_field = "ea_geocode"
        for field in fields:
            if field.name().lower() in ("ea_geocode", "geocode", "bsn_geoid", "geo_code"):
                geocode_field = field.name()
                break

        # Helper to check for missing/null attribute values
        def is_missing(val: Any) -> bool:
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            return str(val).strip().lower() in ("", "null", "none", "nan", "na")

        # Filter features where geocode is NULL / empty / missing
        flagged_features = []
        for f in features:
            if feedback and feedback.isCanceled():
                break
            val = f.attribute(geocode_field) if geocode_field in fields.names() else NULL
            if is_missing(val):
                flagged_features.append(f)

        feedback.pushInfo(
            f"Flagged {len(flagged_features)} feature(s) with missing or null '{geocode_field}' values."
        )

        # Build a temporary layer from flagged_features so select_mv can operate on it
        temp_layer = QgsVectorLayer(
            f"Point?crs={geojson_data.sourceCrs().authid()}", "temp", "memory"
        )
        temp_layer_dp = temp_layer.dataProvider()
        temp_layer_dp.addAttributes(fields.toList())
        temp_layer.updateFields()
        temp_layer_dp.addFeatures(flagged_features)

        # Select & organize columns using select_mv
        final_output = gmdhelpers.select_mv(
            temp_layer,
            [],
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
