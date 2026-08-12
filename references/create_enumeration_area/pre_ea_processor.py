# -*- coding: utf-8 -*-
"""
Pre-EA Processor
----------------
Implements the Pre-EA Processing workflow for the EA Delineation and Merging plugin.

Workflow:
  Phase 1 — EA-to-Barangay matching (attribute geocode prefix, spatial fallback)
  Phase 2 — Clip each EA to its parent Barangay boundary
  Phase 3 — Detect uncovered Barangay areas (gaps) after clipping
  Phase 4 — Assign each gap to the contiguous EA with the longest shared boundary
  Phase 5 — Final spatial validation
  Phase 6 — Build and return the output memory layer

Purpose:
  Ensure all EA polygons are completely contained within their corresponding
  Barangay polygon and that no meaningful uncovered area (gap) remains
  within the Barangay after EA boundary adjustments.

Inputs:
  - Barangay polygon layer
  - EA polygon layer

Output:
  - New in-memory polygon layer named <pppmm>_ea2026_preprocessed
  - PreEAResult dataclass containing summary statistics, per-row results, and log lines

Dependencies:
  PyQGIS (QGIS 3.x LTR / PyQt5)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsFields,
    QgsGeometry,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Attribute field names searched (case-insensitive) when matching EA to Barangay.
_GEOCODE_FIELDS = ("geocode", "geo_code", "psgc", "adm4_pcode", "adm_pcode", "brgy_code")
_EA_GEOCODE_FIELDS = ("geocode", "geo_code", "psgc", "ean", "ea_code", "adm4_pcode")

# Number of geocode prefix characters used for attribute-based matching.
_GEOCODE_PREFIX_LEN = 9


# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ResultRow:
    """One row in the processing results table."""

    barangay_id: str
    ea_id: str
    original_area: float  # square metres
    corrected_area: float  # square metres
    area_change: float     # corrected - original (signed)
    action: str            # "No Change" | "Clipped" | "Gap Assigned" | "Geometry Fixed" | "Unresolved" | "Error"
    status: str            # "Valid" | "Corrected" | "Unresolved" | "Error"


@dataclass
class PreEASummary:
    """Aggregate statistics after processing."""

    barangays_processed: int = 0
    eas_processed: int = 0
    eas_requiring_correction: int = 0
    eas_clipped: int = 0
    gaps_detected: int = 0
    gaps_assigned: int = 0
    unresolved_gaps: int = 0
    final_eas_outside_bgy: int = 0
    final_uncovered_area: float = 0.0  # total area of unresolved gaps in m²
    output_name: str = ""
    overall_status: str = "PASS"  # "PASS" | "WARNING" | "ERROR"


@dataclass
class PreEAResult:
    """Full result returned by PreEAProcessor.run()."""

    output_layer: Optional[QgsVectorLayer]
    summary: PreEASummary
    result_rows: List[ResultRow]
    log_lines: List[str]
    success: bool
    error_message: str = ""


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------


class PreEAProcessor:
    """
    Executes the Pre-EA Processing workflow.

    Usage::

        processor = PreEAProcessor()
        result = processor.run(
            barangay_layer=bgy_layer,
            ea_layer=ea_layer,
            gap_tolerance=1.0,
            clip_to_bgy=True,
            detect_gaps=True,
            assign_gaps=True,
            feedback_callback=my_log_fn,
            progress_callback=my_progress_fn,
            is_cancelled_fn=lambda: False,
        )
    """

    @staticmethod
    def short_help_string() -> str:
        """Returns the HTML description string for Pre-EA Processing."""
        return (
            "<h3>Pre-EA Processing</h3>"
            "<p>Prepares an existing Enumeration Area (EA) layer for use in the Create Enumeration Areas "
            "workflow by enforcing two fundamental spatial rules: clipping EAs extending outside their parent "
            "Barangay and filling uncovered coverage gaps within the Barangay boundary.</p>"

            "<h4>Inputs</h4>"
            "<b>Required</b>"
            "<ul>"
            "<li><b>Barangay Layer</b> (polygon) — Administrative barangay polygon boundaries. "
            "Must contain a <i>geocode</i> attribute field used to match EAs to their parent Barangay. "
            "Auto-detected by <code>*_bgy</code> layer name pattern.</li>"
            "<li><b>EA Layer</b> (polygon) — Starting EA polygon boundaries to be pre-processed. "
            "Must contain a <i>geocode</i> attribute field. Auto-detected by <code>*_ea</code> or <code>*_ea2024</code> layer name pattern.</li>"
            "<li><b>Gap Area Tolerance (m²)</b> — Minimum area threshold (default 1.0 m²) for a gap to be processed; "
            "smaller gaps are treated as geometry precision slivers and skipped.</li>"
            "<li><b>Clip EA to Barangay Boundary</b> — When enabled (default: True), clips any portion of an EA extending outside its parent Barangay boundary.</li>"
            "<li><b>Detect Uncovered Barangay Areas</b> — When enabled (default: True), identifies uncovered gaps within each Barangay after clipping.</li>"
            "<li><b>Assign Gaps to Contiguous EA</b> — When enabled (default: True), assigns each detected gap to the adjacent EA sharing the longest boundary.</li>"
            "</ul>"

            "<h4>Process</h4>"
            "<ol>"
            "<li>Validates input Barangay and EA vector layers and repairs invalid geometries.</li>"
            "<li>Matches each EA to its parent Barangay using attribute geocode prefix matching, centroid containment, or largest spatial overlap.</li>"
            "<li>Clips EAs extending beyond parent Barangay boundaries by computing spatial intersections.</li>"
            "<li>Computes uncovered Barangay coverage gaps by taking the spatial difference between the Barangay polygon and the union of constituent EAs.</li>"
            "<li>Decomposes gap geometries and assigns each gap polygon to the adjacent contiguous EA sharing the longest boundary (or nearest/largest EA).</li>"
            "<li>Performs final topological validation to ensure zero EAs extend outside Barangays and no uncovered gaps remain.</li>"
            "<li>Generates pre-processed output polygon features preserving original fields and adding process summary metadata.</li>"
            "</ol>"

            "<h4>Output</h4>"
            "<ul>"
            "<li><b>Pre-Processed EA Layer</b> (polygon, named <i>&lt;5-digit geocode&gt;_ea2026_preprocessed</i>) — "
            "In-memory vector layer containing pre-processed EAs fully aligned with Barangay boundaries and gap-filled. "
            "All fields from the original EA layer are preserved. Additional/updated fields:</li>"
            "<li><i>original_area</i> — Original surface area of the EA polygon in square metres.</li>"
            "<li><i>corrected_area</i> — Corrected surface area of the EA polygon after clipping and gap assignment.</li>"
            "<li><i>area_change</i> — Net area change (square metres) after pre-processing.</li>"
            "<li><i>pre_action</i> — Pre-processing action applied to the feature (e.g. <i>No Change</i>, <i>Clipped</i>, <i>Gap Assigned</i>).</li>"
            "<li><i>pre_status</i> — Pre-processing validation status (e.g. <i>Valid</i>, <i>Corrected</i>, <i>Unresolved</i>).</li>"
            "</ul>"
        )

    def run(
        self,
        barangay_layer: QgsVectorLayer,
        ea_layer: QgsVectorLayer,
        gap_tolerance: float = 1.0,
        clip_to_bgy: bool = True,
        detect_gaps: bool = True,
        assign_gaps: bool = True,
        feedback_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        is_cancelled_fn: Optional[Callable[[], bool]] = None,
    ) -> PreEAResult:
        """
        Run the full Pre-EA Processing workflow.

        :param barangay_layer: Polygon vector layer of Barangays.
        :param ea_layer: Polygon vector layer of EAs.
        :param gap_tolerance: Minimum area (m²) for a gap to be considered meaningful.
        :param clip_to_bgy: Whether to clip EAs extending outside their parent Barangay.
        :param detect_gaps: Whether to detect uncovered areas within each Barangay.
        :param assign_gaps: Whether to assign detected gaps to contiguous EAs.
        :param feedback_callback: Optional callable receiving log message strings.
        :param progress_callback: Optional callable receiving integer 0-100 progress values.
        :param is_cancelled_fn: Optional callable returning True when the user cancels.
        :returns: PreEAResult containing the output layer, summary, per-EA rows, and logs.
        """
        log_lines: List[str] = []
        result_rows: List[ResultRow] = []
        summary = PreEASummary()

        def _log(msg: str) -> None:
            log_lines.append(msg)
            if feedback_callback:
                feedback_callback(msg)

        def _progress(pct: int) -> None:
            if progress_callback:
                progress_callback(pct)

        def _cancelled() -> bool:
            return bool(is_cancelled_fn and is_cancelled_fn())

        try:
            _log("[INFO] Starting Pre-EA Processing...")
            _log(f"[INFO] Barangay Layer: {barangay_layer.name()}")
            _log(f"[INFO] EA Layer: {ea_layer.name()}")
            _log("[INFO] Validating input layers...")

            # -- Input validation -------------------------------------------------
            validation_error = self._validate_inputs(barangay_layer, ea_layer)
            if validation_error:
                _log(f"[ERROR] {validation_error}")
                summary.overall_status = "ERROR"
                return PreEAResult(
                    output_layer=None,
                    summary=summary,
                    result_rows=result_rows,
                    log_lines=log_lines,
                    success=False,
                    error_message=validation_error,
                )

            # -- Repair input geometries ------------------------------------------
            _log("[INFO] Checking and repairing input geometries...")
            bgy_features = self._load_and_repair_features(barangay_layer, _log, "Barangay")
            ea_features = self._load_and_repair_features(ea_layer, _log, "EA")

            if not bgy_features:
                msg = "Barangay layer has no valid features after geometry repair."
                _log(f"[ERROR] {msg}")
                summary.overall_status = "ERROR"
                return PreEAResult(None, summary, result_rows, log_lines, False, msg)

            if not ea_features:
                msg = "EA layer has no valid features after geometry repair."
                _log(f"[ERROR] {msg}")
                summary.overall_status = "ERROR"
                return PreEAResult(None, summary, result_rows, log_lines, False, msg)

            _progress(5)

            # -- Phase 1: EA-to-Barangay matching ---------------------------------
            _log("[INFO] Matching EAs to parent Barangays...")
            bgy_index = QgsSpatialIndex()
            bgy_by_fid: Dict[int, QgsFeature] = {}
            for feat in bgy_features:
                bgy_index.addFeature(feat)
                bgy_by_fid[feat.id()] = feat

            ea_to_bgy: Dict[int, int] = self._match_ea_to_barangay(
                ea_features, bgy_by_fid, bgy_index, _log
            )

            if _cancelled():
                _log("[INFO] Processing cancelled by user.")
                summary.overall_status = "ERROR"
                return PreEAResult(None, summary, result_rows, log_lines, False, "Cancelled")

            _progress(15)

            # -- Build per-Barangay EA lists --------------------------------------
            bgy_to_eas: Dict[int, List[QgsFeature]] = {}
            for ea_feat in ea_features:
                bgy_fid = ea_to_bgy.get(ea_feat.id())
                if bgy_fid is None:
                    _log(
                        f"[WARNING] EA {self._ea_label(ea_feat)} could not be matched "
                        "to a parent Barangay. It will be skipped."
                    )
                    continue
                bgy_to_eas.setdefault(bgy_fid, []).append(ea_feat)

            # -- Corrected geometry dict: ea_fid -> QgsGeometry ------------------
            corrected_geoms: Dict[int, QgsGeometry] = {}

            total_bgys = len(bgy_to_eas)
            summary.barangays_processed = total_bgys

            for bgy_step, (bgy_fid, eas_in_bgy) in enumerate(bgy_to_eas.items()):
                if _cancelled():
                    _log("[INFO] Processing cancelled by user.")
                    summary.overall_status = "ERROR"
                    return PreEAResult(None, summary, result_rows, log_lines, False, "Cancelled")

                bgy_feat = bgy_by_fid[bgy_fid]
                bgy_geom = bgy_feat.geometry()
                bgy_label = self._bgy_label(bgy_feat)
                _log(f"[INFO] Processing Barangay {bgy_label} ({len(eas_in_bgy)} EAs)...")

                # ---- Phase 2: Clip EAs to Barangay ----------------------------
                for ea_feat in eas_in_bgy:
                    ea_geom = ea_feat.geometry()
                    ea_label = self._ea_label(ea_feat)
                    original_area = ea_geom.area()

                    if not clip_to_bgy:
                        corrected_geoms[ea_feat.id()] = ea_geom
                        summary.eas_processed += 1
                        result_rows.append(ResultRow(
                            barangay_id=bgy_label,
                            ea_id=ea_label,
                            original_area=original_area,
                            corrected_area=original_area,
                            area_change=0.0,
                            action="No Change",
                            status="Valid",
                        ))
                        continue

                    # Check if EA extends beyond the Barangay
                    if bgy_geom.contains(ea_geom):
                        corrected_geoms[ea_feat.id()] = ea_geom
                        summary.eas_processed += 1
                        result_rows.append(ResultRow(
                            barangay_id=bgy_label,
                            ea_id=ea_label,
                            original_area=original_area,
                            corrected_area=original_area,
                            area_change=0.0,
                            action="No Change",
                            status="Valid",
                        ))
                    else:
                        _log(f"[INFO] EA {ea_label} extends outside Barangay {bgy_label}. Clipping...")
                        summary.eas_requiring_correction += 1
                        clipped = ea_geom.intersection(bgy_geom)
                        clipped = self._clean_geometry(clipped, _log, f"EA {ea_label} (clipped)")
                        if clipped is None or clipped.isEmpty():
                            _log(
                                f"[WARNING] EA {ea_label} intersection with Barangay {bgy_label} "
                                "produced an empty geometry. Skipping EA."
                            )
                            result_rows.append(ResultRow(
                                barangay_id=bgy_label,
                                ea_id=ea_label,
                                original_area=original_area,
                                corrected_area=0.0,
                                area_change=-original_area,
                                action="Error",
                                status="Error",
                            ))
                        else:
                            corrected_area = clipped.area()
                            corrected_geoms[ea_feat.id()] = clipped
                            summary.eas_clipped += 1
                            summary.eas_processed += 1
                            _log(f"[INFO] EA {ea_label} clipped successfully.")
                            result_rows.append(ResultRow(
                                barangay_id=bgy_label,
                                ea_id=ea_label,
                                original_area=original_area,
                                corrected_area=corrected_area,
                                area_change=corrected_area - original_area,
                                action="Clipped",
                                status="Corrected",
                            ))

                # ---- Phase 3+4: Fill Barangay gaps (unconditional) -----------
                # Always compute gap = bgy_geom - union(EAs) and fill every
                # uncovered area into the adjacent EA.  The Barangay polygon is
                # the definitive outer boundary; no area inside it is left unfilled.
                self._fill_barangay_gaps(
                    bgy_geom=bgy_geom,
                    bgy_label=bgy_label,
                    eas_in_bgy=eas_in_bgy,
                    corrected_geoms=corrected_geoms,
                    gap_tolerance=gap_tolerance,
                    summary=summary,
                    result_rows=result_rows,
                    log_fn=_log,
                    crs=barangay_layer.crs(),
                )

                bgy_step_pct = 15 + int((bgy_step + 1) / max(total_bgys, 1) * 70)
                _progress(bgy_step_pct)


            _progress(85)

            # -- Phase 5: Final validation ----------------------------------------
            _log("[INFO] Performing final topology validation...")
            self._final_validation(
                bgy_by_fid, bgy_to_eas, ea_to_bgy, corrected_geoms, summary, _log
            )

            _progress(90)

            # -- Phase 6: Build output layer --------------------------------------
            output_name = self._build_output_name(barangay_layer, ea_layer)
            summary.output_name = output_name
            _log(f"[INFO] Building output layer: {output_name}")

            output_layer = self._build_output_layer(
                ea_layer, ea_features, corrected_geoms, ea_to_bgy, bgy_by_fid, output_name, _log,
                crs=barangay_layer.crs()
            )

            if output_layer is None:
                summary.overall_status = "ERROR"
                return PreEAResult(None, summary, result_rows, log_lines, False, "Failed to build output layer.")

            # Add to QGIS project
            QgsProject.instance().addMapLayer(output_layer)
            _log(f"[INFO] Output layer added to QGIS project: {output_name}")
            _progress(100)

            # Determine overall status
            if summary.unresolved_gaps > 0 or summary.final_eas_outside_bgy > 0:
                summary.overall_status = "WARNING"
            else:
                summary.overall_status = "PASS"

            _log(f"[INFO] Processing completed. Status: {summary.overall_status}")
            _log(f"[INFO] Output: {output_name}")

            return PreEAResult(
                output_layer=output_layer,
                summary=summary,
                result_rows=result_rows,
                log_lines=log_lines,
                success=True,
            )

        except Exception as exc:
            error_msg = f"Unexpected error during Pre-EA Processing: {exc}"
            _log(f"[ERROR] {error_msg}")
            summary.overall_status = "ERROR"
            return PreEAResult(
                output_layer=None,
                summary=summary,
                result_rows=result_rows,
                log_lines=log_lines,
                success=False,
                error_message=error_msg,
            )

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def _validate_inputs(
        self, barangay_layer: QgsVectorLayer, ea_layer: QgsVectorLayer
    ) -> Optional[str]:
        """Return an error string if inputs are invalid, else None."""
        if not barangay_layer:
            return "Barangay Layer is required."
        if not ea_layer:
            return "EA Layer is required."
        if not barangay_layer.isValid():
            return "Barangay Layer is not a valid layer."
        if not ea_layer.isValid():
            return "EA Layer is not a valid layer."

        bgy_geom_type = barangay_layer.geometryType()
        if bgy_geom_type != QgsWkbTypes.PolygonGeometry:
            return "Barangay Layer must be a polygon layer."

        ea_geom_type = ea_layer.geometryType()
        if ea_geom_type != QgsWkbTypes.PolygonGeometry:
            return "EA Layer must be a polygon layer."

        if barangay_layer.featureCount() == 0:
            return "Barangay Layer contains no features."
        if ea_layer.featureCount() == 0:
            return "EA Layer contains no features."

        return None

    # -------------------------------------------------------------------------
    # Geometry helpers
    # -------------------------------------------------------------------------

    def _load_and_repair_features(
        self,
        layer: QgsVectorLayer,
        log_fn: Callable[[str], None],
        layer_label: str,
    ) -> List[QgsFeature]:
        """Load all features from a layer, repairing invalid geometries."""
        features: List[QgsFeature] = []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                log_fn(
                    f"[WARNING] Empty geometry in {layer_label} feature id={feat.id()}. Skipping."
                )
                continue
            if not geom.isGeosValid():
                repaired = geom.makeValid()
                if repaired and not repaired.isEmpty():
                    fixed_feat = QgsFeature(feat)
                    fixed_feat.setGeometry(repaired)
                    features.append(fixed_feat)
                    log_fn(
                        f"[INFO] Invalid geometry repaired for {layer_label} feature id={feat.id()}."
                    )
                else:
                    log_fn(
                        f"[WARNING] Could not repair geometry for {layer_label} feature id={feat.id()}. Skipping."
                    )
            else:
                features.append(feat)
        return features

    def _clean_geometry(
        self,
        geom: Optional[QgsGeometry],
        log_fn: Callable[[str], None],
        label: str,
    ) -> Optional[QgsGeometry]:
        """Repair a geometry if invalid; return None if it cannot be repaired."""
        if geom is None or geom.isEmpty():
            return None
        if not geom.isGeosValid():
            repaired = geom.makeValid()
            if repaired and not repaired.isEmpty():
                return repaired
            log_fn(f"[WARNING] Could not repair geometry for {label}.")
            return None
        return geom

    def _explode_to_polygons(self, geom: QgsGeometry) -> List[QgsGeometry]:
        """Decompose a geometry into a list of single-part polygon geometries."""
        polygons: List[QgsGeometry] = []
        if geom is None or geom.isEmpty():
            return polygons

        flat_type = QgsWkbTypes.flatType(geom.wkbType())
        if flat_type == QgsWkbTypes.Polygon:
            polygons.append(geom)
        elif flat_type == QgsWkbTypes.MultiPolygon:
            for part in geom.constParts():
                polygons.append(QgsGeometry(part.clone()))
        elif flat_type == QgsWkbTypes.GeometryCollection or geom.isMultipart():
            try:
                for part in geom.constParts():
                    part_geom = QgsGeometry(part.clone())
                    part_flat = QgsWkbTypes.flatType(part_geom.wkbType())
                    if part_flat == QgsWkbTypes.Polygon:
                        polygons.append(part_geom)
                    elif part_flat == QgsWkbTypes.MultiPolygon:
                        for sub_part in part_geom.constParts():
                            polygons.append(QgsGeometry(sub_part.clone()))
                    elif part_flat == QgsWkbTypes.GeometryCollection:
                        polygons.extend(self._explode_to_polygons(part_geom))
            except Exception:
                if flat_type in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
                    polygons.append(geom)
        else:
            if flat_type in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
                polygons.append(geom)
        return polygons

    # -------------------------------------------------------------------------
    # EA-to-Barangay matching
    # -------------------------------------------------------------------------

    def _match_ea_to_barangay(
        self,
        ea_features: List[QgsFeature],
        bgy_by_fid: Dict[int, QgsFeature],
        bgy_index: QgsSpatialIndex,
        log_fn: Callable[[str], None],
    ) -> Dict[int, int]:
        """
        Return a mapping of EA feature id -> Barangay feature id.

        Strategy:
          1. Attribute geocode prefix match (first _GEOCODE_PREFIX_LEN digits).
          2. Spatial fallback: Barangay whose polygon contains the EA centroid,
             or has the largest intersection area with the EA.
        """
        ea_to_bgy: Dict[int, int] = {}

        # Pre-extract Barangay geocode prefixes for attribute matching
        bgy_geocode_map: Dict[str, int] = {}  # prefix -> bgy fid
        for bgy_fid, bgy_feat in bgy_by_fid.items():
            prefix = self._extract_geocode_prefix(bgy_feat, _GEOCODE_FIELDS)
            if prefix:
                bgy_geocode_map[prefix] = bgy_fid

        for ea_feat in ea_features:
            ea_fid = ea_feat.id()
            matched_bgy_fid: Optional[int] = None

            # Strategy 1: attribute geocode prefix
            ea_prefix = self._extract_geocode_prefix(ea_feat, _EA_GEOCODE_FIELDS)
            if ea_prefix and ea_prefix in bgy_geocode_map:
                matched_bgy_fid = bgy_geocode_map[ea_prefix]

            # Strategy 2: spatial — Barangay containing the EA centroid
            if matched_bgy_fid is None:
                centroid = ea_feat.geometry().centroid()
                candidate_fids = bgy_index.intersects(centroid.boundingBox())
                for bgy_fid in candidate_fids:
                    bgy_geom = bgy_by_fid[bgy_fid].geometry()
                    if bgy_geom.contains(centroid):
                        matched_bgy_fid = bgy_fid
                        break

            # Strategy 3: spatial — largest intersection area
            if matched_bgy_fid is None:
                ea_bbox = ea_feat.geometry().boundingBox()
                candidate_fids = bgy_index.intersects(ea_bbox)
                best_area = 0.0
                for bgy_fid in candidate_fids:
                    bgy_geom = bgy_by_fid[bgy_fid].geometry()
                    inter = ea_feat.geometry().intersection(bgy_geom)
                    if inter and not inter.isEmpty():
                        area = inter.area()
                        if area > best_area:
                            best_area = area
                            matched_bgy_fid = bgy_fid

            if matched_bgy_fid is not None:
                ea_to_bgy[ea_fid] = matched_bgy_fid
            else:
                log_fn(
                    f"[WARNING] EA {self._ea_label(ea_feat)} could not be matched to any Barangay."
                )

        return ea_to_bgy

    def _extract_geocode_prefix(
        self, feat: QgsFeature, field_names: Tuple[str, ...]
    ) -> Optional[str]:
        """
        Extract the first _GEOCODE_PREFIX_LEN digit characters from a geocode
        attribute field.  Returns None if no match is found.
        """
        feat_fields = feat.fields()
        for candidate_name in field_names:
            # Case-insensitive field lookup
            for i in range(feat_fields.count()):
                if feat_fields.at(i).name().lower() == candidate_name.lower():
                    val = feat.attribute(i)
                    if val is None:
                        break
                    digits = re.sub(r"\D", "", str(val))
                    if len(digits) >= _GEOCODE_PREFIX_LEN:
                        return digits[:_GEOCODE_PREFIX_LEN]
                    elif len(digits) >= 5:
                        return digits[:5]
                    break
        # Fallback: try layer name digits
        return None

    # -------------------------------------------------------------------------
    # Gap assignment
    # -------------------------------------------------------------------------

    def _fill_barangay_gaps(
        self,
        bgy_geom: QgsGeometry,
        bgy_label: str,
        eas_in_bgy: List[QgsFeature],
        corrected_geoms: Dict[int, QgsGeometry],
        gap_tolerance: float,
        summary: "PreEASummary",
        result_rows: List["ResultRow"],
        log_fn: Callable[[str], None],
        crs: Optional[QgsCoordinateReferenceSystem] = None,
    ) -> None:
        """
        Fill every gap inside a Barangay polygon by distributing uncovered areas
        into adjacent EAs.

        The Barangay polygon is the definitive outer boundary.  The gap is
        computed as::

            gap = bgy_geom.difference( union_of_all_eas_in_barangay )

        Each gap piece is assigned to the adjacent or nearest EA sharing the longest
        boundary or closest distance.

        :param bgy_geom:       Geometry of the Barangay polygon.
        :param bgy_label:      Human-readable label used in log messages.
        :param eas_in_bgy:     EA features that belong to this Barangay.
        :param corrected_geoms: Mutable dict of ea_fid -> current geometry.
                                Updated in-place as gaps are merged.
        :param gap_tolerance:  Minimum gap area (m²) to report as a distinct gap item.
        :param summary:        PreEASummary counters, updated in-place.
        :param result_rows:    Per-EA result rows, updated in-place.
        :param log_fn:         Logging callback.
        :param crs:            Optional Coordinate Reference System for distance thresholds.
        """
        ea_geoms_in_bgy = [
            corrected_geoms[ea_feat.id()]
            for ea_feat in eas_in_bgy
            if ea_feat.id() in corrected_geoms
        ]

        if not ea_geoms_in_bgy:
            return

        # Compute total gap = Barangay polygon minus union of all EAs
        ea_union = QgsGeometry.unaryUnion(ea_geoms_in_bgy)
        if ea_union is None:
            ea_union = QgsGeometry()

        gap_geom = bgy_geom.difference(ea_union)
        gap_geom = self._clean_geometry(gap_geom, log_fn, f"Barangay {bgy_label} gap")

        if gap_geom is None or gap_geom.isEmpty():
            return  # Barangay already fully covered — nothing to do

        # Decompose multipart gap into individual polygons for assignment
        gap_parts = self._explode_to_polygons(gap_geom)
        
        # Sort gap parts by area descending so larger gaps are assigned first
        gap_parts.sort(key=lambda g: g.area(), reverse=True)

        meaningful_count = sum(1 for g in gap_parts if g.area() >= gap_tolerance)
        if meaningful_count > 0:
            log_fn(f"[INFO] {meaningful_count} gap(s) detected in Barangay {bgy_label}.")
            summary.gaps_detected += meaningful_count

        for gap in gap_parts:
            gap_area = gap.area()
            if gap_area < 1e-6:
                continue

            # Primary: EA with the longest shared boundary or nearest proximity
            best_ea_fid, best_shared_len = self._find_best_ea_for_gap(
                gap, eas_in_bgy, corrected_geoms, crs
            )

            if best_ea_fid is None:
                # Fallback: largest-area EA in the Barangay
                best_ea_fid = self._largest_ea_fid(eas_in_bgy, corrected_geoms)

            if best_ea_fid is None:
                if gap_area >= gap_tolerance:
                    summary.unresolved_gaps += 1
                    log_fn(
                        f"[WARNING] Unresolved gap in Barangay {bgy_label} "
                        f"({gap_area:.2f} m²). No EA available."
                    )
                    result_rows.append(ResultRow(
                        barangay_id=bgy_label,
                        ea_id="(gap)",
                        original_area=gap_area,
                        corrected_area=gap_area,
                        area_change=0.0,
                        action="Unresolved",
                        status="Unresolved",
                    ))
                continue

            # Merge the gap into the chosen EA
            current_geom = corrected_geoms[best_ea_fid]
            merged_geom = current_geom.combine(gap).buffer(0.0, 3)
            merged_geom = self._clean_geometry(merged_geom, log_fn, "Gap merged EA")
            if merged_geom is None or merged_geom.isEmpty():
                merged_geom = current_geom

            corrected_geoms[best_ea_fid] = merged_geom

            if gap_area >= gap_tolerance:
                summary.gaps_assigned += 1

            ea_label_for_gap = self._ea_label_by_fid(best_ea_fid, eas_in_bgy)
            log_fn(
                f"[INFO] Gap ({gap_area:.2f} m²) in Barangay {bgy_label} → "
                f"EA {ea_label_for_gap} (shared edge: {best_shared_len:.2f} m)."
            )

            # Update or create the result row for the receiving EA
            for row in result_rows:
                if row.barangay_id == bgy_label and row.ea_id == ea_label_for_gap:
                    row.corrected_area = merged_geom.area()
                    row.area_change = merged_geom.area() - row.original_area
                    if row.action in ("No Change", "Clipped"):
                        row.action = "Gap Assigned"
                        row.status = "Corrected"
                    break
            else:
                result_rows.append(ResultRow(
                    barangay_id=bgy_label,
                    ea_id=ea_label_for_gap,
                    original_area=current_geom.area(),
                    corrected_area=merged_geom.area(),
                    area_change=merged_geom.area() - current_geom.area(),
                    action="Gap Assigned",
                    status="Corrected",
                ))

    def _find_best_ea_for_gap(
        self,
        gap: QgsGeometry,
        eas_in_bgy: List[QgsFeature],
        corrected_geoms: Dict[int, QgsGeometry],
        crs: Optional[QgsCoordinateReferenceSystem] = None,
    ) -> Tuple[Optional[int], float]:
        """
        Find the EA in eas_in_bgy best suited to absorb the gap.

        Primary criterion: EA sharing the longest boundary / perimeter with the gap.
        Secondary criterion: closest EA by distance (for near-touching gaps).

        :returns: (best_ea_fid, best_shared_length_or_score) or (None, 0.0)
        """
        is_geographic = crs.isGeographic() if crs else False
        search_radius = 0.0005 if is_geographic else 5.0  # 5 meters buffer search

        gap_buffered = gap.buffer(search_radius, 5)

        best_touching_fid: Optional[int] = None
        best_touching_len: float = -1.0

        best_near_fid: Optional[int] = None
        best_near_dist: float = float("inf")

        for ea_feat in eas_in_bgy:
            ea_fid = ea_feat.id()
            ea_geom = corrected_geoms.get(ea_fid)
            if ea_geom is None or ea_geom.isEmpty():
                continue

            dist = gap.distance(ea_geom)

            # Check for direct touching or near-touching
            dist_threshold = 0.00005 if is_geographic else 0.5
            if dist <= dist_threshold:
                # Measure shared boundary length
                ea_boundary = ea_geom.convertToType(QgsWkbTypes.LineGeometry)
                if ea_boundary is not None and not ea_boundary.isEmpty():
                    shared = gap_buffered.intersection(ea_boundary)
                    shared_len = shared.length() if shared else 0.0
                else:
                    shared = gap_buffered.intersection(ea_geom)
                    shared_len = shared.length() if shared else 0.0

                if shared_len > best_touching_len:
                    best_touching_len = shared_len
                    best_touching_fid = ea_fid

            # Keep track of nearest EA as fallback if no touching EA matches
            if dist < best_near_dist:
                best_near_dist = dist
                best_near_fid = ea_fid

        if best_touching_fid is not None:
            return best_touching_fid, max(best_touching_len, 0.0)

        if best_near_fid is not None:
            return best_near_fid, 0.0

        return None, 0.0

    def _largest_ea_fid(
        self,
        eas_in_bgy: List[QgsFeature],
        corrected_geoms: Dict[int, QgsGeometry],
    ) -> Optional[int]:
        """
        Return the feature id of the EA with the largest area among eas_in_bgy.

        Used as the last-resort fallback when no contiguous EA can be found
        for a gap, ensuring the gap is always absorbed by some EA rather than
        left unassigned.

        :returns: Feature id of the largest EA, or None if eas_in_bgy is empty.
        """
        best_fid: Optional[int] = None
        best_area: float = -1.0

        for ea_feat in eas_in_bgy:
            ea_fid = ea_feat.id()
            ea_geom = corrected_geoms.get(ea_fid)
            if ea_geom is None or ea_geom.isEmpty():
                continue
            area = ea_geom.area()
            if area > best_area:
                best_area = area
                best_fid = ea_fid

        return best_fid

    # -------------------------------------------------------------------------
    # Final validation
    # -------------------------------------------------------------------------

    def _final_validation(
        self,
        bgy_by_fid: Dict[int, QgsFeature],
        bgy_to_eas: Dict[int, List[QgsFeature]],
        ea_to_bgy: Dict[int, int],
        corrected_geoms: Dict[int, QgsGeometry],
        summary: PreEASummary,
        log_fn: Callable[[str], None],
    ) -> None:
        """Run post-processing spatial validation checks."""
        outside_count = 0
        uncovered_total = 0.0

        for bgy_fid, eas_in_bgy in bgy_to_eas.items():
            bgy_feat = bgy_by_fid[bgy_fid]
            bgy_geom = bgy_feat.geometry()
            bgy_label = self._bgy_label(bgy_feat)

            ea_geoms_in_bgy = [
                corrected_geoms[ea_feat.id()]
                for ea_feat in eas_in_bgy
                if ea_feat.id() in corrected_geoms
            ]

            # Validation 1: No EA outside Barangay
            for ea_feat in eas_in_bgy:
                ea_fid = ea_feat.id()
                ea_geom = corrected_geoms.get(ea_fid)
                if ea_geom is None:
                    continue
                if not bgy_geom.contains(ea_geom):
                    # Allow a very small tolerance (floating point slivers)
                    outside_area = ea_geom.difference(bgy_geom)
                    if outside_area and not outside_area.isEmpty() and outside_area.area() > 0.01:
                        outside_count += 1
                        log_fn(
                            f"[WARNING] Validation: EA {self._ea_label(ea_feat)} still extends "
                            f"outside Barangay {bgy_label} (area={outside_area.area():.4f} m²)."
                        )

            # Validation 2: No meaningful uncovered Barangay area
            if ea_geoms_in_bgy:
                ea_union = QgsGeometry.unaryUnion(ea_geoms_in_bgy)
                if ea_union:
                    residual_gap = bgy_geom.difference(ea_union)
                    if residual_gap and not residual_gap.isEmpty():
                        gap_area = residual_gap.area()
                        if gap_area > 1.0:
                            uncovered_total += gap_area
                            log_fn(
                                f"[WARNING] Validation: Barangay {bgy_label} has residual "
                                f"uncovered area of {gap_area:.2f} m²."
                            )

        summary.final_eas_outside_bgy = outside_count
        summary.final_uncovered_area = uncovered_total

        if outside_count == 0 and uncovered_total == 0.0:
            log_fn("[INFO] Final validation passed.")
        else:
            log_fn(
                f"[WARNING] Final validation: {outside_count} EA(s) outside Barangay, "
                f"{uncovered_total:.2f} m² uncovered area."
            )

    # -------------------------------------------------------------------------
    # Output layer construction
    # -------------------------------------------------------------------------

    def _build_output_layer(
        self,
        ea_layer: QgsVectorLayer,
        ea_features: List[QgsFeature],
        corrected_geoms: Dict[int, QgsGeometry],
        ea_to_bgy: Dict[int, int],
        bgy_by_fid: Dict[int, QgsFeature],
        output_name: str,
        log_fn: Callable[[str], None],
        crs: Optional[QgsCoordinateReferenceSystem] = None,
    ) -> Optional[QgsVectorLayer]:
        """
        Construct the output in-memory polygon layer.

        Copies all field definitions from the input EA layer and writes each
        EA feature with its corrected geometry and original attribute values.

        Two guarantees are enforced on every output geometry:
          1. Final clip: each EA is intersected with its parent Barangay so no
             output polygon crosses a Barangay boundary.
          2. Final reconciliation: after writing all EAs, any area within a
             Barangay not yet covered by the output EAs is decomposed into gap
             parts and merged into adjacent/nearest EAs — ensuring 100% complete
             coverage of the Barangay polygon.
        """
        # Determine CRS
        crs_auth = ea_layer.crs().authid()
        uri = f"Polygon?crs={crs_auth}"
        output_layer = QgsVectorLayer(uri, output_name, "memory")

        if not output_layer.isValid():
            log_fn("[ERROR] Failed to create output memory layer.")
            return None

        # Copy field schema from input EA layer
        dp = output_layer.dataProvider()
        ea_fields: QgsFields = ea_layer.fields()
        dp.addAttributes(ea_fields)
        output_layer.updateFields()

        # ── Pass 1: build a mutable geometry dict with the final clip applied ──
        # Maps ea_fid → final output geometry (clipped to Barangay)
        final_geoms: Dict[int, QgsGeometry] = {}

        for ea_feat in ea_features:
            ea_fid = ea_feat.id()
            geom = corrected_geoms.get(ea_fid)
            if geom is None:
                geom = ea_feat.geometry()

            # Clip to parent Barangay boundary
            bgy_fid = ea_to_bgy.get(ea_fid)
            if bgy_fid is not None and bgy_fid in bgy_by_fid:
                bgy_geom = bgy_by_fid[bgy_fid].geometry()
                if not bgy_geom.contains(geom):
                    clipped = geom.intersection(bgy_geom)
                    if clipped and not clipped.isEmpty():
                        geom = clipped

            final_geoms[ea_fid] = geom

        # ── Pass 2: reconcile — ensure every Barangay is fully covered ────────
        # Group EAs by Barangay to check coverage
        bgy_to_ea_fids: Dict[int, List[int]] = {}
        for ea_fid, bgy_fid in ea_to_bgy.items():
            if ea_fid in final_geoms:
                bgy_to_ea_fids.setdefault(bgy_fid, []).append(ea_fid)

        for bgy_fid, ea_fids in bgy_to_ea_fids.items():
            bgy_feat = bgy_by_fid.get(bgy_fid)
            if bgy_feat is None or not ea_fids:
                continue
            bgy_geom = bgy_feat.geometry()

            # Union of all output EA geometries for this Barangay
            ea_union = QgsGeometry.unaryUnion(
                [final_geoms[fid] for fid in ea_fids if not final_geoms[fid].isEmpty()]
            )

            if ea_union is None:
                ea_union = QgsGeometry()

            residual = bgy_geom.difference(ea_union)
            if residual is None or residual.isEmpty() or residual.area() < 1e-6:
                continue

            # Explode residual into individual gap polygon parts
            residual_parts = self._explode_to_polygons(residual)
            eas_in_bgy_subset = [f for f in ea_features if f.id() in ea_fids]

            for r_part in residual_parts:
                if r_part is None or r_part.isEmpty() or r_part.area() < 1e-6:
                    continue

                best_fid, _ = self._find_best_ea_for_gap(r_part, eas_in_bgy_subset, final_geoms, crs)
                if best_fid is None:
                    best_fid = self._largest_ea_fid(eas_in_bgy_subset, final_geoms)

                if best_fid is not None:
                    merged = final_geoms[best_fid].combine(r_part)
                    merged = self._clean_geometry(merged, log_fn, "Reconciliation EA")
                    if merged and not merged.isEmpty():
                        final_geoms[best_fid] = merged
                        log_fn(
                            f"[INFO] Reconciliation: residual {r_part.area():.4f} m² in Barangay "
                            f"{self._bgy_label(bgy_feat)} merged into EA fid={best_fid}."
                        )

        # ── Pass 3: write output features ──────────────────────────────────────
        new_features: List[QgsFeature] = []
        for ea_feat in ea_features:
            ea_fid = ea_feat.id()
            geom = final_geoms.get(ea_fid)
            if geom is None or geom.isEmpty():
                continue

            new_feat = QgsFeature(output_layer.fields())
            new_feat.setGeometry(geom)
            for i in range(ea_fields.count()):
                new_feat.setAttribute(i, ea_feat.attribute(i))
            new_features.append(new_feat)

        dp.addFeatures(new_features)
        output_layer.updateExtents()

        log_fn(f"[INFO] Output layer '{output_name}' created with {len(new_features)} features.")
        return output_layer

    # -------------------------------------------------------------------------
    # Output naming
    # -------------------------------------------------------------------------

    def _build_output_name(
        self, barangay_layer: QgsVectorLayer, ea_layer: QgsVectorLayer
    ) -> str:
        """
        Derive the output layer name as <pppmm>_ea2026_preprocessed.

        The 5-digit geographic code is extracted exclusively from the Barangay
        input layer, in the following priority order:

          1. The Barangay layer name (first 5 consecutive digits).
             e.g. "04340_bgy"  ->  "04340"
          2. The geocode / PSGC attribute of the first Barangay feature.
          3. Falls back to 'xxxxx' if no code can be determined.

        The EA layer name is intentionally not used as a code source so that
        the output name always mirrors the Barangay input layer.
        """
        # Priority 1: digits in the Barangay layer name
        digits = re.sub(r"\D", "", barangay_layer.name())
        if len(digits) >= 5:
            return f"{digits[:5]}_ea2026_preprocessed"

        # Priority 2: geocode attribute of the first Barangay feature
        for field_name in _GEOCODE_FIELDS:
            idx = -1
            for i in range(barangay_layer.fields().count()):
                if barangay_layer.fields().at(i).name().lower() == field_name.lower():
                    idx = i
                    break
            if idx != -1:
                feat = next(barangay_layer.getFeatures(QgsFeatureRequest().setLimit(1)), None)
                if feat:
                    val = str(feat.attribute(idx))
                    digits = re.sub(r"\D", "", val)
                    if len(digits) >= 5:
                        return f"{digits[:5]}_ea2026_preprocessed"

        return "xxxxx_ea2026_preprocessed"


    # -------------------------------------------------------------------------
    # Label helpers
    # -------------------------------------------------------------------------

    def _bgy_label(self, feat: QgsFeature) -> str:
        """Return a human-readable label for a Barangay feature."""
        fields = feat.fields()
        for candidate in ("name", "barangay", "bgy_name", "brgy_name", "adm4_en", "geocode"):
            for i in range(fields.count()):
                if fields.at(i).name().lower() == candidate:
                    val = feat.attribute(i)
                    if val is not None:
                        s = str(val).strip()
                        if s:
                            return s
        return f"fid={feat.id()}"

    def _ea_label(self, feat: QgsFeature) -> str:
        """Return a human-readable label for an EA feature."""
        fields = feat.fields()
        for candidate in ("ea_name", "ea_no", "ean", "ea_number", "geocode", "id"):
            for i in range(fields.count()):
                if fields.at(i).name().lower() == candidate:
                    val = feat.attribute(i)
                    if val is not None:
                        s = str(val).strip()
                        if s.endswith(".0"):
                            s = s[:-2]
                        if s:
                            return s
        return f"fid={feat.id()}"

    def _ea_label_by_fid(self, ea_fid: int, eas_in_bgy: List[QgsFeature]) -> str:
        """Return the label for an EA given its feature id."""
        for feat in eas_in_bgy:
            if feat.id() == ea_fid:
                return self._ea_label(feat)
        return f"fid={ea_fid}"
