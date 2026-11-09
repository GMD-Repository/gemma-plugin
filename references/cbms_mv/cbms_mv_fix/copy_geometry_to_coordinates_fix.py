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
    from qgis.PyQt.QtCore import Qt, QVariant
except ImportError:
    try:
        from PyQt5.QtCore import Qt, QVariant
    except ImportError:
        Qt = None
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

    target_err_fids = kwargs.get("target_err_fids")
    target_err_set = _flatten_ids(target_err_fids) if target_err_fids is not None else set()
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
            new_fld = QgsField("sf_longitude", QVariant.Double)
            if hasattr(active_layer, "addAttribute") and active_layer.isEditable() and getattr(active_layer, "providerType", lambda: "memory")() != "memory":
                active_layer.addAttribute(new_fld)
            else:
                active_layer.dataProvider().addAttributes([new_fld])
                active_layer.updateFields()
            target_lon_fields.append("sf_longitude")
        except Exception:
            pass

    if not target_lat_fields:
        try:
            new_fld = QgsField("sf_latitude", QVariant.Double)
            if hasattr(active_layer, "addAttribute") and active_layer.isEditable() and getattr(active_layer, "providerType", lambda: "memory")() != "memory":
                active_layer.addAttribute(new_fld)
            else:
                active_layer.dataProvider().addAttributes([new_fld])
                active_layer.updateFields()
            target_lat_fields.append("sf_latitude")
        except Exception:
            pass

    active_field_names = active_layer.fields().names() if hasattr(active_layer.fields(), "names") else []
    is_error_active = (error_layer is not None and active_layer == error_layer)

    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    updated_values: Dict[Any, Dict[str, str]] = {}
    fixed_count = 0
    skipped_no_geom = 0

    rows_to_process: List[int] = list(target_rows) if target_rows is not None else []
    if not rows_to_process and table and hasattr(table, "rowCount") and Qt is not None:
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if item0 and item0.checkState() == Qt.Checked:
                rows_to_process.append(r)

    def _extract_lon_lat_from_feat(feat_obj: Any, lyr_obj: Any) -> Optional[tuple]:
        geom = feat_obj.geometry() if (feat_obj and feat_obj.hasGeometry() and not feat_obj.geometry().isEmpty()) else None
        source_crs = lyr_obj.crs() if (lyr_obj and hasattr(lyr_obj, "crs")) else None
        if not geom or geom.isEmpty():
            return None
        if source_crs and hasattr(source_crs, "isValid") and source_crs.isValid() and source_crs != wgs84:
            try:
                xform = QgsCoordinateTransform(source_crs, wgs84, QgsProject.instance())
                geom = QgsGeometry(geom)
                geom.transform(xform)
            except Exception:
                pass
        pt = None
        try:
            if hasattr(geom, "type") and geom.type() == 0:
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
            return None
        lon_val = None
        lat_val = None
        try:
            exp_x = QgsExpression("$x")
            exp_y = QgsExpression("$y")
            ctx = QgsExpressionContext()
            if hasattr(QgsExpressionContextUtils, "globalProjectLayerScopes") and lyr_obj is not None:
                ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyr_obj))
            ctx.setFeature(feat_obj)
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
        return lon_val, lat_val

    # Branch A: Row-Driven Table Iteration (1-to-1 with selected UI rows)
    if table and hasattr(table, "rowCount") and rows_to_process:
        err_field_names = (
            error_layer.fields().names()
            if (error_layer and error_layer.isValid() and hasattr(error_layer.fields(), "names"))
            else []
        )
        err_lon_fields = [f for f in ("sf_longitude", "longitude", "x_current", "df_x_current") if f in err_field_names]
        err_lat_fields = [f for f in ("sf_latitude", "latitude", "y_current", "df_y_current") if f in err_field_names]

        for r in rows_to_process:
            if feedback and feedback.isCanceled():
                break
            item0 = table.item(r, 0)
            if not item0:
                skipped_no_geom += 1
                continue

            s_fid = item0.data(Qt.UserRole) if Qt is not None else None
            u_str = str(item0.data(Qt.UserRole + 1) or "").strip() if Qt is not None else ""
            e_fid = item0.data(Qt.UserRole + 3) if Qt is not None else None
            df_f = item0.data(Qt.UserRole + 4) if Qt is not None else None
            df_u = str(item0.data(Qt.UserRole + 5) or "").strip() if Qt is not None else ""
            sf_f = item0.data(Qt.UserRole + 6) if Qt is not None else None
            sf_u = str(item0.data(Qt.UserRole + 7) or "").strip() if Qt is not None else ""

            row_main_fid = (
                sf_f
                if (sf_f is not None and str(sf_f).strip() not in ("", "NULL", "None"))
                else (
                    s_fid
                    if (s_fid is not None and str(s_fid).strip() not in ("", "NULL", "None") and s_fid != e_fid)
                    else None
                )
            )
            row_uuid = sf_u or u_str or df_u
            key_fid = row_main_fid if row_main_fid is not None else (df_f if df_f is not None else s_fid)
            row_ukey = make_unique_feature_key(key_fid, row_uuid)

            # Locate feature in active_layer
            feat = None
            if dialog and hasattr(dialog, "_find_main_feature"):
                feat = dialog._find_main_feature(active_layer, fid=row_main_fid, map_uuid=row_uuid)
            if not feat:
                if row_main_fid is not None:
                    try:
                        cand_id = int(row_main_fid) if str(row_main_fid).lstrip("-").isdigit() else row_main_fid
                        cand_f = active_layer.getFeature(cand_id)
                        if cand_f and cand_f.isValid():
                            feat = cand_f
                    except Exception:
                        feat = None
                if (not feat or not feat.isValid()) and row_uuid:
                    for f in active_layer.getFeatures():
                        u_cand = ""
                        for col in ("sf_map_uuid", "map_uuid", "uuid"):
                            if col in active_field_names:
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
                        cand_ef_id = int(e_fid) if str(e_fid).lstrip("-").isdigit() else e_fid
                        cand_ef = error_layer.getFeature(cand_ef_id)
                        if cand_ef and cand_ef.isValid():
                            ef = cand_ef
                    except Exception:
                        ef = None
                if (not ef or not ef.isValid()) and row_uuid:
                    for f in error_layer.getFeatures():
                        u_cand = ""
                        for col in ("sf_map_uuid", "map_uuid", "uuid", "df_map_uuid"):
                            if col in err_field_names:
                                v = f.attribute(col)
                                if v and str(v).strip().lower() not in ("", "null", "none"):
                                    u_cand = str(v).strip()
                                    break
                        if u_cand and u_cand.lower() == row_uuid.lower():
                            ef = f
                            break

            coords = None
            if feat and feat.isValid():
                coords = _extract_lon_lat_from_feat(feat, active_layer)
            if coords is None and ef and ef.isValid():
                coords = _extract_lon_lat_from_feat(ef, error_layer)
                if coords is not None and feat and feat.isValid() and hasattr(active_layer, "changeGeometry"):
                    active_layer.changeGeometry(feat.id(), ef.geometry())

            if coords is None:
                skipped_no_geom += 1
                continue

            lon_val, lat_val = coords
            lon_str = str(lon_val)
            lat_str = str(lat_val)

            if feat and feat.isValid():
                f_id = feat.id()
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

            if error_layer and error_layer.isValid() and ef and ef.isValid() and error_layer != active_layer:
                for lf in err_lon_fields:
                    idx = error_layer.fields().indexOf(lf)
                    if idx != -1:
                        error_layer.changeAttributeValue(ef.id(), idx, lon_str)
                for lf in err_lat_fields:
                    idx = error_layer.fields().indexOf(lf)
                    if idx != -1:
                        error_layer.changeAttributeValue(ef.id(), idx, lat_str)

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
            updated_values[f"row_{r}"] = payload
            if e_fid is not None and str(e_fid).strip() not in ("", "NULL", "None"):
                updated_values[f"err_{e_fid}"] = payload
            if row_ukey:
                updated_values[row_ukey] = payload
                updated_values[row_ukey.lower()] = payload
                updated_values[f"sf_{row_ukey}"] = payload
                updated_values[f"sf_{row_ukey.lower()}"] = payload
            if row_main_fid is not None:
                updated_values[row_main_fid] = payload
                updated_values[f"fid_{row_main_fid}"] = payload
            if row_uuid:
                updated_values[row_uuid] = payload
                updated_values[row_uuid.lower()] = payload
                updated_values[f"uuid_{row_uuid.lower()}"] = payload

            fixed_count += 1

        if feedback:
            feedback.pushInfo(f"Copied geometry to longitude and latitude for {fixed_count} feature(s).")

        return {
            "success": True,
            "fixed_count": fixed_count,
            "selected_count": len(rows_to_process),
            "skipped_count": skipped_no_geom,
            "updated_values": updated_values,
            "message": (
                f"Copied map coordinates to longitude and latitude for {fixed_count} record(s)."
                if fixed_count > 0
                else "No records updated (please make sure the selected records have points on the map)."
            ),
        }

    # Branch B: Layer Feature Iteration (Headless / non-table fallback)
    for feat in active_layer.getFeatures():
        if feedback and feedback.isCanceled():
            break

        f_id = feat.id()
        spatial_ids = _flatten_ids(f_id)
        feat_ids = set(spatial_ids)
        feat_uuid = ""

        if "sf_fid" in active_field_names:
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
            if col in active_field_names:
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
                if col in active_field_names:
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

        # Extract geometry
        geom = feat.geometry() if (feat.hasGeometry() and not feat.geometry().isEmpty()) else None
        source_crs = active_layer.crs() if hasattr(active_layer, "crs") else None

        # Fallback to error_layer feature geometry if active_layer feature lacked geometry
        if not geom and error_layer and error_layer.isValid() and error_layer != active_layer:
            err_fnames = error_layer.fields().names() if hasattr(error_layer.fields(), "names") else []
            for ef in error_layer.getFeatures():
                ef_uuid = ""
                for col in ("sf_map_uuid", "map_uuid", "uuid", "df_map_uuid"):
                    if col in err_fnames:
                        try:
                            val = ef.attribute(col)
                            if val is not None and val != NULL and str(val).strip():
                                ef_uuid = str(val).strip()
                                break
                        except Exception:
                            pass
                ef_matched = False
                if "sf_fid" in err_fnames:
                    try:
                        ef_sf = ef.attribute("sf_fid")
                        if ef_sf is not None and ef_sf != NULL:
                            ef_uk = make_unique_feature_key(ef_sf, ef_uuid)
                            ef_matched = bool(ef_uk and (ef_uk in cand_keys or ef_uk.lower() in cand_keys_lower))
                    except Exception:
                        pass
                elif feat_uuid and ef_uuid:
                    ef_matched = (ef_uuid.lower() == feat_uuid.lower())

                if ef_matched:
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
        err_field_names = error_layer.fields().names() if hasattr(error_layer.fields(), "names") else []
        err_lon_fields = [f for f in ("sf_longitude", "longitude", "x_current", "df_x_current") if f in err_field_names]
        err_lat_fields = [f for f in ("sf_latitude", "latitude", "y_current", "df_y_current") if f in err_field_names]
        has_err_sf_fid = ("sf_fid" in err_field_names or "fid" in err_field_names)
        if err_lon_fields or err_lat_fields:
            for ef in error_layer.getFeatures():
                ef_uuid = ""
                for col in ("sf_map_uuid", "map_uuid", "uuid", "df_map_uuid"):
                    if col in err_field_names:
                        try:
                            val = ef.attribute(col)
                            if val is not None and val != NULL and str(val).strip():
                                ef_uuid = str(val).strip()
                                break
                        except Exception:
                            pass

                matched_payload = None
                if has_err_sf_fid:
                    sf_col_name = "sf_fid" if "sf_fid" in err_field_names else "fid"
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
                    for lf in err_lon_fields:
                        idx = error_layer.fields().indexOf(lf)
                        if idx != -1:
                            error_layer.changeAttributeValue(ef.id(), idx, matched_payload["sf_longitude"])
                    for lf in err_lat_fields:
                        idx = error_layer.fields().indexOf(lf)
                        if idx != -1:
                            error_layer.changeAttributeValue(ef.id(), idx, matched_payload["sf_latitude"])

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
