# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Concatenate BSN GEOID Process
Action: "Concatenate the bsn_geoid"
Validation IDs: mv_2027_hp_4b_bsn_geoid__invalid, mv_2027_hp_4b_bsn_geoid__missing

Computes missing or invalid BSN GEOID following a 2-scenario fallback cascade:
  1st Scenario:
    - Priority 1: sf_ea_geocode + sf_bsn
    - Priority 2: ea_geocode + bsn
  2nd Scenario:
    - Priority 3: sf_province_code + sf_city_mun_code + sf_barangay_code + sf_ean + sf_bsn
    - Priority 4: province_code + city_mun_code + barangay_code + ean + bsn
  Resilient Fallback:
    - Synthesized EA geocode + available BSN.
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
    from .concatenate_ea_geocode_fix import compute_ea_geocode_field_calculator
except ImportError:
    from common import _flatten_ids, _get_val, is_valid_qobject, make_unique_feature_key
    from concatenate_ea_geocode_fix import compute_ea_geocode_field_calculator

FIX_ID = "mv_2027_hp_4b_bsn_geoid__invalid"
FIX_NAME = "Concatenate and paste BSN GEOID"
FIX_DESCRIPTION = (
    "Calculates and assigns 'sf_bsn_geoid' using a 2-scenario fallback cascade: "
    "1) ea_geocode + bsn (sf_* or standard), 2) province_code + city_mun_code + barangay_code + ean + bsn."
)


def _format_bsn_code(bsn_val: Any) -> Optional[str]:
    """Safely formats and zero-pads BSN code to standard 5 digits if needed."""
    if bsn_val is None or bsn_val == NULL:
        return None
    s = str(bsn_val).strip()
    if not s or s.upper() in ("", "NULL", "NONE", "NAN") or s.startswith(("<", "Mock")):
        return None
    if s.isdigit() and len(s) < 5:
        return s.zfill(5)
    return s


def compute_bsn_geoid_field_calculator(
    feature: QgsFeature,
    layer: Optional[QgsVectorLayer] = None,
) -> str:
    """
    Computes BSN geoid following a 2-scenario fallback cascade:
      1st Scenario:
        - Priority 1: sf_ea_geocode + sf_bsn
        - Priority 2: ea_geocode + bsn
      2nd Scenario:
        - Priority 3: sf_province_code + sf_city_mun_code + sf_barangay_code + sf_ean + sf_bsn
        - Priority 4: province_code + city_mun_code + barangay_code + ean + bsn
      Resilient Fallback:
        - Synthesized EA geocode + available BSN.
    """
    # 1. Try QGIS Expression Engine
    exp_str = (
        'coalesce('
        # 1st Scenario (Priority 1): sf_ea_geocode + sf_bsn
        'if("sf_ea_geocode" IS NOT NULL AND upper(trim(to_string("sf_ea_geocode"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_bsn" IS NOT NULL AND upper(trim(to_string("sf_bsn"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'concat(to_string("sf_ea_geocode"), '
        'if(length(to_string("sf_bsn")) < 5, lpad(to_string("sf_bsn"), 5, \'0\'), to_string("sf_bsn"))), NULL), '
        # 1st Scenario (Priority 2): ea_geocode + bsn
        'if("ea_geocode" IS NOT NULL AND upper(trim(to_string("ea_geocode"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"bsn" IS NOT NULL AND upper(trim(to_string("bsn"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'concat(to_string("ea_geocode"), '
        'if(length(to_string("bsn")) < 5, lpad(to_string("bsn"), 5, \'0\'), to_string("bsn"))), NULL), '
        # 2nd Scenario (Priority 3): sf_province_code + sf_city_mun_code + sf_barangay_code + sf_ean + sf_bsn
        'if("sf_province_code" IS NOT NULL AND upper(trim(to_string("sf_province_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_city_mun_code" IS NOT NULL AND upper(trim(to_string("sf_city_mun_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_barangay_code" IS NOT NULL AND upper(trim(to_string("sf_barangay_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_ean" IS NOT NULL AND upper(trim(to_string("sf_ean"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"sf_bsn" IS NOT NULL AND upper(trim(to_string("sf_bsn"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'concat(to_string("sf_province_code"), to_string("sf_city_mun_code"), '
        'to_string("sf_barangay_code"), to_string("sf_ean"), '
        'if(length(to_string("sf_bsn")) < 5, lpad(to_string("sf_bsn"), 5, \'0\'), to_string("sf_bsn"))), NULL), '
        # 2nd Scenario (Priority 4): province_code + city_mun_code + barangay_code + ean + bsn
        'if("province_code" IS NOT NULL AND upper(trim(to_string("province_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"city_mun_code" IS NOT NULL AND upper(trim(to_string("city_mun_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"barangay_code" IS NOT NULL AND upper(trim(to_string("barangay_code"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"ean" IS NOT NULL AND upper(trim(to_string("ean"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\') AND '
        '"bsn" IS NOT NULL AND upper(trim(to_string("bsn"))) NOT IN (\'\', \'NULL\', \'NONE\', \'NAN\'), '
        'concat(to_string("province_code"), to_string("city_mun_code"), '
        'to_string("barangay_code"), to_string("ean"), '
        'if(length(to_string("bsn")) < 5, lpad(to_string("bsn"), 5, \'0\'), to_string("bsn"))), NULL), '
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

    # 2. Resilient Python Fallback Engine
    # 1st Scenario - Priority 1: sf_ea_geocode + sf_bsn
    sf_ea = _get_val(feature, "sf_ea_geocode")
    sf_bsn = _format_bsn_code(_get_val(feature, "sf_bsn"))
    if sf_ea is not None and sf_bsn is not None:
        return f"{sf_ea}{sf_bsn}"

    # 1st Scenario - Priority 2: ea_geocode + bsn
    ea = _get_val(feature, "ea_geocode")
    bsn = _format_bsn_code(_get_val(feature, "bsn"))
    if ea is not None and bsn is not None:
        return f"{ea}{bsn}"

    # 2nd Scenario - Priority 3: sf_province_code, sf_city_mun_code, sf_barangay_code, sf_ean, sf_bsn
    p1, m1, b1, e1 = (
        _get_val(feature, "sf_province_code"),
        _get_val(feature, "sf_city_mun_code"),
        _get_val(feature, "sf_barangay_code"),
        _get_val(feature, "sf_ean"),
    )
    if p1 is not None and m1 is not None and b1 is not None and e1 is not None and sf_bsn is not None:
        return f"{p1}{m1}{b1}{e1}{sf_bsn}"

    # 2nd Scenario - Priority 4: province_code, city_mun_code, barangay_code, ean, bsn
    p2, m2, b2, e2 = (
        _get_val(feature, "province_code"),
        _get_val(feature, "city_mun_code"),
        _get_val(feature, "barangay_code"),
        _get_val(feature, "ean"),
    )
    if p2 is not None and m2 is not None and b2 is not None and e2 is not None and bsn is not None:
        return f"{p2}{m2}{b2}{e2}{bsn}"

    # Resilient fallback across mixed/joined columns
    best_ea = sf_ea or ea
    if not best_ea:
        for fn in ("df_ea_geocode", "geocode"):
            v = _get_val(feature, fn)
            if v:
                best_ea = v
                break
    if not best_ea:
        best_ea = compute_ea_geocode_field_calculator(feature, layer)

    best_bsn = sf_bsn or bsn
    if not best_bsn:
        for fn in ("df_bsn", "bsn_num", "bldg_sn"):
            v = _format_bsn_code(_get_val(feature, fn))
            if v:
                best_bsn = v
                break

    if best_ea and best_bsn:
        return f"{best_ea}{best_bsn}"

    return ""


def _compute_bsn_geoid_from_dict(attrs: Dict[str, Any]) -> str:
    """Compute BSN geoid from dictionary of attributes (case-insensitive keys)."""
    if not attrs:
        return ""
    a_lower = {str(k).strip().lower(): str(v).strip() for k, v in attrs.items() if v is not None and v != NULL}

    # Priority 1: sf_ea_geocode + sf_bsn
    sf_ea = a_lower.get("sf_ea_geocode")
    sf_bsn = _format_bsn_code(a_lower.get("sf_bsn"))
    if sf_ea and sf_bsn and sf_ea.lower() not in ("null", "none"):
        return f"{sf_ea}{sf_bsn}"

    # Priority 2: ea_geocode + bsn
    ea = a_lower.get("ea_geocode")
    bsn = _format_bsn_code(a_lower.get("bsn"))
    if ea and bsn and ea.lower() not in ("null", "none"):
        return f"{ea}{bsn}"

    # Priority 3: sf_province_code + sf_city_mun_code + sf_barangay_code + sf_ean + sf_bsn
    p1 = a_lower.get("sf_province_code")
    m1 = a_lower.get("sf_city_mun_code")
    b1 = a_lower.get("sf_barangay_code")
    e1 = a_lower.get("sf_ean")
    if p1 and m1 and b1 and e1 and sf_bsn:
        return f"{p1}{m1}{b1}{e1}{sf_bsn}"

    # Priority 4: province_code + city_mun_code + barangay_code + ean + bsn
    p2 = a_lower.get("province_code")
    m2 = a_lower.get("city_mun_code")
    b2 = a_lower.get("barangay_code")
    e2 = a_lower.get("ean")
    if p2 and m2 and b2 and e2 and bsn:
        return f"{p2}{m2}{b2}{e2}{bsn}"

    # Resilient fallback across mixed keys
    best_ea = sf_ea or ea or a_lower.get("df_ea_geocode") or a_lower.get("geocode")
    best_bsn = sf_bsn or bsn or _format_bsn_code(a_lower.get("df_bsn")) or _format_bsn_code(a_lower.get("bsn_num")) or _format_bsn_code(a_lower.get("bldg_sn"))
    if best_ea and best_bsn:
        return f"{best_ea}{best_bsn}"

    return ""


def _run_fix_bsn_geoid(
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
    Execute automated fix: computes BSN geoid using the 2-scenario logic
    and assigns it strictly to the targeted/selected records.
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

    field_names = active_layer.fields().names() if hasattr(active_layer.fields(), "names") else []
    target_fields = [f for f in ("sf_bsn_geoid", "bsn_geoid") if f in field_names]

    if not target_fields:
        if not active_layer.isEditable():
            active_layer.startEditing()
        active_layer.dataProvider().addAttributes([QgsField("sf_bsn_geoid", QVariant.String, len=30)])
        active_layer.updateFields()
        target_fields.append("sf_bsn_geoid")

    if not active_layer.isEditable() and not active_layer.startEditing():
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "The Building Points file could not be opened for editing.",
        }

    if error_layer and error_layer.isValid() and error_layer != active_layer:
        if not error_layer.isEditable():
            try:
                error_layer.startEditing()
            except Exception:
                pass

    updated_values: Dict[Any, Dict[str, str]] = {}
    fixed_count = 0

    # Branch A: Process by selected table rows (UI selection scope)
    if rows_to_process and table is not None and is_valid_qobject(table):
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
            row_uuid = sf_u or u_str or df_u
            row_ukey = make_unique_feature_key(row_main_fid or df_f or e_fid, row_uuid)

            # Table row attributes dictionary
            row_attrs = {}
            for c in range(table.columnCount()):
                h_item = table.horizontalHeaderItem(c)
                col_name = h_item.text().strip() if h_item else ""
                it = table.item(r, c)
                if it and col_name:
                    row_attrs[col_name] = it.text().strip()

            # Locate feature in active_layer (main building layer)
            feat = None
            if active_layer and active_layer.isValid():
                if row_main_fid is not None:
                    try:
                        feat = active_layer.getFeature(row_main_fid)
                    except Exception:
                        feat = None
                if (not feat or not feat.isValid()) and row_uuid:
                    for f in active_layer.getFeatures():
                        u_cand = ""
                        for col in ("sf_map_uuid", "map_uuid", "uuid"):
                            if col in field_names:
                                v = f.attribute(col)
                                if v and str(v).strip().lower() not in ("", "null", "none"):
                                    u_cand = str(v).strip()
                                    break
                        if u_cand and u_cand.lower() == row_uuid.lower():
                            feat = f
                            break

            # Locate feature in error_layer
            ef = None
            if error_layer and error_layer.isValid():
                if e_fid is not None:
                    try:
                        ef = error_layer.getFeature(e_fid)
                    except Exception:
                        ef = None
                if (not ef or not ef.isValid()) and row_uuid:
                    for f in error_layer.getFeatures():
                        u_cand = ""
                        for col in ("sf_map_uuid", "map_uuid", "uuid"):
                            if col in error_layer.fields().names():
                                v = f.attribute(col)
                                if v and str(v).strip().lower() not in ("", "null", "none"):
                                    u_cand = str(v).strip()
                                    break
                        if u_cand and u_cand.lower() == row_uuid.lower():
                            ef = f
                            break

            target_feat = feat if (feat and feat.isValid()) else (ef if (ef and ef.isValid()) else None)
            concat_bsn_geoid = ""
            if target_feat:
                concat_bsn_geoid = compute_bsn_geoid_field_calculator(target_feat, active_layer if feat else error_layer)
            if not concat_bsn_geoid and row_attrs:
                concat_bsn_geoid = _compute_bsn_geoid_from_dict(row_attrs)
            if not concat_bsn_geoid and ef and ef.isValid():
                concat_bsn_geoid = compute_bsn_geoid_field_calculator(ef, error_layer)

            if not concat_bsn_geoid:
                continue

            # Update active_layer feature strictly
            if feat and feat.isValid():
                for tf_name in target_fields:
                    idx = active_layer.fields().indexOf(tf_name)
                    if idx != -1:
                        active_layer.changeAttributeValue(feat.id(), idx, concat_bsn_geoid)

            # Update error_layer feature strictly
            if error_layer and error_layer.isValid() and ef and ef.isValid() and error_layer != active_layer:
                err_target_fields = [f for f in ("sf_bsn_geoid", "bsn_geoid") if f in error_layer.fields().names()]
                for tf_name in err_target_fields:
                    idx = error_layer.fields().indexOf(tf_name)
                    if idx != -1:
                        error_layer.changeAttributeValue(ef.id(), idx, concat_bsn_geoid)

            payload = {"sf_bsn_geoid": concat_bsn_geoid, "bsn_geoid": concat_bsn_geoid, "df_bsn_geoid": concat_bsn_geoid}
            updated_values[f"row_{r}"] = payload
            if row_ukey:
                updated_values[row_ukey] = payload
                updated_values[row_ukey.lower()] = payload
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

        err_feats_lookup = {}
        if error_layer and error_layer.isValid() and error_layer != active_layer:
            for ef in error_layer.getFeatures():
                ef_ids = _flatten_ids(ef.id())
                ef_uuid = ""
                for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
                    if col in error_layer.fields().names():
                        try:
                            val = ef.attribute(col)
                            if val is not None and val != NULL:
                                ef_ids.update(_flatten_ids(val))
                                if not ef_uuid and col in ("sf_map_uuid", "map_uuid", "uuid"):
                                    ef_uuid = str(val).strip()
                        except Exception:
                            pass
                for eid in ef_ids:
                    err_feats_lookup[eid] = ef
                    uk = make_unique_feature_key(eid, ef_uuid)
                    if uk:
                        err_feats_lookup[uk] = ef
                        err_feats_lookup[uk.lower()] = ef

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
                matched = (
                    bool(feat_ids & clean_target_fids)
                    or (bool(feat_uuid) and feat_uuid.lower() in clean_target_uuids)
                    or bool(cand_keys & target_keys_set)
                    or bool(cand_keys_lower & target_keys_lower)
                )
                if not matched:
                    continue

            concat_bsn_geoid = compute_bsn_geoid_field_calculator(feat, active_layer)
            if not concat_bsn_geoid:
                for kid in list(feat_ids) + list(cand_keys):
                    if kid in err_feats_lookup:
                        concat_bsn_geoid = compute_bsn_geoid_field_calculator(err_feats_lookup[kid], error_layer)
                        if concat_bsn_geoid:
                            break

            if not concat_bsn_geoid:
                continue

            for tf_name in target_fields:
                idx = active_layer.fields().indexOf(tf_name)
                if idx != -1:
                    active_layer.changeAttributeValue(f_id, idx, concat_bsn_geoid)

            payload = {"sf_bsn_geoid": concat_bsn_geoid, "bsn_geoid": concat_bsn_geoid, "df_bsn_geoid": concat_bsn_geoid}
            for k in feat_ids:
                updated_values[k] = payload
            for ck in cand_keys:
                updated_values[ck] = payload
                updated_values[ck.lower()] = payload

            fixed_count += 1

        if error_layer and error_layer.isValid() and error_layer != active_layer:
            err_field_names = error_layer.fields().names() if hasattr(error_layer.fields(), "names") else []
            err_target_fields = [f for f in ("sf_bsn_geoid", "bsn_geoid") if f in err_field_names]
            if err_target_fields:
                for ef in error_layer.getFeatures():
                    ef_ids = _flatten_ids(ef.id())
                    ef_uuid = ""
                    for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
                        if col in err_field_names:
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
                    cand_ef_keys_lower = {k.lower() for k in cand_ef_keys}

                    if is_targeted:
                        matched_ef = (
                            bool(ef_ids & clean_target_fids)
                            or (bool(ef_uuid) and ef_uuid.lower() in clean_target_uuids)
                            or bool(cand_ef_keys & target_keys_set)
                            or bool(cand_ef_keys_lower & target_keys_lower)
                        )
                        if not matched_ef:
                            continue

                    matched_cand = None
                    for k in list(ef_ids) + list(cand_ef_keys) + [k.lower() for k in cand_ef_keys]:
                        if k in updated_values:
                            matched_cand = k
                            break
                    if matched_cand:
                        new_val = updated_values[matched_cand]["sf_bsn_geoid"]
                        for tf_name in err_target_fields:
                            idx = error_layer.fields().indexOf(tf_name)
                            if idx != -1:
                                error_layer.changeAttributeValue(ef.id(), idx, new_val)

    if feedback:
        feedback.pushInfo(f"Calculated and assigned BSN GEOID for {fixed_count} feature(s).")

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Updated BSN GEOID for {fixed_count} record(s).",
    }


def concatenate_bsn_geoid(
    dialog: Any,
    *args,
    **kwargs,
) -> None:
    """
    Process handler for concatenating BSN GEOID on checked table rows.
    Processes the action directly regardless of validation check or file.
    """
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    target_rule = "concatenate_bsn_geoid"
    if hasattr(dialog, "_fix_selected_features"):
        dialog._fix_selected_features(target_rule, layer, table)
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
    """Execute automated fix for mv_2027_hp_4b_bsn_geoid__invalid and mv_2027_hp_4b_bsn_geoid__missing."""
    return _run_fix_bsn_geoid(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        target_keys=target_keys,
        **kwargs,
    )

