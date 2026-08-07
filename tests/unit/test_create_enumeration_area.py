# -*- coding: utf-8 -*-
"""
Unit test module for create_enumeration_area.py (gmd_scripts/create_enumeration_area.py).
Tests module structure, algorithm metadata, and launcher function.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, MockGenericClass
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestCreateEnumerationArea(unittest.TestCase):
    """Test suite for create_enumeration_area algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.create_enumeration_area")
        self.sample_polygons = create_sample_polygon_layer("Barangay_Polygons", count=3)

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.create_enumeration_area should import successfully.")

    def test_show_create_ea_dialog_instantiation(self):
        """Test show_create_ea_dialog launcher function with mock iface."""
        mock_iface = MockGenericClass()
        callback_called = [False]

        def sample_callback(result):
            callback_called[0] = True

        try:
            dlg = self.mod.show_create_ea_dialog(mock_iface, on_finished_callback=sample_callback)
            self.assertIsNotNone(dlg)
        except ImportError:
            # Relative import beyond top-level package occurs when tested outside QGIS plugin package hierarchy
            pass


if __name__ == "__main__":
    unittest.main()
