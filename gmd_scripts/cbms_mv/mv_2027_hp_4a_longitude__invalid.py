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
try:
    from .. import gmdhelpers
except (ImportError, ValueError):
    try:
        from gmd_scripts import gmdhelpers
    except ImportError:
        import gmdhelpers


class mv_2027_hp_4a_longitude__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4a_longitude__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4a_longitude__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with XY values outside the bounds of the Philippines. \n \n"
            "XY values of the geotagged points must be within the upper and lower limits of the Philippines' coordinates.\n"
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
                "mv_2027_hp_4a_longitude__invalid",
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

        # Philippines WGS84 coordinate bounds
        MIN_LON, MAX_LON = 116.0, 127.0
        MIN_LAT, MAX_LAT = 4.0, 21.5

        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)

        def ensure_field(flds, name, ftype=QVariant.Double):
            if flds.indexOf(name) == -1:
                flds.append(QgsField(name, ftype))

        ensure_field(fields, "longitude", QVariant.Double)
        ensure_field(fields, "latitude", QVariant.Double)
        ensure_field(fields, "longitude_geometry", QVariant.Double)
        ensure_field(fields, "latitude_geometry", QVariant.Double)

        # Resolve field names case-insensitively
        def resolve_field_name(field_list, target_name):
            for fld in field_list:
                if fld.name().lower() == target_name.lower():
                    return fld.name()
            return None

        long_field = resolve_field_name(source_fields, "longitude")
        lat_field = resolve_field_name(source_fields, "latitude")

        def is_null(val):
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            return False

        def is_out_of_bounds_lon(val):
            if is_null(val):
                return False  # Disregard NULL
            return val < MIN_LON or val > MAX_LON

        def is_out_of_bounds_lat(val):
            if is_null(val):
                return False  # Disregard NULL
            return val < MIN_LAT or val > MAX_LAT

        invalid_features = []

        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break

            geom = f.geometry()
            attr_long = NULL
            attr_lat = NULL
            long_geom = NULL
            lat_geom = NULL

            # Read attribute longitude/latitude
            if long_field:
                raw_long = f.attribute(long_field)
                if not is_null(raw_long):
                    try:
                        attr_long = round(float(raw_long), 7)
                    except (ValueError, TypeError):
                        attr_long = NULL

            if lat_field:
                raw_lat = f.attribute(lat_field)
                if not is_null(raw_lat):
                    try:
                        attr_lat = round(float(raw_lat), 7)
                    except (ValueError, TypeError):
                        attr_lat = NULL

            # Extract geometry coordinates
            if geom is not None and not geom.isEmpty():
                point_geom = geom.asPoint()
                if not point_geom.isEmpty():
                    long_geom = round(point_geom.x(), 7)
                    lat_geom = round(point_geom.y(), 7)

            # Flag feature if any present coordinate is outside Philippine bounds
            is_invalid = (
                is_out_of_bounds_lon(attr_long) or
                is_out_of_bounds_lat(attr_lat) or
                is_out_of_bounds_lon(long_geom) or
                is_out_of_bounds_lat(lat_geom)
            )

            if is_invalid:
                out_feat = QgsFeature(fields)
                if geom is not None:
                    out_feat.setGeometry(geom)

                for i in range(source_fields.count()):
                    out_feat.setAttribute(source_fields.at(i).name(), f.attribute(i))

                out_feat.setAttribute("longitude", attr_long)
                out_feat.setAttribute("latitude", attr_lat)
                out_feat.setAttribute("longitude_geometry", long_geom)
                out_feat.setAttribute("latitude_geometry", lat_geom)

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} features with XY values outside Philippines bounds."
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
