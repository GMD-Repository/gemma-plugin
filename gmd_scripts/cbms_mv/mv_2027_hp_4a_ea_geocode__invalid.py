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
    QgsCoordinateTransform,
    QgsSpatialIndex,
    QgsProviderRegistry,
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers


TARGET_FIELDS = ["sf_ea_geocode", "ref_ea_geocode"]

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
            "Value of the ea_geocode should be the same as the ean of its location\n"
        )

    def initAlgorithm(self, config: Optional[Dict[str, Any]] = None):

        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_DATA,
                "INPUT_DATA (.csv file)",
                behavior=QgsProcessingParameterFile.File,
                extension="csv",
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
        json_data = gmdhelpers.load_cbms_csv(self, parameters, self.INPUT_DATA, context, feedback)
        ref_ea = gmdhelpers.load_base_layer(self, parameters, self.BASE_LAYER, context, suffix="_ea")

        src_crs = geojson_data.sourceCrs()
        if not src_crs.isValid():
            src_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        ref_crs = ref_ea.sourceCrs()
        coord_transform = None
        if ref_crs.isValid() and ref_crs != src_crs:
            coord_transform = QgsCoordinateTransform(ref_crs, src_crs, context.transformContext())

        ref_fields_lower = {fld.name().lower(): fld.name() for fld in ref_ea.fields()}
        ref_ea_field = ref_fields_lower.get("ref_ea_geocode") or ref_fields_lower.get("ea_geocode")
        if not ref_ea_field:
            raise QgsProcessingException("Reference EA layer is missing 'ref_ea_geocode' / 'ea_geocode' field.")

        sf_fields_lower = {fld.name().lower(): fld.name() for fld in geojson_data.fields()}
        sf_ea_field = sf_fields_lower.get("sf_ea_geocode") or sf_fields_lower.get("ea_geocode")

        # 1. Build spatial index of reference EA polygons (reprojected to point layer CRS if needed)
        spatial_index = QgsSpatialIndex()
        ref_polygons: Dict[int, tuple] = {}
        for idx_id, feat in enumerate(ref_ea.getFeatures(), start=1):
            if feedback and feedback.isCanceled():
                break
            ea_code = feat.attribute(ref_ea_field)
            if ea_code is None or ea_code == NULL:
                continue
            ea_str = str(ea_code).strip()
            if not ea_str:
                continue
            geom = QgsGeometry(feat.geometry())
            if not geom or geom.isEmpty():
                continue
            if coord_transform is not None:
                geom.transform(coord_transform)

            idx_feat = QgsFeature(idx_id)
            idx_feat.setGeometry(geom)
            spatial_index.addFeature(idx_feat)
            ref_polygons[idx_id] = (ea_str, geom)

        # 2. Build output fields (source fields + ref_ea_geocode)
        source_fields = geojson_data.fields()
        out_fields = QgsFields(source_fields)

        if out_fields.indexOf("ref_ea_geocode") == -1:
            out_fields.append(QgsField("ref_ea_geocode", QVariant.String))

        ref_ea_geocode_idx = out_fields.indexOf("ref_ea_geocode")

        invalid_features = []

        # 3. Find points located inside a reference EA polygon with a different ea_geocode
        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break
            point_geom = f.geometry()
            if not point_geom or point_geom.isEmpty():
                continue

            sf_ea_val = f.attribute(sf_ea_field) if sf_ea_field else None
            sf_ea_str = "" if (sf_ea_val is None or sf_ea_val == NULL) else str(sf_ea_val).strip()

            candidate_ids = spatial_index.intersects(point_geom.boundingBox())
            if not candidate_ids:
                continue

            containing_codes: List[str] = []
            intersecting_codes: List[str] = []
            for cid in candidate_ids:
                ref_code, poly_geom = ref_polygons[cid]
                if poly_geom.contains(point_geom):
                    if ref_code not in containing_codes:
                        containing_codes.append(ref_code)
                    if ref_code not in intersecting_codes:
                        intersecting_codes.append(ref_code)
                elif poly_geom.intersects(point_geom):
                    if ref_code not in intersecting_codes:
                        intersecting_codes.append(ref_code)

            if not intersecting_codes:
                continue

            # Valid if point lies inside (or on the boundary of) the EA polygon matching its sf_ea_geocode
            if sf_ea_str and sf_ea_str in intersecting_codes:
                continue

            matched_ref_ea = containing_codes[0] if containing_codes else intersecting_codes[0]

            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(point_geom)
            attrs = list(f.attributes())
            while len(attrs) < out_fields.count():
                attrs.append(NULL)
            attrs[ref_ea_geocode_idx] = matched_ref_ea
            out_feat.setAttributes(attrs)
            invalid_features.append(out_feat)

        # 4. Create temporary memory layer for invalid features
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