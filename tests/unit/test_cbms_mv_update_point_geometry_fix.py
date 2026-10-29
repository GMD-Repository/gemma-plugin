# -*- coding: utf-8 -*-
"""
Unit tests for update_point_geometry_fix module.
Verifies updating point geometries of selected and multi-selected rows
using valid sf_longitude and sf_latitude columns.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()

import qgis.core as _qgis_core
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from references.cbms_mv.cbms_mv_fix import cbms_mv_fix, get_fix_handler
from references.cbms_mv.cbms_mv_fix.update_point_geometry_fix import (
    FIX_ID,
    FIX_NAME,
    _is_valid_lat,
    _is_valid_lon,
    _parse_valid_lat,
    _parse_valid_lon,
    run_fix,
    update_point_geometry,
)

IS_MOCK_QGIS = hasattr(_qgis_core, "MockGenericClass")


class TestUpdatePointGeometryFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])

    def _create_main_building_layer(self, crs_authid: str = "EPSG:4326") -> QgsVectorLayer:
        """Create an unprefixed Building Points layer mirroring .geojson schema."""
        layer = QgsVectorLayer(f"Point?crs={crs_authid}", "building_points", "memory")
        dp = layer.dataProvider()
        dp.addAttributes([
            QgsField("fid", QVariant.Int),
            QgsField("map_uuid", QVariant.String),
            QgsField("longitude", QVariant.Double),
            QgsField("latitude", QVariant.Double),
            QgsField("bsn_geoid", QVariant.String),
            QgsField("ea_geocode", QVariant.String),
            QgsField("status", QVariant.String),
            QgsField("remarks", QVariant.String),
        ])
        layer.updateFields()

        initial_rows = [
            (1, "uuid-001", 100.0000, 5.0000, "BSN-ORIG-1", "EA-ORIG-1", "active", "keep-1"),
            (2, "uuid-002", 101.0000, 6.0000, "BSN-ORIG-2", "EA-ORIG-2", "active", "keep-2"),
            (3, "uuid-003", 102.0000, 7.0000, "BSN-ORIG-3", "EA-ORIG-3", "active", "keep-3"),
        ]
        feats = []
        for fid_v, uid, lon, lat, bsn, ea, st, rem in initial_rows:
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
            feat.setAttribute("fid", fid_v)
            feat.setAttribute("map_uuid", uid)
            feat.setAttribute("longitude", lon)
            feat.setAttribute("latitude", lat)
            feat.setAttribute("bsn_geoid", bsn)
            feat.setAttribute("ea_geocode", ea)
            feat.setAttribute("status", st)
            feat.setAttribute("remarks", rem)
            feats.append(feat)

        dp.addFeatures(feats)
        layer.updateExtents()
        return layer

    def _create_error_layer_and_table(self, include_sf_coords: bool = True):
        """Create a prefixed validation error_layer and matching QTableWidget."""
        err_layer = QgsVectorLayer("Point?crs=EPSG:4326", "mv_error_layer", "memory")
        dp = err_layer.dataProvider()
        fields = [
            QgsField("sf_fid", QVariant.Int),
            QgsField("sf_map_uuid", QVariant.String),
            QgsField("df_x_current", QVariant.String),
            QgsField("df_y_current", QVariant.String),
        ]
        if include_sf_coords:
            fields.extend([
                QgsField("sf_longitude", QVariant.String),
                QgsField("sf_latitude", QVariant.String),
            ])
        dp.addAttributes(fields)
        err_layer.updateFields()

        records = [
            (1, "uuid-001", "125.0001", "15.0001", "120.9842", "14.5995"),
            (2, "uuid-002", "125.0002", "15.0002", "121.0437", "14.6760"),
            (3, "uuid-003", "125.0003", "15.0003", "123.8854", "10.3157"),
        ]
        feats = []
        for sf_fid, uid, df_x, df_y, sf_lon, sf_lat in records:
            feat = QgsFeature(err_layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(100.0, 5.0)))
            feat.setAttribute("sf_fid", sf_fid)
            feat.setAttribute("sf_map_uuid", uid)
            feat.setAttribute("df_x_current", df_x)
            feat.setAttribute("df_y_current", df_y)
            if include_sf_coords:
                feat.setAttribute("sf_longitude", sf_lon)
                feat.setAttribute("sf_latitude", sf_lat)
            feats.append(feat)
        dp.addFeatures(feats)
        err_layer.updateExtents()

        field_names = [f.name() for f in err_layer.fields()]
        headers = [""] + field_names + ["Action"]
        table = QTableWidget(len(records), len(headers))
        table.setHorizontalHeaderLabels(headers)
        if hasattr(table, "SelectRows"):
            table.setSelectionBehavior(table.SelectRows)
        if hasattr(table, "setSelectionMode") and hasattr(table, "MultiSelection"):
            table.setSelectionMode(table.MultiSelection)

        for row_idx, feat in enumerate(err_layer.getFeatures()):
            chk = QTableWidgetItem()
            if hasattr(chk, "setFlags") and hasattr(Qt, "ItemIsUserCheckable"):
                chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, feat["sf_fid"])
            chk.setData(Qt.UserRole + 1, feat["sf_map_uuid"])
            chk.setData(Qt.UserRole + 3, feat.id())
            chk.setData(Qt.UserRole + 6, feat["sf_fid"])
            chk.setData(Qt.UserRole + 7, feat["sf_map_uuid"])
            table.setItem(row_idx, 0, chk)

            for c_idx, fname in enumerate(field_names):
                cell = QTableWidgetItem(str(feat[fname]))
                cell.setData(Qt.UserRole + 2, fname)
                table.setItem(row_idx, c_idx + 1, cell)

        return err_layer, table

    def _feat_by_uuid(self, layer: QgsVectorLayer, target_uuid: str) -> QgsFeature:
        col = "map_uuid" if "map_uuid" in [f.name() for f in layer.fields()] else "sf_map_uuid"
        for f in layer.getFeatures():
            if f[col] == target_uuid:
                return f
        raise AssertionError(f"Feature {target_uuid} not found")

    def test_coordinate_validation_helpers(self):
        """Verify valid and invalid WGS84 longitude and latitude parsing."""
        self.assertAlmostEqual(_parse_valid_lon("120.9842"), 120.9842)
        self.assertAlmostEqual(_parse_valid_lat("14.5995"), 14.5995)
        self.assertTrue(_is_valid_lon(-180.0))
        self.assertTrue(_is_valid_lon(180.0))
        self.assertTrue(_is_valid_lat(-90.0))
        self.assertTrue(_is_valid_lat(90.0))

        # Invalid values
        for bad in (None, "", "NULL", "None", "nan", "inf", 0, "0.0", True, False):
            self.assertFalse(_is_valid_lon(bad))
            self.assertFalse(_is_valid_lat(bad))

        self.assertFalse(_is_valid_lon(180.5))
        self.assertFalse(_is_valid_lon(-181.0))
        self.assertFalse(_is_valid_lat(90.1))
        self.assertFalse(_is_valid_lat(-95.0))
        self.assertFalse(_is_valid_lat("121.0437"))  # Swapped Philippine longitude into latitude

    def test_dispatcher_routes_without_collision(self):
        """Verify get_fix_handler and cbms_mv_fix route update_point_geometry without colliding."""
        self.assertEqual(FIX_ID, "update_point_geometry")
        self.assertIn("sf_longitude", FIX_NAME)
        self.assertIn("sf_latitude", FIX_NAME)

        handler = get_fix_handler("update_point_geometry")
        self.assertIs(handler, run_fix)
        self.assertIsNot(get_fix_handler("generate_point_geometry"), run_fix)
        self.assertIsNot(get_fix_handler("update_datafile_coordinates"), run_fix)
        self.assertIs(
            get_fix_handler("update_coordinates_using_sf_longitude_and_sf_latitude"),
            run_fix,
        )
        self.assertIn(FIX_ID, cbms_mv_fix.FIX_REGISTRY)

    def test_updates_geometry_for_multi_checked_rows_only(self):
        """Verify multi-checked rows update point geometry while unchecked rows and unrelated attributes remain intact."""
        main_layer = self._create_main_building_layer()
        err_layer, table = self._create_error_layer_and_table(include_sf_coords=True)

        # Check rows 0 and 2; leave row 1 unchecked
        table.item(0, 0).setCheckState(Qt.Checked)
        table.item(2, 0).setCheckState(Qt.Checked)

        res = run_fix(
            main_layer,
            error_layer=err_layer,
            table=table,
            prompt_confirm=False,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 2)
        self.assertEqual(main_layer.featureCount(), 3)

        f1 = self._feat_by_uuid(main_layer, "uuid-001")
        f2 = self._feat_by_uuid(main_layer, "uuid-002")
        f3 = self._feat_by_uuid(main_layer, "uuid-003")

        self.assertAlmostEqual(f1.geometry().asPoint().x(), 120.9842, places=6)
        self.assertAlmostEqual(f1.geometry().asPoint().y(), 14.5995, places=6)

        # Row 1 was unchecked -> must remain at (101.0, 6.0)
        self.assertAlmostEqual(f2.geometry().asPoint().x(), 101.0000, places=6)
        self.assertAlmostEqual(f2.geometry().asPoint().y(), 6.0000, places=6)

        self.assertAlmostEqual(f3.geometry().asPoint().x(), 123.8854, places=6)
        self.assertAlmostEqual(f3.geometry().asPoint().y(), 10.3157, places=6)

        # Unrelated attributes must remain unmodified
        self.assertEqual(f1["bsn_geoid"], "BSN-ORIG-1")
        self.assertEqual(f1["ea_geocode"], "EA-ORIG-1")
        self.assertEqual(f1["status"], "active")
        self.assertEqual(f1["remarks"], "keep-1")

        # Payload must NOT contain df_* or map_uuid keys
        payload = res["updated_values"]["row_0"]
        self.assertEqual(payload["sf_longitude"], "120.9842")
        self.assertEqual(payload["sf_latitude"], "14.5995")
        self.assertFalse(any(k.startswith("df_") for k in payload.keys()))
        self.assertNotIn("map_uuid", payload)

    def test_updates_geometry_for_multi_selected_rows_via_selection_model(self):
        """Verify multi-selected rows via QTableWidget selectionModel update geometry even when checkboxes are unchecked."""
        main_layer = self._create_main_building_layer()
        err_layer, table = self._create_error_layer_and_table(include_sf_coords=True)

        # Multi-select rows 1 and 2 without checking Column 0 checkboxes
        table.selectRow(1)
        table.selectRow(2)

        res = run_fix(
            main_layer,
            error_layer=err_layer,
            table=table,
            prompt_confirm=False,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 2)

        f1 = self._feat_by_uuid(main_layer, "uuid-001")
        f2 = self._feat_by_uuid(main_layer, "uuid-002")
        f3 = self._feat_by_uuid(main_layer, "uuid-003")

        # Row 0 untouched
        self.assertAlmostEqual(f1.geometry().asPoint().x(), 100.0000, places=6)
        self.assertAlmostEqual(f1.geometry().asPoint().y(), 5.0000, places=6)

        # Rows 1 and 2 updated
        self.assertAlmostEqual(f2.geometry().asPoint().x(), 121.0437, places=6)
        self.assertAlmostEqual(f2.geometry().asPoint().y(), 14.6760, places=6)
        self.assertAlmostEqual(f3.geometry().asPoint().x(), 123.8854, places=6)
        self.assertAlmostEqual(f3.geometry().asPoint().y(), 10.3157, places=6)

    def test_missing_sf_longitude_and_sf_latitude_columns_rejected(self):
        """Verify missing sf_longitude/sf_latitude columns fail cleanly without falling back to df_x_current/df_y_current."""
        main_layer = self._create_main_building_layer()
        err_layer, table = self._create_error_layer_and_table(include_sf_coords=False)
        table.item(0, 0).setCheckState(Qt.Checked)

        res = run_fix(
            main_layer,
            error_layer=err_layer,
            table=table,
            prompt_confirm=False,
        )
        self.assertFalse(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 0)
        self.assertIn("sf_longitude", res.get("message", ""))

        # Geometry must NOT have used df_x_current (125.0001)
        f1 = self._feat_by_uuid(main_layer, "uuid-001")
        self.assertAlmostEqual(f1.geometry().asPoint().x(), 100.0000, places=6)
        self.assertAlmostEqual(f1.geometry().asPoint().y(), 5.0000, places=6)

    def test_invalid_coordinates_rejected_and_mixed_batch_skips_invalid(self):
        """Verify invalid sf_longitude/sf_latitude values are rejected or skipped safely."""
        main_layer = self._create_main_building_layer()
        err_layer, table = self._create_error_layer_and_table(include_sf_coords=True)

        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        lon_col = headers.index("sf_longitude")
        lat_col = headers.index("sf_latitude")

        # Set Row 0 to out-of-range longitude, Row 1 to empty/NULL latitude
        table.item(0, lon_col).setText("1210.9842")
        table.item(1, lat_col).setText("NULL")

        # 1. Selecting only invalid rows -> fails with 0 fixed
        table.item(0, 0).setCheckState(Qt.Checked)
        table.item(1, 0).setCheckState(Qt.Checked)
        res_bad = run_fix(main_layer, error_layer=err_layer, table=table, prompt_confirm=False)
        self.assertFalse(res_bad.get("success"))
        self.assertEqual(res_bad.get("fixed_count"), 0)

        # 2. Adding valid Row 2 -> updates Row 2 and skips Rows 0 and 1
        table.item(2, 0).setCheckState(Qt.Checked)
        res_mixed = run_fix(main_layer, error_layer=err_layer, table=table, prompt_confirm=False)
        self.assertTrue(res_mixed.get("success"))
        self.assertEqual(res_mixed.get("fixed_count"), 1)

        f1 = self._feat_by_uuid(main_layer, "uuid-001")
        f2 = self._feat_by_uuid(main_layer, "uuid-002")
        f3 = self._feat_by_uuid(main_layer, "uuid-003")
        self.assertAlmostEqual(f1.geometry().asPoint().x(), 100.0000, places=6)
        self.assertAlmostEqual(f2.geometry().asPoint().x(), 101.0000, places=6)
        self.assertAlmostEqual(f3.geometry().asPoint().x(), 123.8854, places=6)
        self.assertAlmostEqual(f3.geometry().asPoint().y(), 10.3157, places=6)

    def test_projected_crs_transformation_and_headless_mode(self):
        """Verify WGS84 sf_longitude/sf_latitude updates via cbms_mv_fix.run_fix in headless mode."""
        projected_main = self._create_main_building_layer(crs_authid="EPSG:32651")
        err_layer, _ = self._create_error_layer_and_table(include_sf_coords=True)

        res = cbms_mv_fix.run_fix(
            projected_main,
            val_id="update_point_geometry",
            error_layer=err_layer,
            target_uuids=["uuid-001"],
            prompt_confirm=False,
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)

        f1 = self._feat_by_uuid(projected_main, "uuid-001")
        pt = f1.geometry().asPoint()
        if IS_MOCK_QGIS:
            self.assertAlmostEqual(pt.x(), 120.9842, places=6)
            self.assertAlmostEqual(pt.y(), 14.5995, places=6)
        else:
            # Manila (120.9842 E, 14.5995 N) in UTM Zone 51N is ~282,800m E, ~1,614,900m N
            self.assertTrue(200000.0 < pt.x() < 400000.0)
            self.assertTrue(1500000.0 < pt.y() < 1700000.0)

    def test_dialog_process_wrapper_delegates_to_fix_selected_features(self):
        """Verify update_point_geometry delegates to dialog._fix_selected_features when available."""
        err_layer, table = self._create_error_layer_and_table(include_sf_coords=True)
        mock_dialog = MagicMock()
        update_point_geometry(mock_dialog, err_layer, table)
        mock_dialog._fix_selected_features.assert_called_once_with(
            "update_point_geometry",
            err_layer,
            table,
        )

    def test_cbmsmv_dialog_execute_fix_leaves_pending_json_edits_clean(self):
        """Verify CbmsmvDialog._execute_fix updates geometry, unchecks rows, and does not dirty _pending_json_edits."""
        from unittest.mock import patch
        from references.cbms_mv.cbms_mv_fix.common import is_valid_qobject as common_is_valid_qobject
        from references.cbms_mv.cbmsmv_dialog import CbmsmvDialog

        main_layer = self._create_main_building_layer()
        err_layer, table = self._create_error_layer_and_table(include_sf_coords=True)
        if not hasattr(table, "setProperty"):
            table.setProperty = MagicMock()

        # Attach df_fid and df_uuid metadata to row 0 checkbox to simulate joined table rows
        table.item(0, 0).setData(Qt.UserRole + 4, 10)
        table.item(0, 0).setData(Qt.UserRole + 5, "df-uuid-001")
        table.item(0, 0).setCheckState(Qt.Checked)

        dialog = MagicMock()
        dialog._pending_json_edits = {}
        dialog.iface = None
        dialog.lbl_footer_status = MagicMock()
        dialog._style_table_cell = MagicMock()
        dialog._style_row_fix_button = MagicMock()
        dialog._get_or_load_main_building_layer.return_value = main_layer
        dialog._find_main_feature = CbmsmvDialog._find_main_feature.__get__(dialog, CbmsmvDialog)
        dialog._fix_selected_features = CbmsmvDialog._fix_selected_features.__get__(dialog, CbmsmvDialog)
        dialog._execute_fix = CbmsmvDialog._execute_fix.__get__(dialog, CbmsmvDialog)
        dialog._on_update_point_geometry = CbmsmvDialog._on_update_point_geometry.__get__(dialog, CbmsmvDialog)

        with patch("references.cbms_mv.cbmsmv_dialog.QMessageBox"), patch(
            "references.cbms_mv.cbmsmv_dialog.is_valid_qobject",
            side_effect=common_is_valid_qobject,
        ):
            dialog._on_update_point_geometry(err_layer, table)

        f1 = self._feat_by_uuid(main_layer, "uuid-001")
        self.assertAlmostEqual(f1.geometry().asPoint().x(), 120.9842, places=6)
        self.assertAlmostEqual(f1.geometry().asPoint().y(), 14.5995, places=6)
        self.assertEqual(table.item(0, 0).checkState(), Qt.Unchecked)
        self.assertEqual(dialog._pending_json_edits, {})


if __name__ == "__main__":
    unittest.main()
