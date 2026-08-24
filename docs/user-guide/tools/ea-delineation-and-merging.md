# <img src="/icons/create_ea.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> EA Delineation and Merging

The **EA Delineation and Merging** module automates the pre-processing, spatial aggregation, delineation (splitting), and merging of census Enumeration Areas (EAs) based on building household load, spatial contiguity, administrative barangay boundaries, and linear feature alignment (roads and rivers).

It combines two core processing tabs in a single integrated launcher dialog:

1. **Tab 1: EA Preprocessing** &mdash; Enforces spatial coverage rules, clips EAs extending outside Barangay boundaries, and fills uncovered coverage gaps within parent Barangays.
2. **Tab 2: EA Delineation & Merging** &mdash; Executes building point household aggregation, candidate classification, single-pass splitting for overpopulated EAs (>300 HH), and iterative spatial merging for underpopulated EAs (<=100 HH).

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → EA Delineation and Merging
- **Algorithm ID:** `gmd_pipeline:createea`
- **Menu:** Gemma → EA Delineation → EA Delineation and Merging
- **Toolbar:** Gemma Toolbar → EA Delineation and Merging icon

## When to Use

Use this module when:

- Cleaning and preparing starting EA polygon layers prior to census field operations.
- Enforcing 100% complete polygon coverage within Barangay administrative boundaries (no uncovered gaps).
- Re-balancing EA boundaries to ensure enumerator workloads fall within a target household range (default 100 to 300 households).
- Delineating overpopulated EAs (>300 households) using building point spatial clustering and road/river network centrelines.
- Merging underpopulated EAs (<=100 households) with adjacent contiguous neighbors within the same barangay boundary.

## Module Interface & Features

The **EA Delineation and Merging** launcher dialog provides an interactive workflow prior to executing processing routines:

- **Dual-Tab Processing Launcher:** Switch seamlessly between **EA Preprocessing** (Tab 1) and **EA Delineation & Merging** (Tab 2).
- **Auto-Detect Project Layers:** Automatically scans open layers in the QGIS project and populates input dropdowns based on standard layer naming conventions (`_bgy`, `_ea`, `_bldgpts`, `road`, `river`).
- **Auto Arrange Layers:** One-click utility inside **Input Layers** that restructures project layer tree nodes into `<PSGC>_<City_Mun>_MBI` and `<PSGC>_<City_Mun>_baselayers` groups, re-orders layers (Points → Lines → Polygons → Rasters), renames gaps/overlaps (`<PSGC>_gaps`, `<PSGC>_overlaps`), and applies official GEMMA QML style templates (`1. Base Layer Building Points.qml`, `2. Base Layer Landmark.qml`, etc.).
- **Fill Missing Household Counts:** Built-in utility to compute missing household counts (`hhcount`) directly from building points within each EA polygon before running delineation algorithms.
- **KPI Summary Cards & Candidate Preview:** Renders dynamic statistics and color-coded candidate tables for Delineation (>300 HH) and Merging (<=100 HH) candidates before execution.

---

## Tab 1 — EA Preprocessing

The **EA Preprocessing** tab prepares starting EA boundaries before running delineation algorithms by enforcing two fundamental spatial rules:

1. **Rule 1 (Clip to Barangay)**: Every EA polygon must be completely within its parent Barangay boundary.
2. **Rule 2 (Gap Filling)**: Every Barangay must be fully covered by its constituent EAs with zero uncovered coverage gaps remaining.

### Parameters & Options

| Parameter | Type | Description |
|-----------|------|-------------|
| **Barangay Layer** | Vector (Polygon) | Administrative barangay polygon boundaries. Must contain a `geocode` field used to assign parent barangay codes. Required. |
| **EA Layer** | Vector (Polygon) | Starting EA polygon boundaries to be pre-processed. Must contain a `geocode` field. Attributes are inherited by output. Required. |
| **Gap Area Tolerance (m²)** | Double | Minimum area threshold (default: `1.0 m²`) for a gap to be processed; smaller gaps are treated as geometry precision slivers and skipped. |
| **Clip EA to Barangay Boundary** | Boolean | When enabled (default: `True`), clips any portion of an EA extending outside its parent Barangay boundary. |
| **Detect Uncovered Barangay Areas** | Boolean | When enabled (default: `True`), identifies uncovered gaps within each Barangay after clipping. |
| **Assign Gaps to Contiguous EA** | Boolean | When enabled (default: `True`), assigns each detected gap to the adjacent EA sharing the longest boundary edge. |

### EA Preprocessing Output & Attribute Fields

| Output / Field Name | Type | Description |
|---------------------|------|-------------|
| **Pre-Processed EA Layer** | Vector (Polygon) | In-memory polygon layer (`<5-digit geocode>_ea2026_preprocessed`) containing aligned and gap-filled EAs. |
| **hhcount** | Double | Household count for the EA polygon. |
| **bldgcount** | Integer | Building count for the EA polygon. |
| **original_area** | Double | Original surface area of the starting EA polygon in square metres. |
| **corrected_area** | Double | Corrected surface area of the EA polygon after boundary clipping and gap assignment in square metres. |
| **area_change** | Double | Net area change (square metres) computed as `corrected_area - original_area`. |
| **pre_action** | String | Pre-processing action applied (`No Change`, `Clipped`, `Gap Assigned`, `Geometry Fixed`, or `Unresolved`). |
| **pre_status** | String | Validation status (`Valid`, `Corrected`, `Unresolved`, or `Error`). |

---

## Tab 2 — EA Delineation & Merging

The **EA Delineation & Merging** tab executes spatial aggregation, single-pass splitting for overpopulated EAs, and iterative merging for underpopulated EAs.

### Parameters & Options

| Parameter | Type | Description |
|-----------|------|-------------|
| **Barangay Layer** | Vector (Polygon) | Administrative barangay boundaries (`geocode` field required). Required. |
| **Building Point Layer** | Vector (Point) | Structure/building point data with an `hhcount` field representing households per building. Required. |
| **Previous EA Layer** | Vector (Polygon) | Starting EA boundaries from previous census round (or pre-processed output from Tab 1). Required. |
| **Road Layer** | Vector (Line) | Road network lines used to snap EA split boundaries to road centrelines. Optional. |
| **River Layer** | Vector (Line) | River and waterway centrelines used for split line snapping. Optional. |
| **Minimum Household Count per EA** | Integer | Minimum target household threshold per EA (default: `100`). EAs below this limit are merged. |
| **Maximum Household Count per EA** | Integer | Maximum target household threshold per EA (default: `300`). EAs above this limit are split. |
| **Splitting Rule (>300 Houses)** | Enumeration | Controls splitting rule: `Follow Roads & Rivers (Recommended)`, `Strict Minimum 100 Houses`, or `Do Not Split`. |
| **Boundary Cut Method** | Enumeration | Selects line tool for splitting: `Auto (Roads First, then Houses)`, `Roads & Rivers Only`, `House Groups Only`, `Straight Line Only`, or `Do Not Split`. |
| **Optimize for Compactness** | Boolean | Prefers spatially compact EA shapes over purely household-balanced splits (default: `True`). |
| **Allow Merging Candidate EAs** | Boolean | Allows candidate EAs (<=100 HH) to merge with each other when no reference EAs exist (default: `True`). |
| **Sliver Polygon Area Threshold** | Enumeration | Threshold for identifying and dissolving remnant sliver polygons into neighboring EAs. |
| **Snapping Tolerance (metres)** | Double | Maximum search distance for snapping proposed split lines to road or river centrelines (default: `15.0 m`). |
| **Target CRS** | CRS | Output Coordinate Reference System (default: `EPSG:4326`). |

### Outputs & QML Symbology Styles

| Output Layer | Type | Style File (.qml) | Description |
|--------------|------|-------------------|-------------|
| **Output EA Layer** | Vector (Polygon) | `ea_output.qml` | Consolidated output layer containing all final updated EA polygons (`<geocode>_ea2026`). Styled with vibrant blue borders and automated labels. |
| **Delineated EAs Layer** | Vector (Polygon) | `ea_output.qml` | Optional output containing sub-polygons generated from delineation (`<geocode>_delineated_ea2026`). |
| **Merged EAs Layer** | Vector (Polygon) | `ea_output.qml` | Optional output containing EAs generated from merging underpopulated EAs (`<geocode>_merged_ea2026`). |
| **Boundary Update Lines Layer** | Vector (Line) | `eadel_update_lines.qml` | Line layer (`<geocode>_eadel_update`) representing new boundary cuts generated from road/river splits. |
| **Candidate for Delineation Layer** | Vector (Polygon) | `delineation_candidates.qml` | Layer containing EAs identified as candidates for delineation (>300 HH). Styled with amber highlight. |
| **Candidate for Merging Layer** | Vector (Polygon) | `merge_candidates.qml` | Layer containing under-threshold initiator EAs (<=100 HH) and reference neighbor EAs evaluated for intra-barangay merging. |
### Final Output Attribute Schema (`delineated_ea2026`, `merge_ea2026`, `special_ea`)

The output layers `<geocode>_delineated_ea2026`, `<geocode>_merged_ea2026`, and `<geocode>_special_ea` share the following 18 standard attributes:

| Field Name | Type | Description |
|------------|------|-------------|
| **fid** | Integer | Feature Identifier (primary key). |
| **map_uuid** | String | Unique UUID assigned to the map sheet or starting EA polygon. |
| **geocode** | String | Full 9–14 digit PSGC administrative geocode for the EA polygon. |
| **region** | String | Region administrative code or name. |
| **province** | String | Province administrative code or name. |
| **city_mun** | String | City / Municipality administrative code or name. |
| **barangay** | String | Barangay administrative code or name. |
| **code** | String | PSGC administrative code / reference suffix. |
| **name** | String | Formatted Enumeration Area display label (e.g. `EA 001000`). |
| **ean** | String | Original starting Enumeration Area Number prior to processing. |
| **hhcount** | Double | Original household count from the starting EA input layer. |
| **bldgcount** | Integer | Original building count from the starting EA input layer. |
| **sy** | String / Integer | Survey Year / Census round identifier (e.g. `2026`). |
| **new_ean** | String | Newly assigned post-delineation 6-digit EA sequence number code (e.g. `001000`). |
| **hh_count** | Integer | New total household count aggregated from building points assigned to this polygon (whole number). |
| **bldg_count** | Integer | New total building point count contained in this polygon. |
| **ea_type** | String | EA classification type (`STANDARD` or `SPECIAL`). |
| **remarks** | String | Processing note detailing action or split strategy (e.g. `Split along road network`, `Merged EA`, `Generated from Gap layer`). |

---

## How It Works

1. **Pre-Processing Alignment (Tab 1)**:
   - Validates geometries and clips EAs extending outside parent Barangay boundaries.
   - Identifies uncovered gaps within parent Barangays and dissolves gap polygons into adjacent EAs sharing the longest boundary edge (`buffer(0.0, 3)` cleanups).

2. **Building Point Spatial Join & Aggregation (Tab 2)**:
   - Spatially joins building points to starting EAs and sums building counts (`bldgcount`) and household load (`hhcount`).

3. **Single-Pass EA Delineation (Splitting)**:
   - Overpopulated EAs (>300 HH) are split using weighted K-Means clustering on building points in a single pass.
   - Generated cut lines are buffered and snapped to nearest road or river centrelines within snapping tolerance.

4. **Iterative Spatial Merging**:
   - Underpopulated EAs (<=100 HH) undergo up to 5 iterative passes of spatial adjacency merging strictly within the same parent Barangay.

5. **Sliver Dissolve & Final Output**:
   - Remnant sliver polygons smaller than the area threshold are dissolved into adjacent neighbors.
   - Consolidated output layers (`<geocode>_ea2026`) are created with full attribute schemas and automated QML styling.

## Supported Geometry Types

- **Polygon** and **MultiPolygon**
- **Point** (Building points)
- **LineString** (Roads and rivers)

::: tip Complete Module Workflow
In the **EA Delineation and Merging** launcher dialog:
1. Run **Tab 1: EA Preprocessing** first to create the `<pppmm>_ea2026_preprocessed` layer.
2. Switch to **Tab 2: EA Delineation & Merging** and select `<pppmm>_ea2026_preprocessed` as the **Previous EA Layer**.
3. Execute the algorithm to produce 100% gap-free, household-balanced Enumeration Areas.
:::
