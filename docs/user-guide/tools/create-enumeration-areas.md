# <img src="/icons/create_ea.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Create Enumeration Areas

The **Create Enumeration Areas** tool automates the spatial aggregation and delineation (splitting) of census Enumeration Areas (EAs) based on building household load, spatial contiguity, administrative barangay boundaries, and optional linear feature alignment (roads and rivers).

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Create Enumeration Areas
- **Algorithm ID:** `gmd_pipeline:createea`
- **Menu:** Gemma → EA Delineation → Create Enumeration Areas
- **Toolbar:** Gemma Toolbar → Create Enumeration Areas icon

## When to Use

Use this tool when:

- Preparing enumeration area boundaries for national census and demographic field operations.
- Re-balancing EA boundaries to ensure every field enumerator workload falls within a target household range (default 100 to 300 households).
- Delineating overpopulated EAs (>300 households) using building point spatial clustering and road/river network centrelines.
- Merging underpopulated EAs (<100 households) with adjacent contiguous neighbors within the same barangay boundary.

## User Interface Features

The dedicated **EA Launcher** dialog provides an interactive workflow prior to executing the algorithm:

- **Auto-Detect Layers:** Automatically scans open layers in the QGIS project and selects matching inputs based on standard layer naming conventions (`_bgy`, `_ea`, `_bldgpts`, `road`, `river`).
- **Fill Missing Household Counts:** Includes a built-in pre-processing utility to compute missing household counts (`hhcount`) directly from building points within each EA polygon before running the algorithm.
- **KPI Cards & Live Candidate Preview:** Renders dynamic statistics and color-coded candidate tables for Delineation (>300 HH) and Merging (<100 HH) candidates before execution.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **Barangay Layer** | Vector (Polygon) | Administrative barangay boundaries. Must contain a `geocode` field representing administrative boundary codes. Required. |
| **Building Point Layer** | Vector (Point) | Structure/building point data with an `hhcount` field representing households per building. Required. |
| **Previous EA Layer** | Vector (Polygon) | Starting EA boundaries from the previous census round. Must contain `geocode` or `ean` fields. Attributes are inherited by outputs. Required. |
| **Road Layer** | Vector (Line) | Road network lines used to snap split boundaries to road centrelines. Optional. |
| **River Layer** | Vector (Line) | River and waterway centrelines used for split line snapping. Optional. |
| **Gap Layer** | Vector (Polygon) | Polygon layer representing unmapped boundary gaps, extracted into Special EAs. Optional. |
| **Overlap Layer** | Vector (Polygon) | Polygon layer representing boundary overlaps, extracted into Special EAs. Optional. |
| **Minimum Household Count per EA** | Integer | Minimum target household threshold per EA (default: 100). EAs below this limit are merged. |
| **Maximum Household Count per EA** | Integer | Maximum target household threshold per EA (default: 300). EAs above this limit are split. |
| **Optimize for Compactness** | Boolean | Prefers spatially compact EA shapes over purely household-balanced splits (default: True). |
| **Allow Merging Between Under-Threshold Candidate EAs** | Boolean | Controls whether under-threshold candidate EAs (<=100 HH) can merge with each other when no reference EAs exist (default: True). |
| **Sliver Polygon Area Threshold** | Enumeration | Controls area threshold for identifying and dissolving remnant sliver polygons into neighboring EAs. |
| **Snapping Tolerance (metres)** | Double | Maximum search distance for snapping proposed split lines to road or river centrelines (default: 15.0 m). |
| **Target CRS** | CRS | Output Coordinate Reference System (default: EPSG:4326). |
| **Preview Candidates Only** | Boolean | When enabled, generates candidate preview layers and exits without altering EA geometries. |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Output EA Layer** | Vector (Polygon) | Consolidated output layer containing all final updated EA polygons (`<geocode>_ea2026`). |
| **Delineated EAs Layer** | Vector (Polygon) | Optional output containing all sub-polygons generated from delineation (`<geocode>_delineated_ea2026`). |
| **Merged EAs Layer** | Vector (Polygon) | Optional output containing only EAs generated from merging underpopulated EAs (`<geocode>_merged_ea2026`). |
| **Special EAs Layer** | Vector (Polygon) | Optional output containing Special EAs generated from Gap and Overlap layers (`<geocode>_special_ea`). |
| **Candidate for Delineation Layer** | Vector (Polygon) | Layer containing EAs identified as candidates for delineation (>300 HH). |
| **Candidate for Merging Layer** | Vector (Polygon) | Layer containing under-threshold initiator EAs (<=100 HH) together with their adjacent reference neighbor EAs evaluated for intra-barangay merging (`<geocode>_merge_candidates`). |
| **Extracted Building Points Layer** | Vector (Point) | Point layer containing building points tagged with assigned EA identifiers. |

::: note Understanding Zero Feature Counts in Output Layers
Depending on your input dataset's household load distribution, specific output layers may legitimately contain **0 features**:

- **Delineated EAs = 0**: Delineation (splitting) only occurs when starting EAs exceed the **Maximum Household Count per EA** threshold (default: >300 HH) or intersect Gap/Overlap layers. If no EAs exceed 300 HH, 0 Delineated EAs are generated.
- **Merged EAs = 0**: Merging only occurs when under-threshold EAs (<=100 HH) are present. If all EAs fall within the valid target range (100–300 HH), 0 Merged EAs are generated.
:::

## How It Works

1. **Initialization and Coordinate Transformation**:
   - Validates input parameter combinations and transforms all vector layers to the Target CRS (default EPSG:4326).

2. **Building Point Spatial Join and Household Aggregation**:
   - Performs a spatial join between building points and previous EA boundaries.
   - Calculates total building load (`bldg_count`) and sums households (`hhcount`) per EA.

3. **Spatial Indexing of Linear and Special Layers**:
   - Builds spatial R-tree indexes for road networks, river centrelines, and gap/overlap polygons for fast spatial queries.

4. **EA Classification**:
   - Categorizes starting EAs into Pass-through EAs (100 to 300 HH), Delineation Candidates (>300 HH or gap/overlap), and Merge Candidates (<100 HH).

5. **Single-Pass EA Delineation (Splitting)**:
   - Overpopulated EAs are split using weighted K-Means clustering on internal building points in a single deterministic pass.
   - Generated cut lines are buffered and snapped to the nearest road or river centrelines within the specified snapping tolerance.

6. **Iterative EA Merging**:
   - Underpopulated EAs undergo up to 5 iterative passes of spatial adjacency merging.
   - Merging is strictly restricted to contiguous EAs (`touches()` or `intersects()`) within the same parent barangay, ensuring combined households do not exceed the maximum threshold (300 HH).
   - When **Allow Merging Between Under-Threshold Candidate EAs** is enabled (default), candidate EAs can merge with neighboring candidate EAs in barangays lacking standard reference EAs.

7. **Compliance Sweep and Sliver Dissolve**:
   - Identifies remnant sliver polygons smaller than `SLIVER_THRESHOLD` and dissolves them into the largest adjacent neighbor.
   - Applies feature guards to eliminate any empty geometries or unpopulated key identifiers.

8. **Output Sink Writing and Attribute Inheritance**:
   - Writes final polygons to output sinks while preserving original attribute fields from the previous EA layer.
   - Appends metadata tracking fields including `hhcount`, `bldg_count`, `split_by` (`road`, `river`, `kmeans`), `new_ea`, and `correspondence_ea_geocode`.

## Candidate Merging Example

The following example demonstrates how under-threshold candidate EAs are processed within a small barangay (e.g. Barangay 01737) under both configuration settings:

### Input Dataset State (Barangay 01737)

| EA Code | Households (HH) | Classification | Initial Status |
|---|:---:|---|---|
| `EA 01737001` | 45 HH | Under-Threshold Candidate ($\le 100$ HH) | Initiator Candidate |
| `EA 01737002` | 35 HH | Under-Threshold Candidate ($\le 100$ HH) | Initiator Candidate |
| `EA 01737003` | 50 HH | Under-Threshold Candidate ($\le 100$ HH) | Initiator Candidate |
| `EA 01737004` | 40 HH | Under-Threshold Candidate ($\le 100$ HH) | Initiator Candidate |

### Setting Comparison

#### Case A: Allow Merging Between Candidate EAs = Disabled (`False`)
- **Search Rule:** Candidates can only merge into adjacent reference EAs (>100 HH).
- **Processing Outcome:** Because all 4 EAs in Barangay 01737 are candidates ($\le 100$ HH), no valid reference neighbors exist.
- **Output:** **0 Merged EAs** created (`01737_merged_ea2026` is empty). All 4 EAs remain unmerged and are logged in `01737_merge_candidates`.

#### Case B: Allow Merging Between Candidate EAs = Enabled (`True`, Default)
- **Search Rule:** Candidate EAs are permitted to merge with adjacent candidate EAs if no reference EAs exist.
- **Step-by-Step Consolidation:**
  1. **Pass 1:** `EA 01737001` (45 HH) merges with adjacent candidate `EA 01737002` (35 HH) $\rightarrow$ Subtotal: **80 HH**.
  2. **Pass 2:** Combined sub-polygon (80 HH) merges with adjacent candidate `EA 01737003` (50 HH) $\rightarrow$ Subtotal: **130 HH** (Reaches optimal 100–300 HH range!).
  3. **Pass 3:** Remaining under-threshold `EA 01737004` (40 HH) merges into the 130 HH polygon $\rightarrow$ Total: **170 HH**.
- **Output:** **1 Consolidated Merged EA** (170 HH) written to `<geocode>_merged_ea2026`, successfully resolving the under-threshold coverage gap.

## Supported Geometry Types

- **Polygon** and **MultiPolygon** (Barangay, EA, Gap, Overlap layers)
- **Point** and **MultiPoint** (Building Point layer)
- **LineString** and **MultiLineString** (Road and River layers)

::: tip
For best results, verify that building point layer household attributes (`hhcount`) are populated before running delineation. You can use the built-in **Fill missing hhcount** button in the EA Launcher dialog to automatically update missing values from building points within each EA.
:::

