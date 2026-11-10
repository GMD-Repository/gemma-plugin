# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Deduplicate Features Process
Action: "Delete duplicate features (retain one)"
Validation ID: mv_2027_hp_4a_longitude__duplicate

Checks all columns to see if features with duplicate coordinates are identical.
Retains only one active feature and marks duplicate features as 'deleted' in sf_status / status.
"""
from typing import Any, Dict, List, Optional, Tuple

from qgis.core import (
    NULL,
    QgsFeature,
    QgsField,
    QgsProcessingFeedback,
    QgsVectorLayer,
)
try:
    from qgis.PyQt.QtCore import Qt, QVariant
    from qgis.PyQt.QtWidgets import (
        QMessageBox,
        QPushButton,
    )
except ImportError:
    try:
        from PyQt5.QtCore import Qt, QVariant
        from PyQt5.QtWidgets import (
            QMessageBox,
            QPushButton,
        )
    except ImportError:
        Qt = None
        QVariant = None
        QMessageBox = None
        QPushButton = None

try:
    from .common import (
        _extract_feature_coord_sig,
        _extract_feature_id_sig,
        _flatten_ids,
        _normalize_cell_val,
        _normalize_coordinate,
        is_valid_qobject,
        make_unique_feature_key,
    )
    from .delete_selected_features_fix import _is_deleted_val, mark_feature_deleted
    from .generate_point_geometry_fix import (
        _extract_feature_xy,
        _load_reference_bldg_layer,
        _same_5_digits_after_dot,
    )
except ImportError:
    from common import (
        _extract_feature_coord_sig,
        _extract_feature_id_sig,
        _flatten_ids,
        _normalize_cell_val,
        _normalize_coordinate,
        is_valid_qobject,
        make_unique_feature_key,
    )
    from delete_selected_features_fix import _is_deleted_val, mark_feature_deleted
    from generate_point_geometry_fix import (
        _extract_feature_xy,
        _load_reference_bldg_layer,
        _same_5_digits_after_dot,
    )

FIX_ID = "mv_2027_hp_4a_longitude__duplicate"
FIX_NAME = "Delete duplicate features (retain one)"
FIX_DESCRIPTION = (
    "Checks all columns of features with duplicate coordinates to see if they are identical. "
    "Retains only one active feature and marks duplicate features as 'deleted' in sf_status / status."
)

# Columns to check for identical values in deduplication:
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
}


def _is_deduplication_check_col(col_name: str) -> bool:
    c = str(col_name).strip().lower()
    base_c = c[3:] if c.startswith(("sf_", "df_")) else c
    return base_c in DEDUPLICATION_CHECK_COLS


_TECHNICAL_SKIP_COLS = {
    "id",
    "fid",
    "sf_fid",
    "df_fid",
    "ref_fid",
    "err_fid",
    "source_fid",
    "is_deleted",
    "sf_is_deleted",
    "df_is_deleted",
    "is_status",
    "sf_is_status",
    "status",
    "sf_status",
    "distance",
    "action",
    "#",
    "",
}


def _has_meaningful_val(val: Any) -> bool:
    """Return True if val is a non-empty, non-null attribute value."""
    if val is None or val == NULL or isinstance(val, bool):
        return False
    s = str(val).strip()
    return bool(s) and s.lower() not in ("null", "none", "nan")


def _normalize_attr_col_key(col_name: str) -> str:
    """Strip sf_/df_/ref_ prefix and lowercase so equivalent columns are counted once."""
    c = str(col_name).strip().lower()
    for pfx in ("sf_", "df_", "ref_"):
        if c.startswith(pfx):
            return c[len(pfx):]
    return c


def _load_ref_bldg_points(
    dialog: Optional[Any] = None, **kwargs
) -> List[Tuple[str, Optional[float], Optional[float]]]:
    """
    Load Reference Points (*_bldg_point in .gpkg) as a list of (ref_uuid_lower, rx, ry).
    Reuses dialog._cached_ref_bldg_index when available.
    """
    ref_points: List[Tuple[str, Optional[float], Optional[float]]] = []
    try:
        ref_layer = _load_reference_bldg_layer(dialog, **kwargs)
        if not ref_layer or not hasattr(ref_layer, "isValid") or not ref_layer.isValid():
            return ref_points

        ref_cache_key = ref_layer.source() if hasattr(ref_layer, "source") else id(ref_layer)
        cached_idx = getattr(dialog, "_cached_ref_bldg_index", None) if dialog is not None else None
        if isinstance(cached_idx, tuple) and len(cached_idx) == 5 and cached_idx[0] == ref_cache_key:
            for item in cached_idx[3]:
                if len(item) >= 4:
                    _, rx, ry, r_u = item[0], item[1], item[2], item[3]
                    if r_u:
                        ref_points.append((str(r_u).strip().lower(), rx, ry))
            return ref_points

        ref_fnames = ref_layer.fields().names()
        ref_lmap = {fn.lower(): fn for fn in ref_fnames}
        ref_uuid_cols = [
            ref_lmap[uf]
            for uf in ("ref_map_uuid", "map_uuid", "sf_map_uuid", "uuid")
            if uf in ref_lmap
        ]
        for r_feat in ref_layer.getFeatures():
            r_uuid = ""
            for uf in ref_uuid_cols:
                try:
                    val_u = r_feat[uf]
                except Exception:
                    val_u = None
                if _has_meaningful_val(val_u):
                    r_uuid = str(val_u).strip().lower()
                    break
            if r_uuid:
                rx, ry = _extract_feature_xy(r_feat)
                ref_points.append((r_uuid, rx, ry))
    except Exception:
        pass
    return ref_points


def _matches_reference_bldg_point(
    uuid_val: Optional[str],
    lon_val: Any,
    lat_val: Any,
    ref_points: Optional[List[Tuple[str, Optional[float], Optional[float]]]] = None,
) -> int:
    """
    Return 1 if BOTH map_uuid AND coordinates (5 digits after the dot) match a
    Reference Point in *_bldg_point (.gpkg), else 0.
    """
    if not ref_points or not _has_meaningful_val(uuid_val):
        return 0
    try:
        lon_f = float(str(lon_val).strip())
        lat_f = float(str(lat_val).strip())
    except (ValueError, TypeError):
        return 0

    u_low = str(uuid_val).strip().lower()
    for r_u, rx, ry in ref_points:
        if (
            r_u == u_low
            and _same_5_digits_after_dot(rx, lon_f)
            and _same_5_digits_after_dot(ry, lat_f)
        ):
            return 1
    return 0


def _compute_feature_completeness_score(
    main_feat: Optional[QgsFeature] = None,
    layer_feat: Optional[QgsFeature] = None,
    table: Optional[Any] = None,
    row_idx: Optional[int] = None,
    tie_breaker: int = 0,
    ref_match: int = 0,
) -> Tuple[int, int, int, int]:
    """
    Compute retention priority score for a candidate duplicate record:
      (ref_match, other_cols_filled_count, total_cols_filled_count, -tie_breaker)
    1. ref_match: 1 if map_uuid + coordinates match Reference Points (*_bldg_point in .gpkg), else 0.
    2. other_cols_filled_count: count of non-empty values in other active-layer (.geojson) columns.
    3. total_cols_filled_count: total count of non-empty columns.
    4. -tie_breaker: earlier row/feature index wins on tie.
    """
    filled_other_cols = set()
    filled_all_cols = set()

    for feat in (main_feat, layer_feat):
        if feat is not None and feat.isValid():
            for fld in feat.fields():
                fn = fld.name()
                fn_low = fn.strip().lower()
                base_k = _normalize_attr_col_key(fn_low)
                if (
                    fn_low in _TECHNICAL_SKIP_COLS
                    or base_k in _TECHNICAL_SKIP_COLS
                    or fn_low.startswith(("dup_", "_orig"))
                ):
                    continue
                try:
                    val = feat[fn]
                except Exception:
                    val = None
                if _has_meaningful_val(val):
                    filled_all_cols.add(base_k)
                    if base_k not in DEDUPLICATION_CHECK_COLS:
                        filled_other_cols.add(base_k)

    if table is not None and row_idx is not None and hasattr(table, "columnCount"):
        for c in range(1, table.columnCount() - 1):
            h_it = table.horizontalHeaderItem(c)
            h_name = h_it.text().strip() if h_it else ""
            h_low = h_name.lower()
            base_k = _normalize_attr_col_key(h_low)
            if (
                h_low in _TECHNICAL_SKIP_COLS
                or base_k in _TECHNICAL_SKIP_COLS
                or h_low.startswith(("dup_", "_orig"))
            ):
                continue
            cell_it = table.item(row_idx, c)
            cell_txt = cell_it.text().strip() if cell_it else ""
            if _has_meaningful_val(cell_txt):
                filled_all_cols.add(base_k)
                if base_k not in DEDUPLICATION_CHECK_COLS:
                    filled_other_cols.add(base_k)

    return (int(ref_match), len(filled_other_cols), len(filled_all_cols), -int(tie_breaker))


def _resolve_feature_by_fid(target_layer: Optional[Any], fid_candidates: List[Any]) -> Optional[QgsFeature]:
    """Resolve a QgsFeature from target_layer by feature ID or fid/sf_fid attribute."""
    if not target_layer or not hasattr(target_layer, "isValid") or not target_layer.isValid():
        return None
    clean_ints = []
    for fc in fid_candidates:
        if fc is None or fc == NULL:
            continue
        s = str(fc).strip()
        if s and s.lstrip("-").isdigit():
            try:
                clean_ints.append(int(s))
            except Exception:
                pass
    for fid_int in clean_ints:
        try:
            f = target_layer.getFeature(fid_int)
            if f and f.isValid():
                return f
        except Exception:
            pass
    if clean_ints and hasattr(target_layer, "getFeatures"):
        try:
            fnames = [f.name() for f in target_layer.fields() if f.name().lower() in ("fid", "sf_fid", "id")]
            if fnames:
                target_set = set(clean_ints)
                for f in target_layer.getFeatures():
                    for fn in fnames:
                        try:
                            v = f[fn]
                            if v is not None and v != NULL and str(v).strip().lstrip("-").isdigit():
                                if int(str(v).strip()) in target_set:
                                    return f
                        except Exception:
                            pass
        except Exception:
            pass
    return None


def _is_feature_already_deleted(feat: Optional[QgsFeature]) -> bool:
    """Return True if a feature has is_deleted=True or status='deleted'."""
    if not feat or not feat.isValid():
        return False
    for fn in ("is_deleted", "sf_is_deleted", "df_is_deleted", "is_status", "sf_is_status"):
        try:
            if _is_deleted_val(feat[fn]):
                return True
        except Exception:
            pass
    for fn in ("status", "sf_status"):
        try:
            v = feat[fn]
            if v is not None and v != NULL and str(v).strip().lower() == "deleted":
                return True
        except Exception:
            pass
    return False


def _is_table_row_already_deleted(table: Any, r: int, layer: Optional[Any] = None) -> bool:
    """Return True if row r is already marked deleted in table cells, action button, or layer feature."""
    for c in range(1, table.columnCount() - 1):
        h_it = table.horizontalHeaderItem(c)
        h_name = h_it.text().strip().lower() if h_it else ""
        cell_it = table.item(r, c)
        cell_txt = cell_it.text().strip() if cell_it else ""
        if not cell_txt:
            continue
        if h_name in ("is_deleted", "sf_is_deleted", "df_is_deleted", "is_status", "sf_is_status"):
            if _is_deleted_val(cell_txt):
                return True
        elif h_name in ("status", "sf_status"):
            if cell_txt.lower() == "deleted":
                return True

    if QPushButton is not None:
        act_w = table.cellWidget(r, table.columnCount() - 1)
        if act_w:
            for child in act_w.findChildren(QPushButton):
                if child.text().strip().lower() == "deleted":
                    return True

    item0 = table.item(r, 0)
    if item0 and layer and hasattr(layer, "getFeature"):
        source_fid = item0.data(Qt.UserRole)
        err_fid = item0.data(Qt.UserRole + 3)
        try:
            feat = None
            if err_fid is not None:
                feat = layer.getFeature(err_fid)
            if (not feat or not feat.isValid()) and source_fid is not None:
                feat = layer.getFeature(source_fid)
            if _is_feature_already_deleted(feat):
                return True
        except Exception:
            pass

    return False


def deduplicate_features(
    dialog: Any,
    *args,
    combo_actions: Optional[Any] = None,
    btn_actions: Optional[Any] = None,
    btn_update_selected: Optional[Any] = None,
    process_all: bool = False,
    prompt_confirm: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    """
    Interactive process handler for deduplicating features in the table:
    1. Compares all survey columns across features in the tab (or checked features).
    2. Verifies if duplicate features are 100% identical in all compared columns.
    3. If identical, retains only one feature without sf_status 'deleted'.
    4. Marks all other duplicate features as 'deleted' in sf_status / status.
    5. Styles the table cells with 'deleted'.
    """
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    val_id = args[0] if (len(args) >= 3 and isinstance(args[0], str)) else "deduplicate_features"

    if not is_valid_qobject(dialog) or not is_valid_qobject(table):
        return {"success": False, "fixed_count": 0, "message": "Dialog or table is not valid."}

    # Determine which rows to process
    checked_rows = []
    for r in range(table.rowCount()):
        item0 = table.item(r, 0)
        if item0 and item0.checkState() == Qt.Checked:
            checked_rows.append(r)

    if checked_rows and not process_all:
        candidate_rows = checked_rows
    else:
        candidate_rows = list(range(table.rowCount()))

    # Disregard all rows that are already marked deleted (is_deleted = true / status = 'deleted')
    rows_to_process = [
        r for r in candidate_rows
        if not _is_table_row_already_deleted(table, r, layer=layer)
    ]

    if len(rows_to_process) < 2:
        if QMessageBox:
            QMessageBox.information(
                dialog,
                "Not Enough Records",
                "Please select at least 2 records to check for duplicates.",
            )
        return {"success": False, "fixed_count": 0, "message": "Fewer than 2 rows to process."}

    # Identify compared columns from table headers
    compared_cols = []
    for c in range(1, table.columnCount() - 1):
        h_it = table.horizontalHeaderItem(c)
        h_name = h_it.text().strip() if h_it else ""
        if _is_deduplication_check_col(h_name):
            compared_cols.append((c, h_name))

    # Fallback to non-technical columns if none match
    if not compared_cols:
        for c in range(1, table.columnCount() - 1):
            h_it = table.horizontalHeaderItem(c)
            h_name = h_it.text().strip() if h_it else ""
            c_low = h_name.lower()
            base_low = c_low[3:] if c_low.startswith(("sf_", "df_")) else c_low
            if not c_low.startswith(("dup_", "sf_status", "status", "fid", "err_fid", "_orig", "action")) \
               and c_low not in ("", "#", "distance", "sf_en_code", "en_code", "df_en_code", "sf_remarks", "remarks") \
               and base_low not in ("pos_longitude", "pos_latitude", "pos_longit", "pos_latitu"):
                compared_cols.append((c, h_name))

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

        if base_c in ("longitude", "longitud"):
            lon_cols.append(c)
        elif base_c in ("latitude", "latitud"):
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

    row_coord_sigs: Dict[int, Tuple[str, str, str, str, str]] = {}
    row_attr_sigs: Dict[int, Tuple] = {}

    for r in rows_to_process:
        item0 = table.item(r, 0)
        source_fid = item0.data(Qt.UserRole) if item0 else None
        uuid_data = item0.data(Qt.UserRole + 1) if item0 else None
        err_fid = item0.data(Qt.UserRole + 3) if item0 else None

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

    def _get_row_distinct_sf_fid(r_idx: int) -> Any:
        it0 = table.item(r_idx, 0)
        if it0:
            sf_f = it0.data(Qt.UserRole + 6)
            if _has_meaningful_val(sf_f):
                return str(sf_f).strip()
            s_f = it0.data(Qt.UserRole)
            if _has_meaningful_val(s_f):
                return str(s_f).strip()
        for c in range(1, table.columnCount() - 1):
            h_it = table.horizontalHeaderItem(c)
            if h_it and h_it.text().strip().lower() in ("sf_fid", "fid"):
                c_it = table.item(r_idx, c)
                if c_it and _has_meaningful_val(c_it.text()):
                    return c_it.text().strip()
        return f"row_{r_idx}"

    # Deduplicate each candidate group by distinct sf_fid so multiple UI rows for the same sf_fid
    # are not treated as duplicates of themselves
    def _filter_distinct_sf_fid_rows(r_list: List[int]) -> List[int]:
        seen_fids = set()
        unique_rows = []
        for r_idx in r_list:
            f_key = _get_row_distinct_sf_fid(r_idx)
            if f_key not in seen_fids:
                seen_fids.add(f_key)
                unique_rows.append(r_idx)
        return unique_rows

    # Check A: Group by 4 key coordinate fields
    coord_groups: Dict[Tuple, List[int]] = {}
    for r in rows_to_process:
        csig = row_coord_sigs.get(r)
        if csig and csig[0] and csig[1] and csig[2] and csig[3]:
            ckey = (csig[0], csig[1], csig[2], csig[3])
            if ckey not in coord_groups:
                coord_groups[ckey] = []
            coord_groups[ckey].append(r)

    coord_dup_groups = []
    for ckey, r_list in coord_groups.items():
        distinct_r_list = _filter_distinct_sf_fid_rows(r_list)
        if len(distinct_r_list) > 1:
            active_statuses = {row_coord_sigs[r][4] for r in distinct_r_list if row_coord_sigs[r][4]}
            if len(active_statuses) <= 1:
                coord_dup_groups.append(distinct_r_list)

    # Check B: Group by all compared survey columns
    attr_groups: Dict[Tuple, List[int]] = {}
    for r in rows_to_process:
        asig = row_attr_sigs.get(r)
        if asig:
            if asig not in attr_groups:
                attr_groups[asig] = []
            attr_groups[asig].append(r)
    attr_dup_groups = []
    for r_list in attr_groups.values():
        distinct_r_list = _filter_distinct_sf_fid_rows(r_list)
        if len(distinct_r_list) > 1:
            attr_dup_groups.append(distinct_r_list)

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
        dup_type_desc = "duplicate features with same location and same IDs"
    elif attr_dup_groups and not coord_dup_groups:
        dup_type_desc = "same values in all checked columns"
    else:
        dup_type_desc = "same location and same values"

    if not dup_groups:
        diff_cols = []
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

        cols_checked_str = (
            '"map_uuid",\n    "bsn_geoid",\n    "geocode",\n    "ea_geocode",\n    '
            '"region_code",\n    "province_code",\n    "city_mun_code",\n    "barangay_code",\n    '
            '"ean",\n    "bsn",\n    "status",\n    "longitude",\n    "longitud",\n    '
            '"latitude",\n    "latitud"'
        )

        msg = (
            f"No duplicate records found (these columns will be checked to consider them duplicates:\n    {cols_checked_str})\n\n"
            f"The selected records have different values in:\n{diff_details}\n\n"
            "Records with different values will not be deleted."
        ) if diff_cols else (
            f"No duplicate features (these columns will be checked to consider them duplicates:\n    {cols_checked_str})"
        )

        if QMessageBox:
            QMessageBox.warning(dialog, "No Duplicates Found", msg)
        if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
            dialog.lbl_footer_status.setText("No duplicates found. Nothing was deleted.")
        return {"success": False, "fixed_count": 0, "message": msg}

    total_to_delete = sum(len(r_list) - 1 for r_list in dup_groups)
    retained_count = len(dup_groups)
    non_duplicate_rows = [r for r in rows_to_process if r not in grouped_rows]
    non_dup_count = len(non_duplicate_rows)

    if prompt_confirm and QMessageBox:
        non_dup_details = ""
        if non_dup_count > 0:
            non_dup_labels = []
            non_dup_rows_preview = non_duplicate_rows[:5]
            for r in non_dup_rows_preview:
                item0 = table.item(r, 0)
                fid_val = None
                if item0:
                    fid_val = item0.data(Qt.UserRole + 6) or item0.data(Qt.UserRole)
                fid_str = f"#{fid_val}" if fid_val is not None else f"Row {r + 1}"
                non_dup_labels.append(fid_str)
            extra_non_dup = f", and {non_dup_count - 5} more" if non_dup_count > 5 else ""
            non_dup_details = (
                f"\n• Not duplicated (left unchanged): {non_dup_count} record(s) "
                f"({', '.join(non_dup_labels)}{extra_non_dup})\n"
                f"  (These records have different map_uuid or coordinates/attributes from the other records.)\n"
            )

        reply = QMessageBox.question(
            dialog,
            "Remove Duplicates",
            f"Found {len(dup_groups)} set(s) of duplicate records ({dup_type_desc}).\n\n"
            f"• Keep: {retained_count} record(s)\n"
            f"• Mark as deleted: {total_to_delete} duplicate record(s)"
            f"{non_dup_details}\n"
            f"Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return {"success": False, "fixed_count": 0, "message": "Cancelled."}

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

    ref_points = _load_ref_bldg_points(dialog, **kwargs)
    deleted_count = 0
    updated_values = {}

    for r_list in dup_groups:
        # Sort duplicate rows by:
        # 1. Match in Reference Points (*_bldg_point in .gpkg) on map_uuid + coordinates (5 digits after dot)
        # 2. Feature completeness in the other columns of the active layer (.geojson)
        # 3. Total filled columns & row index tie-breaker
        def _row_completeness_key(r_idx: int) -> Tuple[int, int, int, int]:
            it0 = table.item(r_idx, 0)
            s_f = it0.data(Qt.UserRole) if it0 else None
            e_f = it0.data(Qt.UserRole + 3) if it0 else None
            sf_f = it0.data(Qt.UserRole + 6) if it0 else None
            m_feat = _resolve_feature_by_fid(main_layer, [sf_f, s_f]) if main_layer else None
            l_feat = _resolve_feature_by_fid(layer, [e_f, s_f, sf_f]) if layer else None
            csig = row_coord_sigs.get(r_idx, ("", "", "", "", ""))
            ref_match = _matches_reference_bldg_point(csig[0], csig[2], csig[3], ref_points)
            return _compute_feature_completeness_score(
                main_feat=m_feat,
                layer_feat=l_feat,
                table=table,
                row_idx=r_idx,
                tie_breaker=r_idx,
                ref_match=ref_match,
            )

        sorted_r_list = sorted(r_list, key=_row_completeness_key, reverse=True)
        retained_sf_fid = _get_row_distinct_sf_fid(sorted_r_list[0])
        # Retain sorted_r_list[0] and mark sorted_r_list[1:] as deleted
        for r in sorted_r_list[1:]:
            if _get_row_distinct_sf_fid(r) == retained_sf_fid:
                continue
            item0 = table.item(r, 0)
            if not item0:
                continue
            s_fid = item0.data(Qt.UserRole)
            u_str = item0.data(Qt.UserRole + 1)
            e_fid = item0.data(Qt.UserRole + 3)

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
            ukey = make_unique_feature_key(s_fid, u_str)
            if ukey:
                updated_values[ukey] = {"sf_status": "deleted"}
                updated_values[ukey.lower()] = {"sf_status": "deleted"}

    if combo_actions:
        combo_actions.setItemText(0, "Actions")
    elif btn_actions:
        btn_actions.setText("Actions ▾")
    if btn_update_selected:
        btn_update_selected.setText("Apply Fix Action")
        btn_update_selected.setEnabled(False)

    if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
        dialog.lbl_footer_status.setText(
            f"Removed duplicates: kept {retained_count} record(s), "
            f"marked {deleted_count} as deleted. Click 'Save Changes' (Ctrl+S) to keep them."
        )
    if hasattr(dialog, "iface") and dialog.iface and dialog.iface.mapCanvas():
        dialog.iface.mapCanvas().refresh()

    return {
        "success": True,
        "fixed_count": deleted_count,
        "updated_values": updated_values,
        "message": (
            f"Removed duplicates: kept {retained_count} record(s) "
            f"and marked {deleted_count} duplicate(s) as deleted."
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

    flattened_targets = _flatten_ids(target_fids or []) | _flatten_ids(target_uuids or [])
    features_to_check = []
    for feat in active_layer.getFeatures():
        if _is_feature_already_deleted(feat):
            continue
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
            and (f.name().lower()[3:] if f.name().lower().startswith(("sf_", "df_")) else f.name().lower())
            not in ("pos_longitude", "pos_latitude", "pos_longit", "pos_latitu")
        ]

    # Check A: Coordinate duplicate check
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
    if not main_layer.isEditable():
        main_layer.startEditing()

    if status_field_name is None:
        try:
            new_fld = QgsField("status", QVariant.String)
            if hasattr(main_layer, "addAttribute") and main_layer.isEditable() and getattr(main_layer, "providerType", lambda: "memory")() != "memory":
                main_layer.addAttribute(new_fld)
            else:
                main_layer.dataProvider().addAttributes([new_fld])
                main_layer.updateFields()
            status_field_name = "status"
        except Exception:
            status_field_name = "status"

    status_idx = main_layer.fields().indexOf(status_field_name)

    ref_points = _load_ref_bldg_points(dialog, **kwargs)
    updated_values = {}
    deleted_count = 0

    for feat_list in dup_groups:
        def _feat_completeness_key(f_obj: QgsFeature) -> Tuple[int, int, int, int]:
            f_id = f_obj.id()
            m_feat = None
            if active_layer == main_layer:
                m_feat = f_obj
            else:
                f_cands = [f_id]
                for fid_col in ("sf_fid", "df_fid", "source_fid", "fid"):
                    try:
                        if fid_col in [fld.name() for fld in active_layer.fields()]:
                            f_cands.insert(0, f_obj[fid_col])
                    except Exception:
                        pass
                m_feat = _resolve_feature_by_fid(main_layer, f_cands)
            f_uuid, _ = _extract_feature_id_sig(m_feat or f_obj)
            f_lon, f_lat = _extract_feature_coord_sig(m_feat or f_obj, precision=7)
            ref_match = _matches_reference_bldg_point(f_uuid, f_lon, f_lat, ref_points)
            return _compute_feature_completeness_score(
                main_feat=m_feat,
                layer_feat=f_obj,
                tie_breaker=f_id if isinstance(f_id, int) else 0,
                ref_match=ref_match,
            )

        sorted_feat_list = sorted(feat_list, key=_feat_completeness_key, reverse=True)
        # Retain sorted_feat_list[0] (Reference Point match + most complete feature) and mark sorted_feat_list[1:] as deleted
        for dup_feat in sorted_feat_list[1:]:
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
                ukey = make_unique_feature_key(dup_id, dup_uuid)
                if ukey:
                    updated_values[ukey] = {status_field_name: "deleted"}
                    updated_values[ukey.lower()] = {status_field_name: "deleted"}

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


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute automated fix for mv_2027_hp_4a_longitude__duplicate."""
    return _run_fix_longitude_duplicate(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        **kwargs,
    )
