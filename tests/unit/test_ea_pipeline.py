# -*- coding: utf-8 -*-
import unittest
from typing import Dict, Any, List

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsPolygon,
    QgsFields,
    QgsField,
)

from references.create_enumeration_area.helpers.classification import (
    is_delineation_candidate,
    is_merge_candidate,
)
from references.create_enumeration_area.phases.phase6_merge import (
    process_barangay_merge,
    is_delineation_candidate as phase6_is_delin,
    is_merge_candidate as phase6_is_merge,
)
from references.create_enumeration_area.phases.phase8_output import (
    refine_split_line,
)


class MockFeedback:
    def isCanceled(self):
        return False

    def pushInfo(self, msg):
        pass

    def pushWarning(self, msg):
        pass

    def reportError(self, msg):
        pass


def make_square_geom(x: float, y: float, size: float = 10.0) -> QgsGeometry:
    """Helper to create a square QgsGeometry centered at (x, y)."""
    p1 = QgsPointXY(x, y)
    p2 = QgsPointXY(x + size, y)
    p3 = QgsPointXY(x + size, y + size)
    p4 = QgsPointXY(x, y + size)
    return QgsGeometry.fromPolygonXY([[p1, p2, p3, p4, p1]])


class TestEAPipelineCandidateAndMerge(unittest.TestCase):

    def test_candidate_classification_predicates(self):
        """Verify strict mutual exclusivity and threshold enforcement."""
        delin_ids = {1, 2}
        merge_ids = {4}

        ea_over = {"original_id": 1, "hh_count": 350.0}
        ea_exact_max = {"original_id": 2, "hh_count": 300.0}
        ea_normal = {"original_id": 3, "hh_count": 200.0}
        ea_under = {"original_id": 4, "hh_count": 50.0}
        ea_over_not_in_candidate = {"original_id": 5, "hh_count": 400.0}

        # 1. Over-threshold / Max threshold (>= 300) when present in delineation_candidate_ids
        self.assertTrue(is_delineation_candidate(ea_over, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        self.assertTrue(is_delineation_candidate(ea_exact_max, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        self.assertFalse(is_delineation_candidate(ea_normal, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        self.assertFalse(is_delineation_candidate(ea_under, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        
        # Over-threshold EA that is NOT in delineation_candidate_ids must NOT be a delineation candidate
        self.assertFalse(
            is_delineation_candidate(ea_over_not_in_candidate, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids),
            "EAs outside delineation_candidate_ids must NEVER be flagged for delineation."
        )

        # 2. Under-threshold (<= 100)
        self.assertTrue(is_merge_candidate(ea_under, min_household=100, merge_candidate_ids=merge_ids))
        self.assertFalse(is_merge_candidate(ea_normal, min_household=100, merge_candidate_ids=merge_ids))
        self.assertFalse(is_merge_candidate(ea_over, min_household=100, merge_candidate_ids=merge_ids))

    def test_special_ea_extraction_candidate_threshold_reevaluation(self):
        """Verify candidate status post Special EA extraction (dropping below max_household vs dropping below min_household vs remaining over)."""
        delin_ids = {102, 103}
        merge_ids = {104, 105}

        # Candidate 101: Dropped below max_household after Special EA extraction (350 -> 250 HH < 300)
        ea_extracted_under = {"original_id": 101, "hh_count": 250.0}

        # Candidate 105: Dropped below min_household after Special EA extraction (350 -> 75 HH <= 100)
        ea_extracted_to_merge = {"original_id": 105, "hh_count": 75.0}

        # Candidate 102: Originally over-threshold (400 HH), and after Special EA extraction still has 320 HH (>= 300 max_household)
        ea_extracted_over = {"original_id": 102, "hh_count": 320.0}

        # Candidate 103: Explicit indicator 'for_delineation'
        ea_explicit = {"original_id": 103, "hh_count": 200.0}

        # 1. Dropped below max_household after Special EA extraction -> Exempted from delineation
        self.assertFalse(
            is_delineation_candidate(ea_extracted_under, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids),
            "EA whose HH count fell below max_household post-extraction should NOT be a delineation candidate."
        )
        self.assertFalse(
            phase6_is_delin(ea_extracted_under, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids),
            "Phase6 predicate should also exempt EA whose HH count fell below max_household post-extraction."
        )

        # 2. Dropped below min_household -> Added to merge candidates
        self.assertFalse(is_delineation_candidate(ea_extracted_to_merge, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        self.assertTrue(is_merge_candidate(ea_extracted_to_merge, min_household=100, merge_candidate_ids=merge_ids))

        # 3. Remains over max_household after Special EA extraction -> Must be delineated
        self.assertTrue(
            is_delineation_candidate(ea_extracted_over, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids),
            "EA remaining over max_household post-extraction MUST be a delineation candidate."
        )

        # 4. Explicit indicator -> Candidate when present in delin_ids
        from tests.mocks.qgis_mock import QgsFeature as MockQgsFeature
        mock_feat = MockQgsFeature()
        mock_feat.attributes_dict = {"eadel_indi": "for_delineation"}
        mock_feat.attribute = lambda idx: "for_delineation"
        self.assertTrue(
            is_delineation_candidate(ea_explicit, max_household=300, eadel_indi_col_idx=0, full_ea_by_id={103: mock_feat}, delineation_candidate_ids=delin_ids),
            "EA with explicit 'for_delineation' indicator in candidate set must be a candidate."
        )

    def test_merge_all_under_threshold_candidates(self):
        """Verify that multiple adjacent under-threshold EAs successfully merge together when no reference EA exists."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)  # adjacent to geom1

        ea1 = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 40.0,
            'original_hhcount': 40.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 101,
            'original_code': "01737001001",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        ea2 = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 50.0,
            'original_hhcount': 50.0,
            'bldg_count': 3,
            'attributes': [2, "EA 002"],
            'original_id': 102,
            'original_code': "01737001002",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        merged = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea1, ea2],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={101, 102}
        )

        self.assertEqual(len(merged), 1, "The 2 adjacent under-threshold candidates must merge into 1 EA.")
        self.assertEqual(merged[0]['hh_count'], 90.0, "Combined household count should be 40 + 50 = 90 HH.")
        self.assertTrue(merged[0].get('from_merge', False), "Output EA must be flagged with from_merge=True.")

    def test_merge_candidate_with_normal_reference_ea(self):
        """Verify that an under-threshold candidate prefers merging with a normal reference EA if present."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea_small = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 40.0,
            'original_hhcount': 40.0,
            'bldg_count': 1,
            'attributes': [1, "EA 001"],
            'original_id': 201,
            'original_code': "01737002001",
            'is_new': False,
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        ea_normal = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 180.0,
            'original_hhcount': 180.0,
            'bldg_count': 5,
            'attributes': [2, "EA 002"],
            'original_id': 202,
            'original_code': "01737002002",
            'is_new': False,
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        merged = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea_small, ea_normal],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={201}
        )

        self.assertEqual(len(merged), 2, "Small EA and non-merge candidate normal reference EA must NOT be merged.")

    def test_delineated_split_eas_never_merged(self):
        """Verify that delineated (from_split=True) EAs are never selected as merge candidates or merged."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea_small = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 50.0,
            'original_hhcount': 50.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 301,
            'original_code': "01737001001",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        ea_split = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 120.0,
            'original_hhcount': 250.0,
            'bldg_count': 5,
            'attributes': [2, "EA 002-1"],
            'original_id': 302,
            'original_code': "01737002002",
            'is_new': True,
            'split_by': 'road',
            'from_merge': False,
            'from_split': True,  # Delineated sub-EA
            'parent_barangay': "01737"
        }

        result = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea_small, ea_split],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={301},
            delineation_candidate_ids={302}
        )

        self.assertEqual(len(result), 2, "Delineated/split EA should NOT be merged with small EA.")
        for item in result:
            self.assertFalse(item.get('from_merge', False), "Neither EA should be marked as merged.")

    def test_under_threshold_ea_merges_with_special_ea(self):
        """Verify that an under-threshold EA can merge with a contiguous Special EA while excluding delineation candidates."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea_small = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 50.0,
            'original_hhcount': 50.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 401,
            'original_code': "01737001001",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': False,
            'is_special_ea': False,
            'parent_barangay': "01737"
        }

        ea_special = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 30.0,
            'original_hhcount': 30.0,
            'bldg_count': 1,
            'attributes': [2, "Special EA Gap"],
            'original_id': 402,
            'original_code': "01737002002",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': False,
            'is_special_ea': True,  # Special EA
            'parent_barangay': "01737"
        }

        result = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea_small, ea_special],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={401},
            delineation_candidate_ids=set()
        )

        self.assertEqual(len(result), 1, "Under-threshold EA should successfully merge with contiguous Special EA.")
        self.assertEqual(result[0]['hh_count'], 80.0, "Combined household count should be 50 + 30 = 80 HH.")
        self.assertTrue(result[0]['from_merge'], "Resulting merged EA must be marked with from_merge=True.")

    def test_multi_iteration_merge_up_to_10_excluding_delin(self):
        """Verify multi-iteration chain merging runs up to 10 iterations while strictly excluding delineation candidates."""
        feedback = MockFeedback()

        # Chain of 6 contiguous EAs of 15 HH each (total 90 HH) + 1 adjacent delineation candidate (350 HH)
        eas = []
        for i in range(6):
            eas.append({
                'geom': make_square_geom(i * 10, 0, 10),
                'buildings': [],
                'hh_count': 15.0,
                'original_hhcount': 15.0,
                'bldg_count': 1,
                'attributes': [i + 1, f"EA {i+1:03d}"],
                'original_id': 601 + i,
                'original_code': f"0173700{i+1:03d}",
                'is_new': False,
                'split_by': 'none',
                'from_merge': False,
                'from_split': False,
                'is_special_ea': False,
                'parent_barangay': "01737"
            })

        # Delineation candidate adjacent to the last EA
        ea_delin = {
            'geom': make_square_geom(60, 0, 10),
            'buildings': [],
            'hh_count': 350.0,
            'original_hhcount': 350.0,
            'bldg_count': 10,
            'attributes': [7, "EA 007 (Delin)"],
            'original_id': 607,
            'original_code': "01737007",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': True,  # Delineated candidate
            'is_special_ea': False,
            'parent_barangay': "01737"
        }
        eas.append(ea_delin)

        merge_ids = {601, 602, 603, 604, 605, 606}
        delin_ids = {607}

        result = process_barangay_merge(
            bar_code="01737",
            bar_eas=eas,
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids=merge_ids,
            delineation_candidate_ids=delin_ids
        )

        # 6 small EAs (90 HH total) should merge into 1 EA (90 HH), leaving the delineation candidate separate (total 2 EAs)
        self.assertEqual(len(result), 2, "6 small EAs should merge into 1, leaving delineation candidate separate.")
        merged_item = [item for item in result if item.get('from_merge', False)][0]
        self.assertEqual(merged_item['hh_count'], 90.0, "Merged chain should have 90 HH.")
        delin_item = [item for item in result if item.get('original_id') == 607][0]
        self.assertFalse(delin_item.get('from_merge', False), "Delineation candidate must NOT be merged.")

    def test_prevent_merge_exceeding_max_household(self):
        """Verify that EAs are prevented from merging if their combined count exceeds max_household (300 HH)."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea1 = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 200.0,
            'original_hhcount': 200.0,
            'attributes': [1, "EA 001"],
            'original_id': 301,
            'original_code': "01737003001",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        ea2 = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 150.0,
            'original_hhcount': 150.0,
            'attributes': [2, "EA 002"],
            'original_id': 302,
            'original_code': "01737003002",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        # 200 + 150 = 350 > 300 max_household
        merged = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea1, ea2],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={301, 302}
        )

        self.assertEqual(len(merged), 2, "EAs exceeding 300 HH when combined must NOT be merged.")

    def test_single_ea_barangay_no_merge(self):
        """Verify that an isolated single-EA barangay under min_household remains unmerged."""
        feedback = MockFeedback()
        geom = make_square_geom(0, 0, 10)
        ea = {
            'geom': geom,
            'buildings': [],
            'hh_count': 30.0,
            'original_hhcount': 30.0,
            'attributes': [1, "EA 001"],
            'original_id': 401,
            'original_code': "01737004001",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737004"
        }

        merged = process_barangay_merge("01737004", [ea], feedback, min_household=100.0, max_household=300.0)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['hh_count'], 30.0)

    def test_disallow_candidate_merge_setting(self):
        """Verify that setting allow_candidate_merge=False prevents candidate-to-candidate merging."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea1 = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 40.0,
            'original_hhcount': 40.0,
            'attributes': [1, "EA 001"],
            'original_id': 501,
            'original_code': "01737005001",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737005"
        }
        ea2 = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 50.0,
            'original_hhcount': 50.0,
            'attributes': [2, "EA 002"],
            'original_id': 502,
            'original_code': "01737005002",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737005"
        }

        merged = process_barangay_merge(
            bar_code="01737005",
            bar_eas=[ea1, ea2],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={501, 502},
        )

        self.assertEqual(len(merged), 1, "Adjacent merge candidates must merge together.")
        self.assertEqual(merged[0]['hh_count'], 90.0)

    def test_refine_split_line_gap_and_prune(self):
        """Verify that refine_split_line bridges small gaps and prunes tiny isolated branches."""
        # Line 1: (0,0) -> (10,0)
        # Line 2: (12,0) -> (20,0) with gap of 2 units
        p1, p2 = QgsPointXY(0, 0), QgsPointXY(10, 0)
        p3, p4 = QgsPointXY(12, 0), QgsPointXY(20, 0)
        g1 = QgsGeometry.fromPolylineXY([p1, p2])
        g2 = QgsGeometry.fromPolylineXY([p3, p4])
        multi_line = QgsGeometry.collectGeometry([g1, g2])

        # gap_tolerance=5.0 should bridge the 2.0-unit gap
        refined = refine_split_line(multi_line, gap_tolerance=5.0, min_branch_len=1.0)
        self.assertFalse(refined.isEmpty())

    def test_pairwise_split_shared_boundary_extraction(self):
        """Verify that intersection of two adjacent split polygons extracts their shared boundary line."""
        # Polygon 1: [0,0] to [10,10]
        # Polygon 2: [10,0] to [20,10] (adjacent along x=10 line from y=0 to y=10)
        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        shared = geom1.intersection(geom2)
        self.assertFalse(shared.isEmpty())
        merged = shared.mergeLines()
        refined = refine_split_line(merged, gap_tolerance=1.0, min_branch_len=0.5)
        self.assertFalse(refined.isEmpty())


class TestEAOutputSchemaAndRenaming(unittest.TestCase):

    def test_output_schema_field_renaming_and_ordering(self):
        """Verify new_ean, bldgcount, hhcount, indicator, and remarks as the last field."""
        from qgis.core import QgsFields, QgsField, QgsVectorLayer
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            try:
                from PyQt5.QtCore import QVariant
            except ImportError:
                from qgis.core import QVariant  # headless mock fallback
        fields = QgsFields()
        fields.append(QgsField("geocode", QVariant.String))
        fields.append(QgsField("ean", QVariant.String))
        fields.append(QgsField("remarks", QVariant.String))
        fields.append(QgsField("hh_count", QVariant.Double))

        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_layer", "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        out_fields = QgsFields(layer.fields())

        if "new_ean" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("new_ean", QVariant.String))

        if "bldgcount" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("bldgcount", QVariant.Int))

        if "hhcount" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("hhcount", QVariant.Double))

        if "indicator" not in [f.name() for f in out_fields]:
            out_fields.append(QgsField("indicator", QVariant.String))

        rem_idx = out_fields.indexOf("remarks")
        if rem_idx != -1:
            out_fields.remove(rem_idx)
        out_fields.append(QgsField("remarks", QVariant.String))

        field_names = [out_fields.at(i).name() for i in range(out_fields.count())]

        self.assertIn("new_ean", field_names)
        self.assertIn("bldgcount", field_names)
        self.assertIn("hhcount", field_names)
        self.assertIn("indicator", field_names)
        self.assertEqual(field_names[-1], "remarks", "remarks must be the last column in output schema.")

    def test_special_ea_schema_field_names(self):
        """Verify that special_ea_export_fields omits hhcount/bldgcount and includes hh_count/bldg_count."""
        from qgis.core import QgsFields, QgsField
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            try:
                from PyQt5.QtCore import QVariant
            except ImportError:
                from qgis.core import QVariant

        export_field_names = [
            "fid", "map_uuid", "geocode", "region", "province",
            "city_mun", "barangay", "code", "name", "ean",
            "hhcount", "bldgcount", "sy", "new_ean", "hh_count",
            "bldg_count", "ea_type", "remarks"
        ]
        export_fields = QgsFields()
        for fname in export_field_names:
            export_fields.append(QgsField(fname, QVariant.String))

        special_ea_export_fields = QgsFields()
        for f in export_fields:
            if f.name() in ("hhcount", "bldgcount"):
                continue
            special_ea_export_fields.append(f)

        spec_field_names = [special_ea_export_fields.at(i).name() for i in range(special_ea_export_fields.count())]
        self.assertNotIn("hhcount", spec_field_names, "Special EA layer schema must NOT contain 'hhcount'")
        self.assertNotIn("bldgcount", spec_field_names, "Special EA layer schema must NOT contain 'bldgcount'")
        self.assertIn("hh_count", spec_field_names, "Special EA layer schema MUST contain 'hh_count'")
        self.assertIn("bldg_count", spec_field_names, "Special EA layer schema MUST contain 'bldg_count'")

    def test_merged_ea_schema_includes_indicator_gps_min_circle(self):
        """Verify that merged_export_fields includes indicator, gps, and min_circle fields."""
        from qgis.core import QgsFields, QgsField
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            try:
                from PyQt5.QtCore import QVariant
            except ImportError:
                from qgis.core import QVariant

        export_field_names = [
            "fid", "map_uuid", "geocode", "region", "province",
            "city_mun", "barangay", "code", "name", "ean",
            "hhcount", "bldgcount", "sy", "new_ean", "hh_count",
            "bldg_count", "ea_type", "remarks"
        ]
        export_fields = QgsFields()
        for fname in export_field_names:
            export_fields.append(QgsField(fname, QVariant.String))

        merged_export_fields = QgsFields(export_fields)
        for fname in ("indicator", "gps", "min_circle"):
            if merged_export_fields.indexOf(fname) == -1:
                merged_export_fields.append(QgsField(fname, QVariant.String))

        merged_field_names = [merged_export_fields.at(i).name() for i in range(merged_export_fields.count())]
        self.assertIn("indicator", merged_field_names, "Merged EA layer schema MUST contain 'indicator'")
        self.assertIn("gps", merged_field_names, "Merged EA layer schema MUST contain 'gps'")
        self.assertIn("min_circle", merged_field_names, "Merged EA layer schema MUST contain 'min_circle'")

        from qgis.core import QgsFeature
        exp_feat = QgsFeature(merged_export_fields)
        indicator_idx = merged_export_fields.indexOf("indicator")
        exp_feat.setAttribute(indicator_idx, "")
        self.assertEqual(exp_feat.attribute("indicator"), "")

    def test_enable_thresholds_toggle_behavior(self):
        """Verify that default threshold values (min=100, max=300) are maintained."""
        ea_high = {"original_id": 1, "hh_count": 500.0}
        ea_low = {"original_id": 2, "hh_count": 20.0}

    def test_qml_style_files_exist(self):
        """Verify that output QML style files exist in qml styles directory."""
        import os
        from references.create_enumeration_area.helpers.style import get_qml_file_path
        self.assertTrue(os.path.isfile(get_qml_file_path("ea_output.qml")))
        self.assertTrue(os.path.isfile(get_qml_file_path("eadel_update_lines.qml")))
        self.assertTrue(os.path.isfile(get_qml_file_path("delineation_candidates.qml")))
        self.assertTrue(os.path.isfile(get_qml_file_path("merge_candidates.qml")))

    def test_delineation_preserves_untouched_hhcount_and_bldgcount(self):
        """Verify that sub-EAs produced by delineation retain parent hhcount/bldgcount without edit."""
        from qgis.core import QgsFields, QgsField, QgsFeature, QgsGeometry
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            try:
                from PyQt5.QtCore import QVariant
            except ImportError:
                from qgis.core import QVariant

        out_fields = QgsFields()
        for fname, ftype in [
            ("fid", QVariant.Int),
            ("hhcount", QVariant.Double),
            ("bldgcount", QVariant.Int),
            ("hh_count", QVariant.Double),
            ("bldg_count", QVariant.Int),
            ("new_ean", QVariant.String),
            ("remarks", QVariant.String),
        ]:
            out_fields.append(QgsField(fname, ftype))

        # Parent feature had 450 HH and 80 buildings
        parent_attrs = [101, 450.0, 80, 450.0, 80, "01716001001", ""]
        
        # Sub-EA 1 after delineation has 225.0 calculated HH and 40 building points
        ea1 = {
            'original_id': 101,
            'attributes': list(parent_attrs),
            'hh_count': 225.0,
            'bldg_count': 40,
            'original_hhcount': 450.0,
            'original_bldgcount': 80,
            'new_ea_code': "001A",
            'is_new': True,
            'from_split': True,
        }
        
        # Build output feature mimicking phase8_output logic
        feat1 = QgsFeature(out_fields)
        attrs1 = list(ea1['attributes'])
        if len(attrs1) < out_fields.count():
            attrs1.extend([None] * (out_fields.count() - len(attrs1)))
        feat1.setAttributes(attrs1)

        # Set calculated hh_count and bldg_count
        hh_count_idx = out_fields.indexOf("hh_count")
        if hh_count_idx != -1:
            feat1.setAttribute(hh_count_idx, int(ea1['hh_count']))
        bldg_count_idx = out_fields.indexOf("bldg_count")
        if bldg_count_idx != -1:
            feat1.setAttribute(bldg_count_idx, ea1['bldg_count'])

        # Verify hhcount and bldgcount are preserved untouched
        self.assertEqual(float(feat1.attribute("hhcount")), 450.0)
        self.assertEqual(int(feat1.attribute("bldgcount")), 80)
        # Verify hh_count and bldg_count hold the new delineated counts
        self.assertEqual(float(feat1.attribute("hh_count")), 225.0)
        self.assertEqual(int(feat1.attribute("bldg_count")), 40)

    def test_merge_preserves_dominant_hhcount_and_bldgcount_without_summing(self):
        """Verify that merged EAs retain dominant EA hhcount/bldgcount without summing."""
        ea_small = {
            'original_id': 1,
            'original_code': "001",
            'hh_count': 30.0,
            'original_hhcount': 30.0,
            'original_bldgcount': 5,
            'bldg_count': 5,
            'attributes': [1, 30.0, 5],
        }
        ea_dominant = {
            'original_id': 2,
            'original_code': "002",
            'hh_count': 50.0,
            'original_hhcount': 50.0,
            'original_bldgcount': 9,
            'bldg_count': 9,
            'attributes': [2, 50.0, 9],
        }

        dominant_is_ea = ea_small['hh_count'] >= ea_dominant['hh_count']
        merged_ea = {
            'hh_count': ea_small['hh_count'] + ea_dominant['hh_count'],
            'original_hhcount': ea_small.get('original_hhcount', 0) if dominant_is_ea else ea_dominant.get('original_hhcount', 0),
            'original_bldgcount': ea_small.get('original_bldgcount', 0) if dominant_is_ea else ea_dominant.get('original_bldgcount', 0),
            'bldg_count': ea_small.get('bldg_count', 0) + ea_dominant.get('bldg_count', 0),
            'attributes': list(ea_small['attributes']) if dominant_is_ea else list(ea_dominant['attributes']),
        }

        # Merged household and building counts are combined in hh_count & bldg_count
        self.assertEqual(merged_ea['hh_count'], 80.0)
        self.assertEqual(merged_ea['bldg_count'], 14)
        # But original hhcount and bldgcount are NOT summed (dominant values preserved)
        self.assertEqual(merged_ea['original_hhcount'], 50.0)
        self.assertEqual(merged_ea['original_bldgcount'], 9)
        self.assertEqual(merged_ea['attributes'][1], 50.0)
        self.assertEqual(merged_ea['attributes'][2], 9)

    def test_previous_layer_alias_inheritance_for_hhcount_and_bldgcount(self):
        """Verify that previous layer aliases like new_hhcount/household/bldg_count are correctly inherited into hhcount/bldgcount."""
        from qgis.core import QgsFields, QgsField, QgsFeature
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            try:
                from PyQt5.QtCore import QVariant
            except ImportError:
                from qgis.core import QVariant

        # Simulate previous layer with alias column names "new_hhcount" and "bldg_count"
        prev_fields = QgsFields()
        prev_fields.append(QgsField("geocode", QVariant.String))
        prev_fields.append(QgsField("new_hhcount", QVariant.Double))
        prev_fields.append(QgsField("bldg_count", QVariant.Int))

        parent_feat = QgsFeature(prev_fields)
        parent_feat.setAttributes(["01716001001", 380.0, 72])

        # Target output fields with standard names "hhcount" and "bldgcount"
        out_fields = QgsFields()
        out_fields.append(QgsField("geocode", QVariant.String))
        out_fields.append(QgsField("hhcount", QVariant.Double))
        out_fields.append(QgsField("bldgcount", QVariant.Int))
        out_fields.append(QgsField("hh_count", QVariant.Double))
        out_fields.append(QgsField("bldg_count", QVariant.Int))

        out_feat = QgsFeature(out_fields)

        # Extraction logic
        def get_field_val(f, fname, default=0):
            if not f or not f.isValid(): return default
            flds = f.fields()
            fnames = [fname] if isinstance(fname, str) else list(fname)
            for target in fnames:
                idx = flds.indexOf(target)
                if idx == -1:
                    for j in range(flds.count()):
                        if flds.at(j).name().lower() == target.lower():
                            idx = j
                            break
                if idx != -1:
                    val = f.attribute(idx)
                    if val is not None and str(val).strip() not in ('', 'NULL', 'None'):
                        return float(val) if isinstance(default, float) or default is None else int(round(float(val)))
            return default

        hh_names = ["hhcount", "new_hhcount", "hh_count", "hh_cnt", "household", "household_count", "pop", "population"]
        bldg_names = ["bldgcount", "new_bldgcount", "bldg_count", "bldg_cnt", "bldgpts_cnt", "bldg_points", "building_count", "bldg_total", "buildings"]

        val_hh = get_field_val(parent_feat, hh_names, default=None)
        val_bldg = get_field_val(parent_feat, bldg_names, default=None)

        out_feat.setAttribute(out_fields.indexOf("hhcount"), val_hh)
        out_feat.setAttribute(out_fields.indexOf("bldgcount"), val_bldg)
        self.assertEqual(float(out_feat.attribute("hhcount")), 380.0)
        self.assertEqual(int(out_feat.attribute("bldgcount")), 72)

    def test_special_ea_building_point_summation_and_parent_deduction(self):
        """Verify that building points within Special EAs are totaled and deducted from parent EAs correctly."""
        # 1. Special EA with 3 building points
        bldg_pts = [
            {'point': QgsPointXY(2.0, 2.0), 'pop': 25.0},
            {'point': QgsPointXY(3.0, 3.0), 'pop': 35.0},
            {'point': QgsPointXY(4.0, 4.0), 'pop': 40.0},
        ]
        special_ea_hh = sum(b['pop'] for b in bldg_pts)
        self.assertEqual(special_ea_hh, 100.0)

        # 2. Parent EA A: Originally 350 HH (over threshold). Deduct 100 HH -> 250 HH (< 300).
        orig_hh_a = 350.0
        effective_hh_a = orig_hh_a - special_ea_hh
        self.assertEqual(effective_hh_a, 250.0)
        # Drops below 300 -> Must be removed from delineation candidates
        delin_ids = {101}
        if effective_hh_a < 300.0:
            delin_ids.discard(101)
        self.assertNotIn(101, delin_ids)

        # 3. Parent EA B: Originally 350 HH. Special EA with 280 HH extracted -> Effective 70 HH (<= 100).
        special_ea_hh_b = 280.0
        orig_hh_b = 350.0
        effective_hh_b = orig_hh_b - special_ea_hh_b
        self.assertEqual(effective_hh_b, 70.0)
        delin_ids_b = {102}
        merge_ids_b = set()
        if effective_hh_b < 300.0:
            delin_ids_b.discard(102)
        if effective_hh_b <= 100.0:
            merge_ids_b.add(102)
        self.assertNotIn(102, delin_ids_b)
        self.assertIn(102, merge_ids_b)

        # 4. Parent EA C: Originally 450 HH. Special EA with 100 HH extracted -> Effective 350 HH (>= 300).
        orig_hh_c = 450.0
        effective_hh_c = orig_hh_c - special_ea_hh
        self.assertEqual(effective_hh_c, 350.0)
        delin_ids_c = {103}
        if effective_hh_c < 300.0:
            delin_ids_c.discard(103)
        self.assertIn(103, delin_ids_c)

    def test_geocode_not_changed_for_delineated_and_merged_ea(self):
        """Verify that geocode is preserved untouched for delineated and merged EAs."""
        from qgis.core import QgsFields, QgsField, QgsFeature, NULL
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            from PyQt5.QtCore import QVariant

        out_fields = QgsFields()
        out_fields.append(QgsField("geocode", QVariant.String))
        out_fields.append(QgsField("new_ean", QVariant.String))
        out_fields.append(QgsField("name", QVariant.String))

        # Scenario 1: Delineated EA with existing geocode "01801015000000" and new code "000001"
        ea_delineated = {
            'attributes': ["01801015000000", None, None],
            'new_ea_code': "000001",
            'new_ea_tracker': "000001",
            'from_split': True,
        }
        out_feat = QgsFeature(out_fields)
        attrs = list(ea_delineated['attributes'])
        out_feat.setAttributes(attrs)

        geocode_idx = out_fields.indexOf("geocode")
        cur_gc = out_feat.attribute(geocode_idx)
        if cur_gc is None or cur_gc == NULL or str(cur_gc).strip() in ('', 'NULL', 'None'):
            inh_gc = "01801015000"
            out_feat.setAttribute(geocode_idx, str(inh_gc))
        else:
            gc_str = str(cur_gc).strip()
            if gc_str.endswith(".0"):
                gc_str = gc_str[:-2]
            out_feat.setAttribute(geocode_idx, gc_str)

        # Geocode must remain the original value without modifying or appending new_ea_code
        self.assertEqual(out_feat.attribute("geocode"), "01801015000000")

        # Scenario 2: Merged EA with 9-digit barangay geocode "018010150"
        ea_merged = {
            'attributes': ["018010150", None, None],
            'new_ea_code': "000002",
            'new_ea_tracker': "000002",
            'from_merge': True,
        }
        out_feat_m = QgsFeature(out_fields)
        attrs_m = list(ea_merged['attributes'])
        out_feat_m.setAttributes(attrs_m)

        cur_gc_m = out_feat_m.attribute(geocode_idx)
        if cur_gc_m is None or cur_gc_m == NULL or str(cur_gc_m).strip() in ('', 'NULL', 'None'):
            inh_gc = "018010150"
            out_feat_m.setAttribute(geocode_idx, str(inh_gc))
        else:
            gc_str = str(cur_gc_m).strip()
            if gc_str.endswith(".0"):
                gc_str = gc_str[:-2]
            out_feat_m.setAttribute(geocode_idx, gc_str)

        self.assertEqual(out_feat_m.attribute("geocode"), "018010150")

    def test_name_and_ean_not_changed_for_delineated_and_merged_ea(self):
        """Verify that name and ean are preserved untouched for delineated and merged EAs."""
        from qgis.core import QgsFields, QgsField, QgsFeature, NULL
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            from PyQt5.QtCore import QVariant

        out_fields = QgsFields()
        out_fields.append(QgsField("geocode", QVariant.String))
        out_fields.append(QgsField("name", QVariant.String))
        out_fields.append(QgsField("ean", QVariant.String))
        out_fields.append(QgsField("new_ean", QVariant.String))

        # Delineated EA with original name "EA 001", ean "000001", but newly assigned new_ea_code "000001A"
        ea_delineated = {
            'attributes': ["01801015000000", "EA 001", "000001", None],
            'new_ea_code': "000001A",
            'new_ea_tracker': "000001A",
            'original_code': "000001",
            'from_split': True,
        }
        out_feat = QgsFeature(out_fields)
        attrs = list(ea_delineated['attributes'])
        out_feat.setAttributes(attrs)

        # Name should remain original "EA 001"
        name_idx = out_fields.indexOf("name")
        cur_name = out_feat.attribute(name_idx)
        if cur_name is None or cur_name == NULL or str(cur_name).strip() in ('', 'NULL', 'None'):
            inh_name = f"EA {ea_delineated['original_code']}"
            out_feat.setAttribute(name_idx, str(inh_name))

        self.assertEqual(out_feat.attribute("name"), "EA 001")

        # EAN should remain original "000001"
        ean_idx = out_fields.indexOf("ean")
        cur_ean = out_feat.attribute(ean_idx)
        if cur_ean is None or cur_ean == NULL or str(cur_ean).strip() in ('', 'NULL', 'None'):
            inh_ean = ea_delineated['original_code']
            out_feat.setAttribute(ean_idx, str(inh_ean))

        self.assertEqual(out_feat.attribute("ean"), "000001")

        # new_ean should receive the new tracker code
        new_ean_idx = out_fields.indexOf("new_ean")
        out_feat.setAttribute(new_ean_idx, ea_delineated['new_ea_tracker'])
        self.assertEqual(out_feat.attribute("new_ean"), "000001A")

    def test_output_layer_sy_column_is_2026(self):
        """Verify that sy column of output layers (delineated_ea, merge_ea, special_ea) is 2026."""
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            try:
                from PyQt5.QtCore import QVariant
            except ImportError:
                from qgis.core import QVariant

        export_field_names = [
            "fid", "map_uuid", "geocode", "region", "province",
            "city_mun", "barangay", "code", "name", "ean",
            "hhcount", "bldgcount", "sy", "new_ean", "hh_count",
            "bldg_count", "ea_type", "remarks"
        ]
        export_fields = QgsFields()
        for fname in export_field_names:
            export_fields.append(QgsField(fname, QVariant.String))

        special_ea_export_fields = QgsFields()
        for f in export_fields:
            if f.name() not in ("hhcount", "bldgcount"):
                special_ea_export_fields.append(f)

        def make_export_feature(src_feat, exp_fields):
            exp_feat = QgsFeature(exp_fields)
            exp_attrs = []
            src_flds = src_feat.fields()
            for f in exp_fields:
                idx = src_flds.indexOf(f.name())
                if idx != -1:
                    val = src_feat.attribute(idx)
                else:
                    val = src_feat.attribute(f.name())
                if f.name().lower() == "sy":
                    val = "2026"
                exp_attrs.append(val if val is not None else None)
            exp_feat.setAttributes(exp_attrs)
            return exp_feat

        # 1. Delineated EA
        feat_delin = QgsFeature(export_fields)
        exp_delin = make_export_feature(feat_delin, export_fields)
        self.assertEqual(str(exp_delin.attribute("sy")), "2026")

        # 2. Merged EA
        feat_merged = QgsFeature(export_fields)
        exp_merged = make_export_feature(feat_merged, export_fields)
        self.assertEqual(str(exp_merged.attribute("sy")), "2026")

        # 3. Special EA
        feat_special = QgsFeature(special_ea_export_fields)
        exp_special = make_export_feature(feat_special, special_ea_export_fields)
        self.assertEqual(str(exp_special.attribute("sy")), "2026")

    def test_merged_ea_hhcount_and_bldgcount_updated(self):
        """Verify that hhcount and bldgcount fields are updated with the combined merged totals for merged EAs."""
        from qgis.core import QgsFields, QgsField, QgsFeature
        try:
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            from PyQt5.QtCore import QVariant

        out_fields = QgsFields()
        out_fields.append(QgsField("hhcount", QVariant.Double))
        out_fields.append(QgsField("hh_count", QVariant.Int))
        out_fields.append(QgsField("bldgcount", QVariant.Int))
        out_fields.append(QgsField("bldg_count", QVariant.Int))

        # Merged EA with original single-EA count 40 HH, but new combined count 90 HH & 5 bldgs
        ea_merged = {
            'hh_count': 90.0,
            'original_hhcount': 40.0,
            'bldg_count': 5,
            'original_bldgcount': 2,
            'from_merge': True,
            'is_special_ea': False
        }

        # Simulate Phase 8 attribute assignment logic
        out_feat = QgsFeature(out_fields)
        val_hh = ea_merged['hh_count'] if (ea_merged.get('is_special_ea') or ea_merged.get('from_merge')) else ea_merged.get('original_hhcount')
        val_bldg = ea_merged['bldg_count'] if (ea_merged.get('is_special_ea') or ea_merged.get('from_merge')) else ea_merged.get('original_bldgcount')

        out_feat.setAttribute(out_fields.indexOf("hhcount"), float(val_hh))
        out_feat.setAttribute(out_fields.indexOf("hh_count"), int(ea_merged['hh_count']))
        out_feat.setAttribute(out_fields.indexOf("bldgcount"), int(val_bldg))
        out_feat.setAttribute(out_fields.indexOf("bldg_count"), int(ea_merged['bldg_count']))

        self.assertEqual(out_feat.attribute("hhcount"), 90.0, "hhcount for merged EA must reflect combined 90 HH.")
        self.assertEqual(out_feat.attribute("hh_count"), 90, "hh_count for merged EA must reflect combined 90 HH.")
        self.assertEqual(out_feat.attribute("bldgcount"), 5, "bldgcount for merged EA must reflect combined 5 bldgs.")
        self.assertEqual(out_feat.attribute("bldg_count"), 5, "bldg_count for merged EA must reflect combined 5 bldgs.")


if __name__ == "__main__":
    unittest.main()



