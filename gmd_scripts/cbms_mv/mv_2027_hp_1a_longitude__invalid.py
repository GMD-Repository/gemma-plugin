from multiprocessing import context
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
    QgsProviderRegistry,
    QgsDistanceArea,
    QgsPointXY,
)
from PyQt5.QtGui import QIcon
from .. import gmdhelpers


TARGET_FIELDS = ["sf_longitude", "sf_latitude", "df_x_current", "df_y_current", "sf_map_uuid", "df_map_uuid", "ref_map_uuid"]
SUGGESTED_FIX = ["copy_geometry_to_coordinates", "update_datafiles_coordinates"]

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
            "List of datafiles and geotagged points with the same coordinates but different map_uuid\n \n"
            "Datafiles and geotagged points with the same coordinates should have the same map_uuid\n"
        )

    def initAlgorithm(self, config=None):

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
                "mv_2027_hp_1a_longitude__invalid",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

    def processAlgorithm(self, parameters, context, feedback):

        geojson_data = gmdhelpers.load_cbms_geojson(self, parameters, self.INPUT_LAYER, context)
        json_data = gmdhelpers.load_cbms_csv(self, parameters, self.INPUT_DATA, context, feedback)
        ref_bldg_point = gmdhelpers.load_base_layer(self, parameters, self.BASE_LAYER, context)

        # 1. Add rounded coordinate join key (coord_key) to geojson_data using QGIS Field Calculator
        geojson_with_key = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": geojson_data,
                "FIELD_NAME": "coord_key",
                "FIELD_TYPE": 2,  # String
                "FIELD_LENGTH": 100,
                #"FORMULA": 'to_string(round($x, 7)) + \'_\' + to_string(round($y, 7))',
                "FORMULA": r"""
                    if(
                        "sf_longitude" IS NULL OR "sf_longitude" = '' OR "sf_latitude" IS NULL OR "sf_latitude" = '',
                        'sf is null',
                        to_string(round(to_real("sf_longitude"), 7)) + '\\' + to_string(round(to_real("sf_latitude"), 7))
                    )
                """,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 2. Add rounded coordinate join key (coord_key) to json_data table using QGIS Field Calculator (df_x_current, df_y_current)
        json_with_key = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": json_data,
                "FIELD_NAME": "coord_key",
                "FIELD_TYPE": 2,  # String
                "FIELD_LENGTH": 100,
                "FORMULA": r"""
                    if(
                        "df_x_current" IS NULL OR "df_x_current" = '' OR "df_y_current" IS NULL OR "df_y_current" = '',
                        'df is null',
                        to_string(round(to_real("df_x_current"), 7)) + '\\' + to_string(round(to_real("df_y_current"), 7))
                    )
                """,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 3. Join feature attributes using QGIS native Join Attributes Table on coord_key
        joined_layer = processing.run(
            "native:joinattributestable",
            {
                "INPUT": json_with_key,
                "FIELD": "coord_key",
                "INPUT_2": geojson_with_key,
                "FIELD_2": "coord_key",
                "FIELDS_TO_COPY": [],
                "METHOD": 1,
                "DISCARD_NONMATCHING": False,
                "PREFIX": "",
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 4. Extract mismatched features where geotagged map_uuid != reference JSON map_uuid
        mismatched_layer = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": joined_layer,
                "EXPRESSION": '"df_map_uuid" != "sf_map_uuid"',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

        # 5. Match reference building points (*_bldg_point in BASE_LAYER) by coordinates (5 decimal places / <= 1e-5)
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        ref_xform = None
        if ref_bldg_point and ref_bldg_point.isValid():
            ref_crs = ref_bldg_point.sourceCrs()
            if ref_crs.isValid() and ref_crs != wgs84_crs:
                ref_xform = QgsCoordinateTransform(ref_crs, wgs84_crs, context.transformContext())

        ref_buckets: Dict[tuple, List[tuple]] = {}
        if ref_bldg_point and ref_bldg_point.isValid():
            ref_flds_lower = {fld.name().lower(): fld.name() for fld in ref_bldg_point.fields()}
            ref_uuid_col = (
                ref_flds_lower.get("ref_map_uuid")
                or ref_flds_lower.get("map_uuid")
                or ref_flds_lower.get("uuid")
            )
            ref_lon_col = ref_flds_lower.get("ref_longitude") or ref_flds_lower.get("longitude")
            ref_lat_col = ref_flds_lower.get("ref_latitude") or ref_flds_lower.get("latitude")

            if ref_uuid_col:
                for rf in ref_bldg_point.getFeatures():
                    if feedback and feedback.isCanceled():
                        break
                    ru = rf.attribute(ref_uuid_col)
                    if ru is None or ru == NULL:
                        continue
                    ru_str = str(ru).strip()
                    if not ru_str or ru_str.lower() in ("null", "none"):
                        continue

                    rx, ry = None, None
                    geom = rf.geometry()
                    if geom and not geom.isEmpty():
                        try:
                            g_copy = QgsGeometry(geom)
                            if ref_xform is not None:
                                g_copy.transform(ref_xform)
                            pt = g_copy.asMultiPoint()[0] if g_copy.isMultipart() else g_copy.asPoint()
                            rx, ry = float(pt.x()), float(pt.y())
                        except Exception:
                            rx, ry = None, None
                    if (rx is None or ry is None) and ref_lon_col and ref_lat_col:
                        try:
                            lv, bv = rf.attribute(ref_lon_col), rf.attribute(ref_lat_col)
                            if lv is not None and lv != NULL and bv is not None and bv != NULL:
                                rx, ry = float(str(lv).strip()), float(str(bv).strip())
                        except (ValueError, TypeError):
                            rx, ry = None, None

                    if rx is not None and ry is not None:
                        bkey = (round(rx, 4), round(ry, 4))
                        ref_buckets.setdefault(bkey, []).append((rx, ry, ru_str))

        def _find_ref_map_uuid(lon_val: Any, lat_val: Any, sf_u: str, df_u: str) -> Any:
            if not ref_buckets:
                return NULL
            try:
                fx = float(str(lon_val).strip())
                fy = float(str(lat_val).strip())
            except (ValueError, TypeError):
                return NULL
            bx, by = round(fx, 4), round(fy, 4)
            tol = 1e-5 + 1e-9
            best_match = None
            best_score = None
            for dx in (-0.0001, 0.0, 0.0001):
                for dy in (-0.0001, 0.0, 0.0001):
                    cand_list = ref_buckets.get((round(bx + dx, 4), round(by + dy, 4)))
                    if not cand_list:
                        continue
                    for rx, ry, ru_str in cand_list:
                        if abs(rx - fx) <= tol and abs(ry - fy) <= tol:
                            dist_sq = (rx - fx) ** 2 + (ry - fy) ** 2
                            ru_low = ru_str.lower()
                            uuid_hit = 0 if (ru_low == sf_u.lower() or ru_low == df_u.lower()) else 1
                            score = (uuid_hit, dist_sq)
                            if best_score is None or score < best_score:
                                best_score = score
                                best_match = ru_str
            return best_match if best_match is not None else NULL

        out_fields = QgsFields(mismatched_layer.fields())
        if out_fields.indexOf("ref_map_uuid") == -1:
            out_fields.append(QgsField("ref_map_uuid", QVariant.String))
        ref_uuid_idx = out_fields.indexOf("ref_map_uuid")

        m_flds_lower = {fld.name().lower(): fld.name() for fld in mismatched_layer.fields()}
        sf_lon_fld = m_flds_lower.get("sf_longitude") or m_flds_lower.get("df_x_current")
        sf_lat_fld = m_flds_lower.get("sf_latitude") or m_flds_lower.get("df_y_current")
        sf_u_fld = m_flds_lower.get("sf_map_uuid")
        df_u_fld = m_flds_lower.get("df_map_uuid")

        enriched_feats: List[QgsFeature] = []
        for f in mismatched_layer.getFeatures():
            if feedback and feedback.isCanceled():
                break
            lon_v = f.attribute(sf_lon_fld) if sf_lon_fld else None
            lat_v = f.attribute(sf_lat_fld) if sf_lat_fld else None
            sf_u_v = f.attribute(sf_u_fld) if sf_u_fld else ""
            df_u_v = f.attribute(df_u_fld) if df_u_fld else ""
            sf_u_s = "" if (sf_u_v is None or sf_u_v == NULL) else str(sf_u_v).strip()
            df_u_s = "" if (df_u_v is None or df_u_v == NULL) else str(df_u_v).strip()

            matched_ref_uuid = _find_ref_map_uuid(lon_v, lat_v, sf_u_s, df_u_s)

            out_f = QgsFeature(out_fields)
            if f.hasGeometry():
                out_f.setGeometry(f.geometry())
            attrs = list(f.attributes())
            while len(attrs) < out_fields.count():
                attrs.append(NULL)
            attrs[ref_uuid_idx] = matched_ref_uuid
            out_f.setAttributes(attrs)
            enriched_feats.append(out_f)

        enriched_layer = gmdhelpers.create_temporary_layer(
            enriched_feats,
            fields=out_fields,
            source_layer=mismatched_layer,
        )

        # 6. Select & organize output columns using select_mv
        final_output = gmdhelpers.select_mv(
            enriched_layer,
            ["df_fid", "df_x_current", "df_y_current", "df_map_uuid", "sf_map_uuid", "ref_map_uuid", "sf_longitude", "sf_latitude"],
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