# -*- coding: utf-8 -*-
"""
Style Helper Utility for Create Enumeration Areas
------------------------------------------------
Provides safe QML style path resolution and layer styling methods.
"""

import os
from qgis.core import QgsVectorLayer, QgsMapLayer


def get_qml_file_path(qml_filename: str) -> str:
    """Find absolute path to *qml_filename* inside 'qml styles' folder by traversing parent dirs."""
    if not qml_filename.lower().endswith(".qml"):
        qml_filename += ".qml"

    curr = os.path.abspath(__file__)
    for _ in range(6):
        curr = os.path.dirname(curr)
        cand = os.path.join(curr, "qml styles", qml_filename)
        if os.path.isfile(cand):
            return cand
    return ""


def apply_qml_to_layer(layer: QgsVectorLayer, qml_filename: str) -> bool:
    """Safely apply a QML style file to a QGIS layer and trigger repaint."""
    if layer is None or not layer.isValid():
        return False

    qml_path = get_qml_file_path(qml_filename)
    if not qml_path or not os.path.isfile(qml_path):
        return False

    try:
        categories = QgsMapLayer.AllStyleCategories & ~QgsMapLayer.Fields
        msg, ok = layer.loadNamedStyle(qml_path, categories=categories)
        layer.triggerRepaint()
        return bool(ok)
    except Exception:
        try:
            msg, ok = layer.loadNamedStyle(qml_path)
            layer.triggerRepaint()
            return bool(ok)
        except Exception:
            return False
