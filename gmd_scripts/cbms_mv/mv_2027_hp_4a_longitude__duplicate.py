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


class mv_2027_hp_4a_longitude__duplicate(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self):
        return "mv_2027_hp_4a_longitude__duplicate"

    def displayName(self):
        return "mv_2027_hp_4a_longitude__duplicate"

    def group(self):
        return "2027 CBMS"

    def groupId(self):
        return "cbms_mv"

    def shortHelpString(self):
        return (
            "List of geotagged points with duplicate longitude. \n \n"
            "The longitude should be unique.\n"
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
                "mv_2027_hp_4a_longitude__duplicate",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        geojson_data = gmdhelpers.load_cbms_geojson(self, parameters, self.INPUT_LAYER, context)
        json_data = gmdhelpers.load_cbms_json(self, parameters, self.INPUT_DATA, context, feedback)

        features = gmdhelpers.filter_geometry_validity(geojson_data, feedback)
        fields = geojson_data.fields()

        # Add a field holding combined (longitude, latitude) rounded to 7 decimal places as a string
        if fields.indexFromName("coord_key") == -1:
            fields.append(QgsField("coord_key", QVariant.String))

        # Resolve field names case-insensitively
        def resolve_field_name(field_list, target_name):
            for fld in field_list:
                if fld.name().lower() == target_name.lower():
                    return fld.name()
            return None

        long_field = resolve_field_name(fields, "longitude")
        lat_field = resolve_field_name(fields, "latitude")

        valid_features = []
        for f in features:
            f.setFields(fields, False)
            f.resizeAttributes(fields.count())

            lon_value = f.attribute(long_field) if long_field else None
            lat_value = f.attribute(lat_field) if lat_field else None

            if lon_value is None or lon_value == NULL or lat_value is None or lat_value == NULL:
                feedback.pushWarning(
                    "Feature id " + str(f.id()) + " has null longitude or latitude, skipping."
                )
                continue

            try:
                lon_str = "{:.7f}".format(float(lon_value))
                lat_str = "{:.7f}".format(float(lat_value))
                f["coord_key"] = f"{lon_str}_{lat_str}"
            except (TypeError, ValueError) as e:
                feedback.pushWarning(
                    "Feature id " + str(f.id()) + " has invalid coordinates: " + str(e)
                )
                continue

            valid_features.append(f)

        features = valid_features

        features, fields = gmdhelpers.add_count(features, fields, "coord_key")

        features = [
            f for f in features
            if f["n"] is not None and f["n"] != NULL and f["n"] > 1
        ]

        features = gmdhelpers.arrange(features, "coord_key")

        return gmdhelpers.export_features_to_sink(
            self,
            parameters,
            self.OUTPUT,
            context,
            fields,
            geojson_data.wkbType(),
            geojson_data.sourceCrs(),
            features,
            feedback,
        )

    def createInstance(self):
        return self.__class__()