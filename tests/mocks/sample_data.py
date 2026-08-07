# -*- coding: utf-8 -*-
"""
Sample spatial data fixture generator for GEMMA QGIS plugin unit tests.
Creates realistic vector layers, features, geometries, and attribute tables
matching PSA enumeration and barangay mapping schemas for both PyQGIS native
and headless mock execution environments.
"""

from tests.mocks.qgis_mock import (
    MockQVariant,
)

# When running inside a real QGIS environment (e.g. qgis/qgis:latest Docker),
# we MUST use the native C++ classes from qgis.core. If we use the mock Python
# classes, the SIP bindings reject them with:
#   TypeError: index 0 has type 'QgsField' but 'QgsField' is expected
# Only fall back to mock classes when qgis.core is not available.
try:
    from qgis.core import (
        QgsVectorLayer,
        QgsFeature,
        QgsGeometry,
        QgsField,
        QgsFields,
        QgsPointXY,
        QgsWkbTypes,
    )
    _NATIVE_QGIS = True
except ImportError:
    from tests.mocks.qgis_mock import (
        QgsVectorLayer,
        QgsFeature,
        QgsGeometry,
        QgsField,
        QgsFields,
        QgsPointXY,
        QgsWkbTypes,
    )
    _NATIVE_QGIS = False

try:
    from qgis.PyQt.QtCore import QVariant
except Exception:
    QVariant = MockQVariant



def _populate_layer(layer, fields, features):
    """Helper to populate fields and features across both Native PyQGIS and Mock layer objects."""
    dp = layer.dataProvider() if hasattr(layer, "dataProvider") else None
    if dp:
        if dp.fields().count() == 0:
            dp.addAttributes(list(fields))
            if hasattr(layer, "updateFields"):
                layer.updateFields()
        layer_fields = layer.fields()
        bound_features = []
        for f in features:
            nf = QgsFeature(layer_fields)
            if hasattr(f, "geometry") and f.geometry():
                nf.setGeometry(f.geometry())
            if hasattr(f, "attributes"):
                attrs = f.attributes()
                for idx, val in enumerate(attrs):
                    nf.setAttribute(idx, val)
            bound_features.append(nf)
        dp.addFeatures(bound_features)
        if hasattr(layer, "updateExtents"):
            layer.updateExtents()
    else:
        if hasattr(layer, "setFields"):
            layer.setFields(fields)
        if hasattr(layer, "setFeatures"):
            layer.setFeatures(features)


def create_sample_polygon_layer(name="Sample_EA_Polygons", count=5):
    """
    Create a vector polygon layer containing sample Enumeration Areas / Barangay boundaries.
    """
    var_str = getattr(QVariant, "String", 1)
    var_int = getattr(QVariant, "Int", 2)

    fields = QgsFields()
    fields.append(QgsField("brgy_code", var_str))
    fields.append(QgsField("ea_code", var_str))
    fields.append(QgsField("ea_name", var_str))
    fields.append(QgsField("total_hh", var_int))
    fields.append(QgsField("status", var_str))

    layer = QgsVectorLayer("Polygon?crs=EPSG:4326", name, "memory")

    features = []
    for i in range(1, count + 1):
        feat = QgsFeature(fields)
        feat.setAttributes([
            f"05173700{i:02d}",
            f"05173700{i:02d}001",
            f"EA Candidate {i}",
            150 + (i * 35),
            "VERIFIED" if i % 2 == 0 else "UNCHECKED"
        ])
        # Mock polygon geometry (square rings)
        pts = [
            QgsPointXY(123.0 + i * 0.01, 13.0 + i * 0.01),
            QgsPointXY(123.01 + i * 0.01, 13.0 + i * 0.01),
            QgsPointXY(123.01 + i * 0.01, 13.01 + i * 0.01),
            QgsPointXY(123.0 + i * 0.01, 13.01 + i * 0.01),
            QgsPointXY(123.0 + i * 0.01, 13.0 + i * 0.01)
        ]
        feat.setGeometry(QgsGeometry.fromPolygonXY([pts]))
        features.append(feat)

    _populate_layer(layer, fields, features)
    return layer


def create_sample_point_layer(name="Sample_Building_Points", count=10):
    """
    Create a vector point layer containing sample building / household centroids.
    """
    var_str = getattr(QVariant, "String", 1)
    var_int = getattr(QVariant, "Int", 2)

    fields = QgsFields()
    fields.append(QgsField("building_id", var_int))
    fields.append(QgsField("structure_type", var_str))
    fields.append(QgsField("hh_count", var_int))

    layer = QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")

    features = []
    for i in range(1, count + 1):
        feat = QgsFeature(fields)
        feat.setAttributes([
            1000 + i,
            "Residential" if i % 2 == 0 else "Commercial",
            1 + (i % 3)
        ])
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(123.0 + i * 0.005, 13.0 + i * 0.005)))
        features.append(feat)

    _populate_layer(layer, fields, features)
    return layer


def create_sample_line_layer(name="Sample_Road_Lines", count=5):
    """
    Create a vector line layer containing sample road / river boundaries.
    """
    var_str = getattr(QVariant, "String", 1)
    var_int = getattr(QVariant, "Int", 2)

    fields = QgsFields()
    fields.append(QgsField("road_id", var_int))
    fields.append(QgsField("road_name", var_str))
    fields.append(QgsField("road_type", var_str))

    layer = QgsVectorLayer("LineString?crs=EPSG:4326", name, "memory")

    features = []
    for i in range(1, count + 1):
        feat = QgsFeature(fields)
        feat.setAttributes([
            2000 + i,
            f"National Highway {i}",
            "Primary" if i == 1 else "Secondary"
        ])
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(123.0 + i * 0.01, 13.0 + i * 0.01),
            QgsPointXY(123.05 + i * 0.01, 13.05 + i * 0.01)
        ]))
        features.append(feat)

    _populate_layer(layer, fields, features)
    return layer
