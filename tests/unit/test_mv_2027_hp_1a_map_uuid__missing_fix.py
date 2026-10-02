# -*- coding: utf-8 -*-
"""
Unit test for 2027 CBMS Map Validation automated fix:
mv_2027_hp_1a_map_uuid__missing (now in unified cbms_mv_fix module)
"""

import unittest
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant

setup_qgis_mock_if_needed()

try:
    from references.cbms_mv.cbms_mv_fix import cbms_mv_fix as fix_module
except ImportError:
    import importlib
    fix_module = importlib.import_module("references.cbms_mv.cbms_mv_fix.cbms_mv_fix")


class TestMv2027Hp1aMapUuidMissingFix(unittest.TestCase):
    """Test suite for 1a map_uuid missing fix metadata and utilities."""

    def test_fix_metadata(self):
        """Verify fix constants and identifiers for hp_1a."""
        self.assertEqual(fix_module.FIX_ID_HP_1A, "mv_2027_hp_1a_map_uuid__missing")
        self.assertTrue(len(fix_module.FIX_NAME_HP_1A) > 0)
        self.assertTrue(len(fix_module.FIX_DESCRIPTION_HP_1A) > 0)

    def test_fix_registry_contains_hp_1a(self):
        """Verify FIX_REGISTRY contains the hp_1a entry."""
        self.assertIn("mv_2027_hp_1a_map_uuid__missing", fix_module.FIX_REGISTRY)
        entry = fix_module.FIX_REGISTRY["mv_2027_hp_1a_map_uuid__missing"]
        self.assertIn("name", entry)
        self.assertIn("description", entry)

    def test_flatten_ids(self):
        """Verify _flatten_ids extracts IDs correctly."""
        ids = fix_module._flatten_ids([1, "UUID-123", {"fid": 42}])
        self.assertIn(1, ids)
        self.assertIn("1", ids)
        self.assertIn("uuid-123", ids)
        self.assertIn(42, ids)

    def test_dispatch_table_contains_hp_1a(self):
        """Verify _FIX_DISPATCH routes hp_1a to _run_fix_map_uuid_missing."""
        self.assertIn("mv_2027_hp_1a_map_uuid__missing", fix_module._FIX_DISPATCH)
        self.assertEqual(
            fix_module._FIX_DISPATCH["mv_2027_hp_1a_map_uuid__missing"],
            fix_module._run_fix_map_uuid_missing,
        )


if __name__ == "__main__":
    unittest.main()
