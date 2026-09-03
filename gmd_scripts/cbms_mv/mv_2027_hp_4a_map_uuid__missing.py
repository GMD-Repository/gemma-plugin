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

    def name(self):
        return "mv_2027_hp_4a_map_uuid__missing"

    def displayName(self):
        return "mv_2027_hp_4a_map_uuid__missing"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points without CBMS Form 2 datafile. \n \n"
            "Every geotagged point (except for BSN 00000) should have a counterpart datafile with the same map_uuid.\n"
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

        source_fields = geojson_data.fields()
        fields = QgsFields(source_fields)
        if fields.indexOf("status") == -1:
            fields.append(QgsField("status", QVariant.String))

        def clean(v: Any) -> str:
            if v is None or v == NULL or (isinstance(v, QVariant) and v.isNull()):
                return ""
            s = str(v).strip()
            return "" if s.lower() in ("null", "none", "na", "n/a", "nan") else s

        # Index Form 2 JSON records by 19-digit bsn_geoid:
        # province (3) + city_mun (2) + barangay (3) + ean (6) + bsn (5)
        form2_by_geoid: Dict[str, Set[str]] = {}
        if json_data:
            records = json_data if isinstance(json_data, list) else (
                json_data.get("records") or json_data.get("features") or json_data.get("data") or [json_data]
            )
            for rec in records:
                if feedback and feedback.isCanceled():
                    break
                p = rec.get("properties", rec) if isinstance(rec, dict) else {}
                if not isinstance(p, dict):
                    continue

                gid = clean(p.get("bsn_geoid"))
                if not gid:
                    try:
                        prov = int(p.get("province_code", 0))
                        mun = int(p.get("city_mun_code", 0))
                        bgy = int(p.get("barangay_code", 0))
                        ean = int(p.get("ean", 0))
                        bsn = int(p.get("bsn_code", p.get("bsn", 0)))
                        gid = f"{prov:03d}{mun:02d}{bgy:03d}{ean:06d}{bsn:05d}"
                    except (ValueError, TypeError):
                        gid = ""

                uuid = clean(p.get("map_uuid"))
                if gid:
                    entry = form2_by_geoid.setdefault(gid, set())
                    if uuid:
                        entry.add(uuid)

        invalid_features = []

        for f in geojson_data.getFeatures():
            if feedback and feedback.isCanceled():
                break

            bsn = clean(f["bsn"])
            geoid = clean(f["bsn_geoid"])

            # Skip BSN 0 / 00000 points
            if bsn in ("0", "00", "000", "0000", "00000") or geoid.endswith("00000"):
                continue

            uuid = clean(f["map_uuid"])
            status = None

            if not uuid:
                status = "Missing/NULL Map UUID in GeoJSON"
            elif json_data is not None:
                if geoid in form2_by_geoid:
                    uuids = form2_by_geoid[geoid]
                    if not uuids:
                        status = "Datafile exists but missing map_uuid"
                    elif uuid not in uuids:
                        status = "Map UUID mismatch with Form 2 Datafile"
                else:
                    status = "Missing Form 2 Datafile Record"

            if status:
                out_feat = QgsFeature(fields)
                if f.geometry() is not None:
                    out_feat.setGeometry(f.geometry())
                out_feat.setAttributes(list(f.attributes()) + [status])
                invalid_features.append(out_feat)

        feedback.pushInfo(f"Results: {len(invalid_features)} flagged features.")

        # Create in-memory temp_layer from flagged features
        geom_type = QgsWkbTypes.displayString(geojson_data.wkbType())
        crs_authid = geojson_data.sourceCrs().authid()
        temp_layer = QgsVectorLayer(f"{geom_type}?crs={crs_authid}", "temp_layer", "memory")
        temp_layer.dataProvider().addAttributes(fields)
        temp_layer.updateFields()
        temp_layer.dataProvider().addFeatures(invalid_features)

        # Select & organize columns using select_mv
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
