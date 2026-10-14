# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Copy Geometry to Coordinates Process
Action: "Copy the geometry and paste it into the longitude and latitude columns"
Validation ID: copy_geometry_to_coordinates

Extracts original $x (longitude) and $y (latitude) coordinates from point geometries
and pastes them into the longitude (sf_longitude, longitude) and latitude
(sf_latitude, latitude) columns without 7-decimal truncation.
"""
from typing import Any, Dict, List, Optional

from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsField,
    QgsGeometry,
    QgsProcessingFeedback,
    QgsProject,
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
    from .common import _flatten_ids, is_valid_qobject, make_unique_feature_key
except ImportError:
    from common import _flatten_ids, is_valid_qobject, make_unique_feature_key

FIX_ID = "copy_geometry_to_coordinates"
FIX_NAME = "Copy geometry and paste into longitude and latitude columns"
FIX_DESCRIPTION = (
    "Extracts original X (longitude) and Y (latitude) from point geometries and updates "
    "the corresponding longitude and latitude columns."
)


def _run_fix_copy_geometry_to_coordinates(
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
    Automated fix algorithm: copies original geometry point coordinates ($x -> longitude,
    $y -> latitude) into the layer's longitude and latitude columns
    (sf_longitude, longitude, sf_latitude, latitude, etc.).
    """
    active_layer = main_layer if (main_layer and main_layer.isValid()) else error_layer
    if not active_layer or not active_layer.isValid():
        return {
            "success": False,
            "message": "The map layer is missing or could not be opened.",
            "fixed_count": 0,
            "updated_values": {},
        }

    if not active_layer.isEditable() and not active_layer.startEditing():
        return {
            "success": False,
            "message": "The map layer could not be opened for editing.",
            "fixed_count": 0,
            "updated_values": {},
        }

    if error_layer and error_layer.isValid() and not error_layer.isEditable():
        try:
            error_layer.startEditing()
        except Exception:
            pass

    target_keys_set = set(target_keys) if target_keys else set()
    target_keys_lower = {str(k).strip().lower() for k in target_keys_set if k}
    is_targeted = (target_fids is not None) or (target_uuids is not None) or bool(target_keys_set)
    target_set = _flatten_ids(target_fids) | _flatten_ids(target_uuids)

    if is_targeted and not target_set and not target_keys_set:
        return {
            "success": True,
            "fixed_count": 0,
            "updated_values": {},
            "message": "No valid target ID or UUID provided.",
        }

    # Ensure longitude and latitude fields exist on active_layer
    target_lon_fields = [f.name() for f in active_layer.fields() if f.name().lower() in ("sf_longitude", "longitude")]
    target_lat_fields = [f.name() for f in active_layer.fields() if f.name().lower() in ("sf_latitude", "latitude")]

    if not target_lon_fields:
        try:
            active_layer.dataProvider().addAttributes([QgsField("sf_longitude", QVariant.Double)])
            active_layer.updateFields()
            target_lon_fields.append("sf_longitude")
        except Exception:
            pass

    if not target_lat_fields:
        try:
            active_layer.dataProvider().addAttributes([QgsField("sf_latitude", QVariant.Double)])
            active_layer.updateFields()
            target_lat_fields.append("sf_latitude")
        except Exception:
            pass

    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    updated_values: Dict[Any, Dict[str, str]] = {}
    fixed_count = 0
    skipped_no_geom = 0

    for feat in active_layer.getFeatures():
        if feedback and feedback.isCanceled():
            break

        f_id = feat.id()
        feat_ids = _flatten_ids(f_id)
        feat_uuid = ""
        for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
            if col in active_layer.fields().names():
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
            matched = bool(target_set and (feat_ids & target_set))
            if not matched and target_keys_set:
                matched = bool(cand_keys & target_keys_set) or bool(cand_keys_lower & target_keys_lower)
            if not matched:
                continue

        # Extract geometry
        geom = feat.geometry() if (feat.hasGeometry() and not feat.geometry().isEmpty()) else None
        source_crs = active_layer.crs() if hasattr(active_layer, "crs") else None

        # Fallback to error_layer feature geometry if active_layer feature lacked geometry
        if not geom and error_layer and error_layer.isValid() and error_layer != active_layer:
            for ef in error_layer.getFeatures():
                ef_ids = _flatten_ids(ef.id())
                for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
                    if col in error_layer.fields().names():
                        try:
                            val = ef.attribute(col)
                            if val is not None and val != NULL:
                                ef_ids.update(_flatten_ids(val))
                        except Exception:
                            pass
                if ef_ids & feat_ids:
                    if ef.hasGeometry() and not ef.geometry().isEmpty():
                        geom = ef.geometry()
                        source_crs = error_layer.crs()
                        if hasattr(active_layer, "changeGeometry"):
                            active_layer.changeGeometry(f_id, geom)
                    break

        if not geom or geom.isEmpty():
            skipped_no_geom += 1
            continue

        # Coordinate transformation to EPSG:4326 if needed
        if source_crs and hasattr(source_crs, "isValid") and source_crs.isValid() and source_crs != wgs84:
            try:
                xform = QgsCoordinateTransform(source_crs, wgs84, QgsProject.instance())
                geom = QgsGeometry(geom)
                geom.transform(xform)
            except Exception:
                pass

        pt = None
        try:
            if hasattr(geom, "type") and geom.type() == 0:  # Point geometry
                if geom.isMultipart():
                    pts = geom.asMultiPoint()
                    pt = pts[0] if pts else None
                else:
                    pt = geom.asPoint()
            else:
                pt = geom.centroid().asPoint()
        except Exception:
            try:
                pt = geom.asPoint()
            except Exception:
                pass

        if not pt:
            skipped_no_geom += 1
            continue

        # Use original values of $x and $y
        lon_val = None
        lat_val = None
        try:
            exp_x = QgsExpression("$x")
            exp_y = QgsExpression("$y")
            ctx = QgsExpressionContext()
            if hasattr(QgsExpressionContextUtils, "globalProjectLayerScopes"):
                ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(active_layer))
            ctx.setFeature(feat)
            res_x = exp_x.evaluate(ctx)
            res_y = exp_y.evaluate(ctx)
            if res_x is not None and res_x != NULL and not str(res_x).startswith(("<", "Mock")):
                lon_val = float(res_x)
            if res_y is not None and res_y != NULL and not str(res_y).startswith(("<", "Mock")):
                lat_val = float(res_y)
        except Exception:
            pass

        if lon_val is None or lat_val is None:
            lon_val = pt.x()
            lat_val = pt.y()

        lon_str = str(lon_val)
        lat_str = str(lat_val)

        # Assign values to active_layer
        for tf_name in target_lon_fields:
            idx = active_layer.fields().indexOf(tf_name)
            if idx != -1:
                fld = active_layer.fields().at(idx) if hasattr(active_layer.fields(), "at") else active_layer.fields()[idx]
                val_to_set = lon_val if (fld and hasattr(fld, "isNumeric") and fld.isNumeric()) else lon_str
                active_layer.changeAttributeValue(f_id, idx, val_to_set)

        for tf_name in target_lat_fields:
            idx = active_layer.fields().indexOf(tf_name)
            if idx != -1:
                fld = active_layer.fields().at(idx) if hasattr(active_layer.fields(), "at") else active_layer.fields()[idx]
                val_to_set = lat_val if (fld and hasattr(fld, "isNumeric") and fld.isNumeric()) else lat_str
                active_layer.changeAttributeValue(f_id, idx, val_to_set)

        payload = {
            "sf_longitude": lon_str,
            "longitude": lon_str,
            "sf_latitude": lat_str,
            "latitude": lat_str,
            "x_current": lon_str,
            "y_current": lat_str,
            "df_x_current": lon_str,
            "df_y_current": lat_str,
        }
        for k in feat_ids:
            updated_values[k] = payload
        for ck in cand_keys:
            updated_values[ck] = payload
            updated_values[ck.lower()] = payload

        fixed_count += 1

    # Also synchronize error_layer if active_layer is main_layer
    if error_layer and error_layer.isValid() and error_layer != active_layer:
        err_field_names = error_layer.fields().names() if hasattr(error_layer.fields(), "names") else []
        err_lon_fields = [f for f in ("sf_longitude", "longitude", "x_current", "df_x_current") if f in err_field_names]
        err_lat_fields = [f for f in ("sf_latitude", "latitude", "y_current", "df_y_current") if f in err_field_names]
        if err_lon_fields or err_lat_fields:
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

                matched_cand = None
                for k in list(ef_ids) + list(cand_ef_keys) + [k.lower() for k in cand_ef_keys]:
                    if k in updated_values:
                        matched_cand = k
                        break
                if matched_cand:
                    p = updated_values[matched_cand]
                    for lf in err_lon_fields:
                        idx = error_layer.fields().indexOf(lf)
                        if idx != -1:
                            error_layer.changeAttributeValue(ef.id(), idx, p["sf_longitude"])
                    for lf in err_lat_fields:
                        idx = error_layer.fields().indexOf(lf)
                        if idx != -1:
                            error_layer.changeAttributeValue(ef.id(), idx, p["sf_latitude"])

    if feedback:
        feedback.pushInfo(f"Copied geometry to longitude and latitude for {fixed_count} feature(s).")

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": (
            f"Copied map coordinates to longitude and latitude for {fixed_count} record(s)."
            if fixed_count > 0 else
            "No records updated (please make sure the selected records have points on the map)."
        ),
    }


def copy_geometry_to_coordinates(
    dialog: Any,
    *args,
    combo_actions: Optional[Any] = None,
    btn_actions: Optional[Any] = None,
    btn_update_selected: Optional[Any] = None,
    **kwargs,
) -> None:
    """
    Process handler for copying point geometry coordinates and pasting them
    into the longitude and latitude columns for checked table rows.
    Processes the action directly regardless of validation check or file.
    """
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    target_rule = "copy_geometry_to_coordinates"
    if hasattr(dialog, "_fix_selected_features"):
        dialog._fix_selected_features(target_rule, layer, table)
    else:
        _run_fix_copy_geometry_to_coordinates(
            layer,
            error_layer=layer,
            table=table,
            dialog=dialog,
        )


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    target_keys: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute automated fix for copy_geometry_to_coordinates."""
    return _run_fix_copy_geometry_to_coordinates(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        target_keys=target_keys,
        **kwargs,
    )
