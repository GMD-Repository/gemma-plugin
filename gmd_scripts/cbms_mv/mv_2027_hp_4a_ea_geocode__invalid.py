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
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers


class mv_2027_hp_4a_ea_geocode__invalid(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    BASE_LAYER = "BASE_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4a_ea_geocode__invalid"

    def displayName(self) -> str:
        return "mv_2027_hp_4a_ea_geocode__invalid"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points whose locations are not in the EA of its ea_geocode \n \n "
            "Value of the ea_geocode should be the same as the ean of its location.\n"
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
                "mv_2027_hp_4a_ea_geocode__invalid",
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
        ref_ea = gmdhelpers.load_base_layer(self, parameters, self.BASE_LAYER, context, suffix="_ea")

        # 1. Map ea_geocode to list of reference EA polygon geometries
        ref_ea_map = {}
        for feat in ref_ea.getFeatures():
            if feedback and feedback.isCanceled():
                break
            ea_code = feat.attribute("ea_geocode")
            if ea_code is not None and ea_code != NULL:
                ea_str = str(ea_code)
                geom = feat.geometry()
                if ea_str not in ref_ea_map:
                    ref_ea_map[ea_str] = []
                if geom and not geom.isEmpty():
                    ref_ea_map[ea_str].append(geom)

        # 2. Build output fields (source fields + ref_ea_geocode)
        source_fields = geojson_data.fields()
        out_fields = QgsFields(source_fields)

        if out_fields.indexOf("ref_ea_geocode") == -1:
            out_fields.append(QgsField("ref_ea_geocode", QVariant.String))

        ref_ea_geocode_idx = out_fields.indexOf("ref_ea_geocode")

        invalid_features = []

        # 3. Find features matching ea_geocode whose geometry is NOT within the reference EA polygon
        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break
            ea_val = f.attribute("ea_geocode")
            if ea_val is None or ea_val == NULL:
                continue

            ea_str = str(ea_val)
            if ea_str in ref_ea_map:
                point_geom = f.geometry()
                if point_geom and not point_geom.isEmpty():
                    is_within = False
                    for poly_geom in ref_ea_map[ea_str]:
                        if poly_geom.contains(point_geom):
                            is_within = True
                            break

                    if not is_within:
                        out_feat = QgsFeature(out_fields)
                        out_feat.setGeometry(point_geom)
                        attrs = list(f.attributes())
                        while len(attrs) < out_fields.count():
                            attrs.append(NULL)
                        attrs[ref_ea_geocode_idx] = ea_str
                        out_feat.setAttributes(attrs)
                        invalid_features.append(out_feat)

        # 4. Create temporary memory layer for invalid features
        crs = geojson_data.sourceCrs()
        if not crs.isValid():
            crs = QgsCoordinateReferenceSystem("EPSG:4326")

        temp_layer = gmdhelpers.create_temporary_layer(
            invalid_features,
            fields=out_fields,
            source_layer=geojson_data,
        )

        # 5. Select & organize columns using select_mv
        final_output = gmdhelpers.select_mv(
            temp_layer,
            ["ref_ea_geocode"],
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