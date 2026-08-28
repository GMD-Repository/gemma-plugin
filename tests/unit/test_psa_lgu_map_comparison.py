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


class TestFindDefaultLayerId(unittest.TestCase):
    """Test suite for the dialog pre-fill helper find_default_layer_id."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.psa_lgu_map_comparison")
        self.project = self.mod.QgsProject.instance()
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def add_polygon_layer(self, name):
        layer = self.mod.QgsVectorLayer("Polygon?crs=EPSG:4326", name, "memory")
        self.project.addMapLayer(layer)
        return layer

    def find(self, hints, exclude_ids=()):
        return self.mod.find_default_layer_id(
            hints, self.mod.QgsWkbTypes.PolygonGeometry, exclude_ids=exclude_ids)

    def test_picks_psa_and_lgu_layers_by_name(self):
        """The PSA hints should find the PSA layer and the LGU hints the LGU one."""
        psa = self.add_polygon_layer("000102_PSA")
        lgu = self.add_polygon_layer("000102_LGU")
        self.assertEqual(self.find(self.mod.PSA_LAYER_HINTS), psa.id())
        self.assertEqual(self.find(self.mod.LGU_LAYER_HINTS), lgu.id())

    def test_returns_none_when_no_layer_matches(self):
        """A project with no PSA-like layer should pre-fill nothing."""
        self.add_polygon_layer("Barangay Boundary")
        self.assertIsNone(self.find(self.mod.PSA_LAYER_HINTS))

    def test_skips_this_algorithms_own_output_layers(self):
        """Outputs of a previous run must not be offered as inputs on a re-run."""
        self.add_polygon_layer("000102_PSA_Matched")
        self.add_polygon_layer("000102_PSA_Unmatched")
        self.assertIsNone(self.find(self.mod.PSA_LAYER_HINTS))
        source = self.add_polygon_layer("000102_PSA")
        self.assertEqual(self.find(self.mod.PSA_LAYER_HINTS), source.id())

    def test_exclude_ids_keeps_psa_pick_out_of_the_lgu_running(self):
        """A layer already chosen for PSA is not reused for LGU."""
        both = self.add_polygon_layer("000102_PSA_LGU_draft")
        self.assertEqual(self.find(self.mod.PSA_LAYER_HINTS), both.id())
        self.assertIsNone(self.find(self.mod.LGU_LAYER_HINTS, exclude_ids=(both.id(),)))


if __name__ == "__main__":
    unittest.main()
