# -*- coding: utf-8 -*-
"""
Fix Algorithm for mv_2027_hp_4b_geocode__missing.

Validation Problem:
    Geotagged building points with NULL or invalid ea_geocode (length != 14).

Fix Logic:
    Calculates the 'ea_geocode' attribute by extracting the first 14 characters
    from 'bsn_geoid' using QGIS built-in native:fieldcalculator:
        FORMULA: left("bsn_geoid", 14)

    Identifies features primarily by 'fid' to ensure robustness against
    duplicate or missing map_uuids, with fallback to map_uuid.
"""
try:
    import processing
except ImportError:
    processing = None

from typing import Any, Dict, List, Optional

try:
    from qgis.core import (
        QgsFeatureRequest,
        QgsProcessingFeedback,
        QgsVectorLayer,
        QgsExpression,
        QgsExpressionContext,
        QgsExpressionContextUtils,
    )
except ImportError:
    QgsFeatureRequest = None
    QgsProcessingFeedback = None
    QgsVectorLayer = None
    QgsExpression = None
    QgsExpressionContext = None
    QgsExpressionContextUtils = None

FIX_ID = "mv_2027_hp_4b_geocode__missing"
FIX_NAME = "Calculate ea_geocode from bsn_geoid"
FIX_DESCRIPTION = "Calculates 'ea_geocode' by extracting left(bsn_geoid, 14) using QGIS Field Calculator."


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute automated fix on specified features in main_layer using QGIS built-in tools.
    Prioritizes 'fid' for unambiguous matching against potential duplicate map_uuids.

    Args:
        main_layer: The primary Geotagged Building Points QgsVectorLayer.
        target_fids: List of feature IDs (from GeoJSON fid or feat.id()) to fix.
        target_uuids: Optional list of map_uuid strings (used as fallback).
        feedback: Optional QgsProcessingFeedback for reporting progress.

    Returns:
        Dict containing:
            - success (bool)
            - fixed_count (int)
            - updated_values (dict): {fid: {"ea_geocode": new_value}, map_uuid: ...}
            - message (str)
    """
    if not main_layer or not main_layer.isValid():
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "Main building points layer is invalid or not loaded.",
        }

    # Handle backwards compatibility if target_uuids was passed positionally
    if target_fids is not None and not isinstance(target_fids, list):
        target_fids = [target_fids]
    if target_uuids is not None and not isinstance(target_uuids, list):
        target_uuids = [target_uuids]

    if not target_fids and not target_uuids:
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "No target features specified for fix.",
        }

    ea_idx = main_layer.fields().indexOf("ea_geocode")
    if ea_idx == -1:
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "Attribute field 'ea_geocode' not found in layer.",
        }

    bsn_idx = main_layer.fields().indexOf("bsn_geoid")
    if bsn_idx == -1:
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "Attribute field 'bsn_geoid' not found in layer.",
        }

    # Ensure editing mode is active on main_layer
    if not main_layer.isEditable():
        if not main_layer.startEditing():
            return {
                "success": False,
                "fixed_count": 0,
                "updated_values": {},
                "message": "Failed to start edit session on main building points layer.",
            }

    updated_values: Dict[Any, Dict[str, Any]] = {}
    fixed_count = 0

    has_fid_field = "fid" in [f.name().lower() for f in main_layer.fields()]

    # Build SQL-style filter expression prioritizing fid
    filter_expr = ""
    if target_fids:
        clean_fids = [f for f in target_fids if f is not None]
        if clean_fids:
            if has_fid_field:
                formatted = [
                    str(f) if isinstance(f, int) or (isinstance(f, str) and f.isdigit())
                    else f"'{str(f).replace(chr(39), chr(39)+chr(39))}'"
                    for f in clean_fids
                ]
                filter_expr = f'"fid" IN ({", ".join(formatted)})'
            else:
                formatted_ids = [str(int(f)) for f in clean_fids if str(f).isdigit()]
                if formatted_ids:
                    filter_expr = f'$id IN ({", ".join(formatted_ids)})'

    if not filter_expr and target_uuids:
        escaped_uuids = ", ".join(f"'{str(u).strip().replace(chr(39), chr(39)+chr(39))}'" for u in target_uuids if str(u).strip())
        if escaped_uuids:
            filter_expr = f'"map_uuid" IN ({escaped_uuids})'

    if not filter_expr:
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "Could not construct valid feature query filter.",
        }

    try:
        # Backend 1: QGIS Native Field Calculator on extracted subset
        extracted = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": main_layer,
                "EXPRESSION": filter_expr,
                "OUTPUT": "memory:",
            },
            feedback=feedback,
        )["OUTPUT"]

        calc_layer = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": extracted,
                "FIELD_NAME": "ea_geocode",
                "FIELD_TYPE": 2,  # String
                "FIELD_LENGTH": 14,
                "FORMULA": 'coalesce(left("sf_bsn_geoid", 14), left("bsn_geoid", 14))',
                "OUTPUT": "memory:",
            },
            feedback=feedback,
        )["OUTPUT"]

        # Read calculated values and apply directly to main_layer edit buffer
        calc_fnames = {f.name().lower(): f.name() for f in calc_layer.fields()}
        ea_col = calc_fnames.get("ea_geocode") or calc_fnames.get("sf_ea_geocode")
        fid_col = calc_fnames.get("sf_fid") or calc_fnames.get("fid") or calc_fnames.get("df_fid")
        uuid_col = calc_fnames.get("sf_map_uuid") or calc_fnames.get("map_uuid") or calc_fnames.get("df_map_uuid")

        for feat in calc_layer.getFeatures():
            new_val = feat[ea_col] if ea_col else None
            new_val_str = "" if new_val is None else str(new_val).strip()

            target_fid_val = feat[fid_col] if fid_col and feat[fid_col] is not None else None
            uuid_str = str(feat[uuid_col]).strip() if uuid_col and feat[uuid_col] else ""

            # Locate feature in main_layer using fid first, then map_uuid
            main_feat = None
            if target_fid_val is not None and has_fid_field:
                q = (
                    f'"fid" = {int(target_fid_val)}'
                    if (isinstance(target_fid_val, int) or (isinstance(target_fid_val, str) and target_fid_val.isdigit()))
                    else f'"fid" = \'{str(target_fid_val).replace(chr(39), chr(39)+chr(39))}\''
                )
                for mf in main_layer.getFeatures(QgsFeatureRequest().setFilterExpression(q)):
                    main_feat = mf
                    break

            if not main_feat and target_fid_val is not None:
                try:
                    mf = main_layer.getFeature(int(target_fid_val))
                    if mf.isValid():
                        main_feat = mf
                except Exception:
                    pass

            if not main_feat and uuid_str:
                clean_uuid = uuid_str.replace("'", "''")
                for mf in main_layer.getFeatures(QgsFeatureRequest().setFilterExpression(f'"map_uuid" = \'{clean_uuid}\'')):
                    main_feat = mf
                    break

            if main_feat and main_feat.isValid():
                main_layer.changeAttributeValue(main_feat.id(), ea_idx, new_val_str)
                # Store by fid and uuid for caller UI lookups (both sf_ea_geocode and ea_geocode)
                res_dict = {"sf_ea_geocode": new_val_str, "ea_geocode": new_val_str}
                if target_fid_val is not None:
                    updated_values[target_fid_val] = res_dict
                    updated_values[str(target_fid_val)] = res_dict
                if uuid_str:
                    updated_values[uuid_str] = res_dict
                # Also store by QGIS internal feature id
                updated_values[main_feat.id()] = res_dict
                fixed_count += 1

    except Exception as exc:
        # Fallback: Direct QGIS Expression engine evaluation
        if feedback:
            feedback.pushWarning(f"Field calculator processing failed ({exc}), using QgsExpression fallback.")

        expr = QgsExpression('coalesce(left("sf_bsn_geoid", 14), left("bsn_geoid", 14))')
        expr_context = QgsExpressionContext()
        expr_context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(main_layer))

        # Query matching features in main_layer
        for main_feat in main_layer.getFeatures(QgsFeatureRequest().setFilterExpression(filter_expr)):
            expr_context.setFeature(main_feat)
            calc_res = expr.evaluate(expr_context)
            res_str = "" if calc_res is None else str(calc_res).strip()
            main_layer.changeAttributeValue(main_feat.id(), ea_idx, res_str)

            fid_val = main_feat["fid"] if has_fid_field else main_feat.id()
            res_dict = {"sf_ea_geocode": res_str, "ea_geocode": res_str}
            updated_values[fid_val] = res_dict
            updated_values[str(fid_val)] = res_dict
            updated_values[main_feat.id()] = res_dict

            if "map_uuid" in [f.name().lower() for f in main_layer.fields()]:
                u_str = str(main_feat["map_uuid"]).strip()
                if u_str:
                    updated_values[u_str] = {"ea_geocode": res_str}

            fixed_count += 1

    return {
        "success": fixed_count > 0,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Successfully calculated ea_geocode for {fixed_count} feature(s).",
    }
