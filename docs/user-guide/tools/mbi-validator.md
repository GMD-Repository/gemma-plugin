# <img src="/icons/mbi_validator.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> MBI Validator

The **MBI Validator** (Map Boundary Issues Validator) cross-checks a single combined Reference MBI layer (containing both Gap and Overlap cases, distinguished by `mbi_type`) against separate Checker GAP and OVERLAP polygon layers to audit status mismatches, new unrecorded boundary issues, confirmed resolved cases, and output consolidated GeoPackage reports.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → MBI Validator
- **Algorithm ID:** `gmd_pipeline:mbi_validator`

## When to Use

Use this tool when you need to:
- Audit and cross-verify Map Boundary Issues (MBI) status reports submitted by LGUs or processing teams.
- Detect status discrepancies where a case is marked `1_Updated` (resolved) but still physically detected by the topological checker.
- Identify `2_Pending` cases that lack justification remarks or have zero intersecting building points.
- Isolate new boundary gaps or overlaps that were not previously present in the Reference dataset.
- Confirm and catalog boundary cases that have been successfully resolved.
- Export all audit findings into a single, timestamped GeoPackage dataset (`ref_mbi_reviewed-YYYY-MM-DD_HH-MM-SS.gpkg`).

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **Reference layer** | Feature Source (Polygon) | The combined Reference MBI polygon layer containing baseline cases, `mbi_status`, `pso_remarks`, `mbi_type`, and `num_bldg_pts`. Required. Automatically pre-selects matching `ref_mbi_cases` layer loaded in active QGIS project. |
| **Checker GAP layer** | Feature Source (Polygon) | Topological checker output layer containing detected boundary gaps. Optional. Automatically pre-selects matching `Gaps` layer loaded in active QGIS project. |
| **Checker OVERLAP layer** | Feature Source (Polygon) | Topological checker output layer containing detected boundary overlaps. Optional. Automatically pre-selects matching `Overlaps` layer loaded in active QGIS project. |
| **Save outputs as GeoPackage** | Boolean | Option to consolidate all non-empty audit result categories into a single GeoPackage file. Default is `False`. |
| **Save Path** | Folder Directory | Destination folder where the GeoPackage will be saved. Optional unless **Save outputs as GeoPackage** is checked. The filename is automatically generated as `ref_mbi_reviewed-YYYY-MM-DD_HH-MM-SS.gpkg`. |

### Outputs

Outputs are generated conditionally and will only create output layers when at least one matching feature is found:

| Output | Type | Description |
|--------|------|-------------|
| **Status Mismatch** | Feature Sink (Polygon) | Cases where reported status conflicts with spatial evidence or attribute rules (e.g. marked resolved but still detected, Pending w/ 0 building points and no remarks, or Updated w/ nonzero building points and no remarks). |
| **Mismatch with Remarks** | Feature Sink (Polygon) | Reference cases marked `1_Updated` with non-zero building points where remarks are present (review justification). |
| **Pending Cases** | Feature Sink (Polygon) | All `2_Pending` reference cases, except Pending with 0 building points and no remarks (which routes to Status Mismatch). |
| **New Cases** | Feature Sink (Polygon) | Checker cases that do not genuinely overlap any existing reference case in the baseline. |
| **Remaining Cases** | Feature Sink (Polygon) | Baseline reference cases actively detected by the checker that remain open (non-Pending, non-Updated). |
| **Confirmed Resolved** | Feature Sink (Polygon) | Reference cases marked `1_Updated` with 0 building points that are no longer detected by topological checkers. |
| **Manual Review** | Feature Sink (Polygon) | Ambiguous cases where a single checker polygon overlaps multiple reference polygons. |
| **No Status** | Feature Sink (Polygon) | Reference boundary cases where the `mbi_status` field is blank or NULL. |
| **GeoPackage File** | File (GeoPackage) | Timestamped `.gpkg` file containing each non-empty result category as an individual layer table. |

## How It Works

1. **Layer Auto-Detection**:
   - When the tool dialog opens, the algorithm scans loaded layers in `QgsProject.instance()` for valid polygon vector layers matching `ref_mbi_cases`, `Gaps`, or `Overlaps` in their layer names and pre-populates parameter dropdowns automatically.

2. **Genuine Area Overlap Linking**:
   - Checker polygons are matched against Reference features using spatial index intersection (`QgsSpatialIndex`).
   - Boundary-touching features (sharing only edges or vertices without interior area overlap) are excluded from matching to prevent brand-new adjacent boundary cases from inheriting old reference statuses.

3. **Status Audit & Rule Evaluation**:
   - **Status Mismatch**: Cases reported as `1_Updated` (resolved) that are still physically detected, `2_Pending` cases with `0` building points and empty remarks, or `1_Updated` cases with remaining building points and empty remarks.
   - **Mismatch with Remarks**: Cases marked `1_Updated` with remaining building points and non-empty justification remarks.
   - **Pending Cases**: Reference cases marked `2_Pending` (with building points or remarks), providing a dedicated layer for all open pending boundary issues.
   - **Remaining Cases**: Cases in the reference layer confirmed detected by the checker that remain legitimately open for other non-Pending status codes.
   - **Confirmed Resolved**: Reference cases marked `1_Updated` with zero building points that no longer spatially intersect any active checker polygon.
   - **New Cases**: Active checker polygons that have zero interior area overlap against reference cases.

4. **Timestamped GeoPackage Consolidation**:
   - If enabled (by checking **Save outputs as GeoPackage**), non-empty result categories are automatically saved into a single `.gpkg` file formatted as `ref_mbi_reviewed-YYYY-MM-DD_HH-MM-SS.gpkg`. A **Save Path** destination folder is required only when this option is checked; if unchecked, the algorithm runs without requiring an output folder.

## Classification Rules

1. **Status Mismatch (`STATUS_MISMATCH`)**:
   - Case marked `1_Updated` but spatially detected by the Checker layer.
   - Case marked `2_Pending` with `0` building points (`num_bldg_pts = 0`) and no substantive justification remarks.
   - Case marked `1_Updated` with non-zero building points (`num_bldg_pts > 0`) and no substantive justification remarks.

2. **Mismatch with Remarks (`MISMATCH_WITH_REMARKS`)**:
   - Case marked `1_Updated` with non-zero building points (`num_bldg_pts > 0`) and containing non-empty justification remarks.

3. **Pending Cases (`PENDING_CASES`)**:
   - All cases marked `2_Pending` (with remarks or with building points > 0).

4. **New Cases (`NEW_CASE`)**:
   - Detected by Checker GAP or OVERLAP layers with zero area overlap against the Reference dataset (merely touching polygon boundaries does not count as a match).

5. **Remaining Cases (`REMAINING_CASE`)**:
   - Reference cases detected by the Checker layer that remain open (non-Pending, non-Updated).

6. **Confirmed Resolved (`CONFIRMED_RESOLVED`)**:
   - Reference cases marked `1_Updated` with zero building points that no longer overlap any Checker polygons.

7. **Manual Review (`MANUAL_REVIEW`)**:
   - Checker polygons that spatially overlap two or more distinct Reference cases.

8. **No Status (`NO_STATUS`)**:
   - Reference boundary cases where the `mbi_status` field is empty or NULL.

## Output Fields

| Field Name | Type | Description |
|------------|------|-------------|
| `case_uuid` | String (100) | Unique identifier of the boundary case |
| `case_type` | String (20) | Type of boundary case (`Gap` or `Overlap`) |
| `remarks` | String (255) | Automated audit finding explanation |
| `ref_status` | String (60) | Original status reported in Reference layer |
| `ref_remarks` | String (255) | Original remarks from Reference layer |
| `ref_involved_bgys` | String (255) | Involved barangays listed in Reference layer |
| `ref_num_bldg_pts` | Integer | Count of building points inside reference polygon |

## Supported Geometry Types

- **Polygon** and **MultiPolygon**

::: tip
If only one type of issue is being audited (e.g. Gaps only or Overlaps only), leave the unused Checker parameter empty. The validator will automatically audit the provided layer while cataloging reference cases for the remaining type.
:::
