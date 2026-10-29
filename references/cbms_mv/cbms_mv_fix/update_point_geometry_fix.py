# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Update Point Geometry Process
Action: "Update point geometry using sf_longitude and sf_latitude"
Validation ID: update_point_geometry

Updates the point geometry of selected or multi-selected rows/features
using valid coordinate values from the sf_longitude and sf_latitude columns,
without creating new features or modifying unrelated attributes.
"""
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorLayer,
)

try:
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QMessageBox, QWidget
except ImportError:
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QMessageBox, QWidget
    except ImportError:
        Qt = None
        QMessageBox = None
        QWidget = None

try:
    from .common import _flatten_ids, is_valid_qobject, make_unique_feature_key
except ImportError:
    from common import _flatten_ids, is_valid_qobject, make_unique_feature_key

FIX_ID = "update_point_geometry"
FIX_NAME = "Update point geometry using sf_longitude and sf_latitude"
FIX_DESCRIPTION = (
    "Updates the point geometry of selected or multi-selected features using valid "
    "coordinate values from the sf_longitude and sf_latitude columns."
)

_INVALID_TOKENS = frozenset({"", "null", "none", "nan", "inf", "-inf", "+inf", "undefined"})


def _parse_valid_lon(val: Any) -> Optional[float]:
    """Parse and validate a WGS84 longitude value (-180 <= lon <= 180, non-zero)."""
    if val is None or val == NULL or isinstance(val, bool):
        return None
    s = str(val).strip()
    if s.lower() in _INVALID_TOKENS:
        return None
    try:
        f = float(s)
        if not math.isfinite(f):
            return None
        if abs(f) <= 1e-5:
            return None
        if f < -180.0 or f > 180.0:
            return None
        return f
    except (ValueError, TypeError):
        return None


def _parse_valid_lat(val: Any) -> Optional[float]:
    """Parse and validate a WGS84 latitude value (-90 <= lat <= 90, non-zero)."""
    if val is None or val == NULL or isinstance(val, bool):
        return None
    s = str(val).strip()
    if s.lower() in _INVALID_TOKENS:
        return None
    try:
        f = float(s)
        if not math.isfinite(f):
            return None
        if abs(f) <= 1e-5:
            return None
        if f < -90.0 or f > 90.0:
            return None
        return f
    except (ValueError, TypeError):
        return None


def _is_valid_lon(val: Any) -> bool:
    """Return True if val is a valid non-zero WGS84 longitude."""
    return _parse_valid_lon(val) is not None


def _is_valid_lat(val: Any) -> bool:
    """Return True if val is a valid non-zero WGS84 latitude."""
    return _parse_valid_lat(val) is not None


def _clean_id_str(val: Any) -> str:
    """Normalize an ID or UUID value to a clean string, returning '' for null-like values."""
    if val is None or val == NULL:
        return ""
    s = str(val).strip()
    if s.lower() in _INVALID_TOKENS:
        return ""
    return s


def _resolve_parent_qwidget(dialog: Any, kwargs: Dict[str, Any]) -> Optional[Any]:
    """Return a real QWidget parent suitable for QMessageBox, or None in headless/mock runs."""
    if QWidget is None:
        return None
    cand = dialog if dialog is not None else kwargs.get("parent")
    if cand is not None and hasattr(cand, "iface") and getattr(cand, "iface", None):
        try:
            mw = cand.iface.mainWindow()
            if isinstance(mw, QWidget):
                return mw
        except Exception:
            pass
    if isinstance(cand, QWidget):
        return cand
    return None


def _build_table_header_map(table: Any) -> Dict[str, int]:
    """Build a lowercase column-name -> column-index mapping from a QTableWidget."""
    header_map: Dict[str, int] = {}
    if table is None or not hasattr(table, "columnCount"):
        return header_map
    for c in range(table.columnCount()):
        col_name = ""
        if hasattr(table, "horizontalHeaderItem"):
            h_item = table.horizontalHeaderItem(c)
            if h_item and h_item.text():
                col_name = h_item.text().strip()
        if not col_name and Qt is not None and table.rowCount() > 0:
            cell = table.item(0, c)
            if cell is not None:
                meta_name = cell.data(Qt.UserRole + 2)
                if meta_name:
                    col_name = str(meta_name).strip()
        if col_name:
            header_map[col_name.lower()] = c
    return header_map


def _make_point_geometry_for_layer(
    lon: float,
    lat: float,
    layer: QgsVectorLayer,
    wgs84_crs: QgsCoordinateReferenceSystem,
) -> Optional[QgsGeometry]:
    """Create a QgsGeometry point from WGS84 (lon, lat), transforming to layer CRS if projected."""
    pt = QgsPointXY(lon, lat)
    if layer is not None and hasattr(layer, "crs"):
        dest_crs = layer.crs()
        if dest_crs and dest_crs.isValid() and dest_crs != wgs84_crs and not dest_crs.isGeographic():
            try:
                xform = QgsCoordinateTransform(wgs84_crs, dest_crs, QgsProject.instance())
                pt = xform.transform(pt)
            except Exception:
                pass
    geom = QgsGeometry.fromPointXY(pt)
    if not geom or geom.isEmpty():
        return None
    return geom


def _apply_geometry_to_feature(layer: QgsVectorLayer, feat_id: int, new_geom: QgsGeometry) -> bool:
    """Update feature geometry on an editable layer with dataProvider fallback."""
    if hasattr(layer, "changeGeometry"):
        if layer.changeGeometry(feat_id, new_geom):
            return True
    if hasattr(layer, "dataProvider") and layer.dataProvider() and hasattr(layer.dataProvider(), "changeGeometryValues"):
        return bool(layer.dataProvider().changeGeometryValues({feat_id: new_geom}))
    return False


def _is_numeric_field(fld: Any) -> bool:
    """Return True if a QgsField is numeric in either native PyQGIS or mock test environments."""
    if fld is None:
        return False
    if hasattr(fld, "isNumeric") and callable(fld.isNumeric):
        try:
            return bool(fld.isNumeric())
        except Exception:
            pass
    f_type = fld.type() if (hasattr(fld, "type") and callable(fld.type)) else getattr(fld, "_type", None)
    return f_type in (2, 3, 4, 6)


def _sync_lon_lat_attributes_on_layer(
    layer: QgsVectorLayer,
    feat_id: int,
    lon_val: float,
    lat_val: float,
    lon_str: str,
    lat_str: str,
) -> None:
    """
    Synchronize only the spatial longitude/latitude attribute columns (sf_longitude/longitude,
    sf_latitude/latitude) on the updated spatial feature so attributes stay consistent with
    any in-table coordinate edits. Unrelated attributes are never modified.
    """
    fields = layer.fields()
    for f_idx in range(fields.count()):
        fld = fields.at(f_idx) if hasattr(fields, "at") else fields[f_idx]
        fname_l = fld.name().lower()
        if fname_l in ("sf_longitude", "longitude"):
            val_to_set = lon_val if _is_numeric_field(fld) else lon_str
            layer.changeAttributeValue(feat_id, f_idx, val_to_set)
        elif fname_l in ("sf_latitude", "latitude"):
            val_to_set = lat_val if _is_numeric_field(fld) else lat_str
            layer.changeAttributeValue(feat_id, f_idx, val_to_set)


def _locate_target_feature(
    active_layer: QgsVectorLayer,
    sf_fid: Any = None,
    source_fid: Any = None,
    sf_uuid: str = "",
    fallback_uuid: str = "",
    dialog: Any = None,
    error_layer: Optional[QgsVectorLayer] = None,
) -> Optional[QgsFeature]:
    """
    Locate an existing spatial feature in active_layer corresponding to a selected row.
    Prioritizes sf_fid and sf_map_uuid so joined rows with mismatched df_map_uuid
    still resolve to the exact Building Points (.geojson) feature.
    Never creates new features.
    """
    if not active_layer or not active_layer.isValid():
        return None

    clean_sf_fid = _clean_id_str(sf_fid)
    clean_src_fid = _clean_id_str(source_fid)
    clean_sf_uuid = _clean_id_str(sf_uuid)
    clean_fb_uuid = _clean_id_str(fallback_uuid)
    primary_uuid = clean_sf_uuid or clean_fb_uuid

    # 1. Delegate to dialog._find_main_feature when active_layer is the main building layer
    if (
        dialog is not None
        and hasattr(dialog, "_find_main_feature")
        and (error_layer is None or active_layer != error_layer)
    ):
        best_fid_arg = sf_fid if clean_sf_fid else source_fid
        try:
            found = dialog._find_main_feature(
                active_layer,
                fid=best_fid_arg,
                map_uuid=primary_uuid or None,
            )
            if isinstance(found, QgsFeature) and found.isValid():
                return found
        except Exception:
            pass

    flds_map = {f.name().lower(): f.name() for f in active_layer.fields()}
    uuid_cols = [
        flds_map[c]
        for c in ("sf_map_uuid", "map_uuid", "sf_mapid", "mapid", "uuid")
        if c in flds_map
    ]

    # 2. Match by native QGIS feature ID ($id), verifying UUID if both exist
    fid_candidates = []
    for raw_cand in (clean_sf_fid, clean_src_fid):
        if raw_cand and raw_cand not in fid_candidates:
            fid_candidates.append(raw_cand)

    for raw_fid in fid_candidates:
        if raw_fid.lstrip("-").isdigit():
            target_int_fid = int(raw_fid)
            try:
                feat = active_layer.getFeature(target_int_fid)
                if feat and feat.isValid() and feat.id() == target_int_fid:
                    if not primary_uuid or not uuid_cols:
                        return feat
                    for u_col in uuid_cols:
                        f_u = _clean_id_str(feat[u_col])
                        if not f_u or f_u.lower() == primary_uuid.lower():
                            return feat
            except Exception:
                pass

    # 3. Match by UUID attribute column
    for cand_uuid in (clean_sf_uuid, clean_fb_uuid):
        if not cand_uuid:
            continue
        cand_lower = cand_uuid.lower()
        escaped_uuid = cand_uuid.replace("'", "''")
        for real_col in uuid_cols:
            try:
                req = QgsFeatureRequest().setFilterExpression(f'"{real_col}" = \'{escaped_uuid}\'')
                for feat in active_layer.getFeatures(req):
                    if feat and feat.isValid() and _clean_id_str(feat[real_col]).lower() == cand_lower:
                        return feat
            except Exception:
                pass
        # Case-insensitive scan fallback
        for feat in active_layer.getFeatures():
            for real_col in uuid_cols:
                if _clean_id_str(feat[real_col]).lower() == cand_lower:
                    return feat

    # 4. Match by explicit sf_fid / fid attribute column
    fid_cols = [flds_map[c] for c in ("sf_fid", "fid") if c in flds_map]
    for raw_fid in fid_candidates:
        for fid_col in fid_cols:
            try:
                if raw_fid.lstrip("-").isdigit():
                    expr = f'"{fid_col}" = {int(raw_fid)}'
                else:
                    escaped_fid = raw_fid.replace("'", "''")
                    expr = f'"{fid_col}" = \'{escaped_fid}\''
                req = QgsFeatureRequest().setFilterExpression(expr)
                for feat in active_layer.getFeatures(req):
                    if feat and feat.isValid() and _clean_id_str(feat[fid_col]) == raw_fid:
                        return feat
            except Exception:
                pass

    # 5. Final fallback: if explicit sf_fid matched a valid native feature even when df_uuid differed
    if clean_sf_fid and clean_sf_fid.lstrip("-").isdigit():
        target_int_sf = int(clean_sf_fid)
        try:
            feat = active_layer.getFeature(target_int_sf)
            if feat and feat.isValid() and feat.id() == target_int_sf:
                return feat
        except Exception:
            pass

    return None


def _run_fix_update_point_geometry(
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
    Update point geometries of selected or multi-selected rows/features using valid
    sf_longitude and sf_latitude values.
    """
    # Resolve target spatial Building Points layer
    active_layer = main_layer if (main_layer and main_layer.isValid()) else None
    if (active_layer is None or active_layer == error_layer) and dialog is not None:
        if hasattr(dialog, "_get_or_load_main_building_layer"):
            try:
                resolved = dialog._get_or_load_main_building_layer()
                if isinstance(resolved, QgsVectorLayer) and resolved.isValid():
                    active_layer = resolved
            except Exception:
                pass
    if active_layer is None and error_layer and error_layer.isValid():
        active_layer = error_layer

    if not active_layer or not active_layer.isValid():
        return {
            "success": False,
            "message": "The Building Points layer is missing or could not be opened.",
            "fixed_count": 0,
            "updated_values": {},
        }

    if hasattr(active_layer, "isSpatial") and not active_layer.isSpatial():
        return {
            "success": False,
            "message": "The target layer does not support spatial geometry.",
            "fixed_count": 0,
            "updated_values": {},
        }

    called_via_dialog_executor = bool(dialog is not None and hasattr(dialog, "_execute_fix"))
    parent_w = _resolve_parent_qwidget(dialog, kwargs)
    wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")

    has_ui_table = table is not None and is_valid_qobject(table) and hasattr(table, "rowCount")

    # =========================================================================
    # Branch A: UI Table / Row Selection & Multi-Selection Mode
    # =========================================================================
    if has_ui_table or target_rows is not None:
        rows_to_process: List[int] = []
        if target_rows is not None:
            for r in target_rows:
                if r is not None and (not has_ui_table or 0 <= int(r) < table.rowCount()):
                    rows_to_process.append(int(r))
        elif has_ui_table:
            # 1. Checked rows in Column 0
            for r in range(table.rowCount()):
                item0 = table.item(r, 0)
                if item0 is not None and hasattr(item0, "checkState"):
                    checked_flag = Qt.Checked if Qt is not None else 2
                    if item0.checkState() == checked_flag:
                        rows_to_process.append(r)

            # 2. Fallback to highlighted / multi-selected rows in selectionModel
            if not rows_to_process and hasattr(table, "selectionModel") and table.selectionModel():
                sel_model = table.selectionModel()
                sel_rows = [idx.row() for idx in sel_model.selectedRows()]
                if not sel_rows and hasattr(sel_model, "selectedIndexes"):
                    sel_rows = [idx.row() for idx in sel_model.selectedIndexes()]
                rows_to_process = sorted(set(sel_rows))

        if not rows_to_process:
            msg = "Please tick the checkbox or select at least one row first."
            if QMessageBox and parent_w and not called_via_dialog_executor:
                QMessageBox.information(parent_w, "Nothing Selected", msg)
            return {
                "success": False,
                "message": msg,
                "fixed_count": 0,
                "updated_values": {},
            }

        # Validate presence of sf_longitude and sf_latitude columns in table / error_layer
        header_map = _build_table_header_map(table) if has_ui_table else {}
        err_fields_map = (
            {f.name().lower(): f.name() for f in error_layer.fields()}
            if (error_layer and error_layer.isValid())
            else {}
        )

        has_sf_lon_col = ("sf_longitude" in header_map) or ("sf_longitude" in err_fields_map)
        has_sf_lat_col = ("sf_latitude" in header_map) or ("sf_latitude" in err_fields_map)

        if not (has_sf_lon_col and has_sf_lat_col):
            missing_cols = []
            if not has_sf_lon_col:
                missing_cols.append("sf_longitude")
            if not has_sf_lat_col:
                missing_cols.append("sf_latitude")
            missing_str = " and ".join(f"'{c}'" for c in missing_cols)
            msg = (
                f"Cannot update point geometry because the required {missing_str} "
                "column(s) are not present in this validation table."
            )
            if QMessageBox and parent_w and not called_via_dialog_executor:
                QMessageBox.warning(parent_w, "Missing Coordinate Columns", msg)
            return {
                "success": False,
                "message": msg,
                "fixed_count": 0,
                "updated_values": {},
            }

        # Extract row metadata, deduplicate composite keys, and validate coordinates
        seen_ukeys: Dict[str, int] = {}
        duplicate_rows_by_primary: Dict[int, List[int]] = {}
        valid_rows_data: List[Dict[str, Any]] = []
        invalid_rows: List[Tuple[int, str, str]] = []

        for idx_pos, r in enumerate(rows_to_process):
            item0 = table.item(r, 0) if has_ui_table else None
            s_fid = item0.data(Qt.UserRole) if (item0 is not None and Qt is not None) else None
            u_str = _clean_id_str(item0.data(Qt.UserRole + 1)) if (item0 is not None and Qt is not None) else ""
            e_fid = item0.data(Qt.UserRole + 3) if (item0 is not None and Qt is not None) else None
            df_fid = item0.data(Qt.UserRole + 4) if (item0 is not None and Qt is not None) else None
            sf_fid = item0.data(Qt.UserRole + 6) if (item0 is not None and Qt is not None) else None
            sf_uuid = _clean_id_str(item0.data(Qt.UserRole + 7)) if (item0 is not None and Qt is not None) else ""

            # Fallback to table ID/UUID cells or target_fids/target_uuids arguments
            if not _clean_id_str(sf_fid) and "sf_fid" in header_map and has_ui_table:
                c_it = table.item(r, header_map["sf_fid"])
                if c_it and _clean_id_str(c_it.text()):
                    sf_fid = c_it.text().strip()
            if not _clean_id_str(s_fid) and "fid" in header_map and has_ui_table:
                c_it = table.item(r, header_map["fid"])
                if c_it and _clean_id_str(c_it.text()):
                    s_fid = c_it.text().strip()
            if not sf_uuid and "sf_map_uuid" in header_map and has_ui_table:
                c_it = table.item(r, header_map["sf_map_uuid"])
                if c_it:
                    sf_uuid = _clean_id_str(c_it.text())
            if not u_str and "map_uuid" in header_map and has_ui_table:
                c_it = table.item(r, header_map["map_uuid"])
                if c_it:
                    u_str = _clean_id_str(c_it.text())

            if not _clean_id_str(s_fid) and target_fids and idx_pos < len(target_fids):
                s_fid = target_fids[idx_pos]
            if not u_str and target_uuids and idx_pos < len(target_uuids):
                u_str = _clean_id_str(target_uuids[idx_pos])

            best_fid = sf_fid if _clean_id_str(sf_fid) else s_fid
            best_uuid = sf_uuid or u_str
            ukey = make_unique_feature_key(best_fid or df_fid or e_fid, best_uuid)

            if ukey and ukey in seen_ukeys:
                primary_r = seen_ukeys[ukey]
                duplicate_rows_by_primary.setdefault(primary_r, []).append(r)
                continue
            if ukey:
                seen_ukeys[ukey] = r

            # Extract sf_longitude and sf_latitude strictly from sf_longitude / sf_latitude
            raw_lon = ""
            raw_lat = ""
            if "sf_longitude" in header_map and has_ui_table:
                lon_item = table.item(r, header_map["sf_longitude"])
                raw_lon = lon_item.text().strip() if lon_item is not None else ""
            elif "sf_longitude" in err_fields_map and error_layer is not None:
                lookup_efid = e_fid if e_fid is not None else s_fid
                if lookup_efid is not None and str(lookup_efid).lstrip("-").isdigit():
                    ef = error_layer.getFeature(int(lookup_efid))
                    if ef and ef.isValid():
                        raw_lon = _clean_id_str(ef[err_fields_map["sf_longitude"]])

            if "sf_latitude" in header_map and has_ui_table:
                lat_item = table.item(r, header_map["sf_latitude"])
                raw_lat = lat_item.text().strip() if lat_item is not None else ""
            elif "sf_latitude" in err_fields_map and error_layer is not None:
                lookup_efid = e_fid if e_fid is not None else s_fid
                if lookup_efid is not None and str(lookup_efid).lstrip("-").isdigit():
                    ef = error_layer.getFeature(int(lookup_efid))
                    if ef and ef.isValid():
                        raw_lat = _clean_id_str(ef[err_fields_map["sf_latitude"]])

            lon_f = _parse_valid_lon(raw_lon)
            lat_f = _parse_valid_lat(raw_lat)

            if lon_f is not None and lat_f is not None:
                valid_rows_data.append({
                    "row": r,
                    "sf_fid": sf_fid,
                    "source_fid": s_fid,
                    "err_fid": e_fid,
                    "df_fid": df_fid,
                    "sf_uuid": sf_uuid,
                    "uuid": u_str,
                    "ukey": ukey,
                    "lon": lon_f,
                    "lat": lat_f,
                    "lon_str": raw_lon if _clean_id_str(raw_lon) else str(lon_f),
                    "lat_str": raw_lat if _clean_id_str(raw_lat) else str(lat_f),
                })
            else:
                invalid_rows.append((r, raw_lon, raw_lat))

        if not valid_rows_data:
            msg = (
                f"None of the {len(rows_to_process)} selected row(s) contain valid "
                "coordinates in 'sf_longitude' (-180 to 180, non-zero) and "
                "'sf_latitude' (-90 to 90, non-zero)."
            )
            if QMessageBox and parent_w and not called_via_dialog_executor:
                QMessageBox.warning(parent_w, "Invalid Coordinates", msg)
            return {
                "success": False,
                "message": msg,
                "fixed_count": 0,
                "updated_values": {},
            }

        # Confirmation dialog (mirroring generate_point_geometry_fix.py)
        prompt_confirm = kwargs.get("prompt_confirm", True)
        if prompt_confirm and QMessageBox and parent_w is not None:
            if len(valid_rows_data) == 1:
                entry = valid_rows_data[0]
                prompt_msg = (
                    f"Update point geometry for row #{entry['row'] + 1}?\n\n"
                    f"- sf_longitude: {entry['lon_str']}\n"
                    f"- sf_latitude: {entry['lat_str']}\n\n"
                    "This will update the feature's point geometry in the Form 2 Building Points layer (.geojson)."
                )
            else:
                prompt_msg = (
                    f"Update point geometries for {len(valid_rows_data)} selected record(s) "
                    "using 'sf_longitude' and 'sf_latitude'?\n\n"
                    "This will update the point geometries in the Form 2 Building Points layer (.geojson)."
                )

            if invalid_rows:
                prompt_msg += (
                    f"\n\nNote: {len(invalid_rows)} selected row(s) will be skipped "
                    "because their 'sf_longitude' or 'sf_latitude' values are missing or invalid."
                )

            reply = QMessageBox.question(
                parent_w,
                "Confirm Update Point Geometry",
                prompt_msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return {
                    "success": False,
                    "message": "Point geometry update was cancelled by the user.",
                    "fixed_count": 0,
                    "updated_values": {},
                }

        # Ensure editable state on active_layer (and error_layer if distinct)
        if not active_layer.isEditable() and not active_layer.startEditing():
            return {
                "success": False,
                "message": "The Building Points layer could not be opened for editing.",
                "fixed_count": 0,
                "updated_values": {},
            }

        if error_layer and error_layer.isValid() and error_layer != active_layer and not error_layer.isEditable():
            try:
                error_layer.startEditing()
            except Exception:
                pass

        updated_values: Dict[Any, Dict[str, Any]] = {}
        fixed_count = 0
        unmatched_rows: List[int] = []

        for entry in valid_rows_data:
            if feedback and feedback.isCanceled():
                break

            r = entry["row"]
            lon_f = entry["lon"]
            lat_f = entry["lat"]
            lon_str = entry["lon_str"]
            lat_str = entry["lat_str"]

            target_feat = _locate_target_feature(
                active_layer,
                sf_fid=entry["sf_fid"],
                source_fid=entry["source_fid"],
                sf_uuid=entry["sf_uuid"],
                fallback_uuid=entry["uuid"],
                dialog=dialog,
                error_layer=error_layer,
            )
            if target_feat is None or not target_feat.isValid():
                unmatched_rows.append(r)
                continue

            new_geom = _make_point_geometry_for_layer(lon_f, lat_f, active_layer, wgs84_crs)
            if new_geom is None:
                unmatched_rows.append(r)
                continue

            feat_id = target_feat.id()
            if not _apply_geometry_to_feature(active_layer, feat_id, new_geom):
                unmatched_rows.append(r)
                continue

            _sync_lon_lat_attributes_on_layer(active_layer, feat_id, lon_f, lat_f, lon_str, lat_str)

            # Also update geometry on error_layer if spatial and distinct
            if (
                error_layer
                and error_layer.isValid()
                and error_layer != active_layer
                and (not hasattr(error_layer, "isSpatial") or error_layer.isSpatial())
            ):
                err_fid_val = entry["err_fid"]
                err_feat = None
                if err_fid_val is not None and str(err_fid_val).lstrip("-").isdigit():
                    target_int_efid = int(err_fid_val)
                    try:
                        cand_ef = error_layer.getFeature(target_int_efid)
                        if cand_ef and cand_ef.isValid() and cand_ef.id() == target_int_efid:
                            err_feat = cand_ef
                    except Exception:
                        pass
                if err_feat is None:
                    err_feat = _locate_target_feature(
                        error_layer,
                        sf_fid=entry["sf_fid"],
                        source_fid=entry["source_fid"],
                        sf_uuid=entry["sf_uuid"],
                        fallback_uuid=entry["uuid"],
                    )
                if err_feat is not None and err_feat.isValid():
                    err_geom = _make_point_geometry_for_layer(lon_f, lat_f, error_layer, wgs84_crs)
                    if err_geom is not None:
                        _apply_geometry_to_feature(error_layer, err_feat.id(), err_geom)
                    _sync_lon_lat_attributes_on_layer(error_layer, err_feat.id(), lon_f, lat_f, lon_str, lat_str)

            # Record only sf_longitude/sf_latitude (no df_* or map_uuid keys, keeping Form 2 CSV untouched)
            payload = {
                "sf_longitude": lon_str,
                "sf_latitude": lat_str,
            }
            all_rows_for_feat = [r] + duplicate_rows_by_primary.get(r, [])
            for row_idx in all_rows_for_feat:
                updated_values[f"row_{row_idx}"] = payload

            if entry["ukey"]:
                updated_values[entry["ukey"]] = payload
                updated_values[entry["ukey"].lower()] = payload

            for fid_cand in (feat_id, entry["sf_fid"], entry["source_fid"], entry["err_fid"]):
                clean_fc = _clean_id_str(fid_cand)
                if clean_fc:
                    updated_values[fid_cand] = payload
                    updated_values[f"fid_{clean_fc}"] = payload

            for uuid_cand in (entry["sf_uuid"], entry["uuid"]):
                if uuid_cand:
                    updated_values[uuid_cand] = payload
                    updated_values[uuid_cand.lower()] = payload

            fixed_count += 1

        if fixed_count > 0:
            active_layer.triggerRepaint()
            if error_layer and error_layer.isValid() and error_layer != active_layer:
                error_layer.triggerRepaint()
            if dialog and hasattr(dialog, "iface") and dialog.iface and hasattr(dialog.iface, "mapCanvas"):
                canvas = dialog.iface.mapCanvas()
                if canvas:
                    try:
                        canvas.refresh()
                    except Exception:
                        pass
        else:
            msg = (
                "No matching spatial features were found in the Building Points layer "
                "for the selected row(s)."
            )
            return {
                "success": False,
                "fixed_count": 0,
                "updated_values": {},
                "message": msg,
            }

        notes = []
        if invalid_rows:
            notes.append(f"{len(invalid_rows)} skipped due to invalid coordinates")
        if unmatched_rows:
            notes.append(f"{len(unmatched_rows)} unmatched in Building Points layer")
        note_suffix = f" ({'; '.join(notes)})" if notes else ""

        if feedback:
            feedback.pushInfo(
                f"Updated point geometry for {fixed_count} feature(s) using sf_longitude and sf_latitude{note_suffix}."
            )

        return {
            "success": True,
            "fixed_count": fixed_count,
            "updated_values": updated_values,
            "message": (
                f"Updated point geometry for {fixed_count} feature(s) using "
                f"sf_longitude and sf_latitude{note_suffix}."
            ),
        }

    # =========================================================================
    # Branch B: Headless / Direct Layer Invocation (No QTableWidget)
    # =========================================================================
    coord_source_layer = error_layer if (error_layer and error_layer.isValid()) else active_layer
    src_fields_map = {f.name().lower(): f.name() for f in coord_source_layer.fields()}

    if error_layer and error_layer.isValid():
        lon_col = src_fields_map.get("sf_longitude")
        lat_col = src_fields_map.get("sf_latitude")
    else:
        lon_col = src_fields_map.get("sf_longitude") or src_fields_map.get("longitude")
        lat_col = src_fields_map.get("sf_latitude") or src_fields_map.get("latitude")

    if not lon_col or not lat_col:
        missing_cols = []
        if not lon_col:
            missing_cols.append("sf_longitude")
        if not lat_col:
            missing_cols.append("sf_latitude")
        missing_str = " and ".join(f"'{c}'" for c in missing_cols)
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": f"Cannot update point geometry because the required {missing_str} column(s) are missing.",
        }

    clean_target_fids: Set[Any] = {
        fid for fid in _flatten_ids(target_fids)
        if _clean_id_str(fid)
    }
    clean_target_uuids: Set[str] = {
        _clean_id_str(u).lower() for u in _flatten_ids(target_uuids)
        if _clean_id_str(u)
    }
    target_keys_set: Set[str] = {
        _clean_id_str(k) for k in (target_keys or [])
        if _clean_id_str(k)
    }
    target_keys_lower: Set[str] = {k.lower() for k in target_keys_set}

    explicit_target_args = (target_fids is not None) or (target_uuids is not None) or (target_keys is not None)
    if not explicit_target_args and not kwargs.get("process_all", False):
        if hasattr(coord_source_layer, "selectedFeatureIds"):
            sel_ids = coord_source_layer.selectedFeatureIds()
            if sel_ids:
                clean_target_fids.update(_flatten_ids(sel_ids))

    if not clean_target_fids and not clean_target_uuids and not target_keys_set and not kwargs.get("process_all", False):
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "No rows or features were selected.",
        }

    if not active_layer.isEditable() and not active_layer.startEditing():
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "The Building Points layer could not be opened for editing.",
        }

    if error_layer and error_layer.isValid() and error_layer != active_layer and not error_layer.isEditable():
        try:
            error_layer.startEditing()
        except Exception:
            pass

    updated_values = {}
    fixed_count = 0
    invalid_count = 0
    matched_target_count = 0

    src_field_names = list(coord_source_layer.fields().names())
    for src_feat in coord_source_layer.getFeatures():
        if feedback and feedback.isCanceled():
            break

        feat_ids = _flatten_ids(src_feat.id())
        sf_fid_val = None
        sf_uuid_val = ""
        any_uuid_val = ""

        for col in ("sf_fid", "fid", "df_fid"):
            if col in src_field_names:
                v = src_feat[col]
                if _clean_id_str(v):
                    feat_ids.update(_flatten_ids(v))
                    if sf_fid_val is None and col in ("sf_fid", "fid"):
                        sf_fid_val = v

        for col in ("sf_map_uuid", "map_uuid", "sf_mapid", "mapid", "uuid", "df_map_uuid"):
            if col in src_field_names:
                v_str = _clean_id_str(src_feat[col])
                if v_str:
                    if not sf_uuid_val and col in ("sf_map_uuid", "map_uuid", "sf_mapid", "mapid", "uuid"):
                        sf_uuid_val = v_str
                    if not any_uuid_val:
                        any_uuid_val = v_str

        cand_keys = {make_unique_feature_key(fid_v, sf_uuid_val or any_uuid_val) for fid_v in feat_ids}
        cand_keys.discard("")
        cand_keys_lower = {k.lower() for k in cand_keys}

        if not kwargs.get("process_all", False):
            is_match = False
            if clean_target_fids and (feat_ids & clean_target_fids):
                is_match = True
            if not is_match and clean_target_uuids:
                for u_cand in (sf_uuid_val, any_uuid_val):
                    if u_cand and u_cand.lower() in clean_target_uuids:
                        is_match = True
                        break
            if not is_match and target_keys_set:
                if (cand_keys & target_keys_set) or (cand_keys_lower & target_keys_lower):
                    is_match = True
            if not is_match:
                continue

        matched_target_count += 1
        raw_lon_val = src_feat[lon_col]
        raw_lat_val = src_feat[lat_col]
        lon_f = _parse_valid_lon(raw_lon_val)
        lat_f = _parse_valid_lat(raw_lat_val)

        if lon_f is None or lat_f is None:
            invalid_count += 1
            continue

        lon_str = _clean_id_str(raw_lon_val) or str(lon_f)
        lat_str = _clean_id_str(raw_lat_val) or str(lat_f)

        if coord_source_layer == active_layer:
            target_feat = src_feat
        else:
            target_feat = _locate_target_feature(
                active_layer,
                sf_fid=sf_fid_val,
                source_fid=src_feat.id(),
                sf_uuid=sf_uuid_val,
                fallback_uuid=any_uuid_val,
                dialog=dialog,
                error_layer=error_layer,
            )

        if target_feat is None or not target_feat.isValid():
            continue

        new_geom = _make_point_geometry_for_layer(lon_f, lat_f, active_layer, wgs84_crs)
        if new_geom is None:
            continue

        if not _apply_geometry_to_feature(active_layer, target_feat.id(), new_geom):
            continue

        _sync_lon_lat_attributes_on_layer(active_layer, target_feat.id(), lon_f, lat_f, lon_str, lat_str)

        if (
            error_layer
            and error_layer.isValid()
            and error_layer != active_layer
            and coord_source_layer == error_layer
            and (not hasattr(error_layer, "isSpatial") or error_layer.isSpatial())
        ):
            err_geom = _make_point_geometry_for_layer(lon_f, lat_f, error_layer, wgs84_crs)
            if err_geom is not None:
                _apply_geometry_to_feature(error_layer, src_feat.id(), err_geom)

        payload = {
            "sf_longitude": lon_str,
            "sf_latitude": lat_str,
        }
        for k in feat_ids:
            updated_values[k] = payload
        for ck in cand_keys:
            updated_values[ck] = payload
            updated_values[ck.lower()] = payload
        for u_cand in (sf_uuid_val, any_uuid_val):
            if u_cand:
                updated_values[u_cand] = payload
                updated_values[u_cand.lower()] = payload

        fixed_count += 1

    if fixed_count > 0:
        active_layer.triggerRepaint()
        if error_layer and error_layer.isValid() and error_layer != active_layer:
            error_layer.triggerRepaint()
    else:
        if matched_target_count > 0 and invalid_count > 0:
            msg = (
                "None of the selected feature(s) contain valid coordinates in "
                "'sf_longitude' (-180 to 180, non-zero) and 'sf_latitude' (-90 to 90, non-zero)."
            )
        else:
            msg = "No matching spatial features were updated."
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": msg,
        }

    if feedback:
        feedback.pushInfo(f"Updated point geometry for {fixed_count} feature(s) using sf_longitude and sf_latitude.")

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Updated point geometry for {fixed_count} feature(s) using sf_longitude and sf_latitude.",
    }


def update_point_geometry(
    dialog: Any,
    *args,
    combo_actions: Optional[Any] = None,
    btn_actions: Optional[Any] = None,
    btn_update_selected: Optional[Any] = None,
    **kwargs,
) -> Optional[Dict[str, Any]]:
    """
    Process handler for updating point geometry using sf_longitude and sf_latitude
    on checked or multi-selected table rows.
    """
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    if hasattr(dialog, "_fix_selected_features"):
        dialog._fix_selected_features(FIX_ID, layer, table)
        return None

    return _run_fix_update_point_geometry(
        layer,
        error_layer=layer,
        table=table,
        dialog=dialog,
        **kwargs,
    )


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    target_keys: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute automated fix for update_point_geometry."""
    return _run_fix_update_point_geometry(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        target_keys=target_keys,
        **kwargs,
    )


run_update_point_geometry = run_fix
