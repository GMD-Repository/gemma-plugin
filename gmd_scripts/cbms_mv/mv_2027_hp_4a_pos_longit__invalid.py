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
    QgsPointXY,
    QgsDistanceArea,
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



class mv_2027_hp_4a_pos_longit__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4a_pos_longit__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4a_pos_longit__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points whose locations are far from the enumerator's position. \n \n"
            "The enumerator's position during tagging was far from the geotagged building's location.\n"
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
                "mv_2027_hp_4a_pos_longit__invalid",
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

        # Setup ellipsoidal distance calculator (returns meters)
        distance_calc = QgsDistanceArea()
        crs = geojson_data.sourceCrs()
        if not crs.isValid():
            crs = QgsCoordinateReferenceSystem("EPSG:4326")
        distance_calc.setSourceCrs(crs, context.transformContext())
        distance_calc.setEllipsoid("WGS84")

        # Build output fields: copy source fields + ensure new columns exist
        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)

        def ensure_field(flds, name, ftype=QVariant.Double):
            if flds.indexOf(name) == -1:
                flds.append(QgsField(name, ftype))

        ensure_field(fields, "pos_longit", QVariant.Double)
        ensure_field(fields, "pos_latitu", QVariant.Double)
        ensure_field(fields, "longitude_geometry", QVariant.Double)
        ensure_field(fields, "latitude_geometry", QVariant.Double)
        ensure_field(fields, "distance_m", QVariant.Double)

        # Resolve actual field names case-insensitively
        def resolve_field_name(field_list, target_name):
            """Find actual field name matching target_name (case-insensitive)."""
            for fld in field_list:
                if fld.name().lower() == target_name.lower():
                    return fld.name()
            return None

        pos_long_field = resolve_field_name(source_fields, "pos_longit")
        pos_lat_field = resolve_field_name(source_fields, "pos_latitu")

        if pos_long_field is None or pos_lat_field is None:
            feedback.reportError(
                f"Required fields not found. "
                f"pos_longit={'FOUND (' + pos_long_field + ')' if pos_long_field else 'MISSING'}, "
                f"pos_latitu={'FOUND (' + pos_lat_field + ')' if pos_lat_field else 'MISSING'}. "
                f"Available fields: {[f.name() for f in source_fields]}"
            )
            raise QgsProcessingException(
                "Required attribute fields 'pos_longit' and/or 'pos_latitu' not found in input layer."
            )

        def is_null(val):
            """Check if a value is NULL/None/empty (handles QVariant)."""
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
            pos_long = NULL
            pos_lat = NULL
            long_geom = NULL
            lat_geom = NULL
            distance_m = NULL

            # Try to parse enumerator position
            if pos_long_field:
                raw_pos_long = f.attribute(pos_long_field)
                if not is_null(raw_pos_long):
                    try:
                        pos_long = round(float(raw_pos_long), 7)
                    except (ValueError, TypeError):
                        pos_long = NULL

            if pos_lat_field:
                raw_pos_lat = f.attribute(pos_lat_field)
                if not is_null(raw_pos_lat):
                    try:
                        pos_lat = round(float(raw_pos_lat), 7)
                    except (ValueError, TypeError):
                        pos_lat = NULL

            # Try to extract geometry coordinates
            if geom is not None and not geom.isEmpty():
                point_geom = geom.asPoint()
                if not point_geom.isEmpty():
                    long_geom = round(point_geom.x(), 7)
                    lat_geom = round(point_geom.y(), 7)

            # Calculate distance if both positions are available
            if (not is_null(pos_long) and not is_null(pos_lat)
                    and not is_null(long_geom) and not is_null(lat_geom)):
                import math
                R = 6371000  # Earth radius in meters
                lat1 = math.radians(lat_geom)
                lat2 = math.radians(pos_lat)
                dlat = math.radians(pos_lat - lat_geom)
                dlon = math.radians(pos_long - long_geom)
                a = (math.sin(dlat / 2) ** 2 +
                     math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
                a = max(0.0, min(1.0, a))  # clamp to avoid math domain errors
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                distance_m = round(R * c, 4)

            # Include feature if distance > 30m or distance could not be computed
            if is_null(distance_m) or distance_m > 30.0:
                out_feat = QgsFeature(fields)
                if geom is not None:
                    out_feat.setGeometry(geom)

                # Copy existing attributes
                for i in range(source_fields.count()):
                    out_feat.setAttribute(source_fields.at(i).name(), f.attribute(i))

                # Set mutated / new columns
                out_feat.setAttribute("pos_longit", pos_long)
                out_feat.setAttribute("pos_latitu", pos_lat)
                out_feat.setAttribute("longitude_geometry", long_geom)
                out_feat.setAttribute("latitude_geometry", lat_geom)
                out_feat.setAttribute("distance_m", distance_m)

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} features with distance > 30m or missing position data."
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
