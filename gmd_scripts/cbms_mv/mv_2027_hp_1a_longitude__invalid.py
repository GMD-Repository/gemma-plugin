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


class mv_2027_hp_1a_longitude__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self):
        return "mv_2027_hp_1a_longitude__invalid"

    def displayName(self):
        return "mv_2027_hp_1a_longitude__invalid"

    def group(self):
        return "2027 CBMS"

    def groupId(self):
        return "cbms_mv"

    def shortHelpString(self):
        return (
            "List of datafiles and geotagged points with the same coordinates but different map_uuid.\n \n"
            "Datafiles and geotagged points with the same coordinates should have the same map_uuid.\n"
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
                "mv_2027_hp_1a_longitude__invalid",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        geojson_data = gmdhelpers.load_cbms_geojson(self, parameters, self.INPUT_LAYER, context)
        json_data = gmdhelpers.load_cbms_json(self, parameters, self.INPUT_DATA, context, feedback)

        features = gmdhelpers.filter_geometry_validity(geojson_data, feedback)
        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)

        for fname in ("map_uuid_df", "longitude_df", "latitude_df"):
            if fields.indexFromName(fname) == -1:
                fields.append(QgsField(fname, QVariant.String))

        def is_null(val):
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            val_str = str(val).strip()
            if not val_str or val_str.lower() in ("null", "nan", "na"):
                return True
            return False

        # Resolve field names case-insensitively
        def resolve_field_name(field_list, target_names):
            for candidate in target_names:
                for fld in field_list:
                    if fld.name().lower() == candidate.lower():
                        return fld.name()
            return None

        lon_field = resolve_field_name(source_fields, ["longitude"])
        lat_field = resolve_field_name(source_fields, ["latitude"])
        uuid_field = resolve_field_name(source_fields, ["map_uuid"])

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

        # Build a lookup of datafile (cover page) records by rounded coordinates,
        # keeping the first match per coordinate pair (mirrors dplyr's multiple = "first").
        df_lookup: Dict[tuple, Dict[str, Any]] = {}
        for rec in records:
            rec_dict = rec if isinstance(rec, dict) else {}
            rec_props = rec_dict.get("properties", rec_dict) if "properties" in rec_dict else rec_dict

            case_id_val = None
            x_val = None
            y_val = None
            map_uuid_df_val = None

            for k, v in rec_props.items():
                k_lower = k.lower()
                if k_lower == "case_id":
                    case_id_val = v
                elif k_lower == "x_current":
                    x_val = v
                elif k_lower == "y_current":
                    y_val = v
                elif k_lower == "map_uuid":
                    map_uuid_df_val = v

            if is_null(case_id_val):
                continue
            if is_null(x_val) or is_null(y_val):
                continue

            try:
                key = (round(float(x_val), 7), round(float(y_val), 7))
            except (TypeError, ValueError):
                continue

            # Keep first match (SetDefault logic matches R multiple='first')
            df_lookup.setdefault(key, rec_props)

        valid_features = []
        for f in features:
            f.setFields(fields, False)
            f.resizeAttributes(fields.count())

            lon_value = f.attribute(lon_field) if lon_field else None
            lat_value = f.attribute(lat_field) if lat_field else None

            if is_null(lon_value) or is_null(lat_value):
                feedback.pushWarning(
                    "Feature id " + str(f.id()) + " has a null longitude/latitude value, skipping."
                )
                continue

            try:
                lon_key = round(float(lon_value), 7)
                lat_key = round(float(lat_value), 7)
            except (TypeError, ValueError) as e:
                feedback.pushWarning(
                    "Feature id " + str(f.id()) + " has invalid coordinates: " + str(e)
                )
                continue

            rec = df_lookup.get((lon_key, lat_key))
            if rec is None:
                continue

            map_uuid_geo = f.attribute(uuid_field) if uuid_field else None
            
            # Find map_uuid in JSON record properties case-insensitively
            map_uuid_df = None
            for k, v in rec.items():
                if k.lower() == "map_uuid":
                    map_uuid_df = v
                    break

            if is_null(map_uuid_geo) or is_null(map_uuid_df):
                continue

            uuid_geo_str = str(map_uuid_geo).strip()
            uuid_df_str = str(map_uuid_df).strip()

            if uuid_geo_str == uuid_df_str:
                continue

            f["map_uuid_df"] = uuid_df_str
            f["longitude_df"] = "{:.7f}".format(lon_key)
            f["latitude_df"] = "{:.7f}".format(lat_key)

            valid_features.append(f)

        features = gmdhelpers.arrange(valid_features, lon_field if lon_field else "longitude")

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