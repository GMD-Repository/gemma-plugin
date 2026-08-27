# -*- coding: utf-8 -*-
"""
Unit tests for pre_ea_detector helper module.
Verifies dynamic drive scanning, standard folder structure discovery,
Scenario 1 (1_Reset EAs) vs Scenario 2 (2_Adjusted EAs), and diagnostics.
"""

import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()

from references.create_enumeration_area.helpers.pre_ea_detector import (
    detect_available_drives,
    scan_psa_gis_projects,
    find_generated_ea_layer,
    resolve_target_output_folder,
)


class TestPreEaDetector(unittest.TestCase):
    """Test suite for PSA-GIS / Project 1MAP generated EA detection."""

    def setUp(self):
        self.temp_root = tempfile.mkdtemp(prefix="test_psa_gis_")

    def tearDown(self):
        if os.path.exists(self.temp_root):
            shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_detect_available_drives(self):
        """Verify that drive detection returns at least one valid drive."""
        drives = detect_available_drives()
        self.assertIsInstance(drives, list)
        self.assertGreater(len(drives), 0)

    def test_scan_psa_gis_projects_found(self):
        """Test scanning valid project structure across simulated drive."""
        # Create structure: <temp_root>/PSA-GIS/Ilocos Norte/Project 1MAP/3_EA Delineation and Merging/2_Pre-Processing
        prep_dir = os.path.join(
            self.temp_root, "PSA-GIS", "Ilocos Norte",
            "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing"
        )
        os.makedirs(prep_dir, exist_ok=True)

        valid_projects, diagnostics = scan_psa_gis_projects(custom_drives=[self.temp_root])

        self.assertTrue(diagnostics['psa_gis_found'])
        self.assertTrue(diagnostics['project_1map_found'])
        self.assertTrue(diagnostics['prep_found'])
        self.assertEqual(len(valid_projects), 1)
        self.assertEqual(valid_projects[0]['province'], "Ilocos Norte")
        self.assertEqual(os.path.normpath(valid_projects[0]['prep_dir']), os.path.normpath(prep_dir))

    def test_scan_psa_gis_projects_multiple_provinces(self):
        """Test scanning when multiple provinces exist."""
        for prov in ["Laguna", "Batangas"]:
            prep = os.path.join(
                self.temp_root, "PSA-GIS", prov,
                "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing"
            )
            os.makedirs(prep, exist_ok=True)

        valid_projects, diagnostics = scan_psa_gis_projects(custom_drives=[self.temp_root])
        self.assertEqual(len(valid_projects), 2)
        provinces = {p['province'] for p in valid_projects}
        self.assertEqual(provinces, {"Laguna", "Batangas"})

    def test_scan_psa_gis_missing_folders_diagnostics(self):
        """Test diagnostic flags when parts of the hierarchy are missing."""
        # Empty drive
        empty_dir = tempfile.mkdtemp()
        try:
            projects, diag = scan_psa_gis_projects(custom_drives=[empty_dir])
            self.assertFalse(diag['psa_gis_found'])
            self.assertFalse(diag['project_1map_found'])
            self.assertFalse(diag['prep_found'])
            self.assertEqual(len(projects), 0)
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

        # PSA-GIS present, but no Project 1MAP
        psa_only_dir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(psa_only_dir, "PSA-GIS", "Cavite"), exist_ok=True)
            projects, diag = scan_psa_gis_projects(custom_drives=[psa_only_dir])
            self.assertTrue(diag['psa_gis_found'])
            self.assertFalse(diag['project_1map_found'])
            self.assertFalse(diag['prep_found'])
            self.assertEqual(len(projects), 0)
        finally:
            shutil.rmtree(psa_only_dir, ignore_errors=True)

    def test_find_generated_ea_layer_scenario_1_no_input(self):
        """Scenario 1: No EA Input selected -> targets 1_Reset EAs."""
        prep_dir = os.path.join(
            self.temp_root, "PSA-GIS", "Ilocos Norte",
            "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing"
        )
        reset_eas_dir = os.path.join(prep_dir, "1_Reset EAs")
        os.makedirs(reset_eas_dir, exist_ok=True)

        sample_gpkg = os.path.join(reset_eas_dir, "012800000_ea2026_reset.gpkg")
        with open(sample_gpkg, "w") as f:
            f.write("mock_gpkg_content")

        ea_folder, detected_file, status = find_generated_ea_layer(prep_dir, has_ea_input=False)
        self.assertEqual(status, "OK")
        self.assertEqual(os.path.normpath(ea_folder), os.path.normpath(reset_eas_dir))
        self.assertEqual(os.path.normpath(detected_file), os.path.normpath(sample_gpkg))

    def test_find_generated_ea_layer_scenario_2_with_input(self):
        """Scenario 2: EA Input provided -> targets 2_Adjusted EAs."""
        prep_dir = os.path.join(
            self.temp_root, "PSA-GIS", "Laguna",
            "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing"
        )
        adjusted_eas_dir = os.path.join(prep_dir, "2_Adjusted EAs")
        os.makedirs(adjusted_eas_dir, exist_ok=True)

        sample_shp = os.path.join(adjusted_eas_dir, "043400000_ea_adjusted.shp")
        with open(sample_shp, "w") as f:
            f.write("mock_shp_content")

        ea_folder, detected_file, status = find_generated_ea_layer(prep_dir, has_ea_input=True)
        self.assertEqual(status, "OK")
        self.assertEqual(os.path.normpath(ea_folder), os.path.normpath(adjusted_eas_dir))
        self.assertEqual(os.path.normpath(detected_file), os.path.normpath(sample_shp))

    def test_find_generated_ea_layer_missing_subfolder(self):
        """Test error status when target subfolder does not exist."""
        prep_dir = os.path.join(self.temp_root, "2_Pre-Processing")
        os.makedirs(prep_dir, exist_ok=True)

        _, detected_file, status = find_generated_ea_layer(prep_dir, has_ea_input=False)
        self.assertEqual(status, "FOLDER_NOT_FOUND")
        self.assertIsNone(detected_file)

    def test_find_generated_ea_layer_empty_folder(self):
        """Test error status when target subfolder has no vector files."""
        prep_dir = os.path.join(self.temp_root, "2_Pre-Processing")
        reset_dir = os.path.join(prep_dir, "1_Reset EAs")
        os.makedirs(reset_dir, exist_ok=True)

        # Non-GIS file only
        with open(os.path.join(reset_dir, "notes.txt"), "w") as f:
            f.write("notes")

        _, detected_file, status = find_generated_ea_layer(prep_dir, has_ea_input=False)
        self.assertEqual(status, "LAYER_NOT_FOUND")
        self.assertIsNone(detected_file)

    def test_resolve_target_output_folder(self):
        """Test resolving output folder paths for both scenarios."""
        prep_dir = os.path.join(self.temp_root, "2_Pre-Processing")
        os.makedirs(prep_dir, exist_ok=True)

        out_no_input = resolve_target_output_folder(prep_dir, has_ea_input=False)
        self.assertEqual(os.path.normpath(out_no_input), os.path.normpath(os.path.join(prep_dir, "1_Reset EAs")))

        out_with_input = resolve_target_output_folder(prep_dir, has_ea_input=True)
        self.assertEqual(os.path.normpath(out_with_input), os.path.normpath(os.path.join(prep_dir, "2_Adjusted EAs")))

    def test_detect_project_from_layer(self):
        """Test resolving Pre-Processing folder directly from an input layer's source."""
        from references.create_enumeration_area.helpers.pre_ea_detector import detect_project_from_layer
        
        # Build structure
        proj_dir = os.path.join(self.temp_root, "PSA-GIS", "Batangas", "Project 1MAP")
        prep_dir = os.path.join(proj_dir, "3_EA Delineation and Merging", "2_Pre-Processing")
        os.makedirs(prep_dir, exist_ok=True)
        
        # Mock layer in an Inputs folder
        inputs_dir = os.path.join(proj_dir, "1_Inputs")
        os.makedirs(inputs_dir, exist_ok=True)
        shp_file = os.path.join(inputs_dir, "bgy.shp")
        with open(shp_file, "w") as f:
            f.write("dummy")

        class MockLayer:
            def source(self):
                return shp_file

        detected = detect_project_from_layer(MockLayer(), "1_Reset EAs")
        self.assertIsNotNone(detected)
        self.assertEqual(os.path.normpath(detected), os.path.normpath(os.path.join(prep_dir, "1_Reset EAs")))


if __name__ == "__main__":
    unittest.main()
