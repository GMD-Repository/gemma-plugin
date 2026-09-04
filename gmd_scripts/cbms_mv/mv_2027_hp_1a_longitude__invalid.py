import os
import json
import processing
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
    QgsProviderRegistry,
    QgsDistanceArea,
    QgsPointXY,
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers


class mv_2027_hp_1a_longitude__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
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

        def is_null(val):
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            val_str = str(val).strip()
            if not val_str or val_str.lower() in ("null", "nan", "na"):
                return True
            return False

        def resolve_field_name(field_list, target_names):
            for candidate in target_names:
                for fld in field_list:
                    if fld.name().lower() == candidate.lower():
                        return fld.name()
            return None

        def round_coord(val):
            if is_null(val):
                return None
            try:
                return round(float(val), 7)
            except (TypeError, ValueError):
                return None

        def clean_str(val):
            return "" if is_null(val) else str(val).strip()

        lon_field = resolve_field_name(source_fields, ["longitude"])
        lat_field = resolve_field_name(source_fields, ["latitude"])
        uuid_field = resolve_field_name(source_fields, ["map_uuid"])

        # 1. Extract records from the JSON datafile
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

        # 2. GEO lookup by rounded coordinates (multiple = 'first')
        geo_lookup: Dict[tuple, QgsFeature] = {}
        for f in features:
            lon = round_coord(f.attribute(lon_field) if lon_field else None)
            lat = round_coord(f.attribute(lat_field) if lat_field else None)
            if lon is None or lat is None:
                continue
            key = (lon, lat)
            if key not in geo_lookup:
                geo_lookup[key] = f

        out_fields = QgsFields()
        out_fields.append(QgsField("map_uuid_df", QVariant.String))
        out_fields.append(QgsField("longitude_df", QVariant.Double))
        out_fields.append(QgsField("latitude_df", QVariant.Double))
        out_fields.append(QgsField("map_uuid", QVariant.String))
        out_fields.append(QgsField("longitude", QVariant.Double))
        out_fields.append(QgsField("latitude", QVariant.Double))

        # 3. Left-join datafile records onto geo_lookup; keep only mismatches
        matched_features = []
        for rec in records:
            rec_props = rec.get("properties", rec) if isinstance(rec, dict) else {}
            props = {str(k).lower(): v for k, v in rec_props.items()}

            lon = round_coord(props.get("longitude"))
            lat = round_coord(props.get("latitude"))
            
            if lon is None or lat is None:
                continue

            geo_feature = geo_lookup.get((lon, lat))
            if geo_feature is None:
                continue

            map_uuid_df = clean_str(props.get("map_uuid"))
            map_uuid_geo = clean_str(geo_feature.attribute(uuid_field) if uuid_field else None)
            
            if map_uuid_geo == map_uuid_df:
                continue

            new_f = QgsFeature(out_fields)
            new_f.setGeometry(geo_feature.geometry())
            new_f["map_uuid_df"] = map_uuid_df
            new_f["longitude_df"] = lon
            new_f["latitude_df"] = lat
            new_f["map_uuid"] = map_uuid_geo
            new_f["longitude"] = lon
            new_f["latitude"] = lat
            matched_features.append(new_f)

        matched_features = gmdhelpers.arrange(matched_features, "longitude")

        # 4. Build temporary memory layer for matched features
        crs = geojson_data.sourceCrs()
        wkb_type_str = QgsWkbTypes.displayString(geojson_data.wkbType())
        temp_layer = QgsVectorLayer(
            f"{wkb_type_str}?crs={crs.authid()}",
            "matched_layer",
            "memory",
        )
        dp = temp_layer.dataProvider()
        dp.addAttributes(out_fields)
        temp_layer.updateFields()
        dp.addFeatures(matched_features)

        # 5. Select & organize columns using select_mv
        final_output = gmdhelpers.select_mv(
            temp_layer,
            ["map_uuid_df", "longitude_df", "latitude_df", "map_uuid", "longitude", "latitude"],
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