# Changelog

All notable changes to the `gmd-pipeline` QGIS plugin will be documented in this file.

## [Unreleased] - 2026-07-02

### Changed

- **Simplified Delineation Process (Line: 2941-3030):** Removed the iterative loop (`while changed and iteration < max_iterations:`) from the `process_barangay_split` helper function inside `references/create_enumeration_area/algorithm.py`. The EA delineation (splitting) is now executed exactly once (single-pass) for each identified candidate.
- **Delineation Log Updates (Line: 3020-3030):** Cleaned up warning messages and logs inside `process_barangay_split` to remove the recursive iteration counts.
- **Code Comments & Feedback Logs (Line: 3274-3295):** Updated Phase 6 progress log comments and QGIS processing feedback logs to describe the phase as a "splitting process" rather than an "iterative splitting loop."

### Retained

- **Iterative Merging (Line: 3037-3293):** Kept the `process_barangay_merge` logic iterative (running up to 5 passes) so underpopulated EAs can continue to merge recursively to satisfy the minimum threshold constraint.
- **Barangay Boundaries for Merging (Line: 3151-3152):** Merging continues to strictly respect administrative boundaries, using the parent Barangay geocode as the adjacency filter.
