# -*- coding: utf-8 -*-
"""
CBMS Map Validation - Delete Selected Features Process (Soft Delete)
Action: "Delete selected features"

Batch marks checked features as deleted by setting boolean is_deleted column to True.
Synchronizes across table rows, in-memory layers, and the primary building points layer.
Does not touch or modify the status column.
"""
from typing import Any, Dict, List, Optional

from qgis.core import (
    NULL,
    QgsField,
    QgsProcessingFeedback,
    QgsVectorLayer,
)
try:
    from qgis.PyQt.QtCore import Qt, QVariant
    from qgis.PyQt.QtWidgets import (
        QComboBox,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
    )
except ImportError:
    try:
        from PyQt5.QtCore import Qt, QVariant
        from PyQt5.QtWidgets import (
            QComboBox,
            QMessageBox,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
        )
    except ImportError:
        Qt = None
        QVariant = None
        QMessageBox = None
        QTableWidgetItem = None
        QTableWidget = None
        QPushButton = None
        QComboBox = None

try:
    from .common import is_valid_qobject, _flatten_ids, make_unique_feature_key
except ImportError:
    from common import is_valid_qobject, _flatten_ids, make_unique_feature_key

FIX_ID = "delete_selected_features"
FIX_NAME = "Delete selected features"
FIX_DESCRIPTION = (
    "Batch marks checked features as deleted (sets is_deleted to True) and synchronizes "
    "across table rows, in-memory layers, and the primary building points layer."
)


def _is_deleted_val(val: Any) -> bool:
    """Check if a value represents a deleted / True state."""
    if val is True:
        return True
    if val is False or val is None or val == NULL:
        return False
    if isinstance(val, (int, float)):
        return val == 1
    s = str(val).strip().lower()
    return s in ("true", "1", "t", "yes", "y", "deleted")


def delete_selected_features(
    dialog: Any,
    *args,
    combo_actions: Optional[Any] = None,
    btn_actions: Optional[Any] = None,
    btn_update_selected: Optional[Any] = None,
    **kwargs,
) -> None:
    """Batch mark all checked features as deleted (setting is_deleted to True), deduplicated by unique (fid + map_uuid)."""
    if len(args) >= 2 and hasattr(args[1], "rowCount"):
        layer, table = args[0], args[1]
    elif len(args) >= 3 and hasattr(args[2], "rowCount"):
        layer, table = args[1], args[2]
    else:
        layer = kwargs.get("layer")
        table = kwargs.get("table")

    val_id = args[0] if (len(args) >= 3 and isinstance(args[0], str)) else "delete_selected_features"
    if not is_valid_qobject(dialog) or not is_valid_qobject(table):
        return
    checked_rows = []
    for r in range(table.rowCount()):
        item0 = table.item(r, 0)
        if item0 and item0.checkState() == Qt.Checked:
            checked_rows.append(r)

    if not checked_rows:
        if QMessageBox:
            QMessageBox.information(dialog, "Nothing Selected", "Please tick the box of at least one row first.")
        return

    if QMessageBox:
        reply = QMessageBox.question(
            dialog,
            "Delete Selected Records",
            f"Mark {len(checked_rows)} selected record(s) as deleted?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

    # Ensure main building points layer is loaded and editable
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
    seen_unique_keys = set()
    processed_features = set()

    for r in checked_rows:
        item0 = table.item(r, 0)
        if not item0:
            continue
        s_fid = item0.data(Qt.UserRole)
        u_str = item0.data(Qt.UserRole + 1)
        e_fid = item0.data(Qt.UserRole + 3)
        sf_f = item0.data(Qt.UserRole + 6)
        sf_u = item0.data(Qt.UserRole + 7)

        best_f = sf_f if (sf_f is not None and str(sf_f).strip() not in ("", "NULL", "None")) else s_fid
        best_u = sf_u or u_str
        ukey = make_unique_feature_key(best_f, best_u)

        # Find action button if present in row
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
            source_fid=best_f or s_fid,
            map_uuid=best_u or u_str,
            err_fid=e_fid,
            button=row_del_btn,
            prompt_confirm=False,
            target_status="deleted",
            target_row=r,
        )
        item0.setCheckState(Qt.Unchecked)

        if ukey:
            seen_unique_keys.add(ukey)
            seen_unique_keys.add(ukey.lower())

        feat_ident = (best_f, best_u)
        if feat_ident not in processed_features:
            processed_features.add(feat_ident)
            deleted_count += 1

    # Synchronize all other rows in the table that share any seen_unique_keys
    if seen_unique_keys:
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if not item0:
                continue
            r_sf_f = item0.data(Qt.UserRole + 6)
            r_s_fid = item0.data(Qt.UserRole)
            r_sf_u = item0.data(Qt.UserRole + 7)
            r_u = item0.data(Qt.UserRole + 1)
            r_f = r_sf_f if (r_sf_f is not None and str(r_sf_f).strip() not in ("", "NULL", "None")) else r_s_fid
            r_u_str = r_sf_u or r_u
            r_ukey = make_unique_feature_key(r_f, r_u_str)
            if r_ukey and (r_ukey in seen_unique_keys or r_ukey.lower() in seen_unique_keys):
                for c in range(1, table.columnCount() - 1):
                    h_it = table.horizontalHeaderItem(c)
                    h_text = h_it.text().strip().lower() if h_it else ""
                    if h_text in ("is_deleted", "sf_is_deleted"):
                        cell_item = table.item(r, c)
                        if cell_item:
                            table.setProperty("is_populating", True)
                            try:
                                cell_item.setText("true")
                                if hasattr(dialog, "_style_table_cell"):
                                    dialog._style_table_cell(cell_item, "deleted")
                            finally:
                                table.setProperty("is_populating", False)

    if combo_actions:
        combo_actions.setItemText(0, "Actions")
    elif btn_actions:
        btn_actions.setText("Actions ▾")
    if btn_update_selected:
        btn_update_selected.setText("Apply Fix Action")
        btn_update_selected.setEnabled(False)

    if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
        dialog.lbl_footer_status.setText(
            f"Marked {deleted_count} record(s) as deleted (is_deleted = true). Click 'Save Changes' (Ctrl+S) to keep them."
        )
    if hasattr(dialog, "iface") and dialog.iface and dialog.iface.mapCanvas():
        dialog.iface.mapCanvas().refresh()


def mark_feature_deleted(
    dialog: Any,
    val_id: str,
    layer: Any,
    table: Any,
    source_fid: Any = None,
    map_uuid: Optional[str] = None,
    err_fid: Any = None,
    button: Optional[Any] = None,
    prompt_confirm: bool = True,
    target_status: Optional[str] = None,
    target_row: Optional[int] = None,
) -> None:
    """
    Mark a single feature as deleted by setting its boolean 'is_deleted' column to True
    (or False if restoring). Does not modify the status column.
    Updates the QTableWidget cell, the memory result layer, and the primary
    Geotagged Building Points layer (ready for Ctrl+S persistence).
    """
    if not is_valid_qobject(dialog) or not is_valid_qobject(table):
        return

    # 1. Locate target row in table dynamically to be immune against sorting/filtering
    if target_row is None:
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if not item0:
                continue
            r_err_fid = item0.data(Qt.UserRole + 3)
            r_source_fid = item0.data(Qt.UserRole)
            r_uuid = str(item0.data(Qt.UserRole + 1) or "").strip()

            if err_fid is not None and r_err_fid == err_fid:
                target_row = r
                break
            if source_fid is not None and r_source_fid == source_fid:
                target_row = r
                break
            if map_uuid and r_uuid == str(map_uuid).strip():
                target_row = r
                break

    # 2. Locate is_deleted column in table
    del_col_indices = []
    for c in range(1, table.columnCount() - 1):
        h_it = table.horizontalHeaderItem(c)
        h_text = h_it.text().strip().lower() if h_it else ""
        if h_text in ("is_deleted", "sf_is_deleted"):
            del_col_indices.append(c)

    # If table doesn't have is_deleted column, insert it before Action
    if not del_col_indices:
        act_col = table.columnCount() - 1
        table.insertColumn(act_col)
        if QTableWidgetItem:
            table.setHorizontalHeaderItem(act_col, QTableWidgetItem("is_deleted"))
        del_col_indices.append(act_col)
        table.setProperty("is_populating", True)
        try:
            for r in range(table.rowCount()):
                b_item = QTableWidgetItem("false") if QTableWidgetItem else None
                if b_item:
                    b_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                    b_item.setData(Qt.UserRole + 2, "is_deleted")
                    item0 = table.item(r, 0)
                    if item0:
                        b_item.setData(Qt.UserRole, item0.data(Qt.UserRole))
                        b_item.setData(Qt.UserRole + 1, item0.data(Qt.UserRole + 1))
                        b_item.setData(Qt.UserRole + 3, item0.data(Qt.UserRole + 3))
                        b_item.setData(Qt.UserRole + 6, item0.data(Qt.UserRole + 6))
                        b_item.setData(Qt.UserRole + 7, item0.data(Qt.UserRole + 7))
                    table.setItem(r, act_col, b_item)
        finally:
            table.setProperty("is_populating", False)

    # 3. Determine current status and decide to_delete
    is_currently_deleted = False
    if target_row is not None:
        for c in del_col_indices:
            c_item = table.item(target_row, c)
            if c_item and _is_deleted_val(c_item.text()):
                is_currently_deleted = True
                break

    if target_status is not None:
        if isinstance(target_status, bool):
            to_delete = target_status
        elif str(target_status).strip().lower() in ("deleted", "true", "1"):
            to_delete = True
        else:
            to_delete = False
    elif is_currently_deleted:
        if prompt_confirm and QMessageBox:
            reply = QMessageBox.question(
                dialog,
                "Restore Record?",
                f"Record #{source_fid or err_fid} is currently marked as deleted.\n\n"
                f"Do you want to restore it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        to_delete = False
    else:
        to_delete = True

    bool_val = True if to_delete else False
    bool_str = "true" if to_delete else "false"

    # 4. Update QTableWidget is_deleted cells
    if target_row is not None:
        table.setProperty("is_populating", True)
        try:
            for c in del_col_indices:
                cell_item = table.item(target_row, c)
                if not cell_item and QTableWidgetItem:
                    cell_item = QTableWidgetItem()
                    cell_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                    table.setItem(target_row, c, cell_item)
                if cell_item:
                    cell_item.setText(bool_str)
                    if hasattr(dialog, "_style_table_cell"):
                        dialog._style_table_cell(cell_item, "deleted" if to_delete else "normal")
        finally:
            table.setProperty("is_populating", False)

    # 5. Update Result Memory Layer
    if layer and hasattr(layer, "isValid") and layer.isValid():
        target_f_id = err_fid if err_fid is not None else source_fid
        if target_f_id is not None:
            if not layer.isEditable():
                try:
                    layer.startEditing()
                except Exception:
                    pass

            del_f_indices = [
                layer.fields().indexOf(fld.name())
                for fld in layer.fields()
                if fld.name().lower() in ("is_deleted", "sf_is_deleted")
            ]
            if not del_f_indices:
                try:
                    layer.dataProvider().addAttributes([QgsField("sf_is_deleted", QVariant.Bool)])
                    layer.updateFields()
                    idx = layer.fields().indexOf("sf_is_deleted")
                    if idx != -1:
                        del_f_indices.append(idx)
                except Exception:
                    pass

            for f_idx in del_f_indices:
                f_type = layer.fields().at(f_idx).type()
                val_to_set = bool_val if f_type == QVariant.Bool else bool_str
                layer.changeAttributeValue(target_f_id, f_idx, val_to_set)

    # 6. Update Primary Geotagged Building Points Layer (main_layer)
    main_layer = dialog._get_or_load_main_building_layer() if hasattr(dialog, "_get_or_load_main_building_layer") else None
    if main_layer and hasattr(main_layer, "isValid") and main_layer.isValid():
        main_feat = dialog._find_main_feature(main_layer, fid=source_fid, map_uuid=map_uuid) if hasattr(dialog, "_find_main_feature") else None
        if main_feat:
            if not main_layer.isEditable():
                try:
                    main_layer.startEditing()
                except Exception:
                    pass

            m_del_indices = [
                main_layer.fields().indexOf(fld.name())
                for fld in main_layer.fields()
                if fld.name().lower() in ("is_deleted", "sf_is_deleted")
            ]
            if not m_del_indices:
                try:
                    main_layer.dataProvider().addAttributes([QgsField("is_deleted", QVariant.Bool)])
                    main_layer.updateFields()
                    idx = main_layer.fields().indexOf("is_deleted")
                    if idx != -1:
                        m_del_indices.append(idx)
                except Exception:
                    pass

            for m_idx in m_del_indices:
                f_type = main_layer.fields().at(m_idx).type()
                val_to_set = bool_val if f_type == QVariant.Bool else bool_str
                main_layer.changeAttributeValue(main_feat.id(), m_idx, val_to_set)

    # 7. Update Button Text & Style
    if not button and target_row is not None:
        act_w = table.cellWidget(target_row, table.columnCount() - 1)
        if act_w:
            for child in act_w.findChildren(QPushButton):
                if child.text() in ("Delete", "Deleted"):
                    button = child
                    break

    if button:
        button.setText("Deleted" if to_delete else "Delete")
        if hasattr(dialog, "_style_row_delete_button"):
            dialog._style_row_delete_button(button, is_deleted=to_delete)

    # 8. Update Footer Status
    if hasattr(dialog, "lbl_footer_status") and dialog.lbl_footer_status:
        if to_delete:
            dialog.lbl_footer_status.setText(
                f"Marked record #{source_fid or err_fid} as deleted (is_deleted = true). Click 'Save Changes' (Ctrl+S) to keep it."
            )
        else:
            dialog.lbl_footer_status.setText(
                f"Restored record #{source_fid or err_fid} (is_deleted = false). Click 'Save Changes' (Ctrl+S) to keep it."
            )

    if hasattr(dialog, "iface") and dialog.iface and dialog.iface.mapCanvas():
        dialog.iface.mapCanvas().refresh()


def sync_feature_status(
    dialog: Any,
    val_id: str,
    source_fid: Any = None,
    map_uuid: Optional[str] = None,
    new_status: Any = "deleted",
) -> None:
    """
    Synchronize a deletion status update initiated from outside the table (e.g. Review Dock)
    into the corresponding result layer tab's QTableWidget is_deleted cell.
    """
    tabs = getattr(dialog, "results_tab_widget", None) or getattr(dialog, "tab_results", None)
    if not tabs:
        return

    to_delete = _is_deleted_val(new_status)
    bool_str = "true" if to_delete else "false"

    target_table = None
    for table in tabs.findChildren(QTableWidget):
        p = table.parent()
        while p and p != tabs:
            if p.property("val_id") == val_id:
                target_table = table
                break
            p = p.parent()
        if target_table:
            break

    if target_table:
        table = target_table
        for r in range(table.rowCount()):
            item0 = table.item(r, 0)
            if not item0:
                continue
            r_fid = item0.data(Qt.UserRole)
            r_uuid = str(item0.data(Qt.UserRole + 1) or "").strip()
            if (source_fid is not None and str(r_fid) == str(source_fid)) or (map_uuid and r_uuid == str(map_uuid).strip()):
                table.setProperty("is_populating", True)
                try:
                    for c in range(1, table.columnCount() - 1):
                        h_it = table.horizontalHeaderItem(c)
                        h_text = h_it.text().strip().lower() if h_it else ""
                        if h_text in ("is_deleted", "sf_is_deleted"):
                            cell_item = table.item(r, c)
                            if not cell_item and QTableWidgetItem:
                                cell_item = QTableWidgetItem()
                                cell_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                                table.setItem(r, c, cell_item)
                            if cell_item:
                                cell_item.setText(bool_str)
                                if hasattr(dialog, "_style_table_cell"):
                                    dialog._style_table_cell(cell_item, "deleted" if to_delete else "normal")
                finally:
                    table.setProperty("is_populating", False)

                # Update row action button if present
                act_w = table.cellWidget(r, table.columnCount() - 1)
                if act_w:
                    for child in act_w.findChildren(QPushButton):
                        if child.text() in ("Delete", "Deleted"):
                            child.setText("Deleted" if to_delete else "Delete")
                            if hasattr(dialog, "_style_row_delete_button"):
                                dialog._style_row_delete_button(child, is_deleted=to_delete)
                            break
                break


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    target_keys: Optional[Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute automated fix for soft delete (sets is_deleted to True). Does not modify status column."""
    if not main_layer or not main_layer.isValid():
        return {"success": False, "message": "The map layer is missing or could not be opened.", "fixed_count": 0, "updated_values": {}}

    target_keys_set = set(target_keys) if target_keys else set()
    target_keys_lower = {str(k).strip().lower() for k in target_keys_set if k}
    is_targeted = (target_fids is not None) or (target_uuids is not None) or bool(target_keys_set)
    target_set = _flatten_ids(target_fids) | _flatten_ids(target_uuids)

    if not main_layer.isEditable() and not main_layer.startEditing():
        return {"success": False, "message": "The map layer could not be opened for editing.", "fixed_count": 0, "updated_values": {}}

    # Locate or create is_deleted column
    del_idx = -1
    for fld in main_layer.fields():
        if fld.name().lower() in ("is_deleted", "sf_is_deleted"):
            del_idx = main_layer.fields().indexOf(fld.name())
            break
    if del_idx == -1:
        main_layer.dataProvider().addAttributes([QgsField("is_deleted", QVariant.Bool)])
        main_layer.updateFields()
        del_idx = main_layer.fields().indexOf("is_deleted")

    f_type = main_layer.fields().at(del_idx).type() if del_idx != -1 else QVariant.Bool
    val_to_set = True if f_type == QVariant.Bool else "true"

    fixed_count = 0
    updated_values = {}
    for feat in main_layer.getFeatures():
        f_id = feat.id()
        feat_ids = _flatten_ids(f_id)
        feat_uuid = ""
        for col in ("sf_fid", "fid", "df_fid", "sf_map_uuid", "map_uuid", "uuid"):
            if col in main_layer.fields().names():
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

        if del_idx != -1:
            main_layer.changeAttributeValue(f_id, del_idx, val_to_set)

        del_payload = {
            "is_deleted": True,
            "sf_is_deleted": True,
        }
        for k in feat_ids:
            updated_values[k] = del_payload
        for ck in cand_keys:
            updated_values[ck] = del_payload
            updated_values[ck.lower()] = del_payload
        fixed_count += 1

    return {
        "success": True,
        "fixed_count": fixed_count,
        "updated_values": updated_values,
        "message": f"Marked {fixed_count} record(s) as deleted (is_deleted = true).",
    }
