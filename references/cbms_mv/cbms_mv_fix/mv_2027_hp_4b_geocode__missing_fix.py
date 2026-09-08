# -*- coding: utf-8 -*-
"""
Fix Algorithm for mv_2027_hp_4b_geocode__missing.

Validation Problem:
    Geotagged building points with NULL or invalid ea_geocode (length != 14).

Fix Logic:
    Calculates the 'ea_geocode' attribute by extracting the first 14 characters
    from 'bsn_geoid' using QGIS built-in native:fieldcalculator:
        FORMULA: left("bsn_geoid", 14)
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
    target_uuids: List[str],
    feedback: Optional[QgsProcessingFeedback] = None,
) -> Dict[str, Any]:
    """
    Execute automated fix on the specified features in main_layer using QGIS built-in tools.

    Args:
        main_layer: The primary Geotagged Building Points QgsVectorLayer.
        target_uuids: List of map_uuid strings to fix.
        feedback: Optional QgsProcessingFeedback for reporting progress.

    Returns:
        Dict containing:
            - success (bool)
            - fixed_count (int)
            - updated_values (dict): {map_uuid: {"ea_geocode": new_value}}
            - message (str)
    """
    if not main_layer or not main_layer.isValid():
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "Main building points layer is invalid or not loaded.",
        }

    if not target_uuids:
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

    updated_values: Dict[str, Dict[str, Any]] = {}
    fixed_count = 0

    # Build SQL-style list of escaped UUIDs
    escaped_uuids = ", ".join(f"'{str(u).strip()}'" for u in target_uuids if str(u).strip())
    if not escaped_uuids:
        return {
            "success": False,
            "fixed_count": 0,
            "updated_values": {},
            "message": "No valid UUIDs provided.",
        }

    try:
        # Backend 1: Execute QGIS Native Field Calculator on extracted subset
        extracted = processing.run(
            "native:extractbyexpression",
            {
                "INPUT": main_layer,
                "EXPRESSION": f'"map_uuid" IN ({escaped_uuids})',
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
                "FORMULA": 'left("bsn_geoid", 14)',
                "OUTPUT": "memory:",
            },
            feedback=feedback,
        )["OUTPUT"]

        # Read calculated values and apply directly to main_layer edit buffer
        for feat in calc_layer.getFeatures():
            uuid = str(feat["map_uuid"]).strip()
            new_val = feat["ea_geocode"]
            new_val_str = "" if new_val is None else str(new_val).strip()

            req = QgsFeatureRequest().setFilterExpression(f'"map_uuid" = \'{uuid}\'')
            for main_feat in main_layer.getFeatures(req):
                main_layer.changeAttributeValue(main_feat.id(), ea_idx, new_val_str)
                updated_values[uuid] = {"ea_geocode": new_val_str}
                fixed_count += 1
                break

    except Exception as exc:
        # Fallback: Direct QGIS Expression engine evaluation
        if feedback:
            feedback.pushWarning(f"Field calculator processing failed ({exc}), using QgsExpression fallback.")

        expr = QgsExpression('left("bsn_geoid", 14)')
        expr_context = QgsExpressionContext()
        expr_context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(main_layer))

        for uuid_str in target_uuids:
            clean_uuid = str(uuid_str).strip()
            if not clean_uuid:
                continue
            req = QgsFeatureRequest().setFilterExpression(f'"map_uuid" = \'{clean_uuid}\'')
            for main_feat in main_layer.getFeatures(req):
                expr_context.setFeature(main_feat)
                calc_res = expr.evaluate(expr_context)
                res_str = "" if calc_res is None else str(calc_res).strip()
                main_layer.changeAttributeValue(main_feat.id(), ea_idx, res_str)
                updated_values[clean_uuid] = {"ea_geocode": res_str}
                fixed_count += 1
                break

    return {
        "success": fixed_count > 0,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Successfully calculated ea_geocode for {fixed_count} feature(s).",
    }
