# -*- coding: utf-8 -*-
"""
Unit test module for Split EA Dialog functionality.
Verifies dialog initialization, layer auto-detection, line extension math,
split execution pipeline, and in-place layer update with hh_count & bldg_count calculations.
"""

import unittest
from unittest.mock import MagicMock, patch
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, MockGenericClass

setup_qgis_mock_if_needed()

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsWkbTypes,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant
from references.create_enumeration_area.helpers.constants import create_qgs_field


class TestSplitEADialog(unittest.TestCase):
    """Test suite for SplitEADialog."""

    def test_split_ea_btn_exists_in_dialog(self):
        """Verify that split_ea_btn and _open_split_ea_dialog exist on EALauncherDialog."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        self.assertTrue(hasattr(EALauncherDialog, "_open_split_ea_dialog"))

    def test_dialog_init_ui(self):
        """Verify SplitEADialog initializes with all expected UI components."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        dlg = SplitEADialog(default_output_dir="C:/test_out", default_geocode="01728")
        self.assertIsNotNone(dlg.poly_combo)
        self.assertIsNotNone(dlg.line_combo)
        self.assertIsNotNone(dlg.bldg_combo)
        self.assertIsNotNone(dlg.tolerance_spin)
        self.assertIsNotNone(dlg.progress_bar)
        self.assertIsNotNone(dlg.log_console)
        self.assertIsNotNone(dlg.run_btn)
        self.assertIsNotNone(dlg.close_btn)
        self.assertEqual(dlg.default_geocode, "01728")
        self.assertEqual(dlg.default_output_dir, "C:/test_out")

    def test_extend_line_endpoints(self):
        """Verify line extension math extends coordinates outwards."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        dlg = SplitEADialog()
        pts = [QgsPointXY(0, 0), QgsPointXY(10, 0)]
        line_geom = QgsGeometry.fromPolylineXY(pts)

        # Extend by 2 meters
        ext_geom = dlg._extend_line_endpoints(line_geom, 2.0)
        ext_pts = ext_geom.asPolyline()

        self.assertEqual(len(ext_pts), 2)
        # p0 should be extended from (0,0) away from (10,0) -> (-2, 0)
        self.assertAlmostEqual(ext_pts[0].x(), -2.0, places=4)
        self.assertAlmostEqual(ext_pts[0].y(), 0.0, places=4)
        # pn should be extended from (10,0) away from (0,0) -> (12, 0)
        self.assertAlmostEqual(ext_pts[1].x(), 12.0, places=4)
        self.assertAlmostEqual(ext_pts[1].y(), 0.0, places=4)

    def test_auto_detect_layers(self):
        """Verify auto-detection identifies delineated_ea polygon, eadel_update line, and building points."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "01728_delineated_ea2026", "memory")
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "01728_eadel_update", "memory")
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "01728_bldgpts", "memory")

        QgsProject.instance().addMapLayer(poly_lyr)
        QgsProject.instance().addMapLayer(line_lyr)
        QgsProject.instance().addMapLayer(bldg_lyr)

        try:
            dlg = SplitEADialog()
            curr_poly = dlg.poly_combo.currentLayer()
            if hasattr(curr_poly, "name") and not isinstance(curr_poly, MockGenericClass):
                self.assertEqual(curr_poly.name(), "01728_delineated_ea2026")
            curr_line = dlg.line_combo.currentLayer()
            if hasattr(curr_line, "name") and not isinstance(curr_line, MockGenericClass):
                self.assertEqual(curr_line.name(), "01728_eadel_update")
            curr_bldg = dlg.bldg_combo.currentLayer()
            if hasattr(curr_bldg, "name") and not isinstance(curr_bldg, MockGenericClass):
                self.assertEqual(curr_bldg.name(), "01728_bldgpts")
        finally:
            QgsProject.instance().removeMapLayer(poly_lyr.id())
            QgsProject.instance().removeMapLayer(line_lyr.id())
            QgsProject.instance().removeMapLayer(bldg_lyr.id())

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_run_split_recalculates_hh_and_bldg_counts(self, mock_proc_run):
        """Verify run_split calculates hh_count (from est_hhcount) and bldg_count per split polygon."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        # Create input polygon layer (1 square polygon)
        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hhcount", QVariant.Int),
            QgsField("bldgcount", QVariant.Int),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
        ])
        poly_lyr.updateFields()

        poly_feat = QgsFeature(poly_lyr.fields())
        poly_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly_feat.setAttribute("ean", "001000")
        poly_feat.setAttribute("hhcount", 350)
        poly_feat.setAttribute("bldgcount", 50)
        poly_feat.setAttribute("hh_count", 0)
        poly_feat.setAttribute("bldg_count", 0)
        dp_poly.addFeatures([poly_feat])
        poly_lyr.updateExtents()

        # Create input cut lines layer (1 line bisecting the polygon at x=5)
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        line_feat = QgsFeature()
        line_feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        dp_line.addFeatures([line_feat])
        line_lyr.updateExtents()

        # Create building point layer:
        # Part 1 (x: 0..5): 2 buildings with est_hhcount 2.5 and 2.0 -> total HH = 4.5 -> ceil to 5, bldg = 2
        # Part 2 (x: 5..10): 1 building with est_hhcount 3.2 -> total HH = 3.2 -> ceil to 4, bldg = 1
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "bldg_points", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([QgsField("est_hhcount", QVariant.Double)])
        bldg_lyr.updateFields()

        b1 = QgsFeature(bldg_lyr.fields())
        b1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))
        b1.setAttribute("est_hhcount", 2.5)

        b2 = QgsFeature(bldg_lyr.fields())
        b2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(3, 3)))
        b2.setAttribute("est_hhcount", 2.0)

        b3 = QgsFeature(bldg_lyr.fields())
        b3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(8, 8)))
        b3.setAttribute("est_hhcount", 3.2)

        dp_bldg.addFeatures([b1, b2, b3])
        bldg_lyr.updateExtents()

        # Create mock split output layer (2 split polygon parts)
        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()
        dp_split.addAttributes([QgsField("hh_count", QVariant.Int), QgsField("bldg_count", QVariant.Int)])
        split_lyr.updateFields()

        f1 = QgsFeature(split_lyr.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        f2 = QgsFeature(split_lyr.fields())
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))
        dp_split.addFeatures([f1, f2])
        split_lyr.updateExtents()

        def side_effect(alg_name, params):
            if alg_name == "native:splitwithlines":
                return {"OUTPUT": split_lyr}
            elif alg_name == "native:multiparttosingleparts":
                return {"OUTPUT": split_lyr}
            return {"OUTPUT": split_lyr}

        mock_proc_run.side_effect = side_effect

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        # Check features in poly_lyr
        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 2)

        # Baseline fields hhcount and bldgcount MUST remain preserved (350 and 50)
        # And ea_type MUST be set to DELINEATED for split features
        for feat in updated_features:
            self.assertEqual(feat.attribute("hhcount"), 350)
            self.assertEqual(feat.attribute("bldgcount"), 50)
            self.assertEqual(feat.attribute("ea_type"), "DELINEATED")

        # Part 1 (x: 0..5, highest HH=5): new_ean="001000", bldg_count=2, hh_count=5
        # Part 2 (x: 5..10, 2nd highest HH=4): new_ean="002001", bldg_count=1, hh_count=4 (next seq 2 in bgy, mother 001)
        counts_and_ean = [
            (f.attribute("bldg_count"), f.attribute("hh_count"), f.attribute("new_ean"))
            for f in updated_features
        ]
        self.assertIn((2, 5, "001000"), counts_and_ean)
        self.assertIn((1, 4, "002001"), counts_and_ean)

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_split_rejected_if_hh_count_falls_below_minimum_threshold(self, mock_proc_run):
        """Verify split is strictly rejected and parent EA preserved whole when sub-EA falls below min_hh threshold."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hhcount", QVariant.Int),
            QgsField("bldgcount", QVariant.Int),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
        ])
        poly_lyr.updateFields()

        poly_feat = QgsFeature(poly_lyr.fields())
        poly_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly_feat.setAttribute("ean", "001000")
        poly_feat.setAttribute("hhcount", 350)
        poly_feat.setAttribute("bldgcount", 50)
        poly_feat.setAttribute("hh_count", 0)
        poly_feat.setAttribute("bldg_count", 0)
        dp_poly.addFeatures([poly_feat])
        poly_lyr.updateExtents()

        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        line_feat = QgsFeature()
        line_feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        dp_line.addFeatures([line_feat])
        line_lyr.updateExtents()

        # Buildings: Part 1 has 5 HH, Part 2 has 4 HH (total parent HH = 9)
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "bldg_points", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([QgsField("est_hhcount", QVariant.Double)])
        bldg_lyr.updateFields()

        b1 = QgsFeature(bldg_lyr.fields())
        b1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))
        b1.setAttribute("est_hhcount", 5.0)

        b2 = QgsFeature(bldg_lyr.fields())
        b2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(8, 8)))
        b2.setAttribute("est_hhcount", 4.0)

        dp_bldg.addFeatures([b1, b2])
        bldg_lyr.updateExtents()

        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()
        dp_split.addAttributes([QgsField("hh_count", QVariant.Int), QgsField("bldg_count", QVariant.Int)])
        split_lyr.updateFields()

        f1 = QgsFeature(split_lyr.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        f2 = QgsFeature(split_lyr.fields())
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))
        dp_split.addFeatures([f1, f2])
        split_lyr.updateExtents()

        mock_proc_run.return_value = {"OUTPUT": split_lyr}

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        # Threshold is set to 10 (parts 5 and 4 are < 10 -> split is rejected, parent EA preserved whole)
        dlg.min_hh_spin.value = MagicMock(return_value=10)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        # Check features in poly_lyr -> should be preserved whole as exactly 1 feature
        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 1)
        feat = updated_features[0]
        self.assertEqual(feat.attribute("new_ean"), "001000")
        self.assertEqual(feat.attribute("ea_type"), "RETAINED")
        self.assertEqual(feat.attribute("hh_count"), 9)
        self.assertEqual(feat.attribute("bldg_count"), 2)

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_split_accepted_when_all_sub_eas_meet_minimum_threshold(self, mock_proc_run):
        """Verify split succeeds strictly along eadel_update lines when all sub-EAs meet or exceed min_hh threshold."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hhcount", QVariant.Int),
            QgsField("bldgcount", QVariant.Int),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
        ])
        poly_lyr.updateFields()

        poly_feat = QgsFeature(poly_lyr.fields())
        poly_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly_feat.setAttribute("ean", "001000")
        poly_feat.setAttribute("hhcount", 300)
        poly_feat.setAttribute("bldgcount", 50)
        dp_poly.addFeatures([poly_feat])
        poly_lyr.updateExtents()

        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        line_feat = QgsFeature()
        line_feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        dp_line.addFeatures([line_feat])
        line_lyr.updateExtents()

        # Buildings: Part 1 has 150 HH, Part 2 has 120 HH
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "bldg_points", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([QgsField("est_hhcount", QVariant.Double)])
        bldg_lyr.updateFields()

        b1 = QgsFeature(bldg_lyr.fields())
        b1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))
        b1.setAttribute("est_hhcount", 150.0)

        b2 = QgsFeature(bldg_lyr.fields())
        b2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(8, 8)))
        b2.setAttribute("est_hhcount", 120.0)

        dp_bldg.addFeatures([b1, b2])
        bldg_lyr.updateExtents()

        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()
        dp_split.addAttributes([QgsField("hh_count", QVariant.Int), QgsField("bldg_count", QVariant.Int)])
        split_lyr.updateFields()

        f1 = QgsFeature(split_lyr.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        f2 = QgsFeature(split_lyr.fields())
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))
        dp_split.addFeatures([f1, f2])
        split_lyr.updateExtents()

        mock_proc_run.return_value = {"OUTPUT": split_lyr}

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=99)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        # Both parts (150 and 120) >= 99 -> split succeeds into 2 DELINEATED features
        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 2)
        for f in updated_features:
            self.assertEqual(f.attribute("ea_type"), "DELINEATED")
            self.assertGreaterEqual(f.attribute("hh_count"), 99)

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_split_rejected_upfront_when_parent_hh_less_than_twice_min_hh(self, mock_proc_run):
        """Verify split is rejected upfront when parent EA total households < 2 * min_hh_threshold."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hhcount", QVariant.Int),
            QgsField("bldgcount", QVariant.Int),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
        ])
        poly_lyr.updateFields()

        poly_feat = QgsFeature(poly_lyr.fields())
        poly_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly_feat.setAttribute("ean", "001000")
        poly_feat.setAttribute("hhcount", 150)
        poly_feat.setAttribute("bldgcount", 20)
        dp_poly.addFeatures([poly_feat])
        poly_lyr.updateExtents()

        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        line_feat = QgsFeature()
        line_feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        dp_line.addFeatures([line_feat])
        line_lyr.updateExtents()

        # Buildings: 1 building point with 150 HH (< 2 * 99 = 198 HH)
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "bldg_points", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([QgsField("est_hhcount", QVariant.Double)])
        bldg_lyr.updateFields()

        b1 = QgsFeature(bldg_lyr.fields())
        b1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(5, 5)))
        b1.setAttribute("est_hhcount", 150.0)
        dp_bldg.addFeatures([b1])
        bldg_lyr.updateExtents()

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=99)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        # Split should be rejected upfront without calling processing.run split
        mock_proc_run.assert_not_called()
        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 1)
        feat = updated_features[0]
        self.assertEqual(feat.attribute("new_ean"), "001000")
        self.assertEqual(feat.attribute("ea_type"), "RETAINED")
        self.assertEqual(feat.attribute("hh_count"), 150)

    def test_extract_parent_code_and_prefix_formats(self):
        """Verify _extract_parent_code_and_prefix standardizes ean/code to 6-digit code and 3-digit prefix."""
        from references.create_enumeration_area.split_dialog import SplitEADialog
        from qgis.core import QgsFields

        dlg = SplitEADialog()
        fields1 = QgsFields()
        fields1.append(QgsField("ean", QVariant.String))

        f1 = QgsFeature(fields1)
        f1.setAttribute("ean", "002000")
        self.assertEqual(dlg._extract_parent_code_and_prefix(f1, f1.fields()), ("002000", "002"))

        f2 = QgsFeature(fields1)
        f2.setAttribute("ean", "003")
        self.assertEqual(dlg._extract_parent_code_and_prefix(f2, f2.fields()), ("003000", "003"))

        fields2 = QgsFields()
        fields2.append(QgsField("code", QVariant.String))
        f3 = QgsFeature(fields2)
        f3.setAttribute("code", "01737004001")
        self.assertEqual(dlg._extract_parent_code_and_prefix(f3, f3.fields()), ("004001", "004"))

        # 14-digit PSGC EA geocode extracts last 6 digits
        fields3 = QgsFields()
        fields3.append(QgsField("geocode", QVariant.String))
        f4 = QgsFeature(fields3)
        f4.setAttribute("geocode", "01728001002000")
        self.assertEqual(dlg._extract_parent_code_and_prefix(f4, f4.fields()), ("002000", "002"))

        # Priority: geocode prioritized over code/other fields
        fields4 = QgsFields()
        fields4.append(QgsField("code", QVariant.String))
        fields4.append(QgsField("geocode", QVariant.String))
        f5 = QgsFeature(fields4)
        f5.setAttribute("code", "01728001")  # barangay code in code column
        f5.setAttribute("geocode", "01728001002000")
        self.assertEqual(dlg._extract_parent_code_and_prefix(f5, f5.fields()), ("002000", "002"))

    def test_extend_line_to_traverse_polygon(self):
        """Verify cut line drawn inside polygon is extended to fully traverse outside both boundaries."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        dlg = SplitEADialog()
        # 10x10 polygon (0,0 to 10,10)
        poly_geom = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]])

        # Cut line drawn entirely inside the polygon: from (3, 5) to (7, 5)
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(3, 5), QgsPointXY(7, 5)])

        ext_geom = dlg._extend_line_to_traverse_polygon(line_geom, poly_geom, extend_tol=1.0)
        ext_pts = ext_geom.asPolyline()

        self.assertEqual(len(ext_pts), 2)
        # Start point must be extended outside the left polygon boundary (x < 0)
        self.assertLess(ext_pts[0].x(), 0.0)
        self.assertAlmostEqual(ext_pts[0].y(), 5.0, places=4)

        # End point must be extended outside the right polygon boundary (x > 10)
        self.assertGreater(ext_pts[1].x(), 10.0)
        self.assertAlmostEqual(ext_pts[1].y(), 5.0, places=4)

    def test_extend_line_concave_polygon_no_overshoot(self):
        """Verify cut line in concave C-shaped polygon extends only slightly past the nearest exit and does NOT overshoot other arms."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        dlg = SplitEADialog()
        # C-shaped polygon: top arm y=[6,10], bottom arm y=[0,4], connecting spine x=[0,3], bay for x in (3,10], y in (4,6)
        c_poly = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0),
            QgsPointXY(10, 0),
            QgsPointXY(10, 4),
            QgsPointXY(3, 4),
            QgsPointXY(3, 6),
            QgsPointXY(10, 6),
            QgsPointXY(10, 10),
            QgsPointXY(0, 10),
            QgsPointXY(0, 0),
        ]])

        # Line in top arm at x=5, from y=9 to y=7 pointing downward toward the bay
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(5, 9), QgsPointXY(5, 7)])

        ext_geom = dlg._extend_line_to_traverse_polygon(line_geom, c_poly, extend_tol=0.5)
        ext_pts = ext_geom.asPolyline()

        self.assertEqual(len(ext_pts), 2)
        # Top endpoint (y=9) extends past y=10 by 0.5 -> y=10.5
        self.assertGreater(ext_pts[0].y(), 10.0)

        # Bottom endpoint (y=7) hits top arm boundary at y=6, extends by 0.5 -> y=5.5
        # Crucially, it must NEVER overshoot to y <= 4.0 (the bottom arm)!
        self.assertAlmostEqual(ext_pts[1].x(), 5.0, places=4)
        self.assertAlmostEqual(ext_pts[1].y(), 5.5, places=2)
        self.assertGreater(ext_pts[1].y(), 4.0, "Extended line must NOT penetrate the bottom arm!")

    def test_selection_ui_and_signals(self):
        """Verify layer selection updates UI checkbox labels and enables/disables them."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        f1 = QgsFeature()
        f1.setId(1)
        f2 = QgsFeature()
        f2.setId(2)
        dp_poly.addFeatures([f1, f2])

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg._on_layer_selection_changed()

        self.assertFalse(dlg.poly_selected_chk.isChecked())
        self.assertIn("0 selected", dlg.poly_selected_chk.text())

        # Select feature 1
        poly_lyr.selectByIds([1])
        dlg._update_poly_selection_ui()
        self.assertTrue(dlg.poly_selected_chk.isChecked())
        self.assertIn("1 selected", dlg.poly_selected_chk.text())

        # Deselect
        poly_lyr.removeSelection()
        dlg._update_poly_selection_ui()
        self.assertFalse(dlg.poly_selected_chk.isChecked())
        self.assertIn("0 selected", dlg.poly_selected_chk.text())

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_run_split_with_selected_polygon_only(self, mock_proc_run):
        """Verify that when a single polygon is selected, only that polygon is split while others remain untouched."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        # Polygon layer with 2 features: EA 001000 and EA 002000
        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
            QgsField("ea_type", QVariant.String),
        ])
        poly_lyr.updateFields()

        poly1 = QgsFeature(poly_lyr.fields())
        poly1.setId(1)
        poly1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly1.setAttribute("ean", "001000")
        poly1.setAttribute("hh_count", 300)
        poly1.setAttribute("bldg_count", 30)
        poly1.setAttribute("ea_type", "RETAINED")

        poly2 = QgsFeature(poly_lyr.fields())
        poly2.setId(2)
        poly2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(20, 0), QgsPointXY(30, 0), QgsPointXY(30, 10), QgsPointXY(20, 10), QgsPointXY(20, 0)
        ]]))
        poly2.setAttribute("ean", "002000")
        poly2.setAttribute("hh_count", 400)
        poly2.setAttribute("bldg_count", 40)
        poly2.setAttribute("ea_type", "RETAINED")

        dp_poly.addFeatures([poly1, poly2])
        poly_lyr.updateExtents()

        # Cut line crossing polygon 1 at x=5
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        line_feat = QgsFeature()
        line_feat.setId(1)
        line_feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        dp_line.addFeatures([line_feat])
        line_lyr.updateExtents()

        # Mock split output for polygon 1 (2 split pieces)
        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()
        dp_split.addAttributes([QgsField("hh_count", QVariant.Int), QgsField("bldg_count", QVariant.Int)])
        split_lyr.updateFields()

        f1 = QgsFeature(split_lyr.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        f2 = QgsFeature(split_lyr.fields())
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))
        dp_split.addFeatures([f1, f2])
        split_lyr.updateExtents()

        mock_proc_run.return_value = {"OUTPUT": split_lyr}

        # Select ONLY polygon 1
        poly_lyr.selectByIds([1])

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=None)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.poly_selected_chk.setChecked(True)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        # Total features in poly_lyr should now be 3 (2 from split poly 1 + 1 untouched poly 2)
        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 3)

        # Check that untouched poly 2 is present and retained
        eans = [f.attribute("ean") or f.attribute("new_ean") for f in updated_features]
        self.assertIn("002000", eans)

        # Check types: split pieces are DELINEATED, un-split poly 2 is RETAINED
        types_by_ean = {f.attribute("new_ean"): f.attribute("ea_type") for f in updated_features}
        self.assertEqual(types_by_ean.get("002000"), "RETAINED")
        self.assertEqual(types_by_ean.get("001000"), "DELINEATED")
        self.assertEqual(types_by_ean.get("003001"), "DELINEATED")

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_run_split_with_selected_cut_lines_only(self, mock_proc_run):
        """Verify that when cut lines are selected, only selected cut lines are used for splitting."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
            QgsField("ea_type", QVariant.String),
        ])
        poly_lyr.updateFields()

        poly = QgsFeature(poly_lyr.fields())
        poly.setId(1)
        poly.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly.setAttribute("ean", "001000")
        poly.setAttribute("hh_count", 300)
        poly.setAttribute("bldg_count", 30)
        dp_poly.addFeatures([poly])
        poly_lyr.updateExtents()

        # Two cut lines: line 1 (x=5) and line 2 (y=5)
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        l1 = QgsFeature()
        l1.setId(1)
        l1.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        l2 = QgsFeature()
        l2.setId(2)
        l2.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(-1, 5), QgsPointXY(11, 5)]))
        dp_line.addFeatures([l1, l2])
        line_lyr.updateExtents()

        # Mock split output for split with line 1 only
        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()
        dp_split.addAttributes([QgsField("hh_count", QVariant.Int), QgsField("bldg_count", QVariant.Int)])
        split_lyr.updateFields()

        f1 = QgsFeature(split_lyr.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        f2 = QgsFeature(split_lyr.fields())
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))
        dp_split.addFeatures([f1, f2])
        split_lyr.updateExtents()

        def side_effect(alg_name, params):
            # Verify that single_lines_layer in params has only 1 line feature (line 1)
            lines_input = params.get("LINES")
            if lines_input:
                self.assertEqual(lines_input.featureCount(), 1)
            return {"OUTPUT": split_lyr}

        mock_proc_run.side_effect = side_effect

        # Select line 1 ONLY
        line_lyr.selectByIds([1])

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=None)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.line_selected_chk.setChecked(True)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 2)

    def test_extract_barangay_key_formats(self):
        """Verify _extract_barangay_key standardizes barangay identifiers from attributes."""
        from references.create_enumeration_area.split_dialog import SplitEADialog
        from qgis.core import QgsFields

        dlg = SplitEADialog()
        fields1 = QgsFields()
        fields1.append(QgsField("bgy_code", QVariant.String))

        f1 = QgsFeature(fields1)
        f1.setAttribute("bgy_code", "01728001")
        self.assertEqual(dlg._extract_barangay_key(f1, f1.fields()), "01728001")

        fields2 = QgsFields()
        fields2.append(QgsField("geocode", QVariant.String))
        f2 = QgsFeature(fields2)
        f2.setAttribute("geocode", "01728001002000")
        self.assertEqual(dlg._extract_barangay_key(f2, f2.fields()), "01728001")

        fields3 = QgsFields()
        fields3.append(QgsField("ean", QVariant.String))
        f3 = QgsFeature(fields3)
        f3.setAttribute("ean", "002000")
        self.assertEqual(dlg._extract_barangay_key(f3, f3.fields()), "_ALL_")

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_delineation_numbering_three_eas_split_ea_002000(self, mock_proc_run):
        """Verify sequential numbering: barangay with 001000, 002000, 003000 where 002000 is delineated produces 004002."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
            QgsField("bgy_code", QVariant.String),
        ])
        poly_lyr.updateFields()

        # 3 EAs in Barangay 01728001: 001000, 002000, 003000
        p1 = QgsFeature(poly_lyr.fields())
        p1.setId(1)
        p1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        p1.setAttributes(["001000", 150, 20, "01728001"])

        p2 = QgsFeature(poly_lyr.fields())
        p2.setId(2)
        p2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]]))
        p2.setAttributes(["002000", 350, 50, "01728001"])

        p3 = QgsFeature(poly_lyr.fields())
        p3.setId(3)
        p3.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(20, 0), QgsPointXY(30, 0), QgsPointXY(30, 10), QgsPointXY(20, 10), QgsPointXY(20, 0)
        ]]))
        p3.setAttributes(["003000", 200, 25, "01728001"])
        dp_poly.addFeatures([p1, p2, p3])
        poly_lyr.updateExtents()

        # Cut line dividing p2 (x: 10..20) at x=15
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "cut_lines", "memory")
        dp_line = line_lyr.dataProvider()
        line = QgsFeature()
        line.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(15, -2), QgsPointXY(15, 12)]))
        dp_line.addFeatures([line])
        line_lyr.updateExtents()

        # Mock split output for p2 -> two parts
        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_out", "memory")
        dp_split = split_lyr.dataProvider()
        f_part1 = QgsFeature()
        f_part1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(15, 0), QgsPointXY(15, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]]))
        f_part2 = QgsFeature()
        f_part2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(15, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(15, 10), QgsPointXY(15, 0)
        ]]))
        dp_split.addFeatures([f_part1, f_part2])
        split_lyr.updateExtents()

        mock_proc_run.return_value = {"OUTPUT": split_lyr}

        # Select EA 002000 (ID 2) only
        poly_lyr.selectByIds([2])

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=None)
        dlg.poly_selected_chk.setChecked(True)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        # Verify layer features: total 4 features
        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 4)

        # Map new_ean to ea_type
        eans_and_types = {f.attribute("new_ean"): f.attribute("ea_type") for f in updated_features}

        # Untouched EAs 001000 and 003000 are RETAINED
        self.assertIn("001000", eans_and_types)
        self.assertEqual(eans_and_types["001000"], "RETAINED")
        self.assertIn("003000", eans_and_types)
        self.assertEqual(eans_and_types["003000"], "RETAINED")

        # Delineated sub-EAs from 002000:
        # Part 1 retains mother EA code 002000
        self.assertIn("002000", eans_and_types)
        self.assertEqual(eans_and_types["002000"], "DELINEATED")

        # Part 2 is assigned next sequential in barangay (004) + mother EA prefix (002) = 004002!
        self.assertIn("004002", eans_and_types)
        self.assertEqual(eans_and_types["004002"], "DELINEATED")

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_delineation_numbering_isolated_per_barangay(self, mock_proc_run):
        """Verify sequential numbering is strictly isolated per barangay."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
            QgsField("bgy_code", QVariant.String),
        ])
        poly_lyr.updateFields()

        # Barangay A (01728001) has 3 EAs (001000, 002000, 003000)
        p1 = QgsFeature(poly_lyr.fields())
        p1.setId(1)
        p1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)]]))
        p1.setAttributes(["001000", 100, 10, "BGY_A"])

        p2 = QgsFeature(poly_lyr.fields())
        p2.setId(2)
        p2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(10, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)]]))
        p2.setAttributes(["002000", 350, 30, "BGY_A"])

        p3 = QgsFeature(poly_lyr.fields())
        p3.setId(3)
        p3.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(20, 0), QgsPointXY(30, 0), QgsPointXY(30, 10), QgsPointXY(20, 10), QgsPointXY(20, 0)]]))
        p3.setAttributes(["003000", 150, 15, "BGY_A"])

        # Barangay B (BGY_B) has 2 EAs (001000, 002000)
        p4 = QgsFeature(poly_lyr.fields())
        p4.setId(4)
        p4.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(100, 0), QgsPointXY(110, 0), QgsPointXY(110, 10), QgsPointXY(100, 10), QgsPointXY(100, 0)]]))
        p4.setAttributes(["001000", 400, 40, "BGY_B"])

        p5 = QgsFeature(poly_lyr.fields())
        p5.setId(5)
        p5.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(110, 0), QgsPointXY(120, 0), QgsPointXY(120, 10), QgsPointXY(110, 10), QgsPointXY(110, 0)]]))
        p5.setAttributes(["002000", 200, 20, "BGY_B"])

        dp_poly.addFeatures([p1, p2, p3, p4, p5])
        poly_lyr.updateExtents()

        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "cut_lines", "memory")
        dp_line = line_lyr.dataProvider()
        line1 = QgsFeature()
        line1.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(15, -2), QgsPointXY(15, 12)]))
        line2 = QgsFeature()
        line2.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(105, -2), QgsPointXY(105, 12)]))
        dp_line.addFeatures([line1, line2])
        line_lyr.updateExtents()

        sp_a = QgsVectorLayer("Polygon?crs=epsg:4326", "sp_a", "memory")
        dp_a = sp_a.dataProvider()
        feat_a1 = QgsFeature()
        feat_a1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(10, 0), QgsPointXY(15, 0), QgsPointXY(15, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)]]))
        feat_a2 = QgsFeature()
        feat_a2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(15, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(15, 10), QgsPointXY(15, 0)]]))
        dp_a.addFeatures([feat_a1, feat_a2])

        sp_b = QgsVectorLayer("Polygon?crs=epsg:4326", "sp_b", "memory")
        dp_b = sp_b.dataProvider()
        feat_b1 = QgsFeature()
        feat_b1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(100, 0), QgsPointXY(105, 0), QgsPointXY(105, 10), QgsPointXY(100, 10), QgsPointXY(100, 0)]]))
        feat_b2 = QgsFeature()
        feat_b2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(105, 0), QgsPointXY(110, 0), QgsPointXY(110, 10), QgsPointXY(105, 10), QgsPointXY(105, 0)]]))
        dp_b.addFeatures([feat_b1, feat_b2])

        def side_effect(alg_name, params):
            if alg_name == "native:multiparttosingleparts":
                return {"OUTPUT": params.get("INPUT")}
            inp = params.get("INPUT")
            pts = list(inp.getFeatures())
            f = pts[0]
            if f.attribute("bgy_code") == "BGY_A":
                return {"OUTPUT": sp_a}
            else:
                return {"OUTPUT": sp_b}

        mock_proc_run.side_effect = side_effect

        # Select poly 2 (BGY_A) and poly 4 (BGY_B)
        poly_lyr.selectByIds([2, 4])

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=None)
        dlg.poly_selected_chk.setChecked(True)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        updated_features = list(poly_lyr.getFeatures())
        # 3 initial from A + 2 initial from B = 5.
        # Two were split into 2 parts each (+2) -> Total = 7 features
        self.assertEqual(len(updated_features), 7)

        bgy_a_eans = [f.attribute("new_ean") for f in updated_features if f.attribute("bgy_code") == "BGY_A"]
        bgy_b_eans = [f.attribute("new_ean") for f in updated_features if f.attribute("bgy_code") == "BGY_B"]

        # In BGY_A: max was 3, 002000 was split -> part 1: 002000, part 2: 004002
        self.assertIn("001000", bgy_a_eans)
        self.assertIn("002000", bgy_a_eans)
        self.assertIn("003000", bgy_a_eans)
        self.assertIn("004002", bgy_a_eans)

        # In BGY_B: max was 2, 001000 was split -> part 1: 001000, part 2: 003001 (isolated from BGY_A!)
        self.assertIn("001000", bgy_b_eans)
        self.assertIn("002000", bgy_b_eans)
        self.assertIn("003001", bgy_b_eans)

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_delineation_numbering_with_14_digit_geocode(self, mock_proc_run):
        """Verify sequential numbering with 14-digit PSGC geocode:
        Barangay 01728001 with 3 EAs:
          01728001001000 (001000)
          01728001002000 (002000) -> split into 2 parts
          01728001003000 (003000)
        Part 1: new_ean="002000", geocode="01728001002000", ea_type="DELINEATED"
        Part 2: new_ean="004002", geocode="01728001004002", ea_type="DELINEATED"
        """
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("geocode", QVariant.String),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
        ])
        poly_lyr.updateFields()

        # 3 EAs in Barangay 01728001
        p1 = QgsFeature(poly_lyr.fields())
        p1.setId(1)
        p1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        p1.setAttributes(["01728001001000", 150, 20])

        p2 = QgsFeature(poly_lyr.fields())
        p2.setId(2)
        p2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]]))
        p2.setAttributes(["01728001002000", 400, 60])

        p3 = QgsFeature(poly_lyr.fields())
        p3.setId(3)
        p3.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(20, 0), QgsPointXY(30, 0), QgsPointXY(30, 10), QgsPointXY(20, 10), QgsPointXY(20, 0)
        ]]))
        p3.setAttributes(["01728001003000", 220, 30])
        dp_poly.addFeatures([p1, p2, p3])
        poly_lyr.updateExtents()

        # Cut line dividing p2 at x=15
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "cut_lines", "memory")
        dp_line = line_lyr.dataProvider()
        line = QgsFeature()
        line.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(15, -2), QgsPointXY(15, 12)]))
        dp_line.addFeatures([line])
        line_lyr.updateExtents()

        # Mock split output for p2 -> two parts
        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_out", "memory")
        dp_split = split_lyr.dataProvider()
        f_part1 = QgsFeature()
        f_part1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(15, 0), QgsPointXY(15, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]]))
        f_part2 = QgsFeature()
        f_part2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(15, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(15, 10), QgsPointXY(15, 0)
        ]]))
        dp_split.addFeatures([f_part1, f_part2])
        split_lyr.updateExtents()

        mock_proc_run.return_value = {"OUTPUT": split_lyr}

        # Select EA 002000 (ID 2) only
        poly_lyr.selectByIds([2])

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=None)
        dlg.poly_selected_chk.setChecked(True)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 4)

        geocodes = {f.attribute("new_ean"): f.attribute("geocode") for f in updated_features}
        ea_types = {f.attribute("new_ean"): f.attribute("ea_type") for f in updated_features}

        # Untouched
        self.assertEqual(geocodes["001000"], "01728001001000")
        self.assertEqual(ea_types["001000"], "RETAINED")
        self.assertEqual(geocodes["003000"], "01728001003000")
        self.assertEqual(ea_types["003000"], "RETAINED")

        # Split Part 1 retains mother geocode
        self.assertEqual(geocodes["002000"], "01728001002000")
        self.assertEqual(ea_types["002000"], "DELINEATED")

        # Split Part 2 assigned new_ean 004002 and geocode 01728001004002
        self.assertEqual(geocodes["004002"], "01728001004002")
        self.assertEqual(ea_types["004002"], "DELINEATED")

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_delineate_ea_002000_into_three_slices_dissolves_zero_hh_first(self, mock_proc_run):
        """Verify user scenario: EA 002000 bisected into 3 parts (150 HH, 0 HH, 130 HH).
        The 0-HH part MUST be dissolved into an adjacent populated sibling BEFORE numbering new_ean.
        The resulting EAs MUST be:
          - 002000 (150 HH, DELINEATED, remarks='Delineated from EA 002000')
          - 004002 (130 HH, DELINEATED, remarks='Delineated from EA 002000')
        005002 must NEVER be created.
        bldg_points must stay completely untouched.
        """
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("geocode", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
            QgsField("bgy_code", QVariant.String),
            QgsField("ea_type", QVariant.String),
            QgsField("remarks", QVariant.String),
        ])
        poly_lyr.updateFields()

        # 3 EAs in Barangay 01728001: 001000, 002000, 003000
        p1 = QgsFeature(poly_lyr.fields())
        p1.setId(1)
        p1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        p1.setAttributes(["01728001001000", "001000", 150, 20, "01728001", "RETAINED", ""])

        p2 = QgsFeature(poly_lyr.fields())
        p2.setId(2)
        p2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(25, 0), QgsPointXY(25, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]]))
        p2.setAttributes(["01728001002000", "002000", 280, 50, "01728001", "RETAINED", ""])

        p3 = QgsFeature(poly_lyr.fields())
        p3.setId(3)
        p3.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(25, 0), QgsPointXY(35, 0), QgsPointXY(35, 10), QgsPointXY(25, 10), QgsPointXY(25, 0)
        ]]))
        p3.setAttributes(["01728001003000", "003000", 200, 30, "01728001", "RETAINED", ""])

        dp_poly.addFeatures([p1, p2, p3])
        poly_lyr.updateExtents()

        # Building points layer with est_hhcount:
        # Part A (x: 10..15): 1 building with est_hhcount = 150.0
        # Part B (x: 15..20): 0 buildings (0 HH)
        # Part C (x: 20..25): 1 building with est_hhcount = 130.0
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "bldg_points", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([
            QgsField("bldg_id", QVariant.Int),
            QgsField("est_hhcount", QVariant.Double),
        ])
        bldg_lyr.updateFields()

        bf1 = QgsFeature(bldg_lyr.fields())
        bf1.setId(101)
        bf1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(12, 5)))
        bf1.setAttributes([101, 150.0])

        bf2 = QgsFeature(bldg_lyr.fields())
        bf2.setId(102)
        bf2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(22, 5)))
        bf2.setAttributes([102, 130.0])

        dp_bldg.addFeatures([bf1, bf2])
        bldg_lyr.updateExtents()

        # Capture bldg_lyr snapshot before split to prove immutability
        bldg_snapshot_before = [
            (f.id(), f.attributes(), f.geometry().asPoint().x(), f.geometry().asPoint().y())
            for f in bldg_lyr.getFeatures()
        ]

        # Cut lines bisecting p2 at x=15 and x=20
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "cut_lines", "memory")
        dp_line = line_lyr.dataProvider()
        l1 = QgsFeature()
        l1.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(15, -2), QgsPointXY(15, 12)]))
        l2 = QgsFeature()
        l2.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(20, -2), QgsPointXY(20, 12)]))
        dp_line.addFeatures([l1, l2])
        line_lyr.updateExtents()

        # Mock split returns 3 parts:
        # Part 1 (x: 10..15): 150 HH
        # Part 2 (x: 15..20): 0 HH (empty slice, shares boundary with Part 1 and Part 3)
        # Part 3 (x: 20..25): 130 HH
        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()

        f_part1 = QgsFeature()
        f_part1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(10, 0), QgsPointXY(15, 0), QgsPointXY(15, 10), QgsPointXY(10, 10), QgsPointXY(10, 0)
        ]]))
        f_part2 = QgsFeature()
        f_part2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(15, 0), QgsPointXY(20, 0), QgsPointXY(20, 10), QgsPointXY(15, 10), QgsPointXY(15, 0)
        ]]))
        f_part3 = QgsFeature()
        f_part3.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(20, 0), QgsPointXY(25, 0), QgsPointXY(25, 10), QgsPointXY(20, 10), QgsPointXY(20, 0)
        ]]))
        dp_split.addFeatures([f_part1, f_part2, f_part3])
        split_lyr.updateExtents()

        def side_effect(alg_name, params):
            if alg_name in ("native:splitwithlines", "native:multiparttosingleparts"):
                return {"OUTPUT": split_lyr}
            return {"OUTPUT": split_lyr}

        mock_proc_run.side_effect = side_effect

        # Select EA 002000 (ID 2) to be split
        poly_lyr.selectByIds([2])

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.poly_selected_chk.setChecked(True)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        # Poly layer must have exactly 4 features (001000 untouched, 003000 untouched, 2 surviving parts of 002000)
        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 4)

        feature_map = {f.attribute("new_ean"): f for f in updated_features}

        # 1. 005002 MUST NEVER EXIST
        self.assertNotIn("005002", feature_map)

        # 2. Part 1 (150 HH) gets new_ean 002000
        self.assertIn("002000", feature_map)
        feat_002000 = feature_map["002000"]
        self.assertEqual(feat_002000.attribute("ea_type"), "DELINEATED")
        self.assertEqual(feat_002000.attribute("remarks"), "Delineated from EA 002000")
        self.assertEqual(feat_002000.attribute("geocode"), "01728001002000")

        # 3. Part 2 (130 HH) gets new_ean 004002
        self.assertIn("004002", feature_map)
        feat_004002 = feature_map["004002"]
        self.assertEqual(feat_004002.attribute("ea_type"), "DELINEATED")
        self.assertEqual(feat_004002.attribute("remarks"), "Delineated from EA 002000")
        self.assertEqual(feat_004002.attribute("geocode"), "01728001004002")

        # 4. No feature has hh_count == 0
        for f in updated_features:
            hh = f.attribute("hh_count")
            self.assertGreater(hh, 0)

        # 5. Untouched EAs 001000 and 003000 retain RETAINED
        self.assertEqual(feature_map["001000"].attribute("ea_type"), "RETAINED")
        self.assertEqual(feature_map["003000"].attribute("ea_type"), "RETAINED")

        # 6. Verify bldg_points IMMUTABILITY: exactly matches before split
        bldg_snapshot_after = [
            (f.id(), f.attributes(), f.geometry().asPoint().x(), f.geometry().asPoint().y())
            for f in bldg_lyr.getFeatures()
        ]
        self.assertEqual(bldg_snapshot_before, bldg_snapshot_after)

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_cross_crs_bldg_points_reprojected_in_memory_and_unmodified(self, mock_proc_run):
        """Verify cross-CRS support: bldg_points in EPSG:3857 and poly_layer in EPSG:4326.
        Points are matched via in-memory coordinate transform without modifying the bldg_points layer.
        """
        from references.create_enumeration_area.split_dialog import SplitEADialog
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            QgsField("geocode", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Int),
            QgsField("bldg_count", QVariant.Int),
            QgsField("bgy_code", QVariant.String),
            QgsField("ea_type", QVariant.String),
        ])
        poly_lyr.updateFields()

        # Single EA at lon 120.0..120.2, lat 14.0..14.2
        poly_feat = QgsFeature(poly_lyr.fields())
        poly_feat.setId(1)
        poly_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(120.0, 14.0), QgsPointXY(120.2, 14.0),
            QgsPointXY(120.2, 14.2), QgsPointXY(120.0, 14.2),
            QgsPointXY(120.0, 14.0)
        ]]))
        poly_feat.setAttributes(["01728001001000", "001000", 300, 30, "01728001", "RETAINED"])
        dp_poly.addFeatures([poly_feat])
        poly_lyr.updateExtents()

        # Building layer in EPSG:3857
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:3857", "bldg_points_3857", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([
            QgsField("est_hhcount", QVariant.Double),
        ])
        bldg_lyr.updateFields()

        # Transform (120.05, 14.1) and (120.15, 14.1) from 4326 to 3857
        crs4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        crs3857 = QgsCoordinateReferenceSystem("EPSG:3857")
        xform_to_3857 = QgsCoordinateTransform(crs4326, crs3857, QgsProject.instance().transformContext())

        pt1_3857 = xform_to_3857.transform(QgsPointXY(120.05, 14.1))
        pt2_3857 = xform_to_3857.transform(QgsPointXY(120.15, 14.1))

        bf1 = QgsFeature(bldg_lyr.fields())
        bf1.setId(1)
        bf1.setGeometry(QgsGeometry.fromPointXY(pt1_3857))
        bf1.setAttributes([80.0])

        bf2 = QgsFeature(bldg_lyr.fields())
        bf2.setId(2)
        bf2.setGeometry(QgsGeometry.fromPointXY(pt2_3857))
        bf2.setAttributes([90.0])

        dp_bldg.addFeatures([bf1, bf2])
        bldg_lyr.updateExtents()

        # Verify CRS is indeed EPSG:3857
        self.assertEqual(bldg_lyr.crs().authid(), "EPSG:3857")
        self.assertEqual(poly_lyr.crs().authid(), "EPSG:4326")

        # Snapshot bldg layer
        bldg_snap_before = [
            (f.id(), f.geometry().asPoint().x(), f.geometry().asPoint().y(), f.attributes())
            for f in bldg_lyr.getFeatures()
        ]

        # Mock split returning two halves at lon 120.1
        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()

        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(120.0, 14.0), QgsPointXY(120.1, 14.0),
            QgsPointXY(120.1, 14.2), QgsPointXY(120.0, 14.2),
            QgsPointXY(120.0, 14.0)
        ]]))
        f2 = QgsFeature()
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(120.1, 14.0), QgsPointXY(120.2, 14.0),
            QgsPointXY(120.2, 14.2), QgsPointXY(120.1, 14.2),
            QgsPointXY(120.1, 14.0)
        ]]))
        dp_split.addFeatures([f1, f2])
        split_lyr.updateExtents()

        mock_proc_run.return_value = {"OUTPUT": split_lyr}

        # Cut line at lon 120.1
        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "cut_line", "memory")
        dp_line = line_lyr.dataProvider()
        line = QgsFeature()
        line.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(120.1, 13.9), QgsPointXY(120.1, 14.3)]))
        dp_line.addFeatures([line])
        line_lyr.updateExtents()

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 2)

        # Part 1 (with pt2: 90 HH) is rank 1 -> new_ean 001000, hh_count 90
        # Part 2 (with pt1: 80 HH) is rank 2 -> new_ean 002001, hh_count 80
        feature_map = {f.attribute("new_ean"): f for f in updated_features}
        self.assertIn("001000", feature_map)
        self.assertIn("002001", feature_map)
        self.assertEqual(feature_map["001000"].attribute("hh_count"), 90)
        self.assertEqual(feature_map["002001"].attribute("hh_count"), 80)

        # bldg_layer must remain EPSG:3857 and completely unmodified
        self.assertEqual(bldg_lyr.crs().authid(), "EPSG:3857")
        bldg_snap_after = [
            (f.id(), f.geometry().asPoint().x(), f.geometry().asPoint().y(), f.attributes())
            for f in bldg_lyr.getFeatures()
        ]
        self.assertEqual(bldg_snap_before, bldg_snap_after)

    def test_split_cuts_strictly_where_line_ends_without_ray_extension(self):
        """Verify SplitEADialog defaults to 0.0 tolerance and uses exact cut line geometry without ray extension."""
        from references.create_enumeration_area.split_dialog import SplitEADialog
        from qgis.core import QgsGeometry, QgsPointXY

        dlg = SplitEADialog()
        # Default tolerance must be 0.0 (strictly cuts where line ends)
        self.assertEqual(dlg.tolerance_spin.value(), 0.0)

        # Polygon: (0,0) to (10,10)
        poly_geom = QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]])

        # Cut line: (5,0) to (5,10)
        line_geom = QgsGeometry.fromPolylineXY([QgsPointXY(5, 0), QgsPointXY(5, 10)])

        # When tolerance is 0.0, line endpoints are not modified
        # And even when endpoints method is called with 0.0, geometry remains exact
        extended = dlg._extend_line_endpoints(line_geom, 0.0)
        pts = extended.asPolyline()
        self.assertEqual(pts[0], QgsPointXY(5, 0))
        self.assertEqual(pts[-1], QgsPointXY(5, 10))


    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_split_calculates_both_hh_and_bldg_counts_strictly_by_matching_8digit(self, mock_proc_run):
        """Verify run_split filters both hh_count and bldg_count strictly by matching 8-digit geocode and ea_geocode."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            create_qgs_field("ean", QVariant.String),
            create_qgs_field("geocode", QVariant.String),
            create_qgs_field("hhcount", QVariant.Int),
            create_qgs_field("bldgcount", QVariant.Int),
            create_qgs_field("hh_count", QVariant.Int),
            create_qgs_field("bldg_count", QVariant.Int),
        ])
        poly_lyr.updateFields()

        # Delineated EA with 8-digit geocode "01728001" (14-digit "01728001001000")
        poly_feat = QgsFeature(poly_lyr.fields())
        poly_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly_feat.setAttribute("ean", "001000")
        poly_feat.setAttribute("geocode", "01728001001000")
        poly_feat.setAttribute("hhcount", 300)
        poly_feat.setAttribute("bldgcount", 50)
        poly_feat.setAttribute("hh_count", 0)
        poly_feat.setAttribute("bldg_count", 0)
        dp_poly.addFeatures([poly_feat])
        poly_lyr.updateExtents()

        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        line_feat = QgsFeature()
        line_feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        dp_line.addFeatures([line_feat])
        line_lyr.updateExtents()

        # Building points layer with ea_geocode:
        # Part 1 (x: 0..5):
        #   - b1: ea_geocode="01728001001001" (MATCHING 8-digit 01728001), est_hhcount=3.0
        #   - b2: ea_geocode="01728001001002" (MATCHING 8-digit 01728001), est_hhcount=2.0
        #   - b3: ea_geocode="01728002001001" (MISMATCHED 8-digit 01728002), est_hhcount=10.0
        # Expected Part 1: bldg_count = 2, hh_count = 5 (b3 excluded!)
        # Part 2 (x: 5..10):
        #   - b4: ea_geocode="01728001001003" (MATCHING 8-digit 01728001), est_hhcount=4.0
        # Expected Part 2: bldg_count = 1, hh_count = 4
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "bldg_points", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([
            create_qgs_field("ea_geocode", QVariant.String),
            create_qgs_field("est_hhcount", QVariant.Double),
        ])
        bldg_lyr.updateFields()

        b1 = QgsFeature(bldg_lyr.fields())
        b1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))
        b1.setAttribute("ea_geocode", "01728001001001")
        b1.setAttribute("est_hhcount", 3.0)

        b2 = QgsFeature(bldg_lyr.fields())
        b2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(3, 3)))
        b2.setAttribute("ea_geocode", "01728001001002")
        b2.setAttribute("est_hhcount", 2.0)

        b3 = QgsFeature(bldg_lyr.fields())
        b3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(4, 4)))
        b3.setAttribute("ea_geocode", "01728002001001")
        b3.setAttribute("est_hhcount", 10.0)

        b4 = QgsFeature(bldg_lyr.fields())
        b4.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(8, 8)))
        b4.setAttribute("ea_geocode", "01728001001003")
        b4.setAttribute("est_hhcount", 4.0)

        dp_bldg.addFeatures([b1, b2, b3, b4])
        bldg_lyr.updateExtents()

        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()
        dp_split.addAttributes([create_qgs_field("hh_count", QVariant.Int), create_qgs_field("bldg_count", QVariant.Int)])
        split_lyr.updateFields()

        f1 = QgsFeature(split_lyr.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        f2 = QgsFeature(split_lyr.fields())
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(5, 10), QgsPointXY(5, 0)
        ]]))
        dp_split.addFeatures([f1, f2])
        split_lyr.updateExtents()

        def side_effect(alg_name, params):
            return {"OUTPUT": split_lyr}

        mock_proc_run.side_effect = side_effect

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        updated_features = list(poly_lyr.getFeatures())
        self.assertEqual(len(updated_features), 2)

        # Part 1: bldg_count=2, hh_count=5 (3.0+2.0, point 3 with 10.0 excluded)
        # Part 2: bldg_count=1, hh_count=4
        counts = [(f.attribute("bldg_count"), f.attribute("hh_count")) for f in updated_features]
        self.assertIn((2, 5), counts)
        self.assertIn((1, 4), counts)

    @patch("references.create_enumeration_area.split_dialog.processing.run")
    def test_split_falls_back_spatially_when_no_ea_geocode_field(self, mock_proc_run):
        """Verify run_split gracefully falls back to spatial containment if bldg layer lacks ea_geocode."""
        from references.create_enumeration_area.split_dialog import SplitEADialog

        poly_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "delineated_ea", "memory")
        dp_poly = poly_lyr.dataProvider()
        dp_poly.addAttributes([
            create_qgs_field("ean", QVariant.String),
            create_qgs_field("geocode", QVariant.String),
            create_qgs_field("hhcount", QVariant.Int),
            create_qgs_field("bldgcount", QVariant.Int),
            create_qgs_field("hh_count", QVariant.Int),
            create_qgs_field("bldg_count", QVariant.Int),
        ])
        poly_lyr.updateFields()

        poly_feat = QgsFeature(poly_lyr.fields())
        poly_feat.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(10, 0), QgsPointXY(10, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        poly_feat.setAttribute("ean", "001000")
        poly_feat.setAttribute("geocode", "01728001001000")
        poly_feat.setAttribute("hhcount", 300)
        poly_feat.setAttribute("bldgcount", 50)
        dp_poly.addFeatures([poly_feat])
        poly_lyr.updateExtents()

        line_lyr = QgsVectorLayer("LineString?crs=epsg:4326", "eadel_update", "memory")
        dp_line = line_lyr.dataProvider()
        line_feat = QgsFeature()
        line_feat.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(5, -1), QgsPointXY(5, 11)]))
        dp_line.addFeatures([line_feat])
        line_lyr.updateExtents()

        # Building points layer WITHOUT ea_geocode (only est_hhcount)
        bldg_lyr = QgsVectorLayer("Point?crs=epsg:4326", "bldg_points", "memory")
        dp_bldg = bldg_lyr.dataProvider()
        dp_bldg.addAttributes([
            create_qgs_field("est_hhcount", QVariant.Double),
        ])
        bldg_lyr.updateFields()

        b1 = QgsFeature(bldg_lyr.fields())
        b1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(2, 2)))
        b1.setAttribute("est_hhcount", 6.0)

        dp_bldg.addFeatures([b1])
        bldg_lyr.updateExtents()

        split_lyr = QgsVectorLayer("Polygon?crs=epsg:4326", "split_res", "memory")
        dp_split = split_lyr.dataProvider()
        dp_split.addAttributes([create_qgs_field("hh_count", QVariant.Int), create_qgs_field("bldg_count", QVariant.Int)])
        split_lyr.updateFields()

        f1 = QgsFeature(split_lyr.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 10), QgsPointXY(0, 10), QgsPointXY(0, 0)
        ]]))
        dp_split.addFeatures([f1])
        split_lyr.updateExtents()

        mock_proc_run.side_effect = lambda alg_name, params: {"OUTPUT": split_lyr}

        dlg = SplitEADialog()
        dlg.poly_combo.currentLayer = MagicMock(return_value=poly_lyr)
        dlg.line_combo.currentLayer = MagicMock(return_value=line_lyr)
        dlg.bldg_combo.currentLayer = MagicMock(return_value=bldg_lyr)
        dlg.tolerance_spin.value = MagicMock(return_value=1.0)
        dlg.min_hh_spin.value = MagicMock(return_value=1)
        dlg.status_banner = MagicMock()
        dlg.progress_bar = MagicMock()
        dlg.log_console = MagicMock()

        dlg.run_split()

        feat = next(poly_lyr.getFeatures())
        self.assertEqual(feat.attribute("bldg_count"), 1)
        self.assertEqual(feat.attribute("hh_count"), 6)


if __name__ == "__main__":
    unittest.main()


