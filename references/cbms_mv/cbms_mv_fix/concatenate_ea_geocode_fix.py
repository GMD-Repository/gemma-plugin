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
    from qgis.PyQt.QtCore import QVariant
except ImportError:
    try:
        from PyQt5.QtCore import QVariant
    except ImportError:
        QVariant = None

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
    active_layer = main_layer if (main_layer and main_layer.isValid()) else error_layer
    if not active_layer or not active_layer.isValid():
        return {"success": False, "message": "Invalid or missing Building Points layer.", "fixed_count": 0, "updated_values": {}}

    target_keys_set = set(target_keys) if target_keys else set()
    target_keys_lower = {str(k).strip().lower() for k in target_keys_set if k}
    is_targeted = (target_fids is not None) or (target_uuids is not None) or bool(target_keys_set)
    target_set = _flatten_ids(target_fids) | _flatten_ids(target_uuids)

    if is_targeted and not target_set and not target_keys_set:
        return {"success": True, "fixed_count": 0, "updated_values": {}, "message": "No valid target ID or UUID provided."}

    field_names = active_layer.fields().names() if hasattr(active_layer.fields(), "names") else []
    target_fields = [f for f in ("sf_ea_geocode", "ea_geocode", "geocode") if f in field_names]

    if not target_fields:
        if not active_layer.isEditable():
            active_layer.startEditing()
        active_layer.dataProvider().addAttributes([QgsField("ea_geocode", QVariant.String, len=30)])
        active_layer.updateFields()
        target_fields.append("ea_geocode")

    if not active_layer.isEditable() and not active_layer.startEditing():
        return {"success": False, "fixed_count": 0, "updated_values": {}, "message": "Failed to start edit session on building points layer."}

    if error_layer and error_layer.isValid() and error_layer != active_layer:
        if not error_layer.isEditable():
            try:
                error_layer.startEditing()
            except Exception:
                pass

    updated_values: Dict[Any, Dict[str, str]] = {}
    fixed_count = 0

    for feat in active_layer.getFeatures():
        if feedback and feedback.isCanceled():
            break

        f_id = feat.id()
        feat_ids = _flatten_ids(f_id)
        feat_uuid = ""
        for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
            if col in field_names:
                try:
                    val = feat.attribute(col)
                    if val is not None and val != NULL:
                        feat_ids.update(_flatten_ids(val))
                        if not feat_uuid and col in ("sf_map_uuid", "map_uuid", "uuid"):
                            feat_uuid = str(val).strip()
                except Exception:
                    pass

        cand_keys = {make_unique_feature_key(fid_val, feat_uuid) for fid_val in feat_ids}
        cand_keys.discard("")
        cand_keys_lower = {k.lower() for k in cand_keys}

        if is_targeted:
            matched = bool(feat_ids & target_set)
            if not matched and target_keys_set:
                matched = bool(cand_keys & target_keys_set) or bool(cand_keys_lower & target_keys_lower)
            if not matched:
                continue

        concat_geocode = compute_ea_geocode_field_calculator(feat, active_layer)
        if not concat_geocode:
            continue

        for tf_name in target_fields:
            idx = active_layer.fields().indexOf(tf_name)
            if idx != -1:
                active_layer.changeAttributeValue(f_id, idx, concat_geocode)

        payload = {"sf_ea_geocode": concat_geocode, "ea_geocode": concat_geocode}
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
        if err_target_fields:
            for ef in error_layer.getFeatures():
                ef_ids = _flatten_ids(ef.id())
                ef_uuid = ""
                for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
                    if col in err_fields:
                        try:
                            val = ef.attribute(col)
                            if val is not None and val != NULL:
                                ef_ids.update(_flatten_ids(val))
                                if not ef_uuid and col in ("sf_map_uuid", "map_uuid", "uuid"):
                                    ef_uuid = str(val).strip()
                        except Exception:
                            pass
                cand_ef_keys = {make_unique_feature_key(fid_val, ef_uuid) for fid_val in ef_ids}
                cand_ef_keys.discard("")
                matched_k = None
                for k in list(ef_ids) + list(cand_ef_keys) + [k.lower() for k in cand_ef_keys]:
                    if k in updated_values:
                        matched_k = k
                        break
                if matched_k:
                    gc = updated_values[matched_k]["sf_ea_geocode"]
                    for etf in err_target_fields:
                        idx = error_layer.fields().indexOf(etf)
                        if idx != -1:
                            error_layer.changeAttributeValue(ef.id(), idx, gc)

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
