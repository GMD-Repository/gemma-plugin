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
    from qgis.PyQt.QtCore import Qt, QVariant
    from qgis.PyQt.QtWidgets import QMessageBox
except ImportError:
    try:
        from PyQt5.QtCore import Qt, QVariant
        from PyQt5.QtWidgets import QMessageBox
    except ImportError:
        Qt = None
        QVariant = None
        QMessageBox = None

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
    into the datafile coordinates (df_x_current, df_y_current) strictly bounded to the
    explicitly selected/checked feature IDs or table rows.
    """
    active_layer = error_layer if (error_layer and error_layer.isValid()) else main_layer
    if not active_layer or not active_layer.isValid():
        return {
            "success": False,
            "message": "The validation result layer is missing or could not be opened.",
            "fixed_count": 0,
            "updated_values": {},
        }

    # 1. Determine which table rows to fix (Strict Selection Scope)
    rows_to_process: List[int] = []
    if target_rows is not None:
        rows_to_process = [r for r in target_rows if r is not None]
    elif table is not None and is_valid_qobject(table):
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if item0:
                is_checked = (
                    (item0.checkState() == (Qt.Checked if Qt else 2))
                    if hasattr(item0, "checkState")
                    else getattr(item0, "isChecked", lambda: False)()
                )
                if is_checked:
                    rows_to_process.append(r)
        if not rows_to_process and hasattr(table, "selectionModel") and table.selectionModel():
            selected_indexes = table.selectionModel().selectedRows()
            if selected_indexes:
                rows_to_process = [idx.row() for idx in selected_indexes]

    # Clean target sets: strictly non-empty identifiers
    clean_target_fids = {
        fid for fid in _flatten_ids(target_fids)
        if fid is not None and str(fid).strip().lower() not in ("", "none", "null", "nan")
    }
    clean_target_uuids = {
        str(u).strip().lower() for u in _flatten_ids(target_uuids)
        if u is not None and str(u).strip().lower() not in ("", "none", "null", "nan")
    }
    target_keys_set = {
        str(k).strip() for k in (target_keys or [])
        if k and str(k).strip().lower() not in ("", "none", "null", "nan")
    }
    target_keys_lower = {k.lower() for k in target_keys_set}

    # If table was provided or target_rows was explicitly passed, enforce non-empty selection
    if (table is not None or target_rows is not None) and not rows_to_process:
        parent_w = dialog or kwargs.get("parent")
        if parent_w and hasattr(parent_w, "iface") and parent_w.iface:
            parent_w = parent_w.iface.mainWindow()
        if QMessageBox and parent_w:
            QMessageBox.information(
                parent_w,
                "Nothing Selected",
                "Please tick the box or select at least one row first before applying this action.",
            )
        return {
            "success": False,
            "message": "Please tick the box or select at least one row first.",
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

    # Branch A: Process by selected table rows (UI selection scope)
    if rows_to_process and table is not None and is_valid_qobject(table):
        # Build table column map for header lookups
        header_map = {}
        for c in range(table.columnCount()):
            h_item = table.horizontalHeaderItem(c)
            h_text = h_item.text().strip().lower() if h_item else ""
            if h_text:
                header_map[h_text] = c

        for r in rows_to_process:
            if feedback and feedback.isCanceled():
                break
            item0 = table.item(r, 0)
            s_fid = item0.data(Qt.UserRole) if item0 else None
            u_str = str(item0.data(Qt.UserRole + 1) or "").strip() if item0 else ""
            e_fid = item0.data(Qt.UserRole + 3) if item0 else None
            df_f = item0.data(Qt.UserRole + 4) if item0 else None
            df_u = str(item0.data(Qt.UserRole + 5) or "").strip() if item0 else ""
            sf_f = item0.data(Qt.UserRole + 6) if item0 else None
            sf_u = str(item0.data(Qt.UserRole + 7) or "").strip() if item0 else ""

            target_idx = target_rows.index(r) if (target_rows and r in target_rows) else r
            if not s_fid and target_fids and target_idx < len(target_fids):
                s_fid = target_fids[target_idx]
            if not u_str and target_uuids and target_idx < len(target_uuids):
                u_str = str(target_uuids[target_idx] or "").strip()

            row_main_fid = sf_f if (sf_f is not None and str(sf_f).strip() not in ("", "NULL", "None")) else s_fid
            row_uuid = df_u or u_str or sf_u
            row_ukey = make_unique_feature_key(row_main_fid or df_f or e_fid, row_uuid)

            # 1. Extract source coordinates (sf_longitude, sf_latitude) from table cells
            lon_val = None
            lat_val = None
            for cand in ("sf_longitude", "longitude", "pos_longitude", "pos_longit", "x_current", "df_x_current", "x"):
                if cand in header_map:
                    it = table.item(r, header_map[cand])
                    if it and it.text().strip():
                        txt = it.text().strip()
                        if txt.lower() not in ("null", "none", "nan", ""):
                            try:
                                if abs(float(txt)) > 1e-5:
                                    lon_val = txt
                                    break
                            except (ValueError, TypeError):
                                pass

            for cand in ("sf_latitude", "latitude", "pos_latitude", "pos_latitu", "y_current", "df_y_current", "y"):
                if cand in header_map:
                    it = table.item(r, header_map[cand])
                    if it and it.text().strip():
                        txt = it.text().strip()
                        if txt.lower() not in ("null", "none", "nan", ""):
                            try:
                                if abs(float(txt)) > 1e-5:
                                    lat_val = txt
                                    break
                            except (ValueError, TypeError):
                                pass

            # 2. Fallback to error_layer feature
            ef = None
            if (not lon_val or not lat_val) and error_layer and error_layer.isValid():
                if e_fid is not None:
                    try:
                        ef = error_layer.getFeature(e_fid)
                    except Exception:
                        ef = None
                if ef and ef.isValid():
                    f_names = error_layer.fields().names() if hasattr(error_layer.fields(), "names") else []
                    m_lon, m_lat = _extract_source_coords(ef, f_names)
                    lon_val = lon_val or m_lon
                    lat_val = lat_val or m_lat

            # 3. Fallback to main_layer feature
            mf = None
            if (not lon_val or not lat_val) and main_layer and main_layer.isValid():
                if row_main_fid is not None:
                    try:
                        mf = main_layer.getFeature(row_main_fid)
                    except Exception:
                        mf = None
                if mf and mf.isValid():
                    m_field_names = main_layer.fields().names() if hasattr(main_layer.fields(), "names") else []
                    m_lon, m_lat = _extract_source_coords(mf, m_field_names)
                    lon_val = lon_val or m_lon
                    lat_val = lat_val or m_lat

            if not lon_val or not lat_val:
                continue

            lon_str = str(lon_val).strip()
            lat_str = str(lat_val).strip()

            # Update error_layer feature strictly
            if error_layer and error_layer.isValid() and e_fid is not None:
                idx_lon = error_layer.fields().indexOf("df_x_current")
                idx_lat = error_layer.fields().indexOf("df_y_current")
                if idx_lon != -1:
                    error_layer.changeAttributeValue(e_fid, idx_lon, lon_str)
                if idx_lat != -1:
                    error_layer.changeAttributeValue(e_fid, idx_lat, lat_str)

            # Update active_layer feature strictly (if distinct from error_layer)
            if active_layer and active_layer.isValid() and active_layer != error_layer and row_main_fid is not None:
                idx_lon = active_layer.fields().indexOf("df_x_current")
                idx_lat = active_layer.fields().indexOf("df_y_current")
                if idx_lon != -1:
                    active_layer.changeAttributeValue(row_main_fid, idx_lon, lon_str)
                if idx_lat != -1:
                    active_layer.changeAttributeValue(row_main_fid, idx_lat, lat_str)

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
                                matched = False
                                if df_f is not None and (f2_feat.id() == df_f or ("df_fid" in f2_fields and f2_feat["df_fid"] == df_f)):
                                    matched = True
                                elif row_uuid and ("map_uuid" in f2_fields and str(f2_feat["map_uuid"]).strip().lower() == row_uuid.lower()):
                                    matched = True
                                elif row_uuid and ("uuid" in f2_fields and str(f2_feat["uuid"]).strip().lower() == row_uuid.lower()):
                                    matched = True
                                if matched:
                                    if f2_lon_idx != -1:
                                        lyr.changeAttributeValue(f2_feat.id(), f2_lon_idx, lon_str)
                                    if f2_lat_idx != -1:
                                        lyr.changeAttributeValue(f2_feat.id(), f2_lat_idx, lat_str)
                                    break

            # Direct synchronization with dialog pending JSON/CSV edits buffer
            if dialog and hasattr(dialog, "_pending_json_edits"):
                rec_k = f"fid_{df_f}" if df_f is not None else (f"uuid_{row_uuid}" if row_uuid else None)
                if rec_k:
                    if rec_k not in dialog._pending_json_edits:
                        dialog._pending_json_edits[rec_k] = {
                            "df_fid": df_f,
                            "uuid": row_uuid,
                            "props": {},
                        }
                    dialog._pending_json_edits[rec_k]["props"]["df_x_current"] = lon_str
                    dialog._pending_json_edits[rec_k]["props"]["df_y_current"] = lat_str
                    dialog._pending_json_edits[rec_k]["props"]["x_current"] = lon_str
                    dialog._pending_json_edits[rec_k]["props"]["y_current"] = lat_str
                    dialog._pending_json_edits[rec_k]["props"]["longitude"] = lon_str
                    dialog._pending_json_edits[rec_k]["props"]["latitude"] = lat_str

            payload = {
                "df_x_current": lon_str,
                "df_y_current": lat_str,
                "x_current": lon_str,
                "y_current": lat_str,
                "longitude": lon_str,
                "latitude": lat_str,
                "df_longitude": lon_str,
                "df_latitude": lat_str,
            }
            updated_values[f"row_{r}"] = payload
            if row_ukey:
                updated_values[row_ukey] = payload
                updated_values[row_ukey.lower()] = payload
            if df_f is not None and str(df_f).strip() not in ("", "NULL", "None"):
                updated_values[df_f] = payload
                updated_values[f"fid_{df_f}"] = payload
            if row_main_fid is not None and str(row_main_fid).strip() not in ("", "NULL", "None"):
                updated_values[row_main_fid] = payload
                updated_values[f"fid_{row_main_fid}"] = payload
            if row_uuid:
                updated_values[row_uuid] = payload
                updated_values[row_uuid.lower()] = payload
            if e_fid is not None and str(e_fid).strip() not in ("", "NULL", "None"):
                updated_values[f"err_{e_fid}"] = payload

            fixed_count += 1

    # Branch B: Process by feature layer iteration (Headless / unit test scope)
    else:
        is_targeted = bool(clean_target_fids or clean_target_uuids or target_keys_set)

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
                matched = (
                    bool(feat_ids & clean_target_fids)
                    or (bool(feat_uuid) and feat_uuid.lower() in clean_target_uuids)
                    or bool(cand_keys & target_keys_set)
                    or bool(cand_keys_lower & target_keys_lower)
                )
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
                    ef_uuid = ""
                    for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
                        if col in error_layer.fields().names():
                            try:
                                val = ef.attribute(col)
                                if val is not None and val != NULL:
                                    ef_ids.update(_flatten_ids(val))
                                    if col in ("sf_map_uuid", "map_uuid", "uuid") and not ef_uuid:
                                        ef_uuid = str(val).strip()
                            except Exception:
                                pass
                    cand_ef_keys = {make_unique_feature_key(fid_val, ef_uuid) for fid_val in ef_ids}
                    cand_ef_keys.discard("")
                    cand_ef_keys_lower = {k.lower() for k in cand_ef_keys}
                    matched_ef = (
                        bool(ef_ids & clean_target_fids)
                        or (bool(ef_uuid) and ef_uuid.lower() in clean_target_uuids)
                        or bool(cand_ef_keys & target_keys_set)
                        or bool(cand_ef_keys_lower & target_keys_lower)
                    )
                    if matched_ef:
                        if idx_err_lon != -1:
                            error_layer.changeAttributeValue(ef.id(), idx_err_lon, lon_str)
                        if idx_err_lat != -1:
                            error_layer.changeAttributeValue(ef.id(), idx_err_lat, lat_str)
                        break

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
                                matched = False
                                if df_fid_val is not None and (f2_feat.id() == df_fid_val or ("df_fid" in f2_fields and f2_feat["df_fid"] == df_fid_val)):
                                    matched = True
                                elif feat_uuid and ("map_uuid" in f2_fields and str(f2_feat["map_uuid"]).strip().lower() == feat_uuid.lower()):
                                    matched = True
                                elif feat_uuid and ("uuid" in f2_fields and str(f2_feat["uuid"]).strip().lower() == feat_uuid.lower()):
                                    matched = True
                                if matched:
                                    if f2_lon_idx != -1:
                                        lyr.changeAttributeValue(f2_feat.id(), f2_lon_idx, lon_str)
                                    if f2_lat_idx != -1:
                                        lyr.changeAttributeValue(f2_feat.id(), f2_lat_idx, lat_str)
                                    break

            # Direct synchronization with dialog pending JSON/CSV edits buffer
            if dialog and hasattr(dialog, "_pending_json_edits"):
                rec_uuid = df_uuid_val or feat_uuid
                rec_k = f"fid_{df_fid_val}" if df_fid_val is not None else (f"uuid_{rec_uuid}" if rec_uuid else None)
                if rec_k:
                    if rec_k not in dialog._pending_json_edits:
                        dialog._pending_json_edits[rec_k] = {
                            "df_fid": df_fid_val,
                            "uuid": rec_uuid,
                            "props": {},
                        }
                    dialog._pending_json_edits[rec_k]["props"]["df_x_current"] = lon_str
                    dialog._pending_json_edits[rec_k]["props"]["df_y_current"] = lat_str
                    dialog._pending_json_edits[rec_k]["props"]["x_current"] = lon_str
                    dialog._pending_json_edits[rec_k]["props"]["y_current"] = lat_str
                    dialog._pending_json_edits[rec_k]["props"]["longitude"] = lon_str
                    dialog._pending_json_edits[rec_k]["props"]["latitude"] = lat_str

            payload = {
                "df_x_current": lon_str,
                "df_y_current": lat_str,
                "x_current": lon_str,
                "y_current": lat_str,
                "longitude": lon_str,
                "latitude": lat_str,
                "df_longitude": lon_str,
                "df_latitude": lat_str,
            }
            for k in feat_ids:
                updated_values[k] = payload
            for ck in cand_keys:
                updated_values[ck] = payload
                updated_values[ck.lower()] = payload

            fixed_count += 1

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
    else:
        run_fix(layer, table=table, dialog=dialog, **kwargs)


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

