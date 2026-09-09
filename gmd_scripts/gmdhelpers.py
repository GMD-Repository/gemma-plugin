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
    QgsProject,
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


def add_prefix_to_layer_fields(layer, prefix="", context=None, feedback=None):
    """
    Renames all attribute fields in a layer or source by prepending prefix (e.g. 'sf_', 'ref_', 'df_').
    Ensures '{prefix}fid' is present as the first attribute (using $id if 'fid' was not an explicit attribute).
    Returns a new memory QgsVectorLayer with renamed fields and unchanged geometry/CRS.
    """
    if not layer or not prefix:
        return layer

    fields = layer.fields()
    if fields.count() > 0 and all(f.name().startswith(prefix) for f in fields) and fields[0].name() == f"{prefix}fid":
        return layer

    fid_col = None
    for fld in fields:
        if fld.name().lower() in ("fid", f"{prefix}fid".lower()):
            fid_col = fld.name()
            break

    field_mapping = []
    # Guarantee {prefix}fid is the first field in the refactored layer, always strictly enforced as $id.
    # This prevents duplicate or NULL fid values in the source dataset from corrupting primary key resolution.
    field_mapping.append({
        "expression": "$id",
        "length": 0,
        "name": f"{prefix}fid",
        "precision": 0,
        "type": QVariant.LongLong,
    })

    for f in fields:
        if f.name() == fid_col:
            continue
        old_name = f.name()
        new_name = old_name if old_name.startswith(prefix) else f"{prefix}{old_name}"
        
        # Convert null or empty values in x_current and y_current to 0
        if new_name.lower().endswith(("_x_current", "_y_current")) or old_name.lower().endswith(("_x_current", "_y_current")):
            expr = f'coalesce(try(to_real("{old_name}")), 0)'
        else:
            expr = f'"{old_name}"'

        field_mapping.append({
            "expression": expr,
            "length": f.length(),
            "name": new_name,
            "precision": f.precision(),
            "type": f.type(),
        })

    return processing.run(
        "native:refactorfields",
        {
            "INPUT": layer,
            "FIELDS_MAPPING": field_mapping,
            "OUTPUT": "memory:",
        },
        context=context,
        feedback=feedback,
    )["OUTPUT"]


def load_cbms_geojson(alg, parameters, param_name, context, feedback=None, prefix="sf_"):
    """Loads and validates a CBMS GeoJSON vector layer or source from algorithm parameters.
    Automatically prefixes all attribute fields with prefix (default: 'sf_') and ensures 'sf_fid' is present.
    Filters out features marked with status == 'deleted'.
    """
    if isinstance(feedback, str):
        prefix = feedback
        feedback = None

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

    if prefix:
        source = add_prefix_to_layer_fields(source, prefix=prefix, context=context, feedback=feedback)

    # Filter out features marked with status == 'deleted' if status column exists
    status_field = None
    for fld in source.fields():
        name_lower = fld.name().lower()
        if name_lower in ("status", f"{prefix}status".lower()):
            status_field = fld.name()
            break

    if status_field:
        source = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": source,
                "EXPRESSION": f'coalesce(lower("{status_field}"), \'\') != \'deleted\'',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

    return source


def load_cbms_csv(alg, parameters, param_name, context, feedback=None, prefix="df_"):
    """Loads and validates a CBMS CSV table from algorithm parameters.
    Automatically prefixes all attribute fields with prefix (default: 'df_') and ensures 'df_fid' is present.
    Filters out rows marked with status == 'deleted'.
    """
    csv_path = alg.parameterAsFile(parameters, param_name, context)
    vlayer = None

    if csv_path and os.path.exists(csv_path):
        vlayer = QgsVectorLayer(csv_path, "input_csv_table", "ogr")

    if not vlayer or not vlayer.isValid():
        # Fallback to source parameter if passed as layer object/identifier
        source = alg.parameterAsSource(parameters, param_name, context)
        if source is None:
            if csv_path:
                raise QgsProcessingException(f"Could not load input CSV file from path: '{csv_path}'")
            raise QgsProcessingException(alg.invalidSourceError(parameters, param_name))
    else:
        source = vlayer

    if source is None:
        raise QgsProcessingException(alg.invalidSourceError(parameters, param_name))

    if prefix:
        source = add_prefix_to_layer_fields(source, prefix=prefix, context=context, feedback=feedback)

    # Filter out rows marked with status == 'deleted' if status column exists
    status_field = None
    for fld in source.fields():
        name_lower = fld.name().lower()
        if name_lower in ("status", f"{prefix}status".lower()):
            status_field = fld.name()
            break

    if status_field:
        source = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": source,
                "EXPRESSION": f'coalesce(lower("{status_field}"), \'\') != \'deleted\'',
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
        )["OUTPUT"]

    return source


def load_cbms_json(alg, parameters, param_name, context, feedback=None, prefix="df_"):
    """Loads a JSON file from algorithm parameters and returns it as a non-spatial QgsVectorLayer table.
    Automatically prefixes all columns with prefix (default: 'df_') and ensures 'df_fid' is present.
    """
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
    raw_keys_map = {}

    # Ensure prefix + "fid" exists as the first field
    fid_field_name = f"{prefix}fid" if prefix else "fid"
    fields.append(QgsField(fid_field_name, QVariant.Int))
    field_names.append(fid_field_name)
    raw_keys_map[fid_field_name] = "fid"

    # Inspect records to dynamically create fields with prefix
    for rec in records:
        if isinstance(rec, dict):
            props = rec.get("properties", rec) if isinstance(rec.get("properties"), dict) else rec
        else:
            props = {"value": rec}

        if isinstance(props, dict):
            for k, v in props.items():
                k_name = str(k).strip()
                if not k_name:
                    continue
                prefixed_k = k_name if (not prefix or k_name.startswith(prefix)) else f"{prefix}{k_name}"
                if prefixed_k not in field_names:
                    if isinstance(v, bool):
                        ftype = QVariant.Bool
                    elif isinstance(v, int):
                        ftype = QVariant.Int
                    elif isinstance(v, float):
                        ftype = QVariant.Double
                    else:
                        ftype = QVariant.String
                    fields.append(QgsField(prefixed_k, ftype))
                    field_names.append(prefixed_k)
                    raw_keys_map[prefixed_k] = k_name

    dp.addAttributes(fields)
    table_layer.updateFields()

    features = []
    has_fid_in_props = False
    for rec in records:
        props = rec.get("properties", rec) if isinstance(rec, dict) else {}
        if isinstance(props, dict) and any(str(k).strip().lower() == "fid" for k in props.keys()):
            has_fid_in_props = True
            break

    for idx, rec in enumerate(records):
        if isinstance(rec, dict):
            props = rec.get("properties", rec) if isinstance(rec.get("properties"), dict) else rec
        else:
            props = {"value": rec}

        feat = QgsFeature(fields)

        if isinstance(props, dict):
            props_lower = {str(k).strip().lower(): v for k, v in props.items()}
            for fn in field_names:
                orig_k = raw_keys_map.get(fn)
                if orig_k and orig_k in props:
                    val = props[orig_k]
                    feat.setAttribute(fn, val if val is not None else NULL)
                elif orig_k and orig_k.lower() in props_lower:
                    val = props_lower[orig_k.lower()]
                    feat.setAttribute(fn, val if val is not None else NULL)
                elif fn == fid_field_name and not has_fid_in_props:
                    feat.setAttribute(fn, idx + 1)
                else:
                    feat.setAttribute(fn, NULL)
        else:
            if not has_fid_in_props:
                feat.setAttribute(fid_field_name, idx + 1)

        features.append(feat)

    dp.addFeatures(features)
    return table_layer


def load_base_layer(alg, parameters, param_name, context, suffix="_bldg_point", prefix="ref_"):
    """Loads a reference sub-layer ending with suffix (default: '_bldg_point') from a BASE_LAYER GeoPackage parameter.
    Automatically prefixes all attribute fields with prefix (default: 'ref_') and ensures 'ref_fid' is present.
    """
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
            if prefix:
                source = add_prefix_to_layer_fields(source, prefix=prefix, context=context)
            return source
        raise QgsProcessingException(
            f"Could not load reference building point layer ending with '{suffix}' from '{base_layer_path}'"
        )

    if prefix:
        ref_bldg_point = add_prefix_to_layer_fields(ref_bldg_point, prefix=prefix, context=context)

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
    "sf_fid",
    "sf_map_uuid",
    "sf_bsn_geoid",
    "sf_region_code",
    "sf_province_code",
    "sf_city_mun_code",
    "sf_barangay_code",
    "sf_ean",
    "sf_bsn",
    "sf_ea_geocode",
    "sf_en_code",
    "sf_remarks"
]


def select_mv(layer, *extra_fields, context=None, feedback=None, base_fields=None):
    """
    Selects and retains specific columns from a layer using QGIS native:retainfields.

    Pre-selects standard CBMS columns by default (with sf_ prefix):
        sf_map_uuid, sf_bsn_geoid, sf_region_code, sf_province_code, sf_city_mun_code,
        sf_barangay_code, sf_ean, sf_bsn, sf_ea_geocode, sf_en_code, sf_remarks

    Appends any extra user-specified columns.
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
            match = None
            if name_lower in existing_fields:
                match = existing_fields[name_lower]
            elif f"sf_{name_lower}" in existing_fields:
                match = existing_fields[f"sf_{name_lower}"]
            elif name_lower.startswith("sf_") and name_lower[3:] in existing_fields:
                match = existing_fields[name_lower[3:]]
            if match and match not in fields_to_retain:
                fields_to_retain.append(match)
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


def load_cbms_json_to_layer(json_input: Any, layer_name: str = "cbms_json_table", add_to_project: bool = True) -> QgsVectorLayer:
    """
    Parses a CBMS JSON file (or dictionary/list data) and creates an in-memory
    vector table layer with dynamically discovered string attribute fields.

    :param json_input: Path to JSON file, or parsed dict/list object.
    :param layer_name: Name of the generated QGIS layer.
    :param add_to_project: If True, adds the layer directly to QgsProject layer tree.
    :return: QgsVectorLayer (memory layer with table attributes).
    """
    if isinstance(json_input, str):
        if not os.path.exists(json_input):
            raise FileNotFoundError(f"JSON file not found: {json_input}")
        with open(json_input, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json_input

    records = data if isinstance(data, list) else (data.get("records", [data]) if isinstance(data, dict) else [])

    table_layer = QgsVectorLayer("none", layer_name, "memory")
    dp = table_layer.dataProvider()

    fields = QgsFields()
    field_names = []
    for rec in records:
        props = rec.get("properties", rec) if isinstance(rec, dict) else {}
        if isinstance(props, dict):
            for k, v in props.items():
                k_str = str(k).strip()
                if k_str and k_str not in field_names:
                    fields.append(QgsField(k_str, QVariant.String))
                    field_names.append(k_str)

    dp.addAttributes(fields)
    table_layer.updateFields()

    features = []
    for rec in records:
        props = rec.get("properties", rec) if isinstance(rec, dict) else {}
        feat = QgsFeature(fields)
        for fn in field_names:
            val = props.get(fn, NULL) if isinstance(props, dict) else NULL
            feat.setAttribute(fn, val if val is not None else NULL)
        features.append(feat)

    dp.addFeatures(features)

    if add_to_project:
        QgsProject.instance().addMapLayer(table_layer)

    return table_layer


def load_cbms_csv_to_layer(csv_path: str, layer_name: str = "cbms_csv_table", add_to_project: bool = True) -> QgsVectorLayer:
    """
    Loads a CBMS CSV file directly as an editable OGR vector layer.

    :param csv_path: Path to CSV file.
    :param layer_name: Name of the generated QGIS layer.
    :param add_to_project: If True, adds the layer directly to QgsProject layer tree.
    :return: QgsVectorLayer (OGR layer backed by the CSV file on disk).
    """
    if not csv_path or not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    layer = QgsVectorLayer(csv_path, layer_name, "ogr")
    if not layer or not layer.isValid():
        raise QgsProcessingException(f"Failed to open CSV file as vector layer: {csv_path}")

    if add_to_project:
        QgsProject.instance().addMapLayer(layer)

    return layer


