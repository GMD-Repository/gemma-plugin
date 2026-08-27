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



class mv_2027_hp_4b_bsn_geoid__missing(QgsProcessingAlgorithm):

    INPUT_DATA = "INPUT_DATA"
    INPUT_LAYER = "INPUT_LAYER"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mv_2027_hp_4b_bsn_geoid__missing"

    def displayName(self) -> str:
        return "mv_2027_hp_4b_bsn_geoid__missing"

    def group(self) -> str:
        return "2027 CBMS"

    def groupId(self) -> str:
        return "cbms_mv"

    def shortHelpString(self) -> str:
        return (
            "List of geotagged points with different Geocodes. \n \n"
            "Values on the Geocode column must be identical to the substring of the GeoID.\n"
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
                "mv_2027_hp_4b_bsn_geoid__missing",
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

        def ensure_field(flds, name, ftype=QVariant.String):
            if flds.indexOf(name) == -1:
                flds.append(QgsField(name, ftype))

        ensure_field(fields, "geocode", QVariant.String)
        ensure_field(fields, "geoid", QVariant.String)
        ensure_field(fields, "geocode_from_geoid", QVariant.String)

        # Resolve field names case-insensitively
        def resolve_field_name(field_list, target_name):
            for fld in field_list:
                if fld.name().lower() == target_name.lower():
                    return fld.name()
            return None

        geocode_field = resolve_field_name(source_fields, "geocode")
        geoid_field = resolve_field_name(source_fields, "geoid")

        # Try alternate field names if not found
        if geocode_field is None:
            geocode_field = resolve_field_name(source_fields, "bsn")
        if geoid_field is None:
            geoid_field = resolve_field_name(source_fields, "geo_id")

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

            # Read geocode and geoid
            raw_geocode = f.attribute(geocode_field) if geocode_field else None
            raw_geoid = f.attribute(geoid_field) if geoid_field else None

            # Disregard NULL values
            if is_null(raw_geocode) or is_null(raw_geoid):
                continue

            geocode_str = str(raw_geocode).strip()
            geoid_str = str(raw_geoid).strip()

            if not geocode_str or not geoid_str:
                continue

            # Extract the geocode substring from geoid (first len(geocode) characters)
            geocode_from_geoid = geoid_str[:len(geocode_str)]

            # Flag if geocode does not match the leading substring of geoid
            if geocode_str != geocode_from_geoid:
                geom = f.geometry()
                out_feat = QgsFeature(fields)
                if geom is not None:
                    out_feat.setGeometry(geom)

                # Copy existing attributes
                for i in range(source_fields.count()):
                    out_feat.setAttribute(source_fields.at(i).name(), f.attribute(i))

                out_feat.setAttribute("geocode", geocode_str)
                out_feat.setAttribute("geoid", geoid_str)
                out_feat.setAttribute("geocode_from_geoid", geocode_from_geoid)

                invalid_features.append(out_feat)

        feedback.pushInfo(
            f"Results: {len(invalid_features)} features with geocode/geoid mismatch."
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
