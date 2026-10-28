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


class MockTableItem:
    def __init__(self, text="", check_state=2, roles=None):
        self._text = str(text) if text is not None else ""
        self._check_state = check_state
        self._roles = dict(roles or {})

    def text(self):
        return self._text

    def checkState(self):
        return self._check_state

    def isChecked(self):
        return self._check_state == 2

    def data(self, role):
        return self._roles.get(role)


class MockTableHeaderItem:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


class MockTable:
    def __init__(self, headers, rows):
        self._headers = [MockTableHeaderItem(h) for h in headers]
        self._grid = []
        for row in rows:
            row_items = []
            for item in row:
                if isinstance(item, MockTableItem):
                    row_items.append(item)
                else:
                    row_items.append(MockTableItem(str(item) if item is not None else ""))
            self._grid.append(row_items)

    def columnCount(self):
        return len(self._headers)

    def rowCount(self):
        return len(self._grid)

    def horizontalHeaderItem(self, c):
        return self._headers[c] if 0 <= c < len(self._headers) else None

    def item(self, r, c):
        if 0 <= r < len(self._grid) and 0 <= c < len(self._grid[r]):
            return self._grid[r][c]
        return None


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

    def _create_mock_building_layer(self):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "bldg_points", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("longitude", QVariant.String))
        fields.append(QgsField("latitude", QVariant.String))
        fields.append(QgsField("status", QVariant.String))
        fields.append(QgsField("up_feature", QVariant.Int))
        fields.append(QgsField("uplocation", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        layer.setFields(fields)
        return layer

    def test_batch_generate_points_multiple_rows_creates_distinct_features(self):
        """
        Verify that when selecting multiple features with 'NULL' or missing UUIDs,
        each row generates a distinct point feature with a unique UUID,
        instead of collapsing or overwriting into a single point.
        """
        main_layer = self._create_mock_building_layer()

        headers = ["#", "sf_longitude", "sf_latitude", "sf_map_uuid", "df_map_uuid", "Action"]
        rows = [
            [
                MockTableItem("", check_state=2, roles={0: 1, 3: 101}),
                MockTableItem("120.91239693179"),
                MockTableItem("14.278262210011"),
                MockTableItem("NULL"),
                MockTableItem("NULL"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 2, 3: 102}),
                MockTableItem("120.91255064431"),
                MockTableItem("14.277906237442"),
                MockTableItem("NULL"),
                MockTableItem("NULL"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 3, 3: 103}),
                MockTableItem("120.91280011111"),
                MockTableItem("14.277500222222"),
                MockTableItem("NULL"),
                MockTableItem("NULL"),
                MockTableItem("Edit"),
            ],
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[0, 1, 2],
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 3, f"Expected 3 features created, got {res['fixed_count']}")
        self.assertEqual(main_layer.featureCount(), 3, f"Expected 3 features in main_layer, got {main_layer.featureCount()}")

        features = list(main_layer.getFeatures())
        self.assertEqual(len(features), 3)

        # Verify all features have unique, non-null UUIDs
        uuids = [f["map_uuid"] for f in features]
        for u in uuids:
            self.assertIsNotNone(u)
            self.assertNotIn(str(u).lower(), ("null", "none", "nan", ""))
        self.assertEqual(len(set(uuids)), 3, "Each feature must have a distinct UUID!")

        # Verify coordinates of each feature match the row inputs
        coords_x = [f["longitude"] for f in features]
        coords_y = [f["latitude"] for f in features]
        self.assertIn("120.91239693179", coords_x)
        self.assertIn("120.91255064431", coords_x)
        self.assertIn("120.91280011111", coords_x)
        self.assertIn("14.278262210011", coords_y)
        self.assertIn("14.277906237442", coords_y)
        self.assertIn("14.277500222222", coords_y)

    def test_existing_feature_updated_while_new_feature_created_in_same_batch(self):
        """
        Verify that an existing feature with an assigned UUID has its geometry updated,
        while other rows in the batch without UUID get newly created features.
        """
        main_layer = self._create_mock_building_layer()

        # Add pre-existing feature
        feat_existing = QgsFeature(main_layer.fields())
        feat_existing.setAttribute("map_uuid", "EXISTING-UUID-001")
        feat_existing.setAttribute("longitude", "100.0")
        feat_existing.setAttribute("latitude", "10.0")
        feat_existing.setAttribute("status", "deleted")
        main_layer.dataProvider().addFeatures([feat_existing])
        existing_id = list(main_layer.getFeatures())[0].id()

        headers = ["#", "df_x_current", "df_y_current", "sf_map_uuid", "Action"]
        rows = [
            [
                MockTableItem("", check_state=2, roles={0: 10, 1: "EXISTING-UUID-001"}),
                MockTableItem("120.5"),
                MockTableItem("14.5"),
                MockTableItem("EXISTING-UUID-001"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 11}),
                MockTableItem("121.0"),
                MockTableItem("15.0"),
                MockTableItem(""),
                MockTableItem("Edit"),
            ],
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[0, 1],
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 2)
        self.assertEqual(main_layer.featureCount(), 2)

        # Existing feature should be active and have updated coordinates
        updated_existing = main_layer.getFeature(existing_id)
        self.assertEqual(updated_existing["status"], "active")
        self.assertEqual(updated_existing["longitude"], "120.5")
        self.assertEqual(updated_existing["latitude"], "14.5")

        # Second feature should be newly added with a unique UUID
        all_feats = list(main_layer.getFeatures())
        new_feats = [f for f in all_feats if f.id() != existing_id]
        self.assertEqual(len(new_feats), 1)
        self.assertNotEqual(new_feats[0]["map_uuid"], "EXISTING-UUID-001")
        self.assertEqual(new_feats[0]["longitude"], "121.0")

    def test_batch_generate_points_identical_coordinates_reuses_point_and_uuid(self):
        """
        Verify that when multiple selected rows share identical (X, Y) coordinates,
        only 1 unique point feature is created, and that point's UUID is reused
        for all rows sharing those coordinates.
        """
        main_layer = self._create_mock_building_layer()

        headers = ["#", "sf_longitude", "sf_latitude", "sf_map_uuid", "df_map_uuid", "Action"]
        rows = [
            [
                MockTableItem("", check_state=2, roles={0: 1, 3: 101}),
                MockTableItem("120.91255064431"),
                MockTableItem("14.277906237442"),
                MockTableItem("NULL"),
                MockTableItem("NULL"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 2, 3: 102}),
                MockTableItem("120.91255064431"),
                MockTableItem("14.277906237442"),
                MockTableItem("NULL"),
                MockTableItem("NULL"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 3, 3: 103}),
                MockTableItem("120.91239693179"),
                MockTableItem("14.278262210011"),
                MockTableItem("NULL"),
                MockTableItem("NULL"),
                MockTableItem("Edit"),
            ],
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[0, 1, 2],
        )

        self.assertTrue(res["success"])
        # All 3 rows were fixed
        self.assertEqual(res["fixed_count"], 3)
        # But only 2 unique points were created in the layer (Row 0 and Row 1 shared 1 point)
        self.assertEqual(main_layer.featureCount(), 2)

        # Row 0 and Row 1 must have the exact same reused UUID
        uuid_row0 = res["updated_values"]["row_0"]["map_uuid"]
        uuid_row1 = res["updated_values"]["row_1"]["map_uuid"]
        uuid_row2 = res["updated_values"]["row_2"]["map_uuid"]

        self.assertEqual(uuid_row0, uuid_row1, "Rows with identical coordinates must share the same UUID!")
        self.assertNotEqual(uuid_row0, uuid_row2, "Rows with distinct coordinates must have distinct UUIDs!")

    def test_reuse_existing_point_at_coordinates_without_creating_new_feature(self):
        """
        Verify that if a point feature already exists in the layer at (X, Y),
        its UUID is linked without creating an extra duplicate point feature.
        """
        main_layer = self._create_mock_building_layer()

        # Pre-existing point in building layer
        feat = QgsFeature(main_layer.fields())
        feat.setAttribute("map_uuid", "PRE-EXISTING-UUID-999")
        feat.setAttribute("longitude", "120.91255064431")
        feat.setAttribute("latitude", "14.277906237442")
        feat.setAttribute("status", "active")
        main_layer.dataProvider().addFeatures([feat])
        pre_existing_id = list(main_layer.getFeatures())[0].id()

        headers = ["#", "sf_longitude", "sf_latitude", "sf_map_uuid", "Action"]
        rows = [
            [
                MockTableItem("", check_state=2, roles={0: 1, 3: 201}),
                MockTableItem("120.91255064431"),
                MockTableItem("14.277906237442"),
                MockTableItem("NULL"),
                MockTableItem("Edit"),
            ]
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[0],
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)
        # Layer should STILL have only 1 feature (reused, not duplicated)
        self.assertEqual(main_layer.featureCount(), 1)
        self.assertEqual(res["updated_values"]["row_0"]["map_uuid"], "PRE-EXISTING-UUID-999")
        self.assertEqual(res["updated_values"]["row_0"]["sf_fid"], pre_existing_id)

    def test_single_row_selected_does_not_overwrite_unselected_row_keys(self):
        """
        Verify that fixing only row 0 does NOT create bare integer keys like '1'
        or 'row_1' in updated_values that would collide with or overwrite unselected row 1.
        """
        main_layer = self._create_mock_building_layer()

        headers = ["#", "sf_longitude", "sf_latitude", "sf_map_uuid", "df_map_uuid", "Action"]
        rows = [
            [
                MockTableItem("", check_state=2, roles={0: 1, 4: 1, 5: "48eb9e82-76d1-44b5-89bf-6b5749561691"}),
                MockTableItem("124.0"),
                MockTableItem("122.0"),
                MockTableItem("NULL"),
                MockTableItem("48eb9e82-76d1-44b5-89bf-6b5749561691"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=0, roles={0: 2, 4: 2, 5: "ef9b803d-11d0-48c2-833f-6b776f2ac7f3"}),
                MockTableItem("120.9144496"),
                MockTableItem("14.27720843"),
                MockTableItem("NULL"),
                MockTableItem("ef9b803d-11d0-48c2-833f-6b776f2ac7f3"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=0, roles={0: 3, 4: 3, 5: "ef9b803d-11d0-48c2-833f-6b776f2ac7f3"}),
                MockTableItem("120.9144496"),
                MockTableItem("14.27720843"),
                MockTableItem("NULL"),
                MockTableItem("ef9b803d-11d0-48c2-833f-6b776f2ac7f3"),
                MockTableItem("Edit"),
            ],
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[0],
            prompt_confirm=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        # Namespaced row key for row 0 exists
        self.assertIn("row_0", res["updated_values"])
        self.assertNotIn("row_1", res["updated_values"])
        self.assertNotIn("row_2", res["updated_values"])

        # Row 1 candidate keys must find NO match in updated_values
        row1_candidates = ["row_1", "2_ef9b803d-11d0-48c2-833f-6b776f2ac7f3", "ef9b803d-11d0-48c2-833f-6b776f2ac7f3"]
        for c in row1_candidates:
            self.assertNotIn(c, res["updated_values"])

    def test_batch_generate_points_with_distinct_uuids_creates_points_despite_nearby_features(self):
        """
        Verify that when rows have their own UUIDs, new points are created and
        existing features with different UUIDs at the same coordinates are NOT hijacked.
        """
        main_layer = self._create_mock_building_layer()

        # Pre-existing feature in the layer with an unrelated UUID
        pre_feat = QgsFeature(main_layer.fields())
        pre_feat.setAttribute("map_uuid", "EXISTING-OTHER-BUILDING-UUID")
        pre_feat.setAttribute("longitude", "120.9144496")
        pre_feat.setAttribute("latitude", "14.27720843")
        pre_feat.setAttribute("status", "active")
        main_layer.dataProvider().addFeatures([pre_feat])

        headers = ["#", "sf_longitude", "sf_latitude", "sf_map_uuid", "df_map_uuid", "Action"]
        rows = [
            [
                MockTableItem("", check_state=2, roles={0: 1, 4: 1, 5: "48eb9e82-76d1-44b5-89bf-6b5749561691"}),
                MockTableItem("124.0"),
                MockTableItem("122.0"),
                MockTableItem("NULL"),
                MockTableItem("48eb9e82-76d1-44b5-89bf-6b5749561691"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 2, 4: 2, 5: "ef9b803d-11d0-48c2-833f-6b776f2ac7f3"}),
                MockTableItem("120.9144496"),
                MockTableItem("14.27720843"),
                MockTableItem("NULL"),
                MockTableItem("ef9b803d-11d0-48c2-833f-6b776f2ac7f3"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 3, 4: 3, 5: "ef9b803d-11d0-48c2-833f-6b776f2ac7f3"}),
                MockTableItem("120.9144496"),
                MockTableItem("14.27720843"),
                MockTableItem("NULL"),
                MockTableItem("ef9b803d-11d0-48c2-833f-6b776f2ac7f3"),
                MockTableItem("Edit"),
            ],
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[0, 1, 2],
            prompt_confirm=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 3)

        # Features in layer:
        # 1 pre-existing + 1 created for Row 0 + 1 created for Row 1 (Row 2 shares Row 1's building) = 3 total
        self.assertEqual(main_layer.featureCount(), 3)

        layer_uuids = [f["map_uuid"] for f in main_layer.getFeatures()]
        self.assertIn("EXISTING-OTHER-BUILDING-UUID", layer_uuids, "Pre-existing building UUID was preserved!")
        self.assertIn("48eb9e82-76d1-44b5-89bf-6b5749561691", layer_uuids, "Row 0 point was created!")
        self.assertIn("ef9b803d-11d0-48c2-833f-6b776f2ac7f3", layer_uuids, "Row 1 point was created!")

    def test_middle_row_selected_only_updates_middle_row_and_does_not_affect_others(self):
        """
        Verify that selecting ONLY the middle row (Row 1):
        1) Generates the point for Row 1.
        2) Only returns 'row_1' and its composite key in updated_values.
        3) Does NOT include bare integers (like 1, 2, 3) or bare UUIDs that could overwrite Row 0 or Row 2.
        """
        main_layer = self._create_mock_building_layer()

        headers = ["#", "sf_longitude", "sf_latitude", "sf_map_uuid", "df_map_uuid", "Action"]
        rows = [
            [
                MockTableItem("", check_state=0, roles={0: 1, 4: 1, 5: "48eb9e82-76d1-44b5-89bf-6b5749561691"}),
                MockTableItem("124.0"),
                MockTableItem("122.0"),
                MockTableItem("NULL"),
                MockTableItem("48eb9e82-76d1-44b5-89bf-6b5749561691"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=2, roles={0: 2, 4: 2, 5: "ef9b803d-11d0-48c2-833f-6b776f2ac7f3"}),
                MockTableItem("120.9144496"),
                MockTableItem("14.27720843"),
                MockTableItem("NULL"),
                MockTableItem("ef9b803d-11d0-48c2-833f-6b776f2ac7f3"),
                MockTableItem("Edit"),
            ],
            [
                MockTableItem("", check_state=0, roles={0: 3, 4: 3, 5: "ef9b803d-11d0-48c2-833f-6b776f2ac7f3"}),
                MockTableItem("120.9144496"),
                MockTableItem("14.27720843"),
                MockTableItem("NULL"),
                MockTableItem("ef9b803d-11d0-48c2-833f-6b776f2ac7f3"),
                MockTableItem("Edit"),
            ],
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[1],
            prompt_confirm=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)
        self.assertEqual(main_layer.featureCount(), 1)

        # Namespaced row key for Row 1 must exist
        self.assertIn("row_1", res["updated_values"])
        self.assertNotIn("row_0", res["updated_values"])
        self.assertNotIn("row_2", res["updated_values"])

        # Bare integer keys must NOT exist in updated_values
        for bare_int in (0, 1, 2, 3):
            self.assertNotIn(bare_int, res["updated_values"], f"Integer key {bare_int} must NOT be in updated_values!")

        # Bare UUID keys must NOT exist in updated_values (only composite keys like '2_ef9b803d...')
        self.assertNotIn("ef9b803d-11d0-48c2-833f-6b776f2ac7f3", res["updated_values"])
        self.assertNotIn("48eb9e82-76d1-44b5-89bf-6b5749561691", res["updated_values"])

        # Row 0 candidate keys must NOT match
        row0_candidates = ["row_0", 1, "fid_1", "1_48eb9e82-76d1-44b5-89bf-6b5749561691", "48eb9e82-76d1-44b5-89bf-6b5749561691"]
        for c in row0_candidates:
            self.assertNotIn(c, res["updated_values"])

        # Row 2 candidate keys must NOT match
        row2_candidates = ["row_2", 3, "fid_3", "3_ef9b803d-11d0-48c2-833f-6b776f2ac7f3"]
        for c in row2_candidates:
            self.assertNotIn(c, res["updated_values"])

    def test_psgc_code_padding_rule(self):
        """
        Verify PSGC component zero-padding in _extract_padded_boundary_codes and _compute_bsn_geoid:
        province_code: pad to 3 digits
        city_mun_code: pad to 2 digits
        barangay_code: pad to 3 digits
        ean: pad to 6 digits
        bsn: pad to 5 digits
        """
        from references.cbms_mv.cbms_mv_fix import generate_point_geometry_fix as geom_mod

        attrs = {
            "region_code": "4",
            "province_code": "21",
            "city_mun_code": "8",
            "barangay_code": "2",
            "ean": "100",
            "bsn": "5",
        }
        padded = geom_mod._extract_padded_boundary_codes(attrs)
        self.assertEqual(padded["region_code"], "04")
        self.assertEqual(padded["province_code"], "021")
        self.assertEqual(padded["city_mun_code"], "08")
        self.assertEqual(padded["barangay_code"], "002")
        self.assertEqual(padded["ean"], "000100")
        self.assertEqual(padded["bsn"], "00005")
        self.assertEqual(padded["ea_geocode"], "02108002000100")
        self.assertEqual(len(padded["ea_geocode"]), 14)
        self.assertEqual(padded["bsn_geoid"], "0210800200010000005")
        self.assertEqual(len(padded["bsn_geoid"]), 19)

        # Test _compute_bsn_geoid backward-compatible wrapper
        bsn_geoid, ea_geo = geom_mod._compute_bsn_geoid(attrs)
        self.assertEqual(ea_geo, "02108002000100")
        self.assertEqual(bsn_geoid, "0210800200010000005")

    def test_generate_point_geometry_includes_padded_separate_columns_in_updated_values(self):
        """
        Verify that _run_fix_map_uuid_missing populates padded separate columns
        (region_code, province_code, city_mun_code, barangay_code, ean, bsn) in updated_values.
        """
        main_layer = self._create_mock_building_layer()

        headers = ["#", "df_x_current", "df_y_current", "df_region_code", "df_province_code", "df_city_mun_code", "df_barangay_code", "df_ean", "df_bsn", "Action"]
        rows = [
            [
                MockTableItem("", check_state=2, roles={0: 1, 4: 1}),
                MockTableItem("120.9144496"),
                MockTableItem("14.27720843"),
                MockTableItem("4"),
                MockTableItem("21"),
                MockTableItem("8"),
                MockTableItem("2"),
                MockTableItem("100"),
                MockTableItem("5"),
                MockTableItem("Edit"),
            ]
        ]
        mock_table = MockTable(headers, rows)

        res = fix_module._run_fix_map_uuid_missing(
            main_layer,
            table=mock_table,
            target_rows=[0],
            prompt_confirm=False,
        )

        self.assertTrue(res["success"])
        row0_updates = res["updated_values"]["row_0"]
        self.assertEqual(row0_updates["region_code"], "04")
        self.assertEqual(row0_updates["province_code"], "021")
        self.assertEqual(row0_updates["city_mun_code"], "08")
        self.assertEqual(row0_updates["barangay_code"], "002")
        self.assertEqual(row0_updates["ean"], "000100")
        self.assertEqual(row0_updates["bsn"], "00005")
        self.assertEqual(row0_updates["bsn_geoid"], "0210800200010000005")


if __name__ == "__main__":
    unittest.main()

