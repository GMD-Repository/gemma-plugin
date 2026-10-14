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
    from .delete_selected_features_fix import mark_feature_deleted
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
    from delete_selected_features_fix import mark_feature_deleted

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
    "pos_longit",
    "pos_longitude",
    "pos_latitu",
    "pos_latitude",
}


def _is_deduplication_check_col(col_name: str) -> bool:
    c = str(col_name).strip().lower()
    base_c = c[3:] if c.startswith(("sf_", "df_")) else c
    return base_c in DEDUPLICATION_CHECK_COLS


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
        rows_to_process = checked_rows
    else:
        rows_to_process = list(range(table.rowCount()))

    if len(rows_to_process) < 2:
        if QMessageBox:
            QMessageBox.information(
                dialog,
                "Cannot Deduplicate",
                "At least 2 features are required to check for duplicate coordinates and identical columns.",
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
            if not c_low.startswith(("dup_", "sf_status", "status", "fid", "err_fid", "_orig", "action")) \
               and c_low not in ("", "#", "distance", "sf_en_code", "en_code", "df_en_code", "sf_remarks", "remarks"):
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

        if base_c in ("longitude", "longitud", "pos_longitude", "pos_longit"):
            lon_cols.append(c)
        elif base_c in ("latitude", "latitud", "pos_latitude", "pos_latitu"):
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
        if len(r_list) > 1:
            active_statuses = {row_coord_sigs[r][4] for r in r_list if row_coord_sigs[r][4]}
            if len(active_statuses) <= 1:
                coord_dup_groups.append(r_list)

    # Check B: Group by all compared survey columns
    attr_groups: Dict[Tuple, List[int]] = {}
    for r in rows_to_process:
        asig = row_attr_sigs.get(r)
        if asig:
            if asig not in attr_groups:
                attr_groups[asig] = []
            attr_groups[asig].append(r)
    attr_dup_groups = [r_list for r_list in attr_groups.values() if len(r_list) > 1]

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
        dup_type_desc = "duplicate coordinates (matching map_uuid, bsn_geoid, longitude, and latitude up to 7 decimal places)"
    elif attr_dup_groups and not coord_dup_groups:
        dup_type_desc = "identical survey attributes across all columns"
    else:
        dup_type_desc = "duplicate coordinates (7 decimals) and identical survey attributes"

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

        msg = (
            "The features in this tab do not match duplicate criteria (checked duplicate coordinates on map_uuid, bsn_geoid, longitude, and latitude to 7 decimals, as well as identical survey columns).\n\n"
            f"Differences were detected in:\n{diff_details}\n\n"
            "Features with differing survey data will not be marked as deleted automatically."
        ) if diff_cols else (
            "No duplicate features matching coordinate check (7 decimals) or identical survey columns were found."
        )

        if QMessageBox:
            QMessageBox.warning(dialog, "Features Not Identical", msg)
        if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
            dialog.lbl_footer_status.setText("Deduplication skipped: Features differ across columns or coordinates.")
        return {"success": False, "fixed_count": 0, "message": msg}

    total_to_delete = sum(len(r_list) - 1 for r_list in dup_groups)
    retained_count = len(dup_groups)

    if prompt_confirm and QMessageBox:
        reply = QMessageBox.question(
            dialog,
            "Deduplicate Features",
            f"Found {len(dup_groups)} group(s) of duplicate features ({dup_type_desc}).\n\n"
            f"• Retain active: {retained_count} feature(s) (without 'deleted' status)\n"
            f"• Mark as 'deleted': {total_to_delete} duplicate feature(s)\n\n"
            f"Do you want to proceed and mark the duplicates as 'deleted' in sf_status?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return {"success": False, "fixed_count": 0, "message": "Operation cancelled by user."}

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

    deleted_count = 0
    updated_values = {}

    for r_list in dup_groups:
        retained_row = r_list[0]
        item_ret = table.item(retained_row, 0)
        if item_ret:
            ret_s_fid = item_ret.data(Qt.UserRole)
            ret_uuid = item_ret.data(Qt.UserRole + 1)
            ret_err_fid = item_ret.data(Qt.UserRole + 3)
            for c in range(1, table.columnCount() - 1):
                h_it = table.horizontalHeaderItem(c)
                if h_it and h_it.text().strip().lower() in ("status", "sf_status"):
                    sc_item = table.item(retained_row, c)
                    if sc_item and sc_item.text().strip().lower() == "deleted":
                        mark_feature_deleted(
                            dialog,
                            val_id,
                            layer,
                            table,
                            source_fid=ret_s_fid,
                            map_uuid=ret_uuid,
                            err_fid=ret_err_fid,
                            prompt_confirm=False,
                            target_status="",
                            target_row=retained_row,
                        )
                    break

        for r in r_list[1:]:
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
        btn_update_selected.setText("Update Selected")
        btn_update_selected.setEnabled(False)

    if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
        dialog.lbl_footer_status.setText(
            f"Deduplicated features: Retained {retained_count} active feature(s), "
            f"marked {deleted_count} duplicate(s) as 'deleted' in sf_status (Press Ctrl+S to save)"
        )
    if hasattr(dialog, "iface") and dialog.iface and dialog.iface.mapCanvas():
        dialog.iface.mapCanvas().refresh()

    return {
        "success": True,
        "fixed_count": deleted_count,
        "updated_values": updated_values,
        "message": (
            f"Successfully deduplicated features: Retained {retained_count} active feature(s) "
            f"and marked {deleted_count} duplicate feature(s) as 'deleted'."
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
    if status_field_name is None:
        try:
            main_layer.dataProvider().addAttributes([QgsField("status", QVariant.String)])
            main_layer.updateFields()
            status_field_name = "status"
        except Exception:
            status_field_name = "status"

    status_idx = main_layer.fields().indexOf(status_field_name)

    if not main_layer.isEditable():
        main_layer.startEditing()

    updated_values = {}
    deleted_count = 0

    for feat_list in dup_groups:
        if status_idx != -1:
            curr_val = feat_list[0][status_field_name]
            if curr_val is not None and str(curr_val).strip().lower() == "deleted":
                main_layer.changeAttributeValue(feat_list[0].id(), status_idx, "")

        for dup_feat in feat_list[1:]:
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
