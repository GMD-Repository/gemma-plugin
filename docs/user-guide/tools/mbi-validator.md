# <img src="/icons/mbi_validator.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> MBI Validator

The **MBI Validator** (Map-Based Inventory Validator) cross-checks a combined Reference MBI layer (containing Gap and Overlap cases distinguished by the `mbi_type` field) against separate Checker GAP and OVERLAP polygon layers to audit and identify status mismatches, new unrecorded boundary issues, and resolved cases.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → MBI Validator
- **Algorithm ID:** `gmd_pipeline:mbi_validator`

## When to Use

Use this tool when you need to:
- Audit and cross-verify Map-Based Inventory (MBI) status reports submitted by LGUs or processing teams.
- Detect status discrepancies where a case is marked `1_Updated` (resolved) but still physically detected by the topological checker.
- Identify `2_Pending` cases that lack justification remarks or have zero intersecting building points.
- Isolate new boundary gaps or overlaps that were not previously present in the Reference dataset.
- Confirm and catalog boundary cases that have been successfully resolved.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **Reference layer** | Feature Source (Polygon) | The combined Reference MBI polygon layer containing baseline cases, `mbi_status`, `mbi_remarks`, `mbi_type`, and `num_bldg_pts`. Required. |
| **Checker GAP layer** | Feature Source (Polygon) | Topological checker output layer containing detected boundary gaps. Optional. |
| **Checker OVERLAP layer** | Feature Source (Polygon) | Topological checker output layer containing detected boundary overlaps. Optional. |

### Outputs

Outputs are generated conditionally and will only create output layers when at least one matching feature is found:

| Output | Type | Description |
|--------|------|-------------|
| **Status Mismatch** | Feature Sink (Polygon) | Cases where reported status conflicts with spatial evidence or attribute rules (e.g. marked resolved but still detected). |
| **New Cases** | Feature Sink (Polygon) | Checker cases that do not intersect any existing reference case in the baseline. |
| **Remaining Cases** | Feature Sink (Polygon) | Known, legitimately open or pending boundary cases with valid justifications. |
| **Confirmed Resolved** | Feature Sink (Polygon) | Reference cases marked `1_Updated` that are no longer detected by topological checkers. |
| **Manual Review** | Feature Sink (Polygon) | Ambiguous cases where a single checker polygon intersects multiple reference polygons. |
| **No Status** | Feature Sink (Polygon) | Reference boundary cases where the `mbi_status` field is blank or NULL. |

## Classification Rules

1. **Status Mismatch (`STATUS_MISMATCH`)**:
   - Case marked `1_Updated` but spatially detected by the Checker layer.
   - Case marked `2_Pending` with `0` building points (`num_bldg_pts = 0`) and no substantive justification remarks.
   - Case marked `1_Updated` but still intersects non-zero building points (`num_bldg_pts > 0`).

2. **New Cases (`NEW_CASE`)**:
   - Detected by Checker GAP or OVERLAP layers with zero spatial intersection against the Reference dataset.

3. **Remaining Cases (`REMAINING_CASE`)**:
   - Reference cases marked `2_Pending` that have valid remarks and active topological findings.

4. **Confirmed Resolved (`CONFIRMED_RESOLVED`)**:
   - Reference cases marked `1_Updated` with zero building points that no longer intersect any Checker polygons.

5. **Manual Review (`MANUAL_REVIEW`)**:
   - Checker polygons that spatially intersect two or more distinct Reference cases.

## Output Fields

| Field Name | Type | Description |
|------------|------|-------------|
| `case_uuid` | String (100) | Unique identifier of the boundary case |
| `case_type` | String (20) | Type of boundary case (`GAP` or `OVERLAP`) |
| `audit_flag` | String (40) | Classification flag category |
| `gmd_remarks` | String (255) | Automated audit finding explanation |
| `ref_status` | String (60) | Original status reported in Reference layer |
| `ref_remarks` | String (255) | Original remarks from Reference layer |
| `ref_involved_bgys` | String (255) | Involved barangays listed in Reference layer |

::: tip
If only one type of issue is being audited (e.g. Gaps only or Overlaps only), leave the unused Checker parameter empty. The validator will automatically audit the provided layer while cataloging reference cases for the remaining type.
:::
