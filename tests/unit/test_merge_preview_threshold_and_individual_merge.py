# -*- coding: utf-8 -*-
"""
Unit tests for Merge Preview Maximum Household Threshold Gating and Individual EA Merge Execution.
"""

import unittest
from unittest.mock import MagicMock, patch
from qgis.core import (
    QgsApplication,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsField,
    QgsProject,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QComboBox, QPushButton, QTableWidget, QTextEdit

from references.create_enumeration_area.dialog import EALauncherDialog


class TestMergePreviewThresholdAndIndividualMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qgs = QgsApplication([], False)
        cls.qgs.initQgis()

    @classmethod
    def tearDownClass(cls):
        cls.qgs.exitQgis()

    def tearDown(self):
        QgsProject.instance().clear()

    def test_sync_max_hh_and_merge_max_hh(self):
        """Verify two-way sync helper methods between max_hh_spin and merge_max_hh_spin."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin = MagicMock()

        # Tab 1 -> Tab 2 Sub-tab 2
        EALauncherDialog._sync_max_hh(mock_dlg, 250)
        mock_dlg.merge_max_hh_spin.setValue.assert_called_with(250)

        # Tab 2 Sub-tab 2 -> Tab 1
        EALauncherDialog._sync_merge_max_hh(mock_dlg, 350)
        mock_dlg.max_hh_spin.setValue.assert_called_with(350)

    def test_generate_preview_threshold_gating(self):
        """Verify that neighbors exceeding merge_max_hh are filtered out, leaving empty partners when over limit."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 200
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 300
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/test"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"

        # 1. Previous EA layer with Partner 1 (100 HH) and Partner 2 (150 HH)
        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        f1 = QgsFeature(prev_ea_layer.fields())
        f1.setAttributes(["01701001001", "01701001", "Poblacion", 100.0])
        f1.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        f2 = QgsFeature(prev_ea_layer.fields())
        f2.setAttributes(["01701001002", "01701001", "Poblacion", 150.0])
        f2.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr.addFeatures([f1, f2])

        # 2. Merged EA layer with candidate (180 HH)
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        fcand = QgsFeature(merge_ea_layer.fields())
        fcand.setAttributes(["01701001099", "01701001", "Poblacion", 180.0])
        fcand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 1, 1, 2)))
        mpr.addFeatures([fcand])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        # Case A: max_hh is 300
        # Partner 1 (100 HH) -> Combined = 280 <= 300 (VALID)
        # Partner 2 (150 HH) -> Combined = 330 > 300 (EXCLUDED)
        EALauncherDialog.generate_preview(mock_dlg)
        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        cand_row = mock_dlg.all_merged_ea_candidates[0]
        neighbors = cand_row[5]
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0][0], "01701001001")

        # Case B: max_hh is 250
        # Partner 1 (100 HH) -> Combined = 280 > 250 (EXCLUDED)
        # Partner 2 (150 HH) -> Combined = 330 > 250 (EXCLUDED)
        # Neighbors list must be empty []
        mock_dlg.all_merged_ea_candidates.clear()
        mock_dlg.merge_max_hh_spin.value.return_value = 250
        EALauncherDialog.generate_preview(mock_dlg)
        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        cand_row_250 = mock_dlg.all_merged_ea_candidates[0]
        self.assertEqual(cand_row_250[5], [])

    def test_populate_table_rows_empty_partner_dropdown_and_action_button(self):
        """Verify that when partners exceed threshold (empty neighbors), partner combo is empty/disabled, and Action button is disabled."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.current_theme = "light"
        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)

        # 1. Candidate with no eligible partners (empty list)
        candidates_empty = [
            ("01701001099", "EA 99", "Poblacion", 280.0, "Candidate (280 HH)", [])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates_empty, is_delineation=False)

        combo_empty = table.cellWidget(0, 5)
        self.assertIsInstance(combo_empty, QComboBox)
        self.assertEqual(combo_empty.count(), 0)
        self.assertFalse(combo_empty.isEnabled())

        # Total HH cell shows "—"
        total_cell = table.item(0, 6)
        self.assertIsNotNone(total_cell)
        self.assertEqual(total_cell.text(), "—")

        # Action button is disabled
        action_btn_disabled = table.cellWidget(0, 7)
        self.assertIsInstance(action_btn_disabled, QPushButton)
        self.assertFalse(action_btn_disabled.isEnabled())

        # 2. Candidate with eligible partner
        candidates_with_partner = [
            ("01701001099", "EA 99", "Poblacion", 80.0, "Initiator (<= 99 HH)", [("01701001001", 100.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates_with_partner, is_delineation=False)

        combo_valid = table.cellWidget(0, 5)
        self.assertIsInstance(combo_valid, QComboBox)
        self.assertEqual(combo_valid.count(), 1)
        self.assertTrue(combo_valid.isEnabled())
        self.assertEqual(combo_valid.currentText(), "01701001001")

        total_cell_valid = table.item(0, 6)
        self.assertEqual(total_cell_valid.text(), "180")

        action_btn_enabled = table.cellWidget(0, 7)
        self.assertIsInstance(action_btn_enabled, QPushButton)
        self.assertTrue(action_btn_enabled.isEnabled())

    def test_individual_merge_row_logic(self):
        """Verify _merge_individual_row correctly combines geometry, sums HH, adds feature to target layer, and provides UI feedback."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.merge_log_console = QTextEdit()

        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        f_partner = QgsFeature(prev_ea_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001", "Poblacion", 80.0])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        pr.addFeatures([f_partner])

        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        f_cand = QgsFeature(merge_ea_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001", "Poblacion", 40.0])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        mpr.addFeatures([f_cand])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 40.0, "Initiator (<= 99 HH)", [("01701001001", 80.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)

        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        # Execute individual merge
        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
        )

        # Verify UI state updates: button becomes an active Unmerge button
        self.assertTrue(btn_merge.isEnabled())
        self.assertEqual(btn_merge.text(), "Unmerge")
        self.assertEqual(table.item(0, 4).text(), "Merged ✓")
        self.assertFalse(partner_combo.isEnabled())

        # Verify target layer creation in QgsProject
        merged_layers = QgsProject.instance().mapLayersByName("01701_merged_ea2026")
        self.assertTrue(len(merged_layers) >= 1)
        merged_lyr = merged_layers[0]

        self.assertEqual(merged_lyr.featureCount(), 1)
        out_feat = next(merged_lyr.getFeatures())
        self.assertEqual(out_feat["ean"], "01701001001")
        self.assertEqual(out_feat["hh_count"], 120.0)
        self.assertEqual(out_feat["ea_type"], "MERGED")
        self.assertIn("01701001099 + 01701001001", out_feat["remarks"])

        # Geometry bounding box covers combined extent from x=0 to x=2
        bbox = out_feat.geometry().boundingBox()
        self.assertAlmostEqual(bbox.xMinimum(), 0.0, places=3)
        self.assertAlmostEqual(bbox.xMaximum(), 2.0, places=3)

        # Log console received success message
        log_text = mock_dlg.merge_log_console.toPlainText()
        self.assertIn("[MERGE SUCCESS]", log_text)
        self.assertIn("01701001099", log_text)
        self.assertIn("01701001001", log_text)
        self.assertIn("Total HH: 120", log_text)
        self.assertIn("Total Buildings: 0", log_text)

    def test_find_feature_in_layer_14digit_geocode_and_short_ean(self):
        """Verify _find_feature_in_layer correctly resolves 14-digit geocodes matching 6-digit EANs or geocode fields."""
        layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Test_Layer", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("geocode", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("barangay", QVariant.String)
        ])
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttributes(["01718014001000", "001000", "San Pedro"])
        feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        pr.addFeatures([feat])

        # 1. Exact match by full 14-digit geocode
        f_by_geocode = EALauncherDialog._find_feature_in_layer(layer, "01718014001000")
        self.assertIsNotNone(f_by_geocode)
        self.assertEqual(f_by_geocode["ean"], "001000")

        # 2. Exact match by short 6-digit EAN
        f_by_ean = EALauncherDialog._find_feature_in_layer(layer, "001000")
        self.assertIsNotNone(f_by_ean)
        self.assertEqual(f_by_ean["geocode"], "01718014001000")

        # 3. Layer having only short EAN field searched with 14-digit target
        layer_short = QgsVectorLayer("Polygon?crs=epsg:4326", "Short_Layer", "memory")
        layer_short.dataProvider().addAttributes([
            QgsField("ean", QVariant.String)
        ])
        layer_short.updateFields()
        f_short = QgsFeature(layer_short.fields())
        f_short.setAttributes(["001000"])
        f_short.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        layer_short.dataProvider().addFeatures([f_short])

        f_resolved = EALauncherDialog._find_feature_in_layer(layer_short, "01718014001000")
        self.assertIsNotNone(f_resolved)
        self.assertEqual(f_resolved["ean"], "001000")

    def test_individual_merge_with_integer_remarks_and_in_place_update(self):
        """Verify _merge_individual_row safely updates in-place when target_layer already has candidate and has integer remarks."""
        QgsProject.instance().removeAllMapLayers()

        # Existing target layer with integer remarks
        target_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "01701_merged_ea2026", "memory")
        pr_target = target_layer.dataProvider()
        pr_target.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("remarks", QVariant.Int)
        ])
        target_layer.updateFields()

        # Candidate is already inside target_layer (x: 0->1)
        f_cand = QgsFeature(target_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001099", "Poblacion", 40.0, 0])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        pr_target.addFeatures([f_cand])
        QgsProject.instance().addMapLayer(target_layer)

        # Partner layer (x: 1->2)
        partner_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EA", "memory")
        pr_partner = partner_layer.dataProvider()
        pr_partner.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        partner_layer.updateFields()
        f_partner = QgsFeature(partner_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001001", "Poblacion", 80.0])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr_partner.addFeatures([f_partner])
        QgsProject.instance().addMapLayer(partner_layer)

        mock_dlg = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.iface = None
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._safe_get_layer = lambda combo: (
            partner_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else target_layer
        )

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 40.0, "Initiator (<= 99 HH)", [("01701001001", 80.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)
        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        # Merge candidate into partner
        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
        )

        self.assertEqual(target_layer.featureCount(), 1)
        feat = next(target_layer.getFeatures())
        self.assertEqual(feat["hh_count"], 120.0)
        # Original EAN is preserved, not overwritten
        self.assertEqual(feat["ean"], "01701001099")
        # new_ean holds highest household count EAN (partner 80 > candidate 40)
        self.assertEqual(feat["new_ean"], "01701001001")
        # ea_type is set to MERGED
        self.assertEqual(feat["ea_type"], "MERGED")
        # Remarks must be 1 (integer field safety)
        self.assertEqual(feat["remarks"], 1)
        # Geometry must span x=0 to x=2
        bbox = feat.geometry().boundingBox()
        self.assertAlmostEqual(bbox.xMinimum(), 0.0, places=3)
        self.assertAlmostEqual(bbox.xMaximum(), 2.0, places=3)

    def test_individual_merge_with_length_restricted_remarks(self):
        """Verify _merge_individual_row truncates or fits remarks when field length is limited."""
        QgsProject.instance().removeAllMapLayers()

        target_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "01701_merged_ea2026", "memory")
        pr_target = target_layer.dataProvider()
        pr_target.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("remarks", QVariant.String, len=15)
        ])
        target_layer.updateFields()
        QgsProject.instance().addMapLayer(target_layer)

        prev_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EA", "memory")
        pr_prev = prev_layer.dataProvider()
        pr_prev.addAttributes([QgsField("ean", QVariant.String), QgsField("hh_count", QVariant.Double)])
        prev_layer.updateFields()
        f_cand = QgsFeature(prev_layer.fields())
        f_cand.setAttributes(["01701001099", 40.0])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        f_partner = QgsFeature(prev_layer.fields())
        f_partner.setAttributes(["01701001001", 80.0])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr_prev.addFeatures([f_cand, f_partner])
        QgsProject.instance().addMapLayer(prev_layer)

        mock_dlg = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.iface = None
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._safe_get_layer = lambda combo: prev_layer

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 40.0, "Initiator (<= 99 HH)", [("01701001001", 80.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)
        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
        )

        self.assertEqual(target_layer.featureCount(), 1)
        feat = next(target_layer.getFeatures())
        self.assertTrue(len(str(feat["remarks"])) <= 15)

    def test_individual_merge_with_building_points_spatial_aggregation(self):
        """Verify _merge_individual_row computes total building points and sums est_hhcount within merged polygon."""
        QgsProject.instance().removeAllMapLayers()

        prev_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EA", "memory")
        pr_prev = prev_layer.dataProvider()
        pr_prev.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int)
        ])
        prev_layer.updateFields()

        # Candidate feature: [0, 0] to [1, 1]
        f_cand = QgsFeature(prev_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001", "Poblacion", 10.0, 1])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        # Partner feature: [1, 0] to [2, 1]
        f_partner = QgsFeature(prev_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001", "Poblacion", 20.0, 2])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr_prev.addFeatures([f_cand, f_partner])
        QgsProject.instance().addMapLayer(prev_layer)

        # Building Points layer
        bldg_layer = QgsVectorLayer("Point?crs=epsg:4326", "Building_Points", "memory")
        pr_bldg = bldg_layer.dataProvider()
        pr_bldg.addAttributes([
            QgsField("building_id", QVariant.Int),
            QgsField("est_hhcount", QVariant.Double)
        ])
        bldg_layer.updateFields()

        # Building 1: inside candidate polygon (0.5, 0.5) with 3 households
        b1 = QgsFeature(bldg_layer.fields())
        b1.setAttributes([1, 3.0])
        b1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0.5, 0.5)))

        # Building 2: inside partner polygon (1.5, 0.5) with 5 households
        b2 = QgsFeature(bldg_layer.fields())
        b2.setAttributes([2, 5.0])
        b2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1.5, 0.5)))

        # Building 3: inside merged polygon (1.2, 0.8) with 2 households
        b3 = QgsFeature(bldg_layer.fields())
        b3.setAttributes([3, 2.0])
        b3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(1.2, 0.8)))

        # Building 4: outside merged polygon (5.0, 5.0) with 10 households
        b4 = QgsFeature(bldg_layer.fields())
        b4.setAttributes([4, 10.0])
        b4.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5.0, 5.0)))

        pr_bldg.addFeatures([b1, b2, b3, b4])
        QgsProject.instance().addMapLayer(bldg_layer)

        mock_dlg = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.merge_bldg_combo = MagicMock()
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.iface = None
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer

        def _safe_get_layer(combo):
            if combo in (mock_dlg.bldg_combo, mock_dlg.merge_bldg_combo):
                return bldg_layer
            return prev_layer

        mock_dlg._safe_get_layer = _safe_get_layer

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 10.0, "Initiator (<= 99 HH)", [("01701001001", 20.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)
        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        # Execute merge
        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 10.0, partner_combo, table, btn_merge
        )

        merged_layers = QgsProject.instance().mapLayersByName("01701_merged_ea2026")
        self.assertTrue(len(merged_layers) >= 1)
        merged_lyr = merged_layers[0]

        self.assertEqual(merged_lyr.featureCount(), 1)
        out_feat = next(merged_lyr.getFeatures())

        # Total buildings inside merged polygon: b1, b2, b3 = 3 buildings
        self.assertEqual(out_feat["bldg_count"], 3)
        self.assertIsInstance(out_feat["bldg_count"], int)
        # Total households from building points: 3.0 + 5.0 + 2.0 = 10 (whole number)
        self.assertEqual(out_feat["hh_count"], 10)
        self.assertIsInstance(out_feat["hh_count"], int)

        log_text = mock_dlg.merge_log_console.toPlainText()
        self.assertIn("Total HH: 10", log_text)
        self.assertIn("Total Buildings: 3", log_text)

    def test_individual_merge_imputes_candidate_ean_when_candidate_has_higher_hh(self):
        """Verify _merge_individual_row preserves ean and imputes candidate's EAN into new_ean when candidate has higher HH."""
        QgsProject.instance().removeAllMapLayers()

        prev_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EA", "memory")
        pr_prev = prev_layer.dataProvider()
        pr_prev.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int)
        ])
        prev_layer.updateFields()

        # Candidate feature (for merging): 120 HH
        f_cand = QgsFeature(prev_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001", "Poblacion", 120.0, 5])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        # Partner feature (merge partner): 30 HH
        f_partner = QgsFeature(prev_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001", "Poblacion", 30.0, 2])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr_prev.addFeatures([f_cand, f_partner])
        QgsProject.instance().addMapLayer(prev_layer)

        mock_dlg = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.merge_bldg_combo = MagicMock()
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.iface = None
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._safe_get_layer = lambda combo: prev_layer

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 120.0, "Initiator (<= 99 HH)", [("01701001001", 30.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)
        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        # Merge candidate (120 HH) and partner (30 HH)
        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 120.0, partner_combo, table, btn_merge
        )

        merged_layers = QgsProject.instance().mapLayersByName("01701_merged_ea2026")
        self.assertTrue(len(merged_layers) >= 1)
        merged_lyr = merged_layers[0]

        self.assertEqual(merged_lyr.featureCount(), 1)
        out_feat = next(merged_lyr.getFeatures())

        # Original ean is preserved from partner_feat ("01701001001")
        self.assertEqual(out_feat["ean"], "01701001001")
        # new_ean is imputed with the higher HH count EAN (candidate "01701001099" with 120 HH > partner with 30 HH)
        self.assertEqual(out_feat["new_ean"], "01701001099")
        self.assertEqual(out_feat["hh_count"], 150)

    def test_individual_merge_preserves_hhcount_and_only_updates_hh_count(self):
        """Verify that hhcount remains unchanged and only hh_count is updated during merge."""
        QgsProject.instance().removeAllMapLayers()

        prev_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EA", "memory")
        pr_prev = prev_layer.dataProvider()
        pr_prev.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hhcount", QVariant.Double),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int)
        ])
        prev_layer.updateFields()

        # Candidate feature: original hhcount = 77.0, hh_count = 40.0
        f_cand = QgsFeature(prev_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001", "Poblacion", 77.0, 40.0, 2])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        # Partner feature: original hhcount = 55.0, hh_count = 30.0
        f_partner = QgsFeature(prev_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001", "Poblacion", 55.0, 30.0, 3])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr_prev.addFeatures([f_cand, f_partner])
        QgsProject.instance().addMapLayer(prev_layer)

        mock_dlg = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.merge_bldg_combo = MagicMock()
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.iface = None
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._safe_get_layer = lambda combo: prev_layer

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 40.0, "Initiator (<= 99 HH)", [("01701001001", 30.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)
        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        # Merge candidate (40 HH) and partner (30 HH) -> Total = 70 HH
        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
        )

        merged_layers = QgsProject.instance().mapLayersByName("01701_merged_ea2026")
        self.assertTrue(len(merged_layers) >= 1)
        merged_lyr = merged_layers[0]

        self.assertEqual(merged_lyr.featureCount(), 1)
        out_feat = next(merged_lyr.getFeatures())

        # ONLY hh_count is updated to the merged total
        self.assertEqual(out_feat["hh_count"], 70)
        # hhcount is NOT changed, preserving original partner value
        self.assertEqual(out_feat["hhcount"], 55.0)
        # ea_type is set to MERGED
        self.assertEqual(out_feat["ea_type"], "MERGED")

    def test_individual_merge_updates_ea_type_to_merged_on_existing_feature(self):
        """Verify that ea_type is explicitly updated to MERGED even when an existing feature had RETAINED."""
        QgsProject.instance().removeAllMapLayers()

        prev_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EA", "memory")
        pr_prev = prev_layer.dataProvider()
        pr_prev.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("ea_type", QVariant.String),
        ])
        prev_layer.updateFields()

        f_cand = QgsFeature(prev_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001", "Poblacion", 45.0, "RETAINED"])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        f_partner = QgsFeature(prev_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001", "Poblacion", 35.0, "RETAINED"])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr_prev.addFeatures([f_cand, f_partner])
        QgsProject.instance().addMapLayer(prev_layer)

        # Pre-existing target layer with candidate feature having ea_type = "RETAINED"
        target_layer = QgsVectorLayer("MultiPolygon?crs=epsg:4326", "01701_merged_ea2026", "memory")
        pr_target = target_layer.dataProvider()
        pr_target.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("new_ean", QVariant.String),
            QgsField("ea_type", QVariant.String),
            QgsField("remarks", QVariant.String),
        ])
        target_layer.updateFields()

        f_existing = QgsFeature(target_layer.fields())
        f_existing.setAttributes(["01701001099", "01701001", "Poblacion", 45.0, "", "RETAINED", ""])
        f_existing.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        pr_target.addFeatures([f_existing])
        QgsProject.instance().addMapLayer(target_layer)

        mock_dlg = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.merge_bldg_combo = MagicMock()
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.iface = None
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._safe_get_layer = lambda combo: prev_layer

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 45.0, "Initiator (<= 99 HH)", [("01701001001", 35.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)
        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        # Execute merge on existing feature
        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 45.0, partner_combo, table, btn_merge
        )

        updated_feat = next(target_layer.getFeatures())
        self.assertEqual(updated_feat["ean"], "01701001099")
        self.assertEqual(updated_feat["new_ean"], "01701001099")
        self.assertEqual(updated_feat["hh_count"], 80)
        # Verify ea_type was updated from RETAINED to MERGED
        self.assertEqual(updated_feat["ea_type"], "MERGED")

    def test_merge_preview_strictly_contiguous_partners_only(self):
        """Verify that only contiguous EAs are added to the partner dropdown, excluding non-contiguous same-barangay EAs."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 99
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 300
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/test"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"

        # 1. Previous EA layer with:
        # - Contiguous partner 001 (at x=1..2, sharing boundary at x=1 with candidate at x=0..1, 100 HH)
        # - Distant / Non-contiguous partner 002 (at x=10..11, 50 HH, same barangay Poblacion)
        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        f_contig = QgsFeature(prev_ea_layer.fields())
        f_contig.setAttributes(["01701001001", "01701001", "Poblacion", 100.0])
        f_contig.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))

        f_distant = QgsFeature(prev_ea_layer.fields())
        f_distant.setAttributes(["01701001002", "01701001", "Poblacion", 50.0])
        f_distant.setGeometry(QgsGeometry.fromRect(QgsRectangle(10, 10, 11, 11)))
        pr.addFeatures([f_contig, f_distant])

        # 2. Merged EA layer with candidate (80 HH) at x=0..1, y=0..1
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        fcand = QgsFeature(merge_ea_layer.fields())
        fcand.setAttributes(["01701001099", "01701001", "Poblacion", 80.0])
        fcand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        mpr.addFeatures([fcand])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        EALauncherDialog.generate_preview(mock_dlg)

        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        cand_row = mock_dlg.all_merged_ea_candidates[0]
        neighbors = cand_row[5]
        # Only contiguous partner 001 should be present; non-contiguous 002 must NOT be included
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0][0], "01701001001")
        self.assertNotIn("01701001002", [n[0] for n in neighbors])

    def test_merge_preview_no_contiguous_neighbor_under_threshold_disables_dropdown(self):
        """Verify that when contiguous neighbors exceed threshold, non-contiguous same-barangay EAs are NOT used as fallback."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 300
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 300
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/test"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"

        # 1. Previous EA layer:
        # - Contiguous partner 001 (100 HH + candidate 250 HH = 350 > 300 threshold -> EXCLUDED)
        # - Distant partner 002 (40 HH + candidate 250 HH = 290 <= 300 threshold -> must NOT be used as fallback)
        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        f_contig = QgsFeature(prev_ea_layer.fields())
        f_contig.setAttributes(["01701001001", "01701001", "Poblacion", 100.0])
        f_contig.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))

        f_distant = QgsFeature(prev_ea_layer.fields())
        f_distant.setAttributes(["01701001002", "01701001", "Poblacion", 40.0])
        f_distant.setGeometry(QgsGeometry.fromRect(QgsRectangle(20, 20, 21, 21)))
        pr.addFeatures([f_contig, f_distant])

        # Candidate with 250 HH at (0, 0, 1, 1)
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        fcand = QgsFeature(merge_ea_layer.fields())
        fcand.setAttributes(["01701001099", "01701001", "Poblacion", 250.0])
        fcand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        mpr.addFeatures([fcand])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        EALauncherDialog.generate_preview(mock_dlg)

        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        cand_row = mock_dlg.all_merged_ea_candidates[0]
        self.assertEqual(cand_row[5], [])  # No eligible contiguous partners!

        # Render into preview table
        mock_dlg.current_theme = "light"
        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        EALauncherDialog._populate_table_rows(mock_dlg, table, mock_dlg.all_merged_ea_candidates, is_delineation=False)

        combo = table.cellWidget(0, 5)
        self.assertEqual(combo.count(), 0)
        self.assertFalse(combo.isEnabled())
        self.assertEqual(table.item(0, 6).text(), "—")
        btn = table.cellWidget(0, 7)
        self.assertFalse(btn.isEnabled())

    def test_merge_individual_row_rejects_non_contiguous(self):
        """Verify that _merge_individual_row prevents merging if features are non-contiguous."""
        prev_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EA", "memory")
        pr = prev_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_layer.updateFields()

        # Partner EA at distant location (10, 10, 11, 11)
        p_feat = QgsFeature(prev_layer.fields())
        p_feat.setAttributes(["01701001002", "01701001", "Poblacion", 50.0])
        p_feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(10, 10, 11, 11)))

        # Candidate EA at (0, 0, 1, 1)
        c_feat = QgsFeature(prev_layer.fields())
        c_feat.setAttributes(["01701001099", "01701001", "Poblacion", 45.0])
        c_feat.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        pr.addFeatures([p_feat, c_feat])

        mock_dlg = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.merge_bldg_combo = MagicMock()
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._safe_get_layer = lambda combo: prev_layer

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 45.0, "Initiator", [("01701001002", 50.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)
        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        with patch("references.create_enumeration_area.dialog.QMessageBox.warning") as mock_warn:
            EALauncherDialog._merge_individual_row(
                mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 45.0, partner_combo, table, btn_merge
            )
            mock_warn.assert_called_once()
            self.assertIn("not contiguous", mock_warn.call_args[0][2])

    def test_merge_preview_dropdown_displays_geocode_instead_of_6digit_ean(self):
        """Verify that the merge partner dropdown displays the full geocode value instead of 6-digit EAN code."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 99
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 300
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/test"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"

        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        # Partner EA with 6-digit EAN 002000 and 14-digit geocode 01728001002000
        f_partner = QgsFeature(prev_ea_layer.fields())
        f_partner.setAttributes(["002000", "01728001002000", "San Pedro", 75.0])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        pr.addFeatures([f_partner])

        # Candidate EA in Merge EA layer
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        f_cand = QgsFeature(merge_ea_layer.fields())
        f_cand.setAttributes(["001000", "01728001001000", "San Pedro", 50.0])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        mpr.addFeatures([f_cand])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        EALauncherDialog.generate_preview(mock_dlg)

        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        cand_row = mock_dlg.all_merged_ea_candidates[0]
        neighbors = cand_row[5]
        self.assertEqual(len(neighbors), 1)
        # Verify partner geocode value is stored rather than 6-digit EAN
        self.assertEqual(neighbors[0][0], "01728001002000")
        self.assertNotEqual(neighbors[0][0], "002000")

        # Verify populated dropdown shows geocode value
        mock_dlg.current_theme = "light"
        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        EALauncherDialog._populate_table_rows(mock_dlg, table, mock_dlg.all_merged_ea_candidates, is_delineation=False)
        combo = table.cellWidget(0, 5)
        self.assertEqual(combo.currentText(), "01728001002000")
        self.assertNotEqual(combo.currentText(), "002000")

    def test_merge_preview_strictly_excludes_nearby_non_touching_eas(self):
        """Verify that polygons separated by micro-gap (e.g. across a road) are strictly excluded because they do not touch."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 99
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 300
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/test"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"

        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        # Partner 1: strictly touching candidate at boundary x=1 (x from 1 to 2)
        f_touching = QgsFeature(prev_ea_layer.fields())
        f_touching.setAttributes(["002", "017280010002", "Poblacion", 60.0])
        f_touching.setGeometry(QgsGeometry.fromRect(QgsRectangle(1.0, 0.0, 2.0, 1.0)))

        # Partner 2: across street / separated by 0.00005 deg gap (x from 1.00005 to 2.00005), does NOT touch
        f_non_touching = QgsFeature(prev_ea_layer.fields())
        f_non_touching.setAttributes(["003", "017280010003", "Poblacion", 60.0])
        f_non_touching.setGeometry(QgsGeometry.fromRect(QgsRectangle(1.00005, 0.0, 2.00005, 1.0)))

        pr.addFeatures([f_touching, f_non_touching])

        # Candidate at x=0..1
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        fcand = QgsFeature(merge_ea_layer.fields())
        fcand.setAttributes(["001", "017280010001", "Poblacion", 50.0])
        fcand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0.0, 0.0, 1.0, 1.0)))
        mpr.addFeatures([fcand])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        EALauncherDialog.generate_preview(mock_dlg)

        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        cand_row = mock_dlg.all_merged_ea_candidates[0]
        neighbors = cand_row[5]
        # Only strictly touching partner 002 should be in dropdown; non-touching 003 must be excluded
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0][0], "017280010002")
        self.assertNotIn("017280010003", [n[0] for n in neighbors])

    def test_individual_merge_row_triggers_refresh_merge_preview(self):
        """Verify clicking Merge invokes refresh_merge_preview to update Merge Preview table and candidates."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg._find_feature_in_layer = EALauncherDialog._find_feature_in_layer
        mock_dlg._extract_5digit_geocode.return_value = "01701"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.merge_log_console = QTextEdit()
        mock_dlg.refresh_merge_preview = MagicMock()

        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs_Refresh", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        f_partner = QgsFeature(prev_ea_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001", "Poblacion", 80.0])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        pr.addFeatures([f_partner])

        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA_Refresh", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        f_cand = QgsFeature(merge_ea_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001", "Poblacion", 40.0])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        mpr.addFeatures([f_cand])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01701001099", "EA 99", "Poblacion", 40.0, "Initiator (<= 99 HH)", [("01701001001", 80.0)])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)

        partner_combo = table.cellWidget(0, 5)
        btn_merge = table.cellWidget(0, 7)

        # Trigger merge
        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
        )

        # Ensure refresh_merge_preview was invoked
        mock_dlg.refresh_merge_preview.assert_called_once()

    def test_populate_table_rows_merged_status_grayed_out(self):
        """Verify that rows with role 'Merged ✓' are grayed out with light gray styling."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.current_theme = "light"

        table = EALauncherDialog._create_preview_table(mock_dlg, include_merge_partner=True)
        candidates = [
            ("01715009003000", "EA 003000", "Digdigon", 179.0, "Merged ✓", [])
        ]
        EALauncherDialog._populate_table_rows(mock_dlg, table, candidates, is_delineation=False)

        self.assertEqual(table.rowCount(), 1)
        role_item = table.item(0, 4)
        self.assertEqual(role_item.text(), "Merged ✓")

        # Verify cell background is light gray (#f2f4f7)
        bg = role_item.background().color().name().lower()
        self.assertEqual(bg, "#f2f4f7")

        # Verify partner combo is disabled and grayed out
        partner_combo = table.cellWidget(0, 5)
        self.assertFalse(partner_combo.isEnabled())
        self.assertEqual(partner_combo.count(), 0)

        # Verify action button is enabled Unmerge button, styled amber with text 'Unmerge'
        btn_merge = table.cellWidget(0, 7)
        self.assertTrue(btn_merge.isEnabled())
        self.assertEqual(btn_merge.text(), "Unmerge")
        self.assertIn("#d97706", btn_merge.styleSheet())

    def test_merge_preview_excludes_unmerged_candidate_above_min_hh(self):
        """Verify that in Merge Preview, unmerged EAs with household count > min_hh do not appear."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 99
        mock_dlg.merge_min_hh_spin = MagicMock()
        mock_dlg.merge_min_hh_spin.value.return_value = 99
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 300
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/test"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"

        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        # Merge EA layer with 2 features:
        # 1) Unmerged candidate with 150 HH (> 99 min_hh threshold) -> must NOT appear!
        # 2) Unmerged candidate with 50 HH (<= 99 min_hh threshold) -> MUST appear!
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        merge_ea_layer.updateFields()

        f_over = QgsFeature(merge_ea_layer.fields())
        f_over.setAttributes(["01701001001", "01701001", "Poblacion", 150.0])
        f_over.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        f_under = QgsFeature(merge_ea_layer.fields())
        f_under.setAttributes(["01701001002", "01701001", "Poblacion", 50.0])
        f_under.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))
        mpr.addFeatures([f_over, f_under])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        EALauncherDialog.generate_preview(mock_dlg)

        # Only the feature with 50 HH (<= 99) should appear in Merge Preview!
        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        self.assertEqual(mock_dlg.all_merged_ea_candidates[0][0], "01701001002")

    def test_merge_preview_retains_merged_candidate_above_min_hh(self):
        """Verify that in Merge Preview, if an EA has been merged (via ea_type or session) and hh > min_hh, it is retained."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg._session_merged_eans = {"01701001001"}
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 99
        mock_dlg.merge_min_hh_spin = MagicMock()
        mock_dlg.merge_min_hh_spin.value.return_value = 99
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 300
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/test"
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"

        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        # Merge EA layer with 1 merged feature with 180 HH (> 99 min_hh):
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("ea_type", QVariant.String),
            QgsField("remarks", QVariant.String)
        ])
        merge_ea_layer.updateFields()

        f_merged = QgsFeature(merge_ea_layer.fields())
        f_merged.setAttributes(["01701001001", "01701001", "Poblacion", 180.0, "MERGED", "Merged: 001 + 002"])
        f_merged.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))
        mpr.addFeatures([f_merged])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        EALauncherDialog.generate_preview(mock_dlg)

        # Must be retained even though 180 > 99!
        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 1)
        row = mock_dlg.all_merged_ea_candidates[0]
        self.assertEqual(row[0], "01701001001")
        self.assertEqual(row[3], 180.0)
        self.assertEqual(row[4], "Merged ✓")

    def test_generate_preview_filters_already_merged_partners(self):
        """Verify that an EA already merged is excluded from the partner dropdowns of other candidates."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.all_delineation_candidates = []
        mock_dlg.all_merge_candidates = []
        mock_dlg.all_merged_ea_candidates = []
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.min_hh_spin.value.return_value = 99
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.max_hh_spin.value.return_value = 350
        mock_dlg.merge_max_hh_spin = MagicMock()
        mock_dlg.merge_max_hh_spin.value.return_value = 350
        mock_dlg.merge_min_hh_spin = MagicMock()
        mock_dlg.merge_min_hh_spin.value.return_value = 99
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.kpi_merged_ea_val = MagicMock()
        mock_dlg.filter_previews = MagicMock()
        mock_dlg._get_ea_name = lambda feat, ean, fields: f"EA {ean}"
        mock_dlg._extract_5digit_geocode = lambda: "01701"

        # Previous EA layer with Partner 1 (touches both Candidate A and Candidate B)
        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double)
        ])
        prev_ea_layer.updateFields()

        # Partner 1: x: [0, 1]
        p1 = QgsFeature(prev_ea_layer.fields())
        p1.setAttributes(["01701001001", "01701001", "Poblacion", 50.0])
        p1.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        # Candidate A: x: [1, 2] (touches Partner 1)
        ca = QgsFeature(prev_ea_layer.fields())
        ca.setAttributes(["01701001002", "01701001", "Poblacion", 30.0])
        ca.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))

        # Candidate B: x: [-1, 0] (touches Partner 1)
        cb = QgsFeature(prev_ea_layer.fields())
        cb.setAttributes(["01701001003", "01701001", "Poblacion", 40.0])
        cb.setGeometry(QgsGeometry.fromRect(QgsRectangle(-1, 0, 0, 1)))

        pr.addFeatures([p1, ca, cb])

        # Candidate layer in merge_ea_layer
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Merge_EA", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("ea_type", QVariant.String),
            QgsField("remarks", QVariant.String)
        ])
        merge_ea_layer.updateFields()

        feat_ca = QgsFeature(merge_ea_layer.fields())
        feat_ca.setAttributes(["01701001002", "01701001", "Poblacion", 30.0, "RETAINED", ""])
        feat_ca.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))

        feat_cb = QgsFeature(merge_ea_layer.fields())
        feat_cb.setAttributes(["01701001003", "01701001", "Poblacion", 40.0, "RETAINED", ""])
        feat_cb.setGeometry(QgsGeometry.fromRect(QgsRectangle(-1, 0, 0, 1)))

        mpr.addFeatures([feat_ca, feat_cb])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )

        # 1. When Partner 1 is NOT merged, both Candidate A and Candidate B see Partner 1
        mock_dlg._session_merged_eans = set()
        EALauncherDialog.generate_preview(mock_dlg)
        self.assertEqual(len(mock_dlg.all_merged_ea_candidates), 2)
        cand_a_entry = next(c for c in mock_dlg.all_merged_ea_candidates if c[0] == "01701001002")
        cand_b_entry = next(c for c in mock_dlg.all_merged_ea_candidates if c[0] == "01701001003")
        self.assertIn("01701001001", [n[0] for n in cand_a_entry[5]])
        self.assertIn("01701001001", [n[0] for n in cand_b_entry[5]])

        # 2. When Partner 1 IS merged (e.g. into Candidate A), Partner 1 MUST NOT appear for Candidate B!
        mock_dlg.all_merged_ea_candidates.clear()
        mock_dlg._session_merged_eans = {"01701001001", "01701001002"}
        EALauncherDialog.generate_preview(mock_dlg)

        cand_b_after = next(c for c in mock_dlg.all_merged_ea_candidates if c[0] == "01701001003")
        # Partner 1 must be filtered out!
        self.assertNotIn("01701001001", [n[0] for n in cand_b_after[5]])
        self.assertEqual(len(cand_b_after[5]), 0)

    def test_merge_individual_row_rejects_already_merged_candidate(self):
        """Verify that _merge_individual_row rejects merging if candidate is already merged."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg._session_merged_eans = {"01701001099"}
        mock_dlg.merge_log_console = MagicMock()

        table = QTableWidget(1, 8)
        partner_combo = QComboBox()
        partner_combo.addItem("01701001001")
        btn_merge = QPushButton("Merge")

        with patch("references.create_enumeration_area.dialog.QMessageBox.warning") as mock_warn:
            EALauncherDialog._merge_individual_row(
                mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
            )
            mock_warn.assert_called_once()
            self.assertIn("already been merged", mock_warn.call_args[0][2])

    def test_merge_individual_row_rejects_already_merged_partner(self):
        """Verify that _merge_individual_row rejects merging if chosen partner is already merged."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg._session_merged_eans = {"01701001001"}
        mock_dlg.merge_log_console = MagicMock()

        table = QTableWidget(1, 8)
        partner_combo = QComboBox()
        partner_combo.addItem("01701001001")
        btn_merge = QPushButton("Merge")

        with patch("references.create_enumeration_area.dialog.QMessageBox.warning") as mock_warn:
            EALauncherDialog._merge_individual_row(
                mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
            )
            mock_warn.assert_called_once()
            self.assertIn("already been merged", mock_warn.call_args[0][2])

    def test_unmerge_individual_row_restores_features_and_enables_remerge(self):
        """Verify that _unmerge_individual_row restores constituent EA features and clears session merged tracking."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.merge_log_console = MagicMock()
        mock_dlg._session_merged_eans = set()
        mock_dlg._merge_history = {}
        mock_dlg.refresh_merge_preview = MagicMock()
        mock_dlg._extract_5digit_geocode = lambda: "01701"
        mock_dlg.output_folder_widget = MagicMock()
        mock_dlg.output_folder_widget.filePath.return_value = ""
        mock_dlg.merge_output_folder_widget = MagicMock()
        mock_dlg.merge_output_folder_widget.filePath.return_value = ""
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.merge_prev_ea_combo = MagicMock()
        mock_dlg.merge_ea_combo = MagicMock()
        mock_dlg.bldg_combo = None
        mock_dlg.merge_bldg_combo = None
        mock_dlg.iface = None

        # 1. Setup Previous EA layer with two features
        prev_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "Prev_EAs", "memory")
        pr = prev_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("geocode", QVariant.String),
            QgsField("barangay", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
            QgsField("new_ean", QVariant.String),
            QgsField("ea_type", QVariant.String),
            QgsField("remarks", QVariant.String),
        ])
        prev_ea_layer.updateFields()

        f_cand = QgsFeature(prev_ea_layer.fields())
        f_cand.setAttributes(["01701001099", "01701001", "Poblacion", 40.0, 30, "01701001099", "RETAINED", ""])
        f_cand.setGeometry(QgsGeometry.fromRect(QgsRectangle(0, 0, 1, 1)))

        f_partner = QgsFeature(prev_ea_layer.fields())
        f_partner.setAttributes(["01701001001", "01701001", "Poblacion", 80.0, 60, "01701001001", "RETAINED", ""])
        f_partner.setGeometry(QgsGeometry.fromRect(QgsRectangle(1, 0, 2, 1)))

        pr.addFeatures([f_cand, f_partner])

        # 2. Setup Merge EA layer
        merge_ea_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "01701_merge_ea", "memory")
        mpr = merge_ea_layer.dataProvider()
        mpr.addAttributes(prev_ea_layer.fields().toList())
        merge_ea_layer.updateFields()
        mpr.addFeatures([f_cand, f_partner])

        mock_dlg._safe_get_layer.side_effect = lambda combo: (
            prev_ea_layer if combo in (mock_dlg.prev_ea_combo, getattr(mock_dlg, 'merge_prev_ea_combo', None))
            else merge_ea_layer
        )
        mock_dlg._find_feature_in_layer = lambda lyr, target: EALauncherDialog._find_feature_in_layer(lyr, target)

        # 3. Perform merge first
        table = QTableWidget(1, 8)
        partner_combo = QComboBox()
        partner_combo.addItem("01701001001")
        btn_merge = QPushButton("Merge")
        table.setCellWidget(0, 5, partner_combo)
        table.setCellWidget(0, 7, btn_merge)

        EALauncherDialog._merge_individual_row(
            mock_dlg, 0, "01701001099", "EA 99", "Poblacion", 40.0, partner_combo, table, btn_merge
        )

        merged_layers = QgsProject.instance().mapLayersByName("01701_merged_ea2026")
        self.assertTrue(len(merged_layers) >= 1)
        merged_lyr = merged_layers[0]
        self.assertEqual(merged_lyr.featureCount(), 1)
        self.assertIn("01701001099", mock_dlg._session_merged_eans)
        self.assertIn("01701001001", mock_dlg._session_merged_eans)

        # 4. Now perform unmerge on candidate
        EALauncherDialog._unmerge_individual_row(mock_dlg, 0, "01701001099")

        # Merged layer should now have 2 restored features instead of 1 merged feature
        self.assertEqual(merged_lyr.featureCount(), 2)
        eans_in_layer = [f["ean"] for f in merged_lyr.getFeatures()]
        self.assertIn("01701001099", eans_in_layer)
        self.assertIn("01701001001", eans_in_layer)

        # All restored features must have ea_type RETAINED
        for f in merged_lyr.getFeatures():
            self.assertEqual(f["ea_type"], "RETAINED")

        # Session tracking should no longer contain candidate or partner
        self.assertNotIn("01701001099", mock_dlg._session_merged_eans)
        self.assertNotIn("01701001001", mock_dlg._session_merged_eans)
        mock_dlg.refresh_merge_preview.assert_called()

    def test_reconcile_session_merged_eans(self):
        """Verify that _reconcile_session_merged_eans prunes stale EANs not in target layer."""
        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg._session_merged_eans = {"01701001001", "01701001099", "01701001888"}

        target_layer = QgsVectorLayer("Polygon?crs=epsg:4326", "01701_merged_ea2026", "memory")
        pr = target_layer.dataProvider()
        pr.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("ea_type", QVariant.String),
            QgsField("remarks", QVariant.String)
        ])
        target_layer.updateFields()

        # Only 01701001001 and 01701001099 are merged in layer; 01701001888 is stale
        f = QgsFeature(target_layer.fields())
        f.setAttributes(["01701001001", "MERGED", "Merged: 01701001099 + 01701001001"])
        pr.addFeatures([f])

        EALauncherDialog._reconcile_session_merged_eans(mock_dlg, target_layer)

        self.assertIn("01701001001", mock_dlg._session_merged_eans)
        self.assertIn("01701001099", mock_dlg._session_merged_eans)
        self.assertNotIn("01701001888", mock_dlg._session_merged_eans)


if __name__ == "__main__":
    unittest.main()

