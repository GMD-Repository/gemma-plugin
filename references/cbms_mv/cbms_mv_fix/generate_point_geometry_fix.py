# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Generate Point Geometry Process
Action: "Generate point geometry"
Validation ID: mv_2027_hp_1a_map_uuid__missing

Generates point geometries in the Form 2 Geotagged Building Points layer (.geojson)
from coordinates in df_x_current / df_y_current.
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple

from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorLayer,
)

try:
    from .common import is_valid_qobject, make_unique_feature_key
except ImportError:
    from common import is_valid_qobject, make_unique_feature_key

FIX_ID = "mv_2027_hp_1a_map_uuid__missing"
FIX_NAME = "Generate point geometry from df_x_current and df_y_current"
FIX_DESCRIPTION = (
    "Generates and adds a point geometry into the Form 2 Geotagged Building Points "
    "layer (.geojson) using coordinate attributes from 'df_x_current' (X) and 'df_y_current' (Y)."
)


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

        # Extract X coordinate
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

        # Extract Y coordinate
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

        # Extract UUID
        for candidate in ("df_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
            if candidate in header_map:
                it = table.item(r, header_map[candidate])
                if it and it.text().strip():
                    t_str = it.text().strip()
                    if t_str.lower() not in ("null", "none", "nan", ""):
                        row_info["uuid"] = t_str
                        break

        # Extract metadata from Item 0
        it0 = table.item(r, 0)
        if it0:
            row_info["source_fid"] = it0.data(0x0100)  # Qt.UserRole
            if not row_info["uuid"]:
                u_data = it0.data(0x0100 + 1)
                if u_data:
                    row_info["uuid"] = str(u_data).strip()
            row_info["df_fid"] = it0.data(0x0100 + 2)
            row_info["err_fid"] = it0.data(0x0100 + 3)

        # Extract other table attributes
        for col_name, c_idx in header_map.items():
            it = table.item(r, c_idx)
            if it:
                row_info["attributes"][col_name] = it.text().strip()

    # 2. Augment from error_layer if coordinates or UUID are missing
    if error_layer and error_layer.isValid():
        matching_feat = None
        if row_info["err_fid"] is not None:
            try:
                matching_feat = error_layer.getFeature(row_info["err_fid"])
            except Exception:
                pass

        if not matching_feat and row_info["uuid"]:
            clean_uuid = str(row_info["uuid"]).replace("'", "''")
            for uf in ("df_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
                if uf in error_layer.fields().names():
                    try:
                        for f in error_layer.getFeatures(f'"{uf}" = \'{clean_uuid}\''):
                            matching_feat = f
                            break
                    except Exception:
                        pass
                if matching_feat:
                    break

        if not matching_feat and target_fids and r < len(target_fids):
            try:
                matching_feat = error_layer.getFeature(target_fids[r])
            except Exception:
                pass

        if matching_feat:
            for x_col_candidate in ("df_x_current", "x_current", "sf_longitude", "longitude", "x"):
                if row_info["x"] is None and x_col_candidate in matching_feat.fields().names():
                    val = matching_feat[x_col_candidate]
                    if val is not None and val != NULL:
                        try:
                            row_info["x"] = float(str(val).strip())
                        except (ValueError, TypeError):
                            pass

            for y_col_candidate in ("df_y_current", "y_current", "sf_latitude", "latitude", "y"):
                if row_info["y"] is None and y_col_candidate in matching_feat.fields().names():
                    val = matching_feat[y_col_candidate]
                    if val is not None and val != NULL:
                        try:
                            row_info["y"] = float(str(val).strip())
                        except (ValueError, TypeError):
                            pass

            if not row_info["uuid"]:
                for u_candidate in ("df_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
                    if u_candidate in matching_feat.fields().names():
                        val = matching_feat[u_candidate]
                        if val is not None and val != NULL:
                            s = str(val).strip()
                            if s.lower() not in ("null", "none", "nan", ""):
                                row_info["uuid"] = s
                                break

            for fld in matching_feat.fields():
                fn = fld.name()
                if fn not in row_info["attributes"]:
                    row_info["attributes"][fn] = matching_feat[fn]

    # 3. Fallback to target_uuids list if UUID still missing
    if not row_info["uuid"] and target_uuids and r < len(target_uuids):
        row_info["uuid"] = str(target_uuids[r]).strip()

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
    target_keys: Optional[Any] = None,
    x_col: str = "df_x_current",
    y_col: str = "df_y_current",
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute automated fix: generates and writes point geometries into the
    Form 2 Geotagged Building Points layer using df_x_current and df_y_current
    from the selected row in mv_2027_hp_1a_map_uuid__missing.
    """
    active_layer = main_layer if (main_layer and main_layer.isValid()) else error_layer
    if not active_layer or not active_layer.isValid():
        return {
            "success": False,
            "message": "The Building Points file is missing or could not be opened.",
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

    # Deduplicate rows_to_process by unique composite key (fid + map_uuid)
    if table is not None and len(rows_to_process) > 1:
        seen_row_keys = set()
        deduped_rows = []
        for r in rows_to_process:
            row_info = _extract_row_data(r, table, error_layer, target_fids, target_uuids)
            r_fid = row_info.get("source_fid") or row_info.get("df_fid") or row_info.get("err_fid")
            r_uuid = row_info.get("uuid")
            uk = make_unique_feature_key(r_fid, r_uuid)
            if uk and uk in seen_row_keys:
                continue
            if uk:
                seen_row_keys.add(uk)
            deduped_rows.append(r)
        rows_to_process = deduped_rows

    # Ensure active_layer is in editing mode
    if not active_layer.isEditable() and not active_layer.startEditing():
        return {
            "success": False,
            "message": "The Building Points file could not be opened for editing.",
            "fixed_count": 0,
            "updated_values": {},
        }

    main_fields = active_layer.fields()
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

        clean_uuid = str(target_uuid).strip() if target_uuid is not None else ""
        if clean_uuid.lower() in ("null", "none", "nan", ""):
            clean_uuid = ""

        # Validate coordinates
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

        # 1. Match by explicit existing UUID
        if clean_uuid and uuid_fields:
            for feat in active_layer.getFeatures():
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

        # 2. Match by (X, Y) coordinates
        is_geo = dest_crs.isGeographic() if (dest_crs and hasattr(dest_crs, "isGeographic")) else True
        tol = 1e-5 if is_geo else 0.5

        # 2a. Check features created earlier in current batch
        if existing_feat_id is None:
            for c_fid, c_pt, c_x, c_y, c_uuid in created_batch_features:
                if (abs(c_x - x) <= 1e-5 and abs(c_y - y) <= 1e-5) or (abs(c_pt.x() - pt.x()) <= tol and abs(c_pt.y() - pt.y()) <= tol):
                    existing_feat_id = c_fid
                    existing_uuid = c_uuid
                    is_reused_from_batch = True
                    break

        # 2b. Check existing features in active_layer
        if existing_feat_id is None:
            for feat in active_layer.getFeatures():
                if feat.id() in created_batch_fids:
                    continue
                if feat.hasGeometry() and not feat.geometry().isEmpty():
                    try:
                        f_pt = feat.geometry().asPoint()
                        if abs(f_pt.x() - pt.x()) <= tol and abs(f_pt.y() - pt.y()) <= tol:
                            existing_feat = feat
                            existing_feat_id = feat.id()
                            break
                    except Exception:
                        pass
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

            if existing_feat is not None and not existing_uuid:
                for uf in uuid_fields:
                    val = existing_feat[uf]
                    if val is not None and val != NULL:
                        s_val = str(val).strip()
                        if s_val.lower() not in ("null", "none", "nan", ""):
                            existing_uuid = s_val
                            break

        if existing_feat_id is not None:
            assigned_fid = existing_feat_id
            if not existing_uuid:
                existing_uuid = clean_uuid or str(uuid.uuid4())
                if existing_feat is not None:
                    for uf in uuid_fields:
                        idx = main_fields.indexOf(uf)
                        if idx != -1:
                            main_layer.changeAttributeValue(existing_feat_id, idx, existing_uuid)

            target_uuid = existing_uuid

            if existing_feat is not None:
                if not is_reused_from_batch:
                    if hasattr(main_layer, "changeGeometry"):
                        main_layer.changeGeometry(existing_feat_id, new_geom)
                    elif hasattr(main_layer, "dataProvider") and hasattr(main_layer.dataProvider(), "changeGeometryValues"):
                        main_layer.dataProvider().changeGeometryValues({existing_feat_id: new_geom})

                for sf in ("status", "sf_status"):
                    idx = main_fields.indexOf(sf)
                    if idx != -1:
                        main_layer.changeAttributeValue(existing_feat_id, idx, "active")

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
            target_uuid = clean_uuid or str(uuid.uuid4())
            new_feat = QgsFeature(main_fields)
            new_feat.setGeometry(new_geom)

            for uf in uuid_fields:
                _set_feat_attr(new_feat, uf, target_uuid)

            for xf in ("longitude", "pos_longit", "sf_longitude", "x_current", "df_x_current", "x"):
                if xf in main_field_names:
                    _set_feat_attr(new_feat, xf, str(x))

            for yf in ("latitude", "pos_latitu", "sf_latitude", "y_current", "df_y_current", "y"):
                if yf in main_field_names:
                    _set_feat_attr(new_feat, yf, str(y))

            for sf in ("status", "sf_status"):
                if sf in main_field_names:
                    _set_feat_attr(new_feat, sf, "active")

            if "up_feature" in main_field_names:
                _set_feat_attr(new_feat, "up_feature", 1)
            if "uplocation" in main_field_names:
                _set_feat_attr(new_feat, "uplocation", "1")

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

            if hasattr(active_layer, "addFeature"):
                active_layer.addFeature(new_feat)
            elif hasattr(active_layer, "addFeatures"):
                active_layer.addFeatures([new_feat])
            elif hasattr(active_layer, "dataProvider") and hasattr(active_layer.dataProvider(), "addFeatures"):
                active_layer.dataProvider().addFeatures([new_feat])
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

        # Register composite unique keys (fid + map_uuid)
        cand_fids = [row_info.get("source_fid"), row_info.get("df_fid"), row_info.get("err_fid"), assigned_fid]
        if target_fids and r < len(target_fids):
            cand_fids.append(target_fids[r])
        for f_val in cand_fids:
            if f_val is not None:
                uk = make_unique_feature_key(f_val, target_uuid or clean_uuid)
                if uk:
                    updated_values[uk] = col_dict
                    updated_values[uk.lower()] = col_dict

        fixed_count += 1

    if fixed_count > 0:
        active_layer.triggerRepaint()

        dlg = kwargs.get("dialog") or dialog
        if dlg and hasattr(dlg, "iface") and dlg.iface and hasattr(dlg.iface, "mapCanvas") and dlg.iface.mapCanvas():
            try:
                dlg.iface.mapCanvas().refresh()
            except Exception:
                pass
    elif active_layer.isEditable():
        active_layer.rollBack()

    if fixed_count == 0 and failed_rows:
        bad_r, bad_x, bad_y = failed_rows[0]
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": (
                f"Row #{bad_r + 1} has invalid coordinates ({bad_x}, {bad_y}).\n\n"
                "A point cannot be created when the coordinates are 0 or empty. "
                "Please make sure this row has valid GPS coordinates."
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
        "message": f"Added {fixed_count} point(s){summary_str} to the Building Points file.",
    }


def generate_point_geometry(
    dialog: Any,
    *args,
    **kwargs,
) -> None:
    """
    Process handler for generating point geometry on checked table rows.
    Processes the action directly regardless of validation check or file.
    """
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    action_id = "generate_point_geometry"
    if hasattr(dialog, "_fix_selected_features"):
        dialog._fix_selected_features(action_id, layer, table)


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    target_keys: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute automated fix for mv_2027_hp_1a_map_uuid__missing."""
    return _run_fix_map_uuid_missing(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        target_keys=target_keys,
        **kwargs,
    )
