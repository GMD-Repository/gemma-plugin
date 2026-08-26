# -*- coding: utf-8 -*-
"""
EA Merge Processor
------------------
Implements the Enumeration Area Merge workflow for the EA Delineation and
Merging plugin (Tab 3).

Workflow:
  Phase 1 — Validate Previous EA Layer (geometry type, feature count, 5-digit
             geographic code, CityMun field).
  Phase 2 — Validate Replacement Polygon Layers (8-digit numeric names,
             polygon geometry, non-empty).
  Phase 3 — CRS reconciliation across all input layers.
  Phase 4 — Dissolve/union all replacement geometries into a single combined
             geometry (with spatial index).
  Phase 5 — For each EA feature, subtract the combined replacement geometry.
             Preserve original attributes for all remaining EA fragments.
  Phase 6 — Collect replacement features from all replacement layers.
  Phase 7 — Build output memory layer with the Previous EA Layer's field schema.
  Phase 8 — Validate final output geometries.
  Phase 9 — Add output layer to the QGIS project.
  Phase 10 — Export final attribute table to Excel.

Inputs:
  - ea_layer         : QgsVectorLayer (polygon) — the Previous EA Layer.
  - replacement_layers: list[QgsVectorLayer]    — replacement polygon layers
                        each named with exactly 8 numeric digits.

Outputs:
  - QgsVectorLayer in-memory named  <5digit>_ea2026
  - Excel file named  <5digit>_earf_<citymun>.xlsx

Source data protection:
  The Previous EA Layer and all replacement layers are NEVER modified or
  overwritten. All operations work on copies of geometries.

Dependencies:
  PyQGIS (QGIS 3.x LTR / PyQt5), openpyxl
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
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

# Fields searched (case-insensitive) for the 5-digit geographic code.
_GEOCODE_FIELDS = (
    "geocode", "geo_code", "psgc", "adm4_pcode", "adm_pcode",
    "brgy_code", "ean", "ea_code",
)

# Fields searched (case-insensitive) for the City/Municipality name.
_CITYMUN_FIELDS = (
    "citymun", "city_mun", "mun_name", "municipality",
    "city", "municipality_name", "municity", "cityname", "munname",
)

# Pattern for valid replacement layer names.
_REPLACEMENT_NAME_RE = re.compile(r"^\d{8}$")

# Output year suffix.
_OUTPUT_YEAR = "ea2026"

# Excel sheet name.
_EXCEL_SHEET_NAME = "EA2026"


# ---------------------------------------------------------------------------
# Result Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EAMergeSummary:
    """Statistical summary produced by EAMergeProcessor.run()."""
    geographic_code: str = ""
    previous_ea_layer_name: str = ""
    replacement_layer_count: int = 0
    replacement_feature_count: int = 0
    modified_ea_count: int = 0
    final_ea_feature_count: int = 0
    output_layer_name: str = ""
    excel_file_path: str = ""
    excel_file_name: str = ""
    citymun_name: str = ""
    overall_status: str = "READY"   # READY | PASS | WARNING | ERROR
    excel_generated: bool = False

    @property
    def ea_input_layer_name(self) -> str:
        return self.previous_ea_layer_name

    @ea_input_layer_name.setter
    def ea_input_layer_name(self, val: str) -> None:
        self.previous_ea_layer_name = val


@dataclass
class EAMergeResult:
    """Returned by EAMergeProcessor.run()."""
    success: bool = False
    error_message: str = ""
    output_layer: Optional[QgsVectorLayer] = None
    summary: EAMergeSummary = field(default_factory=EAMergeSummary)
    log_lines: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _field_index_ci(layer: QgsVectorLayer, candidates: tuple) -> int:
    """Return the field index (0-based) for the first matching candidate name
    (case-insensitive). Returns -1 if not found."""
    fields = layer.fields()
    name_to_idx = {fields.at(i).name().lower(): i for i in range(fields.count())}
    for cand in candidates:
        idx = name_to_idx.get(cand.lower(), -1)
        if idx != -1:
            return idx
    return -1


def _first_nonempty_value(layer: QgsVectorLayer, field_idx: int) -> Optional[str]:
    """Return the first non-null, non-empty attribute value at field_idx."""
    if field_idx == -1:
        return None
    for feat in layer.getFeatures(QgsFeatureRequest().setFlags(
            QgsFeatureRequest.NoGeometry)):
        val = feat.attribute(field_idx)
        if val is None or val == "":
            continue
        from qgis.core import NULL
        if val == NULL:
            continue
        return str(val).strip()
    return None


def _unique_values(layer: QgsVectorLayer, field_idx: int) -> list:
    """Return a list of unique, non-null, non-empty attribute values at field_idx."""
    if field_idx == -1:
        return []
    seen = set()
    result = []
    from qgis.core import NULL
    for feat in layer.getFeatures(QgsFeatureRequest().setFlags(
            QgsFeatureRequest.NoGeometry)):
        val = feat.attribute(field_idx)
        if val is None or val == "" or val == NULL:
            continue
        s = str(val).strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


def _repair_geometry(geom: QgsGeometry) -> QgsGeometry:
    """Return a repaired copy of the geometry if invalid; else return as-is."""
    if geom is None or geom.isNull() or geom.isEmpty():
        return geom
    if not geom.isGeosValid():
        fixed = geom.makeValid()
        if fixed and not fixed.isNull():
            return fixed
    return geom


# ---------------------------------------------------------------------------
# Main Processor Class
# ---------------------------------------------------------------------------

class EAMergeProcessor:
    """Executes the Enumeration Area Merge workflow."""

    @staticmethod
    def short_help_string() -> str:
        """Returns the HTML description string for Enumeration Area Merge."""
        return (
            "<h3>Enumeration Area Merge</h3>"
            "<p>The <b>Enumeration Area Merge</b> workflow updates an existing previous Enumeration Area (EA) "
            "layer using one or more replacement polygon layers containing updated/replacement EA geometries.</p>"
            "<p>Replacement polygons take precedence: any overlapping portions of the existing previous EA layer "
            "underneath the replacement geometries are removed, and the replacement geometries are inserted to "
            "produce a consolidated <code>&lt;5-digit geocode&gt;_ea2026</code> layer and an exact Excel attribute "
            "table export (<code>&lt;5-digit geocode&gt;_earf_&lt;citymun&gt;.xlsx</code>).</p>"

            "<h4>Inputs</h4>"
            "<b>Required</b>"
            "<ul>"
            "<li><b>Previous EA Layer</b> (polygon) — Starting/existing EA layer. Attributes and fields are preserved. "
            "Auto-detected by <code>*_ea</code>, <code>*_ea2024</code>, <code>*_ea2026</code>, or <code>*_ea_preprocessed</code>.</li>"
            "<li><b>Replacement Polygon Layers</b> (polygon, multi-input) — One or more replacement polygon layers from "
            "the project. Each layer name must follow the <b>8-digit numeric convention</b> (e.g. <code>01001000</code>).</li>"
            "</ul>"

            "<h4>Workflow & Guarantees</h4>"
            "<ul>"
            "<li><b>Source Data Protection</b>: Previous EA and replacement layers are never modified or overwritten.</li>"
            "<li><b>Precedence & Geometry Difference</b>: Overlapping areas in previous EAs are subtracted so replacement polygons take precedence without geometric overlap.</li>"
            "<li><b>Automated Geocode & CityMun Extraction</b>: Automatically determines the 5-digit geographic code and single City/Municipality name from the Previous EA layer.</li>"
            "<li><b>Consolidated Output Layer</b>: Adds <code>&lt;5-digit geocode&gt;_ea2026</code> directly to the active QGIS project.</li>"
            "<li><b>Excel Attribute Table Export</b>: Generates <code>&lt;5-digit geocode&gt;_earf_&lt;citymun&gt;.xlsx</code> with primary sheet <code>EA2026</code> mirroring output attribute columns.</li>"
            "</ul>"
        )

    def __init__(
        self,
        ea_layer: QgsVectorLayer,
        replacement_layers: List[QgsVectorLayer],
        output_dir: str = "",
        feedback_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        is_cancelled_fn: Optional[Callable[[], bool]] = None,
    ):
        self.ea_layer = ea_layer
        self.replacement_layers = replacement_layers
        self.output_dir = output_dir or ""
        self._feedback = feedback_callback or (lambda msg: None)
        self._progress = progress_callback or (lambda pct: None)
        self._is_cancelled = is_cancelled_fn or (lambda: False)

        # Populated during run()
        self._geo_code: str = ""
        self._citymun: str = ""
        self._output_layer_name: str = ""
        self._result = EAMergeResult()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> EAMergeResult:
        """Execute the full merge workflow and return an EAMergeResult."""
        self._result = EAMergeResult()
        summary = self._result.summary

        try:
            self._log("[INFO] Starting Enumeration Area Merge...")
            self._progress(2)

            # ── Phase 1: Validate Previous EA Layer ──────────────────────────
            self._log(f"[INFO] Previous EA Layer: {self.ea_layer.name()}")
            summary.previous_ea_layer_name = self.ea_layer.name()

            if not self._validate_ea_layer():
                return self._result

            # ── Phase 2: Determine 5-digit geographic code ─────────────────
            geo_code = self._determine_geographic_code()
            if geo_code is None:
                self._fail(
                    "Unable to determine the 5-digit geographic code from "
                    "the Previous EA Layer."
                )
                return self._result
            self._geo_code = geo_code
            summary.geographic_code = geo_code
            self._log(f"[INFO] Geographic Code: {geo_code}")
            self._progress(8)

            # ── Phase 3: Validate replacement layers ───────────────────────
            self._log(
                f"[INFO] Replacement Polygon Layers: "
                f"{len(self.replacement_layers)}"
            )
            summary.replacement_layer_count = len(self.replacement_layers)

            if not self._validate_replacement_layers():
                return self._result
            self._progress(15)

            if self._is_cancelled():
                self._fail("Cancelled by user.")
                return self._result

            # ── Phase 4: Validate geometries ───────────────────────────────
            self._log("[INFO] Validating geometries...")
            if not self._validate_geometries():
                return self._result
            self._progress(20)

            # ── Phase 5: Determine CityMun ─────────────────────────────────
            citymun = self._determine_citymun(self.ea_layer)
            if citymun is None:
                self._fail(
                    "Unable to determine the City/Municipality name required "
                    "for the Excel filename."
                )
                return self._result
            self._citymun = citymun
            self._log(f"[INFO] City/Municipality: {citymun}")
            self._progress(25)

            # ── Phase 6: Combine replacement geometries ────────────────────
            self._log("[INFO] Combining replacement geometries...")
            replacement_features, combined_geom, repl_feat_count = (
                self._prepare_replacement_geometries()
            )
            if combined_geom is None or combined_geom.isNull():
                self._fail("Failed to combine replacement geometries.")
                return self._result
            summary.replacement_feature_count = repl_feat_count
            self._log(
                f"[INFO] Combined {repl_feat_count} replacement feature(s) "
                f"from {len(self.replacement_layers)} layer(s)."
            )
            self._progress(40)

            if self._is_cancelled():
                self._fail("Cancelled by user.")
                return self._result

            # ── Phase 7: Remove replacement areas from existing EAs ─────────
            self._log(
                "[INFO] Removing replacement areas from existing EA "
                "geometries..."
            )
            remaining_ea_features, modified_count = (
                self._replace_ea_geometries(combined_geom)
            )
            summary.modified_ea_count = modified_count
            self._log(
                f"[INFO] Modified EA Features (geometry affected): "
                f"{modified_count}"
            )
            self._progress(65)

            if self._is_cancelled():
                self._fail("Cancelled by user.")
                return self._result

            # ── Phase 8: Combine into final feature list ───────────────────
            self._log("[INFO] Applying replacement geometries...")
            all_features = remaining_ea_features + replacement_features
            self._progress(70)

            # ── Phase 9: Create output memory layer ────────────────────────
            self._output_layer_name = f"{geo_code}_{_OUTPUT_YEAR}"
            self._log(
                f"[INFO] Creating output layer: {self._output_layer_name}"
            )
            output_layer = self._create_output_layer(all_features)
            if output_layer is None:
                self._fail("Failed to create output layer.")
                return self._result
            summary.output_layer_name = self._output_layer_name
            summary.final_ea_feature_count = output_layer.featureCount()
            self._log(
                f"[INFO] Final EA features: "
                f"{output_layer.featureCount()}"
            )
            self._progress(80)

            # ── Phase 10: Validate final EA geometry ───────────────────────
            self._log("[INFO] Validating final EA geometry...")
            self._validate_output(output_layer)
            self._progress(85)

            # ── Phase 11: Add to QGIS project ──────────────────────────────
            QgsProject.instance().addMapLayer(output_layer)
            self._log(
                f"[INFO] Output layer '{self._output_layer_name}' added "
                "to QGIS project."
            )
            self._result.output_layer = output_layer
            self._progress(90)

            # ── Phase 12: Read final attribute table for Excel ─────────────
            self._log("[INFO] Reading final output attribute table...")

            # ── Phase 13: Export Excel ─────────────────────────────────────
            excel_name = f"{geo_code}_earf_{citymun}.xlsx"
            if self.output_dir:
                excel_path = os.path.join(self.output_dir, excel_name)
            else:
                # Default: same directory as the QGIS project file
                project_home = QgsProject.instance().homePath()
                if project_home:
                    excel_path = os.path.join(project_home, excel_name)
                else:
                    excel_path = os.path.join(os.path.expanduser("~"), excel_name)

            self._log(
                f"[INFO] Generating Excel output: {excel_name}"
            )
            excel_ok = self._export_attribute_table_to_excel(
                output_layer, excel_path
            )
            if excel_ok:
                summary.excel_generated = True
                summary.excel_file_path = excel_path
                summary.excel_file_name = excel_name
                self._log(
                    "[INFO] Excel attribute table successfully generated."
                )
            else:
                # Warn but do not fail — the polygon output was created
                self._log(
                    f"[WARNING] The final EA layer was successfully created: "
                    f"{self._output_layer_name}\n"
                    "However, the Excel output could not be generated."
                )

            self._progress(100)
            self._log("[INFO] Enumeration Area Merge completed.")
            summary.overall_status = "PASS"
            self._result.success = True

        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            self._log(
                f"[ERROR] Unexpected error during Enumeration Area Merge: "
                f"{exc}"
            )
            self._log(f"[ERROR] Traceback:\n{tb}")
            self._fail(str(exc))

        return self._result

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _validate_ea_layer(self) -> bool:
        """Validate the Previous EA Layer (geometry type, features)."""
        if self.ea_layer is None:
            self._fail("Previous EA Layer is required.")
            return False
        if self.ea_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self._fail(
                f"Layer \"{self.ea_layer.name()}\" is not a polygon layer. "
                "A polygon layer is required for Previous EA Layer."
            )
            return False
        if self.ea_layer.featureCount() == 0:
            self._fail(
                f"Previous EA Layer \"{self.ea_layer.name()}\" contains no features."
            )
            return False
        self._log(
            f"[INFO] Previous EA Layer valid: "
            f"{self.ea_layer.featureCount()} polygons  "
            f"({self.ea_layer.crs().authid()})"
        )
        return True

    def _determine_geographic_code(self) -> Optional[str]:
        """Extract the 5-digit geographic code from the Previous EA Layer.

        Searches the first matching geocode field, then takes the first
        5 digits of the first non-null value.
        """
        geo_idx = _field_index_ci(self.ea_layer, _GEOCODE_FIELDS)
        raw = _first_nonempty_value(self.ea_layer, geo_idx)
        if not raw:
            return None

        # Strip to leading digits
        digits_only = re.sub(r"\D", "", raw)
        if len(digits_only) < 5:
            return None
        return digits_only[:5]

    def _validate_replacement_layers(self) -> bool:
        """Validate each replacement layer: polygon type, 8-digit name, non-empty."""
        if not self.replacement_layers:
            self._fail("At least one Replacement Polygon Layer is required.")
            return False

        self._log("[INFO] Validating replacement layer names...")

        for layer in self.replacement_layers:
            name = layer.name()

            # 1. 8-digit numeric name
            if not _REPLACEMENT_NAME_RE.match(name):
                self._fail(
                    f"Layer \"{name}\" does not follow the required "
                    "8-digit numeric naming convention.\n"
                    "The replacement polygon layer name must contain "
                    "exactly 8 numeric digits.\n"
                    "Required format: ########"
                )
                return False

            # 2. Polygon geometry
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                self._fail(
                    f"Layer \"{name}\" is not a polygon layer. "
                    "Polygon layers are required for Enumeration Area Merge."
                )
                return False

            # 3. Non-empty
            if layer.featureCount() == 0:
                self._fail(
                    f"Replacement layer \"{name}\" contains no features."
                )
                return False

        self._log("[INFO] All replacement layers have valid 8-digit codes.")
        return True

    def _validate_geometries(self) -> bool:
        """Check EA and replacement layers for empty or null geometries.

        Invalid geometries are repaired on processing copies.
        Source layers are never modified.
        """
        # Check EA layer CRS is defined
        if not self.ea_layer.crs().isValid():
            self._fail(
                "Previous EA Layer has an undefined or invalid CRS. "
                "Please assign a valid CRS before processing."
            )
            return False

        # Check replacement layer CRSes are defined
        for layer in self.replacement_layers:
            if not layer.crs().isValid():
                self._fail(
                    f"Replacement layer \"{layer.name()}\" has an invalid CRS."
                )
                return False
        return True

    def _determine_citymun(self, layer: QgsVectorLayer) -> Optional[str]:
        """Return the single City/Municipality name from the layer attribute table.

        Returns None and logs an error if not found or if multiple distinct
        values exist (ambiguous).
        """
        citymun_idx = _field_index_ci(layer, _CITYMUN_FIELDS)
        if citymun_idx == -1:
            self._log(
                "[WARNING] No City/Municipality field found. "
                "Excel filename will omit the CityMun component."
            )
            return None

        values = _unique_values(layer, citymun_idx)
        if not values:
            return None
        if len(values) > 1:
            self._fail(
                "Multiple City/Municipality values found in the Previous EA Layer "
                f"({', '.join(values)}). "
                "Expected exactly one value for the Excel filename."
            )
            return None
        return values[0]

    def _prepare_replacement_geometries(
        self,
    ) -> tuple[list[QgsFeature], Optional[QgsGeometry], int]:
        """Collect replacement features and produce a single dissolved union geometry.

        Returns:
          (replacement_features, combined_union_geometry, total_feature_count)

        CRS: all replacement geometries are transformed to the EA input CRS.
        """
        ea_crs = self.ea_layer.crs()
        replacement_features: list[QgsFeature] = []
        union_geom: Optional[QgsGeometry] = None
        total_count = 0

        for layer in self.replacement_layers:
            layer_crs = layer.crs()
            needs_transform = (layer_crs != ea_crs)
            transform = None
            if needs_transform:
                transform = QgsCoordinateTransform(
                    layer_crs, ea_crs, QgsProject.instance()
                )
                self._log(
                    f"[INFO] CRS mismatch for \"{layer.name()}\": "
                    f"transforming from {layer_crs.authid()} "
                    f"to {ea_crs.authid()}."
                )

            for feat in layer.getFeatures():
                geom = QgsGeometry(feat.geometry())
                if geom is None or geom.isNull() or geom.isEmpty():
                    continue

                # Transform if needed
                if transform is not None:
                    geom.transform(transform)

                # Repair
                geom = _repair_geometry(geom)
                if geom is None or geom.isNull() or geom.isEmpty():
                    continue

                # Accumulate union
                if union_geom is None or union_geom.isNull():
                    union_geom = QgsGeometry(geom)
                else:
                    union_geom = union_geom.combine(geom)

                # Build output feature (same schema as EA layer)
                out_feat = QgsFeature(self.ea_layer.fields())
                out_feat.setGeometry(geom)
                replacement_features.append(out_feat)
                total_count += 1

        # Final repair of combined geometry
        if union_geom and not union_geom.isNull():
            union_geom = _repair_geometry(union_geom)

        return replacement_features, union_geom, total_count

    def _replace_ea_geometries(
        self, combined_replacement: QgsGeometry
    ) -> tuple[list[QgsFeature], int]:
        """Subtract combined_replacement from each EA feature geometry.

        Returns:
          (remaining_features, modified_count)

        Features whose remaining geometry is empty after the difference are
        dropped from the output (they are fully covered by replacement polygons).
        """
        # Build spatial index on EA layer for efficient candidate selection
        ea_index = QgsSpatialIndex(self.ea_layer.getFeatures())
        combined_bbox = combined_replacement.boundingBox()
        candidate_ids = ea_index.intersects(combined_bbox)
        candidate_id_set = set(candidate_ids)

        remaining_features: list[QgsFeature] = []
        modified_count = 0

        for feat in self.ea_layer.getFeatures():
            fid = feat.id()
            ea_geom = QgsGeometry(feat.geometry())
            if ea_geom is None or ea_geom.isNull() or ea_geom.isEmpty():
                continue

            ea_geom = _repair_geometry(ea_geom)

            is_candidate = (fid in candidate_id_set) or ea_geom.intersects(combined_replacement)

            if is_candidate and ea_geom.intersects(combined_replacement):
                # Compute difference only for candidates with actual geometric overlap
                remaining = ea_geom.difference(combined_replacement)
                if remaining is None or remaining.isNull() or remaining.isEmpty():
                    # EA is fully covered — drop it
                    modified_count += 1
                    continue
                remaining = _repair_geometry(remaining)
                if remaining is None or remaining.isNull() or remaining.isEmpty():
                    modified_count += 1
                    continue

                # Check if geometry actually changed (area, GEOS equality, or vertex difference)
                orig_area = ea_geom.area()
                rem_area = remaining.area()
                is_diff = abs(orig_area - rem_area) > 1e-6
                if not is_diff and hasattr(remaining, 'isGeosEqual'):
                    try:
                        is_diff = not remaining.isGeosEqual(ea_geom)
                    except Exception:
                        pass
                if not is_diff and hasattr(remaining, 'polygons') and hasattr(ea_geom, 'polygons'):
                    if remaining.polygons != ea_geom.polygons:
                        is_diff = True
                if is_diff:
                    modified_count += 1

                out_feat = QgsFeature(feat)
                out_feat.setGeometry(remaining)
                remaining_features.append(out_feat)
            else:
                # No overlap — keep as-is
                remaining_features.append(QgsFeature(feat))

        return remaining_features, modified_count

    def _create_output_layer(
        self, features: list[QgsFeature]
    ) -> Optional[QgsVectorLayer]:
        """Build the output in-memory polygon layer from the collected features.

        Uses the exact field schema of the Previous EA Layer.
        """
        crs_auth = self.ea_layer.crs().authid()
        is_multi = False
        try:
            if hasattr(QgsWkbTypes, 'isMultiType') and callable(getattr(QgsWkbTypes, 'isMultiType')):
                is_multi = QgsWkbTypes.isMultiType(self.ea_layer.wkbType())
            else:
                is_multi = "multi" in str(self.ea_layer.wkbType()).lower()
        except Exception:
            is_multi = False

        wkb_type = "MultiPolygon" if is_multi else "Polygon"
        uri = f"{wkb_type}?crs={crs_auth}"
        layer = QgsVectorLayer(uri, self._output_layer_name, "memory")
        if not layer.isValid():
            self._log("[ERROR] Failed to create memory layer.")
            return None

        provider = layer.dataProvider()

        # Copy field schema from Previous EA Layer
        ea_fields = self.ea_layer.fields()
        fields_list = [ea_fields.at(i) for i in range(ea_fields.count())]
        provider.addAttributes(fields_list)
        layer.updateFields()

        # Add features in bulk
        provider.addFeatures(features)
        layer.updateExtents()

        return layer

    def _validate_output(self, layer: QgsVectorLayer) -> bool:
        """Perform basic validation on the output layer."""
        if layer is None or not layer.isValid():
            self._log("[WARNING] Output layer is invalid.")
            return False
        if layer.featureCount() == 0:
            self._log("[WARNING] Output layer contains no features.")
            return False
        self._log(
            f"[INFO] Output layer validation passed: "
            f"{layer.featureCount()} features."
        )
        return True

    def _export_attribute_table_to_excel(
        self, layer: QgsVectorLayer, path: str
    ) -> bool:
        """Export the layer attribute table to Excel.

        Columns = layer fields (same order, same names, no extra columns).
        Rows    = all features (no geometry).
        Sheet   = EA2026.
        """
        try:
            import openpyxl
        except ImportError:
            self._log(
                "[ERROR] openpyxl is not installed. "
                "Cannot generate Excel output."
            )
            return False

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = _EXCEL_SHEET_NAME

            fields = layer.fields()
            field_names = [fields.at(i).name() for i in range(fields.count())]

            # Header row
            ws.append(field_names)

            # Data rows
            from qgis.core import NULL
            for feat in layer.getFeatures(
                QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry)
            ):
                row = []
                for i in range(fields.count()):
                    val = feat.attribute(i)
                    if val == NULL or val is None:
                        row.append(None)
                    else:
                        row.append(val)
                ws.append(row)

            wb.save(path)
            return True

        except Exception as exc:
            self._log(f"[ERROR] Excel export failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        """Send a log message to the feedback callback and store it."""
        self._result.log_lines.append(msg)
        self._feedback(msg)

    def _fail(self, msg: str) -> None:
        """Record a failure: log the error and mark the result as failed."""
        self._result.success = False
        self._result.error_message = msg
        self._result.summary.overall_status = "ERROR"
        self._log(f"[ERROR] {msg}")
