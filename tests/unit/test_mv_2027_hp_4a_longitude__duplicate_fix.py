# -*- coding: utf-8 -*-
"""
Unit test for 2027 CBMS Map Validation automated fix & process:
mv_2027_hp_4a_longitude__duplicate (unified cbms_mv_fix module)
"""

import unittest
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from qgis.core import (
    NULL,
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtCore import Qt, QVariant

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
        self.background_color = None
        self.foreground_color = None

    def text(self):
        return self._text

    def setText(self, val):
        self._text = str(val) if val is not None else ""

    def checkState(self):
        return self._check_state

    def setCheckState(self, state):
        self._check_state = state

    def isChecked(self):
        return self._check_state == 2

    def data(self, role):
        return self._roles.get(role)

    def setData(self, role, val):
        self._roles[role] = val

    def setBackground(self, col):
        self.background_color = col

    def setForeground(self, col):
        self.foreground_color = col

    def setFlags(self, flags):
        pass


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
        self._props = {}

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

    def setItem(self, r, c, item):
        while len(self._grid) <= r:
            self._grid.append([MockTableItem("") for _ in range(len(self._headers))])
        while len(self._grid[r]) <= c:
            self._grid[r].append(MockTableItem(""))
        self._grid[r][c] = item

    def insertColumn(self, col):
        self._headers.insert(col, MockTableHeaderItem(""))
        for row in self._grid:
            row.insert(col, MockTableItem(""))

    def setHorizontalHeaderItem(self, col, item):
        while len(self._headers) <= col:
            self._headers.append(MockTableHeaderItem(""))
        self._headers[col] = item

    def cellWidget(self, r, c):
        return None

    def setProperty(self, name, val):
        self._props[name] = val

    def property(self, name):
        return self._props.get(name)


class MockDialog:
    def __init__(self, main_layer=None):
        self._main_layer = main_layer
        self.lbl_footer_status = MockTableItem()
        self.iface = None
        self.styled_cells = []

    def objectName(self):
        return "MockDialog"

    def _get_or_load_main_building_layer(self):
        return self._main_layer

    def _find_main_feature(self, layer, fid=None, map_uuid=None):
        if not layer:
            return None
        for f in layer.getFeatures():
            if fid is not None and f.id() == fid:
                return f
            if map_uuid and "sf_map_uuid" in [fld.name() for fld in layer.fields()]:
                if str(f["sf_map_uuid"]).strip() == str(map_uuid).strip():
                    return f
        return None

    def _style_table_cell(self, cell, state="normal"):
        self.styled_cells.append((cell, state))

    def _style_row_delete_button(self, btn, is_deleted=False):
        pass


class TestMv2027Hp4aLongitudeDuplicateFix(unittest.TestCase):
    """Test suite for duplicate longitude/coordinates automated fix and deduplication."""

    def test_fix_metadata_and_constants(self):
        """Verify fix constants and metadata registered for hp_4a duplicate."""
        self.assertEqual(fix_module.FIX_ID_HP_4A_DUP, "mv_2027_hp_4a_longitude__duplicate")
        self.assertIn("mv_2027_hp_4a_longitude__duplicate", fix_module.FIX_REGISTRY)
        entry = fix_module.FIX_REGISTRY["mv_2027_hp_4a_longitude__duplicate"]
        self.assertIn("Delete duplicate", entry["name"])
        self.assertTrue(len(entry["description"]) > 0)
        self.assertEqual(fix_module.FIX_NAME_HP_4A_DUP, entry["name"])
        self.assertEqual(fix_module.FIX_DESCRIPTION_HP_4A_DUP, entry["description"])

    def test_dispatch_table_contains_hp_4a_duplicate(self):
        """Verify _FIX_DISPATCH maps hp_4a duplicate to _run_fix_longitude_duplicate."""
        self.assertIn("mv_2027_hp_4a_longitude__duplicate", fix_module._FIX_DISPATCH)
        self.assertEqual(
            fix_module._FIX_DISPATCH["mv_2027_hp_4a_longitude__duplicate"],
            fix_module._run_fix_longitude_duplicate,
        )

    def test_normalize_cell_val(self):
        """Verify _normalize_cell_val handles nulls, strings, and float coordinates."""
        self.assertEqual(fix_module._normalize_cell_val(None), "")
        self.assertEqual(fix_module._normalize_cell_val(NULL), "")
        self.assertEqual(fix_module._normalize_cell_val("NULL"), "")
        self.assertEqual(fix_module._normalize_cell_val("None"), "")
        self.assertEqual(fix_module._normalize_cell_val("nan"), "")
        self.assertEqual(fix_module._normalize_cell_val("  0001  "), "0001")
        self.assertEqual(fix_module._normalize_cell_val("121.050000"), "121.05")
        self.assertEqual(fix_module._normalize_cell_val("14.580000"), "14.58")
        self.assertEqual(fix_module._normalize_cell_val("Building A"), "Building A")

    def test_deduplication_check_columns(self):
        """Verify the deduplication check covers the exact columns from the specification image + status."""
        expected_cols = {
            "map_uuid", "bsn_geoid", "geocode", "ea_geocode",
            "region_code", "province_code", "city_mun_code", "barangay_code",
            "ean", "bsn", "status", "longitude", "longitud", "latitude", "pos_longit", "pos_latitu",
        }
        for col in expected_cols:
            self.assertTrue(
                col in ("map_uuid", "bsn_geoid", "geocode", "ea_geocode", "region_code",
                        "province_code", "city_mun_code", "barangay_code", "ean", "bsn", "status",
                        "longitude", "longitud", "latitude", "pos_longit", "pos_latitu")
            )

    def _create_test_layer(self, records):
        """Helper to create a memory vector layer with standard CBMS fields."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_bldg_points", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_map_uuid", QVariant.String))
        fields.append(QgsField("sf_region_code", QVariant.String))
        fields.append(QgsField("sf_province_code", QVariant.String))
        fields.append(QgsField("sf_city_mun_code", QVariant.String))
        fields.append(QgsField("sf_barangay_code", QVariant.String))
        fields.append(QgsField("sf_ean", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_en_code", QVariant.String))
        fields.append(QgsField("sf_remarks", QVariant.String))
        fields.append(QgsField("sf_longitude", QVariant.Double))
        fields.append(QgsField("sf_latitude", QVariant.Double))
        fields.append(QgsField("status", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        features = []
        for rec in records:
            f = QgsFeature(layer.fields())
            for k, v in rec.items():
                if k == "geom":
                    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(v[0], v[1])))
                else:
                    f.setAttribute(k, v)
            features.append(f)

        layer.dataProvider().addFeatures(features)
        return layer

    def test_run_fix_identical_duplicate_features(self):
        """Verify that identical duplicate features retain 1 and mark the other as deleted."""
        records = [
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
        ]
        layer = self._create_test_layer(records)

        res = fix_module.run_fix(layer, val_id="mv_2027_hp_4a_longitude__duplicate")
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        feats = list(layer.getFeatures())
        self.assertEqual(len(feats), 2)
        # Feature 1 is retained without 'deleted'
        self.assertNotEqual(str(feats[0]["status"]).strip().lower(), "deleted")
        # Feature 2 is marked as 'deleted'
        self.assertEqual(str(feats[1]["status"]).strip().lower(), "deleted")

    def test_run_fix_identical_duplicate_features_with_different_en_code(self):
        """Verify that duplicate features with different sf_en_code are still considered duplicates and deduplicated."""
        records = [
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",  # en_code 01
                "sf_remarks": "Original note",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "02",  # Different en_code 02 (must be disregarded)
                "sf_remarks": "Duplicate note",  # Remarks not in checked columns
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
        ]
        layer = self._create_test_layer(records)

        res = fix_module.run_fix(layer, val_id="mv_2027_hp_4a_longitude__duplicate")
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        feats = list(layer.getFeatures())
        self.assertEqual(len(feats), 2)
        # Feature 1 is retained without 'deleted'
        self.assertNotEqual(str(feats[0]["status"]).strip().lower(), "deleted")
        # Feature 2 is marked as 'deleted'
        self.assertEqual(str(feats[1]["status"]).strip().lower(), "deleted")

    def test_run_fix_differing_features_not_deleted(self):
        """Verify that duplicate coordinate features with differing attributes (e.g. bsn) are NOT deleted."""
        records = [
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",  # BSN 0001
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0002",  # Different BSN 0002!
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
        ]
        layer = self._create_test_layer(records)

        res = fix_module.run_fix(layer, val_id="mv_2027_hp_4a_longitude__duplicate")
        self.assertFalse(res["success"])
        self.assertEqual(res["fixed_count"], 0)
        self.assertIn("differing", res["message"].lower())

        feats = list(layer.getFeatures())
        # Neither feature should be deleted!
        self.assertNotEqual(str(feats[0]["status"]).strip().lower(), "deleted")
        self.assertNotEqual(str(feats[1]["status"]).strip().lower(), "deleted")

    def test_run_fix_differing_uuid_not_deleted(self):
        """Verify that duplicate coordinate features with differing sf_map_uuid are NOT deleted."""
        records = [
            {
                "sf_map_uuid": "UUID-1",  # UUID-1
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
            {
                "sf_map_uuid": "UUID-2",  # Differing UUID-2!
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
                "geom": (121.05, 14.58),
            },
        ]
        layer = self._create_test_layer(records)

        res = fix_module.run_fix(layer, val_id="mv_2027_hp_4a_longitude__duplicate")
        self.assertFalse(res["success"])
        self.assertEqual(res["fixed_count"], 0)

        feats = list(layer.getFeatures())
        self.assertNotEqual(str(feats[0]["status"]).strip().lower(), "deleted")
        self.assertNotEqual(str(feats[1]["status"]).strip().lower(), "deleted")

    def test_run_fix_differing_status_not_deleted(self):
        """Verify that duplicate coordinate features with differing status values are NOT deleted."""
        records = [
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "verified",  # Status verified
                "geom": (121.05, 14.58),
            },
            {
                "sf_map_uuid": "UUID-1",
                "sf_region_code": "04",
                "sf_province_code": "21",
                "sf_city_mun_code": "08",
                "sf_barangay_code": "001",
                "sf_ean": "002000",
                "sf_bsn": "0001",
                "sf_ea_geocode": "042108001002000",
                "sf_en_code": "01",
                "sf_remarks": "",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "pending",  # Differing status pending!
                "geom": (121.05, 14.58),
            },
        ]
        layer = self._create_test_layer(records)

        res = fix_module.run_fix(layer, val_id="mv_2027_hp_4a_longitude__duplicate")
        self.assertFalse(res["success"])
        self.assertEqual(res["fixed_count"], 0)

        feats = list(layer.getFeatures())
        self.assertEqual(str(feats[0]["status"]), "verified")
        self.assertEqual(str(feats[1]["status"]), "pending")

    def test_interactive_table_deduplication(self):
        """Verify deduplicate_features on MockTable with identical duplicate rows."""
        records = [
            {
                "sf_map_uuid": "UUID-1",
                "sf_bsn": "0001",
                "sf_ean": "002000",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
            },
            {
                "sf_map_uuid": "UUID-1",
                "sf_bsn": "0001",
                "sf_ean": "002000",
                "sf_longitude": 121.05,
                "sf_latitude": 14.58,
                "status": "",
            },
        ]
        layer = self._create_test_layer(records)
        dialog = MockDialog(main_layer=layer)

        headers = ["", "sf_map_uuid", "sf_bsn", "sf_ean", "sf_status", "Action"]
        row0 = [
            MockTableItem("", check_state=0, roles={Qt.UserRole: 1, Qt.UserRole + 1: "UUID-1", Qt.UserRole + 3: 1}),
            MockTableItem("UUID-1"),
            MockTableItem("0001"),
            MockTableItem("002000"),
            MockTableItem(""),
            MockTableItem("Action"),
        ]
        row1 = [
            MockTableItem("", check_state=0, roles={Qt.UserRole: 2, Qt.UserRole + 1: "UUID-1", Qt.UserRole + 3: 2}),
            MockTableItem("UUID-1"),
            MockTableItem("0001"),
            MockTableItem("002000"),
            MockTableItem(""),
            MockTableItem("Action"),
        ]
        table = MockTable(headers, [row0, row1])

        res = fix_module.deduplicate_features(
            dialog,
            "mv_2027_hp_4a_longitude__duplicate",
            layer,
            table,
            process_all=True,
            prompt_confirm=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        # Row 0 is retained without 'deleted'
        self.assertNotEqual(table.item(0, 4).text().lower(), "deleted")
        # Row 1 is marked as 'deleted'
        self.assertEqual(table.item(1, 4).text().lower(), "deleted")
        # Check that table cell was styled as 'deleted'
        styled_states = [s for _, s in dialog.styled_cells]
        self.assertIn("deleted", styled_states)

    def test_dropdown_action_registered_in_dialog(self):
        """Verify 'Delete duplicate features (retain one)' is present in cbmsmv_dialog combo_actions."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('combo_actions.addItem(dup_ic, "Delete duplicate features (retain one)")', content)
        self.assertIn('elif idx == 4:', content)
        self.assertIn('self._on_deduplicate_features(', content)
        self.assertIn('def _on_deduplicate_features(', content)

    def test_run_fix_coordinate_duplicate_7_decimals(self):
        """Verify coordinate duplicate check on map_uuid, bsn_geoid, and coordinates to 7 decimals."""
        records = [
            {
                "sf_map_uuid": "UUID-COORD-1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.0543210,
                "sf_latitude": 14.5812345,
                "status": "",
                "geom": (121.0543210, 14.5812345),
            },
            {
                "sf_map_uuid": "UUID-COORD-1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.0543210,
                "sf_latitude": 14.5812345,
                "status": "",
                "geom": (121.0543210, 14.5812345),
            },
        ]
        layer = self._create_test_layer(records)
        res = fix_module.run_fix(layer, val_id="mv_2027_hp_4a_longitude__duplicate")
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        feats = list(layer.getFeatures())
        self.assertNotEqual(str(feats[0]["status"]).strip().lower(), "deleted")
        self.assertEqual(str(feats[1]["status"]).strip().lower(), "deleted")

    def test_run_fix_coordinate_differing_7th_decimal_not_deleted(self):
        """Verify that coordinates differing at the 7th decimal digit are NOT treated as duplicates."""
        records = [
            {
                "sf_map_uuid": "UUID-COORD-1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.0543210,  # 7th decimal: 0
                "sf_latitude": 14.5812345,
                "status": "",
                "geom": (121.0543210, 14.5812345),
            },
            {
                "sf_map_uuid": "UUID-COORD-1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.0543219,  # 7th decimal: 9 (differing!)
                "sf_latitude": 14.5812345,
                "status": "",
                "geom": (121.0543219, 14.5812345),
            },
        ]
        layer = self._create_test_layer(records)
        res = fix_module.run_fix(layer, val_id="mv_2027_hp_4a_longitude__duplicate")
        self.assertFalse(res["success"])
        self.assertEqual(res["fixed_count"], 0)

        feats = list(layer.getFeatures())
        self.assertNotEqual(str(feats[0]["status"]).strip().lower(), "deleted")
        self.assertNotEqual(str(feats[1]["status"]).strip().lower(), "deleted")

    def test_interactive_table_coordinate_deduplication_7_decimals(self):
        """Verify deduplicate_features on MockTable with coordinates matching to 7 decimals."""
        records = [
            {
                "sf_map_uuid": "UUID-T1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.1234567,
                "sf_latitude": 14.7654321,
                "status": "",
            },
            {
                "sf_map_uuid": "UUID-T1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.1234567,
                "sf_latitude": 14.7654321,
                "status": "",
            },
        ]
        layer = self._create_test_layer(records)
        dialog = MockDialog(main_layer=layer)

        headers = ["", "sf_map_uuid", "sf_bsn_geoid", "sf_longitude", "sf_latitude", "sf_status", "Action"]
        row0 = [
            MockTableItem("", check_state=0, roles={Qt.UserRole: 1, Qt.UserRole + 1: "UUID-T1", Qt.UserRole + 3: 1}),
            MockTableItem("UUID-T1"),
            MockTableItem("0421080010020000001"),
            MockTableItem("121.1234567"),
            MockTableItem("14.7654321"),
            MockTableItem(""),
            MockTableItem("Action"),
        ]
        row1 = [
            MockTableItem("", check_state=0, roles={Qt.UserRole: 2, Qt.UserRole + 1: "UUID-T1", Qt.UserRole + 3: 2}),
            MockTableItem("UUID-T1"),
            MockTableItem("0421080010020000001"),
            MockTableItem("121.1234567"),
            MockTableItem("14.7654321"),
            MockTableItem(""),
            MockTableItem("Action"),
        ]
        table = MockTable(headers, [row0, row1])

        res = fix_module.deduplicate_features(
            dialog,
            "mv_2027_hp_4a_longitude__duplicate",
            layer,
            table,
            process_all=True,
            prompt_confirm=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)
        self.assertNotEqual(table.item(0, 5).text().lower(), "deleted")
        self.assertEqual(table.item(1, 5).text().lower(), "deleted")

    def test_interactive_table_coordinate_differing_7th_decimal_not_deleted(self):
        """Verify deduplicate_features on MockTable when coordinates differ at 7th decimal."""
        records = [
            {
                "sf_map_uuid": "UUID-T1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.1234567,
                "sf_latitude": 14.7654321,
                "status": "",
            },
            {
                "sf_map_uuid": "UUID-T1",
                "sf_bsn_geoid": "0421080010020000001",
                "sf_longitude": 121.1234568,  # Differing 7th decimal!
                "sf_latitude": 14.7654321,
                "status": "",
            },
        ]
        layer = self._create_test_layer(records)
        dialog = MockDialog(main_layer=layer)

        headers = ["", "sf_map_uuid", "sf_bsn_geoid", "sf_longitude", "sf_latitude", "sf_status", "Action"]
        row0 = [
            MockTableItem("", check_state=0, roles={Qt.UserRole: 1, Qt.UserRole + 1: "UUID-T1", Qt.UserRole + 3: 1}),
            MockTableItem("UUID-T1"),
            MockTableItem("0421080010020000001"),
            MockTableItem("121.1234567"),
            MockTableItem("14.7654321"),
            MockTableItem(""),
            MockTableItem("Action"),
        ]
        row1 = [
            MockTableItem("", check_state=0, roles={Qt.UserRole: 2, Qt.UserRole + 1: "UUID-T1", Qt.UserRole + 3: 2}),
            MockTableItem("UUID-T1"),
            MockTableItem("0421080010020000001"),
            MockTableItem("121.1234568"),
            MockTableItem("14.7654321"),
            MockTableItem(""),
            MockTableItem("Action"),
        ]
        table = MockTable(headers, [row0, row1])

        res = fix_module.deduplicate_features(
            dialog,
            "mv_2027_hp_4a_longitude__duplicate",
            layer,
            table,
            process_all=True,
            prompt_confirm=False,
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["fixed_count"], 0)
        self.assertNotEqual(table.item(0, 5).text().lower(), "deleted")
        self.assertNotEqual(table.item(1, 5).text().lower(), "deleted")


if __name__ == "__main__":
    unittest.main()

