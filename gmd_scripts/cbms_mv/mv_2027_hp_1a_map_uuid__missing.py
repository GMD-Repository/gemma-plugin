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



class mv_2027_hp_1a_map_uuid__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_1a_map_uuid__missing"

    def displayName(self) -> str:
        return "mv_2027_hp_1a_map_uuid__missing"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of CBMS Form 2 datafile without geotagged points. \n \n"
            "Every datafile should have a counterpart geotagged point with the same GeoID.\n"
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
                "mv_2027_hp_1a_map_uuid__missing",
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

        ensure_field(fields, "map_uuid", QVariant.String)
        ensure_field(fields, "status", QVariant.String)

        # Helper to find field name case-insensitively from list of candidates
        def resolve_field_name(field_list, candidate_names):
            for candidate in candidate_names:
                for fld in field_list:
                    if fld.name().lower() == candidate.lower():
                        return fld.name()
            return None

        def is_null(val):
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            return False

        # Collect all valid Map UUIDs present in the geotagged point features (GeoJSON)
        geotagged_ids = set()
        uuid_field = resolve_field_name(source_fields, ["map_uuid"])

        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break
            if uuid_field:
                val = f.attribute(uuid_field)
                if not is_null(val):
                    geotagged_ids.add(str(val).strip())

        # Extract records list from JSON data (CBMS Form 2 datafile)
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

        invalid_features = []

        # Check each record in the Form 2 datafile for a counterpart in geotagged points
        for rec in records:
            if feedback and feedback.isCanceled():
                break

            rec_dict = rec if isinstance(rec, dict) else {}
            if "properties" in rec_dict and isinstance(rec_dict["properties"], dict):
                rec_props = rec_dict["properties"]
            else:
                rec_props = rec_dict

            # Look up map_uuid in record properties
            rec_id = None
            for k, v in rec_props.items():
                if k.lower() == "map_uuid" and not is_null(v):
                    rec_id = str(v).strip()
                    break

            # If Form 2 record has no matching geotagged point (or no map_uuid), flag it
            if not rec_id or rec_id not in geotagged_ids:
                out_feat = QgsFeature(fields)

                for fld in fields:
                    fld_name = fld.name()
                    val = None
                    for k, v in rec_props.items():
                        if k.lower() == fld_name.lower():
                            val = v
                            break
                    if val is not None:
                        out_feat.setAttribute(fld_name, val)

                if rec_id:
                    out_feat.setAttribute("map_uuid", rec_id)
                out_feat.setAttribute("status", "Missing Geotagged Point")

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} Form 2 datafile records without counterpart geotagged points."
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
