# -*- coding: utf-8 -*-
"""
2027 CBMS Map Validation Unified Fix Module: cbms_mv_fix
---------------------------------------------------------
Contains all automated fix algorithms and action processes for CBMS MV.

Processes and Fixes registered in this module:
  1. Process: Concatenate EA Geocode (mv_2027_hp_4b_ea_geocode__missing)
     Computes missing EA geocode following a 4-step prioritized fallback cascade:
     1) Direct sf_* columns, 2) Standard boundary columns, 3) sf_bsn_geoid, 4) bsn_geoid.
     Entry points: concatenate_ea_geocode(), compute_ea_geocode_field_calculator(), _run_fix_ea_geocode().

  2. Process: Generate Point Geometry (mv_2027_hp_1a_map_uuid__missing)
     Generates point geometries in the Form 2 Geotagged Building Points layer (.geojson)
     from coordinates in df_x_current / df_y_current.
     Entry points: generate_point_geometry(), _run_fix_map_uuid_missing().

  3. Process: Unified Fix Dispatcher
     Single entry point routing any validation check ID to its fix algorithm.
     Entry point: run_fix(main_layer, val_id=..., target_fids=..., target_uuids=...).

  4. Process: Soft Delete
     Batch marks checked features as 'deleted' in the status column and synchronizes
     across table rows, in-memory layers, and the primary building points layer.
     Entry points: delete_selected_features(), mark_feature_deleted(), sync_feature_status().

  5. Process: Deduplicate Features (mv_2027_hp_4a_longitude__duplicate)
     Checks all columns to see if features with duplicate coordinates are identical.
     Retains only one active feature and marks duplicate features as 'deleted' in sf_status / status.
     Entry points: deduplicate_features(), _run_fix_longitude_duplicate().
"""

import datetime
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

try:
    import processing
except ImportError:
    processing = None

from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorLayer,
)
try:
    from qgis.PyQt.QtCore import Qt, QVariant
    from qgis.PyQt.QtWidgets import (
        QComboBox,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
    )
except ImportError:
    try:
        from PyQt5.QtCore import Qt, QVariant
        from PyQt5.QtWidgets import (
            QComboBox,
            QMessageBox,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
        )
    except ImportError:
        Qt = None
        QVariant = None
        QMessageBox = None
        QTableWidgetItem = None
        QTableWidget = None
        QPushButton = None
        QComboBox = None


def is_valid_qobject(obj: Any) -> bool:
    """Safely check whether a Qt C++ wrapper object is still alive and not deleted."""
    if obj is None:
        return False
    try:
        import sip
        return not sip.isdeleted(obj)
    except Exception:
        pass
    try:
        obj.objectName()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fix Metadata Registry
# ---------------------------------------------------------------------------
FIX_REGISTRY = {
    "mv_2027_hp_4b_ea_geocode__missing": {
        "name": "Concatenate and paste EA geocode",
        "description": (
            "Calculates and assigns 'sf_ea_geocode' using 4 prioritized fallback steps: "
            "1) Direct concatenation of sf_* columns, 2) Direct concatenation of standard boundary columns, "
            "3) sf_bsn_geoid (first 14 chars), 4) bsn_geoid (first 14 chars)."
        ),
    },
    "mv_2027_hp_1a_map_uuid__missing": {
        "name": "Generate point geometry from df_x_current and df_y_current",
        "description": (
            "Generates and adds a point geometry into the Form 2 Geotagged Building Points "
            "layer (.geojson) using coordinate attributes from 'df_x_current' (X) and 'df_y_current' (Y)."
        ),
    },
    "mv_2027_hp_4a_longitude__duplicate": {
        "name": "Delete duplicate features (retain one)",
        "description": (
            "Checks all columns of features with duplicate coordinates to see if they are identical. "
            "Retains only one active feature and marks duplicate features as 'deleted' in sf_status / status."
        ),
    },
}

# Backward-compatible module-level constants (default to EA geocode fix)
FIX_ID = "mv_2027_hp_4b_ea_geocode__missing"
FIX_NAME = FIX_REGISTRY[FIX_ID]["name"]
FIX_DESCRIPTION = FIX_REGISTRY[FIX_ID]["description"]

# hp_1a constants (accessible for tests)
FIX_ID_HP_1A = "mv_2027_hp_1a_map_uuid__missing"
FIX_NAME_HP_1A = FIX_REGISTRY[FIX_ID_HP_1A]["name"]
FIX_DESCRIPTION_HP_1A = FIX_REGISTRY[FIX_ID_HP_1A]["description"]

# hp_4a duplicate constants (accessible for tests)
FIX_ID_HP_4A_DUP = "mv_2027_hp_4a_longitude__duplicate"
FIX_NAME_HP_4A_DUP = FIX_REGISTRY[FIX_ID_HP_4A_DUP]["name"]
FIX_DESCRIPTION_HP_4A_DUP = FIX_REGISTRY[FIX_ID_HP_4A_DUP]["description"]


# ---------------------------------------------------------------------------
# Shared Utilities
# ---------------------------------------------------------------------------
def _normalize_cell_val(val: Any, precision: int = 7) -> str:
    """Normalize a cell or attribute value for equality comparison (up to `precision` decimals)."""
    if val is None or val == NULL:
        return ""
    s = str(val).strip()
    if s.lower() in ("null", "none", "nan"):
        return ""
    try:
        f = float(s)
        if "." in s:
            return f"{f:.{precision}f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        pass
    return s


def _normalize_coordinate(val: Any, precision: int = 7) -> str:
    """Normalize coordinate value strictly to `precision` digits after '.' (e.g. 121.0500000)."""
    if val is None or val == NULL:
        return ""
    s = str(val).strip()
    if s.lower() in ("null", "none", "nan"):
        return ""
    try:
        f = float(s)
        return f"{f:.{precision}f}"
    except (ValueError, TypeError):
        return s


def _is_coord_col(col_name: str, coord_type: str) -> bool:
    """Check if column name represents longitude or latitude."""
    c = str(col_name).strip().lower()
    base_c = c[3:] if c.startswith(("sf_", "df_")) else c
    if coord_type == "lon":
        return base_c in ("longitude", "longitud", "pos_longitude", "pos_longit")
    elif coord_type == "lat":
        return base_c in ("latitude", "latitud", "pos_latitude", "pos_latitu")
    return False


def _extract_feature_coord_sig(feat: Any, precision: int = 7) -> Tuple[str, str]:
    """Extract (lon_7dec, lat_7dec) from a QgsFeature geometry and/or attributes."""
    lon_str = ""
    lat_str = ""
    # 1. Geometry coordinate check
    try:
        if feat and hasattr(feat, "hasGeometry") and feat.hasGeometry() and not feat.geometry().isEmpty():
            pt = feat.geometry().asPoint()
            lon_str = _normalize_coordinate(pt.x(), precision=precision)
            lat_str = _normalize_coordinate(pt.y(), precision=precision)
    except Exception:
        pass

    # 2. Attribute coordinate check if geometry was absent or empty
    if not lon_str or not lat_str:
        try:
            if feat and hasattr(feat, "fields") and feat.fields():
                for f in feat.fields():
                    fn = f.name()
                    if not lon_str and _is_coord_col(fn, "lon"):
                        v = feat[fn]
                        if v is not None and v != NULL and str(v).strip():
                            lon_str = _normalize_coordinate(v, precision=precision)
                    elif not lat_str and _is_coord_col(fn, "lat"):
                        v = feat[fn]
                        if v is not None and v != NULL and str(v).strip():
                            lat_str = _normalize_coordinate(v, precision=precision)
        except Exception:
            pass

    return (lon_str, lat_str)


def _extract_feature_id_sig(feat: Any) -> Tuple[str, str]:
    """Extract (map_uuid, bsn_geoid) from a QgsFeature."""
    uuid_str = ""
    bsn_geoid_str = ""
    if not feat:
        return ("", "")

    for fn in ("sf_map_uuid", "df_map_uuid", "map_uuid", "uuid"):
        try:
            val = feat[fn]
            if val is not None and val != NULL and str(val).strip() and str(val).strip().lower() not in ("null", "none"):
                uuid_str = str(val).strip()
                break
        except Exception:
            pass

    for fn in ("sf_bsn_geoid", "df_bsn_geoid", "bsn_geoid"):
        try:
            val = feat[fn]
            if val is not None and val != NULL and str(val).strip() and str(val).strip().lower() not in ("null", "none"):
                bsn_geoid_str = str(val).strip()
                break
        except Exception:
            pass

    # Fallback: synthesize bsn_geoid from ea_geocode + bsn
    if not bsn_geoid_str:
        ea = ""
        bsn = ""
        for fn in ("sf_ea_geocode", "df_ea_geocode", "ea_geocode"):
            try:
                v = feat[fn]
                if v is not None and v != NULL and str(v).strip() and str(v).strip().lower() not in ("null", "none"):
                    ea = str(v).strip()
                    break
            except Exception:
                pass
        for fn in ("sf_bsn", "df_bsn", "bsn"):
            try:
                v = feat[fn]
                if v is not None and v != NULL and str(v).strip() and str(v).strip().lower() not in ("null", "none"):
                    bsn = str(v).strip()
                    break
            except Exception:
                pass
        if ea and bsn:
            bsn_geoid_str = f"{ea}{bsn}"

    return (uuid_str, bsn_geoid_str)



def _flatten_ids(item: Any) -> set:
    """Recursively extract hashable identifiers (int, str, UUIDs) from primitives, dicts, or lists."""
    res = set()
    if item is None or item == NULL:
        return res
    if isinstance(item, (list, tuple, set)):
        for x in item:
            res.update(_flatten_ids(x))
    elif isinstance(item, dict):
        for k in ("fid", "sf_fid", "df_fid", "id", "map_uuid", "sf_map_uuid", "uuid"):
            if k in item and not isinstance(item[k], (dict, list, set, tuple)):
                res.update(_flatten_ids(item[k]))
    else:
        res.add(item)
        s = str(item).strip()
        if s and not s.startswith(("<", "Mock")):
            res.add(s)
            res.add(s.lower())
    return res


# ===========================================================================
# Fix 1: mv_2027_hp_4b_ea_geocode__missing — EA Geocode Concatenation
# ===========================================================================
def _get_val(feat: QgsFeature, col_name: str) -> Optional[str]:
    """Safely extracts clean string value of a column from a feature."""
    try:
        v = feat[col_name] if hasattr(feat, "__getitem__") else feat.attribute(col_name)
        if v is not None and v != NULL:
            s = str(v).strip()
            if s and s.upper() not in ("", "NULL", "NONE", "NAN") and not s.startswith(("<", "Mock")):
                return s
    except Exception:
        pass
    return None


def compute_ea_geocode_field_calculator(
    feature: QgsFeature,
    layer: Optional[QgsVectorLayer] = None,
) -> str:
    """
    Computes EA geocode using the 4-step priority process:
      1. All sf_* columns (sf_province_code, sf_city_mun_code, sf_barangay_code, sf_ean)
      2. All standard columns (province_code, city_mun_code, barangay_code, ean)
      3. left(sf_bsn_geoid, 14)
      4. left(bsn_geoid, 14)
    """
    # 1. Try QGIS Expression Engine
    exp_str = (
        'coalesce('
        # 1st Priority: sf_* columns (all must be non-null & non-empty & not NULL/NONE, direct concat)
        'if("sf_province_code" IS NOT NULL AND upper(trim(to_string("sf_province_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_city_mun_code" IS NOT NULL AND upper(trim(to_string("sf_city_mun_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_barangay_code" IS NOT NULL AND upper(trim(to_string("sf_barangay_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_ean" IS NOT NULL AND upper(trim(to_string("sf_ean"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'concat(to_string("sf_province_code"), to_string("sf_city_mun_code"), '
        'to_string("sf_barangay_code"), to_string("sf_ean")), NULL), '
        # 2nd Priority: standard boundary columns (all must be non-null & non-empty & not NULL/NONE, direct concat)
        'if("province_code" IS NOT NULL AND upper(trim(to_string("province_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"city_mun_code" IS NOT NULL AND upper(trim(to_string("city_mun_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"barangay_code" IS NOT NULL AND upper(trim(to_string("barangay_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"ean" IS NOT NULL AND upper(trim(to_string("ean"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'concat(to_string("province_code"), to_string("city_mun_code"), '
        'to_string("barangay_code"), to_string("ean")), NULL), '
        # 3rd Priority: left(sf_bsn_geoid, 14)
        'if("sf_bsn_geoid" IS NOT NULL AND upper(trim(to_string("sf_bsn_geoid"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'substr(to_string("sf_bsn_geoid"), 1, 14), NULL), '
        # 4th Priority: left(bsn_geoid, 14)
        'if("bsn_geoid" IS NOT NULL AND upper(trim(to_string("bsn_geoid"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'substr(to_string("bsn_geoid"), 1, 14), NULL), '
        '\'\')'
    )

    try:
        exp = QgsExpression(exp_str)
        ctx = QgsExpressionContext()
        if layer and hasattr(QgsExpressionContextUtils, "globalProjectLayerScopes"):
            ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        ctx.setFeature(feature)
        res = exp.evaluate(ctx)
        if res and res != NULL and not str(res).startswith(("<", "Mock")) and str(res).strip():
            return str(res).strip()
    except Exception:
        pass

    # 2. Resilient Python Fallback Engine (Direct Concatenation)
    # 1st Priority: sf_* columns
    p1, m1, b1, e1 = (
        _get_val(feature, "sf_province_code"),
        _get_val(feature, "sf_city_mun_code"),
        _get_val(feature, "sf_barangay_code"),
        _get_val(feature, "sf_ean"),
    )
    if p1 is not None and m1 is not None and b1 is not None and e1 is not None:
        return f"{p1}{m1}{b1}{e1}"

    # 2nd Priority: standard boundary columns
    p2, m2, b2, e2 = (
        _get_val(feature, "province_code"),
        _get_val(feature, "city_mun_code"),
        _get_val(feature, "barangay_code"),
        _get_val(feature, "ean"),
    )
    if p2 is not None and m2 is not None and b2 is not None and e2 is not None:
        return f"{p2}{m2}{b2}{e2}"

    # 3rd Priority: left(sf_bsn_geoid, 14)
    bsn1 = _get_val(feature, "sf_bsn_geoid")
    if bsn1 is not None:
        return bsn1[:14]

    # 4th Priority: left(bsn_geoid, 14)
    bsn2 = _get_val(feature, "bsn_geoid")
    if bsn2 is not None:
        return bsn2[:14]

    return ""


def _run_fix_ea_geocode(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute automated fix: computes EA geocode using the 4-step priority logic
    and assigns it to building points layer.
    """
    if not main_layer or not main_layer.isValid():
        return {"success": False, "message": "Invalid or missing Building Points layer.", "fixed_count": 0, "updated_values": {}}

    is_targeted = (target_fids is not None) or (target_uuids is not None)
    target_set = _flatten_ids(target_fids) | _flatten_ids(target_uuids)

    if is_targeted and not target_set:
        return {"success": True, "fixed_count": 0, "updated_values": {}, "message": "No valid target ID or UUID provided."}

    field_names = main_layer.fields().names() if hasattr(main_layer.fields(), "names") else []
    target_fields = [f for f in ("sf_ea_geocode", "ea_geocode", "geocode") if f in field_names]

    if not target_fields:
        if not main_layer.isEditable():
            main_layer.startEditing()
        main_layer.dataProvider().addAttributes([QgsField("ea_geocode", QVariant.String, len=30)])
        main_layer.updateFields()
        target_fields.append("ea_geocode")

    if not main_layer.isEditable() and not main_layer.startEditing():
        return {"success": False, "fixed_count": 0, "updated_values": {}, "message": "Failed to start edit session on building points layer."}

    updated_values: Dict[Any, Dict[str, str]] = {}
    fixed_count = 0

    for feat in main_layer.getFeatures():
        if feedback and feedback.isCanceled():
            break

        f_id = feat.id()
        feat_ids = _flatten_ids(f_id)
        for col in ("sf_fid", "fid", "sf_map_uuid", "map_uuid", "uuid"):
            if col in field_names:
                try:
                    val = feat.attribute(col)
                    if val is not None and val != NULL:
                        feat_ids.update(_flatten_ids(val))
                except Exception:
                    pass

        if is_targeted and not (feat_ids & target_set):
            continue

        concat_geocode = compute_ea_geocode_field_calculator(feat, main_layer)
        if not concat_geocode:
            continue

        for tf_name in target_fields:
            idx = main_layer.fields().indexOf(tf_name)
            if idx != -1:
                main_layer.changeAttributeValue(f_id, idx, concat_geocode)

        payload = {"sf_ea_geocode": concat_geocode, "ea_geocode": concat_geocode}
        for k in feat_ids:
            updated_values[k] = payload

        fixed_count += 1

    if feedback:
        feedback.pushInfo(f"Calculated and assigned EA geocode for {fixed_count} feature(s).")

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Successfully calculated and updated EA geocode for {fixed_count} feature(s).",
    }


def concatenate_ea_geocode(
    dialog: Any,
    val_id: str,
    layer: Any,
    table: Any,
) -> None:
    """
    Process handler for concatenating EA geocode on checked table rows.
    Keeps all algorithmic processing inside cbms_mv_fix.py.
    """
    if hasattr(dialog, "_fix_selected_features"):
        dialog._fix_selected_features("mv_2027_hp_4b_ea_geocode__missing", layer, table)


# ===========================================================================
# Fix 2: mv_2027_hp_1a_map_uuid__missing — Generate Point Geometry
# ===========================================================================
def _set_feat_attr(feat: Any, field_name: str, val: Any) -> None:
    try:
        feat.setAttribute(field_name, val)
    except Exception:
        try:
            feat[field_name] = val
        except Exception:
            pass


def _prompt_numerical_digitize(
    info: Any,
    parent: Any = None,
    iface: Any = None,
    initial_x: Any = None,
    initial_y: Any = None,
) -> Optional[Tuple[float, float]]:
    return None


def _extract_row_data(
    r: int,
    table: Optional[Any],
    error_layer: Optional[QgsVectorLayer],
    target_fids: Optional[List[Any]],
    target_uuids: Optional[List[str]],
) -> Dict[str, Any]:
    """Extract coordinates, UUID, and other attributes from table row and/or error_layer."""
    row_info = {
        "x": None,
        "y": None,
        "uuid": "",
        "df_fid": None,
        "source_fid": None,
        "err_fid": None,
        "attributes": {},
    }

    # 1. Read from table widget if provided
    if table is not None:
        header_map = {}
        for c in range(table.columnCount()):
            h_item = table.horizontalHeaderItem(c)
            h_text = h_item.text().strip().lower() if h_item else ""
            if h_text and h_text not in ("", "action", "actions"):
                header_map[h_text] = c

        # Extract X coordinate: check candidates in priority order for a valid numeric value in row r
        for candidate in (
            "df_x_current", "x_current", "sf_longitude", "longitude", "x",
            "pos_longit", "sf_pos_longit", "df_longitude", "df_x"
        ):
            if candidate in header_map:
                it = table.item(r, header_map[candidate])
                if it and it.text().strip():
                    txt = it.text().strip()
                    if txt.lower() not in ("null", "none", "nan", ""):
                        try:
                            val = float(txt)
                            if abs(val) > 1e-5:
                                row_info["x"] = val
                                break
                        except (ValueError, TypeError):
                            pass

        # Extract Y coordinate: check candidates in priority order for a valid numeric value in row r
        for candidate in (
            "df_y_current", "y_current", "sf_latitude", "latitude", "y",
            "pos_latitu", "sf_pos_latitu", "df_latitude", "df_y"
        ):
            if candidate in header_map:
                it = table.item(r, header_map[candidate])
                if it and it.text().strip():
                    txt = it.text().strip()
                    if txt.lower() not in ("null", "none", "nan", ""):
                        try:
                            val = float(txt)
                            if abs(val) > 1e-5:
                                row_info["y"] = val
                                break
                        except (ValueError, TypeError):
                            pass

        # Extract UUID: prioritize df_map_uuid over sf_map_uuid, and reject literal 'NULL'/'None'
        for candidate in ("df_map_uuid", "map_uuid", "uuid", "sf_map_uuid"):
            if candidate in header_map:
                it = table.item(r, header_map[candidate])
                if it and it.text().strip():
                    txt = it.text().strip()
                    if txt.lower() not in ("null", "none", "nan", ""):
                        row_info["uuid"] = txt
                        break

        # Check item0 (column 0 checkbox item) metadata roles if UUID or DF_FID not found
        item0 = table.item(r, 0)
        if item0:
            if item0.data(Qt.UserRole + 3) is not None:
                row_info["err_fid"] = item0.data(Qt.UserRole + 3)
            if item0.data(Qt.UserRole) is not None:
                row_info["source_fid"] = item0.data(Qt.UserRole)

            if not row_info["uuid"]:
                for role_off in (5, 1, 7):  # Qt.UserRole + 5 (df_uuid), + 1 (uuid_str), + 7 (sf_uuid)
                    val = item0.data(Qt.UserRole + role_off)
                    if val is not None:
                        s_val = str(val).strip()
                        if s_val and s_val.lower() not in ("null", "none", "nan", ""):
                            row_info["uuid"] = s_val
                            break

            if row_info["df_fid"] is None:
                for role_off in (4, 0, 6):  # Qt.UserRole + 4 (df_fid), + 0 (source_fid), + 6 (sf_fid)
                    val = item0.data(Qt.UserRole + role_off)
                    if val is not None:
                        s_val = str(val).strip()
                        if s_val and s_val.lower() not in ("null", "none", "nan", ""):
                            row_info["df_fid"] = s_val
                            break

        # Capture other cell values (excluding 'NULL' / 'None' placeholders)
        for h_name, c_idx in header_map.items():
            it = table.item(r, c_idx)
            if it and it.text().strip():
                txt = it.text().strip()
                if txt.lower() not in ("null", "none", "nan", ""):
                    row_info["attributes"][h_name] = txt

    # 2. Cross-reference or fallback with error_layer
    if error_layer is not None and (row_info["x"] is None or row_info["y"] is None or not row_info["uuid"]):
        field_names = [f.name() for f in error_layer.fields()]
        feat = None

        # Direct O(1) lookup using err_fid stored in item0 (Qt.UserRole + 3)
        if table is not None:
            item0 = table.item(r, 0)
            if item0:
                err_fid = item0.data(Qt.UserRole + 3)
                if err_fid is not None:
                    try:
                        candidate_f = error_layer.getFeature(int(err_fid))
                        if candidate_f and candidate_f.isValid():
                            feat = candidate_f
                    except Exception:
                        pass
                if feat is None:
                    source_fid = item0.data(Qt.UserRole)
                    if source_fid is not None:
                        try:
                            candidate_f = error_layer.getFeature(int(source_fid))
                            if candidate_f and candidate_f.isValid():
                                feat = candidate_f
                        except Exception:
                            pass

        # Fallback to matching feature by target_uuids or target_fids
        if feat is None:
            cur_fid = None
            if table is not None and item0:
                cur_fid = item0.data(Qt.UserRole) or item0.data(Qt.UserRole + 4)
            if cur_fid is None and target_fids:
                if r < len(target_fids):
                    cur_fid = target_fids[r]
                elif len(target_fids) == 1:
                    cur_fid = target_fids[0]

            cur_uuid = None
            if table is not None and item0:
                cur_uuid = item0.data(Qt.UserRole + 1) or item0.data(Qt.UserRole + 5)
            if not cur_uuid and target_uuids:
                if r < len(target_uuids):
                    cur_uuid = target_uuids[r]
                elif len(target_uuids) == 1:
                    cur_uuid = target_uuids[0]

            for candidate_feat in error_layer.getFeatures():
                feat_uuid = ""
                for u_col in ("df_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
                    if u_col in field_names:
                        val = candidate_feat[u_col]
                        if val is not None and val != NULL:
                            s_val = str(val).strip()
                            if s_val.lower() not in ("null", "none", "nan", ""):
                                feat_uuid = s_val
                                break

                feat_fid = candidate_feat["df_fid"] if "df_fid" in field_names else candidate_feat.id()

                is_match = False
                if cur_uuid and feat_uuid == cur_uuid:
                    is_match = True
                elif cur_fid is not None and (feat_fid == cur_fid or candidate_feat.id() == cur_fid):
                    is_match = True

                if is_match:
                    feat = candidate_feat
                    break

        if feat is not None:
            feat_uuid = ""
            for u_col in ("df_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
                if u_col in field_names:
                    val = feat[u_col]
                    if val is not None and val != NULL:
                        s_val = str(val).strip()
                        if s_val.lower() not in ("null", "none", "nan", ""):
                            feat_uuid = s_val
                            break

            feat_fid = feat["df_fid"] if "df_fid" in field_names else feat.id()
            row_info["feat_fid"] = feat.id()

            if row_info["x"] is None:
                for xc in ("df_x_current", "x_current", "sf_longitude", "longitude", "x", "pos_longit", "sf_pos_longit", "df_longitude"):
                    if xc in field_names and feat[xc] not in (None, NULL):
                        txt = str(feat[xc]).strip()
                        if txt.lower() not in ("null", "none", "nan", ""):
                            try:
                                val = float(txt)
                                if abs(val) > 1e-5:
                                    row_info["x"] = val
                                    break
                            except (ValueError, TypeError):
                                pass

            if row_info["y"] is None:
                for yc in ("df_y_current", "y_current", "sf_latitude", "latitude", "y", "pos_latitu", "sf_pos_latitu", "df_latitude"):
                    if yc in field_names and feat[yc] not in (None, NULL):
                        txt = str(feat[yc]).strip()
                        if txt.lower() not in ("null", "none", "nan", ""):
                            try:
                                val = float(txt)
                                if abs(val) > 1e-5:
                                    row_info["y"] = val
                                    break
                            except (ValueError, TypeError):
                                pass

            if not row_info["uuid"] and feat_uuid:
                row_info["uuid"] = feat_uuid

            if row_info["df_fid"] is None and feat_fid is not None:
                row_info["df_fid"] = feat_fid

            for fn in field_names:
                if fn not in row_info["attributes"]:
                    val = feat[fn]
                    if val not in (None, NULL):
                        txt = str(val).strip()
                        if txt.lower() not in ("null", "none", "nan", ""):
                            row_info["attributes"][fn] = txt

    return row_info


def _run_fix_map_uuid_missing(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    error_layer: Optional[QgsVectorLayer] = None,
    table: Optional[Any] = None,
    dialog: Optional[Any] = None,
    target_rows: Optional[List[int]] = None,
    x_col: str = "df_x_current",
    y_col: str = "df_y_current",
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute automated fix: generates and writes point geometries into the
    Form 2 Geotagged Building Points layer using df_x_current and df_y_current
    from the selected row in mv_2027_hp_1a_map_uuid__missing.
    """
    if not main_layer or not main_layer.isValid():
        return {
            "success": False,
            "message": "Invalid or missing Form 2 Building Points layer.",
            "fixed_count": 0,
            "updated_values": {},
        }

    # Determine which table rows to fix
    if target_rows is not None and len(target_rows) > 0:
        rows_to_process = list(target_rows)
    elif table is not None:
        rows_to_process = []
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if item0:
                is_checked = (item0.checkState() == 2) if hasattr(item0, "checkState") else getattr(item0, "isChecked", lambda: False)()
                if is_checked:
                    rows_to_process.append(r)
        if not rows_to_process:
            rows_to_process = list(range(table.rowCount()))
    elif target_fids is not None and len(target_fids) > 0:
        rows_to_process = list(range(len(target_fids)))
    elif target_uuids is not None and len(target_uuids) > 0:
        rows_to_process = list(range(len(target_uuids)))
    else:
        rows_to_process = [0]

    # Ensure main_layer is in editing mode
    if not main_layer.isEditable() and not main_layer.startEditing():
        return {
            "success": False,
            "message": "Failed to start edit session on Form 2 Building Points layer.",
            "fixed_count": 0,
            "updated_values": {},
        }

    main_fields = main_layer.fields()
    main_field_names = [f.name() for f in main_fields]

    # Coordinate transformation if layer is projected
    src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    dest_crs = main_layer.crs()
    transform = None
    if dest_crs.isValid() and dest_crs != src_crs and not dest_crs.isGeographic():
        transform = QgsCoordinateTransform(src_crs, dest_crs, QgsProject.instance())

    updated_values: Dict[Any, Dict[str, Any]] = {}
    fixed_count = 0
    created_count = 0
    reused_count = 0
    failed_rows = []
    created_batch_fids = set()
    created_batch_features: List[Tuple[Any, Any, float, float, str]] = []  # (assigned_fid, pt, x, y, target_uuid)

    for r in rows_to_process:
        if feedback and feedback.isCanceled():
            break

        row_info = _extract_row_data(r, table, error_layer, target_fids, target_uuids)
        x = row_info["x"]
        y = row_info["y"]
        target_uuid = row_info.get("uuid")

        # Sanitize candidate UUID from row
        clean_uuid = str(target_uuid).strip() if target_uuid is not None else ""
        if clean_uuid.lower() in ("null", "none", "nan", ""):
            clean_uuid = ""

        # Validate coordinates: reject None, (0, 0), or near-zero invalid coords
        if x is None or y is None or (abs(x) < 1e-5 and abs(y) < 1e-5):
            dlg = kwargs.get("dialog")
            prompted = _prompt_numerical_digitize(
                row_info,
                parent=dlg,
                iface=getattr(dlg, "iface", None) if dlg else None,
                initial_x=x,
                initial_y=y,
            )
            if prompted and isinstance(prompted, (tuple, list)) and len(prompted) >= 2:
                x, y = prompted[0], prompted[1]
            else:
                failed_rows.append((r, x, y))
                continue

        pt = QgsPointXY(x, y)
        if transform:
            try:
                pt = transform.transform(pt)
            except Exception:
                pass

        new_geom = QgsGeometry.fromPointXY(pt)
        if not new_geom or new_geom.isEmpty():
            failed_rows.append((r, x, y))
            continue

        existing_feat = None
        existing_feat_id = None
        existing_uuid = None
        is_reused_from_batch = False
        uuid_fields = [fn for fn in main_field_names if fn.lower() in ("map_uuid", "sf_map_uuid", "uuid")]

        # 1. Match by explicit existing UUID if row already has a valid non-empty UUID
        if clean_uuid and uuid_fields:
            for feat in main_layer.getFeatures():
                if feat.id() in created_batch_fids:
                    continue
                for uf in uuid_fields:
                    val = feat[uf]
                    if val is not None and val != NULL:
                        s_val = str(val).strip()
                        if s_val.lower() not in ("null", "none", "nan", "") and s_val == clean_uuid:
                            existing_feat = feat
                            existing_feat_id = feat.id()
                            existing_uuid = clean_uuid
                            break
                if existing_feat_id is not None:
                    break

        # 2. Match by (X, Y) coordinates: check if a point already exists at this location
        is_geo = dest_crs.isGeographic() if (dest_crs and hasattr(dest_crs, "isGeographic")) else True
        tol = 1e-5 if is_geo else 0.5

        # 2a. Check features created earlier in the current batch:
        if existing_feat_id is None:
            for c_fid, c_pt, c_x, c_y, c_uuid in created_batch_features:
                if (abs(c_x - x) <= 1e-5 and abs(c_y - y) <= 1e-5) or (abs(c_pt.x() - pt.x()) <= tol and abs(c_pt.y() - pt.y()) <= tol):
                    existing_feat_id = c_fid
                    existing_uuid = c_uuid
                    is_reused_from_batch = True
                    break

        # 2b. Check existing features in main_layer:
        if existing_feat_id is None:
            for feat in main_layer.getFeatures():
                if feat.id() in created_batch_fids:
                    continue
                # Check spatial geometry
                if feat.hasGeometry() and not feat.geometry().isEmpty():
                    try:
                        f_pt = feat.geometry().asPoint()
                        if abs(f_pt.x() - pt.x()) <= tol and abs(f_pt.y() - pt.y()) <= tol:
                            existing_feat = feat
                            existing_feat_id = feat.id()
                            break
                    except Exception:
                        pass
                # Check coordinate attributes as fallback
                if existing_feat_id is None:
                    feat_x, feat_y = None, None
                    for xf in ("longitude", "pos_longit", "sf_longitude", "x_current", "df_x_current", "x"):
                        if xf in main_field_names and feat[xf] not in (None, NULL):
                            try:
                                feat_x = float(str(feat[xf]).strip())
                                break
                            except (ValueError, TypeError):
                                pass
                    for yf in ("latitude", "pos_latitu", "sf_latitude", "y_current", "df_y_current", "y"):
                        if yf in main_field_names and feat[yf] not in (None, NULL):
                            try:
                                feat_y = float(str(feat[yf]).strip())
                                break
                            except (ValueError, TypeError):
                                pass
                    if feat_x is not None and feat_y is not None:
                        if abs(feat_x - x) <= 1e-5 and abs(feat_y - y) <= 1e-5:
                            existing_feat = feat
                            existing_feat_id = feat.id()
                            break

            # If existing feature was found at (X, Y) in main_layer, extract its UUID
            if existing_feat is not None and not existing_uuid:
                for uf in uuid_fields:
                    val = existing_feat[uf]
                    if val is not None and val != NULL:
                        s_val = str(val).strip()
                        if s_val.lower() not in ("null", "none", "nan", ""):
                            existing_uuid = s_val
                            break

        if existing_feat_id is not None:
            # Reusing / updating an existing point feature at (X, Y) or by UUID
            assigned_fid = existing_feat_id

            if not existing_uuid:
                existing_uuid = clean_uuid or str(uuid.uuid4())
                if existing_feat is not None:
                    for uf in uuid_fields:
                        idx = main_fields.indexOf(uf)
                        if idx != -1:
                            main_layer.changeAttributeValue(existing_feat_id, idx, existing_uuid)

            target_uuid = existing_uuid

            # If matched an existing feature from main_layer (not just batch cache):
            if existing_feat is not None:
                # If matched by explicit UUID with differing coordinates, update geometry
                if not is_reused_from_batch:
                    if hasattr(main_layer, "changeGeometry"):
                        main_layer.changeGeometry(existing_feat_id, new_geom)
                    elif hasattr(main_layer, "dataProvider") and hasattr(main_layer.dataProvider(), "changeGeometryValues"):
                        main_layer.dataProvider().changeGeometryValues({existing_feat_id: new_geom})

                # Ensure status is 'active' (NOT 'deleted')
                for sf in ("status", "sf_status"):
                    idx = main_fields.indexOf(sf)
                    if idx != -1:
                        main_layer.changeAttributeValue(existing_feat_id, idx, "active")

                # Update coordinates attributes
                for xf in ("longitude", "pos_longit", "sf_longitude", "x_current", "df_x_current", "x"):
                    idx = main_fields.indexOf(xf)
                    if idx != -1:
                        main_layer.changeAttributeValue(existing_feat_id, idx, str(x))

                for yf in ("latitude", "pos_latitu", "sf_latitude", "y_current", "df_y_current", "y"):
                    idx = main_fields.indexOf(yf)
                    if idx != -1:
                        main_layer.changeAttributeValue(existing_feat_id, idx, str(y))

                idx_rem = main_fields.indexOf("remarks")
                if idx_rem != -1:
                    main_layer.changeAttributeValue(existing_feat_id, idx_rem, "")

                idx_up = main_fields.indexOf("up_feature")
                if idx_up != -1:
                    main_layer.changeAttributeValue(existing_feat_id, idx_up, 1)

                idx_uploc = main_fields.indexOf("uplocation")
                if idx_uploc != -1:
                    main_layer.changeAttributeValue(existing_feat_id, idx_uploc, "1")

            reused_count += 1

        else:
            # Create and add a new feature to main_layer
            target_uuid = clean_uuid or str(uuid.uuid4())
            new_feat = QgsFeature(main_fields)
            new_feat.setGeometry(new_geom)

            # Assign UUID to appropriate field(s)
            for uf in uuid_fields:
                _set_feat_attr(new_feat, uf, target_uuid)

            # Assign coordinates to layer fields
            for xf in ("longitude", "pos_longit", "sf_longitude", "x_current", "df_x_current", "x"):
                if xf in main_field_names:
                    _set_feat_attr(new_feat, xf, str(x))

            for yf in ("latitude", "pos_latitu", "sf_latitude", "y_current", "df_y_current", "y"):
                if yf in main_field_names:
                    _set_feat_attr(new_feat, yf, str(y))

            # Assign status as 'active' (NOT 'deleted')
            for sf in ("status", "sf_status"):
                if sf in main_field_names:
                    _set_feat_attr(new_feat, sf, "active")

            if "up_feature" in main_field_names:
                _set_feat_attr(new_feat, "up_feature", 1)
            if "uplocation" in main_field_names:
                _set_feat_attr(new_feat, "uplocation", "1")

            # Copy other matching attributes from row (excluding empty/null placeholders and UUID/coordinate fields)
            for attr_k, attr_v in row_info["attributes"].items():
                if attr_v is None or str(attr_v).strip().lower() in ("null", "none", "nan", ""):
                    continue
                clean_k = attr_k
                if clean_k.startswith("df_") or clean_k.startswith("sf_"):
                    clean_k = clean_k[3:]
                if clean_k.lower() in ("map_uuid", "uuid", "x_current", "y_current", "longitude", "latitude", "x", "y"):
                    continue
                for target_k in (attr_k, clean_k, f"sf_{clean_k}"):
                    if target_k in main_field_names:
                        try:
                            _set_feat_attr(new_feat, target_k, attr_v)
                        except Exception:
                            pass

            if hasattr(main_layer, "addFeature"):
                main_layer.addFeature(new_feat)
            elif hasattr(main_layer, "addFeatures"):
                main_layer.addFeatures([new_feat])
            elif hasattr(main_layer, "dataProvider") and hasattr(main_layer.dataProvider(), "addFeatures"):
                main_layer.dataProvider().addFeatures([new_feat])
            assigned_fid = new_feat.id()
            if assigned_fid is not None:
                created_batch_fids.add(assigned_fid)
                created_batch_features.append((assigned_fid, pt, x, y, target_uuid))

            created_count += 1

        col_dict = {
            "sf_map_uuid": target_uuid,
            "df_map_uuid": target_uuid,
            "map_uuid": target_uuid,
            "sf_fid": assigned_fid,
            "sf_longitude": str(x),
            "sf_latitude": str(y),
            "df_x_current": str(x),
            "df_y_current": str(y),
            "x_current": str(x),
            "y_current": str(y),
            "sf_status": "active",
            "status": "active",
        }

        # Register updates under row index and candidate keys
        updated_values[r] = col_dict
        updated_values[str(r)] = col_dict
        if target_uuid:
            updated_values[target_uuid] = col_dict
            updated_values[target_uuid.lower()] = col_dict
        if row_info.get("df_fid") is not None:
            updated_values[row_info["df_fid"]] = col_dict
            updated_values[str(row_info["df_fid"])] = col_dict
        if row_info.get("feat_fid") is not None:
            updated_values[row_info["feat_fid"]] = col_dict
            updated_values[str(row_info["feat_fid"])] = col_dict
        if row_info.get("source_fid") is not None:
            updated_values[row_info["source_fid"]] = col_dict
            updated_values[str(row_info["source_fid"])] = col_dict
        if row_info.get("err_fid") is not None:
            updated_values[row_info["err_fid"]] = col_dict
            updated_values[str(row_info["err_fid"])] = col_dict
        if target_fids and r < len(target_fids):
            updated_values[target_fids[r]] = col_dict

        fixed_count += 1

    # Commit changes directly back to the Form 2 GeoJSON data source
    if fixed_count > 0:
        if not main_layer.commitChanges():
            return {
                "success": False,
                "fixed_count": 0,
                "updated_values": {},
                "message": "Failed to commit changes to Form 2 Building Points (.geojson).",
            }
        # Keep layer editable for further workflow or Save Changes clicks
        main_layer.startEditing()
        main_layer.triggerRepaint()

        # Refresh map canvas if dialog / iface available
        dlg = kwargs.get("dialog") or dialog
        if dlg and hasattr(dlg, "iface") and dlg.iface and hasattr(dlg.iface, "mapCanvas") and dlg.iface.mapCanvas():
            try:
                dlg.iface.mapCanvas().refresh()
            except Exception:
                pass
    elif main_layer.isEditable():
        main_layer.rollBack()

    if fixed_count == 0 and failed_rows:
        bad_r, bad_x, bad_y = failed_rows[0]
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": (
                f"Row #{bad_r + 1} has coordinates ({bad_x}, {bad_y}) in df_x_current / df_y_current.\n\n"
                "A point cannot be generated with (0, 0) or missing coordinates. "
                "Please ensure valid GPS coordinates exist in this row."
            ),
        }

    summary_parts = []
    if created_count > 0:
        summary_parts.append(f"{created_count} point(s) created")
    if reused_count > 0:
        summary_parts.append(f"{reused_count} existing point(s) linked")
    summary_str = f" ({', '.join(summary_parts)})" if summary_parts else ""

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Successfully processed {fixed_count} feature(s){summary_str} in Form 2 Building Points (.geojson).",
    }


def generate_point_geometry(
    dialog: Any,
    val_id: str,
    layer: Any,
    table: Any,
) -> None:
    """
    Process handler for generating point geometry on checked table rows.
    Keeps all algorithmic processing inside cbms_mv_fix.py.
    """
    if hasattr(dialog, "_fix_selected_features"):
        dialog._fix_selected_features("mv_2027_hp_1a_map_uuid__missing", layer, table)


# ===========================================================================
# Unified Dispatcher: run_fix
# ===========================================================================
# Maps validation IDs to their internal fix handler functions.
_FIX_DISPATCH = {
    "mv_2027_hp_4b_ea_geocode__missing": _run_fix_ea_geocode,
    "mv_2027_hp_1a_map_uuid__missing": _run_fix_map_uuid_missing,
}


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Unified dispatcher for all CBMS MV fix algorithms.
    Routes to the correct handler based on the 'val_id' keyword argument.
    Falls back to EA geocode fix if val_id is not provided (backward compatible).
    """
    val_id = kwargs.pop("val_id", None)

    handler = _FIX_DISPATCH.get(val_id, _run_fix_ea_geocode)
    return handler(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        **kwargs,
    )


# ===========================================================================
# Fix 3: Soft Delete Process: delete_selected_features, mark_feature_deleted, sync_feature_status
# ===========================================================================
def delete_selected_features(
    dialog: Any,
    val_id: str,
    layer: Any,
    table: Any,
    combo_actions: Optional[Any] = None,
    btn_actions: Optional[Any] = None,
    btn_update_selected: Optional[Any] = None,
) -> None:
    """Batch mark all checked features as 'deleted' in the status column."""
    if not is_valid_qobject(dialog) or not is_valid_qobject(table):
        return
    checked_rows = []
    for r in range(table.rowCount()):
        item0 = table.item(r, 0)
        if item0 and item0.checkState() == Qt.Checked:
            checked_rows.append(r)

    if not checked_rows:
        if QMessageBox:
            QMessageBox.information(dialog, "No Selection", "Please check at least one row using the checkboxes.")
        return

    if QMessageBox:
        reply = QMessageBox.question(
            dialog,
            "Delete Selected Features",
            f"Are you sure you want to mark {len(checked_rows)} selected feature(s) as 'deleted' in the status column?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

    # Ensure main building points layer is loaded and editable
    try:
        main_layer = dialog._get_or_load_main_building_layer() if hasattr(dialog, "_get_or_load_main_building_layer") else None
        if main_layer and main_layer.isValid() and not main_layer.isEditable():
            main_layer.startEditing()
    except Exception as exc:
        if hasattr(dialog, "_log_error"):
            dialog._log_error(f"Error accessing main building points layer: {exc}")
        main_layer = None

    if layer and layer.isValid() and not layer.isEditable():
        try:
            layer.startEditing()
        except Exception:
            pass

    deleted_count = 0
    for r in checked_rows:
        item0 = table.item(r, 0)
        if not item0:
            continue
        s_fid = item0.data(Qt.UserRole)
        u_str = item0.data(Qt.UserRole + 1)
        e_fid = item0.data(Qt.UserRole + 3)

        # Find action button if present in row
        row_del_btn = None
        act_w = table.cellWidget(r, table.columnCount() - 1)
        if act_w:
            for child in act_w.findChildren(QPushButton):
                if child.text() in ("Delete", "Deleted"):
                    row_del_btn = child
                    break

        mark_feature_deleted(
            dialog,
            val_id,
            layer,
            table,
            source_fid=s_fid,
            map_uuid=u_str,
            err_fid=e_fid,
            button=row_del_btn,
            prompt_confirm=False,
            target_status="deleted",
            target_row=r,
        )
        item0.setCheckState(Qt.Unchecked)
        deleted_count += 1

    if combo_actions:
        combo_actions.setItemText(0, "Actions")
    elif btn_actions:
        btn_actions.setText("Actions ▾")
    if btn_update_selected:
        btn_update_selected.setText("Update Selected")
        btn_update_selected.setEnabled(False)

    if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
        dialog.lbl_footer_status.setText(
            f"Marked {deleted_count} feature(s) as 'deleted' in status column (Press Ctrl+S to save)"
        )
    if hasattr(dialog, "iface") and dialog.iface and dialog.iface.mapCanvas():
        dialog.iface.mapCanvas().refresh()


def mark_feature_deleted(
    dialog: Any,
    val_id: str,
    layer: Any,
    table: Any,
    source_fid: Any = None,
    map_uuid: Optional[str] = None,
    err_fid: Any = None,
    button: Optional[Any] = None,
    prompt_confirm: bool = True,
    target_status: Optional[str] = None,
    target_row: Optional[int] = None,
) -> None:
    """
    Mark a single feature as 'deleted' in its status column.
    Updates the QTableWidget cell, the memory result layer, and the primary
    Geotagged Building Points layer (ready for Ctrl+S persistence).
    """
    if not is_valid_qobject(dialog) or not is_valid_qobject(table):
        return

    # 1. Locate target row in table dynamically to be immune against sorting/filtering
    if target_row is None:
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if not item0:
                continue
            r_err_fid = item0.data(Qt.UserRole + 3)
            r_source_fid = item0.data(Qt.UserRole)
            r_uuid = str(item0.data(Qt.UserRole + 1) or "").strip()

            if err_fid is not None and r_err_fid == err_fid:
                target_row = r
                break
            if source_fid is not None and r_source_fid == source_fid:
                target_row = r
                break
            if map_uuid and r_uuid == str(map_uuid).strip():
                target_row = r
                break

    # 2. Locate status column in table
    status_col_idx = None
    for c in range(1, table.columnCount() - 1):
        h_it = table.horizontalHeaderItem(c)
        h_text = h_it.text().strip().lower() if h_it else ""
        if h_text in ("status", "sf_status"):
            status_col_idx = c
            break

    # If table doesn't have status or sf_status column, insert it before Action
    if status_col_idx is None:
        act_col = table.columnCount() - 1
        table.insertColumn(act_col)
        if QTableWidgetItem:
            table.setHorizontalHeaderItem(act_col, QTableWidgetItem("sf_status"))
        status_col_idx = act_col
        table.setProperty("is_populating", True)
        try:
            for r in range(table.rowCount()):
                b_item = QTableWidgetItem("") if QTableWidgetItem else None
                if b_item:
                    b_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                    table.setItem(r, status_col_idx, b_item)
        finally:
            table.setProperty("is_populating", False)

    # 3. Determine current status and new status
    current_status = ""
    if target_row is not None and status_col_idx is not None:
        c_item = table.item(target_row, status_col_idx)
        if c_item:
            current_status = c_item.text().strip().lower()

    is_currently_deleted = (current_status == "deleted")
    if target_status is not None:
        new_status = target_status
    elif is_currently_deleted:
        if prompt_confirm and QMessageBox:
            reply = QMessageBox.question(
                dialog,
                "Restore Feature?",
                f"Feature FID #{source_fid or err_fid} is currently marked as 'deleted'.\n\n"
                f"Do you want to restore this feature and clear its status?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        new_status = ""
    else:
        new_status = "deleted"

    # 4. Update QTableWidget cell
    if target_row is not None and status_col_idx is not None:
        cell_item = table.item(target_row, status_col_idx)
        if not cell_item:
            cell_item = QTableWidgetItem() if QTableWidgetItem else None
            if cell_item:
                cell_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                table.setItem(target_row, status_col_idx, cell_item)

        if cell_item:
            table.setProperty("is_populating", True)
            try:
                cell_item.setText(new_status)
                if hasattr(dialog, "_style_table_cell"):
                    if new_status.lower() == "deleted":
                        dialog._style_table_cell(cell_item, "deleted")
                    else:
                        dialog._style_table_cell(cell_item, "normal")
            finally:
                table.setProperty("is_populating", False)

    # 5. Update Result Memory Layer
    if layer and hasattr(layer, "isValid") and layer.isValid():
        f_idx = -1
        for fld in layer.fields():
            if fld.name().lower() in ("status", "sf_status"):
                f_idx = layer.fields().indexOf(fld.name())
                break
        if f_idx == -1:
            try:
                layer.dataProvider().addAttributes([QgsField("sf_status", QVariant.String)])
                layer.updateFields()
                f_idx = layer.fields().indexOf("sf_status")
            except Exception:
                pass

        if f_idx != -1:
            if not layer.isEditable():
                layer.startEditing()
            target_f_id = err_fid if err_fid is not None else source_fid
            layer.changeAttributeValue(target_f_id, f_idx, new_status)

    # 6. Update Primary Geotagged Building Points Layer
    main_layer = dialog._get_or_load_main_building_layer() if hasattr(dialog, "_get_or_load_main_building_layer") else None
    if main_layer and hasattr(main_layer, "isValid") and main_layer.isValid():
        main_feat = dialog._find_main_feature(main_layer, fid=source_fid, map_uuid=map_uuid) if hasattr(dialog, "_find_main_feature") else None
        if main_feat:
            m_idx = -1
            for fld in main_layer.fields():
                if fld.name().lower() in ("status", "sf_status"):
                    m_idx = main_layer.fields().indexOf(fld.name())
                    break
            if m_idx == -1:
                try:
                    main_layer.dataProvider().addAttributes([QgsField("status", QVariant.String)])
                    main_layer.updateFields()
                    m_idx = main_layer.fields().indexOf("status")
                except Exception:
                    pass

            if m_idx != -1:
                if not main_layer.isEditable():
                    main_layer.startEditing()
                main_layer.changeAttributeValue(main_feat.id(), m_idx, new_status)

    # 7. Update Button Text & Style
    if not button and target_row is not None:
        act_w = table.cellWidget(target_row, table.columnCount() - 1)
        if act_w:
            for child in act_w.findChildren(QPushButton):
                if child.text() in ("Delete", "Deleted"):
                    button = child
                    break

    if button:
        is_del = (new_status.lower() == "deleted")
        button.setText("Deleted" if is_del else "Delete")
        if hasattr(dialog, "_style_row_delete_button"):
            dialog._style_row_delete_button(button, is_deleted=is_del)

    # 8. Update Footer Status
    if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
        if new_status.lower() == "deleted":
            dialog.lbl_footer_status.setText(
                f"Marked feature FID #{source_fid or err_fid} as 'deleted' in status column (Press Ctrl+S to save)"
            )
        else:
            dialog.lbl_footer_status.setText(
                f"Restored status for feature FID #{source_fid or err_fid} (Press Ctrl+S to save)"
            )

    if hasattr(dialog, "iface") and dialog.iface and dialog.iface.mapCanvas():
        dialog.iface.mapCanvas().refresh()


def sync_feature_status(
    dialog: Any,
    val_id: str,
    source_fid: Any = None,
    map_uuid: Optional[str] = None,
    new_status: str = "deleted",
) -> None:
    """
    Synchronize a status update initiated from outside the table (e.g. Review Dock)
    into the corresponding result layer tab's QTableWidget.
    """
    tabs = getattr(dialog, "results_tab_widget", None) or getattr(dialog, "tab_results", None)
    if not tabs:
        return

    target_table = None
    for table in tabs.findChildren(QTableWidget):
        p = table.parent()
        while p and p != tabs:
            if p.property("val_id") == val_id:
                target_table = table
                break
            p = p.parent()
        if target_table:
            break

    if target_table:
        table = target_table
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if not item0:
                continue
            r_fid = item0.data(Qt.UserRole)
            r_uuid = str(item0.data(Qt.UserRole + 1) or "").strip()
            if (source_fid is not None and str(r_fid) == str(source_fid)) or (map_uuid and r_uuid == str(map_uuid).strip()):
                status_col_idx = None
                for c in range(1, table.columnCount() - 1):
                    h_it = table.horizontalHeaderItem(c)
                    h_text = h_it.text().strip().lower() if h_it else ""
                    if h_text in ("status", "sf_status"):
                        status_col_idx = c
                        break
                if status_col_idx is not None:
                    cell_item = table.item(r, status_col_idx)
                    if not cell_item and QTableWidgetItem:
                        cell_item = QTableWidgetItem()
                        cell_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                        table.setItem(r, status_col_idx, cell_item)
                    if cell_item:
                        table.setProperty("is_populating", True)
                        try:
                            cell_item.setText(new_status)
                            if hasattr(dialog, "_style_table_cell"):
                                if new_status.lower() == "deleted":
                                    dialog._style_table_cell(cell_item, "deleted")
                                else:
                                    dialog._style_table_cell(cell_item, "normal")
                        finally:
                            table.setProperty("is_populating", False)
                break


# ===========================================================================
# Fix 4 / Process 5: Deduplicate Features (mv_2027_hp_4a_longitude__duplicate)
# ===========================================================================
def deduplicate_features(
    dialog: Any,
    val_id: str,
    layer: Any,
    table: Any,
    combo_actions: Optional[Any] = None,
    btn_actions: Optional[Any] = None,
    btn_update_selected: Optional[Any] = None,
    process_all: bool = False,
    prompt_confirm: bool = True,
) -> Dict[str, Any]:
    """
    Interactive process handler for deduplicating features in the table:
    1. Compares all survey columns across features in the tab (or checked features).
       Specifically disregards sf_en_code, en_code, and df_en_code; nothing else from survey attributes.
       Checks all other columns (including sf_map_uuid, sf_bsn, sf_ean, sf_ea_geocode, sf_remarks, coordinates).
    2. Verifies if duplicate features are 100% identical in all compared columns.
    3. If identical, retains only one feature without sf_status 'deleted'.
    4. Marks all other duplicate features as 'deleted' in sf_status / status.
    5. Styles the table cells with 'deleted' (red text, light pink background).
    """
    if not is_valid_qobject(dialog) or not is_valid_qobject(table):
        return {"success": False, "fixed_count": 0, "message": "Dialog or table is not valid."}

    # Columns to check for identical values in deduplication (directly from user image / layer fields):
    # map_uuid, bsn_geoid, geocode, ea_geocode, region_code, province_code,
    # city_mun_code, barangay_code, ean, bsn, status, longitude/longitud, latitude/latitud,
    # pos_longit/pos_longitude, pos_latitu/pos_latitude.
    # Excludes sf_en_code / en_code / df_en_code, remarks, and technical/join columns.
    DEDUPLICATION_CHECK_COLS = {
        "map_uuid",
        "bsn_geoid",
        "geocode",
        "ea_geocode",
        "region_code",
        "province_code",
        "city_mun_code",
        "barangay_code",
        "ean",
        "bsn",
        "status",
        "longitude",
        "longitud",
        "latitude",
        "latitud",
        "pos_longit",
        "pos_longitude",
        "pos_latitu",
        "pos_latitude",
    }

    def _is_deduplication_check_col(col_name: str) -> bool:
        c = str(col_name).strip().lower()
        base_c = c[3:] if c.startswith(("sf_", "df_")) else c
        return base_c in DEDUPLICATION_CHECK_COLS

    # Determine which rows to process
    checked_rows = []
    for r in range(table.rowCount()):
        item0 = table.item(r, 0)
        if item0 and item0.checkState() == Qt.Checked:
            checked_rows.append(r)

    if checked_rows and not process_all:
        rows_to_process = checked_rows
    else:
        rows_to_process = list(range(table.rowCount()))

    if len(rows_to_process) < 2:
        if QMessageBox:
            QMessageBox.information(
                dialog,
                "Cannot Deduplicate",
                "At least 2 features are required to check for duplicate coordinates and identical columns.",
            )
        return {"success": False, "fixed_count": 0, "message": "Fewer than 2 rows to process."}

    # Identify compared columns from table headers matching image specification
    compared_cols = []
    for c in range(1, table.columnCount() - 1):
        h_it = table.horizontalHeaderItem(c)
        h_name = h_it.text().strip() if h_it else ""
        if _is_deduplication_check_col(h_name):
            compared_cols.append((c, h_name))

    # Fallback to non-technical columns if none of the standard names match headers
    if not compared_cols:
        for c in range(1, table.columnCount() - 1):
            h_it = table.horizontalHeaderItem(c)
            h_name = h_it.text().strip() if h_it else ""
            c_low = h_name.lower()
            if not c_low.startswith(("dup_", "sf_status", "status", "fid", "err_fid", "_orig", "action")) \
               and c_low not in ("", "#", "distance", "sf_en_code", "en_code", "df_en_code", "sf_remarks", "remarks"):
                compared_cols.append((c, h_name))

    # -----------------------------------------------------------------------
    # Dual Checking Setup:
    # Check A: Coordinate Duplicate Check (map_uuid, bsn_geoid, longitude [7 decimals], latitude [7 decimals])
    # Check B: Full Survey Attributes Check (all columns matching, floats to 7 decimals)
    # -----------------------------------------------------------------------

    # Map column headers to coordinate / identifier roles
    lon_cols = []
    lat_cols = []
    uuid_cols = []
    bsn_geoid_cols = []
    ea_cols = []
    bsn_cols = []
    status_cols = []

    for c in range(1, table.columnCount() - 1):
        h_it = table.horizontalHeaderItem(c)
        h_name = h_it.text().strip() if h_it else ""
        c_low = h_name.lower()
        base_c = c_low[3:] if c_low.startswith(("sf_", "df_")) else c_low

        if base_c in ("longitude", "longitud", "pos_longitude", "pos_longit"):
            lon_cols.append(c)
        elif base_c in ("latitude", "latitud", "pos_latitude", "pos_latitu"):
            lat_cols.append(c)
        elif base_c in ("map_uuid", "uuid"):
            uuid_cols.append(c)
        elif base_c == "bsn_geoid":
            bsn_geoid_cols.append(c)
        elif base_c == "ea_geocode":
            ea_cols.append(c)
        elif base_c == "bsn":
            bsn_cols.append(c)
        elif base_c in ("status", "sf_status"):
            status_cols.append(c)

    # Extract signatures for both checks for each row
    row_coord_sigs: Dict[int, Tuple[str, str, str, str, str]] = {}
    row_attr_sigs: Dict[int, Tuple] = {}

    for r in rows_to_process:
        item0 = table.item(r, 0)
        source_fid = item0.data(Qt.UserRole) if item0 else None
        uuid_data = item0.data(Qt.UserRole + 1) if item0 else None
        err_fid = item0.data(Qt.UserRole + 3) if item0 else None

        # Fetch backing layer feature if accessible
        feat = None
        if layer and hasattr(layer, "getFeature"):
            try:
                if err_fid is not None:
                    feat = layer.getFeature(err_fid)
                if (not feat or not feat.isValid()) and source_fid is not None:
                    feat = layer.getFeature(source_fid)
            except Exception:
                feat = None

        # 1. map_uuid
        r_uuid = ""
        for c in uuid_cols:
            txt = table.item(r, c).text().strip() if table.item(r, c) else ""
            if txt and txt.lower() not in ("null", "none"):
                r_uuid = txt
                break
        if not r_uuid and uuid_data:
            r_uuid = str(uuid_data).strip()
        if not r_uuid and feat:
            f_uuid, _ = _extract_feature_id_sig(feat)
            r_uuid = f_uuid

        # 2. bsn_geoid
        r_bsn_geoid = ""
        for c in bsn_geoid_cols:
            txt = table.item(r, c).text().strip() if table.item(r, c) else ""
            if txt and txt.lower() not in ("null", "none"):
                r_bsn_geoid = txt
                break
        if not r_bsn_geoid and ea_cols and bsn_cols:
            ea_txt = table.item(r, ea_cols[0]).text().strip() if table.item(r, ea_cols[0]) else ""
            bsn_txt = table.item(r, bsn_cols[0]).text().strip() if table.item(r, bsn_cols[0]) else ""
            if ea_txt and bsn_txt:
                r_bsn_geoid = f"{ea_txt}{bsn_txt}"
        if not r_bsn_geoid and feat:
            _, f_bsn_geoid = _extract_feature_id_sig(feat)
            r_bsn_geoid = f_bsn_geoid

        # 3. coordinates (longitude, latitude) normalized strictly to 7 decimals
        r_lon = ""
        for c in lon_cols:
            txt = table.item(r, c).text().strip() if table.item(r, c) else ""
            if txt:
                norm_c = _normalize_coordinate(txt, precision=7)
                if norm_c:
                    r_lon = norm_c
                    break

        r_lat = ""
        for c in lat_cols:
            txt = table.item(r, c).text().strip() if table.item(r, c) else ""
            if txt:
                norm_c = _normalize_coordinate(txt, precision=7)
                if norm_c:
                    r_lat = norm_c
                    break

        if feat and (not r_lon or not r_lat):
            f_lon, f_lat = _extract_feature_coord_sig(feat, precision=7)
            if not r_lon:
                r_lon = f_lon
            if not r_lat:
                r_lat = f_lat

        # 4. workflow status check
        r_status = ""
        for c in status_cols:
            txt = table.item(r, c).text().strip() if table.item(r, c) else ""
            if txt and txt.lower() not in ("null", "none", "deleted"):
                r_status = txt.lower()
                break

        row_coord_sigs[r] = (r_uuid, r_bsn_geoid, r_lon, r_lat, r_status)

        # Full survey attributes signature
        row_attr_sigs[r] = tuple(
            (h_name, _normalize_cell_val(table.item(r, c).text() if table.item(r, c) else "", precision=7))
            for c, h_name in compared_cols
        )

    # Check A: Group by 4 key coordinate fields (map_uuid, bsn_geoid, lon_7dec, lat_7dec)
    coord_groups: Dict[Tuple, List[int]] = {}
    for r in rows_to_process:
        csig = row_coord_sigs.get(r)
        if csig and csig[0] and csig[1] and csig[2] and csig[3]:
            ckey = (csig[0], csig[1], csig[2], csig[3])
            if ckey not in coord_groups:
                coord_groups[ckey] = []
            coord_groups[ckey].append(r)

    # Exclude groups where features have conflicting workflow statuses (e.g. verified vs pending)
    coord_dup_groups = []
    for ckey, r_list in coord_groups.items():
        if len(r_list) > 1:
            active_statuses = {row_coord_sigs[r][4] for r in r_list if row_coord_sigs[r][4]}
            if len(active_statuses) <= 1:
                coord_dup_groups.append(r_list)

    # Check B: Group by all compared survey columns
    attr_groups: Dict[Tuple, List[int]] = {}
    for r in rows_to_process:
        asig = row_attr_sigs.get(r)
        if asig:
            if asig not in attr_groups:
                attr_groups[asig] = []
            attr_groups[asig].append(r)
    attr_dup_groups = [r_list for r_list in attr_groups.values() if len(r_list) > 1]

    # Combine duplicate groups from both checks
    dup_groups = []
    dup_type_desc = ""
    grouped_rows = set()

    for g in coord_dup_groups:
        dup_groups.append(g)
        grouped_rows.update(g)

    for g in attr_dup_groups:
        new_g = [r for r in g if r not in grouped_rows]
        if len(new_g) > 1:
            dup_groups.append(new_g)
            grouped_rows.update(new_g)

    if coord_dup_groups and (len(dup_groups) == len(coord_dup_groups)):
        dup_type_desc = "duplicate coordinates (matching map_uuid, bsn_geoid, longitude, and latitude up to 7 decimal places)"
    elif attr_dup_groups and not coord_dup_groups:
        dup_type_desc = "identical survey attributes across all columns"
    else:
        dup_type_desc = "duplicate coordinates (7 decimals) and identical survey attributes"

    if not dup_groups:
        diff_cols = []
        # Check coordinate differences
        lon_vals = {row_coord_sigs[r][2] for r in rows_to_process if r in row_coord_sigs and row_coord_sigs[r][2]}
        lat_vals = {row_coord_sigs[r][3] for r in rows_to_process if r in row_coord_sigs and row_coord_sigs[r][3]}
        uuid_vals = {row_coord_sigs[r][0] for r in rows_to_process if r in row_coord_sigs and row_coord_sigs[r][0]}
        bsn_vals = {row_coord_sigs[r][1] for r in rows_to_process if r in row_coord_sigs and row_coord_sigs[r][1]}

        if len(lon_vals) > 1:
            diff_cols.append(f"• Longitude (7 decimals): {', '.join(repr(v) for v in list(lon_vals)[:3])}")
        if len(lat_vals) > 1:
            diff_cols.append(f"• Latitude (7 decimals): {', '.join(repr(v) for v in list(lat_vals)[:3])}")
        if len(bsn_vals) > 1:
            diff_cols.append(f"• bsn_geoid: {', '.join(repr(v) for v in list(bsn_vals)[:3])}")
        if len(uuid_vals) > 1:
            diff_cols.append(f"• map_uuid: {', '.join(repr(v) for v in list(uuid_vals)[:3])}")

        for c, h_name in compared_cols:
            vals = set(
                _normalize_cell_val(table.item(r, c).text() if table.item(r, c) else "", precision=7)
                for r in rows_to_process
            )
            if len(vals) > 1 and h_name.lower() not in (
                "longitude", "latitude", "sf_longitude", "sf_latitude",
                "sf_map_uuid", "map_uuid", "sf_bsn_geoid", "bsn_geoid"
            ):
                vals_preview = list(vals)[:3]
                diff_cols.append(f"• {h_name}: {', '.join(repr(v) for v in vals_preview)}")

        diff_details = "\n".join(diff_cols[:6])
        if len(diff_cols) > 6:
            diff_details += f"\n... and {len(diff_cols) - 6} more column(s)"

        msg = (
            "The features in this tab do not match duplicate criteria (checked duplicate coordinates on map_uuid, bsn_geoid, longitude, and latitude to 7 decimals, as well as identical survey columns).\n\n"
            f"Differences were detected in:\n{diff_details}\n\n"
            "Features with differing survey data will not be marked as deleted automatically."
        ) if diff_cols else (
            "No duplicate features matching coordinate check (7 decimals) or identical survey columns were found."
        )

        if QMessageBox:
            QMessageBox.warning(dialog, "Features Not Identical", msg)
        if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
            dialog.lbl_footer_status.setText("Deduplication skipped: Features differ across columns or coordinates.")
        return {"success": False, "fixed_count": 0, "message": msg}

    total_to_delete = sum(len(r_list) - 1 for r_list in dup_groups)
    retained_count = len(dup_groups)

    if prompt_confirm and QMessageBox:
        reply = QMessageBox.question(
            dialog,
            "Deduplicate Features",
            f"Found {len(dup_groups)} group(s) of duplicate features ({dup_type_desc}).\n\n"
            f"• Retain active: {retained_count} feature(s) (without 'deleted' status)\n"
            f"• Mark as 'deleted': {total_to_delete} duplicate feature(s)\n\n"
            f"Do you want to proceed and mark the duplicates as 'deleted' in sf_status?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return {"success": False, "fixed_count": 0, "message": "Operation cancelled by user."}

    # Ensure main building points layer is loaded and editable
    try:
        main_layer = dialog._get_or_load_main_building_layer() if hasattr(dialog, "_get_or_load_main_building_layer") else None
        if main_layer and main_layer.isValid() and not main_layer.isEditable():
            main_layer.startEditing()
    except Exception as exc:
        if hasattr(dialog, "_log_error"):
            dialog._log_error(f"Error accessing main building points layer: {exc}")
        main_layer = None

    if layer and layer.isValid() and not layer.isEditable():
        try:
            layer.startEditing()
        except Exception:
            pass

    deleted_count = 0
    updated_values = {}

    for r_list in dup_groups:
        # Retain first feature: ensure its status is not 'deleted'
        retained_row = r_list[0]
        item_ret = table.item(retained_row, 0)
        if item_ret:
            ret_s_fid = item_ret.data(Qt.UserRole)
            ret_uuid = item_ret.data(Qt.UserRole + 1)
            ret_err_fid = item_ret.data(Qt.UserRole + 3)
            for c in range(1, table.columnCount() - 1):
                h_it = table.horizontalHeaderItem(c)
                if h_it and h_it.text().strip().lower() in ("status", "sf_status"):
                    sc_item = table.item(retained_row, c)
                    if sc_item and sc_item.text().strip().lower() == "deleted":
                        mark_feature_deleted(
                            dialog,
                            val_id,
                            layer,
                            table,
                            source_fid=ret_s_fid,
                            map_uuid=ret_uuid,
                            err_fid=ret_err_fid,
                            prompt_confirm=False,
                            target_status="",
                            target_row=retained_row,
                        )
                    break

        # Mark all duplicate features as 'deleted'
        for r in r_list[1:]:
            item0 = table.item(r, 0)
            if not item0:
                continue
            s_fid = item0.data(Qt.UserRole)
            u_str = item0.data(Qt.UserRole + 1)
            e_fid = item0.data(Qt.UserRole + 3)

            # Find action button if present
            row_del_btn = None
            act_w = table.cellWidget(r, table.columnCount() - 1)
            if act_w:
                for child in act_w.findChildren(QPushButton):
                    if child.text() in ("Delete", "Deleted"):
                        row_del_btn = child
                        break

            mark_feature_deleted(
                dialog,
                val_id,
                layer,
                table,
                source_fid=s_fid,
                map_uuid=u_str,
                err_fid=e_fid,
                button=row_del_btn,
                prompt_confirm=False,
                target_status="deleted",
                target_row=r,
            )
            item0.setCheckState(Qt.Unchecked)
            deleted_count += 1
            updated_values[s_fid or r] = {"sf_status": "deleted"}
            if u_str:
                updated_values[u_str] = {"sf_status": "deleted"}

    if combo_actions:
        combo_actions.setItemText(0, "Actions")
    elif btn_actions:
        btn_actions.setText("Actions ▾")
    if btn_update_selected:
        btn_update_selected.setText("Update Selected")
        btn_update_selected.setEnabled(False)

    if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
        dialog.lbl_footer_status.setText(
            f"Deduplicated features: Retained {retained_count} active feature(s), "
            f"marked {deleted_count} duplicate(s) as 'deleted' in sf_status (Press Ctrl+S to save)"
        )
    if hasattr(dialog, "iface") and dialog.iface and dialog.iface.mapCanvas():
        dialog.iface.mapCanvas().refresh()

    return {
        "success": True,
        "fixed_count": deleted_count,
        "updated_values": updated_values,
        "message": (
            f"Successfully deduplicated features: Retained {retained_count} active feature(s) "
            f"and marked {deleted_count} duplicate feature(s) as 'deleted'."
        ),
    }


def _run_fix_longitude_duplicate(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    error_layer: Optional[QgsVectorLayer] = None,
    table: Optional[Any] = None,
    dialog: Optional[Any] = None,
    target_rows: Optional[List[int]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Automated fix algorithm for mv_2027_hp_4a_longitude__duplicate:
    Inspects features to check if all columns are identical.
    Specifically disregards sf_en_code, en_code, and df_en_code; nothing else from survey attributes.
    Retains only one feature without sf_status 'deleted', and marks all duplicate
    features as 'deleted' in sf_status / status.
    """
    if dialog is not None and table is not None and is_valid_qobject(dialog) and is_valid_qobject(table):
        return deduplicate_features(
            dialog,
            "mv_2027_hp_4a_longitude__duplicate",
            error_layer or main_layer,
            table,
            process_all=(target_rows is None or len(target_rows) == 0),
        )

    # Headless fallback on layers
    active_layer = error_layer if (error_layer and error_layer.isValid()) else main_layer
    if not active_layer or not active_layer.isValid():
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "Cannot run fix: No valid layer provided.",
        }

    # Columns to check for identical values in deduplication (directly from user image / layer fields):
    # map_uuid, bsn_geoid, geocode, ea_geocode, region_code, province_code,
    # city_mun_code, barangay_code, ean, bsn, status, longitude/longitud, latitude/latitud,
    # pos_longit/pos_longitude, pos_latitu/pos_latitude.
    # Excludes sf_en_code / en_code / df_en_code, remarks, and technical/join columns.
    DEDUPLICATION_CHECK_COLS = {
        "map_uuid",
        "bsn_geoid",
        "geocode",
        "ea_geocode",
        "region_code",
        "province_code",
        "city_mun_code",
        "barangay_code",
        "ean",
        "bsn",
        "status",
        "longitude",
        "longitud",
        "latitude",
        "latitud",
        "pos_longit",
        "pos_longitude",
        "pos_latitu",
        "pos_latitude",
    }

    def _is_deduplication_check_col(col_name: str) -> bool:
        c = str(col_name).strip().lower()
        base_c = c[3:] if c.startswith(("sf_", "df_")) else c
        return base_c in DEDUPLICATION_CHECK_COLS

    flattened_targets = _flatten_ids(target_fids or []) | _flatten_ids(target_uuids or [])
    features_to_check = []
    for feat in active_layer.getFeatures():
        if flattened_targets:
            f_ids = _flatten_ids(feat.id())
            for fn in ("sf_map_uuid", "map_uuid", "uuid", "sf_fid", "df_fid", "id"):
                try:
                    f_ids.update(_flatten_ids(feat[fn]))
                except Exception:
                    pass
            if not (f_ids & flattened_targets):
                continue
        features_to_check.append(feat)

    if len(features_to_check) < 2:
        return {
            "success": True,
            "fixed_count": 0,
            "updated_values": {},
            "message": "Fewer than 2 features found to check for duplicates.",
        }

    compared_fields = [
        f.name() for f in active_layer.fields()
        if _is_deduplication_check_col(f.name())
    ]
    if not compared_fields:
        compared_fields = [
            f.name() for f in active_layer.fields()
            if not f.name().lower().startswith(("dup_", "sf_status", "status", "fid", "err_fid", "_orig"))
            and f.name().lower() not in ("distance", "sf_en_code", "en_code", "df_en_code", "sf_remarks", "remarks")
        ]

    # Check A: Coordinate duplicate check on (map_uuid, bsn_geoid, lon_7dec, lat_7dec)
    coord_groups: Dict[Tuple, List[QgsFeature]] = {}
    for feat in features_to_check:
        f_uuid, f_bsn_geoid = _extract_feature_id_sig(feat)
        f_lon, f_lat = _extract_feature_coord_sig(feat, precision=7)
        if f_uuid and f_bsn_geoid and f_lon and f_lat:
            ckey = (f_uuid, f_bsn_geoid, f_lon, f_lat)
            if ckey not in coord_groups:
                coord_groups[ckey] = []
            coord_groups[ckey].append(feat)

    coord_dup_groups = []
    for ckey, feats in coord_groups.items():
        if len(feats) > 1:
            active_statuses = set()
            for feat in feats:
                for fn in ("status", "sf_status"):
                    try:
                        v = feat[fn]
                        if v is not None and v != NULL and str(v).strip() and str(v).strip().lower() not in ("null", "none", "deleted"):
                            active_statuses.add(str(v).strip().lower())
                    except Exception:
                        pass
            if len(active_statuses) <= 1:
                coord_dup_groups.append(feats)

    # Check B: Full survey columns check
    attr_groups: Dict[Tuple, List[QgsFeature]] = {}
    for feat in features_to_check:
        sig = tuple(
            (fname, _normalize_cell_val(feat[fname], precision=7))
            for fname in compared_fields
        )
        if sig not in attr_groups:
            attr_groups[sig] = []
        attr_groups[sig].append(feat)

    attr_dup_groups = [feats for feats in attr_groups.values() if len(feats) > 1]

    # Combine duplicate groups
    dup_groups = []
    grouped_feat_ids = set()
    for g in coord_dup_groups:
        dup_groups.append(g)
        grouped_feat_ids.update(f.id() for f in g)
    for g in attr_dup_groups:
        new_g = [f for f in g if f.id() not in grouped_feat_ids]
        if len(new_g) > 1:
            dup_groups.append(new_g)
            grouped_feat_ids.update(f.id() for f in new_g)
    if not dup_groups:
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": (
                "Features have differing values across columns and are not identical. "
                "No features were marked as deleted."
            ),
        }

    status_field_name = None
    for f in main_layer.fields():
        if f.name().lower() in ("status", "sf_status"):
            status_field_name = f.name()
            break
    if status_field_name is None:
        try:
            main_layer.dataProvider().addAttributes([QgsField("status", QVariant.String)])
            main_layer.updateFields()
            status_field_name = "status"
        except Exception:
            status_field_name = "status"

    status_idx = main_layer.fields().indexOf(status_field_name)

    if not main_layer.isEditable():
        main_layer.startEditing()

    updated_values = {}
    deleted_count = 0

    for feat_list in dup_groups:
        # feat_list[0] is retained active
        if status_idx != -1:
            curr_val = feat_list[0][status_field_name]
            if curr_val is not None and str(curr_val).strip().lower() == "deleted":
                main_layer.changeAttributeValue(feat_list[0].id(), status_idx, "")

        # Features 1..N-1 are marked as 'deleted'
        for dup_feat in feat_list[1:]:
            dup_id = dup_feat.id()
            dup_uuid = None
            for fn in ("sf_map_uuid", "map_uuid", "uuid"):
                try:
                    val = dup_feat[fn]
                    if val is not None and val != NULL and str(val).strip():
                        dup_uuid = str(val).strip()
                        break
                except Exception:
                    pass

            target_feat = None
            if active_layer == main_layer:
                target_feat = dup_feat
            else:
                for fid_col in ("sf_fid", "df_fid", "source_fid"):
                    try:
                        if fid_col in [f.name() for f in active_layer.fields()]:
                            s_fid = dup_feat[fid_col]
                            if s_fid is not None and s_fid != NULL:
                                tf = main_layer.getFeature(int(s_fid))
                                if tf and tf.isValid():
                                    target_feat = tf
                                    break
                    except Exception:
                        pass
                if not target_feat:
                    for mf in main_layer.getFeatures():
                        if mf.id() == dup_id:
                            target_feat = mf
                            break

            if target_feat and status_idx != -1:
                main_layer.changeAttributeValue(target_feat.id(), status_idx, "deleted")
                deleted_count += 1
                updated_values[dup_id] = {status_field_name: "deleted"}
                if dup_uuid:
                    updated_values[dup_uuid] = {status_field_name: "deleted"}

            if active_layer and active_layer != main_layer and active_layer.isValid():
                e_status_idx = -1
                for f in active_layer.fields():
                    if f.name().lower() in ("status", "sf_status"):
                        e_status_idx = active_layer.fields().indexOf(f.name())
                        break
                if e_status_idx != -1:
                    if not active_layer.isEditable():
                        active_layer.startEditing()
                    active_layer.changeAttributeValue(dup_feat.id(), e_status_idx, "deleted")

    return {
        "success": True,
        "fixed_count": deleted_count,
        "updated_values": updated_values,
        "message": (
            f"Successfully deduplicated features: retained 1 active feature and marked "
            f"{deleted_count} duplicate feature(s) as 'deleted' in {status_field_name}."
        ),
    }


# Register in dispatch table
_FIX_DISPATCH["mv_2027_hp_4a_longitude__duplicate"] = _run_fix_longitude_duplicate

