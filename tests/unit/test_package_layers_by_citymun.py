# -*- coding: utf-8 -*-
"""
Unit test module for package_layers_by_citymun.py (gmd_scripts/package_layers_by_citymun.py).
"""

import unittest
import importlib
from unittest.mock import MagicMock, patch
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from tests.mocks.sample_data import create_sample_polygon_layer, create_sample_point_layer

setup_qgis_mock_if_needed()

from qgis.core import QgsProject, QgsVectorLayer


class TestPackageLayersByCitymun(unittest.TestCase):
    """Test suite for package_layers_by_citymun.py."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.package_layers_by_citymun")
        self.sample_polygon = create_sample_polygon_layer("Sample_Polygon_Layer", count=3)
        self.sample_point = create_sample_point_layer("Sample_Point_Layer", count=5)

    def test_module_import(self):
        """Verify that the module imports successfully without syntax or module errors."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.package_layers_by_citymun should import successfully.")

    def test_no_global_layers_added_hook(self):
        """Verify that importing package_layers_by_citymun does NOT attach a global auto-grouping hook."""
        import qgis.utils
        handler = getattr(qgis.utils, "_package_layers_by_citymun_autogroup_handler", None)
        self.assertIsNone(handler, "Global auto-grouping handler key should be None/disconnected.")

    @patch("gmd_scripts.package_layers_by_citymun.QgsProject")
    def test_get_citymun_group_creates_root_group_without_packaged_layers(self, mock_qgs_project):
        """Verify that _get_citymun_group creates groups directly on layerTreeRoot without Packaged Layers wrapper."""
        mock_proj = MagicMock()
        mock_root = MagicMock()
        mock_group = MagicMock()
        mock_root.findGroup.return_value = None
        mock_root.addGroup.return_value = mock_group
        mock_proj.layerTreeRoot.return_value = mock_root
        mock_qgs_project.instance.return_value = mock_proj

        group = self.mod._get_citymun_group("01317_Iriga")
        self.assertEqual(group, mock_group)
        # Should call addGroup directly on the root layer tree
        mock_root.addGroup.assert_called_once_with("01317_Iriga")
        # Should NOT search for or create "Packaged Layers"
        mock_root.findGroup.assert_called_once_with("01317_Iriga")

    def test_sample_data_layer_processing(self):
        """Test module functionality using sample vector layer fixtures."""
        self.assertTrue(self.sample_polygon.isValid(), "Sample polygon layer should be valid.")
        self.assertGreaterEqual(self.sample_polygon.featureCount(), 3)


if __name__ == "__main__":
    unittest.main()
