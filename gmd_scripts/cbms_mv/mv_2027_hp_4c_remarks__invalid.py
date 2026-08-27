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


class mv_2027_hp_4c_remarks__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"
    OUTPUT_ERRORS = "OUTPUT_ERRORS"
    OPEN_FOR_EDITING = "OPEN_FOR_EDITING"

    def name(self):
        return "mv_2027_hp_4c_remarks__invalid"

    def displayName(self):
        return "mv_2027_hp_4c_remarks__invalid"

    def group(self):
        return "2027 CBMS"

    def groupId(self):
        return "cbms_mv"

    def shortHelpString(self):
        return (
            "List of geotagged points with deletion or review remarks. \n \n"
            "Features with remarks value are flagged for review.\n"
            "A separate table lists each unique remarks value \n"
            "and how many features share it, for cross-validation.\n"
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
                "mv_2027_hp_4c_remarks__invalid",
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

        open_for_editing = self.parameterAsBoolean(parameters, self.OPEN_FOR_EDITING, context)

        features = gmdhelpers.filter_geometry_validity(geojson_data, feedback)
        fields = geojson_data.fields()

        # Keep only features that have a non-null, non-empty remarks value.
        # QGIS returns NULL / QVariant() for missing attributes, not Python None.
        valid_features = []
        for f in features:
            remarks_value = f["remarks"]

            # Skip features with null or empty remarks
            if remarks_value is None or remarks_value == NULL:
                continue
            if str(remarks_value).strip() == "":
                continue

            valid_features.append(f)

        features = valid_features

        # Add per-remarks count column for cross-validation
        features, fields = gmdhelpers.add_count(features, fields, "remarks")

        # Defensive filter: skip any feature where n came back null
        features = [
            f for f in features
            if f["n"] is not None and f["n"] != NULL
        ]

        features = gmdhelpers.arrange(features, "remarks")

        # --- Main flagged-features output ---
        result = gmdhelpers.export_features_to_sink(
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

        # --- Error summary table: one row per unique remarks value + count ---
        error_fields = QgsFields()
        error_fields.append(QgsField("remarks", QVariant.String))
        error_fields.append(QgsField("n", QVariant.Int))

        # Aggregate unique remarks values and their counts
        seen = {}
        for f in features:
            rval = str(f["remarks"])
            seen[rval] = f["n"]

        (error_sink, error_dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_ERRORS,
            context,
            error_fields,
            QgsWkbTypes.NoGeometry,
            QgsCoordinateReferenceSystem("EPSG:4326"),
        )
        if error_sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT_ERRORS))

        for rval, count in sorted(seen.items()):
            if feedback and feedback.isCanceled():
                break
            err_feat = QgsFeature(error_fields)
            err_feat.setAttributes([rval, count])
            error_sink.addFeature(err_feat, QgsFeatureSink.FastInsert)

        feedback.pushInfo(
            f"Flagged {len(features)} feature(s) across {len(seen)} unique remarks value(s)."
        )

        result[self.OUTPUT_ERRORS] = error_dest_id

        # --- Open output layer in edit mode if requested ---
        if open_for_editing:
            main_dest_id = result.get(self.OUTPUT)
            if main_dest_id:
                context.addLayerToLoadOnCompletion(
                    main_dest_id,
                    context.LayerDetails(
                        "mv_2027_hp_4c_remarks__invalid [editable]",
                        QgsProject.instance(),
                    ),
                )

        return result

    def createInstance(self):
        return self.__class__()

