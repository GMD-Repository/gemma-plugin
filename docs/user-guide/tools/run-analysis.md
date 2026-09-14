# <img src="/icons/run_analysis.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Run Analysis

The **Run Analysis** tool performs comprehensive boundary topology and discrepancy detection across LGU and PSA polygon layers and building points. It first resolves a single authoritative boundary per city/municipality — deduplicating repeated submissions, giving precedence to the LGU's latest submission over the PSA reference, and labeling every remaining non-LGU polygon's source as `PSA` — then consolidates all Gaps/Overlaps/Disputed findings against that boundary into a unified Reference MBI layer named `ref_mbi_cases`.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Run Analysis
- **Algorithm ID:** `gmd_pipeline:run_analysis`

## When to Use

Use this tool when:
- Establishing the baseline Reference MBI cases layer (`ref_mbi_cases`) for a municipality or province.
- Generating the required reference input layer consumed by the [MBI Validator](/tools/mbi-validator) tool.
- Resolving LGU vs PSA boundary precedence: the LGU layer is treated as the latest submission, so any city/municipality with at least one LGU polygon uses LGU boundaries exclusively; a city/municipality with no LGU submission falls back to PSA.
- Cleaning up duplicate boundary submissions (the same barangay digitized twice, or the same area present in more than one selected input layer) before they can produce false gap/overlap findings.
- Detecting sliver gaps between adjacent barangay polygons while automatically excluding already-recorded disputed territories.
- Identifying boundary overlaps across different administrative levels (Inter-Region, Inter-Province, Inter-City/Municipality, Inter-Barangay, or Within-Barangay).
- Extracting contested boundary claims tagged as disputed in LGU datasets.
- Setting up pre-configured attribute table dropdown widgets (`ValueMap` for `mbi_status`) for provincial field validation.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **Select Polygon Layer(s)** | Multiple Layers (Polygon) | One or more vector polygon layers representing barangay boundaries from LGU and PSA datasets. Required. |
| **Select Building Point Layer(s)** | Multiple Layers (Point) | One or more point layers representing structures/buildings used to count intersecting points within each finding. Required. |

::: info Fixed Analysis Execution
All three boundary analyses (**Gaps**, **Overlaps**, and **Disputed Areas**) execute automatically as mandatory procedures. No manual analysis mode parameter is required.
:::

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **2026_province_boundary** | Vector Layer (Polygon, In-Memory) | The resolved authoritative boundary set in EPSG:4326: exact duplicate polygons removed, LGU polygons kept wherever an LGU submission exists for a city_mun (its PSA counterpart excluded), and every remaining non-LGU polygon explicitly labeled `source = PSA`. This is the sole input to Gaps/Overlaps/Disputed detection below, loaded for reviewers to inspect which polygons were kept, superseded, or relabeled. |
| **ref_mbi_cases** | Feature Sink (Polygon) | A consolidated polygon layer in EPSG:4326 containing all detected boundary findings categorized by `mbi_type`. Formatted with pre-configured attribute table editor widgets. |

## Output Layer Schema

The resulting `ref_mbi_cases` layer contains the following standardized attributes:

| Field Name | Type | Access | Description |
|------------|------|--------|-------------|
| **case_uuid** | String | Read-Only | Unique UUID string assigned to each individual finding. |
| **geocode** | String | Editable | 9-digit PSGC geocode associated with the primary reference polygon. |
| **region** | String | Read-Only | Region name or code. |
| **province** | String | Read-Only | Province name. |
| **city_mun** | String | Editable | City or municipality name. |
| **barangay** | String | Editable | Barangay name. |
| **source** | String | Read-Only | Data source provenance label (e.g. LGU or PSA; NULL for gaps). |
| **mbi_level** | String | Read-Only | Administrative boundary hierarchy level: *Inter-Region*, *Inter-Province*, *Inter-City/Municipality*, *Inter-Barangay*, or *Within-Barangay*. |
| **involved_areas** | String | Read-Only | Comma-separated list of all involved PSGC geocodes. |
| **involved_bgys** | String | Read-Only | Semicolon-separated list of all involved barangay and city/municipality names. |
| **count_involved_areas** | Integer | Read-Only | Total count of distinct administrative units participating in the finding. |
| **mbi_type** | String | Read-Only | Classification category: `1_Gap`, `2_Overlap`, or `3_Disputed`. |
| **num_bldg_pts** | Integer | Read-Only | Count of intersecting building points falling within the finding polygon. |
| **mbi_status** | String | Editable | Status field equipped with a QGIS ValueMap dropdown widget: `1_Updated` or `2_Pending`. |
| **mbi_remarks** | String | Read-Only | System remarks populated automatically when an overlap touches a disputed polygon (`For Review - Involves Disputed Area`). |
| **pso_remarks** | String | Editable | Text field reserved for notes entered by Provincial Statistical Offices. |
| **lgu_bgy_name** | String | Editable | LGU-declared barangay name populated specifically for Disputed records (NULL for gaps/overlaps). |

## How It Works

1. **Layer Pre-Processing and Coordinate Normalization**:
   - Multiple input polygon and building point layers are refactored, merged, and projected to Web Mercator (`EPSG:3857`) for accurate metric area calculations and geometric topological operations.
   - Geometries are validated and repaired using geometry fixing algorithms, and multipart geometries are exploded into single parts.

2. **Duplicate Removal**:
   - Polygons are keyed by `geocode` + `source` — the PSGC geocode is the unique identifier per barangay within a given source (LGU or PSA). A repeated `geocode` + `source` pair is dropped only when its geometry is identical to one already kept, so the same barangay submitted twice (duplicate rows in a file, or the same area present in more than one selected input layer) collapses to a single feature.
   - The identical-geometry requirement protects barangays with islands or other disjoint pieces: `multiparttosingleparts` explodes them into several features that all share one geocode but have different geometry, so each genuine piece is retained rather than discarded as a duplicate of the mainland piece.

3. **Boundary Precedence Resolution**:
   - The LGU layer is treated as the latest submission. For every `city_mun` where at least one polygon's `source` contains `LGU`, that city_mun's PSA polygon(s) are excluded and only the LGU polygon(s) are kept.
   - A `city_mun` with no LGU submission at all falls back to using its PSA polygon(s) unchanged.
   - Every non-LGU polygon that survives this step then has its `source` attribute explicitly set to `PSA` (overwriting a blank/`NULL`/other value), so downstream findings never carry an ambiguous source label.
   - The resulting authoritative set is reprojected to `EPSG:4326` and loaded into the project as **2026_province_boundary**, and is also the sole input to spatial indexing and detection below.

4. **Spatial Indexing & Attribute Extraction**:
   - Spatial bounding box indexes (`QgsSpatialIndex`) and cached feature lookups are constructed for both the resolved polygon boundaries and building points.
   - Core administrative attributes (`geocode`, `region`, `province`, `city_mun`, `barangay`, `boundary`, `source`) are normalized into structured lookup records.

5. **Disputed Territory Identification**:
   - Polygons tagged with `boundary = Contested` or disputed markers are isolated.
   - Each contested area is converted to `3_Disputed` in the output schema and its footprint is unioned in memory.

6. **Overlap Detection Engine**:
   - Pairs of intersecting polygons are detected using the spatial index.
   - The geometric intersection is computed, filtered to retain polygons with areas greater than 0.10 square meters, and tagged with administrative level hierarchy (`mbi_level`).
   - If either overlapping polygon is marked as disputed, `mbi_remarks` is automatically populated with `For Review - Involves Disputed Area`.
   - Intersecting building points within the overlap polygon are tallied into `num_bldg_pts`.

7. **Gap Detection Engine**:
   - Non-disputed boundary polygons are dissolved into a unified regional coverage.
   - Holes within the dissolved polygon coverage are filled, and a symmetric difference is computed between the filled coverage and the original dissolved coverage to extract internal void slivers.
   - The unioned footprint of all Disputed territories is subtracted from the candidate gap geometries, ensuring that contested territories are never duplicated as gaps.
   - Qualifying gap slivers are linked to adjacent participating barangays and assigned `mbi_type` = `1_Gap`.

8. **Output Layer Generation, Styling & Editor Widget Application**:
   - All findings are transformed to WGS 84 (`EPSG:4326`) and added to the consolidated `ref_mbi_cases` layer.
   - The layer post-processor (`FieldWidgetPostProcessor`) automatically loads and applies the embedded categorized QML style (`ref_mbi_cases.qml`), displaying distinct symbology and labeling for `1_Gap`, `2_Overlap`, and `3_Disputed` cases.
   - Attaches `ValueMap` editor widgets to `mbi_status` (`1_Updated`, `2_Pending`) and text input setups to remarks fields directly upon loading into QGIS.
   - Sets computed reference attributes to **Read-Only** (`case_uuid`, `region`, `province`, `source`, `mbi_level`, `involved_areas`, `involved_bgys`, `count_involved_areas`, `mbi_type`, `num_bldg_pts`, and `mbi_remarks`) to prevent accidental edits while keeping reviewer fields (`geocode`, `city_mun`, `barangay`, `mbi_status`, `pso_remarks`, and `lgu_bgy_name`) fully **Editable**.

## Supported Geometry Types

- **Polygon** and **MultiPolygon** (Vector boundary layers)
- **Point** and **MultiPoint** (Building point layers)

::: tip Reference Layer Downstream Compatibility
The output layer `ref_mbi_cases` is engineered to feed directly into the **MBI Validator** tool. When opening MBI Validator, it will automatically detect and pre-select `ref_mbi_cases` as the Reference layer input.
:::

::: tip Reviewing Boundary Precedence Decisions
Inspect `2026_province_boundary`'s attribute table to confirm which polygons were kept, superseded, or relabeled: a `city_mun` with mixed LGU/PSA submissions will show only LGU polygons for that city_mun, and any polygon whose `source` was blank or non-LGU will read `PSA`. This is the exact boundary set that Gaps/Overlaps/Disputed detection ran against.
:::
