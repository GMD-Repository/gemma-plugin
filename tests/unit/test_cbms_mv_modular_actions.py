# -*- coding: utf-8 -*-
"""
Unit test suite verifying modular per-action architecture for CBMS MV.
Ensures that each action in the Actions dropdown has its own dedicated .py file.
"""
import importlib
import os
import unittest

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()


class TestCbmsMvModularActions(unittest.TestCase):
    """Verify that each dropdown action is separated into its own .py module."""

    def test_all_action_files_exist(self):
        """Verify each of the 6 actions from the dropdown has its dedicated .py file."""
        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "references", "cbms_mv", "cbms_mv_fix")
        )
        expected_files = [
            "concatenate_ea_geocode_fix.py",
            "delete_selected_features_fix.py",
            "generate_point_geometry_fix.py",
            "deduplicate_features_fix.py",
            "concatenate_bsn_geoid_fix.py",
            "copy_geometry_to_coordinates_fix.py",
            "common.py",
            "cbms_mv_fix.py",
            "__init__.py",
        ]
        for f in expected_files:
            file_path = os.path.join(base_dir, f)
            self.assertTrue(
                os.path.isfile(file_path),
                f"Expected action module file does not exist: {f}",
            )

    def test_import_concatenate_ea_geocode_fix(self):
        """Action 1: Concatenate EA Geocode module."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.concatenate_ea_geocode_fix")
        self.assertTrue(hasattr(mod, "concatenate_ea_geocode"))
        self.assertTrue(hasattr(mod, "compute_ea_geocode_field_calculator"))
        self.assertTrue(hasattr(mod, "_run_fix_ea_geocode"))
        self.assertTrue(hasattr(mod, "run_fix"))

    def test_import_delete_selected_features_fix(self):
        """Action 2: Soft delete features module."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.delete_selected_features_fix")
        self.assertTrue(hasattr(mod, "delete_selected_features"))
        self.assertTrue(hasattr(mod, "mark_feature_deleted"))
        self.assertTrue(hasattr(mod, "sync_feature_status"))
        self.assertTrue(hasattr(mod, "run_fix"))

    def test_import_generate_point_geometry_fix(self):
        """Action 3: Generate point geometry module."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.generate_point_geometry_fix")
        self.assertTrue(hasattr(mod, "generate_point_geometry"))
        self.assertTrue(hasattr(mod, "_run_fix_map_uuid_missing"))
        self.assertTrue(hasattr(mod, "run_fix"))

    def test_import_deduplicate_features_fix(self):
        """Action 4: Deduplicate features module."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.deduplicate_features_fix")
        self.assertTrue(hasattr(mod, "deduplicate_features"))
        self.assertTrue(hasattr(mod, "_run_fix_longitude_duplicate"))
        self.assertTrue(hasattr(mod, "run_fix"))

    def test_import_concatenate_bsn_geoid_fix(self):
        """Action 5: Concatenate BSN GEOID module."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.concatenate_bsn_geoid_fix")
        self.assertTrue(hasattr(mod, "concatenate_bsn_geoid"))
        self.assertTrue(hasattr(mod, "compute_bsn_geoid_field_calculator"))
        self.assertTrue(hasattr(mod, "_run_fix_bsn_geoid"))
        self.assertTrue(hasattr(mod, "run_fix"))

    def test_import_copy_geometry_to_coordinates_fix(self):
        """Action 6: Copy geometry to coordinates module."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.copy_geometry_to_coordinates_fix")
        self.assertTrue(hasattr(mod, "copy_geometry_to_coordinates"))
        self.assertTrue(hasattr(mod, "_run_fix_copy_geometry_to_coordinates"))
        self.assertTrue(hasattr(mod, "run_fix"))

    def test_facade_cbms_mv_fix_reexports_all(self):
        """cbms_mv_fix facade re-exports all action functions and dispatcher."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.cbms_mv_fix")
        self.assertTrue(hasattr(mod, "concatenate_ea_geocode"))
        self.assertTrue(hasattr(mod, "delete_selected_features"))
        self.assertTrue(hasattr(mod, "generate_point_geometry"))
        self.assertTrue(hasattr(mod, "deduplicate_features"))
        self.assertTrue(hasattr(mod, "concatenate_bsn_geoid"))
        self.assertTrue(hasattr(mod, "copy_geometry_to_coordinates"))
        self.assertTrue(hasattr(mod, "run_fix"))

    def test_get_fix_handler_resolves_all_actions(self):
        """Package get_fix_handler resolves all actions and validation IDs."""
        pkg = importlib.import_module("references.cbms_mv.cbms_mv_fix")
        self.assertTrue(callable(pkg.get_fix_handler("mv_2027_hp_4b_ea_geocode__missing")))
        self.assertTrue(callable(pkg.get_fix_handler("mv_2027_hp_1a_map_uuid__missing")))
        self.assertTrue(callable(pkg.get_fix_handler("mv_2027_hp_4a_longitude__duplicate")))
        self.assertTrue(callable(pkg.get_fix_handler("mv_2027_hp_4b_bsn_geoid__invalid")))
        self.assertTrue(callable(pkg.get_fix_handler("copy_geometry_to_coordinates")))
        self.assertTrue(callable(pkg.get_fix_handler("delete_selected_features")))

    def test_make_unique_feature_key(self):
        """Verify composite unique key generation from fid and map_uuid."""
        common = importlib.import_module("references.cbms_mv.cbms_mv_fix.common")
        make_key = common.make_unique_feature_key
        self.assertEqual(make_key(101, "abc-uuid"), "101_abc-uuid")
        self.assertEqual(make_key("101", "abc-uuid"), "101_abc-uuid")
        self.assertEqual(make_key(None, "abc-uuid"), "_abc-uuid")
        self.assertEqual(make_key(101, None), "101_")
        self.assertEqual(make_key(None, None), "")
        self.assertEqual(make_key("NULL", "none"), "")

    def test_actions_register_composite_unique_key(self):
        """Verify actions accept target_keys and return payload under composite unique key."""
        pkg = importlib.import_module("references.cbms_mv.cbms_mv_fix")
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
        from PyQt5.QtCore import QVariant

        layer = QgsVectorLayer("Point?crs=epsg:4326", "test_lyr", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("fid", QVariant.Int),
            QgsField("map_uuid", QVariant.String),
            QgsField("province_code", QVariant.String),
            QgsField("city_mun_code", QVariant.String),
            QgsField("barangay_code", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("bsn", QVariant.String),
            QgsField("status", QVariant.String),
        ])
        layer.updateFields()

        f = QgsFeature(layer.fields())
        f.setAttribute("fid", 42)
        f.setAttribute("map_uuid", "uuid-test-99")
        f.setAttribute("province_code", "01")
        f.setAttribute("city_mun_code", "02")
        f.setAttribute("barangay_code", "03")
        f.setAttribute("ean", "004")
        f.setAttribute("bsn", "00005")
        f.setAttribute("status", "active")
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(120.9842, 14.5995)))
        pr.addFeatures([f])

        # Test EA Geocode fix
        handler_ea = pkg.get_fix_handler("mv_2027_hp_4b_ea_geocode__missing")
        res_ea = handler_ea(layer, target_keys=["42_uuid-test-99"])
        self.assertTrue(res_ea.get("success"))
        updated_vals = res_ea.get("updated_values", {})
        self.assertIn("42_uuid-test-99", updated_vals)

        # Test BSN GEOID fix
        handler_bsn = pkg.get_fix_handler("mv_2027_hp_4b_bsn_geoid__invalid")
        res_bsn = handler_bsn(layer, target_keys=["42_uuid-test-99"])
        self.assertTrue(res_bsn.get("success"))
        updated_vals_bsn = res_bsn.get("updated_values", {})
        self.assertIn("42_uuid-test-99", updated_vals_bsn)

        # Test Copy Geometry fix
        handler_geom = pkg.get_fix_handler("copy_geometry_to_coordinates")
        res_geom = handler_geom(layer, target_keys=["42_uuid-test-99"])
        self.assertTrue(res_geom.get("success"))
        updated_vals_geom = res_geom.get("updated_values", {})
        self.assertIn("42_uuid-test-99", updated_vals_geom)

        # Test Soft Delete fix
        handler_del = pkg.get_fix_handler("delete_selected_features")
        res_del = handler_del(layer, target_keys=["42_uuid-test-99"])
        self.assertTrue(res_del.get("success"))
        updated_vals_del = res_del.get("updated_values", {})
        self.assertIn("42_uuid-test-99", updated_vals_del)

    def test_deduplicate_keeps_duplicate_detection_logic(self):
        """Verify deduplicate algorithm retains coordinate (7 decimals) and survey column comparison."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.deduplicate_features_fix")
        self.assertTrue(hasattr(mod, "_is_deduplication_check_col"))
        self.assertTrue(hasattr(mod, "DEDUPLICATION_CHECK_COLS"))
        self.assertIn("longitude", mod.DEDUPLICATION_CHECK_COLS)
        self.assertIn("latitude", mod.DEDUPLICATION_CHECK_COLS)


if __name__ == "__main__":
    unittest.main()
