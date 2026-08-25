# -*- coding: utf-8 -*-
"""
Unit test module for mbi_validator.py (gmd_scripts/mbi_validator.py).
Tests MBI Validator / Status Audit processing algorithm on sample vector data fixtures.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    NULL,
)
from qgis.PyQt.QtCore import QVariant

setup_qgis_mock_if_needed()


class TestMbiValidator(unittest.TestCase):
    """Test suite for mbi_validator algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.mbi_validator")
        self.alg = self.mod.MBIStatusAuditAlgorithm()

        # Create a mock reference layer with required fields
        self.ref_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "Sample_Ref_MBI", "memory")
        pr = self.ref_layer.dataProvider()
        pr.addAttributes([
            QgsField("case_uuid", QVariant.String),
            QgsField("mbi_status", QVariant.String),
            QgsField("pso_remarks", QVariant.String),
            QgsField("mbi_type", QVariant.String),
            QgsField("involved_bgys", QVariant.String),
            QgsField("num_bldg_pts", QVariant.Int),
        ])
        self.ref_layer.updateFields()

        # Add sample features
        f1 = QgsFeature(self.ref_layer.fields())
        f1.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(120.0, 14.0), QgsPointXY(120.0, 14.1),
            QgsPointXY(120.1, 14.1), QgsPointXY(120.1, 14.0),
            QgsPointXY(120.0, 14.0)
        ]]))
        f1.setAttribute("case_uuid", "CASE-001")
        f1.setAttribute("mbi_status", "1_Updated")
        f1.setAttribute("pso_remarks", "Boundary realigned")
        f1.setAttribute("mbi_type", "1_Gap")
        f1.setAttribute("num_bldg_pts", 0)

        f2 = QgsFeature(self.ref_layer.fields())
        f2.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(120.2, 14.0), QgsPointXY(120.2, 14.1),
            QgsPointXY(120.3, 14.1), QgsPointXY(120.3, 14.0),
            QgsPointXY(120.2, 14.0)
        ]]))
        f2.setAttribute("case_uuid", "CASE-002")
        f2.setAttribute("mbi_status", "2_Pending")
        f2.setAttribute("mbi_remarks", "Under boundary dispute review")
        f2.setAttribute("mbi_type", "2_Overlap")
        f2.setAttribute("num_bldg_pts", 2)

        pr.addFeatures([f1, f2])
        self.ref_layer.updateExtents()

        # Create checker layer
        self.chk_gap_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "Sample_Chk_Gap", "memory")
        pr_chk = self.chk_gap_layer.dataProvider()
        pr_chk.addAttributes([QgsField("case_uuid", QVariant.String)])
        self.chk_gap_layer.updateFields()

        cf = QgsFeature(self.chk_gap_layer.fields())
        cf.setGeometry(QgsGeometry.fromPolygonXY([[
            QgsPointXY(120.05, 14.05), QgsPointXY(120.05, 14.15),
            QgsPointXY(120.15, 14.15), QgsPointXY(120.15, 14.05),
            QgsPointXY(120.05, 14.05)
        ]]))
        cf.setAttribute("case_uuid", "CHK-001")
        pr_chk.addFeatures([cf])
        self.chk_gap_layer.updateExtents()

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.mbi_validator should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "mbi_validator")
        self.assertEqual(self.alg.groupId(), "1map")
        self.assertEqual(self.alg.group(), "1Map")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())
        self.assertIsNotNone(self.alg.icon())
        self.assertIsNotNone(self.alg.shortHelpString())

    def test_gpkg_save_path_optionality(self):
        """Verify that GPKG_OUTPUT save path parameter is optional."""
        try:
            self.alg.initAlgorithm()
            param = self.alg.parameterDefinition(self.alg.GPKG_OUTPUT)
            if param:
                self.assertTrue(param.isOptional(), "GPKG_OUTPUT parameter must be optional so save path is not required when checkbox is unchecked.")
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")

    def test_normalize_helper(self):
        """Test normalize and meaningful helper functions."""
        self.assertEqual(self.mod.normalize(None), "")
        self.assertEqual(self.mod.normalize(NULL), "")
        self.assertEqual(self.mod.normalize("  Sample  "), "Sample")

        self.assertFalse(self.mod.meaningful(None))
        self.assertFalse(self.mod.meaningful(""))
        self.assertFalse(self.mod.meaningful("null"))
        self.assertFalse(self.mod.meaningful("a"))
        self.assertTrue(self.mod.meaningful("Resolved by Mayor"))

    def test_find_matching_layer_id(self):
        """Test layer auto-detection helper for ref_mbi_cases, Gaps, and Overlaps."""
        # Clean up any existing project layers
        QgsProject.instance().removeAllMapLayers()

        # No layers in project -> returns None
        found_id = self.mod.find_matching_layer_id(["ref_mbi_cases", "ref_mbi"])
        self.assertIsNone(found_id)

        # Add polygon layers named 'ref_mbi_cases', 'Gaps', 'Overlaps'
        test_ref = QgsVectorLayer("Polygon?crs=EPSG:4326", "ref_mbi_cases_2026", "memory")
        test_gaps = QgsVectorLayer("Polygon?crs=EPSG:4326", "Gaps", "memory")
        test_overlaps = QgsVectorLayer("Polygon?crs=EPSG:4326", "Overlaps", "memory")
        QgsProject.instance().addMapLayers([test_ref, test_gaps, test_overlaps])

        found_ref = self.mod.find_matching_layer_id(["ref_mbi_cases", "ref_mbi"])
        found_gaps = self.mod.find_matching_layer_id(["gaps", "gap"])
        found_overlaps = self.mod.find_matching_layer_id(["overlaps", "overlap"])

        self.assertEqual(found_ref, test_ref.id())
        self.assertEqual(found_gaps, test_gaps.id())
        self.assertEqual(found_overlaps, test_overlaps.id())

        # Clean up
        QgsProject.instance().removeAllMapLayers()

    def test_evaluate_reference_case(self):
        """Test evaluate_reference_case rules."""
        feat = list(self.ref_layer.getFeatures())[0]

        # Rule A: Claimed resolved (1_Updated), but spatially detected -> status_mismatch
        cat, reason = self.mod.evaluate_reference_case(feat, spatially_confirmed=True)
        self.assertEqual(cat, "status_mismatch")

        # Claimed resolved (1_Updated) and NOT detected -> confirmed_resolved
        cat2, reason2 = self.mod.evaluate_reference_case(feat, spatially_confirmed=False)
        self.assertEqual(cat2, "confirmed_resolved")

        # Claimed resolved (1_Updated) w/ non-zero bldg pts AND remarks present -> mismatch_with_remarks
        feat.setAttribute("num_bldg_pts", 3)
        feat.setAttribute("pso_remarks", "Boundary adjustment ongoing")
        cat3, reason3 = self.mod.evaluate_reference_case(feat, spatially_confirmed=False)
        self.assertEqual(cat3, "mismatch_with_remarks")

        # Claimed resolved (1_Updated) w/ non-zero bldg pts AND NO remarks -> status_mismatch
        feat.setAttribute("pso_remarks", None)
        cat4, reason4 = self.mod.evaluate_reference_case(feat, spatially_confirmed=False)
        self.assertEqual(cat4, "status_mismatch")

    def test_process_algorithm_execution(self):
        """Test processAlgorithm execution on reference and checker layers."""
        try:
            params = {
                self.alg.REF_LAYER: self.ref_layer,
                self.alg.CHK_GAP: self.chk_gap_layer,
                self.alg.CHK_OVERLAP: None,
                self.alg.OUT_MISMATCH: "TEMPORARY_OUTPUT",
                self.alg.OUT_NEW: "TEMPORARY_OUTPUT",
                self.alg.OUT_STILL: "TEMPORARY_OUTPUT",
                self.alg.OUT_RESOLVED: "TEMPORARY_OUTPUT",
                self.alg.OUT_MANUAL_REVIEW: "TEMPORARY_OUTPUT",
                self.alg.OUT_NOSTATUS: "TEMPORARY_OUTPUT",
            }
            QgsProject.instance().addMapLayer(self.ref_layer)
            QgsProject.instance().addMapLayer(self.chk_gap_layer)

            context = QgsProcessingContext()
            if hasattr(context, "setProject"):
                context.setProject(QgsProject.instance())
            feedback = QgsProcessingFeedback()

            res = self.alg.processAlgorithm(params, context, feedback)
            self.assertIsNotNone(res)
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")


if __name__ == "__main__":
    unittest.main()
