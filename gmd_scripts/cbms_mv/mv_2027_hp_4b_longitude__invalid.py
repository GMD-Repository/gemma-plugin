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



class mv_2027_hp_4b_longitude__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4b_longitude__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4b_longitude__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points whose Longitude and Latitude values are far from their geometry. \n \n"
            "The geometry of each geotagged point must match its Longitude and Latitude column values.\n"
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
                "mv_2027_hp_4b_longitude__invalid",
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

        # Build output fields: copy source fields + ensure target columns exist
        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)

        def ensure_field(flds, name, ftype=QVariant.Double):
            if flds.indexOf(name) == -1:
                flds.append(QgsField(name, ftype))

        ensure_field(fields, "longitude", QVariant.Double)
        ensure_field(fields, "latitude", QVariant.Double)
        ensure_field(fields, "longitude_geometry", QVariant.Double)
        ensure_field(fields, "latitude_geometry", QVariant.Double)
        ensure_field(fields, "distance_m", QVariant.Double)

        # Resolve actual field names case-insensitively
        def resolve_field_name(field_list, target_name):
            for fld in field_list:
                if fld.name().lower() == target_name.lower():
                    return fld.name()
            return None

        long_field = resolve_field_name(source_fields, "longitude")
        lat_field = resolve_field_name(source_fields, "latitude")

        if long_field is None or lat_field is None:
            feedback.reportError(
                f"Required fields not found. "
                f"longitude={'FOUND (' + long_field + ')' if long_field else 'MISSING'}, "
                f"latitude={'FOUND (' + lat_field + ')' if lat_field else 'MISSING'}. "
                f"Available fields: {[f.name() for f in source_fields]}"
            )
            raise QgsProcessingException(
                "Required attribute fields 'longitude' and/or 'latitude' not found in input layer."
            )

        def is_null(val):
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            return False

        invalid_features = []

        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break

            geom = f.geometry()
            if geom is None or geom.isEmpty():
                continue

            point_geom = geom.asPoint()
            if point_geom.isEmpty():
                continue

            raw_long = f.attribute(long_field)
            raw_lat = f.attribute(lat_field)

            if is_null(raw_long) or is_null(raw_lat):
                continue

            try:
                attr_long = round(float(raw_long), 7)
                attr_lat = round(float(raw_lat), 7)
            except (ValueError, TypeError):
                continue

            long_geom = round(point_geom.x(), 7)
            lat_geom = round(point_geom.y(), 7)

            # Calculate Haversine distance between attribute coords and geometry coords
            import math
            R = 6371000  # Earth radius in meters
            lat1 = math.radians(lat_geom)
            lat2 = math.radians(attr_lat)
            dlat = math.radians(attr_lat - lat_geom)
            dlon = math.radians(attr_long - long_geom)
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
            a = max(0.0, min(1.0, a))  # Clamp to prevent math domain error
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance_m = round(R * c, 4)

            # Include feature only if distance > 30m
            if distance_m > 30.0:
                out_feat = QgsFeature(fields)
                out_feat.setGeometry(geom)

                # Copy existing attributes
                for i in range(source_fields.count()):
                    out_feat.setAttribute(source_fields.at(i).name(), f.attribute(i))

                # Set mutated / target attributes
                out_feat.setAttribute("longitude", attr_long)
                out_feat.setAttribute("latitude", attr_lat)
                out_feat.setAttribute("longitude_geometry", long_geom)
                out_feat.setAttribute("latitude_geometry", lat_geom)
                out_feat.setAttribute("distance_m", distance_m)

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} features with geometry distance mismatch > 30m."
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
