# -*- coding: utf-8 -*-
"""
Unit tests for delete_selected_features_fix module.
Verifies that deleting selected features sets the boolean is_deleted column to True.
"""
import unittest
from unittest.mock import MagicMock

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsField,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from references.cbms_mv.cbms_mv_fix.delete_selected_features_fix import (
    delete_selected_features,
    mark_feature_deleted,
    sync_feature_status,
    run_fix,
    _is_deleted_val,
)


class TestDeleteSelectedFeaturesFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])

    def _create_mock_layer(self, has_is_deleted_col: bool = True):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_sf", "memory")
        dp = layer.dataProvider()
        fields = [
            QgsField("fid", QVariant.Int),
            QgsField("map_uuid", QVariant.String),
            QgsField("bsn", QVariant.String),
        ]
        if has_is_deleted_col:
            fields.append(QgsField("is_deleted", QVariant.Bool))
        dp.addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(120.9842, 14.5995)))
        feat.setAttribute("fid", 1)
        feat.setAttribute("map_uuid", "uuid-test-001")
        feat.setAttribute("bsn", "0001")
        if has_is_deleted_col:
            feat.setAttribute("is_deleted", False)

        dp.addFeatures([feat])
        layer.updateExtents()
        return layer

    def test_is_deleted_val_helper(self):
        """Test truthy boolean and string values for soft delete."""
        self.assertTrue(_is_deleted_val(True))
        self.assertTrue(_is_deleted_val("true"))
        self.assertTrue(_is_deleted_val("True"))
        self.assertTrue(_is_deleted_val("1"))
        self.assertTrue(_is_deleted_val(1))
        self.assertTrue(_is_deleted_val("deleted"))

        self.assertFalse(_is_deleted_val(False))
        self.assertFalse(_is_deleted_val("false"))
        self.assertFalse(_is_deleted_val("0"))
        self.assertFalse(_is_deleted_val(0))
        self.assertFalse(_is_deleted_val(""))
        self.assertFalse(_is_deleted_val(None))

    def test_run_fix_sets_is_deleted_boolean_to_true(self):
        """Verify run_fix sets boolean is_deleted column to True on target features."""
        layer = self._create_mock_layer(has_is_deleted_col=True)
        res = run_fix(layer, target_uuids=["uuid-test-001"])

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)

        # Verify layer feature attribute
        feat = next(layer.getFeatures())
        self.assertEqual(feat["is_deleted"], True)

        # Verify updated_values payload
        payload = res.get("updated_values", {}).get("uuid-test-001")
        self.assertIsNotNone(payload)
        self.assertTrue(payload.get("is_deleted"))

    def test_run_fix_creates_is_deleted_column_if_missing(self):
        """Verify run_fix dynamically adds is_deleted as QVariant.Bool if missing."""
        layer = self._create_mock_layer(has_is_deleted_col=False)
        self.assertNotIn("is_deleted", [f.name() for f in layer.fields()])

        res = run_fix(layer, target_uuids=["uuid-test-001"])
        self.assertTrue(res.get("success"))
        self.assertIn("is_deleted", [f.name() for f in layer.fields()])

        feat = next(layer.getFeatures())
        self.assertEqual(feat["is_deleted"], True)

    def test_mark_feature_deleted_updates_table_and_layer(self):
        """Verify mark_feature_deleted updates table item to 'true' and layer attribute to True."""
        main_layer = self._create_mock_layer(has_is_deleted_col=True)
        err_layer = self._create_mock_layer(has_is_deleted_col=True)

        table = QTableWidget(1, 3)
        table.setHorizontalHeaderLabels(["", "is_deleted", "Action"])
        item0 = QTableWidgetItem()
        item0.setData(Qt.UserRole, 1)
        item0.setData(Qt.UserRole + 1, "uuid-test-001")
        item0.setData(Qt.UserRole + 3, 1)
        table.setItem(0, 0, item0)

        item_del = QTableWidgetItem("false")
        table.setItem(0, 1, item_del)

        mock_dialog = MagicMock()
        mock_dialog._get_or_load_main_building_layer.return_value = main_layer
        mock_feat = next(main_layer.getFeatures())
        mock_dialog._find_main_feature.return_value = mock_feat

        mark_feature_deleted(
            mock_dialog,
            "test_val",
            err_layer,
            table,
            source_fid=1,
            map_uuid="uuid-test-001",
            prompt_confirm=False,
            target_status="deleted",
            target_row=0,
        )

        # Check table cell text
        self.assertEqual(table.item(0, 1).text(), "true")
        # Check main layer feature
        updated_feat = next(main_layer.getFeatures())
        self.assertEqual(updated_feat["is_deleted"], True)

    def test_sync_feature_status_updates_table_is_deleted_cell(self):
        """Verify sync_feature_status updates is_deleted cell text to 'true'."""
        table = QTableWidget(1, 3)
        table.setHorizontalHeaderLabels(["", "is_deleted", "Action"])
        item0 = QTableWidgetItem()
        item0.setData(Qt.UserRole, 1)
        item0.setData(Qt.UserRole + 1, "uuid-test-001")
        table.setItem(0, 0, item0)
        table.setItem(0, 1, QTableWidgetItem("false"))

        mock_dialog = MagicMock()
        from qgis.PyQt.QtWidgets import QWidget, QTabWidget
        tab_widget = QTabWidget()
        page = QWidget()
        page.setProperty("val_id", "test_val")
        layout = table.setParent(page)
        tab_widget.addTab(page, "Test")
        mock_dialog.results_tab_widget = tab_widget

        sync_feature_status(
            mock_dialog,
            "test_val",
            source_fid=1,
            map_uuid="uuid-test-001",
            new_status="deleted",
        )

        self.assertEqual(table.item(0, 1).text(), "true")

    def test_status_column_is_not_modified(self):
        """Verify that status column is NOT modified when deleting features."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_sf", "memory")
        dp = layer.dataProvider()
        dp.addAttributes([
            QgsField("fid", QVariant.Int),
            QgsField("map_uuid", QVariant.String),
            QgsField("status", QVariant.String),
            QgsField("is_deleted", QVariant.Bool),
        ])
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(120.9842, 14.5995)))
        feat.setAttribute("fid", 1)
        feat.setAttribute("map_uuid", "uuid-test-001")
        feat.setAttribute("status", "original_status")
        feat.setAttribute("is_deleted", False)
        dp.addFeatures([feat])
        layer.updateExtents()

        res = run_fix(layer, target_uuids=["uuid-test-001"])
        self.assertTrue(res.get("success"))

        updated_feat = next(layer.getFeatures())
        self.assertEqual(updated_feat["is_deleted"], True)
        # Ensure status was NOT changed to 'deleted'
        self.assertEqual(updated_feat["status"], "original_status")

        # Verify del_payload does not overwrite status
        payload = res.get("updated_values", {}).get("uuid-test-001")
        self.assertNotIn("status", payload)

    def test_on_table_item_changed_handles_arbitrary_input_and_none_field_name(self):
        """Verify _on_table_item_changed gracefully handles None field_name and arbitrary user text."""
        from references.cbms_mv.cbmsmv_dialog import CbmsmvDialog
        dialog = MagicMock()
        dialog._on_table_item_changed = CbmsmvDialog._on_table_item_changed.__get__(dialog, CbmsmvDialog)
        dialog._style_table_cell = MagicMock()
        dialog._style_row_delete_button = MagicMock()
        dialog.lbl_footer_status = MagicMock()

        main_layer = self._create_mock_layer(has_is_deleted_col=True)
        dialog._get_or_load_main_building_layer.return_value = main_layer
        mock_feat = next(main_layer.getFeatures())
        dialog._find_main_feature.return_value = mock_feat

        table = QTableWidget(1, 3)
        table.setHorizontalHeaderLabels(["", "is_deleted", "Action"])
        item0 = QTableWidgetItem()
        item0.setData(Qt.UserRole, 1)
        item0.setData(Qt.UserRole + 1, "uuid-test-001")
        table.setItem(0, 0, item0)

        # 1. Test None field_name on item without crashing; header fallback resolves to "is_deleted"
        cell = QTableWidgetItem("yes")
        table.setItem(0, 1, cell)

        # Calling _on_table_item_changed should NOT raise AttributeError: 'NoneType' object has no attribute 'lower'
        dialog._on_table_item_changed("val_test", main_layer, table, cell)

        # Should normalize "yes" to "true"
        self.assertEqual(cell.text(), "true")
        self.assertEqual(next(main_layer.getFeatures())["is_deleted"], True)

        # 2. Test typing arbitrary text like "gibberish_string"
        cell.setText("gibberish_string")
        dialog._on_table_item_changed("val_test", main_layer, table, cell)

        # Should normalize arbitrary non-truthy text to "false"
        self.assertEqual(cell.text(), "false")
        self.assertEqual(next(main_layer.getFeatures())["is_deleted"], False)


if __name__ == "__main__":
    unittest.main()


