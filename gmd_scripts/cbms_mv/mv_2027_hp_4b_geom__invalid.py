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



class mv_2027_hp_4b_geom__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4b_geom__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4b_geom__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with mismatched values in the geometry and Longitude and Latitude columns. \n \n"
            "Values in the geometry of the geotagged points should be identical to the values in the Longitude and Latitude columns.\n"
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
                "mv_2027_hp_4b_geom__invalid",
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

            # Read attribute values
            raw_long = f.attribute(long_field) if long_field else None
            raw_lat = f.attribute(lat_field) if lat_field else None

            if is_null(raw_long) or is_null(raw_lat):
                continue

            try:
                attr_long = round(float(raw_long), 7)
                attr_lat = round(float(raw_lat), 7)
            except (ValueError, TypeError):
                continue

            # Geometry coordinates
            long_geom = round(point_geom.x(), 7)
            lat_geom = round(point_geom.y(), 7)

            # Flag if geometry values are NOT identical to attribute values
            if attr_long != long_geom or attr_lat != lat_geom:
                out_feat = QgsFeature(fields)
                out_feat.setGeometry(geom)

                # Copy existing attributes
                for i in range(source_fields.count()):
                    out_feat.setAttribute(source_fields.at(i).name(), f.attribute(i))

                out_feat.setAttribute("longitude", attr_long)
                out_feat.setAttribute("latitude", attr_lat)
                out_feat.setAttribute("longitude_geometry", long_geom)
                out_feat.setAttribute("latitude_geometry", lat_geom)

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} features with geometry/attribute coordinate mismatch."
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
