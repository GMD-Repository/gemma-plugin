# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Concatenate EA Geocode Process
Action: "Concatenate the ea_geocode"
Validation ID: mv_2027_hp_4b_ea_geocode__missing

Computes missing EA geocode following a 4-step prioritized fallback cascade:
  1) Direct sf_* columns (sf_province_code, sf_city_mun_code, sf_barangay_code, sf_ean)
  2) Direct standard boundary columns (province_code, city_mun_code, barangay_code, ean)
  3) sf_bsn_geoid (first 14 chars)
  4) bsn_geoid (first 14 chars)
"""
from typing import Any, Dict, List, Optional

from qgis.core import (
    NULL,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsField,
    QgsProcessingFeedback,
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
    from .common import _flatten_ids, _get_val, is_valid_qobject, make_unique_feature_key
except ImportError:
    from common import _flatten_ids, _get_val, is_valid_qobject, make_unique_feature_key

FIX_ID = "mv_2027_hp_4b_ea_geocode__missing"
FIX_NAME = "Concatenate and paste EA geocode"
FIX_DESCRIPTION = (
    "Calculates and assigns 'sf_ea_geocode' using 4 prioritized fallback steps: "
    "1) Direct concatenation of sf_* columns, 2) Direct concatenation of standard boundary columns, "
    "3) sf_bsn_geoid (first 14 chars), 4) bsn_geoid (first 14 chars)."
)


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


def _inspect_missing_ea_geocode_columns(
    feat: Optional[QgsFeature] = None,
    row_attrs: Optional[Dict[str, Any]] = None,
    ef: Optional[QgsFeature] = None,
) -> List[str]:
    """Return the list of required columns that are NULL/empty when EA Geocode concatenation produces NULL."""
    a_lower: Dict[str, str] = {}
    if row_attrs:
        for k, v in row_attrs.items():
            if v is not None and v != NULL:
                s = str(v).strip()
                if s and s.upper() not in ("", "NULL", "NONE", "NAN"):
                    a_lower[str(k).strip().lower()] = s

    def _has_any(*col_names: str) -> bool:
        for cn in col_names:
            if feat is not None and _get_val(feat, cn) is not None:
                return True
            if ef is not None and _get_val(ef, cn) is not None:
                return True
            if cn.lower() in a_lower:
                return True
        return False

    missing_cols: List[str] = []
    if not _has_any("sf_province_code", "province_code", "df_province_code"):
        missing_cols.append("sf_province_code / province_code")
    if not _has_any("sf_city_mun_code", "city_mun_code", "df_city_mun_code"):
        missing_cols.append("sf_city_mun_code / city_mun_code")
    if not _has_any("sf_barangay_code", "barangay_code", "df_barangay_code"):
        missing_cols.append("sf_barangay_code / barangay_code")
    if not _has_any("sf_ean", "ean", "df_ean"):
        missing_cols.append("sf_ean / ean")
    if not _has_any("sf_bsn_geoid", "bsn_geoid", "df_bsn_geoid"):
        missing_cols.append("sf_bsn_geoid / bsn_geoid")
    return missing_cols


def _build_null_ea_geocode_message(
    null_records: List[Dict[str, Any]],
    selected_count: int = 0,
) -> str:
    """Build a detailed user-facing prompt indicating that all required columns need to be checked when EA Geocode remains NULL."""
    count = len(null_records) or selected_count
    count_str = f"{count} selected record(s)" if count > 0 else "all selected record(s)"
    header = (
        f"The concatenated EA GEOCODE is still NULL for {count_str}.\n"
        "All required columns need to be checked because one or more values are missing or NULL.\n\n"
    )
    row_lines: List[str] = []
    for item in null_records[:5]:
        label = item.get("label", "Record")
        missing = item.get("missing_cols") or []
        if missing:
            row_lines.append(f"  • {label}: check {', '.join(missing)}")
        else:
            row_lines.append(f"  • {label}: all required columns need to be checked")
    if len(null_records) > 5:
        row_lines.append(f"  • ...and {len(null_records) - 5} more record(s).")

    rows_section = ("Affected Record(s):\n" + "\n".join(row_lines) + "\n\n") if row_lines else ""

    columns_guide = (
        "All columns that need to be checked:\n\n"
        "1st Scenario (Geographic Codes):\n"
        "  • sf_province_code (or province_code)\n"
        "  • sf_city_mun_code (or city_mun_code)\n"
        "  • sf_barangay_code (or barangay_code)\n"
        "  • sf_ean (or ean)\n\n"
        "2nd Scenario (BSN GEOID — first 14 chars):\n"
        "  • sf_bsn_geoid (or bsn_geoid)"
    )
    return f"{header}{rows_section}{columns_guide}"


def _run_fix_ea_geocode(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    target_keys: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute automated fix: computes EA geocode using the 4-step priority logic
    and assigns it to building points layer.
    """
    error_layer = kwargs.get("error_layer")
    target_err_fids = kwargs.get("target_err_fids")
    target_err_set = _flatten_ids(target_err_fids) if target_err_fids is not None else set()

    active_layer = main_layer if (main_layer and main_layer.isValid()) else error_layer
    if not active_layer or not active_layer.isValid():
        return {"success": False, "message": "The Building Points file is missing or could not be opened.", "fixed_count": 0, "updated_values": {}}

    target_keys_set = set(target_keys) if target_keys else set()
    target_keys_lower = {str(k).strip().lower() for k in target_keys_set if k}
    is_targeted = (
        (target_fids is not None)
        or (target_uuids is not None)
        or bool(target_keys_set)
        or (target_err_fids is not None)
    )
    target_set = _flatten_ids(target_fids) | _flatten_ids(target_uuids)

    if is_targeted and not target_set and not target_keys_set and not target_err_set:
        return {"success": True, "fixed_count": 0, "updated_values": {}, "message": "No valid target ID or UUID provided."}

    field_names = active_layer.fields().names() if hasattr(active_layer.fields(), "names") else []
    target_fields = [f for f in ("sf_ea_geocode", "ea_geocode", "geocode") if f in field_names]

    if not target_fields:
        if not active_layer.isEditable():
            active_layer.startEditing()
        new_fld = QgsField("ea_geocode", QVariant.String, len=30)
        if hasattr(active_layer, "addAttribute") and active_layer.isEditable() and getattr(active_layer, "providerType", lambda: "memory")() != "memory":
            active_layer.addAttribute(new_fld)
        else:
            active_layer.dataProvider().addAttributes([new_fld])
            active_layer.updateFields()
        target_fields.append("ea_geocode")
        field_names = active_layer.fields().names() if hasattr(active_layer.fields(), "names") else []

    if not active_layer.isEditable() and not active_layer.startEditing():
        return {"success": False, "fixed_count": 0, "updated_values": {}, "message": "The Building Points file could not be opened for editing."}

    if error_layer and error_layer.isValid() and error_layer != active_layer:
        if not error_layer.isEditable():
            try:
                error_layer.startEditing()
            except Exception:
                pass

    is_error_active = (error_layer is not None and active_layer == error_layer)
    updated_values: Dict[Any, Dict[str, str]] = {}
    fixed_count = 0
    null_records: List[Dict[str, Any]] = []
    table = kwargs.get("table")
    dialog = kwargs.get("dialog")
    target_rows = kwargs.get("target_rows")

    # Pre-index table row labels and row attributes so Affected Record(s) matches Row #N (FID: ...)
    row_info_by_key: Dict[str, Dict[str, Any]] = {}
    row_info_by_fid: Dict[str, Dict[str, Any]] = {}
    if table is not None and is_valid_qobject(table) and Qt is not None:
        rows_iter = list(target_rows) if target_rows else list(range(table.rowCount()))
        for r in rows_iter:
            if r < 0 or r >= table.rowCount():
                continue
            item0 = table.item(r, 0)
            s_fid = item0.data(Qt.UserRole) if item0 else None
            u_str = str(item0.data(Qt.UserRole + 1) or "").strip() if item0 else ""
            e_fid = item0.data(Qt.UserRole + 3) if item0 else None
            df_f = item0.data(Qt.UserRole + 4) if item0 else None
            df_u = str(item0.data(Qt.UserRole + 5) or "").strip() if item0 else ""
            sf_f = item0.data(Qt.UserRole + 6) if item0 else None
            sf_u = str(item0.data(Qt.UserRole + 7) or "").strip() if item0 else ""
            row_uuid = sf_u or u_str or df_u
            key_fid = (
                sf_f
                if (sf_f is not None and str(sf_f).strip() not in ("", "NULL", "None"))
                else (
                    s_fid
                    if (s_fid is not None and str(s_fid).strip() not in ("", "NULL", "None"))
                    else (df_f if (df_f is not None and str(df_f).strip() not in ("", "NULL", "None")) else e_fid)
                )
            )
            fid_disp = key_fid if key_fid is not None else (r + 1)
            row_attrs = {}
            for c in range(table.columnCount()):
                h_item = table.horizontalHeaderItem(c)
                col_name = h_item.text().strip() if h_item else ""
                it = table.item(r, c)
                if it and col_name:
                    row_attrs[col_name] = it.text().strip()
            r_info = {
                "row": r,
                "label": f"Row #{r + 1} (FID: {fid_disp})",
                "row_attrs": row_attrs,
            }
            uk = make_unique_feature_key(key_fid, row_uuid)
            if uk:
                row_info_by_key[uk.lower()] = r_info
            for fc in _flatten_ids(key_fid):
                row_info_by_fid[str(fc)] = r_info

    for feat in active_layer.getFeatures():
        if feedback and feedback.isCanceled():
            break

        f_id = feat.id()
        spatial_ids = _flatten_ids(f_id)
        feat_ids = set(spatial_ids)
        feat_uuid = ""

        if "sf_fid" in field_names:
            try:
                sf_val = feat.attribute("sf_fid")
                if sf_val is not None and sf_val != NULL:
                    if is_error_active:
                        spatial_ids = _flatten_ids(sf_val)
                    else:
                        spatial_ids.update(_flatten_ids(sf_val))
                    feat_ids.update(_flatten_ids(sf_val))
            except Exception:
                pass

        for col in ("sf_map_uuid", "map_uuid", "uuid"):
            if col in field_names:
                try:
                    val = feat.attribute(col)
                    if val is not None and val != NULL:
                        s_val = str(val).strip()
                        if s_val and s_val.lower() not in ("null", "none"):
                            feat_ids.update(_flatten_ids(s_val))
                            if not feat_uuid:
                                feat_uuid = s_val
                except Exception:
                    pass

        if is_error_active or not target_keys_set or (f_id is not None and f_id < 0):
            for col in ("fid", "df_fid"):
                if col in field_names:
                    try:
                        val = feat.attribute(col)
                        if val is not None and val != NULL:
                            feat_ids.update(_flatten_ids(val))
                            if is_error_active or (f_id is not None and f_id < 0):
                                spatial_ids.update(_flatten_ids(val))
                    except Exception:
                        pass

        cand_keys = {make_unique_feature_key(fid_val, feat_uuid) for fid_val in spatial_ids}
        if feat_uuid:
            cand_keys.add(make_unique_feature_key(None, feat_uuid))
        cand_keys.discard("")
        cand_keys_lower = {k.lower() for k in cand_keys}

        if is_targeted:
            if is_error_active and target_err_set:
                matched = bool(_flatten_ids(f_id) & target_err_set)
            elif target_keys_set:
                matched = bool(cand_keys & target_keys_set) or bool(cand_keys_lower & target_keys_lower)
                if not matched and not feat_uuid and target_set:
                    matched = bool(spatial_ids & target_set)
            else:
                matched = bool(target_set and (feat_ids & target_set))
            if not matched:
                continue

        concat_geocode = compute_ea_geocode_field_calculator(feat, active_layer)
        if not concat_geocode:
            matched_r_info = None
            for ck_l in cand_keys_lower:
                if ck_l in row_info_by_key:
                    matched_r_info = row_info_by_key[ck_l]
                    break
            if not matched_r_info:
                for fid_c in spatial_ids:
                    if str(fid_c) in row_info_by_fid:
                        matched_r_info = row_info_by_fid[str(fid_c)]
                        break
            label = matched_r_info["label"] if matched_r_info else f"FID: {f_id}"
            r_attrs = matched_r_info["row_attrs"] if matched_r_info else None
            null_records.append({
                "label": label,
                "missing_cols": _inspect_missing_ea_geocode_columns(feat, r_attrs, None),
            })
            continue

        for tf_name in target_fields:
            idx = active_layer.fields().indexOf(tf_name)
            if idx != -1:
                active_layer.changeAttributeValue(f_id, idx, concat_geocode)

        payload = {"sf_ea_geocode": concat_geocode, "ea_geocode": concat_geocode}
        if is_error_active:
            updated_values[f"err_{f_id}"] = payload
        sf_keys = {make_unique_feature_key(fid_val, feat_uuid) for fid_val in spatial_ids} - {""}
        for uk in sf_keys:
            updated_values[uk] = payload
            updated_values[uk.lower()] = payload
            updated_values[f"sf_{uk}"] = payload
            updated_values[f"sf_{uk.lower()}"] = payload
        if feat_uuid:
            updated_values[f"uuid_{feat_uuid.lower()}"] = payload
        for k in feat_ids:
            updated_values[k] = payload
        for ck in cand_keys:
            updated_values[ck] = payload
            updated_values[ck.lower()] = payload

        fixed_count += 1

    # Also synchronize error_layer if active_layer is main_layer
    if error_layer and error_layer.isValid() and error_layer != active_layer:
        err_fields = error_layer.fields().names() if hasattr(error_layer.fields(), "names") else []
        err_target_fields = [f for f in ("sf_ea_geocode", "ea_geocode", "geocode") if f in err_fields]
        has_err_sf_fid = ("sf_fid" in err_fields or "fid" in err_fields)
        if err_target_fields:
            for ef in error_layer.getFeatures():
                ef_uuid = ""
                for col in ("sf_map_uuid", "map_uuid", "uuid", "df_map_uuid"):
                    if col in err_fields:
                        try:
                            val = ef.attribute(col)
                            if val is not None and val != NULL and str(val).strip():
                                ef_uuid = str(val).strip()
                                break
                        except Exception:
                            pass

                matched_payload = None
                if has_err_sf_fid:
                    sf_col_name = "sf_fid" if "sf_fid" in err_fields else "fid"
                    try:
                        ef_sf_val = ef.attribute(sf_col_name)
                    except Exception:
                        ef_sf_val = None
                    if ef_sf_val is not None and ef_sf_val != NULL:
                        for fid_c in _flatten_ids(ef_sf_val):
                            uk = make_unique_feature_key(fid_c, ef_uuid)
                            if uk and f"sf_{uk}" in updated_values:
                                matched_payload = updated_values[f"sf_{uk}"]
                                break
                            if uk and f"sf_{uk.lower()}" in updated_values:
                                matched_payload = updated_values[f"sf_{uk.lower()}"]
                                break
                elif ef_uuid and f"uuid_{ef_uuid.lower()}" in updated_values:
                    matched_payload = updated_values[f"uuid_{ef_uuid.lower()}"]

                if matched_payload:
                    gc = matched_payload["sf_ea_geocode"]
                    for etf in err_target_fields:
                        idx = error_layer.fields().indexOf(etf)
                        if idx != -1:
                            error_layer.changeAttributeValue(ef.id(), idx, gc)

    if feedback:
        feedback.pushInfo(f"Calculated and assigned EA geocode for {fixed_count} feature(s).")

    # If no active_layer feature matched a selected table row when fixed_count == 0, still populate null_records from the table
    if fixed_count == 0 and not null_records and row_info_by_fid:
        seen_rows = set()
        for r_info in row_info_by_fid.values():
            if r_info["row"] not in seen_rows:
                seen_rows.add(r_info["row"])
                null_records.append({
                    "label": r_info["label"],
                    "missing_cols": _inspect_missing_ea_geocode_columns(None, r_info["row_attrs"], None),
                })

    selected_count = len(target_rows or target_fids or target_uuids or [])
    null_warning_msg = (
        _build_null_ea_geocode_message(null_records, selected_count=selected_count)
        if (null_records or fixed_count == 0)
        else ""
    )
    if fixed_count == 0:
        if dialog is None and QMessageBox is not None and kwargs.get("parent") is not None:
            try:
                QMessageBox.warning(kwargs["parent"], "Check all columns", null_warning_msg)
            except Exception:
                pass
        return {
            "success": True,
            "fixed_count": 0,
            "updated_values": {},
            "title": "Check all columns",
            "null_columns_warning": null_warning_msg,
            "message": null_warning_msg,
        }

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "title": "Check all columns" if null_warning_msg else "Fix Applied",
        "null_columns_warning": null_warning_msg,
        "message": f"Updated EA geocode for {fixed_count} record(s).",
    }


def concatenate_ea_geocode(
    dialog: Any,
    *args,
    **kwargs,
) -> None:
    """
    Process handler for concatenating EA geocode on checked table rows.
    Processes the action directly regardless of validation check or file.
    """
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    action_id = "concatenate_ea_geocode"
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
    """Execute automated fix for mv_2027_hp_4b_ea_geocode__missing."""
    return _run_fix_ea_geocode(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        target_keys=target_keys,
        **kwargs,
    )
