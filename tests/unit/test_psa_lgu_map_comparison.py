# -*- coding: utf-8 -*-
"""
Unit test module for psa_lgu_map_comparison.py (gmd_scripts/psa_lgu_map_comparison.py).
Tests module import, the pure geocode-matching helper functions, and
PsaLguComparisonAlgorithm processing-algorithm metadata.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()


class TestPsaLguMapComparison(unittest.TestCase):
    """Test suite for psa_lgu_map_comparison module."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.psa_lgu_map_comparison")
        self.alg = self.mod.PsaLguComparisonAlgorithm()

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.psa_lgu_map_comparison should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "psalgu_boundary_comparison")
        self.assertEqual(self.alg.groupId(), "1map")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_first8_truncates_and_handles_none(self):
        """first8 should truncate to 8 characters and treat None as empty."""
        self.assertEqual(self.mod.first8("012345678900"), "01234567")
        self.assertEqual(self.mod.first8("0123"), "0123")
        self.assertEqual(self.mod.first8(None), "")

    def test_guess_geocode_field_exact_and_substring(self):
        """guess_geocode_field should prefer an exact 'Geocode' match, then fall back to substring."""
        self.assertEqual(self.mod.guess_geocode_field(["Barangay", "Geocode"]), "Geocode")
        self.assertEqual(self.mod.guess_geocode_field(["Barangay", "Geocode_10"]), "Geocode_10")
        self.assertIsNone(self.mod.guess_geocode_field(["Barangay", "PSGC"]))

    def test_extract_code_from_layer_name(self):
        """extract_code should pull the pppmm-style prefix off PSA/LGU layer names."""
        self.assertEqual(self.mod.extract_code("000102_LGU"), "000102")
        self.assertEqual(self.mod.extract_code("00102_PSA_Boundary"), "00102")
        self.assertEqual(self.mod.extract_code("12345_no_suffix"), "12345")
        self.assertEqual(self.mod.extract_code(""), "")


if __name__ == "__main__":
    unittest.main()
