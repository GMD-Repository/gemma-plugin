__author__ = 'Geosptial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geosptial Management Division'

import os
import json
import subprocess
import pip
import importlib
import processing
from typing import Any, Dict, Optional

from PyQt5.QtCore import QVariant
from qgis.core import (
    NULL,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsFeatureSink,
    QgsGeometry,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingException,
)


def check_geometry_validity(geom: QgsGeometry) -> bool:
    """Recreates check_geometry_validity from R: checks if geometry is non-empty and valid."""
    if geom is None or geom.isEmpty():
        return False
    return geom.isGeosValid()


def filter_geometry_validity(source, feedback=None):
    """Filters features from layer/source that have valid, non-empty geometries."""
    valid_features = []
    for f in source.getFeatures():
        if feedback and feedback.isCanceled():
            break
        if check_geometry_validity(f.geometry()):
            valid_features.append(f)
    return valid_features


def add_count(features, source_fields, col_name, count_col="n"):
    """Recreates dplyr::add_count(col_name) by calculating counts and attaching field 'n'."""
    fields = QgsFields(source_fields)
    n_idx = fields.indexOf(count_col)
    if n_idx == -1:
        fields.append(QgsField(count_col, QVariant.Int))
        n_idx = fields.count() - 1

    col_field_name = col_name
    if col_field_name not in fields.names():
        for field in fields:
            if field.name().lower() == col_name.lower():
                col_field_name = field.name()
                break

    counts = {}
    for f in features:
        val = f.attribute(col_field_name)
        key = None if (val is NULL or val is None) else str(val)
        counts[key] = counts.get(key, 0) + 1

    counted_features = []
    for f in features:
        val = f.attribute(col_field_name)
        key = None if (val is NULL or val is None) else str(val)
        n_val = counts.get(key, 0)

        out_feat = QgsFeature(fields)
        out_feat.setGeometry(f.geometry())
        attrs = list(f.attributes())
        if len(attrs) < fields.count():
            attrs.append(n_val)
        else:
            attrs[n_idx] = n_val
        out_feat.setAttributes(attrs)
        counted_features.append(out_feat)

    return counted_features, fields


def arrange(features, col_name, ascending=True):
    """Recreates dplyr::arrange(col_name) on a list of QgsFeatures."""
    def sort_key(f):
        val = f.attribute(col_name)
        if val is NULL or val is None:
            return (1, "")
        return (0, str(val))

    return sorted(features, key=sort_key, reverse=not ascending)


def export_features_to_sink(alg, parameters, param_name, context, fields, wkb_type, crs, features, feedback=None):
    """Exports features to a QgsProcessingParameterFeatureSink and logs feature count to feedback."""
    (sink, dest_id) = alg.parameterAsSink(
        parameters,
        param_name,
        context,
        fields,
        wkb_type,
        crs,
    )
    if sink is None:
        raise QgsProcessingException(alg.invalidSinkError(parameters, param_name))

    feature_list = features.getFeatures() if hasattr(features, "getFeatures") else features

    count = 0
    for f in feature_list:
        if feedback and feedback.isCanceled():
            break
        sink.addFeature(f, QgsFeatureSink.FastInsert)
        count += 1

    if feedback:
        feedback.pushInfo(f"Result: {count} feature(s) written to output sink '{param_name}'.")

    return {param_name: dest_id}


def load_cbms_geojson(alg, parameters, param_name, context):
    """Loads and validates a CBMS GeoJSON vector layer or source from algorithm parameters."""
    input_layer_path = alg.parameterAsFile(parameters, param_name, context)
    vlayer = None

    if input_layer_path and os.path.exists(input_layer_path):
        vlayer = QgsVectorLayer(input_layer_path, "input_layer", "ogr")

    if not vlayer or not vlayer.isValid():
        # Fallback to source parameter if passed as layer object/identifier
        source = alg.parameterAsSource(parameters, param_name, context)
        if source is None and input_layer_path:
            raise QgsProcessingException(f"Could not load input GeoJSON file from path: '{input_layer_path}'")
    else:
        source = vlayer

    if source is None:
        raise QgsProcessingException(alg.invalidSourceError(parameters, param_name))

    return source


def load_cbms_json(alg, parameters, param_name, context, feedback=None):
    """Loads a JSON file from algorithm parameters and returns it as a non-spatial QgsVectorLayer table."""
    json_path = alg.parameterAsFile(parameters, param_name, context)
    if not json_path or not os.path.exists(json_path):
        if feedback:
            feedback.pushInfo(f"Warning: JSON file path not found: '{json_path}'")
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if feedback:
            feedback.pushInfo(f"Loaded JSON input data from: '{json_path}'")
    except Exception as e:
        if feedback:
            feedback.pushInfo(f"Warning: Failed to parse JSON file: {e}")
        return None

    # Extract records list
    records = []
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in ["records", "features", "data", "cover_page"]:
            if key in data and isinstance(data[key], list):
                records = data[key]
                break
        if not records:
            records = [data]

    table_layer = QgsVectorLayer("none", "cbms_json_table", "memory")
    dp = table_layer.dataProvider()

    fields = QgsFields()
    field_names = []

    # Inspect records to dynamically create fields
    for rec in records:
        if isinstance(rec, dict):
            props = rec.get("properties", rec) if isinstance(rec.get("properties"), dict) else rec
        else:
            props = {"value": rec}

        if isinstance(props, dict):
            for k, v in props.items():
                k_name = str(k).strip()
                if k_name and k_name not in field_names:
                    if isinstance(v, bool):
                        ftype = QVariant.Bool
                    elif isinstance(v, int):
                        ftype = QVariant.Int
                    elif isinstance(v, float):
                        ftype = QVariant.Double
                    else:
                        ftype = QVariant.String
                    fields.append(QgsField(k_name, ftype))
                    field_names.append(k_name)

    dp.addAttributes(fields)
    table_layer.updateFields()

    features = []
    for rec in records:
        if isinstance(rec, dict):
            props = rec.get("properties", rec) if isinstance(rec.get("properties"), dict) else rec
        else:
            props = {"value": rec}

        feat = QgsFeature(fields)

        if isinstance(props, dict):
            for fn in field_names:
                if fn in props:
                    val = props[fn]
                    feat.setAttribute(fn, val if val is not None else NULL)
                else:
                    feat.setAttribute(fn, NULL)

        features.append(feat)

    dp.addFeatures(features)
    return table_layer


def load_base_layer(alg, parameters, param_name, context, suffix="_bldg_point"):
    """Loads a reference sub-layer ending with suffix (default: '_bldg_point') from a BASE_LAYER GeoPackage parameter."""
    base_layer_path = alg.parameterAsFile(parameters, param_name, context)
    ref_bldg_point = None

    if base_layer_path and os.path.exists(base_layer_path):
        bldg_point_sublayer = None
        tmp_layer = QgsVectorLayer(base_layer_path, "tmp_gpkg", "ogr")
        if tmp_layer and tmp_layer.isValid():
            for sub_item in tmp_layer.dataProvider().subLayers():
                parts = sub_item.split("!!::!!") if "!!::!!" in sub_item else sub_item.split(":")
                for part in parts:
                    if part.endswith(suffix):
                        bldg_point_sublayer = part
                        break
                if bldg_point_sublayer:
                    break

        if bldg_point_sublayer:
            ref_bldg_point = QgsVectorLayer(
                f"{base_layer_path}|layername={bldg_point_sublayer}",
                bldg_point_sublayer,
                "ogr",
            )

    if not ref_bldg_point or not ref_bldg_point.isValid():
        source = alg.parameterAsSource(parameters, param_name, context)
        if source is not None:
            return source
        raise QgsProcessingException(
            f"Could not load reference building point layer ending with '{suffix}' from '{base_layer_path}'"
        )

    return ref_bldg_point


def install_package(package_name):
    try:
        importlib.import_module(package_name)
        print(f"✅ Importing '{package_name}' is successful!")
        return True
    except ImportError:
        print(f"⚠️ '{package_name}' not found. Attempting installation...")
        pip.main(["install", package_name])
        try:
            importlib.import_module(package_name)
            print(f"✅ Installation and import of '{package_name}' succeeded!")
            return True
        except ImportError:
            print(f"❌ Installation of '{package_name}' failed. Please install manually.")
            return False


def uninstall_package(package_name):
    pip.main(["uninstall", package_name])


def remove_layer_lengths(layer, context=None, feedback=None):
    field_mapping = []
    for f in layer.fields():
        field_mapping.append({
            'expression': f'"{f.name()}"',
            'length': 0,  # no limit
            'name': f.name(),
            'type': f.type()
        })
    return processing.run("native:refactorfields", {
        'INPUT': layer,
        'FIELDS_MAPPING': field_mapping,
        'OUTPUT': 'memory:'
    }, context=context, feedback=feedback)['OUTPUT']


def set_status_bar(self, status_bar):
    status_bar.setMinimum(0)
    status_bar.setMaximum(100)
    status_bar.setValue(0)
    status_bar.setFormat("Ready")
    self.status_bar = status_bar


def create_temporary_layer(
    features,
    fields=None,
    source_layer=None,
    wkb_type=None,
    crs=None,
    layer_name="temp_layer",
):
    """
    Creates an in-memory QgsVectorLayer from a list or iterable of QgsFeature.

    Can automatically infer geometry type, CRS, and fields from:
    1. An optional source_layer (e.g. geojson_data, GPKG layer)
    2. Explicit fields, wkb_type, or crs parameters
    3. The first feature in features if available
    4. Safe defaults (Point geometry, EPSG:4326)

    Usage examples:
        temp_layer = create_temporary_layer(invalid_features)
        temp_layer = create_temporary_layer(invalid_features, fields, geojson_data)
        temp_layer = create_temporary_layer(invalid_features, source_layer=geojson_data)
        temp_layer = create_temporary_layer(invalid_features, fields=fields)
    """
    if isinstance(features, QgsVectorLayer):
        return features

    # Handle flexible positional arguments:
    # e.g., create_temporary_layer(features, geojson_data)
    if fields is not None and hasattr(fields, "sourceCrs") and source_layer is None:
        source_layer = fields
        fields = None

    feat_list = list(features) if features is not None else []

    # Infer metadata from source_layer if provided
    if source_layer is not None:
        if wkb_type is None and hasattr(source_layer, "wkbType"):
            wkb_type = source_layer.wkbType()
        if crs is None and hasattr(source_layer, "sourceCrs"):
            crs = source_layer.sourceCrs()
        if fields is None and hasattr(source_layer, "fields"):
            fields = source_layer.fields()

    # Infer fields from first feature if still None
    if fields is None and feat_list:
        first_feat = feat_list[0]
        if hasattr(first_feat, "fields") and first_feat.fields() is not None:
            fields = first_feat.fields()

    # Infer geometry type from first feature if still None
    if wkb_type is None and feat_list:
        first_feat = feat_list[0]
        if hasattr(first_feat, "hasGeometry") and first_feat.hasGeometry() and first_feat.geometry():
            wkb_type = first_feat.geometry().wkbType()

    # Fallback geometry type to Point
    if wkb_type is None:
        wkb_type = QgsWkbTypes.Point

    # Resolve geometry string
    if isinstance(wkb_type, str):
        geom_type_str = wkb_type
    else:
        geom_type_str = QgsWkbTypes.displayString(wkb_type)

    # Resolve CRS string
    if crs is not None:
        crs_str = crs.authid() if hasattr(crs, "authid") else str(crs)
    else:
        crs_str = "EPSG:4326"

    uri = f"{geom_type_str}?crs={crs_str}"
    temp_layer = QgsVectorLayer(uri, layer_name, "memory")
    dp = temp_layer.dataProvider()

    if fields is not None:
        dp.addAttributes(fields)
        temp_layer.updateFields()

    if feat_list:
        dp.addFeatures(feat_list)

    return temp_layer


REF_SELECT_MV_COLS  = [
    "map_uuid",
    "bsn_geoid",
    "region_code",
    "province_code",
    "city_mun_code",
    "barangay_code",
    "ean",
    "bsn",
    "ea_geocode",
    "en_code",
]


def select_mv(layer, *extra_fields, context=None, feedback=None, base_fields=None):
    """
    Selects and retains specific columns from a layer using QGIS native:retainfields.

    Pre-selects standard CBMS columns by default:
        map_uuid, bsn_geoid, region_code, province_code, city_mun_code,
        barangay_code, ean, bsn, ea_geocode, en_code

    Appends any extra user-specified columns.

    Usage examples:
        # 1. Multiple additional columns
        final_output = select_mv(semi_final_output, ["ref_map_uuid", "ref_bsn_geoid"])

        # 2. Single additional column
        final_output = select_mv(semi_final_output, ["ref_bsn_geoid"])

        # 3. Default columns only (no extra columns)
        final_output = select_mv(semi_final_output, [])
        # or
        final_output = select_mv(semi_final_output)

    """
    if layer is None:
        return None

    initial_fields = list(base_fields) if base_fields is not None else list(REF_SELECT_MV_COLS )

    fields_to_add = []
    for arg in extra_fields:
        if isinstance(arg, (list, tuple, set)):
            fields_to_add.extend(list(arg))
        elif isinstance(arg, str):
            fields_to_add.append(arg)

    target_names = []
    for f in initial_fields + fields_to_add:
        if f and isinstance(f, str) and f not in target_names:
            target_names.append(f)

    existing_fields = {}
    if hasattr(layer, "fields") and layer.fields() is not None:
        for f in layer.fields():
            existing_fields[f.name().lower()] = f.name()

    fields_to_retain = []
    if existing_fields:
        for name in target_names:
            name_lower = name.lower()
            if name_lower in existing_fields:
                fields_to_retain.append(existing_fields[name_lower])
    else:
        fields_to_retain = target_names

    if not fields_to_retain:
        return layer

    return processing.run(
        "native:retainfields",
        {
            "INPUT": layer,
            "FIELDS": fields_to_retain,
            "OUTPUT": "memory:",
        },
        context=context,
        feedback=feedback,
    )["OUTPUT"]
