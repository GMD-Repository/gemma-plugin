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
    """Exports features to a QgsProcessingParameterFeatureSink."""
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

    for f in features:
        if feedback and feedback.isCanceled():
            break
        sink.addFeature(f, QgsFeatureSink.FastInsert)

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
    """Loads and parses a CBMS JSON data file from algorithm parameters."""
    json_data = None
    json_path = alg.parameterAsFile(parameters, param_name, context)

    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            if feedback:
                feedback.pushInfo(f"Loaded JSON input data from: '{json_path}'")
        except Exception as e:
            if feedback:
                feedback.pushInfo(f"Warning: Failed to parse INPUT_DATA JSON: {e}")

    return json_data


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
