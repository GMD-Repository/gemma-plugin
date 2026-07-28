# Changelog

All notable changes to the `gmd-pipeline` QGIS plugin will be documented in this file.

## [Unreleased] - 2026-07-28

### Fixed

- **Blank Geographic Fields on Merged EA Output Layer (MERGED_OUTPUT only):** Merged EA features had blank values for `region`, `province`, `city_mun`, `barangay`, `name`, and `ean` fields. The existing `barangay_attrs_cache` (built from the first non-NULL EA per barangay) failed when all source EAs were also blank. Fix adds a `barangay_max_hh_attrs_cache` — a per-barangay lookup that tracks the attributes of the EA with the **highest household count** in the final `eas` list. After the primary cache fill, any field still blank on a merged EA is filled from that highest-hhcount EA's attributes. The highest hhcount always prevails. This secondary fill is scoped exclusively to the `MERGED_OUTPUT` layer (`from_merge=True`). Changes in [algorithm.py](algorithm.py) at Lines ~4861–4875 (`barangay_max_hh_attrs_cache` build) and ~4983–5006 (secondary fill).


## [Unreleased] - 2026-07-02

### Changed

- **Simplified Delineation Process (Line: 2941-3030):** Removed the iterative loop (`while changed and iteration < max_iterations:`) from the `process_barangay_split` helper function inside `references/create_enumeration_area/algorithm.py`. The EA delineation (splitting) is now executed exactly once (single-pass) for each identified candidate.
- **Delineation Log Updates (Line: 3020-3030):** Cleaned up warning messages and logs inside `process_barangay_split` to remove the recursive iteration counts.
- **Code Comments & Feedback Logs (Line: 3274-3295):** Updated Phase 6 progress log comments and QGIS processing feedback logs to describe the phase as a "splitting process" rather than an "iterative splitting loop."

### Retained

- **Iterative Merging (Line: 3037-3293):** Kept the `process_barangay_merge` logic iterative (running up to 5 passes) so underpopulated EAs can continue to merge recursively to satisfy the minimum threshold constraint.
- **Barangay Boundaries for Merging (Line: 3151-3152):** Merging continues to strictly respect administrative boundaries, using the parent Barangay geocode as the adjacency filter.
