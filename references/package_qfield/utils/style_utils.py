# -*- coding: utf-8 -*-
"""
Utility module for managing QML styles embedded in the plugin.

The plugin ships with a 'qml styles' folder containing .qml files.
This module provides functions to:
- List available QML styles
- Auto-detect the best matching QML style for a given layer name
- Apply a QML style to a QGIS layer
"""

import os
import re
from qgis.core import QgsProject


def get_qml_styles_dir():
    """Return the absolute path to the 'qml styles' folder in the plugin directory.

    Does NOT create it — it is expected to ship with the plugin.
    """
    # Navigate from references/package_qfield/utils/ up to the plugin root (gmd-pipeline-v2/)
    plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(plugin_dir, "qml styles")


def get_available_qml_files():
    """Return a sorted list of QML filenames (with extension) found in the
    'qml styles' folder.  Returns an empty list if the folder doesn't exist.
    """
    qml_dir = get_qml_styles_dir()
    if not os.path.isdir(qml_dir):
        return []
    return sorted(
        f for f in os.listdir(qml_dir)
        if f.lower().endswith(".qml")
    )


def get_available_qml_display_names():
    """Return a sorted list of QML display names (filename without .qml extension).

    Example: '1. Base Layer Barangay'
    """
    return [os.path.splitext(f)[0] for f in get_available_qml_files()]


# ---------------------------------------------------------------------------
# Abbreviation / keyword map used for auto-detection.
# Keys = lowercase keywords extracted from QML display names.
# Values = list of lowercase layer-name suffixes or substrings that should
#           match this QML style.
# ---------------------------------------------------------------------------
_KEYWORD_ALIAS_MAP = {
    "barangay": ["bgy", "brgy", "barangay"],
    "ea": ["_ea", "ea2024"],
    "building points": ["bldgpts", "bldg_points", "bldg"],
    "landmark": ["landmark", "landmarks"],
    "road": ["road"],
    "river": ["river"],
    "block": ["block"],
}


def _extract_qml_keyword(display_name):
    """Extract the meaningful keyword from a QML display name.

    '1. Base Layer Barangay' → 'barangay'
    '4. Base Layer EA'       → 'ea'
    """
    name = display_name.strip()
    # Strip leading number + dot  (e.g. '1. ')
    name = re.sub(r"^\d+\.\s*", "", name)
    # Strip common prefixes
    name = re.sub(r"^Base\s+Layer\s*", "", name, flags=re.IGNORECASE)
    return name.strip().lower()


def auto_detect_qml_for_layer(layer_name, available_display_names=None):
    """Return the best-matching QML display name for *layer_name*, or '' if
    no match is found.

    Matching priority:
      1. Keyword alias map (covers abbreviations like bgy → Barangay)
      2. Substring / suffix match against the extracted keyword
    """
    if available_display_names is None:
        available_display_names = get_available_qml_display_names()

    layer_lower = layer_name.lower()

    # Build keyword → display_name lookup
    keyword_to_display = {}
    for dname in available_display_names:
        kw = _extract_qml_keyword(dname)
        keyword_to_display[kw] = dname

    # --- Pass 1: alias map --------------------------------------------------
    for kw, aliases in _KEYWORD_ALIAS_MAP.items():
        if kw not in keyword_to_display:
            continue
        for alias in aliases:
            # Check if the layer name ends with the alias (after _ or at start)
            if layer_lower.endswith(alias) or layer_lower.endswith("_" + alias):
                return keyword_to_display[kw]

    # --- Pass 2: direct substring match on the extracted keyword -------------
    for kw, dname in keyword_to_display.items():
        if kw and kw in layer_lower:
            return dname

    return ""


def get_qml_file_path(display_name):
    """Return the full file path for a QML given its display name."""
    qml_dir = get_qml_styles_dir()
    return os.path.join(qml_dir, display_name + ".qml")


def apply_qml_to_layer(layer, display_name):
    """Apply the QML style identified by *display_name* to *layer*.

    Returns True on success, False on failure.
    """
    if not display_name:
        return False
    qml_path = get_qml_file_path(display_name)
    if not os.path.isfile(qml_path):
        print(f"[QML ERROR] File does not exist: {qml_path}")
        return False

    # Normalize path to forward slashes for QGIS C++ API compatibility
    normalized_path = qml_path.replace("\\", "/")
    
    # Try 1: Standard loadNamedStyle with normalized path
    res = layer.loadNamedStyle(normalized_path)
    print(f"[QML LOAD RESULT] Layer='{layer.name()}' QML='{display_name}' raw_res={res}")
    
    msg = res[0] if isinstance(res, tuple) else ""
    success = res[1] if isinstance(res, tuple) else bool(res)

    # If QGIS fell back to 'Loaded from Provider', try importing via QDomDocument
    if msg == "Loaded from Provider" or not success:
        print(f"[QML RETRY] loadNamedStyle returned '{msg}'. Attempting importNamedStyle via QDomDocument...")
        try:
            from qgis.PyQt.QtXml import QDomDocument
            doc = QDomDocument()
            with open(qml_path, "r", encoding="utf-8") as f:
                content = f.read()
            if doc.setContent(content):
                msg, success = layer.importNamedStyle(doc)
                print(f"[QML QDOM RESULT] importNamedStyle msg='{msg}' success={success}")
            else:
                print(f"[QML QDOM ERROR] Failed to parse XML content of {qml_path}")
        except Exception as e:
            print(f"[QML QDOM EXCEPTION] {e}")

    print(f"[QML FINAL RESULT] Layer='{layer.name()}' msg='{msg}' success={success}")
    if success:
        layer.triggerRepaint()
        try:
            from qgis.utils import iface
            iface.layerTreeView().refreshLayerSymbology(layer.id())
        except Exception as e:
            print(f"[QML ERROR] refreshLayerSymbology failed: {e}")
    return success


def apply_embedded_qml_styles(project=None):
    """Auto-detect and apply QML styles to ALL layers in the current project.

    Returns a dict  { layer_name: applied_qml_display_name_or_empty }.
    """
    if project is None:
        project = QgsProject.instance()

    available = get_available_qml_display_names()
    results = {}

    for layer in project.mapLayers().values():
        lname = layer.name()
        match = auto_detect_qml_for_layer(lname, available)
        if match:
            apply_qml_to_layer(layer, match)
        results[lname] = match

    return results

