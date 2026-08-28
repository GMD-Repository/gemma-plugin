import os
import json
from typing import Any, Optional, Dict, List, Set

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


class mv_2027_hp_4a_map_uuid__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4a_map_uuid__missing"

    def displayName(self) -> str:
        return "mv_2027_hp_4a_map_uuid__missing"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points without CBMS Form 2 datafile.\n\n"
            "Every geotagged point (except for BSN 00000) should have a counterpart datafile with the same GeoID / map_uuid.\n"
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
                "mv_2027_hp_4a_map_uuid__missing",
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

        def is_na(val: Any) -> bool:
            if val is None or val == NULL:
                return True
            if isinstance(val, QVariant) and val.isNull():
                return True
            return str(val).strip().lower() in ("", "null", "none", "nan", "na")

        # ---------------------------------------------------------------------
        # 1. Extract valid map_uuid values from the Form 2 JSON dataset (cover page)
        #    where case_id is present and not NA.
        # ---------------------------------------------------------------------
        valid_form2_map_uuids: Set[str] = set()

        def extract_records(data: Any) -> List[Dict[str, Any]]:
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            elif isinstance(data, dict):
                # If wrapped under standard keys (e.g. 'cover_page', 'cases', etc.)
                for key in ("cover_page", "cases", "records", "data", "features"):
                    if key in data and isinstance(data[key], list):
                        return [item for item in data[key] if isinstance(item, dict)]
                # If dictionary of objects keyed by id
                return [v for v in data.values() if isinstance(v, dict)]
            return []

        form2_records = extract_records(json_data)

        for rec in form2_records:
            # Check map_uuid and case_id
            m_uuid = rec.get("map_uuid") or rec.get("MAP_UUID")
            c_id = rec.get("case_id") or rec.get("CASE_ID")

            if not is_na(m_uuid) and not is_na(c_id):
                valid_form2_map_uuids.add(str(m_uuid).strip().lower())

        # ---------------------------------------------------------------------
        # 2. Prepare Output Fields
        # ---------------------------------------------------------------------
        src_fields = geojson_data.fields()
        out_fields = QgsFields(src_fields)

        # Ensure case_id, longitude_df, and latitude_df fields exist in output schema
        field_names_lower = [f.name().lower() for f in src_fields]

        if "case_id" not in field_names_lower:
            out_fields.append(QgsField("case_id", QVariant.String))
        if "longitude_df" not in field_names_lower:
            out_fields.append(QgsField("longitude_df", QVariant.Double))
        if "latitude_df" not in field_names_lower:
            out_fields.append(QgsField("latitude_df", QVariant.Double))

        # Helper to find attribute case-insensitively
        def get_attr_by_names(feat: QgsFeature, possible_names: List[str]) -> Any:
            for name in possible_names:
                for f in src_fields:
                    if f.name().lower() == name.lower():
                        return feat.attribute(f.name())
            return NULL

        # ---------------------------------------------------------------------
        # 3. Find Geotagged Points with Missing Form 2 Counterpart
        # ---------------------------------------------------------------------
        missing_features: List[QgsFeature] = []

        for feat in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break

            map_uuid_val = get_attr_by_names(feat, ["map_uuid"])
            bsn_geoid_val = get_attr_by_names(feat, ["bsn_geoid", "cbms_geoid", "geoid"])

            # Check if map_uuid is missing or does not match any valid Form 2 record
            clean_uuid = str(map_uuid_val).strip().lower() if not is_na(map_uuid_val) else ""
            is_missing_match = not clean_uuid or clean_uuid not in valid_form2_map_uuids

            if is_missing_match:
                # Generate placeholder case_id: paste0(bsn_geoid, 'xxxxxxxxxx')
                bsn_prefix = str(bsn_geoid_val).strip() if not is_na(bsn_geoid_val) else ""
                generated_case_id = f"{bsn_prefix}xxxxxxxxxx" if bsn_prefix else "xxxxxxxxxx"

                out_feat = QgsFeature(out_fields)
                out_feat.setGeometry(feat.geometry())

                # Copy existing attributes
                for field in src_fields:
                    out_feat.setAttribute(field.name(), feat.attribute(field.name()))

                # Set generated fields
                out_feat.setAttribute("case_id", generated_case_id)
                out_feat.setAttribute("longitude_df", NULL)
                out_feat.setAttribute("latitude_df", NULL)

                missing_features.append(out_feat)

        # ---------------------------------------------------------------------
        # 4. Export to Sink
        # ---------------------------------------------------------------------
        return gmdhelpers.export_features_to_sink(
            self,
            parameters,
            self.OUTPUT,
            context,
            out_fields,
            geojson_data.wkbType(),
            geojson_data.sourceCrs(),
            missing_features,
            feedback,
        )

    def createInstance(self):
        return self.__class__()
