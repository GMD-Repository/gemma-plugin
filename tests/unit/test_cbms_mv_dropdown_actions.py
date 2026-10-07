# -*- coding: utf-8 -*-
"""
Unit test module for CBMS MV toolbar actions dropdown button.
Verifies:
- Actions dropdown button placed next to Select All
- Dropdown-only architecture (no separate Updated Selected or Delete Selected button)
- "Concatenate the ea_geocode" action directly triggers EA concatenation process
- "Delete selected features" action directly triggers delete selected features
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant

setup_qgis_mock_if_needed()


class TestCbmsMvDropdownActions(unittest.TestCase):
    """Test suite for CBMS MV toolbar dropdown button and actions."""

    def setUp(self):
        self.dialog_mod = importlib.import_module("references.cbms_mv.cbmsmv_dialog")
        try:
            self.fix_mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.cbms_mv_fix")
        except ModuleNotFoundError:
            self.fix_mod = importlib.import_module(
                "references.cbms_mv.cbms_mv_fix.mv_2027_hp_4b_ea_geocode__missing_fix"
            )

    def test_dropdown_and_update_selected_toolbar_structure(self):
        """Verify the toolbar has combo_actions and Update Selected button."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        # Check normal dropdown combobox placed after Select All
        self.assertIn('btn_select_all = QPushButton("Select All")', content)
        self.assertIn('toolbar.addWidget(btn_select_all)', content)
        self.assertIn('combo_actions = QComboBox()', content)
        self.assertIn('toolbar.addWidget(combo_actions)', content)

        # Check Update Selected button placed on the right side of Action dropdown
        self.assertIn('btn_update_selected = QPushButton("Update Selected")', content)
        self.assertIn('toolbar.addWidget(btn_update_selected)', content)

        # Check order: combo_actions followed by btn_update_selected
        combo_pos = content.index('toolbar.addWidget(combo_actions)')
        update_pos = content.index('toolbar.addWidget(btn_update_selected)')
        self.assertLess(combo_pos, update_pos)

        # Check dropdown items
        self.assertIn('combo_actions.addItem(dropdown_icon, "Actions")', content)
        self.assertIn('combo_actions.addItem(concat_ic, "Concatenate the ea_geocode")', content)
        self.assertIn('combo_actions.addItem(del_icon_menu, "Delete selected features")', content)
        self.assertIn('combo_actions.addItem(geom_ic, "Generate point geometry")', content)

        # Verify redundant delete button was removed from toolbar
        self.assertNotIn('toolbar.addWidget(btn_delete_selected)', content)

        # Check trigger wiring
        self.assertIn('btn_update_selected.clicked.connect(_on_trigger_update_selected)', content)
        self.assertIn('def _on_concatenate_ea_geocode(', content)
        self.assertIn('def _delete_selected_features(', content)
        self.assertIn('def _on_generate_point_geometry(', content)

    def test_save_button_confirmation_dialog(self):
        """Verify Save Changes button triggers Save / Discard / Cancel confirmation."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('btn_save_changes.clicked.connect(lambda checked=False, v=val_id: self._prompt_save_confirmation(v))', content)
        self.assertIn('def _prompt_save_confirmation(self, target_val_id: Optional[str] = None)', content)
        self.assertIn('QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel', content)
        self.assertIn('def _discard_changes(self, target_val_id: Optional[str] = None)', content)

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
        """Verify that selecting index 2 in combo_actions invokes _delete_selected_features with target_status='deleted'."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("idx = combo_actions.currentIndex()", content)
        self.assertIn("elif idx == 2:", content)
        self.assertIn("self._delete_selected_features(", content)

        with open("references/cbms_mv/cbms_mv_fix/cbms_mv_fix.py", "r", encoding="utf-8") as f:
            fix_content = f.read()

        self.assertIn('target_status="deleted"', fix_content)
        self.assertIn('new_status = "deleted"', fix_content)
        self.assertIn('layer.changeAttributeValue(target_f_id, f_idx, new_status)', fix_content)
        self.assertIn('main_layer.changeAttributeValue(main_feat.id(), m_idx, new_status)', fix_content)

    def test_generate_point_geometry_wiring(self):
        """Verify that selecting index 3 in combo_actions invokes _on_generate_point_geometry and calls fix."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("idx = combo_actions.currentIndex()", content)
        self.assertIn("elif idx == 3:", content)
        self.assertIn("self._on_generate_point_geometry(", content)

        self.assertTrue(hasattr(self.fix_mod, "generate_point_geometry"))

    def test_vertical_header_row_click_toggles_checkbox(self):
        """Verify that clicking the row number in the vertical header checks/toggles the row checkbox and unchecks others if not multi-selection."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("table.verticalHeader().sectionClicked.connect(", content)
        self.assertIn("def _on_vertical_header_section_clicked(", content)
        self.assertIn("def _sync_row_checkbox_with_selection(", content)
        self.assertIn("it.setCheckState(Qt.Checked if r == row_idx else Qt.Unchecked)", content)

    def test_deduplicate_features_action_wiring(self):
        """Verify that selecting index 4 in combo_actions invokes _on_deduplicate_features and calls fix."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('combo_actions.addItem(dup_ic, "Delete duplicate features (retain one)")', content)
        self.assertIn("elif idx == 4:", content)
        self.assertIn("self._on_deduplicate_features(", content)
        self.assertIn("def _on_deduplicate_features(", content)

        self.assertTrue(hasattr(self.fix_mod, "deduplicate_features"))

    def test_deduplicate_features_action_auto_selects_all_features(self):
        """Verify that selecting deduplicate features in combo_actions automatically selects all features in the tab."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("def _on_combo_actions_changed(idx: int):", content)
        self.assertIn('if "duplicate" in action_text or idx == 4:', content)
        self.assertIn("it.setCheckState(Qt.Checked)", content)
        self.assertIn("table.selectAll()", content)
        self.assertIn('btn_select_all.setText("Select None")', content)
        self.assertIn("combo_actions.currentIndexChanged.connect(_on_combo_actions_changed)", content)


if __name__ == "__main__":
    unittest.main()



