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
            "update_datafile_coordinates_fix.py",
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

    def test_import_update_datafile_coordinates_fix(self):
        """Action 7: Update Datafile's Coordinates module."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.update_datafile_coordinates_fix")
        self.assertTrue(hasattr(mod, "update_datafile_coordinates"))
        self.assertTrue(hasattr(mod, "_run_fix_update_datafile_coordinates"))
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
        self.assertTrue(hasattr(mod, "update_datafile_coordinates"))
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
        self.assertTrue(callable(pkg.get_fix_handler("update_datafiles_coordinates")))
        self.assertTrue(callable(pkg.get_fix_handler("update_datafile_coordinates")))
        self.assertTrue(callable(pkg.get_fix_handler("mv_2027_hp_4a_pos_longit__invalid")))

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


    def test_action_registry_deleted_and_streamlined(self):
        """Verify the complex dynamic action registry was deleted from cbms_mv_fix.__init__."""
        pkg = importlib.import_module("references.cbms_mv.cbms_mv_fix")
        # Dynamic discovery registries removed
        self.assertFalse(hasattr(pkg, "AVAILABLE_ACTIONS"))
        self.assertFalse(hasattr(pkg, "ACTION_MODULE_MAP"))
        self.assertFalse(hasattr(pkg, "resolve_action_stem"))
        # Direct action functions exported
        self.assertTrue(callable(getattr(pkg, "concatenate_ea_geocode", None)))
        self.assertTrue(callable(getattr(pkg, "delete_selected_features", None)))
        self.assertTrue(callable(getattr(pkg, "generate_point_geometry", None)))
        self.assertTrue(callable(getattr(pkg, "deduplicate_features", None)))
        self.assertTrue(callable(getattr(pkg, "concatenate_bsn_geoid", None)))
        self.assertTrue(callable(getattr(pkg, "copy_geometry_to_coordinates", None)))

    def test_action_processed_regardless_of_validation_rule_or_file(self):
        """Verify action is processed directly regardless of what validation check or tab is active."""
        pkg = importlib.import_module("references.cbms_mv.cbms_mv_fix")
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature
        from PyQt5.QtCore import QVariant

        # Create a layer with a totally mismatched validation ID
        arbitrary_val_id = "custom_validation_rule_xyz_999"
        layer = QgsVectorLayer("Point?crs=epsg:4326", "arbitrary_layer", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("fid", QVariant.Int),
            QgsField("map_uuid", QVariant.String),
            QgsField("province_code", QVariant.String),
            QgsField("city_mun_code", QVariant.String),
            QgsField("barangay_code", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("bsn", QVariant.String),
        ])
        layer.updateFields()

        f = QgsFeature(layer.fields())
        f.setAttribute("fid", 10)
        f.setAttribute("map_uuid", "uuid-any-10")
        f.setAttribute("province_code", "09")
        f.setAttribute("city_mun_code", "12")
        f.setAttribute("barangay_code", "01")
        f.setAttribute("ean", "001")
        f.setAttribute("bsn", "00002")
        pr.addFeatures([f])

        # Regardless of arbitrary_val_id, the chosen action handler runs directly
        ea_handler = pkg.get_fix_handler("concatenate_ea_geocode")
        res_ea = ea_handler(layer, target_keys=["10_uuid-any-10"])
        self.assertTrue(res_ea.get("success"))
        self.assertEqual(res_ea.get("fixed_count"), 1)
        self.assertIn("10_uuid-any-10", res_ea.get("updated_values", {}))
        self.assertEqual(res_ea["updated_values"]["10_uuid-any-10"]["sf_ea_geocode"], "091201001")

        bsn_handler = pkg.get_fix_handler("concatenate_bsn_geoid")
        res_bsn = bsn_handler(layer, target_keys=["10_uuid-any-10"])
        self.assertTrue(res_bsn.get("success"))
        self.assertEqual(res_bsn.get("fixed_count"), 1)
        self.assertEqual(res_bsn["updated_values"]["10_uuid-any-10"]["sf_bsn_geoid"], "09120100100002")

    def test_actions_work_without_main_building_layer(self):
        """Verify actions process cleanly on error_layer alone when main_layer is None."""
        pkg = importlib.import_module("references.cbms_mv.cbms_mv_fix")
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
        from PyQt5.QtCore import QVariant

        layer = QgsVectorLayer("Point?crs=epsg:4326", "error_layer_only", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("fid", QVariant.Int),
            QgsField("map_uuid", QVariant.String),
            QgsField("sf_province_code", QVariant.String),
            QgsField("sf_city_mun_code", QVariant.String),
            QgsField("sf_barangay_code", QVariant.String),
            QgsField("sf_ean", QVariant.String),
            QgsField("sf_bsn", QVariant.String),
        ])
        layer.updateFields()

        f = QgsFeature(layer.fields())
        f.setAttribute("fid", 1)
        f.setAttribute("map_uuid", "m-1")
        f.setAttribute("sf_province_code", "01")
        f.setAttribute("sf_city_mun_code", "02")
        f.setAttribute("sf_barangay_code", "03")
        f.setAttribute("sf_ean", "004")
        f.setAttribute("sf_bsn", "00005")
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.0, 14.0)))
        pr.addFeatures([f])

        # Test with main_layer=None
        ea_handler = pkg.get_fix_handler("concatenate_ea_geocode")
        res = ea_handler(None, target_keys=["1_m-1"], error_layer=layer)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)

        copy_handler = pkg.get_fix_handler("copy_geometry_to_coordinates")
        res_copy = copy_handler(None, target_keys=["1_m-1"], error_layer=layer)
        self.assertTrue(res_copy.get("success"))
        self.assertEqual(res_copy.get("fixed_count"), 1)

    def test_update_datafile_coordinates_execution(self):
        """Verify update_datafile_coordinates correctly copies sf_longitude and sf_latitude to df_longitude and df_latitude."""
        pkg = importlib.import_module("references.cbms_mv.cbms_mv_fix")
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature
        from PyQt5.QtCore import QVariant

        layer = QgsVectorLayer("None", "test_coord_layer", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("fid", QVariant.Int),
            QgsField("map_uuid", QVariant.String),
            QgsField("sf_longitude", QVariant.String),
            QgsField("sf_latitude", QVariant.String),
            QgsField("df_x_current", QVariant.String),
            QgsField("df_y_current", QVariant.String),
        ])
        layer.updateFields()

        f = QgsFeature(layer.fields())
        f.setAttribute("fid", 1)
        f.setAttribute("map_uuid", "uuid-coords-101")
        f.setAttribute("sf_longitude", "121.054321")
        f.setAttribute("sf_latitude", "14.123456")
        f.setAttribute("df_x_current", "0.0")
        f.setAttribute("df_y_current", "0.0")
        pr.addFeatures([f])

        handler = pkg.get_fix_handler("update_datafiles_coordinates")
        self.assertIsNotNone(handler)

        res = handler(layer, target_keys=["1_uuid-coords-101"], error_layer=layer)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)

        # Verify values on layer were updated
        feat = next(layer.getFeatures())
        self.assertEqual(str(feat["df_x_current"]), "121.054321")
        self.assertEqual(str(feat["df_y_current"]), "14.123456")

        # Verify returned payload
        self.assertIn("1_uuid-coords-101", res.get("updated_values", {}))
        payload = res["updated_values"]["1_uuid-coords-101"]
        self.assertEqual(payload.get("df_x_current"), "121.054321")
        self.assertEqual(payload.get("df_y_current"), "14.123456")
        self.assertEqual(payload.get("longitude"), "121.054321")
        self.assertEqual(payload.get("latitude"), "14.123456")

    def test_generate_point_geometry_bsn_geoid_computation(self):
        """Verify _compute_bsn_geoid correctly concatenates province_code, city_mun_code, barangay__code, ean, and bsn_code (zero-padded)."""
        mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.generate_point_geometry_fix")
        self.assertTrue(hasattr(mod, "_compute_bsn_geoid"))

        # Test with double underscore barangay__code and numeric bsn_code (padded to 3, 2, 3, 6, 5)
        attrs = {
            "df_province_code": "01",
            "df_city_mun_code": "02",
            "barangay__code": "003",
            "df_ean": "000100",
            "bsn_code": "7",
        }
        bsn_geoid, ea_geo = mod._compute_bsn_geoid(attrs)
        self.assertEqual(ea_geo, "00102003000100")
        self.assertEqual(bsn_geoid, "0010200300010000007")

        # Test with float decimals like .0 from CSV import (padded to 3, 2, 3, 6, 5)
        attrs_float = {
            "province_code": "1.0",
            "city_mun_code": "2.0",
            "barangay_code": "3.0",
            "ean": "100.0",
            "bsn": "12.0",
        }
        bsn_geoid2, _ = mod._compute_bsn_geoid(attrs_float)
        self.assertEqual(bsn_geoid2, "0010200300010000012")

    def test_generate_point_geometry_execution_without_initial_uuid(self):
        """Verify generate_point_geometry creates point and auto-generates map_uuid when missing in CSV."""
        pkg = importlib.import_module("references.cbms_mv.cbms_mv_fix")
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry
        from PyQt5.QtCore import QVariant

        main_layer = QgsVectorLayer("Point?crs=EPSG:4326", "building_pts", "memory")
        pr = main_layer.dataProvider()
        pr.addAttributes([
            QgsField("map_uuid", QVariant.String),
            QgsField("bsn_geoid", QVariant.String),
            QgsField("longitude", QVariant.String),
            QgsField("latitude", QVariant.String),
            QgsField("status", QVariant.String),
        ])
        main_layer.updateFields()

        err_layer = QgsVectorLayer("None", "err_layer", "memory")
        err_pr = err_layer.dataProvider()
        err_pr.addAttributes([
            QgsField("df_fid", QVariant.Int),
            QgsField("df_x_current", QVariant.String),
            QgsField("df_y_current", QVariant.String),
            QgsField("df_province_code", QVariant.String),
            QgsField("df_city_mun_code", QVariant.String),
            QgsField("df_barangay_code", QVariant.String),
            QgsField("df_ean", QVariant.String),
            QgsField("df_bsn_code", QVariant.String),
        ])
        err_layer.updateFields()

        err_f = QgsFeature(err_layer.fields())
        err_f.setAttribute("df_fid", 1)
        err_f.setAttribute("df_x_current", "120.9842")
        err_f.setAttribute("df_y_current", "14.5995")
        err_f.setAttribute("df_province_code", "03")
        err_f.setAttribute("df_city_mun_code", "14")
        err_f.setAttribute("df_barangay_code", "005")
        err_f.setAttribute("df_ean", "000200")
        err_f.setAttribute("df_bsn_code", "42")
        err_pr.addFeatures([err_f])

        handler = pkg.get_fix_handler("generate_point_geometry")
        self.assertIsNotNone(handler)

        res = handler(
            main_layer,
            target_fids=[err_f.id()],
            error_layer=err_layer,
            prompt_confirm=False,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)

        # Check that point was created in main_layer
        features = list(main_layer.getFeatures())
        self.assertEqual(len(features), 1)
        pt_feat = features[0]
        self.assertTrue(pt_feat.hasGeometry())
        self.assertEqual(str(pt_feat["bsn_geoid"]), "0031400500020000042")
        # Ensure UUID was generated
        self.assertTrue(len(str(pt_feat["map_uuid"])) > 0)

    def test_update_datafile_coordinates_single_selection_scoping_headless(self):
        """Verify update_datafile_coordinates strictly updates only targeted feature in headless mode."""
        from references.cbms_mv.cbms_mv_fix.update_datafile_coordinates_fix import _run_fix_update_datafile_coordinates
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature
        from PyQt5.QtCore import QVariant

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "pts", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("map_uuid", QVariant.String),
            QgsField("sf_longitude", QVariant.String),
            QgsField("sf_latitude", QVariant.String),
            QgsField("df_x_current", QVariant.Double),
            QgsField("df_y_current", QVariant.Double),
        ])
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setAttribute("map_uuid", "uuid-1")
        f1.setAttribute("sf_longitude", "120.1")
        f1.setAttribute("sf_latitude", "14.1")
        f1.setAttribute("df_x_current", 0.0)
        f1.setAttribute("df_y_current", 0.0)

        f2 = QgsFeature(layer.fields())
        f2.setAttribute("map_uuid", "uuid-2")
        f2.setAttribute("sf_longitude", "120.2")
        f2.setAttribute("sf_latitude", "14.2")
        f2.setAttribute("df_x_current", 0.0)
        f2.setAttribute("df_y_current", 0.0)

        f3 = QgsFeature(layer.fields())
        f3.setAttribute("map_uuid", "uuid-3")
        f3.setAttribute("sf_longitude", "120.3")
        f3.setAttribute("sf_latitude", "14.3")
        f3.setAttribute("df_x_current", 0.0)
        f3.setAttribute("df_y_current", 0.0)

        pr.addFeatures([f1, f2, f3])
        feats = list(layer.getFeatures())
        f1_id, f2_id, f3_id = feats[0].id(), feats[1].id(), feats[2].id()

        res = _run_fix_update_datafile_coordinates(layer, target_uuids=["uuid-2"])
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        refreshed = {f.id(): f for f in layer.getFeatures()}
        # Only f2 should be updated with coordinates
        self.assertEqual(str(refreshed[f2_id]["df_x_current"]), "120.2")
        self.assertEqual(str(refreshed[f2_id]["df_y_current"]), "14.2")
        # f1 and f3 must remain untouched (0.0)
        self.assertEqual(float(refreshed[f1_id]["df_x_current"]), 0.0)
        self.assertEqual(float(refreshed[f3_id]["df_x_current"]), 0.0)

    def test_update_datafile_coordinates_single_selection_scoping_with_table(self):
        """Verify update_datafile_coordinates strictly updates only checked row when table is provided."""
        from references.cbms_mv.cbms_mv_fix.update_datafile_coordinates_fix import _run_fix_update_datafile_coordinates
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature
        from PyQt5.QtCore import QVariant, Qt
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "pts", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("map_uuid", QVariant.String),
            QgsField("sf_longitude", QVariant.String),
            QgsField("sf_latitude", QVariant.String),
            QgsField("df_x_current", QVariant.Double),
            QgsField("df_y_current", QVariant.Double),
        ])
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setAttribute("map_uuid", "uuid-1")
        f1.setAttribute("sf_longitude", "120.1")
        f1.setAttribute("sf_latitude", "14.1")
        f1.setAttribute("df_x_current", 0.0)
        f1.setAttribute("df_y_current", 0.0)

        f2 = QgsFeature(layer.fields())
        f2.setAttribute("map_uuid", "uuid-2")
        f2.setAttribute("sf_longitude", "120.2")
        f2.setAttribute("sf_latitude", "14.2")
        f2.setAttribute("df_x_current", 0.0)
        f2.setAttribute("df_y_current", 0.0)

        f3 = QgsFeature(layer.fields())
        f3.setAttribute("map_uuid", "uuid-3")
        f3.setAttribute("sf_longitude", "120.3")
        f3.setAttribute("sf_latitude", "14.3")
        f3.setAttribute("df_x_current", 0.0)
        f3.setAttribute("df_y_current", 0.0)

        pr.addFeatures([f1, f2, f3])
        feats = list(layer.getFeatures())
        f1_id, f2_id, f3_id = feats[0].id(), feats[1].id(), feats[2].id()

        table = QTableWidget(3, 3)
        table.setHorizontalHeaderLabels(["Select", "sf_longitude", "sf_latitude"])
        for r, (fid, u, lon, lat) in enumerate([
            (f1_id, "uuid-1", "120.1", "14.1"),
            (f2_id, "uuid-2", "120.2", "14.2"),
            (f3_id, "uuid-3", "120.3", "14.3"),
        ]):
            item0 = QTableWidgetItem(f"Row {r}")
            item0.setData(Qt.UserRole, fid)
            item0.setData(Qt.UserRole + 1, u)
            item0.setData(Qt.UserRole + 6, fid)
            item0.setData(Qt.UserRole + 7, u)
            item0.setCheckState(Qt.Checked if r == 1 else Qt.Unchecked)
            table.setItem(r, 0, item0)
            table.setItem(r, 1, QTableWidgetItem(lon))
            table.setItem(r, 2, QTableWidgetItem(lat))

        res = _run_fix_update_datafile_coordinates(layer, table=table, target_rows=[1])
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        refreshed = {f.id(): f for f in layer.getFeatures()}
        self.assertEqual(str(refreshed[f2_id]["df_x_current"]), "120.2")
        self.assertEqual(str(refreshed[f2_id]["df_y_current"]), "14.2")
        self.assertEqual(float(refreshed[f1_id]["df_x_current"]), 0.0)
        self.assertEqual(float(refreshed[f3_id]["df_x_current"]), 0.0)

    def test_update_datafile_coordinates_empty_selection_warns_and_does_nothing(self):
        """Verify update_datafile_coordinates with no selection returns failure and leaves layer untouched."""
        from references.cbms_mv.cbms_mv_fix.update_datafile_coordinates_fix import _run_fix_update_datafile_coordinates
        from qgis.core import QgsVectorLayer, QgsField, QgsFeature
        from PyQt5.QtCore import QVariant, Qt
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "pts", "memory")
        pr = layer.dataProvider()
        pr.addAttributes([
            QgsField("map_uuid", QVariant.String),
            QgsField("sf_longitude", QVariant.String),
            QgsField("sf_latitude", QVariant.String),
            QgsField("df_x_current", QVariant.Double),
            QgsField("df_y_current", QVariant.Double),
        ])
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setAttribute("map_uuid", "uuid-1")
        f1.setAttribute("sf_longitude", "120.1")
        f1.setAttribute("sf_latitude", "14.1")
        f1.setAttribute("df_x_current", 0.0)
        f1.setAttribute("df_y_current", 0.0)
        pr.addFeatures([f1])

        table = QTableWidget(1, 1)
        item0 = QTableWidgetItem("Row 0")
        item0.setCheckState(Qt.Unchecked)
        table.setItem(0, 0, item0)

        res = _run_fix_update_datafile_coordinates(layer, table=table, target_rows=[])
        self.assertFalse(res["success"])
        self.assertEqual(res["fixed_count"], 0)
        self.assertIn("select at least one row", res.get("message", "").lower())

        refreshed = list(layer.getFeatures())
        self.assertEqual(float(refreshed[0]["df_x_current"]), 0.0)


if __name__ == "__main__":
    unittest.main()


