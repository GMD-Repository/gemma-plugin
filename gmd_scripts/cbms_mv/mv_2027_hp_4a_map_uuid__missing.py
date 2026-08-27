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


class mv_2027_hp_4a_map_uuid__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self):
        return "mv_2027_hp_4a_map_uuid__missing"

    def displayName(self):
        return "mv_2027_hp_4a_map_uuid__missing"

    def group(self):
        return "2027 CBMS"

    def groupId(self):
        return "cbms_mv"

    def shortHelpString(self):
        return (
            "List of geotagged points without CBMS Form 2 datafile. \n \n"
            "Every geotagged point (except for BSN 00000) should have a counterpart datafile with the same map_uuid.\n"
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
                "mv_2027_hp_4a_map_uuid__missing",
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

        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)

        def ensure_field(flds, name, ftype=QVariant.String):
            if flds.indexOf(name) == -1:
                flds.append(QgsField(name, ftype))

        ensure_field(fields, "status", QVariant.String)

        # Helper to find field name case-insensitively from list of candidates
        def resolve_field_name(field_list, candidate_names):
            for candidate in candidate_names:
                for fld in field_list:
                    if fld.name().lower() == candidate.lower():
                        return fld.name()
            return None

        # Helper to check if a value is missing, null, na, n/a, none, or empty
        def is_na(val: Any) -> bool:
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            val_str = str(val).strip().lower()
            return val_str in ("", "null", "none", "na", "n/a", "nan")

        # Extract records list from JSON data (Form 2 datafile)
        records = []
        if isinstance(json_data, list):
            records = json_data
        elif isinstance(json_data, dict):
            if "records" in json_data and isinstance(json_data["records"], list):
                records = json_data["records"]
            elif "features" in json_data and isinstance(json_data["features"], list):
                records = json_data["features"]
            elif "data" in json_data and isinstance(json_data["data"], list):
                records = json_data["data"]
            else:
                records = [json_data]

        # Collect set of all GeoIDs / Map UUIDs present in Form 2 JSON records
        form2_ids = set()
        for rec in records:
            if feedback and feedback.isCanceled():
                break

            rec_dict = rec if isinstance(rec, dict) else {}
            if "properties" in rec_dict and isinstance(rec_dict["properties"], dict):
                rec_props = rec_dict["properties"]
            else:
                rec_props = rec_dict

            rec_id = None
            for k, v in rec_props.items():
                if k.lower() == "map_uuid" and not is_na(v):
                    rec_id = str(v).strip()
                    break

            if rec_id:
                form2_ids.add(rec_id)

        uuid_field = resolve_field_name(source_fields, ["map_uuid"])
        invalid_features = []

        # Iterate over geotagged point features and check for missing/null/na/n/a map_uuid or missing Form 2 record
        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break

            feat_uuid = f.attribute(uuid_field) if uuid_field else None

            # Flag if map_uuid is missing, NULL, NA, N/A, None, or not found in Form 2 datafile
            if is_na(feat_uuid) or str(feat_uuid).strip() not in form2_ids:
                geom = f.geometry()
                out_feat = QgsFeature(fields)
                if geom is not None:
                    out_feat.setGeometry(geom)

                # Copy existing attributes
                for i in range(source_fields.count()):
                    out_feat.setAttribute(source_fields.at(i).name(), f.attribute(i))

                if is_na(feat_uuid):
                    out_feat.setAttribute("status", "Missing/NULL Map UUID")
                else:
                    out_feat.setAttribute("status", "Missing Form 2 Datafile Record")

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} geotagged points with missing/NULL map_uuid or missing Form 2 records."
        )

        return gmdhelpers.export_features_to_sink(
            self,
            parameters,
            self.OUTPUT,
            context,
            fields,
            geojson_data.wkbType(),
            geojson_data.sourceCrs(),
            invalid_features,
            feedback,
        )


    def createInstance(self):
        return self.__class__()
