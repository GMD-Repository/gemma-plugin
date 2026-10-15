import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from PyQt5.QtCore import Qt, QVariant
from PyQt5.QtWidgets import QApplication, QWidget
from qgis.core import (
    QgsApplication,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
)

# Ensure plugin root is in sys.path
PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

# Ensure QGIS plugins path is available for processing
QGIS_PLUGINS = r"C:\Program Files\QGIS 3.44.12\apps\qgis-ltr\python\plugins"
if os.path.exists(QGIS_PLUGINS) and QGIS_PLUGINS not in sys.path:
    sys.path.insert(0, QGIS_PLUGINS)

from references.cbms_mv.cbmsmv_dialog import CbmsmvDialog, ensure_processing_initialized
from gmd_scripts.gmdhelpers import (
    add_prefix_to_layer_fields,
    select_mv,
    ensure_processing_initialized as gmd_ensure_processing_initialized,
)


class TestCbmsMvTabSizesAndProcessing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_results_tab_widget_properties(self):
        """Test that results_tab_widget and its tabBar are configured to never elide and not compress."""
        dlg = CbmsmvDialog(None)
        tb = dlg.results_tab_widget.tabBar()
        self.assertIsNotNone(tb)
        self.assertEqual(tb.elideMode(), Qt.ElideNone)
        self.assertFalse(tb.expanding())
        self.assertTrue(tb.usesScrollButtons())
        self.assertTrue(dlg.results_tab_widget.usesScrollButtons())

    def test_config_tab_widget_properties(self):
        """Test that config_tab_widget and its tabBar are configured to never elide and not compress."""
        dlg = CbmsmvDialog(None)
        tb = dlg.config_tab_widget.tabBar()
        self.assertIsNotNone(tb)
        self.assertEqual(tb.elideMode(), Qt.ElideNone)
        self.assertFalse(tb.expanding())
        self.assertTrue(tb.usesScrollButtons())
        self.assertTrue(dlg.config_tab_widget.usesScrollButtons())

    def test_populate_results_workspace_tab_sizing(self):
        """Test that after populating results with various categories and counts, tabs do not elide."""
        dlg = CbmsmvDialog(None)

        # Mock result layers with missing and invalid checks
        dummy_layer = QgsVectorLayer("Point?crs=EPSG:4326", "dummy", "memory")
        dp = dummy_layer.dataProvider()
        dp.addAttributes([QgsField("map_uuid", QVariant.String)])
        dummy_layer.updateFields()

        result_layers = {
            "mv_2027_hp_1a_longitude__invalid": {
                "layer": dummy_layer,
                "rule": {"id": "mv_2027_hp_1a_longitude__invalid", "name": "Invalid coords", "category": "invalid"},
                "count": 3,
            },
            "mv_2027_hp_4b_bsn_geoid__missing": {
                "layer": dummy_layer,
                "rule": {"id": "mv_2027_hp_4b_bsn_geoid__missing", "name": "Missing BSN", "category": "missing"},
                "count": 13,
            },
        }
        exec_summary = [
            {"id": "mv_2027_hp_1a_longitude__invalid", "name": "Invalid coords", "status": "Finished", "features_flagged": 3},
            {"id": "mv_2027_hp_4b_bsn_geoid__missing", "name": "Missing BSN", "status": "Finished", "features_flagged": 13},
        ]

        dlg._populate_results_workspace(exec_summary, result_layers)

        tb = dlg.results_tab_widget.tabBar()
        self.assertEqual(tb.elideMode(), Qt.ElideNone)
        self.assertFalse(tb.expanding())
        self.assertTrue(tb.usesScrollButtons())

        # Check tab texts are fully populated
        tab_texts = [dlg.results_tab_widget.tabText(i) for i in range(dlg.results_tab_widget.count())]
        self.assertTrue(any("Invalid Values (3)" in t for t in tab_texts))
        self.assertTrue(any("Missing / Blank (13)" in t for t in tab_texts))

    def test_ensure_processing_initialized(self):
        """Test that ensure_processing_initialized registers the native provider."""
        ensure_processing_initialized()
        gmd_ensure_processing_initialized()
        reg = QgsApplication.processingRegistry()
        native_provider = reg.providerById("native")
        self.assertIsNotNone(native_provider, "native processing provider should be registered")
        refactor_alg = reg.algorithmById("native:refactorfields")
        self.assertIsNotNone(refactor_alg, "native:refactorfields should be found in registry")

    def test_add_prefix_fallback_when_processing_fails(self):
        """Test that add_prefix_to_layer_fields gracefully falls back to in-memory layer if refactorfields raises."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_points", "memory")
        dp = layer.dataProvider()
        dp.addAttributes([
            QgsField("map_uuid", QVariant.String),
            QgsField("longitude", QVariant.Double),
            QgsField("latitude", QVariant.Double),
            QgsField("x_current", QVariant.String),
        ])
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(120.98, 14.59)))
        feat.setAttributes(["uuid-12345", 120.98, 14.59, "120.98"])
        dp.addFeatures([feat])
        layer.updateExtents()

        # Force processing.run to raise algorithm not found error
        with patch("processing.run", side_effect=Exception("Algorithm native:refactorfields not found")):
            prefixed = add_prefix_to_layer_fields(layer, prefix="sf_")
            self.assertIsNotNone(prefixed)
            self.assertTrue(prefixed.isValid())
            field_names = [f.name() for f in prefixed.fields()]
            self.assertIn("sf_fid", field_names)
            self.assertIn("sf_map_uuid", field_names)
            self.assertIn("sf_longitude", field_names)
            self.assertIn("sf_x_current", field_names)

            # Check that features were copied
            feats = list(prefixed.getFeatures())
            self.assertEqual(len(feats), 1)
            self.assertEqual(feats[0]["sf_map_uuid"], "uuid-12345")

    def test_checkbox_properties_safe_when_disabled(self):
        """Test that should_load_canvas and should_group_layers default safely to False when checkboxes are None."""
        dlg = CbmsmvDialog(None)
        self.assertIsNone(dlg.chk_load_canvas)
        self.assertIsNone(dlg.chk_group_layers)
        self.assertFalse(dlg.should_load_canvas)
        self.assertFalse(dlg.should_group_layers)

    def test_checkbox_properties_with_qcheckbox(self):
        """Test that should_load_canvas and should_group_layers reflect QCheckBox states if attached."""
        from PyQt5.QtWidgets import QCheckBox
        dlg = CbmsmvDialog(None)
        dlg.chk_load_canvas = QCheckBox()
        dlg.chk_group_layers = QCheckBox()

        dlg.chk_load_canvas.setChecked(False)
        dlg.chk_group_layers.setChecked(True)
        self.assertFalse(dlg.should_load_canvas)
        self.assertTrue(dlg.should_group_layers)

        dlg.chk_load_canvas.setChecked(True)
        dlg.chk_group_layers.setChecked(False)
        self.assertTrue(dlg.should_load_canvas)
        self.assertFalse(dlg.should_group_layers)


if __name__ == "__main__":
    unittest.main()

