# Changelog

All notable changes to the `gmd-pipeline` QGIS plugin will be documented in this file.

## [Unreleased] - 2026-07-28

### Fixed

- **Global Blank EA Feature Exclusion:**
  - Added a feature guard prior to adding features to output sinks (`delineated_sink`, `merged_sink`, etc.).
  - Any feature with an **empty geometry** or **unpopulated key identifiers (`geocode`/`ean`)** is automatically skipped (`continue`) and logged as a warning.
  - Guarantees that **no blank EA rows** can ever exist in any output attribute table. Changes in [algorithm.py](algorithm.py) at Lines ~5103–5125.
- **Strict EA Merging Rules Enforced:**
  - Merging is strictly restricted to **2 contiguous EAs** (`touches()` or `intersects()`).
  - Neither EA can be a **delineation candidate** (`hhcount >= max_household` or intersecting gap/overlap).
  - Merging is strictly performed **within the same parent barangay** (`parent_barangay` match).
  - The resulting combined household count **must not exceed `max_household` (300)** (`combined <= 300`).
  - Removed non-contiguous centroid-distance fallback (Pass 3) from the compliance sweep to guarantee strict boundary contiguity. Changes in [algorithm.py](algorithm.py) at Lines ~4320–4365.
- **"Cannot zoom to selected feature(s): No extent could be determined" on Merged EAs:** Merged EA features were written to the `MERGED_OUTPUT` sink with a null/empty geometry when `clean_and_remove_holes()` classified the merged polygon as a sliver (area < threshold) and returned `QgsGeometry()`. No guard existed after the cleaner, so the empty geometry was silently written — producing a feature with no spatial extent and triggering the QGIS zoom error. Fix adds two guards: (1) immediately after `clean_and_remove_holes()` — for merged EAs, falls back to the pre-clean geometry and logs a warning instead of emitting a null-extent feature; for all other EA types, skips the feature with a warning; (2) after the final `simplify()`/`makeValid()` — skips any EA whose geometry is still empty after those operations. Changes in [algorithm.py](algorithm.py) at Lines ~4933–4970.


## [Unreleased] - 2026-07-02

### Changed

- **Simplified Delineation Process (Line: 2941-3030):** Removed the iterative loop (`while changed and iteration < max_iterations:`) from the `process_barangay_split` helper function inside `references/create_enumeration_area/algorithm.py`. The EA delineation (splitting) is now executed exactly once (single-pass) for each identified candidate.
- **Delineation Log Updates (Line: 3020-3030):** Cleaned up warning messages and logs inside `process_barangay_split` to remove the recursive iteration counts.
- **Code Comments & Feedback Logs (Line: 3274-3295):** Updated Phase 6 progress log comments and QGIS processing feedback logs to describe the phase as a "splitting process" rather than an "iterative splitting loop."

### Retained

- **Iterative Merging (Line: 3037-3293):** Kept the `process_barangay_merge` logic iterative (running up to 5 passes) so underpopulated EAs can continue to merge recursively to satisfy the minimum threshold constraint.
- **Barangay Boundaries for Merging (Line: 3151-3152):** Merging continues to strictly respect administrative boundaries, using the parent Barangay geocode as the adjacency filter.
