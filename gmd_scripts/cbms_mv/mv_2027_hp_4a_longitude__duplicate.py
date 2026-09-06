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


class mv_2027_hp_4a_longitude__duplicate(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4a_longitude__duplicate"

    def displayName(self) -> str:
        return "mv_2027_hp_4a_longitude__duplicate"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with duplicate coordinates. \n \n"
            "The coordinates should be unique.\n"
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
                "mv_2027_hp_4a_longitude__duplicate",
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

        features = gmdhelpers.filter_geometry_validity(geojson_data, feedback)
        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)

        # Ensure 'dupli_coor' field exists for grouping
        if fields.indexOf("dupli_coor") == -1:
            fields.append(QgsField("dupli_coor", QVariant.String))

        dupli_coor_idx = fields.indexOf("dupli_coor")

        # Resolve field names case-insensitively
        def resolve_field_name(field_list, target_name):
            target_lower = target_name.lower()
            for fld in field_list:
                if fld.name().lower() == target_lower:
                    return fld.name()
            return None

        long_field = resolve_field_name(source_fields, "longitude")
        lat_field = resolve_field_name(source_fields, "latitude")

        long_idx = fields.indexOf(long_field) if long_field else -1
        lat_idx = fields.indexOf(lat_field) if lat_field else -1

        valid_features = []
        for f in features:
            if feedback and feedback.isCanceled():
                break

            lon_val = f.attribute(long_field) if long_field else None
            lat_val = f.attribute(lat_field) if lat_field else None

            lon_float, lat_float = None, None

            # 1. Try parsing attribute coordinates
            if lon_val is not None and lon_val != NULL and lat_val is not None and lat_val != NULL:
                try:
                    lon_float = round(float(lon_val), 7)
                    lat_float = round(float(lat_val), 7)
                except (ValueError, TypeError):
                    pass

            # 2. Fallback to point geometry if attribute coordinates are missing or invalid
            if lon_float is None or lat_float is None:
                geom = f.geometry()
                if geom and not geom.isEmpty():
                    pt = geom.asPoint()
                    if not pt.isEmpty():
                        lon_float = round(pt.x(), 7)
                        lat_float = round(pt.y(), 7)

            if lon_float is None or lat_float is None:
                if feedback:
                    feedback.pushWarning(
                        f"Feature id {f.id()} has null or invalid longitude/latitude, skipping."
                    )
                continue

            # dupli_coor = paste0(round(longitude, 7), round(latitude, 7))
            dupli_coor = f"{lon_float:.7f}{lat_float:.7f}"

            out_feat = QgsFeature(fields)
            out_feat.setGeometry(f.geometry())
            attrs = list(f.attributes())
            while len(attrs) < fields.count():
                attrs.append(NULL)

            attrs[dupli_coor_idx] = dupli_coor
            if long_idx != -1:
                attrs[long_idx] = lon_float
            if lat_idx != -1:
                attrs[lat_idx] = lat_float

            out_feat.setAttributes(attrs)
            valid_features.append(out_feat)

        # 3. add_count(dupli_coor) -> attaches 'n'
        features, fields = gmdhelpers.add_count(valid_features, fields, "dupli_coor")

        # 4. filter(n > 1)
        features = [
            f for f in features
            if f["n"] is not None and f["n"] != NULL and f["n"] > 1
        ]

        # 5. arrange(geom / dupli_coor)
        features = gmdhelpers.arrange(features, "dupli_coor")

        # 6. Create temporary memory layer to apply select_mv
        crs = geojson_data.sourceCrs()
        if not crs.isValid():
            crs = QgsCoordinateReferenceSystem("EPSG:4326")
        wkb_type_str = QgsWkbTypes.displayString(geojson_data.wkbType())
        temp_layer = QgsVectorLayer(
            f"{wkb_type_str}?crs={crs.authid()}",
            "temp_duplicates",
            "memory",
        )
        dp = temp_layer.dataProvider()
        dp.addAttributes(fields)
        temp_layer.updateFields()
        dp.addFeatures(features)

        # 7. select_mv(longitude, latitude) & select(-dupli_coor)
        final_output = gmdhelpers.select_mv(
            temp_layer,
            ["longitude", "latitude", "n"],
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
