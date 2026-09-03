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



class mv_2027_hp_4a_geom__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4a_geom__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4a_geom__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with map_uuid not in the reference layer. \n \n"
            "The map_uuid should be retained unless the geotagged point is a new building or has a special BSN.\n"
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
            QgsProcessingParameterFile(
                self.BASE_LAYER,
                "BASE_LAYER (.gpkg file)",
                behavior=QgsProcessingParameterFile.File,
                extension="gpkg",
                optional=False,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "mv_2027_hp_4a_geom__invalid",
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
        ref_bldg_point = gmdhelpers.load_base_layer(self, parameters, self.BASE_LAYER, context)

        # 1. Build map_uuid lookup dictionary for reference building points
        ref_map = {}
        for ref_f in ref_bldg_point.getFeatures():
            if feedback and feedback.isCanceled():
                break
            uuid_val = ref_f.attribute("map_uuid")
            if uuid_val is not None and uuid_val != NULL:
                ref_map[str(uuid_val)] = {
                    "geom": ref_f.geometry(),
                    "bsn_geoid": ref_f.attribute("bsn_geoid") if hasattr(ref_f, "attribute") else NULL,
                }

        # 2. Setup ellipsoidal distance calculator (measures distance in meters)
        distance_calc = QgsDistanceArea()
        crs = geojson_data.sourceCrs()
        if not crs.isValid():
            crs = QgsCoordinateReferenceSystem("EPSG:4326")
        distance_calc.setSourceCrs(crs, context.transformContext())
        distance_calc.setEllipsoid("WGS84")

        # 3. Construct output fields (source fields + ref_map_uuid + ref_bsn_geoid + distance_m)
        source_fields = geojson_data.fields()
        out_fields = QgsFields(source_fields)

        def ensure_field(flds, name, ftype=QVariant.String):
            if flds.indexOf(name) == -1:
                flds.append(QgsField(name, ftype))

        ensure_field(out_fields, "ref_map_uuid", QVariant.String)
        ensure_field(out_fields, "ref_bsn_geoid", QVariant.String)
        ensure_field(out_fields, "distance_m", QVariant.Double)

        ref_map_uuid_idx = out_fields.indexOf("ref_map_uuid")
        ref_bsn_geoid_idx = out_fields.indexOf("ref_bsn_geoid")
        distance_m_idx = out_fields.indexOf("distance_m")

        matched_features = []

        # 4. Process features from geojson_data that have matching map_uuid in ref_bldg_point
        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break
            uuid_val = f.attribute("map_uuid")
            if uuid_val is None or uuid_val == NULL:
                continue

            uuid_str = str(uuid_val)
            if uuid_str in ref_map:
                ref_info = ref_map[uuid_str]
                g1 = f.geometry()
                g2 = ref_info["geom"]

                dist_m = NULL
                if g1 and not g1.isEmpty() and g2 and not g2.isEmpty():
                    p1 = QgsPointXY(g1.centroid().asPoint())
                    p2 = QgsPointXY(g2.centroid().asPoint())
                    dist_m = round(float(distance_calc.measureLine(p1, p2)), 3)

                out_feat = QgsFeature(out_fields)
                out_feat.setGeometry(g1)
                attrs = list(f.attributes())
                while len(attrs) < out_fields.count():
                    attrs.append(NULL)

                attrs[ref_map_uuid_idx] = uuid_str
                attrs[ref_bsn_geoid_idx] = ref_info["bsn_geoid"] if ref_info["bsn_geoid"] is not None else NULL
                attrs[distance_m_idx] = dist_m

                out_feat.setAttributes(attrs)
                matched_features.append(out_feat)

        # 5. Create temporary memory layer for matched features
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


        extracted_joined = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": temp_layer,
                "EXPRESSION": 'to_int("distance_m") > 50',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 6. Select & organize columns using select_mv
        final_output = gmdhelpers.select_mv(
            extracted_joined,
            ["ref_map_uuid", "ref_bsn_geoid", "distance_m"],
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