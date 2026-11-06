# -*- coding: utf-8 -*-
"""
Unit test module for CBMS MV toolbar actions dropdown, SUGGESTED_FIX highlighting,
Row-0 (sf_fid = 0) fix counts, Reset Form confirmation, and contextual Save/Discard UX.
"""

import os
import unittest
import importlib
from unittest.mock import patch
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QMessageBox


class TestCbmsMvDropdownActions(unittest.TestCase):
    """Test suite for CBMS MV toolbar dropdown button, SUGGESTED_FIX, Row-0 fix count, and Save/Discard UX."""

    def setUp(self):
        self.dialog_mod = importlib.import_module("references.cbms_mv.cbmsmv_dialog")
        self.targets_mod = importlib.import_module("references.cbms_mv.cbms_mv_targets")
        try:
            self.fix_mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.cbms_mv_fix")
        except ModuleNotFoundError:
            self.fix_mod = importlib.import_module(
                "references.cbms_mv.cbms_mv_fix.concatenate_ea_geocode_fix"
            )

    def test_dropdown_and_update_selected_toolbar_structure(self):
        """Verify the toolbar has combo_actions, SUGGESTED_FIX catalog, Apply Fix Action, and contextual Discard."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        # Check normal dropdown combobox placed after Select All
        self.assertIn('btn_select_all = QPushButton("Select All")', content)
        self.assertIn('toolbar.addWidget(btn_select_all)', content)
        self.assertIn('combo_actions = QComboBox()', content)
        self.assertIn('toolbar.addWidget(combo_actions)', content)

        # Check Apply Fix Action button placed on the right side of Action dropdown
        self.assertIn('btn_update_selected = QPushButton("Apply Fix Action")', content)
        self.assertIn('toolbar.addWidget(btn_update_selected)', content)

        # Check order: combo_actions -> btn_update_selected -> btn_discard_changes -> btn_save_changes
        combo_pos = content.index('toolbar.addWidget(combo_actions)')
        update_pos = content.index('toolbar.addWidget(btn_update_selected)')
        discard_pos = content.index('toolbar.addWidget(btn_discard_changes)')
        save_pos = content.index('toolbar.addWidget(btn_save_changes)')
        self.assertLess(combo_pos, update_pos)
        self.assertLess(update_pos, discard_pos)
        self.assertLess(discard_pos, save_pos)

        # Check all 8 canonical actions in actions_catalog
        self.assertIn('combo_actions.addItem(dropdown_icon, "Actions")', content)
        self.assertIn('("concatenate_ea_geocode", "Concatenate the ea_geocode", concat_ic)', content)
        self.assertIn('("delete_selected_features", "Delete selected features", del_icon_menu)', content)
        self.assertIn('("generate_point_geometry", "Generate point geometry", geom_ic)', content)
        self.assertIn('("deduplicate_features", "Delete duplicate features (retain one)", dup_ic)', content)
        self.assertIn('("concatenate_bsn_geoid", "Concatenate the bsn_geoid", concat_bsn_ic)', content)
        self.assertIn('("copy_geometry_to_coordinates", "Copy the geometry and paste it into the longitude and latitude columns", copy_geom_ic)', content)
        self.assertIn('("update_datafiles_coordinates", "Update Datafile\'s Coordinates", update_coord_ic)', content)
        self.assertIn('("update_point_geometry", "Update point geometry using sf_longitude and sf_latitude", update_geom_ic)', content)
        self.assertIn('display_label = f"(Suggested) {label}"', content)

        # Verify redundant delete button was removed from toolbar
        self.assertNotIn('toolbar.addWidget(btn_delete_selected)', content)

        # Check trigger wiring
        self.assertIn('btn_update_selected.clicked.connect(_on_trigger_update_selected)', content)
        self.assertIn('def _on_concatenate_ea_geocode(', content)
        self.assertIn('def _delete_selected_features(', content)
        self.assertIn('def _on_generate_point_geometry(', content)
        self.assertIn('def _on_copy_geometry_to_coordinates(', content)
        self.assertIn('def _on_update_datafile_coordinates(', content)
        self.assertIn('def _on_update_point_geometry(', content)

    def test_save_and_contextual_discard_confirmation_dialogs(self):
        """Verify separate 2-option Save | Cancel and Discard | Cancel confirmation prompts."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('btn_discard_changes.clicked.connect(lambda checked=False, v=val_id: self._prompt_discard_confirmation(v))', content)
        self.assertIn('btn_save_changes.clicked.connect(lambda checked=False, v=val_id: self._prompt_save_confirmation(v))', content)
        self.assertIn('def _prompt_save_confirmation(self, target_val_id: Optional[str] = None)', content)
        self.assertIn('def _prompt_discard_confirmation(self, target_val_id: Optional[str] = None)', content)
        self.assertIn('QMessageBox.Save | QMessageBox.Cancel', content)
        self.assertIn('QMessageBox.Discard | QMessageBox.Cancel', content)
        self.assertIn('def _discard_changes(self, target_val_id: Optional[str] = None)', content)

    def test_reset_form_confirmation_and_icon_wiring(self):
        """Verify Reset Form asks for confirmation before clearing and cbms_mv.svg icon is wired."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('"cbms_mv.svg"', content)
        self.assertIn('"Are you sure you want to reset the form?\\n\\n"', content)
        self.assertTrue(os.path.exists("icons/cbms_mv.svg"))
        self.assertTrue(os.path.exists("docs/user-guide/public/icons/cbms_mv.svg"))

    def test_suggested_fix_discovery_across_all_19_scripts(self):
        """Verify discover_cbms_mv_rules extracts valid SUGGESTED_FIX action IDs from all 19 scripts."""
        rules = self.dialog_mod.discover_cbms_mv_rules("gmd_scripts/cbms_mv")
        self.assertGreaterEqual(len(rules), 19)
        rules_by_id = {r["id"]: r for r in rules}
        self.assertEqual(
            rules_by_id["mv_2027_hp_1a_longitude__invalid"]["suggested_fixes"],
            ["copy_geometry_to_coordinates", "update_datafiles_coordinates"],
        )
        for r in rules:
            self.assertTrue(len(r["suggested_fixes"]) >= 1, f"Missing SUGGESTED_FIX for {r['id']}")
            for act_id in r["suggested_fixes"]:
                self.assertIn(act_id, self.targets_mod.CBMS_MV_FIX_ACTIONS)

    def test_ea_geocode_concatenation_logic(self):
        """Verify the 4-step EA geocode calculation used by Concatenate action."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_province_code", QVariant.String))
        fields.append(QgsField("sf_city_mun_code", QVariant.String))
        fields.append(QgsField("sf_barangay_code", QVariant.String))
        fields.append(QgsField("sf_ean", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("sf_province_code", "04")
        feat.setAttribute("sf_city_mun_code", "21")
        feat.setAttribute("sf_barangay_code", "08")
        feat.setAttribute("sf_ean", "002000")
        layer.dataProvider().addFeatures([feat])

        calc = self.fix_mod.compute_ea_geocode_field_calculator(feat, layer)
        self.assertEqual(calc, "042108002000")

    def test_row_zero_sf_fid_does_not_inflate_fix_count(self):
        """Verify fixing Row 0 (sf_fid=0, err_fid=1) fixes 1 record (not 2), and Row 0+1 fixes 2 records (not 3)."""
        copy_mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.copy_geometry_to_coordinates_fix")
        err_layer = QgsVectorLayer("Point?crs=EPSG:4326", "err_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_fid", QVariant.Int))
        fields.append(QgsField("sf_map_uuid", QVariant.String))
        fields.append(QgsField("sf_longitude", QVariant.Double))
        fields.append(QgsField("sf_latitude", QVariant.Double))
        err_layer.dataProvider().addAttributes(fields)
        err_layer.updateFields()

        features = []
        for sf_fid in (0, 1, 2):
            f = QgsFeature(err_layer.fields())
            f.setAttribute("sf_fid", sf_fid)
            f.setAttribute("sf_map_uuid", "")
            f.setAttribute("sf_longitude", 0.0)
            f.setAttribute("sf_latitude", 0.0)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.0 + sf_fid * 0.01, 14.5 + sf_fid * 0.01)))
            features.append(f)
        err_layer.dataProvider().addFeatures(features)

        # Row 0 alone (sf_fid = 0, while memory err_layer feature IDs are 1, 2, 3) -> must fix 1 record!
        res_row0 = copy_mod.run_fix(
            err_layer,
            target_fids=[0],
            target_uuids=[""],
            target_keys={"0|"},
            error_layer=err_layer,
        )
        self.assertTrue(res_row0["success"])
        self.assertEqual(res_row0["fixed_count"], 1)

        # Row 0 + Row 1 (sf_fid = 0 and sf_fid = 1) -> must fix 2 records!
        res_row0_1 = copy_mod.run_fix(
            err_layer,
            target_fids=[0, 1],
            target_uuids=["", ""],
            target_keys={"0|", "1|"},
            error_layer=err_layer,
        )
        self.assertTrue(res_row0_1["success"])
        self.assertEqual(res_row0_1["fixed_count"], 2)

        # Row 1 alone (sf_fid = 1, must NOT collide with Row 0's memory ef.id() = 1) -> must fix 1 record!
        res_row1 = copy_mod.run_fix(
            err_layer,
            target_fids=[1],
            target_uuids=[""],
            target_keys={"1|"},
            error_layer=err_layer,
        )
        self.assertTrue(res_row1["success"])
        self.assertEqual(res_row1["fixed_count"], 1)

    def test_validation_header_labels_no_word_wrap(self):
        """Verify that lbl_vname and lbl_vcount do not wrap text into vertical columns."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("lbl_vname = QLabel(f\"<b>{check_name}</b>\")", content)
        self.assertIn("lbl_vname.setWordWrap(False)", content)
        self.assertIn("lbl_vcount.setWordWrap(False)", content)

    def test_soft_delete_transferred_to_cbms_mv_fix(self):
        """Verify soft delete process functions reside in cbms_mv_fix and are delegated to from cbmsmv_dialog."""
        self.assertTrue(hasattr(self.fix_mod, "delete_selected_features"))
        self.assertTrue(hasattr(self.fix_mod, "mark_feature_deleted"))
        self.assertTrue(hasattr(self.fix_mod, "sync_feature_status"))

        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("cbms_mv_fix.delete_selected_features(", content)
        self.assertIn("cbms_mv_fix.mark_feature_deleted(", content)
        self.assertIn("cbms_mv_fix.sync_feature_status(", content)

    def test_delete_selected_features_wiring(self):
        """Verify that selecting delete_selected_features in combo_actions invokes _delete_selected_features."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("idx = combo_actions.currentIndex()", content)
        self.assertIn('elif act_id == "delete_selected_features"', content)
        self.assertIn("self._delete_selected_features(", content)

        with open("references/cbms_mv/cbms_mv_fix/cbms_mv_fix.py", "r", encoding="utf-8") as f:
            fix_content = f.read()

        self.assertIn('target_status="deleted"', fix_content)
        self.assertIn('new_status = "deleted"', fix_content)
        self.assertIn('layer.changeAttributeValue(target_f_id, f_idx, new_status)', fix_content)
        self.assertIn('main_layer.changeAttributeValue(main_feat.id(), m_idx, new_status)', fix_content)

    def test_generate_point_geometry_wiring(self):
        """Verify that selecting generate_point_geometry in combo_actions invokes _on_generate_point_geometry."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("idx = combo_actions.currentIndex()", content)
        self.assertIn('elif act_id == "generate_point_geometry"', content)
        self.assertIn("self._on_generate_point_geometry(", content)
        self.assertTrue(hasattr(self.fix_mod, "generate_point_geometry"))

    def test_vertical_header_row_click_toggles_checkbox(self):
        """Verify that clicking the row number in the vertical header checks/toggles the row checkbox."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("table.verticalHeader().sectionClicked.connect(", content)
        self.assertIn("def _on_vertical_header_section_clicked(", content)
        self.assertIn("def _sync_row_checkbox_with_selection(", content)
        self.assertIn("it.setCheckState(Qt.Checked if r == row_idx else Qt.Unchecked)", content)

    def test_deduplicate_features_action_wiring_and_auto_select(self):
        """Verify deduplicate_features wiring and auto-select-all behavior in combo_actions."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('("deduplicate_features", "Delete duplicate features (retain one)", dup_ic)', content)
        self.assertIn('elif act_id == "deduplicate_features"', content)
        self.assertIn("self._on_deduplicate_features(", content)
        self.assertIn("def _on_deduplicate_features(", content)
        self.assertIn("def _on_combo_actions_changed(idx: int):", content)
        self.assertIn('if act_id == "deduplicate_features" or "duplicate" in action_text:', content)
        self.assertIn("it.setCheckState(Qt.Checked)", content)
        self.assertIn("table.selectAll()", content)
        self.assertIn('btn_select_all.setText("Select None")', content)
        self.assertIn("combo_actions.currentIndexChanged.connect(_on_combo_actions_changed)", content)
        self.assertTrue(hasattr(self.fix_mod, "deduplicate_features"))


if __name__ == "__main__":
    unittest.main()
