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
     Entry point: _run_fix_map_uuid_missing().

  3. Process: Unified Fix Dispatcher
     Single entry point routing any validation check ID to its fix algorithm.
     Entry point: run_fix(main_layer, val_id=..., target_fids=..., target_uuids=...).

  4. Process: Soft Delete
     Batch marks checked features as 'deleted' in the status column and synchronizes
     across table rows, in-memory layers, and the primary building points layer.
     Entry points: delete_selected_features(), mark_feature_deleted(), sync_feature_status().
"""

import datetime
import os
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
}

# Backward-compatible module-level constants (default to EA geocode fix)
FIX_ID = "mv_2027_hp_4b_ea_geocode__missing"
FIX_NAME = FIX_REGISTRY[FIX_ID]["name"]
FIX_DESCRIPTION = FIX_REGISTRY[FIX_ID]["description"]

# hp_1a constants (accessible for tests)
FIX_ID_HP_1A = "mv_2027_hp_1a_map_uuid__missing"
FIX_NAME_HP_1A = FIX_REGISTRY[FIX_ID_HP_1A]["name"]
FIX_DESCRIPTION_HP_1A = FIX_REGISTRY[FIX_ID_HP_1A]["description"]


# ---------------------------------------------------------------------------
# Shared Utilities
# ---------------------------------------------------------------------------
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

        # Find X column
        x_idx = None
        for candidate in ("df_x_current", "x_current", "sf_longitude", "longitude", "x"):
            if candidate in header_map:
                x_idx = header_map[candidate]
                break

        # Find Y column
        y_idx = None
        for candidate in ("df_y_current", "y_current", "sf_latitude", "latitude", "y"):
            if candidate in header_map:
                y_idx = header_map[candidate]
                break

        # Find UUID column
        uuid_idx = None
        for candidate in ("df_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
            if candidate in header_map:
                uuid_idx = header_map[candidate]
                break

        # Find DF_FID column
        df_fid_idx = header_map.get("df_fid") or header_map.get("fid")

        if x_idx is not None:
            it = table.item(r, x_idx)
            if it and it.text().strip():
                try:
                    row_info["x"] = float(it.text().strip())
                except (ValueError, TypeError):
                    pass

        if y_idx is not None:
            it = table.item(r, y_idx)
            if it and it.text().strip():
                try:
                    row_info["y"] = float(it.text().strip())
                except (ValueError, TypeError):
                    pass

        if uuid_idx is not None:
            it = table.item(r, uuid_idx)
            if it and it.text().strip():
                row_info["uuid"] = it.text().strip()

        if df_fid_idx is not None:
            it = table.item(r, df_fid_idx)
            if it and it.text().strip():
                row_info["df_fid"] = it.text().strip()

        # Capture other cell values
        for h_name, c_idx in header_map.items():
            it = table.item(r, c_idx)
            if it and it.text().strip():
                row_info["attributes"][h_name] = it.text().strip()

    # 2. Cross-reference or fallback with error_layer
    if error_layer is not None and (row_info["x"] is None or row_info["y"] is None or not row_info["uuid"]):
        field_names = [f.name() for f in error_layer.fields()]
        for feat in error_layer.getFeatures():
            feat_uuid = ""
            for u_col in ("df_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
                if u_col in field_names:
                    val = feat[u_col]
                    if val is not None and val != NULL:
                        feat_uuid = str(val).strip()
                        break

            feat_fid = feat["df_fid"] if "df_fid" in field_names else feat.id()

            cur_fid = target_fids[r] if (target_fids and r < len(target_fids)) else None
            cur_uuid = target_uuids[r] if (target_uuids and r < len(target_uuids)) else None

            is_match = False
            if cur_uuid:
                is_match = (feat_uuid == cur_uuid)
            elif cur_fid is not None:
                is_match = (feat_fid == cur_fid or feat.id() == cur_fid)
            elif target_uuids:
                is_match = (feat_uuid in target_uuids)
            elif target_fids:
                is_match = (feat_fid in target_fids or feat.id() in target_fids)
            elif table is None:
                is_match = True

            if is_match:
                row_info["feat_fid"] = feat.id()
                if row_info["x"] is None:
                    for xc in ("df_x_current", "x_current", "sf_longitude", "longitude", "x"):
                        if xc in field_names and feat[xc] not in (None, NULL):
                            try:
                                row_info["x"] = float(feat[xc])
                                break
                            except (ValueError, TypeError):
                                pass

                if row_info["y"] is None:
                    for yc in ("df_y_current", "y_current", "sf_latitude", "latitude", "y"):
                        if yc in field_names and feat[yc] not in (None, NULL):
                            try:
                                row_info["y"] = float(feat[yc])
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
                            row_info["attributes"][fn] = val
                break

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
    failed_rows = []

    for r in rows_to_process:
        if feedback and feedback.isCanceled():
            break

        row_info = _extract_row_data(r, table, error_layer, target_fids, target_uuids)
        x = row_info["x"]
        y = row_info["y"]
        target_uuid = row_info["uuid"]

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

        # Check if a feature with this UUID already exists in main_layer
        existing_feat_id = None
        uuid_fields = [fn for fn in main_field_names if fn.lower() in ("map_uuid", "sf_map_uuid", "uuid")]

        if target_uuid and uuid_fields:
            for feat in main_layer.getFeatures():
                for uf in uuid_fields:
                    val = feat[uf]
                    if val is not None and val != NULL and str(val).strip() == target_uuid:
                        existing_feat_id = feat.id()
                        break
                if existing_feat_id is not None:
                    break

        if existing_feat_id is not None:
            # Overwrite geometry of existing feature
            if hasattr(main_layer, "changeGeometry"):
                main_layer.changeGeometry(existing_feat_id, new_geom)
            elif hasattr(main_layer, "dataProvider") and hasattr(main_layer.dataProvider(), "changeGeometryValues"):
                main_layer.dataProvider().changeGeometryValues({existing_feat_id: new_geom})
            assigned_fid = existing_feat_id

            # CRITICAL: If the feature was previously marked 'deleted', clear/activate it!
            # CBMS validation checks exclude any features where status == 'deleted'.
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

            # Clear 'For deletion' remarks if present
            idx_rem = main_fields.indexOf("remarks")
            if idx_rem != -1:
                main_layer.changeAttributeValue(existing_feat_id, idx_rem, "")

            idx_up = main_fields.indexOf("up_feature")
            if idx_up != -1:
                main_layer.changeAttributeValue(existing_feat_id, idx_up, 1)

            idx_uploc = main_fields.indexOf("uplocation")
            if idx_uploc != -1:
                main_layer.changeAttributeValue(existing_feat_id, idx_uploc, "1")

        else:
            # Create and add a new feature to main_layer
            new_feat = QgsFeature(main_fields)
            new_feat.setGeometry(new_geom)

            # Assign UUID to appropriate field(s)
            if target_uuid:
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

            # Copy other matching attributes from row
            for attr_k, attr_v in row_info["attributes"].items():
                clean_k = attr_k
                if clean_k.startswith("df_") or clean_k.startswith("sf_"):
                    clean_k = clean_k[3:]
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

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Successfully generated and saved point geometry for {fixed_count} feature(s) in Form 2 Building Points (.geojson).",
    }


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
