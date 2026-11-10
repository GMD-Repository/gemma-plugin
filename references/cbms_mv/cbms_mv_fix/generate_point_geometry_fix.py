# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Generate Point Geometry Process
Action: "Generate point geometry"
Universal Fix Action: Accessible across all CBMS map validation rules.

Generates point geometries in the Form 2 Geotagged Building Points layer (.geojson)
using coordinates (x_current, y_current) from the CSV datafile when no corresponding
point exists in the GeoJSON layer. Automatically derives bsn_geoid by concatenating
province_code, city_mun_code, barangay_code, ean, and bsn_code, and generates or
preserves map_uuid across GeoJSON, CSV datafiles, and the Reference Building Points layer.
"""
import math
import os
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

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


def _is_regular_bsn(bsn_str: str) -> bool:
    """Check if BSN represents a regular building (00001 - 55554)."""
    if not bsn_str:
        return False
    try:
        b_int = int(str(bsn_str).strip())
        return 0 < b_int < 55555
    except (ValueError, TypeError):
        return False


def _extract_first_matching(source: Dict[str, Any], candidates: List[str]) -> str:
    """Extract first non-empty value matching candidates (case-insensitive) from a dict."""
    if not source:
        return ""
    source_lower = {str(k).lower(): v for k, v in source.items() if _format_clean_code(v)}
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
    attrs: Dict[str, Any] = {}
    for k, v in (attributes or {}).items():
        if _format_clean_code(v):
            attrs[k] = v
            attrs[str(k).lower()] = v

    if _is_usable_feature(extra_feat):
        for fld in extra_feat.fields():
            fn = fld.name()
            v = _safe_get_attr(extra_feat, fn)
            if _format_clean_code(v) and fn.lower() not in attrs:
                attrs[fn] = v
                attrs[fn.lower()] = v

    raw_reg = _extract_first_matching(
        attrs,
        ["df_region_code", "region_code", "ref_region_code", "sf_region_code", "df_reg_code", "reg_code", "ref_reg_code", "sf_reg_code"],
    )
    raw_prov = _extract_first_matching(
        attrs,
        ["df_province_code", "province_code", "ref_province_code", "sf_province_code", "df_prov_code", "prov_code", "ref_prov_code", "sf_prov_code"],
    )
    raw_mun = _extract_first_matching(
        attrs,
        ["df_city_mun_code", "city_mun_code", "ref_city_mun_code", "sf_city_mun_code", "df_mun_code", "mun_code", "ref_mun_code", "sf_mun_code", "df_city_code", "city_code"],
    )
    raw_brgy = _extract_first_matching(
        attrs,
        ["df_barangay_code", "df_barangay__code", "barangay_code", "barangay__code", "ref_barangay_code", "sf_barangay_code", "sf_barangay__code", "df_brgy_code", "brgy_code", "ref_brgy_code", "sf_brgy_code", "df_bgy_code", "bgy_code"],
    )
    raw_ean = _extract_first_matching(
        attrs,
        ["df_ean", "ean", "ref_ean", "sf_ean", "df_ea_code", "ea_code", "ref_ea_code", "sf_ea_code", "df_ean_code", "ean_code", "df_ea_num", "ea_num"],
    )
    raw_bsn = _extract_first_matching(
        attrs,
        ["df_bsn", "bsn", "df_bsn_code", "bsn_code", "ref_bsn", "sf_bsn", "sf_bsn_code", "df_bldg_sn", "bldg_sn", "sf_bldg_sn", "bsn_num"],
    )
    raw_corr = _extract_first_matching(
        attrs,
        ["df_correspondence_code", "correspondence_code", "ref_correspondence_code", "sf_correspondence_code"],
    )

    reg = _pad_code(raw_reg, 2)
    prov = _pad_code(raw_prov, 3)
    mun = _pad_code(raw_mun, 2)
    brgy = _pad_code(raw_brgy, 3)
    ean = _pad_code(raw_ean, 6)
    bsn = _pad_code(raw_bsn, 5)
    corr = _pad_code(raw_corr, 9)

    ea_geo = _extract_first_matching(
        attrs,
        ["df_ea_geocode", "ea_geocode", "ref_ea_geocode", "sf_ea_geocode", "geocode", "df_geocode"],
    )

    if not ea_geo and prov and mun and brgy and ean:
        ea_geo = f"{prov}{mun}{brgy}{ean}"

    bsn_geoid = _extract_first_matching(
        attrs,
        ["df_bsn_geoid", "bsn_geoid", "ref_bsn_geoid", "sf_bsn_geoid"],
    )
    if prov and mun and brgy and ean and bsn:
        bsn_geoid = f"{prov}{mun}{brgy}{ean}{bsn}"
    elif ea_geo and bsn:
        bsn_geoid = f"{ea_geo}{bsn}"

    # If bsn_geoid was present (e.g. from Reference Layer) and components were missing, derive them
    if bsn_geoid and len(bsn_geoid) == 19:
        if not ea_geo:
            ea_geo = bsn_geoid[:14]
        if not prov:
            prov = bsn_geoid[0:3]
        if not mun:
            mun = bsn_geoid[3:5]
        if not brgy:
            brgy = bsn_geoid[5:8]
        if not ean:
            ean = bsn_geoid[8:14]
        if not bsn:
            bsn = bsn_geoid[14:19]
    elif ea_geo and len(ea_geo) == 14:
        if not prov:
            prov = ea_geo[0:3]
        if not mun:
            mun = ea_geo[3:5]
        if not brgy:
            brgy = ea_geo[5:8]
        if not ean:
            ean = ea_geo[8:14]

    return {
        "region_code": reg,
        "province_code": prov,
        "city_mun_code": mun,
        "barangay_code": brgy,
        "ean": ean,
        "bsn": bsn,
        "ea_geocode": ea_geo,
        "bsn_geoid": bsn_geoid,
        "correspondence_code": corr,
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


def _is_usable_feature(feat: Any) -> bool:
    """Return True if feat is a valid, populated QgsFeature."""
    if feat is None:
        return False
    try:
        if not feat.isValid():
            return False
        if hasattr(feat, "_attributes") and isinstance(feat._attributes, list) and len(feat._attributes) == 0:
            return False
        return True
    except Exception:
        return False


def _safe_get_attr(feat: Any, field_name: str) -> Any:
    """Safely retrieve an attribute value from a QgsFeature without raising IndexError or KeyError."""
    if not _is_usable_feature(feat):
        return None
    try:
        return feat[field_name]
    except Exception:
        try:
            return feat.attribute(field_name)
        except Exception:
            return None


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


def _load_reference_bldg_layer(dialog: Any = None, kwargs: Optional[Dict[str, Any]] = None) -> Optional[QgsVectorLayer]:
    """Locate or load the Reference Building Points layer (*_bldg_point) from dialog, project, or kwargs."""
    if kwargs:
        for k in ("reference_layer", "base_layer", "ref_layer"):
            cand = kwargs.get(k)
            if isinstance(cand, QgsVectorLayer) and cand.isValid():
                return cand

    base_path = ""
    if kwargs and isinstance(kwargs.get("base_layer_path"), str):
        base_path = kwargs["base_layer_path"].strip()
    if not base_path and dialog is not None and hasattr(dialog, "file_base") and dialog.file_base:
        try:
            base_path = dialog.file_base.filePath().strip()
        except Exception:
            base_path = ""

    proj = getattr(dialog, "project", None) if dialog is not None else None
    if proj is None:
        try:
            proj = QgsProject.instance()
        except Exception:
            proj = None

    # 1. Search already loaded project layers
    if proj is not None and hasattr(proj, "mapLayers"):
        try:
            norm_base = os.path.normpath(base_path).lower() if base_path else ""
            for lyr in proj.mapLayers().values():
                if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
                    continue
                src_raw = lyr.source() if hasattr(lyr, "source") else ""
                src_file = os.path.normpath(src_raw.split("|")[0]).lower() if src_raw else ""
                lyr_name_lower = (lyr.name() or "").lower()
                if norm_base and src_file == norm_base and (
                    "_bldg_point" in src_raw.lower() or lyr_name_lower.endswith("_bldg_point")
                ):
                    return lyr
                if not norm_base and lyr_name_lower.endswith("_bldg_point"):
                    return lyr
        except Exception:
            pass

    # 2. Load sublayer ending with '_bldg_point' from GeoPackage on disk (cached on dialog)
    if base_path and os.path.exists(base_path):
        if dialog is not None:
            cached_lyr_pair = getattr(dialog, "_cached_ref_bldg_layer", None)
            if (
                isinstance(cached_lyr_pair, tuple)
                and len(cached_lyr_pair) == 2
                and cached_lyr_pair[0] == base_path
                and cached_lyr_pair[1] is not None
                and hasattr(cached_lyr_pair[1], "isValid")
                and cached_lyr_pair[1].isValid()
            ):
                return cached_lyr_pair[1]
        try:
            bldg_sublayer = None
            try:
                import sqlite3
                conn = sqlite3.connect(base_path)
                cur = conn.cursor()
                cur.execute("SELECT table_name FROM gpkg_contents WHERE LOWER(table_name) LIKE '%_bldg_point'")
                row_s = cur.fetchone()
                conn.close()
                if row_s and row_s[0]:
                    bldg_sublayer = str(row_s[0]).strip()
            except Exception:
                bldg_sublayer = None

            if bldg_sublayer:
                ref_lyr = QgsVectorLayer(
                    f"{base_path}|layername={bldg_sublayer}",
                    bldg_sublayer,
                    "ogr",
                )
                if ref_lyr and ref_lyr.isValid():
                    if dialog is not None:
                        try:
                            setattr(dialog, "_cached_ref_bldg_layer", (base_path, ref_lyr))
                        except Exception:
                            pass
                    return ref_lyr

            tmp_layer = QgsVectorLayer(base_path, "tmp_ref_gpkg", "ogr")
            if tmp_layer and tmp_layer.isValid():
                for sub_item in tmp_layer.dataProvider().subLayers():
                    parts = sub_item.split("!!::!!") if "!!::!!" in sub_item else sub_item.split(":")
                    for part in parts:
                        if part.strip().endswith("_bldg_point"):
                            bldg_sublayer = part.strip()
                            break
                    if bldg_sublayer:
                        break
                if bldg_sublayer:
                    ref_lyr = QgsVectorLayer(
                        f"{base_path}|layername={bldg_sublayer}",
                        bldg_sublayer,
                        "ogr",
                    )
                    if ref_lyr and ref_lyr.isValid():
                        if dialog is not None:
                            try:
                                setattr(dialog, "_cached_ref_bldg_layer", (base_path, ref_lyr))
                            except Exception:
                                pass
                        return ref_lyr
                fnames = [f.name().lower() for f in tmp_layer.fields()]
                if any(u in fnames for u in ("map_uuid", "ref_map_uuid", "bsn_geoid", "ref_bsn_geoid")):
                    if dialog is not None:
                        try:
                            setattr(dialog, "_cached_ref_bldg_layer", (base_path, tmp_layer))
                        except Exception:
                            pass
                    return tmp_layer
        except Exception:
            pass

    return None


def _extract_feature_xy(feat: Any) -> Tuple[Optional[float], Optional[float]]:
    """Extract valid (x, y) from feature geometry or coordinate attributes."""
    if feat is None:
        return None, None
    try:
        if hasattr(feat, "hasGeometry") and feat.hasGeometry() and not feat.geometry().isEmpty():
            pt = feat.geometry().asPoint()
            if _is_valid_coord(pt.x()) and _is_valid_coord(pt.y()):
                return float(pt.x()), float(pt.y())
    except Exception:
        pass

    if hasattr(feat, "fields") and feat.fields():
        fnames_map = {f.name().lower(): f.name() for f in feat.fields()}
        fx, fy = None, None
        for xk in ("sf_longitude", "longitude", "ref_longitude", "df_x_current", "x_current"):
            v = _safe_get_attr(feat, fnames_map[xk]) if xk in fnames_map else None
            if _is_valid_coord(v):
                fx = float(str(v).strip())
                break
        for yk in ("sf_latitude", "latitude", "ref_latitude", "df_y_current", "y_current"):
            v = _safe_get_attr(feat, fnames_map[yk]) if yk in fnames_map else None
            if _is_valid_coord(v):
                fy = float(str(v).strip())
                break
        return fx, fy
    return None, None


def _same_5_digits_after_dot(val_a: Optional[float], val_b: Optional[float]) -> bool:
    """Return True if two coordinates share the same 5 digits after the dot (or differ by <= 1e-5)."""
    if val_a is None or val_b is None:
        return False
    try:
        fa = float(val_a)
        fb = float(val_b)
        if int(fa * 100000) == int(fb * 100000):
            return True
        return abs(fa - fb) <= (1e-5 + 1e-9)
    except (ValueError, TypeError):
        return False


def _extract_row_data(
    r: int,
    table: Optional[Any],
    error_layer: Optional[QgsVectorLayer],
    target_fids: Optional[List[Any]],
    target_uuids: Optional[List[str]],
    target_rows: Optional[List[int]] = None,
    dialog: Optional[Any] = None,
    header_map: Optional[Dict[str, int]] = None,
    err_by_fid: Optional[Dict[Any, QgsFeature]] = None,
    err_by_uuid: Optional[Dict[str, QgsFeature]] = None,
    err_feats_list: Optional[List[QgsFeature]] = None,
    f2_layer: Optional[QgsVectorLayer] = None,
    target_row_to_idx: Optional[Dict[int, int]] = None,
    f2_by_fid: Optional[Dict[Any, QgsFeature]] = None,
    f2_by_uuid: Optional[Dict[str, QgsFeature]] = None,
    f2_fnames_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Extract coordinates, UUID, and other attributes from table row, error_layer, and form2_layer."""
    row_info = {
        "x": None,
        "y": None,
        "uuid": "",
        "df_fid": None,
        "sf_fid": None,
        "source_fid": None,
        "err_fid": None,
        "attributes": {},
    }

    if target_row_to_idx is not None:
        target_idx = target_row_to_idx.get(r, r)
    else:
        target_idx = target_rows.index(r) if (target_rows and r in target_rows) else r

    # 1. Read from table widget if provided
    has_table_x_col = False
    has_table_y_col = False
    if table is not None:
        if header_map is None:
            header_map = {}
            for c in range(table.columnCount()):
                h_item = table.horizontalHeaderItem(c)
                h_text = h_item.text().strip().lower() if h_item else ""
                if h_text and h_text not in ("", "action", "actions"):
                    header_map[h_text] = c

        # Extract X coordinate strictly from df_x_current (or x_current)
        for candidate in ("df_x_current", "x_current"):
            if candidate in header_map:
                has_table_x_col = True
                it = table.item(r, header_map[candidate])
                if it and _is_valid_coord(it.text()):
                    row_info["x"] = float(it.text().strip())
                    break

        # Extract Y coordinate strictly from df_y_current (or y_current)
        for candidate in ("df_y_current", "y_current"):
            if candidate in header_map:
                has_table_y_col = True
                it = table.item(r, header_map[candidate])
                if it and _is_valid_coord(it.text()):
                    row_info["y"] = float(it.text().strip())
                    break

        # Extract UUID
        for candidate in ("df_map_uuid", "ref_map_uuid", "map_uuid", "sf_map_uuid", "df_mapid", "mapid", "uuid"):
            if candidate in header_map:
                it = table.item(r, header_map[candidate])
                if it and _is_valid_uuid(it.text()):
                    row_info["uuid"] = it.text().strip()
                    break

        # Extract metadata from Item 0
        it0 = table.item(r, 0)
        if it0:
            row_info["source_fid"] = it0.data(0x0100) if it0.data(0x0100) is not None else it0.data(0)
            if not row_info["uuid"]:
                for u_role in (0x0100 + 1, 1, 0x0100 + 5, 5, 0x0100 + 7, 7):
                    u_data = it0.data(u_role)
                    if _is_valid_uuid(u_data):
                        row_info["uuid"] = str(u_data).strip()
                        break
            row_info["df_fid"] = next(
                (
                    v for v in (it0.data(0x0100 + 4), it0.data(4), it0.data(0x0100 + 2), it0.data(2))
                    if v is not None and str(v).strip() not in ("", "NULL", "None")
                ),
                None,
            )
            row_info["err_fid"] = it0.data(0x0100 + 3) if it0.data(0x0100 + 3) is not None else it0.data(3)
            row_info["sf_fid"] = it0.data(0x0100 + 6) if it0.data(0x0100 + 6) is not None else it0.data(6)

        # Extract non-empty table attributes
        for col_name, c_idx in header_map.items():
            it = table.item(r, c_idx)
            if it:
                cell_txt = it.text().strip()
                if _format_clean_code(cell_txt):
                    row_info["attributes"][col_name] = cell_txt
                fn_role = it.data(0x0100 + 2)
                if fn_role and _format_clean_code(cell_txt):
                    row_info["attributes"][str(fn_role).strip().lower()] = cell_txt

    # 2. Augment from error_layer if coordinates, UUID, or attributes are missing
    if error_layer and error_layer.isValid():
        matching_feat = None
        if row_info["err_fid"] is not None:
            if err_by_fid is not None:
                matching_feat = err_by_fid.get(row_info["err_fid"]) or err_by_fid.get(str(row_info["err_fid"]))
            if not matching_feat and err_by_fid is None:
                try:
                    cand_f = error_layer.getFeature(row_info["err_fid"])
                    if _is_usable_feature(cand_f):
                        matching_feat = cand_f
                except Exception:
                    pass

        if not matching_feat and row_info["uuid"]:
            u_low = str(row_info["uuid"]).strip().lower()
            if err_by_uuid is not None and u_low in err_by_uuid:
                matching_feat = err_by_uuid[u_low]
            elif err_by_uuid is None:
                clean_uuid = str(row_info["uuid"]).replace("'", "''")
                for uf in ("df_map_uuid", "ref_map_uuid", "map_uuid", "sf_map_uuid", "df_mapid", "mapid", "uuid"):
                    if uf in error_layer.fields().names():
                        try:
                            for f in error_layer.getFeatures(f'"{uf}" = \'{clean_uuid}\''):
                                if _is_usable_feature(f):
                                    matching_feat = f
                                    break
                        except Exception:
                            pass
                    if matching_feat:
                        break

        if not matching_feat and target_fids and target_idx < len(target_fids):
            tfid = target_fids[target_idx]
            if err_by_fid is not None and tfid is not None:
                matching_feat = err_by_fid.get(tfid) or err_by_fid.get(str(tfid))
            if not matching_feat and err_by_fid is None and tfid is not None:
                try:
                    cand_f = error_layer.getFeature(tfid)
                    if _is_usable_feature(cand_f):
                        matching_feat = cand_f
                except Exception:
                    pass

        if not matching_feat:
            if err_feats_list is not None:
                if target_idx < len(err_feats_list):
                    matching_feat = err_feats_list[target_idx]
            else:
                try:
                    feats_list = [f for f in error_layer.getFeatures() if _is_usable_feature(f)]
                    if target_idx < len(feats_list):
                        matching_feat = feats_list[target_idx]
                except Exception:
                    pass

        if _is_usable_feature(matching_feat):
            err_fnames = matching_feat.fields().names()
            if not has_table_x_col:
                for x_col_candidate in ("df_x_current", "x_current"):
                    if row_info["x"] is None and x_col_candidate in err_fnames:
                        val = _safe_get_attr(matching_feat, x_col_candidate)
                        if _is_valid_coord(val):
                            row_info["x"] = float(str(val).strip())

            if not has_table_y_col:
                for y_col_candidate in ("df_y_current", "y_current"):
                    if row_info["y"] is None and y_col_candidate in err_fnames:
                        val = _safe_get_attr(matching_feat, y_col_candidate)
                        if _is_valid_coord(val):
                            row_info["y"] = float(str(val).strip())

            if not row_info["uuid"]:
                for u_candidate in ("df_map_uuid", "ref_map_uuid", "map_uuid", "sf_map_uuid", "df_mapid", "mapid", "uuid"):
                    if u_candidate in err_fnames:
                        val = _safe_get_attr(matching_feat, u_candidate)
                        if _is_valid_uuid(val):
                            row_info["uuid"] = str(val).strip()
                            break

            if row_info["df_fid"] is None and "df_fid" in err_fnames:
                val_df = _safe_get_attr(matching_feat, "df_fid")
                if _format_clean_code(val_df):
                    row_info["df_fid"] = val_df

            if row_info["sf_fid"] is None and "sf_fid" in err_fnames:
                val_sf = _safe_get_attr(matching_feat, "sf_fid")
                if _format_clean_code(val_sf):
                    row_info["sf_fid"] = val_sf

            for fld in matching_feat.fields():
                fn = fld.name()
                val = _safe_get_attr(matching_feat, fn)
                if _format_clean_code(val) and not _format_clean_code(row_info["attributes"].get(fn)):
                    row_info["attributes"][fn] = val

    # 3. Augment from Form 2 CSV layer in O(1) using pre-indexed dicts (or fallback if called standalone)
    f2_feat = None
    lookup_fid = row_info.get("df_fid") if row_info.get("df_fid") is not None else row_info.get("source_fid")
    lookup_uuid = row_info.get("uuid")
    if f2_by_fid is not None or f2_by_uuid is not None:
        if lookup_fid is not None and f2_by_fid:
            f2_feat = f2_by_fid.get(lookup_fid) or f2_by_fid.get(str(lookup_fid).strip())
        if f2_feat is None and lookup_uuid and f2_by_uuid:
            f2_feat = f2_by_uuid.get(str(lookup_uuid).strip().lower())
    elif dialog and hasattr(dialog, "_find_form2_feature"):
        try:
            active_f2 = f2_layer if (f2_layer is not None and f2_layer.isValid()) else (
                dialog._get_or_load_form2_layer() if hasattr(dialog, "_get_or_load_form2_layer") else None
            )
            if active_f2 and active_f2.isValid():
                f2_feat = dialog._find_form2_feature(
                    active_f2,
                    fid=lookup_fid,
                    map_uuid=lookup_uuid,
                )
        except Exception:
            f2_feat = None

    if isinstance(f2_feat, dict):
        try:
            f2_fnames = f2_fnames_map if f2_fnames_map is not None else {k.lower(): k for k in f2_feat}
            if row_info["x"] is None and not has_table_x_col:
                for xc in ("df_x_current", "x_current"):
                    if xc in f2_fnames and _is_valid_coord(f2_feat.get(f2_fnames[xc])):
                        row_info["x"] = float(str(f2_feat[f2_fnames[xc]]).strip())
                        break
            if row_info["y"] is None and not has_table_y_col:
                for yc in ("df_y_current", "y_current"):
                    if yc in f2_fnames and _is_valid_coord(f2_feat.get(f2_fnames[yc])):
                        row_info["y"] = float(str(f2_feat[f2_fnames[yc]]).strip())
                        break
            if not row_info["uuid"]:
                for uc in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid"):
                    if uc in f2_fnames and _is_valid_uuid(f2_feat.get(f2_fnames[uc])):
                        row_info["uuid"] = str(f2_feat[f2_fnames[uc]]).strip()
                        break
            existing_lower = {k.lower(): k for k in row_info["attributes"] if _format_clean_code(row_info["attributes"][k])}
            for fn_low, fn in f2_fnames.items():
                v = f2_feat.get(fn)
                if _format_clean_code(v):
                    if fn_low not in existing_lower:
                        row_info["attributes"][fn] = v
                    if f"df_{fn_low}" not in existing_lower:
                        row_info["attributes"][f"df_{fn}"] = v
        except Exception:
            pass
    elif _is_usable_feature(f2_feat):
        try:
            f2_fnames = f2_fnames_map if f2_fnames_map is not None else {f.name().lower(): f.name() for f in f2_feat.fields()}
            if row_info["x"] is None and not has_table_x_col:
                for xc in ("df_x_current", "x_current"):
                    if xc in f2_fnames and _is_valid_coord(_safe_get_attr(f2_feat, f2_fnames[xc])):
                        row_info["x"] = float(str(_safe_get_attr(f2_feat, f2_fnames[xc])).strip())
                        break
            if row_info["y"] is None and not has_table_y_col:
                for yc in ("df_y_current", "y_current"):
                    if yc in f2_fnames and _is_valid_coord(_safe_get_attr(f2_feat, f2_fnames[yc])):
                        row_info["y"] = float(str(_safe_get_attr(f2_feat, f2_fnames[yc])).strip())
                        break
            if not row_info["uuid"]:
                for uc in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid"):
                    if uc in f2_fnames and _is_valid_uuid(_safe_get_attr(f2_feat, f2_fnames[uc])):
                        row_info["uuid"] = str(_safe_get_attr(f2_feat, f2_fnames[uc])).strip()
                        break
            existing_lower = {k.lower(): k for k in row_info["attributes"] if _format_clean_code(row_info["attributes"][k])}
            for fn_low, fn in f2_fnames.items():
                v = _safe_get_attr(f2_feat, fn)
                if _format_clean_code(v):
                    if fn_low not in existing_lower:
                        row_info["attributes"][fn] = v
                    if f"df_{fn_low}" not in existing_lower:
                        row_info["attributes"][f"df_{fn}"] = v
        except Exception:
            pass

    # 4. Fallback to target_uuids list if UUID still missing
    if not row_info["uuid"] and target_uuids and target_idx < len(target_uuids):
        if _is_valid_uuid(target_uuids[target_idx]):
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
    from the selected row (or Reference Building Points layer fallback),
    generating or preserving map_uuid, and computing bsn_geoid.
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

    dlg = dialog if dialog is not None else kwargs.get("dialog")

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
        parent_w = dlg or kwargs.get("parent")
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

    # Precompute target_rows index map for O(1) lookup instead of O(N) list.index()
    target_row_to_idx: Dict[int, int] = {r: idx for idx, r in enumerate(target_rows)} if target_rows else {}

    # Precompute table header map once
    header_map: Optional[Dict[str, int]] = None
    if table is not None:
        header_map = {}
        for c in range(table.columnCount()):
            h_item = table.horizontalHeaderItem(c)
            h_text = h_item.text().strip().lower() if h_item else ""
            if h_text and h_text not in ("", "action", "actions"):
                header_map[h_text] = c

    # Pre-index error_layer once for O(1) lookup
    err_by_fid: Dict[Any, QgsFeature] = {}
    err_by_uuid: Dict[str, QgsFeature] = {}
    err_feats_list: List[QgsFeature] = []
    if error_layer and error_layer.isValid():
        try:
            err_fnames = error_layer.fields().names()
            err_uuid_cols = [uf for uf in ("df_map_uuid", "ref_map_uuid", "map_uuid", "sf_map_uuid", "df_mapid", "mapid", "uuid") if uf in err_fnames]
            for ef in error_layer.getFeatures():
                if not _is_usable_feature(ef):
                    continue
                err_feats_list.append(ef)
                ef_id = ef.id()
                if ef_id is not None:
                    err_by_fid[ef_id] = ef
                    err_by_fid[str(ef_id)] = ef
                for u_col in err_uuid_cols:
                    u_val = _safe_get_attr(ef, u_col)
                    if _is_valid_uuid(u_val):
                        u_low = str(u_val).strip().lower()
                        if u_low not in err_by_uuid:
                            err_by_uuid[u_low] = ef
        except Exception:
            pass

    # Load and pre-index Form 2 records once before row loop (cached on dialog; uses fast direct CSV reader when possible)
    f2_layer = None
    f2_by_fid: Dict[Any, Any] = {}
    f2_by_uuid: Dict[str, Any] = {}
    f2_fnames_map: Dict[str, str] = {}
    form2_csv_path = ""
    if dlg is not None and hasattr(dlg, "file_form2") and dlg.file_form2:
        try:
            form2_csv_path = dlg.file_form2.filePath().strip()
        except Exception:
            form2_csv_path = ""

    if form2_csv_path and form2_csv_path.lower().endswith(".csv") and os.path.exists(form2_csv_path):
        try:
            f2_mtime = os.path.getmtime(form2_csv_path)
            f2_cache_key = ("csv_direct", form2_csv_path, f2_mtime)
            cached_f2 = getattr(dlg, "_cached_f2_index", None) if dlg is not None else None
            if isinstance(cached_f2, tuple) and len(cached_f2) == 4 and cached_f2[0] == f2_cache_key:
                _, f2_by_fid, f2_by_uuid, f2_fnames_map = cached_f2
            else:
                import csv as _csv
                with open(form2_csv_path, "r", encoding="utf-8-sig", errors="replace") as f_csv:
                    reader = _csv.DictReader(f_csv)
                    fnames = reader.fieldnames or []
                    f2_fnames_map = {fn.strip().lower(): fn for fn in fnames if fn}
                    f2_fid_cols = [f2_fnames_map[c] for c in ("fid", "df_fid", "id", "ogc_fid") if c in f2_fnames_map]
                    f2_uuid_cols = [f2_fnames_map[c] for c in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid") if c in f2_fnames_map]
                    for row_1based, row_d in enumerate(reader, start=1):
                        f2_by_fid[row_1based] = row_d
                        f2_by_fid[str(row_1based)] = row_d
                        for fc in f2_fid_cols:
                            fval = row_d.get(fc)
                            if fval is not None:
                                s_fval = str(fval).strip()
                                if s_fval and s_fval not in f2_by_fid:
                                    f2_by_fid[s_fval] = row_d
                        for uc in f2_uuid_cols:
                            uval = row_d.get(uc)
                            if _is_valid_uuid(uval):
                                u_low = str(uval).strip().lower()
                                if u_low not in f2_by_uuid:
                                    f2_by_uuid[u_low] = row_d
                if dlg is not None:
                    try:
                        setattr(dlg, "_cached_f2_index", (f2_cache_key, f2_by_fid, f2_by_uuid, f2_fnames_map))
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        if dlg is not None:
            if hasattr(dlg, "_find_existing_form2_layer"):
                try:
                    f2_layer = dlg._find_existing_form2_layer()
                except Exception:
                    f2_layer = None
            if f2_layer is None and hasattr(dlg, "_get_or_load_form2_layer"):
                try:
                    f2_layer = dlg._get_or_load_form2_layer()
                except Exception:
                    f2_layer = None
        if f2_layer and f2_layer.isValid():
            try:
                f2_src = f2_layer.source() if hasattr(f2_layer, "source") else id(f2_layer)
                f2_cnt = f2_layer.featureCount() if hasattr(f2_layer, "featureCount") else -1
                f2_cache_key = (f2_src, f2_cnt)
                cached_f2 = getattr(dlg, "_cached_f2_index", None) if dlg is not None else None
                if isinstance(cached_f2, tuple) and len(cached_f2) == 4 and cached_f2[0] == f2_cache_key:
                    _, f2_by_fid, f2_by_uuid, f2_fnames_map = cached_f2
                else:
                    f2_fnames_map = {f.name().lower(): f.name() for f in f2_layer.fields()}
                    f2_fid_cols = [f2_fnames_map[c] for c in ("fid", "df_fid", "id", "ogc_fid") if c in f2_fnames_map]
                    f2_uuid_cols = [f2_fnames_map[c] for c in ("map_uuid", "mapid", "df_map_uuid", "df_mapid", "uuid") if c in f2_fnames_map]
                    for f2_f in f2_layer.getFeatures():
                        if not _is_usable_feature(f2_f):
                            continue
                        fid_id = f2_f.id()
                        if fid_id is not None:
                            f2_by_fid[fid_id] = f2_f
                            f2_by_fid[str(fid_id)] = f2_f
                        for fc in f2_fid_cols:
                            fval = _safe_get_attr(f2_f, fc)
                            if fval is not None:
                                s_fval = str(fval).strip()
                                if s_fval and s_fval not in f2_by_fid:
                                    f2_by_fid[s_fval] = f2_f
                        for uc in f2_uuid_cols:
                            uval = _safe_get_attr(f2_f, uc)
                            if _is_valid_uuid(uval):
                                u_low = str(uval).strip().lower()
                                if u_low not in f2_by_uuid:
                                    f2_by_uuid[u_low] = f2_f
                    if dlg is not None:
                        try:
                            setattr(dlg, "_cached_f2_index", (f2_cache_key, f2_by_fid, f2_by_uuid, f2_fnames_map))
                        except Exception:
                            pass
            except Exception:
                pass

    # Extract row data once per selected row (1-to-1 with rows_to_process)
    row_info_cache: Dict[int, Dict[str, Any]] = {}
    for r in rows_to_process:
        row_info = _extract_row_data(
            r,
            table,
            error_layer,
            target_fids,
            target_uuids,
            target_rows=target_rows,
            dialog=dlg,
            header_map=header_map,
            err_by_fid=err_by_fid,
            err_by_uuid=err_by_uuid,
            err_feats_list=err_feats_list,
            f2_layer=f2_layer,
            target_row_to_idx=target_row_to_idx,
            f2_by_fid=f2_by_fid,
            f2_by_uuid=f2_by_uuid,
            f2_fnames_map=f2_fnames_map,
        )
        row_info_cache[r] = row_info

    # Load Reference Building Points layer (*_bldg_point in .gpkg) if available (cached per layer source)
    ref_layer = _load_reference_bldg_layer(dlg, kwargs)
    ref_by_uuid: Dict[str, QgsFeature] = {}
    ref_by_bsn_geoid: Dict[str, QgsFeature] = {}
    ref_features_list: List[Tuple[QgsFeature, Optional[float], Optional[float], str, str]] = []
    ref_valid_uuids: Set[str] = set()

    if ref_layer and ref_layer.isValid():
        try:
            ref_src = ref_layer.source() if hasattr(ref_layer, "source") else id(ref_layer)
            ref_cnt = ref_layer.featureCount() if hasattr(ref_layer, "featureCount") else -1
            ref_cache_key = (ref_src, ref_cnt)
            cached_ref = getattr(dlg, "_cached_ref_bldg_index", None) if dlg is not None else None
            if isinstance(cached_ref, tuple) and len(cached_ref) == 5 and cached_ref[0] == ref_cache_key:
                _, ref_by_uuid, ref_by_bsn_geoid, ref_features_list, ref_valid_uuids = cached_ref
            else:
                ref_fnames = ref_layer.fields().names()
                ref_lmap = {fn.lower(): fn for fn in ref_fnames}
                ref_uuid_cols = [ref_lmap[uf] for uf in ("ref_map_uuid", "map_uuid", "sf_map_uuid", "uuid") if uf in ref_lmap]
                ref_bsn_geoid_col = next((ref_lmap[c] for c in ("bsn_geoid", "ref_bsn_geoid", "sf_bsn_geoid", "df_bsn_geoid") if c in ref_lmap), None)
                ref_ea_col = next((ref_lmap[c] for c in ("ea_geocode", "ref_ea_geocode", "sf_ea_geocode", "geocode") if c in ref_lmap), None)
                ref_bsn_col = next((ref_lmap[c] for c in ("bsn", "ref_bsn", "bsn_code", "sf_bsn", "bldg_sn") if c in ref_lmap), None)
                for r_feat in ref_layer.getFeatures():
                    r_uuid = ""
                    for uf in ref_uuid_cols:
                        val_u = _safe_get_attr(r_feat, uf)
                        if _is_valid_uuid(val_u):
                            r_uuid = str(val_u).strip()
                            break
                    r_bsn_geoid = _format_clean_code(_safe_get_attr(r_feat, ref_bsn_geoid_col)) if ref_bsn_geoid_col else ""
                    r_bsn = _pad_code(_safe_get_attr(r_feat, ref_bsn_col), 5) if ref_bsn_col else ""
                    if not r_bsn_geoid:
                        if ref_ea_col and r_bsn:
                            r_ea = _format_clean_code(_safe_get_attr(r_feat, ref_ea_col))
                            if r_ea:
                                r_bsn_geoid = f"{r_ea}{r_bsn}"
                        if not r_bsn_geoid:
                            r_padded = _extract_padded_boundary_codes({}, extra_feat=r_feat)
                            r_bsn_geoid = r_padded["bsn_geoid"]
                            r_bsn = r_padded["bsn"]
                    elif not r_bsn and len(r_bsn_geoid) == 19:
                        r_bsn = r_bsn_geoid[14:19]
                    rx, ry = _extract_feature_xy(r_feat)
                    if r_uuid:
                        ref_by_uuid[r_uuid.lower()] = r_feat
                        ref_valid_uuids.add(r_uuid.lower())
                    if r_bsn_geoid and _is_regular_bsn(r_bsn):
                        ref_by_bsn_geoid[r_bsn_geoid] = r_feat
                    ref_features_list.append((r_feat, rx, ry, r_uuid, r_bsn_geoid))
                if dlg is not None:
                    try:
                        setattr(dlg, "_cached_ref_bldg_index", (ref_cache_key, ref_by_uuid, ref_by_bsn_geoid, ref_features_list, ref_valid_uuids))
                    except Exception:
                        pass
        except Exception:
            pass

    # Pre-index active_layer (.geojson) in a single O(N) pass and determine max_positive_fid
    main_fields = active_layer.fields()
    main_field_names = [f.name() for f in main_fields]
    field_idx_map: Dict[str, int] = {f.name(): idx for idx, f in enumerate(main_fields)}
    uuid_fields = [fn for fn in main_field_names if fn.lower() in ("map_uuid", "sf_map_uuid", "uuid")]
    fid_attr_fields = [fn for fn in main_field_names if fn.lower() in ("fid", "sf_fid")]

    active_by_uuid: Dict[str, Tuple[QgsFeature, str]] = {}
    active_by_fid: Dict[int, Tuple[QgsFeature, str]] = {}
    active_by_bsn_geoid: Dict[str, Tuple[QgsFeature, str]] = {}
    active_coords_list: List[Tuple[QgsFeature, Optional[float], Optional[float], str]] = []
    max_positive_fid: int = 0
    uncommitted_feats: List[QgsFeature] = []
    display_fid_by_feat_id: Dict[int, int] = {}
    uncommitted_fid_map: Dict[int, int] = {}
    if dlg is not None:
        existing_uncommitted_map = getattr(dlg, "_uncommitted_fid_map", None)
        if isinstance(existing_uncommitted_map, dict):
            uncommitted_fid_map = existing_uncommitted_map
        else:
            try:
                setattr(dlg, "_uncommitted_fid_map", uncommitted_fid_map)
            except Exception:
                pass

    try:
        for feat in active_layer.getFeatures():
            if not _is_usable_feature(feat):
                continue
            f_id = feat.id()
            pos_fid = None
            if isinstance(f_id, int) and f_id >= 0:
                pos_fid = f_id
                if f_id > max_positive_fid:
                    max_positive_fid = f_id
            elif isinstance(f_id, int) and f_id < 0 and f_id in uncommitted_fid_map:
                pos_fid = uncommitted_fid_map[f_id]
                if pos_fid > max_positive_fid:
                    max_positive_fid = pos_fid
            for ff in fid_attr_fields:
                fv = _safe_get_attr(feat, ff)
                if fv is not None and str(fv).strip().lstrip("-").isdigit():
                    try:
                        fv_int = int(str(fv).strip())
                        if fv_int >= 0 and (pos_fid is None or (isinstance(f_id, int) and f_id < 0 and fv_int > 0)):
                            pos_fid = fv_int
                        if fv_int > max_positive_fid:
                            max_positive_fid = fv_int
                    except Exception:
                        pass
            if f_id is not None:
                if pos_fid is not None and pos_fid >= 0:
                    display_fid_by_feat_id[f_id] = pos_fid
                    if isinstance(f_id, int) and f_id < 0:
                        uncommitted_fid_map[f_id] = pos_fid
                else:
                    uncommitted_feats.append(feat)

            cand_u = ""
            for uf in uuid_fields:
                vu = _safe_get_attr(feat, uf)
                if _is_valid_uuid(vu):
                    cand_u = str(vu).strip()
                    u_low = cand_u.lower()
                    if u_low not in active_by_uuid:
                        active_by_uuid[u_low] = (feat, cand_u)
                    break

            if isinstance(f_id, int):
                active_by_fid[f_id] = (feat, cand_u)
            if pos_fid is not None and pos_fid not in active_by_fid:
                active_by_fid[pos_fid] = (feat, cand_u)

            f_padded = _extract_padded_boundary_codes({}, extra_feat=feat)
            if f_padded["bsn_geoid"] and _is_regular_bsn(f_padded["bsn"]):
                if f_padded["bsn_geoid"] not in active_by_bsn_geoid:
                    active_by_bsn_geoid[f_padded["bsn_geoid"]] = (feat, cand_u)

            fx, fy = _extract_feature_xy(feat)
            active_coords_list.append((feat, fx, fy, cand_u))

        for u_feat in uncommitted_feats:
            uf_id = u_feat.id()
            if uf_id is not None and uf_id not in display_fid_by_feat_id:
                max_positive_fid += 1
                display_fid_by_feat_id[uf_id] = max_positive_fid
                if isinstance(uf_id, int) and uf_id < 0:
                    uncommitted_fid_map[uf_id] = max_positive_fid
    except Exception:
        pass

    # 2. Validation & Reference Layer Enrichment:
    # Check if valid coordinates (x_current, y_current) are present, or recover from Reference Layer / existing feature
    valid_rows_data: List[Tuple[int, Dict[str, Any], float, float, str, str, str, Dict[str, str], str]] = []
    # Items: (r, row_info, x, y, clean_uuid, bsn_geoid, ea_geo, padded_dict, ref_uuid)
    invalid_rows_data: List[Tuple[int, Dict[str, Any], bool, bool]] = []

    for r in rows_to_process:
        row_info = row_info_cache[r]
        x = row_info.get("x")
        y = row_info.get("y")
        raw_uuid = row_info.get("uuid")
        clean_uuid = str(raw_uuid).strip() if _is_valid_uuid(raw_uuid) else ""

        padded_dict = _extract_padded_boundary_codes(row_info.get("attributes", {}))
        bsn_geoid = padded_dict["bsn_geoid"]
        bsn_val = padded_dict["bsn"]

        # Match in Reference Layer (*_bldg_point) when BOTH selected map_uuid AND 5 digits after the dot match
        ref_feat = None
        if clean_uuid and _is_valid_coord(x) and _is_valid_coord(y) and ref_features_list:
            for cand_rf, rx, ry, r_u, _ in ref_features_list:
                if (
                    r_u
                    and r_u.strip().lower() == clean_uuid.strip().lower()
                    and _same_5_digits_after_dot(rx, float(x))
                    and _same_5_digits_after_dot(ry, float(y))
                ):
                    ref_feat = cand_rf
                    break

        ref_uuid = ""
        if ref_feat is not None:
            for uf in ("ref_map_uuid", "map_uuid", "sf_map_uuid", "uuid"):
                if uf in ref_feat.fields().names() and _is_valid_uuid(_safe_get_attr(ref_feat, uf)):
                    ref_uuid = str(_safe_get_attr(ref_feat, uf)).strip()
                    break
            # Enrich missing attributes and padded boundary codes from Reference Layer feature
            padded_dict = _extract_padded_boundary_codes(row_info.get("attributes", {}), extra_feat=ref_feat)
            for fld in ref_feat.fields():
                fn = fld.name()
                val = _safe_get_attr(ref_feat, fn)
                if _format_clean_code(val) and not _format_clean_code(row_info["attributes"].get(fn)):
                    row_info["attributes"][fn] = val

        bsn_geoid = padded_dict["bsn_geoid"]
        ea_geo = padded_dict["ea_geocode"]
        has_coords = _is_valid_coord(x) and _is_valid_coord(y)
        has_uuid = bool(ref_uuid or clean_uuid)

        if has_coords:
            valid_rows_data.append((r, row_info, float(x), float(y), clean_uuid, bsn_geoid, ea_geo, padded_dict, ref_uuid))
        else:
            invalid_rows_data.append((r, row_info, False, has_uuid))

    if not valid_rows_data:
        parent_w = dlg or kwargs.get("parent")
        if parent_w and hasattr(parent_w, "iface") and parent_w.iface:
            parent_w = parent_w.iface.mainWindow()
        if QMessageBox and parent_w:
            QMessageBox.warning(
                parent_w,
                "Cannot Generate Point Geometry",
                f"None of the {len(rows_to_process)} selected row(s) contain valid coordinates "
                "(df_x_current, df_y_current, x_current, y_current).\n\n"
                "Please verify that the selected rows have valid GPS coordinates to create points on the map.",
            )
        return {
            "success": False,
            "message": "The selected row(s) lack valid coordinates (df_x_current, df_y_current, x_current, y_current).",
            "fixed_count": 0,
            "updated_values": {},
        }

    # 3. Ensure active_layer is in editing mode (generate points directly without confirmation prompt)
    if not active_layer.isEditable() and not active_layer.startEditing():
        return {
            "success": False,
            "message": "The Building Points file could not be opened for editing.",
            "fixed_count": 0,
            "updated_values": {},
        }

    # Coordinate transformation if layer is projected
    src_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    dest_crs = active_layer.crs() if hasattr(active_layer, "crs") else None
    transform = None
    if dest_crs and dest_crs.isValid() and dest_crs != src_crs and not dest_crs.isGeographic():
        transform = QgsCoordinateTransform(src_crs, dest_crs, QgsProject.instance())

    is_geo = dest_crs.isGeographic() if (dest_crs and hasattr(dest_crs, "isGeographic") and dest_crs.isValid()) else True
    tol = 1e-7 if is_geo else 0.01

    updated_values: Dict[Any, Dict[str, Any]] = {}
    fixed_count = 0
    created_count = 0
    reused_count = 0
    failed_rows = []
    created_batch_fids = set()
    created_batch_features: List[Tuple[Any, Any, float, float, str]] = []  # (assigned_fid, pt, x, y, target_uuid)
    used_uuids_in_layer: Set[str] = set(active_by_uuid.keys())

    def _set_layer_attr_if_changed(fid_val: int, feat_obj: Optional[QgsFeature], field_name: str, new_val: Any) -> None:
        idx = field_idx_map.get(field_name, -1)
        if idx == -1:
            return
        if feat_obj is not None:
            cur_val = _safe_get_attr(feat_obj, field_name)
            if cur_val == new_val or (cur_val is not None and new_val is not None and str(cur_val) == str(new_val) and not isinstance(new_val, bool)):
                return
        active_layer.changeAttributeValue(fid_val, idx, new_val)

    has_edit_cmd = False
    if hasattr(active_layer, "beginEditCommand"):
        try:
            active_layer.beginEditCommand("Generate Point Geometry")
            has_edit_cmd = True
        except Exception:
            has_edit_cmd = False

    if dlg is not None:
        dlg._suppress_dirty_ui_refresh = True

    try:
        for r, row_info, x, y, clean_uuid, bsn_geoid, ea_geo, padded_dict, ref_uuid in valid_rows_data:
            if feedback and feedback.isCanceled():
                break

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

            # Strict New-Point Generation:
            # Never hijack or overwrite an existing point that already has geometry on the map.
            # Only populate an existing feature in place if the selected row explicitly points to an
            # sf_fid in active_layer whose geometry is currently missing/empty (e.g. geom__missing).
            if _format_clean_code(row_info.get("sf_fid")):
                try:
                    sf_fid_int = int(str(row_info["sf_fid"]).strip())
                    cand_f = None
                    cand_u = ""
                    if sf_fid_int in active_by_fid:
                        cand_f, cand_u = active_by_fid[sf_fid_int]
                    else:
                        f_lookup = active_layer.getFeature(sf_fid_int)
                        if _is_usable_feature(f_lookup):
                            cand_f = f_lookup
                            for uf in uuid_fields:
                                val_u = _safe_get_attr(cand_f, uf)
                                if _is_valid_uuid(val_u):
                                    cand_u = str(val_u).strip()
                                    break
                    if (
                        cand_f is not None
                        and cand_f.id() not in created_batch_fids
                        and (not cand_f.hasGeometry() or cand_f.geometry().isEmpty())
                    ):
                        existing_feat = cand_f
                        existing_feat_id = cand_f.id()
                        existing_uuid = cand_u
                except Exception:
                    pass

            if existing_feat_id is not None:
                assigned_fid = existing_feat_id
                if isinstance(existing_feat_id, int) and existing_feat_id >= 0:
                    display_sf_fid = display_fid_by_feat_id.get(existing_feat_id, existing_feat_id)
                elif existing_feat_id in display_fid_by_feat_id:
                    display_sf_fid = display_fid_by_feat_id[existing_feat_id]
                else:
                    max_positive_fid += 1
                    display_sf_fid = max_positive_fid
                    display_fid_by_feat_id[existing_feat_id] = display_sf_fid
                    if isinstance(existing_feat_id, int) and existing_feat_id < 0:
                        uncommitted_fid_map[existing_feat_id] = display_sf_fid

                # Authoritative UUID priority: Reference Layer UUID -> Form 2 UUID -> Existing Feature UUID -> New UUID4
                if ref_uuid:
                    target_uuid = ref_uuid
                elif clean_uuid:
                    target_uuid = clean_uuid
                elif existing_uuid:
                    target_uuid = existing_uuid
                else:
                    target_uuid = str(uuid.uuid4())

                if existing_feat is not None:
                    for uf in uuid_fields:
                        _set_layer_attr_if_changed(existing_feat_id, existing_feat, uf, target_uuid)

                    if not is_reused_from_batch:
                        if hasattr(active_layer, "changeGeometry"):
                            active_layer.changeGeometry(existing_feat_id, new_geom)
                        elif hasattr(active_layer, "dataProvider") and hasattr(active_layer.dataProvider(), "changeGeometryValues"):
                            active_layer.dataProvider().changeGeometryValues({existing_feat_id: new_geom})

                    for sf in ("status", "sf_status"):
                        _set_layer_attr_if_changed(existing_feat_id, existing_feat, sf, "active")

                    # Reset soft-delete flag so load_cbms_geojson does not filter this feature out
                    for df_col in ("is_deleted", "sf_is_deleted"):
                        _set_layer_attr_if_changed(existing_feat_id, existing_feat, df_col, False)

                    for xf in ("longitude", "pos_longit", "sf_longitude", "x_current", "df_x_current", "x"):
                        _set_layer_attr_if_changed(existing_feat_id, existing_feat, xf, str(x))

                    for yf in ("latitude", "pos_latitu", "sf_latitude", "y_current", "df_y_current", "y"):
                        _set_layer_attr_if_changed(existing_feat_id, existing_feat, yf, str(y))

                    _set_layer_attr_if_changed(existing_feat_id, existing_feat, "remarks", "")
                    _set_layer_attr_if_changed(existing_feat_id, existing_feat, "up_feature", 1)
                    _set_layer_attr_if_changed(existing_feat_id, existing_feat, "uplocation", "1")

                    # Re-derive boundary codes incorporating any existing_feat attributes as fallback
                    if not bsn_geoid or not ea_geo:
                        merged_padded = _extract_padded_boundary_codes(row_info.get("attributes", {}), extra_feat=existing_feat)
                        bsn_geoid = bsn_geoid or merged_padded["bsn_geoid"]
                        ea_geo = ea_geo or merged_padded["ea_geocode"]
                        for pk, pv in merged_padded.items():
                            if pv and not padded_dict.get(pk):
                                padded_dict[pk] = pv

                    if bsn_geoid:
                        for bf in ("bsn_geoid", "sf_bsn_geoid", "df_bsn_geoid"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, bf, bsn_geoid)

                    if ea_geo:
                        for ef in ("ea_geocode", "sf_ea_geocode", "df_ea_geocode"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, ef, ea_geo)

                    # Update padded separate columns on existing feature
                    p_reg = padded_dict.get("region_code")
                    if p_reg:
                        for rf in ("region_code", "sf_region_code", "df_region_code", "reg_code", "sf_reg_code", "df_reg_code"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, rf, p_reg)

                    p_prov = padded_dict.get("province_code")
                    if p_prov:
                        for pf in ("province_code", "sf_province_code", "df_province_code", "prov_code", "sf_prov_code", "df_prov_code"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, pf, p_prov)

                    p_mun = padded_dict.get("city_mun_code")
                    if p_mun:
                        for mf in ("city_mun_code", "sf_city_mun_code", "df_city_mun_code", "mun_code", "sf_mun_code", "df_mun_code", "city_code", "df_city_code"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, mf, p_mun)

                    p_brgy = padded_dict.get("barangay_code")
                    if p_brgy:
                        for bf in ("barangay_code", "sf_barangay_code", "df_barangay_code", "barangay__code", "sf_barangay__code", "df_barangay__code", "brgy_code", "sf_brgy_code", "df_brgy_code"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, bf, p_brgy)

                    p_ean = padded_dict.get("ean")
                    if p_ean:
                        for ef in ("ean", "sf_ean", "df_ean", "ea_code", "sf_ea_code", "df_ea_code", "ean_code", "df_ean_code"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, ef, p_ean)

                    p_bsn = padded_dict.get("bsn")
                    if p_bsn:
                        for bf in ("bsn", "sf_bsn", "df_bsn", "bsn_code", "sf_bsn_code", "df_bsn_code", "bldg_sn", "sf_bldg_sn", "df_bldg_sn"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, bf, p_bsn)

                    p_corr = padded_dict.get("correspondence_code")
                    if p_corr:
                        for cf in ("correspondence_code", "sf_correspondence_code", "df_correspondence_code"):
                            _set_layer_attr_if_changed(existing_feat_id, existing_feat, cf, p_corr)

                    # Populate any missing non-boundary attributes (e.g. en_code) onto existing_feat
                    for attr_k, attr_v in row_info["attributes"].items():
                        if not _format_clean_code(attr_v):
                            continue
                        clean_k = attr_k
                        for pfx in ("df_", "sf_", "ref_"):
                            if clean_k.lower().startswith(pfx):
                                clean_k = clean_k[len(pfx):]
                                break
                        if clean_k.lower() in (
                            "fid", "id", "sf_fid", "df_fid", "ref_fid",
                            "map_uuid", "mapid", "uuid", "x_current", "y_current", "longitude", "latitude", "x", "y",
                            "bsn_geoid", "ea_geocode", "region_code", "reg_code", "province_code", "city_mun_code", "barangay_code",
                            "barangay__code", "ean", "bsn", "bsn_code", "prov_code", "mun_code", "brgy_code",
                            "bldg_sn", "bsn_num", "correspondence_code", "is_deleted", "sf_is_deleted", "status", "sf_status",
                        ):
                            continue
                        for target_k in (attr_k, clean_k, f"sf_{clean_k}"):
                            if target_k in field_idx_map and target_k.lower() not in ("fid", "id", "sf_fid", "df_fid", "ref_fid"):
                                cur_existing = _safe_get_attr(existing_feat, target_k)
                                if not _format_clean_code(cur_existing):
                                    _set_layer_attr_if_changed(existing_feat_id, existing_feat, target_k, attr_v)

                reused_count += 1

            else:
                # 1. Compare Selected Row (df_map_uuid, df_x_current, df_y_current) against Existing Points (.geojson):
                #    Copy map_uuid ONLY when BOTH selected map_uuid AND 5 digits after the dot match.
                # 2. Else if no matching point in .geojson, compare Selected Row against Reference Points (*_bldg_point in .gpkg):
                #    Copy map_uuid ONLY when BOTH selected map_uuid AND 5 digits after the dot match.
                # 3. Else: generate new map_uuid.
                matched_existing_uuid = ""
                matched_existing_feat = None
                if clean_uuid:
                    clean_u_low = clean_uuid.strip().lower()
                    for c_item in created_batch_features:
                        c_x, c_y, c_uuid = c_item[2], c_item[3], c_item[4]
                        c_feat = c_item[5] if len(c_item) > 5 else None
                        if (
                            c_uuid
                            and c_uuid.strip().lower() == clean_u_low
                            and _same_5_digits_after_dot(c_x, x)
                            and _same_5_digits_after_dot(c_y, y)
                        ):
                            matched_existing_uuid = clean_uuid.strip()
                            matched_existing_feat = c_feat
                            break
                    if not matched_existing_uuid:
                        for cand_feat, feat_x, feat_y, cand_uuid in active_coords_list:
                            if (
                                cand_uuid
                                and cand_uuid.strip().lower() == clean_u_low
                                and _same_5_digits_after_dot(feat_x, x)
                                and _same_5_digits_after_dot(feat_y, y)
                            ):
                                matched_existing_uuid = clean_uuid.strip()
                                matched_existing_feat = cand_feat
                                break

                if matched_existing_uuid:
                    target_uuid = matched_existing_uuid
                    if matched_existing_feat is not None:
                        ex_padded = _extract_padded_boundary_codes({}, extra_feat=matched_existing_feat)
                        if ex_padded.get("correspondence_code"):
                            padded_dict["correspondence_code"] = ex_padded["correspondence_code"]
                elif ref_uuid and clean_uuid and ref_uuid.strip().lower() == clean_uuid.strip().lower():
                    target_uuid = clean_uuid.strip()
                else:
                    target_uuid = str(uuid.uuid4())
                used_uuids_in_layer.add(target_uuid.lower())

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

                for df_col in ("is_deleted", "sf_is_deleted"):
                    if df_col in main_field_names:
                        _set_feat_attr(new_feat, df_col, False)

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

                p_corr = padded_dict.get("correspondence_code")
                if p_corr:
                    for cf in ("correspondence_code", "sf_correspondence_code", "df_correspondence_code"):
                        if cf in main_field_names:
                            _set_feat_attr(new_feat, cf, p_corr)

                for attr_k, attr_v in row_info["attributes"].items():
                    if not _format_clean_code(attr_v):
                        continue
                    clean_k = attr_k
                    for pfx in ("df_", "sf_", "ref_"):
                        if clean_k.lower().startswith(pfx):
                            clean_k = clean_k[len(pfx):]
                            break
                    if clean_k.lower() in (
                        "fid", "id", "sf_fid", "df_fid", "ref_fid",
                        "map_uuid", "mapid", "uuid", "x_current", "y_current", "longitude", "latitude", "x", "y",
                        "bsn_geoid", "ea_geocode", "region_code", "reg_code", "province_code", "city_mun_code", "barangay_code",
                        "barangay__code", "ean", "bsn", "bsn_code", "prov_code", "mun_code", "brgy_code",
                        "bldg_sn", "bsn_num", "correspondence_code", "is_deleted", "sf_is_deleted", "status", "sf_status",
                    ):
                        continue
                    for target_k in (attr_k, clean_k, f"sf_{clean_k}"):
                        if target_k in field_idx_map and target_k.lower() not in ("fid", "id", "sf_fid", "df_fid", "ref_fid"):
                            try:
                                _set_feat_attr(new_feat, target_k, attr_v)
                            except Exception:
                                pass

                max_positive_fid += 1
                display_sf_fid = max_positive_fid
                for ff in fid_attr_fields:
                    _set_feat_attr(new_feat, ff, display_sf_fid)

                if hasattr(active_layer, "addFeature"):
                    active_layer.addFeature(new_feat)
                elif hasattr(active_layer, "addFeatures"):
                    active_layer.addFeatures([new_feat])
                elif hasattr(active_layer, "dataProvider") and hasattr(active_layer.dataProvider(), "addFeatures"):
                    active_layer.dataProvider().addFeatures([new_feat])
                assigned_fid = new_feat.id()
                if assigned_fid is not None:
                    if isinstance(assigned_fid, int) and assigned_fid > 0:
                        display_sf_fid = assigned_fid
                        if assigned_fid > max_positive_fid:
                            max_positive_fid = assigned_fid
                    display_fid_by_feat_id[assigned_fid] = display_sf_fid
                    if isinstance(assigned_fid, int) and assigned_fid < 0:
                        uncommitted_fid_map[assigned_fid] = display_sf_fid
                    created_batch_fids.add(assigned_fid)
                    created_batch_features.append((assigned_fid, pt, x, y, target_uuid, new_feat))

                created_count += 1

            col_dict = {
                "sf_map_uuid": target_uuid,
                "df_map_uuid": target_uuid,
                "map_uuid": target_uuid,
                "mapid": target_uuid,
                "df_mapid": target_uuid,
                "sf_fid": display_sf_fid,
                "sf_longitude": str(x),
                "sf_latitude": str(y),
                "df_x_current": str(x),
                "df_y_current": str(y),
                "x_current": str(x),
                "y_current": str(y),
                "sf_status": "active",
                "status": "active",
                "sf_is_deleted": False,
                "is_deleted": False,
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

            p_corr = padded_dict.get("correspondence_code")
            if p_corr:
                for cf in ("correspondence_code", "sf_correspondence_code", "df_correspondence_code"):
                    col_dict[cf] = p_corr

            # Populate other non-empty attributes (such as sf_en_code, en_code) into col_dict so table cells update from NULL
            if _is_usable_feature(existing_feat):
                for fld in existing_feat.fields():
                    fn = fld.name()
                    if fn.lower() in ("fid", "id", "sf_fid", "df_fid", "ref_fid"):
                        continue
                    fv = _safe_get_attr(existing_feat, fn)
                    if _format_clean_code(fv):
                        clean_fn = fn
                        for pfx in ("df_", "sf_", "ref_"):
                            if clean_fn.lower().startswith(pfx):
                                clean_fn = clean_fn[len(pfx):]
                                break
                        for tk in (fn, clean_fn, f"sf_{clean_fn}"):
                            if tk not in col_dict:
                                col_dict[tk] = fv

            for attr_k, attr_v in row_info["attributes"].items():
                if not _format_clean_code(attr_v):
                    continue
                clean_k = attr_k
                for pfx in ("df_", "sf_", "ref_"):
                    if clean_k.lower().startswith(pfx):
                        clean_k = clean_k[len(pfx):]
                        break
                if clean_k.lower() in ("fid", "id", "sf_fid", "df_fid", "ref_fid"):
                    continue
                for tk in (attr_k, clean_k, f"sf_{clean_k}"):
                    if tk not in col_dict:
                        col_dict[tk] = attr_v

            # Store by namespaced row index so table row r matches unambiguously
            updated_values[f"row_{r}"] = col_dict

            # Register composite unique keys (fid + map_uuid) to avoid collisions across rows
            cand_fids = [row_info.get("source_fid"), row_info.get("df_fid"), row_info.get("err_fid"), row_info.get("sf_fid"), assigned_fid, display_sf_fid]
            target_idx = target_row_to_idx.get(r, r)
            if target_fids and target_idx < len(target_fids):
                cand_fids.append(target_fids[target_idx])
            for f_val in cand_fids:
                if f_val is not None and str(f_val).strip() not in ("", "NULL", "None"):
                    for u_val in (target_uuid, clean_uuid, ref_uuid):
                        uk = make_unique_feature_key(f_val, u_val)
                        if uk:
                            updated_values[uk] = col_dict
                            updated_values[uk.lower()] = col_dict

            fixed_count += 1
    finally:
        if dlg is not None:
            dlg._suppress_dirty_ui_refresh = False

    if has_edit_cmd and hasattr(active_layer, "endEditCommand"):
        try:
            if fixed_count > 0:
                active_layer.endEditCommand()
            elif hasattr(active_layer, "destroyEditCommand"):
                active_layer.destroyEditCommand()
        except Exception:
            pass

    if fixed_count > 0:
        if hasattr(active_layer, "layerModified") and hasattr(active_layer.layerModified, "emit"):
            try:
                active_layer.layerModified.emit()
            except Exception:
                pass
        active_layer.triggerRepaint()

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
