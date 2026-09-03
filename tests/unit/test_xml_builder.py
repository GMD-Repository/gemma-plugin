"""
Unit tests for QGIS plugin repository XML builder.
"""

import unittest
import xml.etree.ElementTree as ET
from scripts.utils.xml_builder import build_plugin_xml


class TestXmlBuilder(unittest.TestCase):
    """Test suite for XML builder format and version normalization."""

    def setUp(self):
        self.metadata = {
            "name": "GEMMA",
            "description": "GIS Extension for Map Management and Analysis",
            "about": "Geospatial Management Division plugin",
            "author": "Geospatial Management Division",
            "qgisMinimumVersion": "3.0",
            "tags": "GMD,1Map",
            "category": "Processing Provider",
            "deprecated": "False",
            "server": "False",
        }

    def test_build_stable_xml_version_no_v_prefix(self):
        """Stable XML version attribute and element must NOT have 'v' prefix."""
        xml_str = build_plugin_xml(
            metadata=self.metadata,
            version="1.0.1",
            download_url="https://example.com/gemma.zip",
            date="2026-09-01",
            is_beta=False,
        )
        root = ET.fromstring(xml_str)
        plugin = root.find("pyqgis_plugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.attrib.get("version"), "1.0.1")
        self.assertEqual(plugin.find("version").text, "1.0.1")
        self.assertEqual(plugin.find("experimental").text, "False")

    def test_build_stable_xml_strips_leading_v(self):
        """If 'v1.0.1' is passed, the leading 'v' must be stripped to match metadata.txt."""
        xml_str = build_plugin_xml(
            metadata=self.metadata,
            version="v1.0.1",
            download_url="https://example.com/gemma.zip",
            date="2026-09-01",
            is_beta=False,
        )
        root = ET.fromstring(xml_str)
        plugin = root.find("pyqgis_plugin")
        self.assertEqual(plugin.attrib.get("version"), "1.0.1")
        self.assertEqual(plugin.find("version").text, "1.0.1")

    def test_build_beta_xml_version_format(self):
        """Beta XML should mark experimental True and preserve preview version without 'v'."""
        xml_str = build_plugin_xml(
            metadata=self.metadata,
            version="1.0.1-r738",
            download_url="https://example.com/gemma-r738.zip",
            date="2026-09-01",
            is_beta=True,
        )
        root = ET.fromstring(xml_str)
        plugin = root.find("pyqgis_plugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.attrib.get("version"), "1.0.1-r738")
        self.assertEqual(plugin.find("version").text, "1.0.1-r738")
        self.assertEqual(plugin.find("experimental").text, "True")
        self.assertIn("(Beta)", plugin.attrib.get("name"))


if __name__ == "__main__":
    unittest.main()
