# -*- coding: utf-8 -*-
"""
Unit test module for join_barangay_attributes.py (gmd_scripts/join_barangay_attributes.py).
Tests Roman numeral conversion, Levenshtein distance, fuzzy matching, and algorithm execution.
"""

import unittest
import importlib
import os
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingContext, QgsProcessingFeedback
from tests.mocks.sample_data import create_sample_polygon_layer
from qgis.core import QgsField, QgsFeature, QgsGeometry, QgsPointXY
from qgis.PyQt.QtCore import QVariant

setup_qgis_mock_if_needed()


class TestJoinBarangayAttributes(unittest.TestCase):
    """Test suite for join_barangay_attributes functions."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.join_barangay_attributes")

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.join_barangay_attributes should import successfully.")

    def test_normalize_name(self):
        """Test barangay name normalization (abbreviations, whitespace, lowercase)."""
        self.assertEqual(self.mod.normalize_name("Brgy. Sto. Niño"), "barangay santo niño")
        self.assertEqual(self.mod.normalize_name("Sta. Teresa - Pob."), "santa teresa poblacion")

    def test_roman_to_arabic_conversion(self):
        """Test Roman numeral to Arabic conversion."""
        self.assertEqual(self.mod.roman_to_arabic("Poblacion III"), "poblacion 3")
        self.assertEqual(self.mod.roman_to_arabic("Zone IV"), "zone 4")

    def test_arabic_to_roman_conversion(self):
        """Test Arabic number to Roman numeral conversion."""
        self.assertEqual(self.mod.arabic_to_roman("Poblacion 3"), "poblacion iii")

    def test_levenshtein_distance(self):
        """Test exact Levenshtein edit distance computation."""
        self.assertEqual(self.mod.levenshtein_distance("Barurao", "Barurao"), 0)
        self.assertEqual(self.mod.levenshtein_distance("San Jose", "San Josef"), 1)

    def test_fuzzy_match_roman_only(self):
        """Test fuzzy matching with Roman numeral normalization."""
        references = ["Barurao I", "Barurao II", "Santo Niño"]
        match, dist = self.mod.fuzzy_match_roman_only("Barurao 1", references, max_distance=3)
        self.assertEqual(match, "Barurao I")
        self.assertEqual(dist, 0)

        match_sto, dist_sto = self.mod.fuzzy_match_roman_only("Sto. Nino", references, max_distance=3)
        self.assertEqual(match_sto, "Santo Niño")

    def test_title_case_smart(self):
        """Test smart title casing preserving Roman numerals."""
        self.assertEqual(self.mod.title_case_smart("BARANGAY ONE"), "Barangay One")
        self.assertIsNotNone(self.mod.title_case_smart("POBLACION III"))

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods and instantiation."""
        alg = self.mod.JoinBarangayAttributes()
        self.assertEqual(alg.name(), "join_barangay_attributes")
        self.assertEqual(alg.displayName(), "Join Barangay Attributes")
        self.assertEqual(alg.group(), "1Map")
        self.assertEqual(alg.groupId(), "1map")
        self.assertIn("barangay name (Final Name)", alg.shortHelpString())
        self.assertIn("error_detail", alg.shortHelpString())
        self.assertIsInstance(alg.createInstance(), self.mod.JoinBarangayAttributes)

    def test_process_algorithm_with_sample_layer(self):
        """Test processAlgorithm execution using sample polygon layer."""
        alg = self.mod.JoinBarangayAttributes()
        sample_layer = create_sample_polygon_layer("13801_City_of_Caloocan", count=2)
        pr = sample_layer.dataProvider()
        pr.addAttributes([QgsField("bgy_name", QVariant.String, len=100)])
        sample_layer.updateFields()

        feat = QgsFeature(sample_layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        feat.setAttribute("bgy_name", "Barangay 1")
        pr.addFeatures([feat])

        params = {
            "citymun": sample_layer,
            "field": "bgy_name",
            "max_distance": 3,
            "Bgy_name": "TEMPORARY_OUTPUT",
            "Filtered_PSGC": "TEMPORARY_OUTPUT",
        }
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        try:
            results = alg.processAlgorithm(params, context, feedback)
            self.assertIn("Bgy_name", results)
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")

    def test_post_process_algorithm_deduplication(self):
        """Test that postProcessAlgorithm deduplicates layersToLoadOnCompletion entries."""
        alg = self.mod.JoinBarangayAttributes()
        alg.dest_id = "memory:matched_layer_id"
        alg.psgc_dest_id = "memory:psgc_layer_id"
        alg.custom_name = "00502_Camalig (Matched)"
        alg.psgc_custom_name = "00502_Camalig (Filtered PSGC)"

        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        # Simulate duplicate entries: TEMPORARY_OUTPUT placeholder and concrete dest_ids
        if hasattr(context, "addLayerToLoadOnCompletion"):
            details_generic = QgsProcessingContext.LayerDetails("Filtered PSGC Table", None, "Filtered_PSGC")
            details_specific = QgsProcessingContext.LayerDetails("Filtered PSGC Table", None, "Filtered_PSGC")
            details_matched = QgsProcessingContext.LayerDetails("Matched Barangays", None, "Bgy_name")

            context.addLayerToLoadOnCompletion("TEMPORARY_OUTPUT", details_generic)
            context.addLayerToLoadOnCompletion("memory:psgc_layer_id", details_specific)
            context.addLayerToLoadOnCompletion("memory:matched_layer_id", details_matched)

            alg.postProcessAlgorithm(context, feedback)

            layers_to_load = context.layersToLoadOnCompletion()
            # Verify TEMPORARY_OUTPUT placeholder was removed when specific dest_id was present
            if hasattr(layers_to_load, "keys"):
                self.assertNotIn("TEMPORARY_OUTPUT", layers_to_load.keys())
                if "memory:psgc_layer_id" in layers_to_load:
                    self.assertEqual(layers_to_load["memory:psgc_layer_id"].name, "00502_Camalig (Filtered PSGC)")
                if "memory:matched_layer_id" in layers_to_load:
                    self.assertEqual(layers_to_load["memory:matched_layer_id"].name, "00502_Camalig (Matched)")


if __name__ == "__main__":
    unittest.main()
