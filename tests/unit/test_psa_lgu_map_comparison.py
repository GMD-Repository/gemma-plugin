# -*- coding: utf-8 -*-
"""
Unit test module for psa_lgu_map_comparison.py (gmd_scripts/psa_lgu_map_comparison.py).
Tests module import, the pure geocode-matching helper functions, and
PsaLguComparisonAlgorithm processing-algorithm metadata.
"""

import math
import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()


class TestPsaLguMapComparison(unittest.TestCase):
    """Test suite for psa_lgu_map_comparison module."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.psa_lgu_map_comparison")
        self.alg = self.mod.PsaLguComparisonAlgorithm()

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.psa_lgu_map_comparison should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "psalgu_boundary_comparison")
        self.assertEqual(self.alg.groupId(), "1map")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_first8_truncates_and_handles_none(self):
        """first8 should truncate to 8 characters and treat None as empty."""
        self.assertEqual(self.mod.first8("012345678900"), "01234567")
        self.assertEqual(self.mod.first8("0123"), "0123")
        self.assertEqual(self.mod.first8(None), "")

    def test_guess_geocode_field_exact_and_substring(self):
        """guess_geocode_field should prefer an exact 'Geocode' match, then fall back to substring."""
        self.assertEqual(self.mod.guess_geocode_field(["Barangay", "Geocode"]), "Geocode")
        self.assertEqual(self.mod.guess_geocode_field(["Barangay", "Geocode_10"]), "Geocode_10")
        self.assertIsNone(self.mod.guess_geocode_field(["Barangay", "PSGC"]))

    def test_extract_code_from_layer_name(self):
        """extract_code should pull the pppmm-style prefix off PSA/LGU layer names."""
        self.assertEqual(self.mod.extract_code("000102_LGU"), "000102")
        self.assertEqual(self.mod.extract_code("00102_PSA_Boundary"), "00102")
        self.assertEqual(self.mod.extract_code("12345_no_suffix"), "12345")
        self.assertEqual(self.mod.extract_code(""), "")

    def test_unique_field_name_no_collision_keeps_base_name(self):
        """When the base name isn't taken, it's returned unchanged."""
        fields = self.mod.QgsFields()
        fields.append(self.mod.QgsField("BSN", self.mod.QVariant.String))
        self.assertEqual(self.mod._unique_field_name("geocode", fields), "geocode")

    def test_unique_field_name_avoids_exact_case_collision(self):
        """The regression this fixes: QgsFields.append() silently no-ops on
        an exact-name duplicate, and the value meant for it is then lost --
        this is what made a building's displayed 'geocode' column show its
        own untouched source value instead of the barangay it matched."""
        fields = self.mod.QgsFields()
        fields.append(self.mod.QgsField("geocode", self.mod.QVariant.String))
        self.assertEqual(self.mod._unique_field_name("geocode", fields), "geocode_2")

    def test_unique_field_name_is_case_insensitive(self):
        """Treated case-insensitively to match how GeoPackage and most
        providers treat column names, even though the in-memory provider
        used for this module's own outputs happens to allow same-name
        fields that differ only in case."""
        fields = self.mod.QgsFields()
        fields.append(self.mod.QgsField("Geocode", self.mod.QVariant.String))
        self.assertEqual(self.mod._unique_field_name("geocode", fields), "geocode_2")

    def test_unique_field_name_skips_every_taken_suffix(self):
        """geocode and geocode_2 both taken -> geocode_3."""
        fields = self.mod.QgsFields()
        fields.append(self.mod.QgsField("geocode", self.mod.QVariant.String))
        fields.append(self.mod.QgsField("geocode_2", self.mod.QVariant.String))
        self.assertEqual(self.mod._unique_field_name("geocode", fields), "geocode_3")


class TestFindDefaultLayerId(unittest.TestCase):
    """Test suite for the dialog pre-fill helper find_default_layer_id."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.psa_lgu_map_comparison")
        self.project = self.mod.QgsProject.instance()
        self.project.removeAllMapLayers()

    def tearDown(self):
        self.project.removeAllMapLayers()

    def add_polygon_layer(self, name):
        layer = self.mod.QgsVectorLayer("Polygon?crs=EPSG:4326", name, "memory")
        self.project.addMapLayer(layer)
        return layer

    def find(self, hints, exclude_ids=()):
        return self.mod.find_default_layer_id(
            hints, self.mod.QgsWkbTypes.PolygonGeometry, exclude_ids=exclude_ids)

    def test_picks_psa_and_lgu_layers_by_name(self):
        """The PSA hints should find the PSA layer and the LGU hints the LGU one."""
        psa = self.add_polygon_layer("000102_PSA")
        lgu = self.add_polygon_layer("000102_LGU")
        self.assertEqual(self.find(self.mod.PSA_LAYER_HINTS), psa.id())
        self.assertEqual(self.find(self.mod.LGU_LAYER_HINTS), lgu.id())

    def test_returns_none_when_no_layer_matches(self):
        """A project with no PSA-like layer should pre-fill nothing."""
        self.add_polygon_layer("Barangay Boundary")
        self.assertIsNone(self.find(self.mod.PSA_LAYER_HINTS))

    def test_skips_this_algorithms_own_output_layers(self):
        """Outputs of a previous run must not be offered as inputs on a re-run."""
        self.add_polygon_layer("000102_PSA_Matched")
        self.add_polygon_layer("000102_PSA_Unmatched")
        self.assertIsNone(self.find(self.mod.PSA_LAYER_HINTS))
        source = self.add_polygon_layer("000102_PSA")
        self.assertEqual(self.find(self.mod.PSA_LAYER_HINTS), source.id())

    def test_exclude_ids_keeps_psa_pick_out_of_the_lgu_running(self):
        """A layer already chosen for PSA is not reused for LGU."""
        both = self.add_polygon_layer("000102_PSA_LGU_draft")
        self.assertEqual(self.find(self.mod.PSA_LAYER_HINTS), both.id())
        self.assertIsNone(self.find(self.mod.LGU_LAYER_HINTS, exclude_ids=(both.id(),)))


class TestLguBoundaryLocator(unittest.TestCase):
    """Test suite for _LguBoundaryLocator, the point-in-polygon lookup that
    decides whether a building point is inside the barangay its geocode
    names, and which barangay it does sit in when it is not.

    The two polygons are kept apart (0-10 and 20-30 on x) so no test point
    can ever be a candidate for both -- that keeps the expected answer the
    same whether the containment test is GEOS, Shapely or the bounding-box
    fallback in the mock."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.psa_lgu_map_comparison")
        from qgis.core import QgsPointXY
        self.QgsPointXY = QgsPointXY

    def square(self, x0, y0, x1, y1):
        pts = [
            self.QgsPointXY(x0, y0), self.QgsPointXY(x1, y0),
            self.QgsPointXY(x1, y1), self.QgsPointXY(x0, y1),
            self.QgsPointXY(x0, y0),
        ]
        return self.mod.QgsGeometry.fromPolygonXY([pts])

    def polygon_feature(self, fid, geometry):
        feat = self.mod.QgsFeature()
        feat.setId(fid)
        feat.setGeometry(geometry)
        return feat

    def point(self, x, y):
        return self.mod.QgsGeometry.fromPointXY(self.QgsPointXY(x, y))

    def locator(self):
        """Two barangays: 'A' covering x 0-10, 'B' covering x 20-30."""
        locator = self.mod._LguBoundaryLocator()
        locator.add(self.polygon_feature(1, self.square(0, 0, 10, 10)), "00010201")
        locator.add(self.polygon_feature(2, self.square(20, 0, 30, 10)), "00010202")
        return locator

    def test_point_inside_the_barangay_its_geocode_names(self):
        """The everyday case: the point is where its geocode says it is."""
        self.assertTrue(self.locator().contains("00010201", self.point(5, 5)))
        self.assertTrue(self.locator().contains("00010202", self.point(25, 5)))

    def test_point_inside_a_different_barangay_is_not_contained(self):
        """The regression this fixes. A point carrying barangay A's geocode
        but sitting in barangay B is outside -- being somewhere within the
        municipality is not enough, or nothing would ever be reported."""
        locator = self.locator()
        self.assertFalse(locator.contains("00010201", self.point(25, 5)))
        # ...and the Outside layer records where it actually is.
        self.assertEqual(locator.code_for(self.point(25, 5)), "00010202")

    def test_point_outside_the_municipality_is_not_contained(self):
        """A point in no barangay at all is outside, with nothing to record
        in in_geocode."""
        locator = self.locator()
        self.assertFalse(locator.contains("00010201", self.point(50, 50)))
        self.assertIsNone(locator.code_for(self.point(50, 50)))

    def test_blank_geocode_is_never_contained(self):
        """With no geocode there is no barangay to check against, so the
        point can't be confirmed inside wherever it sits."""
        locator = self.locator()
        self.assertFalse(locator.contains("", self.point(5, 5)))
        self.assertFalse(locator.contains(None, self.point(5, 5)))

    def test_unknown_geocode_is_never_contained(self):
        """A geocode naming no LGU barangay matches no polygon."""
        self.assertFalse(self.locator().contains("99999999", self.point(5, 5)))

    def test_multipart_barangay_counts_any_of_its_parts(self):
        """An island barangay is several polygons under one geocode, and
        landing in any one of them is inside."""
        locator = self.mod._LguBoundaryLocator()
        locator.add(self.polygon_feature(1, self.square(0, 0, 10, 10)), "00010201")
        locator.add(self.polygon_feature(2, self.square(20, 0, 30, 10)), "00010201")
        self.assertTrue(locator.contains("00010201", self.point(5, 5)))
        self.assertTrue(locator.contains("00010201", self.point(25, 5)))

    def test_point_inside_a_polygon_returns_its_geocode(self):
        """A point well inside a barangay is placed in that barangay."""
        self.assertEqual(self.locator().code_for(self.point(5, 5)), "00010201")
        self.assertEqual(self.locator().code_for(self.point(25, 5)), "00010202")

    def test_point_outside_every_polygon_returns_none(self):
        """The regression this fixes: a point outside the boundary must not
        be reported as inside, whatever its geocode column says."""
        self.assertIsNone(self.locator().code_for(self.point(50, 50)))
        self.assertIsNone(self.locator().code_for(self.point(15, 5)))

    def test_point_on_a_boundary_line_stays_inside(self):
        """A point digitised onto the edge is properly contained by no
        polygon, and counts as inside the barangay it touches rather than
        being reported as outside it."""
        self.assertTrue(self.locator().contains("00010201", self.point(10, 5)))
        self.assertEqual(self.locator().code_for(self.point(10, 5)), "00010201")

    def test_missing_geometry_returns_none(self):
        """A building with no geometry can't be placed -- it goes Outside."""
        self.assertIsNone(self.locator().code_for(None))
        self.assertFalse(self.locator().contains("00010201", None))

    def test_empty_locator_reports_itself_empty(self):
        """An LGU layer with no usable geometry places nothing at all."""
        empty = self.mod._LguBoundaryLocator()
        self.assertTrue(empty.is_empty())
        self.assertIsNone(empty.code_for(self.point(5, 5)))
        self.assertFalse(empty.contains("00010201", self.point(5, 5)))
        self.assertFalse(self.locator().is_empty())

    def test_polygon_without_geometry_is_not_indexed(self):
        """An LGU feature carrying no geometry is skipped, not indexed."""
        locator = self.mod._LguBoundaryLocator()
        locator.add(self.polygon_feature(1, self.mod.QgsGeometry()), "00010201")
        self.assertTrue(locator.is_empty())


class TestRigidFit(unittest.TestCase):
    """Test suite for _rigid_fit / _translation_only_fit, the closed-form
    2D Procrustes solver behind LGU boundary alignment. Pure math, no QGIS
    geometry objects involved, so these run the same under the mock as
    they would inside real QGIS."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.psa_lgu_map_comparison")

    def _rotate_translate(self, points, theta, tx, ty):
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        out = []
        for x, y in points:
            out.append((cos_t * x - sin_t * y + tx, sin_t * x + cos_t * y + ty))
        return out

    def test_too_few_pairs_returns_none(self):
        """A single control point can't fix a rotation, only a translation."""
        self.assertIsNone(self.mod._rigid_fit([((0, 0), (5, 5))]))
        self.assertIsNone(self.mod._rigid_fit([]))

    def test_pure_translation_recovered_with_zero_rotation(self):
        """When the PSA points are just the LGU points shifted, the fit
        should recover that shift with (near) zero rotation."""
        lgu = [(0, 0), (10, 0), (0, 10), (5, 5)]
        psa = [(x + 7.0, y - 3.0) for x, y in lgu]
        theta, tx, ty = self.mod._rigid_fit(list(zip(lgu, psa)))
        self.assertAlmostEqual(theta, 0.0, places=9)
        self.assertAlmostEqual(tx, 7.0, places=9)
        self.assertAlmostEqual(ty, -3.0, places=9)

    def test_rotation_and_translation_recovered_exactly(self):
        """A known rotation + translation applied to a non-degenerate point
        set must be recovered exactly (up to floating point) by the
        closed-form fit -- this is the case the ICP loop in
        _icp_fit relies on to converge."""
        lgu = [(0, 0), (10, 0), (0, 10), (5, 5), (3, 8)]
        theta0, tx0, ty0 = math.radians(30.0), 12.5, -4.25
        psa = self._rotate_translate(lgu, theta0, tx0, ty0)
        theta, tx, ty = self.mod._rigid_fit(list(zip(lgu, psa)))
        self.assertAlmostEqual(theta, theta0, places=9)
        self.assertAlmostEqual(tx, tx0, places=9)
        self.assertAlmostEqual(ty, ty0, places=9)

    def test_translation_only_fit_shifts_with_no_rotation(self):
        theta, tx, ty = self.mod._translation_only_fit((1.0, 2.0), (4.0, 0.0))
        self.assertEqual(theta, 0.0)
        self.assertEqual(tx, 3.0)
        self.assertEqual(ty, -2.0)


class TestAlignmentModels(unittest.TestCase):
    """Test suite for the three alignment transform models, all of which
    return the same 6-tuple of affine coefficients. Pure math -- no QGIS
    geometry objects involved."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.psa_lgu_map_comparison")

    def apply(self, coeffs, points):
        return [self.mod._apply_coeffs(coeffs, x, y) for x, y in points]

    def assertMapsOnto(self, coeffs, source, target, places=6):
        for (gx, gy), (ex, ey) in zip(self.apply(coeffs, source), target):
            self.assertAlmostEqual(gx, ex, places=places)
            self.assertAlmostEqual(gy, ey, places=places)

    # Coordinates in the same range as a projected Philippine CRS, so the
    # numerical conditioning of the normal equations is actually exercised
    # rather than being flattered by small test numbers.
    BASE = [(230000.0, 1860000.0), (234000.0, 1861500.0),
            (231500.0, 1857000.0), (236200.0, 1858400.0),
            (229000.0, 1862750.0)]

    def test_similarity_recovers_scale_rotation_and_shift(self):
        """The case the map actually shows: the LGU tracing is rotated,
        shifted AND slightly the wrong size. A rigid fit cannot close that,
        a similarity fit closes it exactly."""
        s, theta = 1.0125, math.radians(0.75)
        tx, ty = 480.0, -260.0
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        target = [(s * (cos_t * x - sin_t * y) + tx,
                   s * (sin_t * x + cos_t * y) + ty) for x, y in self.BASE]

        coeffs = self.mod._similarity_coeffs(list(zip(self.BASE, target)))
        self.assertMapsOnto(coeffs, self.BASE, target, places=3)

        _shift, rotation, scale = self.mod._describe_coeffs(coeffs, self.BASE[0])
        self.assertAlmostEqual(scale, s, places=9)
        self.assertAlmostEqual(rotation, math.degrees(theta), places=9)

    def test_similarity_keeps_shape_by_scaling_both_axes_equally(self):
        """A similarity transform is conformal -- x and y are scaled by the
        same factor, so proportions and angles survive it. That is what
        lets the aligned boundary keep its own shape."""
        target = [(2.0 * x, 2.0 * y) for x, y in self.BASE]
        a, b, _c, d, e, _f = self.mod._similarity_coeffs(list(zip(self.BASE, target)))
        self.assertAlmostEqual(a, e, places=9)   # equal scale on both axes
        self.assertAlmostEqual(b, -d, places=9)  # rotation, not shear

    def test_rigid_fit_cannot_absorb_scale(self):
        """The regression that made a whole-municipality rigid alignment
        look badly off: with a real scale difference present, the best
        rigid fit still leaves the edges of the map far from PSA, while a
        similarity fit lands on it."""
        target = [(1.05 * x, 1.05 * y) for x, y in self.BASE]
        pairs = list(zip(self.BASE, target))

        rigid = self.mod._rigid_coeffs(pairs)
        similarity = self.mod._similarity_coeffs(pairs)

        def worst_error(coeffs):
            return max(math.hypot(gx - ex, gy - ey)
                       for (gx, gy), (ex, ey) in zip(self.apply(coeffs, self.BASE), target))

        self.assertGreater(worst_error(rigid), 100.0)
        self.assertLess(worst_error(similarity), 1e-3)

    def test_affine_recovers_differential_scale_and_shear(self):
        """Affine has the freedom to absorb an x/y scale difference and a
        skew, which neither rigid nor similarity can represent."""
        target = [(1.01 * x + 0.004 * y + 120.0, -0.002 * x + 0.997 * y - 75.0)
                  for x, y in self.BASE]
        coeffs = self.mod._affine_coeffs(list(zip(self.BASE, target)))
        self.assertMapsOnto(coeffs, self.BASE, target, places=2)

    def test_affine_needs_three_non_collinear_pairs(self):
        """Fewer than 3 pairs, or a collinear set, pins down no unique
        affine map -- the caller steps down to a simpler model instead."""
        pairs = [(p, p) for p in self.BASE[:2]]
        self.assertIsNone(self.mod._affine_coeffs(pairs))

        collinear = [((x, 2.0 * x), (x, 2.0 * x)) for x in (0.0, 1.0, 2.0, 3.0)]
        self.assertIsNone(self.mod._affine_coeffs(collinear))

    def test_identity_coefficients_leave_a_point_untouched(self):
        x, y = self.mod._apply_coeffs(self.mod.IDENTITY_COEFFS, 231000.0, 1859000.0)
        self.assertEqual((x, y), (231000.0, 1859000.0))


if __name__ == "__main__":
    unittest.main()
