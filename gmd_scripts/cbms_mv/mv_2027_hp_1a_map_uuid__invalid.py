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



class mv_2027_hp_1a_map_uuid__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
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

        # Build output fields
        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)

        def ensure_field(flds, name, ftype=QVariant.Double):
            if flds.indexOf(name) == -1:
                flds.append(QgsField(name, ftype))

        ensure_field(fields, "json_longitude", QVariant.Double)
        ensure_field(fields, "json_latitude", QVariant.Double)
        ensure_field(fields, "geom_longitude", QVariant.Double)
        ensure_field(fields, "geom_latitude", QVariant.Double)
        ensure_field(fields, "distance_m", QVariant.Double)

        # Helper to find field name case-insensitively
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

        uuid_field = resolve_field_name(source_fields, ["map_uuid"])

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

        # Build lookup table of map_uuid -> (longitude, latitude) from JSON datafile
        json_coords_by_uuid = {}

        for rec in records:
            if feedback and feedback.isCanceled():
                break

            rec_dict = rec if isinstance(rec, dict) else {}
            if "properties" in rec_dict and isinstance(rec_dict["properties"], dict):
                rec_props = rec_dict["properties"]
            else:
                rec_props = rec_dict

            # Find map_uuid in record properties
            rec_id = None
            for k, v in rec_props.items():
                if k.lower() == "map_uuid" and not is_null(v):
                    rec_id = str(v).strip()
                    break

            # Find longitude & latitude in record properties (strictly longitude and latitude)
            json_long = None
            json_lat = None

            for k, v in rec_props.items():
                if k.lower() == "longitude" and not is_null(v):
                    try:
                        json_long = round(float(v), 7)
                    except (ValueError, TypeError):
                        pass
                    break

            for k, v in rec_props.items():
                if k.lower() == "latitude" and not is_null(v):
                    try:
                        json_lat = round(float(v), 7)
                    except (ValueError, TypeError):
                        pass
                    break

            if rec_id and json_long is not None and json_lat is not None:
                json_coords_by_uuid[rec_id] = (json_long, json_lat)

        invalid_features = []

        # Iterate over geotagged points and check for coordinate mismatches with Form 2 datafile
        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break

            geom = f.geometry()
            if geom is None or geom.isEmpty():
                continue

            point_geom = geom.asPoint()
            if point_geom.isEmpty():
                continue

            feat_uuid = f.attribute(uuid_field) if uuid_field else None
            if is_null(feat_uuid):
                continue

            uuid_str = str(feat_uuid).strip()
            if uuid_str not in json_coords_by_uuid:
                continue

            json_long, json_lat = json_coords_by_uuid[uuid_str]
            geom_long = round(point_geom.x(), 7)
            geom_lat = round(point_geom.y(), 7)

            # Calculate Haversine distance between datafile coords and geometry coords
            import math
            R = 6371000  # Earth radius in meters
            lat1 = math.radians(geom_lat)
            lat2 = math.radians(json_lat)
            dlat = math.radians(json_lat - geom_lat)
            dlon = math.radians(json_long - geom_long)
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
            a = max(0.0, min(1.0, a))
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance_m = round(R * c, 4)

            # Flag if coordinates mismatch (distance > 5m or coordinates not identical)
            if distance_m > 5.0 or json_long != geom_long or json_lat != geom_lat:
                out_feat = QgsFeature(fields)
                out_feat.setGeometry(geom)

                # Copy existing attributes
                for i in range(source_fields.count()):
                    out_feat.setAttribute(source_fields.at(i).name(), f.attribute(i))

                out_feat.setAttribute("json_longitude", json_long)
                out_feat.setAttribute("json_latitude", json_lat)
                out_feat.setAttribute("geom_longitude", geom_long)
                out_feat.setAttribute("geom_latitude", geom_lat)
                out_feat.setAttribute("distance_m", distance_m)

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} features with matching map_uuid but mismatched coordinates."
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
