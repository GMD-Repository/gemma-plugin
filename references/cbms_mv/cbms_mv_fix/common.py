# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Shared Utilities for Fix Modules.
"""
from typing import Any, Optional, Set, Tuple

from qgis.core import (
    NULL,
    QgsFeature,
)


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


def make_unique_feature_key(fid: Any, map_uuid: Any) -> str:
    """
    Generate a composite unique identifier by concatenating fid and map_uuid:
        '{clean_fid}_{clean_map_uuid}'
    Handles NULL/None values, empty strings, and type conversions cleanly.
    """
    clean_fid = ""
    if fid is not None and fid != NULL:
        s = str(fid).strip()
        if s and s.lower() not in ("null", "none", "nan"):
            clean_fid = s

    clean_uuid = ""
    if map_uuid is not None and map_uuid != NULL:
        u = str(map_uuid).strip()
        if u and u.lower() not in ("null", "none", "nan"):
            clean_uuid = u

    if clean_fid and clean_uuid:
        return f"{clean_fid}_{clean_uuid}"
    elif clean_fid:
        return f"{clean_fid}_"
    elif clean_uuid:
        return f"_{clean_uuid}"
    return ""


def extract_feature_unique_key(feat: Any) -> str:
    """Extract '{fid}_{map_uuid}' composite unique key from a QgsFeature."""
    if not feat:
        return ""
    fid = feat.id() if hasattr(feat, "id") else None
    uuid_str, _ = _extract_feature_id_sig(feat)
    return make_unique_feature_key(fid, uuid_str)


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
        s = str(item).strip()
        if s and s.lower() not in ("none", "null", "nan") and not s.startswith(("<", "Mock")):
            res.add(item)
            res.add(s)
            res.add(s.lower())
    return res


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
