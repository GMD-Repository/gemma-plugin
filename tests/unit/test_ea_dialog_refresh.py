# -*- coding: utf-8 -*-
"""
Unit test module for EA Delineation and Merging dialog refresh functionality.
Verifies that opening/refreshing the dialog resets all inputs, process states,
logs, KPI cards, results tables, and summaries across Tab 1, Tab 2, and Tab 3.
"""

import unittest
from unittest.mock import MagicMock, patch
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, MockGenericClass

setup_qgis_mock_if_needed()


class TestEADialogRefresh(unittest.TestCase):
    """Test suite for EALauncherDialog refresh lifecycle methods."""

    def test_refresh_all_methods_exist(self):
        """Verify that refresh methods exist on EALauncherDialog class."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        self.assertTrue(hasattr(EALauncherDialog, "refresh_all"), "EALauncherDialog must have refresh_all method")
        self.assertTrue(hasattr(EALauncherDialog, "_pre_ea_refresh"), "EALauncherDialog must have _pre_ea_refresh method")
        self.assertTrue(hasattr(EALauncherDialog, "_create_ea_refresh"), "EALauncherDialog must have _create_ea_refresh method")
        self.assertTrue(hasattr(EALauncherDialog, "_ea_merge_refresh"), "EALauncherDialog must have _ea_merge_refresh method")

    def test_refresh_all_calls_sub_refreshes(self):
        """Verify that refresh_all calls _pre_ea_refresh, _create_ea_refresh, and _ea_merge_refresh."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        # Create a mock instance with methods mocked
        mock_dlg = MagicMock(spec=EALauncherDialog)
        # Bind the real refresh_all method to mock_dlg
        EALauncherDialog.refresh_all(mock_dlg)

        mock_dlg._pre_ea_refresh.assert_called_once()
        mock_dlg._create_ea_refresh.assert_called_once()
        mock_dlg._ea_merge_refresh.assert_called_once()

    def test_pre_ea_refresh_resets_state(self):
        """Verify that _pre_ea_refresh resets controls, logs, tables, and runs auto-detection."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.pre_ea_bgy_combo = MagicMock()
        mock_dlg.pre_ea_ea_combo = MagicMock()
        mock_dlg.pre_ea_output_folder_widget = MagicMock()
        mock_dlg.pre_ea_gap_tol_spin = MagicMock()
        mock_dlg.pre_ea_clip_chk = MagicMock()
        mock_dlg.pre_ea_resolve_overlaps_chk = MagicMock()
        mock_dlg.pre_ea_detect_gaps_chk = MagicMock()
        mock_dlg.pre_ea_assign_gaps_chk = MagicMock()
        mock_dlg.pre_ea_progress_bar = MagicMock()
        mock_dlg.pre_ea_cancel_btn = MagicMock()
        mock_dlg.pre_ea_status_banner = MagicMock()
        mock_dlg.pre_ea_results_table = MagicMock()
        mock_dlg.pre_ea_log_console = MagicMock()
        mock_dlg.pre_ea_right_tabs = MagicMock()
        mock_dlg._pre_ea_sum_status_lbl = MagicMock()
        mock_dlg._pre_ea_sum_bgy_val = MagicMock()

        # Call real method
        EALauncherDialog._pre_ea_refresh(mock_dlg)

        mock_dlg.pre_ea_bgy_combo.setLayer.assert_called_once_with(None)
        mock_dlg.pre_ea_ea_combo.setLayer.assert_called_once_with(None)
        mock_dlg.pre_ea_output_folder_widget.setFilePath.assert_called_once_with("")
        mock_dlg.pre_ea_gap_tol_spin.setValue.assert_called_once_with(1.0)
        mock_dlg.pre_ea_progress_bar.setValue.assert_called_once_with(0)
        mock_dlg.pre_ea_cancel_btn.setEnabled.assert_called_once_with(False)
        mock_dlg.pre_ea_results_table.setRowCount.assert_called_once_with(0)
        mock_dlg.pre_ea_log_console.clear.assert_called_once()
        mock_dlg._pre_ea_auto_detect_layers.assert_called_once()
        mock_dlg.pre_ea_right_tabs.setCurrentIndex.assert_called_once_with(0)

    def test_create_ea_refresh_resets_state(self):
        """Verify that _create_ea_refresh resets controls, logs, KPI cards, and runs auto-detection."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.all_delineation_candidates = ["item1"]
        mock_dlg.all_merge_candidates = ["item2"]
        mock_dlg.bar_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.enable_thresholds_chk = MagicMock()
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.tolerance_spin = MagicMock()
        mock_dlg.compact_chk = MagicMock()
        mock_dlg.allow_candidate_merge_chk = MagicMock()
        mock_dlg.sliver_combo = MagicMock()
        mock_dlg.crs_widget = MagicMock()
        mock_dlg.params_group = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.delineated_edit = MagicMock()
        mock_dlg.merged_edit = MagicMock()
        mock_dlg.search_edit = MagicMock()
        mock_dlg.progress_bar = MagicMock()
        mock_dlg.cancel_btn = MagicMock()
        mock_dlg.run_btn = MagicMock()
        mock_dlg.status_banner = MagicMock()
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.log_console = MagicMock()
        mock_dlg.tab_widget = MagicMock()

        # prev_ea_combo has no layer after reset
        mock_dlg._safe_get_layer.return_value = None

        EALauncherDialog._create_ea_refresh(mock_dlg)

        self.assertEqual(len(mock_dlg.all_delineation_candidates), 0)
        self.assertEqual(len(mock_dlg.all_merge_candidates), 0)
        mock_dlg.output_folder_widget.setFilePath.assert_called_once_with("")
        mock_dlg.enable_thresholds_chk.setChecked.assert_called_once_with(False)
        mock_dlg.min_hh_spin.setValue.assert_called_once_with(99)
        mock_dlg.max_hh_spin.setValue.assert_called_once_with(300)
        mock_dlg.params_group.setCollapsed.assert_called_once_with(True)
        mock_dlg.progress_bar.setValue.assert_called_once_with(0)
        mock_dlg.cancel_btn.setEnabled.assert_called_once_with(False)
        mock_dlg.run_btn.setEnabled.assert_called_once_with(True)
        mock_dlg.kpi_delin_val.setText.assert_called_once_with("0")
        mock_dlg.kpi_merge_val.setText.assert_called_once_with("0")
        mock_dlg.delineation_table.setRowCount.assert_called_once_with(0)
        mock_dlg.merge_table.setRowCount.assert_called_once_with(0)
        mock_dlg.log_console.clear.assert_called_once()
        mock_dlg.auto_detect_layers.assert_called_once()
        mock_dlg.tab_widget.setCurrentIndex.assert_called_once_with(0)

    def test_ea_merge_refresh_resets_state(self):
        """Verify that _ea_merge_refresh resets controls, replacement list, summaries, and logs."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.ea_merge_ea_combo = MagicMock()
        mock_dlg.ea_merge_output_folder_widget = MagicMock()
        mock_dlg.ea_merge_layers_list = MagicMock()
        mock_dlg.ea_merge_progress_bar = MagicMock()
        mock_dlg.ea_merge_cancel_btn = MagicMock()
        mock_dlg.ea_merge_run_btn = MagicMock()
        mock_dlg.ea_merge_status_banner = MagicMock()
        mock_dlg.ea_merge_log_console = MagicMock()
        mock_dlg.ea_merge_right_tabs = MagicMock()
        mock_dlg._ea_merge_sum_status_lbl = MagicMock()
        mock_dlg._ea_merge_sum_geocode_val = MagicMock()

        EALauncherDialog._ea_merge_refresh(mock_dlg)

        self.assertEqual(mock_dlg._ea_merge_replacement_layers, [])
        mock_dlg.ea_merge_layers_list.clear.assert_called_once()
        mock_dlg.ea_merge_output_folder_widget.setFilePath.assert_called_once_with("")
        mock_dlg.ea_merge_progress_bar.setValue.assert_called_once_with(0)
        mock_dlg.ea_merge_cancel_btn.setEnabled.assert_called_once_with(False)
        mock_dlg.ea_merge_run_btn.setEnabled.assert_called_once_with(True)
        mock_dlg._ea_merge_sum_status_lbl.setText.assert_called_once_with("Status: READY")
        mock_dlg.ea_merge_log_console.clear.assert_called_once()
        mock_dlg._ea_merge_auto_detect_ea_layer.assert_called_once()
        mock_dlg.ea_merge_right_tabs.setCurrentIndex.assert_called_once_with(0)

    @patch("references.create_enumeration_area.dialog.QMessageBox")
    def test_fill_missing_hh_count_strictly_requires_hh_count_in_ea_layer(self, mock_msgbox):
        """Verify that fill_missing_hh_count rejects layers having only 'hhcount' or 'household'."""
        from references.create_enumeration_area.dialog import EALauncherDialog
        from qgis.core import QgsVectorLayer, QgsField
        from qgis.PyQt.QtCore import QVariant

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()

        # EA layer with legacy 'hhcount' instead of 'hh_count'
        ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_EA", "memory")
        ea_layer.dataProvider().addAttributes([QgsField("hhcount", QVariant.Double)])
        ea_layer.updateFields()

        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Test_Bldg", "memory")
        bldg_layer.dataProvider().addAttributes([QgsField("hh_count", QVariant.Double)])
        bldg_layer.updateFields()

        def safe_get_layer(combo):
            if combo is mock_dlg.prev_ea_combo:
                return ea_layer
            if combo is mock_dlg.bldg_combo:
                return bldg_layer
            return None

        mock_dlg._safe_get_layer.side_effect = safe_get_layer

        EALauncherDialog.fill_missing_hh_count(mock_dlg)

        mock_msgbox.critical.assert_called_once()
        args = mock_msgbox.critical.call_args[0]
        self.assertIn("Previous EA layer does not contain 'hh_count' field", args[2])

    @patch("references.create_enumeration_area.dialog.QMessageBox")
    def test_fill_missing_hh_count_rejects_missing_household_in_bldg_layer(self, mock_msgbox):
        """Verify that fill_missing_hh_count rejects building layers lacking hhcount/hh_count."""
        from references.create_enumeration_area.dialog import EALauncherDialog
        from qgis.core import QgsVectorLayer, QgsField
        from qgis.PyQt.QtCore import QVariant

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()

        ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_EA", "memory")
        ea_layer.dataProvider().addAttributes([QgsField("hh_count", QVariant.Double)])
        ea_layer.updateFields()

        # Bldg layer with irrelevant field
        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Test_Bldg", "memory")
        bldg_layer.dataProvider().addAttributes([QgsField("other_field", QVariant.Double)])
        bldg_layer.updateFields()

        def safe_get_layer(combo):
            if combo is mock_dlg.prev_ea_combo:
                return ea_layer
            if combo is mock_dlg.bldg_combo:
                return bldg_layer
            return None

        mock_dlg._safe_get_layer.side_effect = safe_get_layer

        EALauncherDialog.fill_missing_hh_count(mock_dlg)

        mock_msgbox.critical.assert_called_once()
        args = mock_msgbox.critical.call_args[0]
        self.assertIn("Building point layer does not contain 'hhcount'", args[2])

    @patch("references.create_enumeration_area.dialog.QMessageBox")
    def test_fill_missing_hh_count_populates_from_bldg_hhcount(self, mock_msgbox):
        """Verify that fill_missing_hh_count computes and updates hh_count and bldg_count in EA from building 'hhcount'."""
        from references.create_enumeration_area.dialog import EALauncherDialog
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
        from qgis.PyQt.QtCore import QVariant

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.generate_preview = MagicMock()

        ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_EA", "memory")
        ea_layer.dataProvider().addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
        ])
        ea_layer.updateFields()

        ea_feat = QgsFeature(ea_layer.fields())
        ea_feat.setAttribute("ean", "001")
        ea_feat.setAttribute("hh_count", None) # Missing hh_count
        ea_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        ea_layer.dataProvider().addFeatures([ea_feat])

        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Test_Bldg", "memory")
        bldg_layer.dataProvider().addAttributes([QgsField("hhcount", QVariant.Double)])
        bldg_layer.updateFields()

        pt1 = QgsFeature(bldg_layer.fields())
        pt1.setAttribute("hhcount", 3.0)
        pt1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))

        pt2 = QgsFeature(bldg_layer.fields())
        pt2.setAttribute("hhcount", 5.0)
        pt2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(4, 4)))

        bldg_layer.dataProvider().addFeatures([pt1, pt2])

        def safe_get_layer(combo):
            if combo is mock_dlg.prev_ea_combo:
                return ea_layer
            if combo is mock_dlg.bldg_combo:
                return bldg_layer
            return None

        mock_dlg._safe_get_layer.side_effect = safe_get_layer

        EALauncherDialog.fill_missing_hh_count(mock_dlg)

        updated_feats = list(ea_layer.getFeatures())
        self.assertEqual(len(updated_feats), 1)
        self.assertEqual(float(updated_feats[0].attribute("hh_count")), 8.0)
        self.assertEqual(int(updated_feats[0].attribute("bldg_count")), 2)
        mock_dlg.generate_preview.assert_called_once()
        mock_msgbox.information.assert_called_once()

    @patch("references.create_enumeration_area.dialog.QMessageBox")
    def test_fill_missing_hh_count_proportional_scaling_to_parent_hhcount(self, mock_msgbox):
        """Verify that fill_missing_hh_count proportionally scales building point counts to match parent hhcount and sets bldg_count."""
        from references.create_enumeration_area.dialog import EALauncherDialog
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
        from qgis.PyQt.QtCore import QVariant

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.generate_preview = MagicMock()

        ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_Delineated_EA", "memory")
        ea_layer.dataProvider().addAttributes([
            QgsField("code", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("hhcount", QVariant.Double),
            QgsField("hh_count", QVariant.Double),
        ])
        ea_layer.updateFields()

        # Sub-EA 1 (001000) from parent 000000 with hhcount 302
        sub_ea1 = QgsFeature(ea_layer.fields())
        sub_ea1.setAttribute("code", "000000")
        sub_ea1.setAttribute("ean", "001000")
        sub_ea1.setAttribute("hhcount", 302.0)
        sub_ea1.setAttribute("hh_count", None)
        sub_ea1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))

        # Sub-EA 2 (002000) from parent 000000 with hhcount 302
        sub_ea2 = QgsFeature(ea_layer.fields())
        sub_ea2.setAttribute("code", "000000")
        sub_ea2.setAttribute("ean", "002000")
        sub_ea2.setAttribute("hhcount", 302.0)
        sub_ea2.setAttribute("hh_count", None)
        sub_ea2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))

        ea_layer.dataProvider().addFeatures([sub_ea1, sub_ea2])

        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Test_Bldg", "memory")
        bldg_layer.dataProvider().addAttributes([QgsField("hhcount", QVariant.Double)])
        bldg_layer.updateFields()

        # 204 HH inside Sub-EA 1 (2 building points)
        pt1 = QgsFeature(bldg_layer.fields())
        pt1.setAttribute("hhcount", 104.0)
        pt1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 5)))

        pt2 = QgsFeature(bldg_layer.fields())
        pt2.setAttribute("hhcount", 100.0)
        pt2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(3, 5)))

        # 106 HH inside Sub-EA 2 (1 building point)
        pt3 = QgsFeature(bldg_layer.fields())
        pt3.setAttribute("hhcount", 106.0)
        pt3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(7, 5)))

        bldg_layer.dataProvider().addFeatures([pt1, pt2, pt3])

        def safe_get_layer(combo):
            if combo is mock_dlg.prev_ea_combo:
                return ea_layer
            if combo is mock_dlg.bldg_combo:
                return bldg_layer
            return None

        mock_dlg._safe_get_layer.side_effect = safe_get_layer

        EALauncherDialog.fill_missing_hh_count(mock_dlg)

        updated_feats = list(ea_layer.getFeatures())
        self.assertEqual(len(updated_feats), 2)

        feat_by_ean = {f.attribute("ean"): f for f in updated_feats}
        # 204 * 302 / 310 = 198.748 -> 199
        self.assertEqual(float(feat_by_ean["001000"].attribute("hh_count")), 199.0)
        self.assertEqual(int(feat_by_ean["001000"].attribute("bldg_count")), 2)

        # 106 * 302 / 310 = 103.251 -> 103
        self.assertEqual(float(feat_by_ean["002000"].attribute("hh_count")), 103.0)
        self.assertEqual(int(feat_by_ean["002000"].attribute("bldg_count")), 1)

        # Total sum matches parent hhcount 302.0
        self.assertEqual(
            float(feat_by_ean["001000"].attribute("hh_count")) + float(feat_by_ean["002000"].attribute("hh_count")),
            302.0
        )
        mock_dlg.generate_preview.assert_called_once()
        mock_msgbox.information.assert_called_once()

    @patch("references.create_enumeration_area.dialog.QMessageBox")
    def test_fill_missing_hh_count_updates_existing_non_empty_values(self, mock_msgbox):
        """Verify that fill_missing_hh_count updates EAs even when hh_count is already non-empty."""
        from references.create_enumeration_area.dialog import EALauncherDialog
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
        from qgis.PyQt.QtCore import QVariant

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.generate_preview = MagicMock()

        ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_EA", "memory")
        ea_layer.dataProvider().addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
        ])
        ea_layer.updateFields()

        ea_feat = QgsFeature(ea_layer.fields())
        ea_feat.setAttribute("ean", "001")
        ea_feat.setAttribute("hh_count", 999.0) # Pre-existing non-empty hh_count
        ea_feat.setAttribute("bldg_count", 0)
        ea_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        ea_layer.dataProvider().addFeatures([ea_feat])

        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Test_Bldg", "memory")
        bldg_layer.dataProvider().addAttributes([QgsField("hhcount", QVariant.Double)])
        bldg_layer.updateFields()

        pt1 = QgsFeature(bldg_layer.fields())
        pt1.setAttribute("hhcount", 15.0)
        pt1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))

        bldg_layer.dataProvider().addFeatures([pt1])

        def safe_get_layer(combo):
            if combo is mock_dlg.prev_ea_combo:
                return ea_layer
            if combo is mock_dlg.bldg_combo:
                return bldg_layer
            return None

        mock_dlg._safe_get_layer.side_effect = safe_get_layer

        EALauncherDialog.fill_missing_hh_count(mock_dlg)

        updated_feats = list(ea_layer.getFeatures())
        self.assertEqual(len(updated_feats), 1)
        self.assertEqual(float(updated_feats[0].attribute("hh_count")), 15.0)
        self.assertEqual(int(updated_feats[0].attribute("bldg_count")), 1)
        mock_dlg.generate_preview.assert_called_once()
        mock_msgbox.information.assert_called_once()

    @patch("references.create_enumeration_area.dialog.QMessageBox")
    def test_fill_missing_hh_count_building_fallback_to_one(self, mock_msgbox):
        """Verify delineation logic: building points with null/empty/0 hhcount fallback to 1.0."""
        from references.create_enumeration_area.dialog import EALauncherDialog
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
        from qgis.PyQt.QtCore import QVariant

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.generate_preview = MagicMock()

        ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_EA", "memory")
        ea_layer.dataProvider().addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Double),
        ])
        ea_layer.updateFields()

        ea_feat = QgsFeature(ea_layer.fields())
        ea_feat.setAttribute("ean", "001")
        ea_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        ea_layer.dataProvider().addFeatures([ea_feat])

        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Test_Bldg", "memory")
        bldg_layer.dataProvider().addAttributes([QgsField("hhcount", QVariant.Double)])
        bldg_layer.updateFields()

        pt1 = QgsFeature(bldg_layer.fields())
        pt1.setAttribute("hhcount", None) # Null -> fallback to 1.0
        pt1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))

        pt2 = QgsFeature(bldg_layer.fields())
        pt2.setAttribute("hhcount", 0.0) # 0.0 -> fallback to 1.0
        pt2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(3, 3)))

        pt3 = QgsFeature(bldg_layer.fields())
        pt3.setAttribute("hhcount", 4.0) # 4.0 -> keeps 4.0
        pt3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(4, 4)))

        bldg_layer.dataProvider().addFeatures([pt1, pt2, pt3])

        def safe_get_layer(combo):
            if combo is mock_dlg.prev_ea_combo:
                return ea_layer
            if combo is mock_dlg.bldg_combo:
                return bldg_layer
            return None

        mock_dlg._safe_get_layer.side_effect = safe_get_layer

        EALauncherDialog.fill_missing_hh_count(mock_dlg)

        updated_feats = list(ea_layer.getFeatures())
        self.assertEqual(len(updated_feats), 1)
        # 1.0 + 1.0 + 4.0 = 6.0
        self.assertEqual(float(updated_feats[0].attribute("hh_count")), 6.0)
        self.assertEqual(int(updated_feats[0].attribute("bldg_count")), 3)

    @patch("references.create_enumeration_area.dialog.QMessageBox")
    def test_fill_missing_hh_count_scales_to_match_hhcount_for_split_sub_eas(self, mock_msgbox):
        """Verify that sub-EAs with parent hhcount 320 and building sums (67, 96 = 163) strictly scale to sum to 320."""
        from references.create_enumeration_area.dialog import EALauncherDialog
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
        from qgis.PyQt.QtCore import QVariant

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.generate_preview = MagicMock()

        ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_Delineated_EA", "memory")
        ea_layer.dataProvider().addAttributes([
            QgsField("barangay", QVariant.String),
            QgsField("code", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("hhcount", QVariant.Double),
            QgsField("bldgcount", QVariant.Int),
            QgsField("new_ean", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
        ])
        ea_layer.updateFields()

        # Row 1: Sub-EA 002000
        sub_ea1 = QgsFeature(ea_layer.fields())
        sub_ea1.setAttribute("barangay", "EA 000000")
        sub_ea1.setAttribute("code", "1004")
        sub_ea1.setAttribute("ean", "1004")
        sub_ea1.setAttribute("hhcount", 320.0)
        sub_ea1.setAttribute("bldgcount", 274)
        sub_ea1.setAttribute("new_ean", "002000")
        sub_ea1.setAttribute("hh_count", None)
        sub_ea1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))

        # Row 2: Sub-EA 001000
        sub_ea2 = QgsFeature(ea_layer.fields())
        sub_ea2.setAttribute("barangay", "EA 000000")
        sub_ea2.setAttribute("code", "1004")
        sub_ea2.setAttribute("ean", "1004")
        sub_ea2.setAttribute("hhcount", 320.0)
        sub_ea2.setAttribute("bldgcount", 274)
        sub_ea2.setAttribute("new_ean", "001000")
        sub_ea2.setAttribute("hh_count", None)
        sub_ea2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))

        ea_layer.dataProvider().addFeatures([sub_ea1, sub_ea2])

        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Test_Bldg", "memory")
        bldg_layer.dataProvider().addAttributes([QgsField("hhcount", QVariant.Double)])
        bldg_layer.updateFields()

        # 109 building points in Sub-EA 1 with total hhcount = 67.0
        bldgs = []
        # 67 points with 1.0, 42 points with 0.0 (fallback to 1.0 in delineation, or suppose 67.0 total)
        for i in range(67):
            pt = QgsFeature(bldg_layer.fields())
            pt.setAttribute("hhcount", 1.0)
            pt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))
            bldgs.append(pt)

        # 96 points with 1.0 in Sub-EA 2
        for i in range(96):
            pt = QgsFeature(bldg_layer.fields())
            pt.setAttribute("hhcount", 1.0)
            pt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(7, 7)))
            bldgs.append(pt)

        bldg_layer.dataProvider().addFeatures(bldgs)

        def safe_get_layer(combo):
            if combo is mock_dlg.prev_ea_combo:
                return ea_layer
            if combo is mock_dlg.bldg_combo:
                return bldg_layer
            return None

        mock_dlg._safe_get_layer.side_effect = safe_get_layer

        EALauncherDialog.fill_missing_hh_count(mock_dlg)

        updated_feats = list(ea_layer.getFeatures())
        self.assertEqual(len(updated_feats), 2)

        feat_by_new_ean = {f.attribute("new_ean"): f for f in updated_feats}
        hh1 = float(feat_by_new_ean["002000"].attribute("hh_count"))
        hh2 = float(feat_by_new_ean["001000"].attribute("hh_count"))

        # Quotas: 67 * 320 / 163 = 131.53 -> 132, 96 * 320 / 163 = 188.46 -> 188
        self.assertEqual(hh1, 132.0)
        self.assertEqual(hh2, 188.0)
        # Total strictly equals parent hhcount 320.0
        self.assertEqual(hh1 + hh2, 320.0)


if __name__ == "__main__":
    unittest.main()


