# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Update Datafile's Coordinates Process
Action: "Update Datafile's Coordinates"
Validation ID: update_datafiles_coordinates

Updates the Form 2 datafile coordinates (df_x_current, df_y_current)
based on the spatial building points coordinates (sf_longitude, sf_latitude).
"""
from typing import Any, Dict, List, Optional, Tuple
import os

from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsField,
    QgsGeometry,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorLayer,
)
try:
    from qgis.PyQt.QtCore import QVariant
except ImportError:
    try:
        from PyQt5.QtCore import QVariant
    except ImportError:
        QVariant = None

try:
    from .common import _flatten_ids, is_valid_qobject, make_unique_feature_key
except ImportError:
    from common import _flatten_ids, is_valid_qobject, make_unique_feature_key

FIX_ID = "update_datafiles_coordinates"
FIX_NAME = "Update Datafile's Coordinates"
FIX_DESCRIPTION = (
    "Updates the df_x_current and df_y_current columns based on the values "
    "of sf_longitude and sf_latitude columns."
)


def _extract_source_coords(feat: Any, field_names: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract source longitude and latitude from a feature.
    Prioritizes sf_longitude and sf_latitude, falling back to longitude/latitude or geometry.
    """
    lon_val = None
    lat_val = None

    # 1. Check sf_longitude / longitude
    for col in ("sf_longitude", "longitude", "x_coord", "x"):
        if col in field_names:
            try:
                v = feat.attribute(col) if hasattr(feat, "attribute") else feat[col]
                if v is not None and v != NULL:
                    s_v = str(v).strip()
                    if s_v and s_v.lower() not in ("null", "none", "nan"):
                        lon_val = s_v
                        break
            except Exception:
                pass

    # 2. Check sf_latitude / latitude
    for col in ("sf_latitude", "latitude", "y_coord", "y"):
        if col in field_names:
            try:
                v = feat.attribute(col) if hasattr(feat, "attribute") else feat[col]
                if v is not None and v != NULL:
                    s_v = str(v).strip()
                    if s_v and s_v.lower() not in ("null", "none", "nan"):
                        lat_val = s_v
                        break
            except Exception:
                pass

    # 3. Fallback to point geometry if attributes are missing/empty
    if (not lon_val or not lat_val) and hasattr(feat, "hasGeometry") and feat.hasGeometry():
        geom = feat.geometry()
        if geom and not geom.isEmpty():
            try:
                pt = geom.asPoint()
                if not lon_val:
                    lon_val = str(pt.x())
                if not lat_val:
                    lat_val = str(pt.y())
            except Exception:
                pass

    return lon_val, lat_val


def _run_fix_update_datafile_coordinates(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    error_layer: Optional[QgsVectorLayer] = None,
    table: Optional[Any] = None,
    dialog: Optional[Any] = None,
    target_rows: Optional[List[int]] = None,
    target_keys: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Automated fix algorithm: copies spatial coordinates (sf_longitude, sf_latitude)
    into the datafile coordinates (df_x_current, df_y_current) and buffers the edits
    into pending Form 2 changes so they can be saved to disk.
    """
    active_layer = error_layer if (error_layer and error_layer.isValid()) else main_layer
    if not active_layer or not active_layer.isValid():
        return {
            "success": False,
            "message": "The validation result layer is missing or could not be opened.",
            "fixed_count": 0,
            "updated_values": {},
        }

    if not active_layer.isEditable() and not active_layer.startEditing():
        return {
            "success": False,
            "message": "The validation layer could not be opened for editing.",
            "fixed_count": 0,
            "updated_values": {},
        }

    if error_layer and error_layer.isValid() and not error_layer.isEditable():
        try:
            error_layer.startEditing()
        except Exception:
            pass

    if main_layer and main_layer.isValid() and main_layer != active_layer and not main_layer.isEditable():
        try:
            main_layer.startEditing()
        except Exception:
            pass

    target_keys_set = set(target_keys) if target_keys else set()
    target_keys_lower = {str(k).strip().lower() for k in target_keys_set if k}
    is_targeted = (target_fids is not None) or (target_uuids is not None) or bool(target_keys_set)
    target_set = _flatten_ids(target_fids) | _flatten_ids(target_uuids)

    if is_targeted and not target_set and not target_keys_set:
        return {
            "success": True,
            "fixed_count": 0,
            "updated_values": {},
            "message": "No valid target ID or UUID provided.",
        }

    # Ensure df_x_current and df_y_current exist on active_layer / error_layer
    for lyr in (active_layer, error_layer):
        if lyr and lyr.isValid():
            f_names = lyr.fields().names() if hasattr(lyr.fields(), "names") else []
            f_to_add = []
            if "df_x_current" not in f_names:
                f_to_add.append(QgsField("df_x_current", QVariant.Double))
            if "df_y_current" not in f_names:
                f_to_add.append(QgsField("df_y_current", QVariant.Double))
            if f_to_add:
                try:
                    lyr.dataProvider().addAttributes(f_to_add)
                    lyr.updateFields()
                except Exception:
                    pass

    updated_values: Dict[Any, Dict[str, str]] = {}
    fixed_count = 0
    skipped_count = 0

    # Build row lookup from table if available
    row_coord_map: Dict[int, Tuple[str, str]] = {}
    if table and hasattr(table, "rowCount"):
        sf_lon_col = -1
        sf_lat_col = -1
        for col_i in range(table.columnCount()):
            hdr = table.horizontalHeaderItem(col_i)
            hdr_text = (hdr.text() if hdr else "").strip().lower()
            if hdr_text in ("sf_longitude", "sf_longitud", "pos_longitude", "pos_longit"):
                sf_lon_col = col_i
            elif hdr_text in ("sf_latitude", "sf_latitud", "pos_latitude", "pos_latitu"):
                sf_lat_col = col_i

        if sf_lon_col != -1 or sf_lat_col != -1:
            for r in range(table.rowCount()):
                t_lon = table.item(r, sf_lon_col).text().strip() if (sf_lon_col != -1 and table.item(r, sf_lon_col)) else ""
                t_lat = table.item(r, sf_lat_col).text().strip() if (sf_lat_col != -1 and table.item(r, sf_lat_col)) else ""
                if t_lon or t_lat:
                    row_coord_map[r] = (t_lon, t_lat)

    # Process features from active_layer
    field_names = active_layer.fields().names() if hasattr(active_layer.fields(), "names") else []
    for feat in active_layer.getFeatures():
        if feedback and feedback.isCanceled():
            break

        f_id = feat.id()
        feat_ids = _flatten_ids(f_id)
        feat_uuid = ""
        df_fid_val = None
        df_uuid_val = ""

        for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid", "df_map_uuid"):
            if col in field_names:
                try:
                    val = feat.attribute(col)
                    if val is not None and val != NULL:
                        feat_ids.update(_flatten_ids(val))
                        if col in ("sf_map_uuid", "map_uuid", "uuid") and not feat_uuid:
                            feat_uuid = str(val).strip()
                        if col == "df_fid" and df_fid_val is None:
                            df_fid_val = val
                        if col == "df_map_uuid" and not df_uuid_val:
                            df_uuid_val = str(val).strip()
                except Exception:
                    pass

        cand_keys = {make_unique_feature_key(fid_val, feat_uuid) for fid_val in feat_ids}
        cand_keys.discard("")
        cand_keys_lower = {k.lower() for k in cand_keys}

        if is_targeted:
            matched = bool(target_set and (feat_ids & target_set))
            if not matched and target_keys_set:
                matched = bool(cand_keys & target_keys_set) or bool(cand_keys_lower & target_keys_lower)
            if not matched:
                continue

        # Extract source coordinates (sf_longitude, sf_latitude)
        lon_val, lat_val = _extract_source_coords(feat, field_names)

        # Fallback to main_layer if missing
        if (not lon_val or not lat_val) and main_layer and main_layer.isValid() and main_layer != active_layer:
            m_field_names = main_layer.fields().names() if hasattr(main_layer.fields(), "names") else []
            for mf in main_layer.getFeatures():
                mf_ids = _flatten_ids(mf.id())
                for col in ("sf_fid", "fid", "sf_map_uuid", "map_uuid", "uuid"):
                    if col in m_field_names:
                        try:
                            v = mf.attribute(col)
                            if v is not None and v != NULL:
                                mf_ids.update(_flatten_ids(v))
                        except Exception:
                            pass
                if mf_ids & feat_ids:
                    m_lon, m_lat = _extract_source_coords(mf, m_field_names)
                    lon_val = lon_val or m_lon
                    lat_val = lat_val or m_lat
                    break

        if not lon_val or not lat_val:
            skipped_count += 1
            continue

        lon_str = str(lon_val).strip()
        lat_str = str(lat_val).strip()

        # Update df_x_current and df_y_current on active_layer
        idx_df_lon = active_layer.fields().indexOf("df_x_current")
        if idx_df_lon != -1:
            active_layer.changeAttributeValue(f_id, idx_df_lon, lon_str)

        idx_df_lat = active_layer.fields().indexOf("df_y_current")
        if idx_df_lat != -1:
            active_layer.changeAttributeValue(f_id, idx_df_lat, lat_str)

        # Also update error_layer if distinct from active_layer
        if error_layer and error_layer.isValid() and error_layer != active_layer:
            idx_err_lon = error_layer.fields().indexOf("df_x_current")
            idx_err_lat = error_layer.fields().indexOf("df_y_current")
            for ef in error_layer.getFeatures():
                ef_ids = _flatten_ids(ef.id())
                for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
                    if col in error_layer.fields().names():
                        try:
                            val = ef.attribute(col)
                            if val is not None and val != NULL:
                                ef_ids.update(_flatten_ids(val))
                        except Exception:
                            pass
                if ef_ids & feat_ids:
                    if idx_err_lon != -1:
                        error_layer.changeAttributeValue(ef.id(), idx_err_lon, lon_str)
                    if idx_err_lat != -1:
                        error_layer.changeAttributeValue(ef.id(), idx_err_lat, lat_str)
                    break

        # Register in updated_values dictionary
        payload = {
            "df_x_current": lon_str,
            "df_y_current": lat_str,
            "longitude": lon_str,
            "latitude": lat_str,
        }
        for k in feat_ids:
            updated_values[k] = payload
        for ck in cand_keys:
            updated_values[ck] = payload
            updated_values[ck.lower()] = payload

        # Direct synchronization with dialog pending JSON/CSV edits buffer
        if dialog and hasattr(dialog, "_pending_json_edits"):
            rec_uuid = df_uuid_val or feat_uuid
            rec_k = f"fid_{df_fid_val}" if df_fid_val is not None else f"uuid_{rec_uuid}"
            if rec_k not in dialog._pending_json_edits:
                dialog._pending_json_edits[rec_k] = {
                    "df_fid": df_fid_val,
                    "uuid": rec_uuid,
                    "props": {},
                }
            dialog._pending_json_edits[rec_k]["props"]["longitude"] = lon_str
            dialog._pending_json_edits[rec_k]["props"]["latitude"] = lat_str

        fixed_count += 1

    # Synchronize loaded Form 2 vector layer if present in project
    if dialog and hasattr(dialog, "project") and dialog.project:
        for lyr in dialog.project.mapLayers().values():
            if lyr.name().startswith("Form 2 ("):
                f2_fields = lyr.fields().names() if hasattr(lyr.fields(), "names") else []
                f2_lon_idx = lyr.fields().indexOf("longitude")
                f2_lat_idx = lyr.fields().indexOf("latitude")
                if f2_lon_idx != -1 or f2_lat_idx != -1:
                    if not lyr.isEditable():
                        try:
                            lyr.startEditing()
                        except Exception:
                            pass
                    for f2_feat in lyr.getFeatures():
                        f2_ids = _flatten_ids(f2_feat.id())
                        f2_u = ""
                        for col in ("map_uuid", "uuid", "fid"):
                            if col in f2_fields:
                                try:
                                    v = f2_feat.attribute(col)
                                    if v is not None and v != NULL:
                                        f2_ids.update(_flatten_ids(v))
                                        if col in ("map_uuid", "uuid") and not f2_u:
                                            f2_u = str(v).strip()
                                except Exception:
                                    pass
                        cand_f2_keys = {make_unique_feature_key(fid_val, f2_u) for fid_val in f2_ids}
                        cand_f2_keys.discard("")
                        matched_k = None
                        for k in list(f2_ids) + list(cand_f2_keys) + [k.lower() for k in cand_f2_keys]:
                            if k in updated_values:
                                matched_k = k
                                break
                        if matched_k:
                            p = updated_values[matched_k]
                            if f2_lon_idx != -1:
                                lyr.changeAttributeValue(f2_feat.id(), f2_lon_idx, p["longitude"])
                            if f2_lat_idx != -1:
                                lyr.changeAttributeValue(f2_feat.id(), f2_lat_idx, p["latitude"])

    if feedback:
        feedback.pushInfo(f"Updated Datafile coordinates for {fixed_count} feature(s).")

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": (
            f"Updated Datafile coordinates for {fixed_count} record(s)."
            if fixed_count > 0 else
            "No records updated (please make sure the selected records have valid sf_longitude and sf_latitude)."
        ),
    }


def update_datafile_coordinates(
    dialog: Any,
    *args,
    combo_actions: Optional[Any] = None,
    btn_actions: Optional[Any] = None,
    btn_update_selected: Optional[Any] = None,
    **kwargs,
) -> None:
    """
    Process handler for updating datafile coordinates on checked table rows.
    Processes the action directly regardless of validation check or file.
    """
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    action_id = "update_datafiles_coordinates"
    if hasattr(dialog, "_fix_selected_features"):
        dialog._fix_selected_features(action_id, layer, table)


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute automated fix for update_datafiles_coordinates."""
    return _run_fix_update_datafile_coordinates(
        main_layer=main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        **kwargs,
    )
