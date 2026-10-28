# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Generate Point Geometry Process
Action: "Generate point geometry"
Universal Fix Action: Accessible across all CBMS map validation rules.

Generates point geometries in the Form 2 Geotagged Building Points layer (.geojson)
using coordinates (x_current, y_current) from the CSV datafile when no corresponding
point exists in the GeoJSON layer. Automatically derives bsn_geoid by concatenating
province_code, city_mun_code, barangay_code, ean, and bsn_code, and generates or
preserves map_uuid across both GeoJSON and CSV datafiles.
"""
import math
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
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QMessageBox
except ImportError:
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QMessageBox
    except ImportError:
        Qt = None
        QMessageBox = None

try:
    from .common import is_valid_qobject, make_unique_feature_key
except ImportError:
    from common import is_valid_qobject, make_unique_feature_key

FIX_ID = "generate_point_geometry"
FIX_NAME = "Generate point geometry from x_current and y_current"
FIX_DESCRIPTION = (
    "Generates and adds a point geometry into the Form 2 Geotagged Building Points "
    "layer (.geojson) using coordinate attributes from 'x_current' (X) and 'y_current' (Y) "
    "(or 'df_x_current' / 'df_y_current'), generates or preserves 'map_uuid', and computes "
    "'bsn_geoid' from concatenated province_code, city_mun_code, barangay_code, ean, and bsn_code."
)


def _is_valid_coord(val: Any) -> bool:
    """Validate that coordinate is a valid non-zero numeric value."""
    if val is None or val == NULL:
        return False
    try:
        f_val = float(str(val).strip())
        if math.isnan(f_val) or math.isinf(f_val):
            return False
        return abs(f_val) > 1e-5
    except (ValueError, TypeError):
        return False


def _is_valid_uuid(val: Any) -> bool:
    """Validate that map_uuid is a valid non-empty string."""
    if val is None or val == NULL:
        return False
    s_val = str(val).strip()
    if not s_val:
        return False
    if s_val.lower() in ("null", "none", "nan", "undefined", "0"):
        return False
    return True


def _format_clean_code(val: Any) -> str:
    """Format numeric/string code, stripping float decimals like '.0' if present."""
    if val is None or val == NULL:
        return ""
    s = str(val).strip()
    if s.lower() in ("", "null", "none", "nan", "undefined"):
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _pad_code(val: Any, length: int) -> str:
    """Format numeric/string code, stripping float decimals and zero-padding to desired length."""
    clean = _format_clean_code(val)
    if not clean:
        return ""
    if clean.isdigit() and len(clean) < length:
        return clean.zfill(length)
    return clean


def _format_bsn_code(val: Any) -> str:
    """Format BSN code to standard 5-digit zero-padded string."""
    return _pad_code(val, 5)


def _extract_first_matching(source: Dict[str, Any], candidates: List[str]) -> str:
    """Extract first non-empty value matching candidates (case-insensitive) from a dict."""
    if not source:
        return ""
    source_lower = {str(k).lower(): v for k, v in source.items()}
    for cand in candidates:
        cand_l = cand.lower()
        if cand_l in source_lower:
            val = _format_clean_code(source_lower[cand_l])
            if val:
                return val
    return ""


def _extract_padded_boundary_codes(
    attributes: Dict[str, Any], extra_feat: Optional[QgsFeature] = None
) -> Dict[str, str]:
    """
    Extract and zero-pad all individual boundary and BSN components, plus composite ea_geocode and bsn_geoid.
    Paddings:
      - region_code: 2 digits
      - province_code: 3 digits
      - city_mun_code: 2 digits
      - barangay_code: 3 digits
      - ean: 6 digits
      - bsn: 5 digits
    Returns dict with keys:
      region_code, province_code, city_mun_code, barangay_code, ean, bsn, ea_geocode, bsn_geoid.
    """
    attrs = dict(attributes)
    if extra_feat and extra_feat.isValid():
        for fld in extra_feat.fields():
            fn = fld.name()
            if fn.lower() not in [k.lower() for k in attrs]:
                v = extra_feat[fn]
                if v is not None and v != NULL:
                    attrs[fn] = v

    raw_reg = _extract_first_matching(
        attrs,
        ["df_region_code", "region_code", "sf_region_code", "df_reg_code", "reg_code", "sf_reg_code"]
    )
    raw_prov = _extract_first_matching(
        attrs,
        ["df_province_code", "province_code", "sf_province_code", "df_prov_code", "prov_code", "sf_prov_code"]
    )
    raw_mun = _extract_first_matching(
        attrs,
        ["df_city_mun_code", "city_mun_code", "sf_city_mun_code", "df_mun_code", "mun_code", "sf_mun_code", "df_city_code", "city_code"]
    )
    raw_brgy = _extract_first_matching(
        attrs,
        ["df_barangay_code", "df_barangay__code", "barangay_code", "barangay__code", "sf_barangay_code", "sf_barangay__code", "df_brgy_code", "brgy_code", "sf_brgy_code", "df_bgy_code", "bgy_code"]
    )
    raw_ean = _extract_first_matching(
        attrs,
        ["df_ean", "ean", "sf_ean", "df_ea_code", "ea_code", "sf_ea_code", "df_ean_code", "ean_code", "df_ea_num", "ea_num"]
    )
    raw_bsn = _extract_first_matching(
        attrs,
        ["df_bsn", "bsn", "df_bsn_code", "bsn_code", "sf_bsn", "sf_bsn_code", "df_bldg_sn", "bldg_sn", "sf_bldg_sn", "bsn_num"]
    )

    reg = _pad_code(raw_reg, 2)
    prov = _pad_code(raw_prov, 3)
    mun = _pad_code(raw_mun, 2)
    brgy = _pad_code(raw_brgy, 3)
    ean = _pad_code(raw_ean, 6)
    bsn = _pad_code(raw_bsn, 5)

    ea_geo = _extract_first_matching(
        attrs,
        ["df_ea_geocode", "ea_geocode", "sf_ea_geocode", "geocode", "df_geocode"]
    )

    if not ea_geo and prov and mun and brgy and ean:
        ea_geo = f"{prov}{mun}{brgy}{ean}"

    bsn_geoid = ""
    if prov and mun and brgy and ean and bsn:
        bsn_geoid = f"{prov}{mun}{brgy}{ean}{bsn}"
    elif ea_geo and bsn:
        bsn_geoid = f"{ea_geo}{bsn}"

    return {
        "region_code": reg,
        "province_code": prov,
        "city_mun_code": mun,
        "barangay_code": brgy,
        "ean": ean,
        "bsn": bsn,
        "ea_geocode": ea_geo,
        "bsn_geoid": bsn_geoid,
    }


def _compute_bsn_geoid(attributes: Dict[str, Any], extra_feat: Optional[QgsFeature] = None) -> Tuple[str, str]:
    """
    Compute bsn_geoid and ea_geocode from attributes and optional feature.
    Concatenates:
      province_code (padded to 3 digits) +
      city_mun_code (padded to 2 digits) +
      barangay_code (padded to 3 digits) +
      ean (padded to 6 digits) +
      bsn (padded to 5 digits).
    Returns (bsn_geoid, ea_geocode).
    """
    res = _extract_padded_boundary_codes(attributes, extra_feat=extra_feat)
    return res["bsn_geoid"], res["ea_geocode"]


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
    target_rows: Optional[List[int]] = None,
    dialog: Optional[Any] = None,
) -> Dict[str, Any]:
    """Extract coordinates, UUID, and other attributes from table row, error_layer, and form2_layer."""
    row_info = {
        "x": None,
        "y": None,
        "uuid": "",
        "df_fid": None,
        "source_fid": None,
        "err_fid": None,
        "attributes": {},
    }

    target_idx = target_rows.index(r) if (target_rows and r in target_rows) else r

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
        for candidate in ("df_map_uuid", "map_uuid", "sf_map_uuid", "df_mapid", "mapid", "uuid"):
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
            row_info["source_fid"] = it0.data(0x0100) if it0.data(0x0100) is not None else it0.data(0)
            if not row_info["uuid"]:
                for u_role in (0x0100 + 1, 1, 0x0100 + 5, 5, 0x0100 + 7, 7):
                    u_data = it0.data(u_role)
                    if u_data and str(u_data).strip().lower() not in ("null", "none", "nan", ""):
                        row_info["uuid"] = str(u_data).strip()
                        break
            row_info["df_fid"] = (
                it0.data(0x0100 + 4) or it0.data(4) or
                it0.data(0x0100 + 2) or it0.data(2)
            )
            row_info["err_fid"] = it0.data(0x0100 + 3) or it0.data(3)

        # Extract other table attributes
        for col_name, c_idx in header_map.items():
            it = table.item(r, c_idx)
            if it:
                row_info["attributes"][col_name] = it.text().strip()
                fn_role = it.data(0x0100 + 2)
                if fn_role:
                    row_info["attributes"][str(fn_role).strip().lower()] = it.text().strip()

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
            for uf in ("df_map_uuid", "map_uuid", "sf_map_uuid", "df_mapid", "mapid", "uuid"):
                if uf in error_layer.fields().names():
                    try:
                        for f in error_layer.getFeatures(f'"{uf}" = \'{clean_uuid}\''):
                            matching_feat = f
                            break
                    except Exception:
                        pass
                if matching_feat:
                    break

        if not matching_feat and target_fids and target_idx < len(target_fids):
            try:
                matching_feat = error_layer.getFeature(target_fids[target_idx])
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
                for u_candidate in ("df_map_uuid", "map_uuid", "sf_map_uuid", "df_mapid", "mapid", "uuid"):
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

    # 3. Augment from Form 2 CSV layer if available in dialog
    if dialog and hasattr(dialog, "_get_or_load_form2_layer"):
        try:
            f2_layer = dialog._get_or_load_form2_layer()
            if f2_layer and f2_layer.isValid() and hasattr(dialog, "_find_form2_feature"):
                f2_feat = dialog._find_form2_feature(
                    f2_layer,
                    fid=row_info.get("df_fid") or row_info.get("source_fid"),
                    map_uuid=row_info.get("uuid"),
                )
                if f2_feat and f2_feat.isValid():
                    f2_fnames = [f.name().lower() for f in f2_feat.fields()]
                    if row_info["x"] is None:
                        for xc in ("x_current", "df_x_current", "longitude", "pos_longit", "x"):
                            if xc in f2_fnames:
                                val = f2_feat[xc]
                                if _is_valid_coord(val):
                                    row_info["x"] = float(str(val).strip())
                                    break
                    if row_info["y"] is None:
                        for yc in ("y_current", "df_y_current", "latitude", "pos_latitu", "y"):
                            if yc in f2_fnames:
                                val = f2_feat[yc]
                                if _is_valid_coord(val):
                                    row_info["y"] = float(str(val).strip())
                                    break
                    if not row_info["uuid"]:
                        for uc in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid"):
                            if uc in f2_fnames:
                                val = f2_feat[uc]
                                if _is_valid_uuid(val):
                                    row_info["uuid"] = str(val).strip()
                                    break
                    for fld in f2_feat.fields():
                        fn = fld.name()
                        if fn.lower() not in [k.lower() for k in row_info["attributes"]]:
                            v = f2_feat[fn]
                            if v is not None and v != NULL:
                                row_info["attributes"][fn] = v
                                row_info["attributes"][f"df_{fn}"] = v
        except Exception:
            pass

    # 4. Fallback to target_uuids list if UUID still missing
    if not row_info["uuid"] and target_uuids and target_idx < len(target_uuids):
        row_info["uuid"] = str(target_uuids[target_idx]).strip()

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
    Form 2 Geotagged Building Points layer using coordinates (x_current, y_current)
    from the selected row, generating or preserving map_uuid, and computing bsn_geoid.
    Universally accessible across all validation rules.
    """
    active_layer = main_layer if (main_layer and main_layer.isValid()) else error_layer
    if not active_layer or not active_layer.isValid():
        return {
            "success": False,
            "message": "The Building Points file is missing or could not be opened.",
            "fixed_count": 0,
            "updated_values": {},
        }

    # 1. Determine which table rows to fix (Strict Selection Scope)
    if target_rows is not None:
        rows_to_process = [r for r in target_rows if r is not None]
    elif table is not None:
        rows_to_process = []
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if item0:
                is_checked = (item0.checkState() == (Qt.Checked if Qt else 2)) if hasattr(item0, "checkState") else getattr(item0, "isChecked", lambda: False)()
                if is_checked:
                    rows_to_process.append(r)
        if not rows_to_process and hasattr(table, "selectionModel") and table.selectionModel():
            selected_indexes = table.selectionModel().selectedRows()
            if selected_indexes:
                rows_to_process = [idx.row() for idx in selected_indexes]
    elif target_fids is not None and len(target_fids) > 0:
        rows_to_process = list(range(len(target_fids)))
    elif target_uuids is not None and len(target_uuids) > 0:
        rows_to_process = list(range(len(target_uuids)))
    else:
        rows_to_process = []

    # Strict Selection Scope check: Ensure fix applies ONLY to explicitly checked/selected rows
    if not rows_to_process:
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

    # Deduplicate rows_to_process by unique composite key (fid + map_uuid)
    if table is not None and len(rows_to_process) > 1:
        seen_row_keys = set()
        deduped_rows = []
        for r in rows_to_process:
            row_info = _extract_row_data(r, table, error_layer, target_fids, target_uuids, target_rows=target_rows, dialog=dialog)
            r_fid = row_info.get("source_fid") or row_info.get("df_fid") or row_info.get("err_fid")
            r_uuid = row_info.get("uuid")
            uk = make_unique_feature_key(r_fid, r_uuid)
            if uk and uk in seen_row_keys:
                continue
            if uk:
                seen_row_keys.add(uk)
            deduped_rows.append(r)
        rows_to_process = deduped_rows

    # 2. Validation: Check if valid coordinates (x_current, y_current) are present
    # If map_uuid is not present, auto-generate a fresh UUID
    valid_rows_data: List[Tuple[int, Dict[str, Any], float, float, str, str, str]] = []
    # Items: (r, row_info, x, y, target_uuid, bsn_geoid, ea_geo)
    invalid_rows_data: List[Tuple[int, Dict[str, Any], bool, bool]] = []

    for r in rows_to_process:
        row_info = _extract_row_data(r, table, error_layer, target_fids, target_uuids, target_rows=target_rows, dialog=dialog)
        x = row_info.get("x")
        y = row_info.get("y")
        target_uuid = row_info.get("uuid")

        has_coords = _is_valid_coord(x) and _is_valid_coord(y)
        has_uuid = _is_valid_uuid(target_uuid)

        if has_coords:
            clean_uuid = str(target_uuid).strip() if has_uuid else ""
            padded_dict = _extract_padded_boundary_codes(row_info.get("attributes", {}))
            bsn_geoid = padded_dict["bsn_geoid"]
            ea_geo = padded_dict["ea_geocode"]
            valid_rows_data.append((r, row_info, float(x), float(y), clean_uuid, bsn_geoid, ea_geo, padded_dict))
        else:
            invalid_rows_data.append((r, row_info, False, has_uuid))

    if not valid_rows_data:
        parent_w = dialog or kwargs.get("parent")
        if parent_w and hasattr(parent_w, "iface") and parent_w.iface:
            parent_w = parent_w.iface.mainWindow()
        if QMessageBox and parent_w:
            QMessageBox.warning(
                parent_w,
                "Cannot Generate Point Geometry",
                f"None of the {len(rows_to_process)} selected row(s) contain valid coordinates "
                "(x_current, y_current).\n\n"
                "Please verify that the selected rows have valid GPS coordinates to create points on the map.",
            )
        return {
            "success": False,
            "message": "The selected row(s) lack valid coordinates (x_current, y_current).",
            "fixed_count": 0,
            "updated_values": {},
        }

    # 3. Prompting: Prompt the user for confirmation before executing the fix
    prompt_confirm = kwargs.get("prompt_confirm", True)
    parent_w = dialog or kwargs.get("parent")
    if prompt_confirm and QMessageBox and parent_w:
        if hasattr(parent_w, "iface") and parent_w.iface:
            parent_w = parent_w.iface.mainWindow()

        if len(valid_rows_data) == 1:
            r_idx, _, v_x, v_y, v_uuid, v_bsn = valid_rows_data[0][:6]
            prompt_msg = (
                f"Generate point geometry for row #{r_idx + 1}?\n\n"
                f"• Coordinates: X={v_x}, Y={v_y}\n"
                f"• Map UUID: {v_uuid or 'Auto-generated'}\n"
            )
            if v_bsn:
                prompt_msg += f"• BSN GEOID: {v_bsn}\n"
            prompt_msg += "\nThis will create or link the point geometry in the Form 2 Building Points layer (.geojson)."
        else:
            prompt_msg = (
                f"Generate point geometries for {len(valid_rows_data)} selected record(s)?\n\n"
                f"Valid coordinates (x_current, y_current) are present for all "
                f"{len(valid_rows_data)} record(s).\n\n"
                "This will create or link the point geometries in the Form 2 Building Points layer (.geojson) and derive BSN GEOID."
            )

        if invalid_rows_data:
            prompt_msg += (
                f"\n\nNote: {len(invalid_rows_data)} selected row(s) will be skipped "
                "because they are missing valid GPS coordinates (x_current, y_current)."
            )

        reply = QMessageBox.question(
            parent_w,
            "Confirm Generate Point Geometry",
            prompt_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return {
                "success": False,
                "message": "Point geometry generation was cancelled by the user.",
                "fixed_count": 0,
                "updated_values": {},
            }

    # 4. Ensure active_layer is in editing mode
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
    dest_crs = active_layer.crs()
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

    for r, row_info, x, y, target_uuid, bsn_geoid, ea_geo, padded_dict in valid_rows_data:
        if feedback and feedback.isCanceled():
            break

        clean_uuid = target_uuid

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

        # 1. Match by explicit existing UUID in active_layer
        if clean_uuid and uuid_fields:
            for feat in active_layer.getFeatures():
                if feat.id() in created_batch_fids:
                    continue
                for uf in uuid_fields:
                    val = feat[uf]
                    if val is not None and val != NULL:
                        s_val = str(val).strip()
                        if s_val.lower() not in ("null", "none", "nan", "") and s_val.lower() == clean_uuid.lower():
                            existing_feat = feat
                            existing_feat_id = feat.id()
                            existing_uuid = clean_uuid
                            break
                if existing_feat_id is not None:
                    break

        # 2a. Check if a feature was created earlier in current batch with the same clean_uuid
        if existing_feat_id is None and clean_uuid:
            for c_fid, c_pt, c_x, c_y, c_uuid in created_batch_features:
                if c_uuid and c_uuid.strip().lower() == clean_uuid.strip().lower():
                    existing_feat_id = c_fid
                    existing_uuid = c_uuid
                    is_reused_from_batch = True
                    break

        # 2b. Only if clean_uuid is empty/NULL: match by (X, Y) coordinates
        if existing_feat_id is None and not clean_uuid:
            is_geo = dest_crs.isGeographic() if (dest_crs and hasattr(dest_crs, "isGeographic")) else True
            tol = 1e-5 if is_geo else 0.5

            for c_fid, c_pt, c_x, c_y, c_uuid in created_batch_features:
                if (abs(c_x - x) <= 1e-5 and abs(c_y - y) <= 1e-5) or (abs(c_pt.x() - pt.x()) <= tol and abs(c_pt.y() - pt.y()) <= tol):
                    existing_feat_id = c_fid
                    existing_uuid = c_uuid
                    is_reused_from_batch = True
                    break

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
                            active_layer.changeAttributeValue(existing_feat_id, idx, existing_uuid)

            target_uuid = existing_uuid

            if existing_feat is not None:
                if not is_reused_from_batch:
                    if hasattr(active_layer, "changeGeometry"):
                        active_layer.changeGeometry(existing_feat_id, new_geom)
                    elif hasattr(active_layer, "dataProvider") and hasattr(active_layer.dataProvider(), "changeGeometryValues"):
                        active_layer.dataProvider().changeGeometryValues({existing_feat_id: new_geom})

                for sf in ("status", "sf_status"):
                    idx = main_fields.indexOf(sf)
                    if idx != -1:
                        active_layer.changeAttributeValue(existing_feat_id, idx, "active")

                for xf in ("longitude", "pos_longit", "sf_longitude", "x_current", "df_x_current", "x"):
                    idx = main_fields.indexOf(xf)
                    if idx != -1:
                        active_layer.changeAttributeValue(existing_feat_id, idx, str(x))

                for yf in ("latitude", "pos_latitu", "sf_latitude", "y_current", "df_y_current", "y"):
                    idx = main_fields.indexOf(yf)
                    if idx != -1:
                        active_layer.changeAttributeValue(existing_feat_id, idx, str(y))

                idx_rem = main_fields.indexOf("remarks")
                if idx_rem != -1:
                    active_layer.changeAttributeValue(existing_feat_id, idx_rem, "")

                idx_up = main_fields.indexOf("up_feature")
                if idx_up != -1:
                    active_layer.changeAttributeValue(existing_feat_id, idx_up, 1)

                idx_uploc = main_fields.indexOf("uplocation")
                if idx_uploc != -1:
                    active_layer.changeAttributeValue(existing_feat_id, idx_uploc, "1")

                if bsn_geoid:
                    for bf in ("bsn_geoid", "sf_bsn_geoid", "df_bsn_geoid"):
                        idx = main_fields.indexOf(bf)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, bsn_geoid)

                if ea_geo:
                    for ef in ("ea_geocode", "sf_ea_geocode", "df_ea_geocode"):
                        idx = main_fields.indexOf(ef)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, ea_geo)

                # Update padded separate columns on existing feature
                p_reg = padded_dict.get("region_code")
                if p_reg:
                    for rf in ("region_code", "sf_region_code", "df_region_code", "reg_code", "sf_reg_code", "df_reg_code"):
                        idx = main_fields.indexOf(rf)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, p_reg)

                p_prov = padded_dict.get("province_code")
                if p_prov:
                    for pf in ("province_code", "sf_province_code", "df_province_code", "prov_code", "sf_prov_code", "df_prov_code"):
                        idx = main_fields.indexOf(pf)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, p_prov)

                p_mun = padded_dict.get("city_mun_code")
                if p_mun:
                    for mf in ("city_mun_code", "sf_city_mun_code", "df_city_mun_code", "mun_code", "sf_mun_code", "df_mun_code", "city_code", "df_city_code"):
                        idx = main_fields.indexOf(mf)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, p_mun)

                p_brgy = padded_dict.get("barangay_code")
                if p_brgy:
                    for bf in ("barangay_code", "sf_barangay_code", "df_barangay_code", "barangay__code", "sf_barangay__code", "df_barangay__code", "brgy_code", "sf_brgy_code", "df_brgy_code"):
                        idx = main_fields.indexOf(bf)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, p_brgy)

                p_ean = padded_dict.get("ean")
                if p_ean:
                    for ef in ("ean", "sf_ean", "df_ean", "ea_code", "sf_ea_code", "df_ea_code", "ean_code", "df_ean_code"):
                        idx = main_fields.indexOf(ef)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, p_ean)

                p_bsn = padded_dict.get("bsn")
                if p_bsn:
                    for bf in ("bsn", "sf_bsn", "df_bsn", "bsn_code", "sf_bsn_code", "df_bsn_code", "bldg_sn", "sf_bldg_sn", "df_bldg_sn"):
                        idx = main_fields.indexOf(bf)
                        if idx != -1:
                            active_layer.changeAttributeValue(existing_feat_id, idx, p_bsn)

            reused_count += 1

        else:
            target_uuid = clean_uuid or str(uuid.uuid4())
            new_feat = QgsFeature(main_fields)
            new_geom = QgsGeometry.fromPointXY(pt)
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

            if bsn_geoid:
                for bf in ("bsn_geoid", "sf_bsn_geoid", "df_bsn_geoid"):
                    if bf in main_field_names:
                        _set_feat_attr(new_feat, bf, bsn_geoid)

            if ea_geo:
                for ef in ("ea_geocode", "sf_ea_geocode", "df_ea_geocode"):
                    if ef in main_field_names:
                        _set_feat_attr(new_feat, ef, ea_geo)

            # Set padded separate columns on new feature
            p_reg = padded_dict.get("region_code")
            if p_reg:
                for rf in ("region_code", "sf_region_code", "df_region_code", "reg_code", "sf_reg_code", "df_reg_code"):
                    if rf in main_field_names:
                        _set_feat_attr(new_feat, rf, p_reg)

            p_prov = padded_dict.get("province_code")
            if p_prov:
                for pf in ("province_code", "sf_province_code", "df_province_code", "prov_code", "sf_prov_code", "df_prov_code"):
                    if pf in main_field_names:
                        _set_feat_attr(new_feat, pf, p_prov)

            p_mun = padded_dict.get("city_mun_code")
            if p_mun:
                for mf in ("city_mun_code", "sf_city_mun_code", "df_city_mun_code", "mun_code", "sf_mun_code", "df_mun_code", "city_code", "df_city_code"):
                    if mf in main_field_names:
                        _set_feat_attr(new_feat, mf, p_mun)

            p_brgy = padded_dict.get("barangay_code")
            if p_brgy:
                for bf in ("barangay_code", "sf_barangay_code", "df_barangay_code", "barangay__code", "sf_barangay__code", "df_barangay__code", "brgy_code", "sf_brgy_code", "df_brgy_code"):
                    if bf in main_field_names:
                        _set_feat_attr(new_feat, bf, p_brgy)

            p_ean = padded_dict.get("ean")
            if p_ean:
                for ef in ("ean", "sf_ean", "df_ean", "ea_code", "sf_ea_code", "df_ea_code", "ean_code", "df_ean_code"):
                    if ef in main_field_names:
                        _set_feat_attr(new_feat, ef, p_ean)

            p_bsn = padded_dict.get("bsn")
            if p_bsn:
                for bf in ("bsn", "sf_bsn", "df_bsn", "bsn_code", "sf_bsn_code", "df_bsn_code", "bldg_sn", "sf_bldg_sn", "df_bldg_sn"):
                    if bf in main_field_names:
                        _set_feat_attr(new_feat, bf, p_bsn)

            for attr_k, attr_v in row_info["attributes"].items():
                if attr_v is None or str(attr_v).strip().lower() in ("null", "none", "nan", ""):
                    continue
                clean_k = attr_k
                if clean_k.startswith("df_") or clean_k.startswith("sf_"):
                    clean_k = clean_k[3:]
                if clean_k.lower() in (
                    "map_uuid", "uuid", "x_current", "y_current", "longitude", "latitude", "x", "y",
                    "bsn_geoid", "ea_geocode", "region_code", "reg_code", "province_code", "city_mun_code", "barangay_code",
                    "barangay__code", "ean", "bsn", "bsn_code", "prov_code", "mun_code", "brgy_code",
                    "bldg_sn", "bsn_num"
                ):
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
            "mapid": target_uuid,
            "df_mapid": target_uuid,
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
        if bsn_geoid:
            col_dict["bsn_geoid"] = bsn_geoid
            col_dict["sf_bsn_geoid"] = bsn_geoid
            col_dict["df_bsn_geoid"] = bsn_geoid
        if ea_geo:
            col_dict["ea_geocode"] = ea_geo
            col_dict["sf_ea_geocode"] = ea_geo
            col_dict["df_ea_geocode"] = ea_geo

        # Populate padded separate columns into col_dict for table cells and CSV sync
        p_reg = padded_dict.get("region_code")
        if p_reg:
            for rf in ("region_code", "sf_region_code", "df_region_code", "reg_code", "sf_reg_code", "df_reg_code"):
                col_dict[rf] = p_reg

        p_prov = padded_dict.get("province_code")
        if p_prov:
            for pf in ("province_code", "sf_province_code", "df_province_code", "prov_code", "sf_prov_code", "df_prov_code"):
                col_dict[pf] = p_prov

        p_mun = padded_dict.get("city_mun_code")
        if p_mun:
            for mf in ("city_mun_code", "sf_city_mun_code", "df_city_mun_code", "mun_code", "sf_mun_code", "df_mun_code", "city_code", "df_city_code"):
                col_dict[mf] = p_mun

        p_brgy = padded_dict.get("barangay_code")
        if p_brgy:
            for bf in ("barangay_code", "sf_barangay_code", "df_barangay_code", "barangay__code", "sf_barangay__code", "df_barangay__code", "brgy_code", "sf_brgy_code", "df_brgy_code"):
                col_dict[bf] = p_brgy

        p_ean = padded_dict.get("ean")
        if p_ean:
            for ef in ("ean", "sf_ean", "df_ean", "ea_code", "sf_ea_code", "df_ea_code", "ean_code", "df_ean_code"):
                col_dict[ef] = p_ean

        p_bsn = padded_dict.get("bsn")
        if p_bsn:
            for bf in ("bsn", "sf_bsn", "df_bsn", "bsn_code", "sf_bsn_code", "df_bsn_code", "bldg_sn", "sf_bldg_sn", "df_bldg_sn"):
                col_dict[bf] = p_bsn

        # Store by namespaced row index so table row r matches unambiguously
        updated_values[f"row_{r}"] = col_dict

        # Register composite unique keys (fid + map_uuid) to avoid collisions across rows
        cand_fids = [row_info.get("source_fid"), row_info.get("df_fid"), row_info.get("err_fid"), assigned_fid]
        target_idx = target_rows.index(r) if (target_rows and r in target_rows) else r
        if target_fids and target_idx < len(target_fids):
            cand_fids.append(target_fids[target_idx])
        for f_val in cand_fids:
            if f_val is not None and str(f_val).strip() not in ("", "NULL", "None"):
                for u_val in (target_uuid, clean_uuid):
                    uk = make_unique_feature_key(f_val, u_val)
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
        "message": f"Added {fixed_count} point(s){summary_str} to the Building Points file with BSN GEOID derived.",
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
    else:
        run_fix(layer, table=table, dialog=dialog, **kwargs)


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    target_keys: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute automated fix for generating point geometries across all validation checks."""
    return _run_fix_map_uuid_missing(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        target_keys=target_keys,
        **kwargs,
    )


run_generate_point_geometry = run_fix
