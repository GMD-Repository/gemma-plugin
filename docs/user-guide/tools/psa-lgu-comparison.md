# <img src="/icons/compare_boundaries.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> PSA - LGU Boundary Comparison

The **PSA - LGU Boundary Comparison** tool provides an automated auditing and spatial discrepancy evaluation workflow that cross-examines official Philippine Statistics Authority (PSA) reference boundaries against LGU-submitted boundary polygons and geotagged building point datasets. It pairs 8-digit PSGC geocode polygon matching with spatial containment indexing to identify boundary discrepancies and detect mis-allocated building points.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → PSA - LGU Boundary Comparison
- **Algorithm ID:** `gmd_pipeline:psalgu_boundary_comparison`
- **Review Panel Menu:** Gemma → Updating of Boundaries → PSA - LGU Comparison Review

The comparison algorithm executes as a standard processing tool and generates styled output layers. Once processing completes in QGIS Desktop, the **PSA - LGU Comparison Review** dock panel opens automatically to facilitate synchronized side-by-side inspection.

## When to Use

Use this tool when:
- Auditing local government boundary submissions against official PSA reference boundaries for municipal harmonization.
- Validating whether geotagged building points physically reside inside the barangay declared in their administrative geocode attributes.
- Telling apart building points that fall outside the LGU-submitted boundary from those that fall outside the official PSA boundary.
- Inspecting matched barangay pairs sequentially with automated zoom framing and dynamic building point filtering.
- Isolating unmatched barangays (declared by either the LGU or PSA but missing in the counterpart dataset) for field review.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **PSA Boundary Layer** | Vector Layer (Polygon) | Official PSA administrative boundary polygon layer. Auto-selects loaded layers containing `_psa` or `psa` in their name. |
| **Geocode Field (PSA)** | Table Field | Geocode attribute field on the PSA layer. If omitted, auto-detects a field literally named `Geocode`. |
| **LGU-Submitted Boundary Layer** | Vector Layer (Polygon) | LGU boundary polygon layer to audit. Auto-selects loaded layers containing `_lgu` or `lgu` in their name. |
| **Geocode Field (LGU)** | Table Field | Geocode attribute field on the LGU layer. If omitted, auto-detects a field literally named `Geocode`. |
| **Building Point Layer** | Vector Layer (Point) | Geotagged building point layer to evaluate against barangay boundaries. Auto-selects layers matching `bldgpts`, `bldg_point`, etc. |
| **Geocode Field (Building Point)** | Table Field | Geocode attribute field on the building point layer specifying its administrative barangay assignment. |

### Outputs

| Output | Geometry Type | Symbology & Role |
|--------|---------------|------------------|
| **`<code>_PSA_Matched`** | Polygon | Blue outline (`#1E88E5`), labeled with the PSA barangay name. Contains PSA polygons matched to LGU counterparts. |
| **`<code>_LGU_Matched`** | Polygon | Yellow outline (`#FBC02D`), labeled with the LGU barangay name. Contains LGU polygons matched to PSA counterparts. |
| **`<code>_PSA_Unmatched`** | Polygon | Gray outline. Contains PSA barangays with no corresponding LGU geocode match. |
| **`<code>_LGU_Unmatched`** | Polygon | Gray outline. Contains LGU barangays with no corresponding PSA geocode match. |
| **`building points inside lgu boundary`** | Point | Green circles (`#43A047`). Building points that physically fall inside the LGU polygon matching their declared barangay geocode. |
| **`building points outside lgu boundary`** | Point | Red circles (`#E31A1C`). Building points positioned outside the LGU polygon of their declared barangay. |
| **`building points outside psa boundary`** | Point | Purple squares (`#9C27B0`), drawn slightly larger so a point outside both boundaries still shows both markers. Building points positioned outside the PSA polygon of their declared barangay. |

*(Note: `<code>` represents the municipal prefix extracted from the input layer names, e.g. `000102`).*

All three building point layers are always created, even when empty. An empty Outside layer means no building point fell outside that boundary, not that the check was skipped.

### Reading the Outside Layers

Both Outside layers share the same attribute columns, each evaluated against its own boundary source:

| Column | Description |
|--------|-------------|
| **`geocode_first8`** | The first 8 characters of the building point's own geocode (the barangay it claims to belong to). |
| **`in_geocode`** | The barangay the point actually sits inside, taken from the same boundary source as the layer (LGU for the LGU layer, PSA for the PSA layer). Empty when the point falls outside every barangay of that boundary. |
| **`match_id`** | Matched-pair ID of the barangay named by the point's own geocode. |
| **`in_match_id`** | Matched-pair ID of the barangay the point physically sits inside. |

Comparing the two layers shows where the discrepancy lies:

| Point appears in | Interpretation |
|------------------|----------------|
| Outside LGU only | The point is inside the official PSA barangay but outside the LGU-submitted polygon, which suggests the LGU boundary needs review. |
| Outside PSA only | The point is inside the LGU-submitted polygon but outside the official PSA barangay, which suggests the LGU boundary extends beyond the PSA reference. |
| Both layers | The point is outside the declared barangay in both sources, which usually indicates a mis-coded geocode (check `in_geocode`) or a point captured outside the municipality. |

On the map, a point in both layers shows a red circle drawn on top of a larger purple square.

## How It Works

1. **Geocode Prefix Matching**:
   - Compares the first 8 characters (`first8`) of the geocode field (Region + Province + City/Mun + Barangay) between PSA and LGU polygon layers.
   - Bypasses name orthography and trailing digit differences, preventing mismatches caused by minor spelling discrepancies.
   - Preserves multipart geometries, ensuring that multi-island barangays remain unified under a single matching key.

2. **Spatial Indexing & Containment Engine**:
   - Constructs a spatial bounding box index (`QgsSpatialIndex`) over the LGU boundary polygons, and a second one over the PSA boundary polygons.
   - Evaluates each building point against the specific LGU polygon, and separately the specific PSA polygon, matching its own 8-character geocode.
   - Points falling inside or intersecting the shared polygon boundary are categorized as **Inside**; points falling outside go to that boundary's own **Outside** layer (LGU or PSA). A point outside both appears in both.
   - Building points are reprojected to each boundary layer's CRS before testing when the CRSs differ; output geometries stay in the building layer's original CRS.
   - Points whose geocode names a barangay from a different city or municipality entirely, and that do not physically fall inside the boundary being checked, are excluded from that Outside layer as unrelated to the comparison.

3. **Field Collision Prevention**:
   - If an input layer already contains an attribute named `geocode`, QGIS appends duplicate columns as `geocode_2`.
   - To guarantee that the review panel reads the true barangay geocode, the algorithm stamps the custom layer property `psalgu_geocode_field` with the exact generated column name.
   - Assigns `match_id` to matched polygons and both `match_id` and `in_match_id` to outside building points, allowing points to be scoped per barangay during review.

4. **Automated Post-Processing**:
   - Organizes all generated output layers into a dedicated Layer Tree group named `<code> PSA - LGU Comparison`.
   - Automatically unchecks the visibility of the raw input layers to keep the canvas focused on comparison results.
   - Adds a Google Satellite XYZ basemap below the layers if the HCMGIS plugin is installed.
   - Activates the comparison review dock panel on the QGIS main thread via post-processing interfaces.

## Comparison Review Panel

The **PSA - LGU Comparison Review** dock panel (`GemmaPsaLguComparisonPanel`) docks beneath the QGIS Layers panel:

1. **Barangay Navigation**:
   - Select any matched barangay from the dropdown list or navigate sequentially using the **Previous** and **Next** buttons.
   - The dropdown displays the clean barangay name and 8-digit geocode.

2. **Synchronized Canvas Zoom**:
   - The map canvas automatically centers and zooms to the combined bounding box of both the PSA and LGU polygons for the selected barangay.
   - A 15% framing margin (`ZOOM_PADDING_RATIO = 0.15`) is applied so boundaries are not flush against canvas edges.

3. **Dynamic Point Scoping**:
   - When stepping through barangays, subset filter strings are dynamically updated on all building point layers:
     - Inside points are filtered by `match_id`.
     - Outside points are filtered by either `match_id` (declared barangay) or `in_match_id` (the physical barangay the point sits inside).
   - This ensures the reviewer only sees building points relevant to the currently inspected barangay.

## Supported Geometry Types

- **Polygon** and **MultiPolygon** (PSA and LGU boundary layers)
- **Point** and **MultiPoint** (Building point layer)

::: tip Geocode Text Formatting
Ensure that geocode attribute fields in shapefiles and GeoPackages are formatted as **String/Text** rather than Numeric/Integer. Numeric formats drop leading zeros (e.g. converting `01030200` to `1030200`), causing 8-digit prefix matching to fail.
:::

::: info Headless Execution
The processing algorithm (`gmd_pipeline:psalgu_boundary_comparison`) can run headless in batch scripts or via `qgis_process`. The graphical review dock panel is loaded lazily and activates only when QGIS is running with a graphical user interface (`iface`).
:::
