# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU General Public License as published by  *
# *   the Free Software Foundation; either version 2 of the License, or     *
# *   (at your option) any later version.                                   *
# *                                                                         *
# ***************************************************************************

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

        # Add a field holding longitude rounded to 6 decimal places, as a string
        # (avoids float precision issues when comparing/grouping values)
        if fields.indexFromName("lon_key") == -1:
            fields.append(QgsField("lon_key", QVariant.String))

        valid_features = []
        for f in features:
            f.setFields(fields, False)
            # Ensure the attribute array actually matches the new field count.
            # setFields() alone does not resize/pad the attribute values,
            # which can leave some features misaligned once a field is added.
            f.resizeAttributes(fields.count())

            lon_value = f["longitude"]

            # Guard against null/invalid longitude values (QGIS returns
            # NULL / QVariant() for missing attributes, not Python None)
            if lon_value is None or lon_value == NULL:
                feedback.pushWarning(
                    "Feature id " + str(f.id()) + " has a null longitude value, skipping."
                )
                continue

            try:
                f["lon_key"] = "{:.6f}".format(float(lon_value))
            except (TypeError, ValueError) as e:
                feedback.pushWarning(
                    "Feature id " + str(f.id()) + " has invalid longitude '" + str(lon_value) + "': " + str(e)
                )
                continue

            valid_features.append(f)

        features = valid_features

        features, fields = gmdhelpers.add_count(features, fields, "lon_key")

        # Defensive filter: skip any feature where the count came back null
        # rather than a real integer (shouldn't happen after the fix above,
        # but keeps the algorithm from crashing if it ever does).
        features = [
            f for f in features
            if f["n"] is not None and f["n"] != NULL and f["n"] > 1
        ]

        features = gmdhelpers.arrange(features, "lon_key")

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