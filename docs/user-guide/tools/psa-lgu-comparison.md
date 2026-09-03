# <img src="/icons/compare_boundaries.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> PSA - LGU Boundary Comparison

The **PSA - LGU Boundary Comparison** tool provides an automated auditing workflow that compares official PSA reference boundaries against LGU-submitted boundary polygons and geotagged building point layers. It combines geocode-based polygon matching, whole-map Procrustes alignment transformations, and spatial containment checks to audit boundary discrepancies and identify mis-allocated building points.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → PSA - LGU Boundary Comparison
- **Algorithm ID:** `gmd_pipeline:psalgu_boundary_comparison`
- **Review Panel Menu:** Gemma → Updating of Boundaries → PSA - LGU Comparison Review

## When to Use

Use this tool when:

- Auditing administrative boundaries submitted by Local Government Units (LGUs) against official PSA reference boundaries.
- Distinguishing between genuine boundary disagreements and digitization artifacts caused by poorly georeferenced raster basemaps.
- Validating whether geotagged building points physically fall inside the barangay declared in their geocode attributes.
- Inspecting matched barangays side-by-side using an interactive review dock panel in QGIS.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **PSA Boundary Layer** | Vector Layer (Polygon) | Official PSA administrative boundary polygon layer (auto-detects layers with `_psa` or `psa` in name) |
| **Geocode Field (PSA)** | Table Field | Geocode attribute field on the PSA layer. If left unselected, auto-detects a field literally named `Geocode` |
| **LGU-Submitted Boundary Layer** | Vector Layer (Polygon) | LGU boundary polygon layer to audit (auto-detects layers with `_lgu` or `lgu` in name) |
| **Geocode Field (LGU)** | Table Field | Geocode attribute field on the LGU layer. If left unselected, auto-detects a field literally named `Geocode` |
| **Building Point Layer** | Vector Layer (Point) | Geotagged building point layer to evaluate against barangay boundaries (auto-detects layers containing `bldgpts`, `bldg`, etc.) |
| **Geocode Field (Building Point)** | Table Field | Geocode attribute field on the building point layer |

### Alignment Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| **Align LGU boundary onto PSA boundary** | Boolean | `True` | Applies a global best-fit mathematical transformation to reposition the entire LGU boundary onto the PSA boundary before evaluating building points |
| **Alignment transform** | Enum | `Similarity` | Mathematical transformation model used for the global alignment: `Similarity`, `Rigid`, or `Affine` |

## Transformation Models

LGU boundaries are frequently digitized from older satellite imagery or scanned maps with slight ground-resolution or rotational drift. Rather than altering individual barangays independently (which would introduce artificial gaps or overlaps along shared edges), the tool applies a single **global 2D transformation** across all matched polygons:

1. **Similarity (Recommended / Default)**:
   - 4 parameters: Shift ($t_x, t_y$), rotation angle ($\theta$), and uniform scale factor ($s$).
   - Preserves angles and polygon proportions exactly while absorbing scale variations caused by ground resolution differences:
     $$\begin{pmatrix} x' \\ y' \end{pmatrix} = s \begin{pmatrix} \cos\theta & -\sin\theta \\ \sin\theta & \cos\theta \end{pmatrix} \begin{pmatrix} x \\ y \end{pmatrix} + \begin{pmatrix} t_x \\ t_y \end{pmatrix}$$
2. **Rigid**:
   - 3 parameters: Shift ($t_x, t_y$) and rotation angle ($\theta$) only.
   - Preserves exact ground distances without resizing. Useful when LGU boundaries must not be scaled.
3. **Affine**:
   - 6 parameters: Shift, rotation, independent X/Y scaling, and shear.
   - Absorbs maximum distortion when base imagery exhibits non-uniform stretching across axes.

Whatever discrepancy remains after alignment represents genuine cartographic disagreement between PSA and LGU boundaries, rather than a georeferencing artifact.

## How It Works

1. **Geocode Prefix Matching**:
   - Compares the first 8 characters (`first8`) of the geocode field (Region + Province + City/Mun + Barangay) between PSA and LGU polygon layers.
   - Ignores name spellings and trailing digits, preventing mismatches caused by orthographic variations.
   - Preserves multipart polygons (such as barangays with islands).

2. **Global Alignment & Iterative Closest Point (ICP)**:
   - Computes centroid-based Procrustes transformation across all matched barangay pairs.
   - Refines alignment through boundary-contour Iterative Closest Point (ICP) optimization.
   - Reports residual discrepancy in meters across the municipality and flags the maximum error.

3. **Building Point Containment Audit**:
   - Evaluates each point against the specific polygon matching its own 8-character geocode.
   - When alignment is active, containment is satisfied if the point falls inside the aligned LGU polygon **or** the corresponding PSA polygon.
   - Assigns `match_id` and `in_match_id` to allow building points to be scoped per barangay during review.

4. **Automated Grouping & Basemap**:
   - Bundles all generated output layers into a dedicated `<code> PSA - LGU Comparison` Layer Tree group.
   - Unchecks the original input layers to focus the map canvas on comparison results.
   - Automatically loads a `Google Satellite` XYZ basemap at the bottom of the layer stack if the HCMGIS plugin is available.

## Output Layers

| Output Layer | Geometry | Symbology & Role |
|--------------|----------|------------------|
| `<code>_PSA_Matched` | Polygon | Blue outline (`#1E88E5`), labeled with PSA barangay name |
| `<code>_LGU_Matched` | Polygon | Yellow outline (`#FBC02D`), labeled with LGU barangay name |
| `<code>_LGU_Aligned_Barangay` | Polygon | White dashed outline (`#FFFFFF`) showing aligned LGU geometry |
| `<code>_LGU_Aligned_Barangay_Contested` | Polygon | Red dashed outline (`#E53935`) for unconfirmed or contested boundary polygons |
| `<code>_PSA_Unmatched` | Polygon | Gray outline for PSA barangays with no matching LGU geocode |
| `<code>_LGU_Unmatched` | Polygon | Gray outline for LGU barangays with no matching PSA geocode |
| `Building Points inside LGU Boundary` | Point | Green circles (`#43A047`) for points correctly located inside their assigned barangay |
| `Building Points outside LGU Boundary` | Point | Red circles (`#E53935`) for points positioned outside their assigned barangay |

*(Note: `<code>` represents the municipal prefix extracted from the input layer names, e.g., `000102`).*

## Comparison Review Panel

When the algorithm finishes execution, the **PSA - LGU Comparison Review** dock panel opens automatically (or can be reopened via **Gemma → Updating of Boundaries → PSA - LGU Comparison Review**):

1. **Barangay Navigation**: Select any matched barangay from the dropdown or use the **Previous** and **Next** buttons to inspect boundaries sequentially.
2. **Synchronized Canvas Zoom**: The map canvas automatically centers and zooms to the combined extent of both PSA and LGU boundary polygons with a 15% margin padding.
3. **Dynamic Point Scoping**: Building points inside and outside the boundary are automatically filtered to show only features associated with the currently active barangay.

## Supported Geometry Types

- **Polygon** and **MultiPolygon** (PSA and LGU boundary layers)
- **Point** and **MultiPoint** (Building point layer)

::: tip Geocode Text Format
Ensure geocode attribute fields are formatted as **String/Text** rather than Integer. Numeric fields may drop leading zeros (e.g., converting `01030200` to `1030200`), which causes 8-digit prefix matching to fail.
:::

::: info Headless Execution
The processing algorithm (`gmd_pipeline:psalgu_boundary_comparison`) can run headless in batch scripts or `qgis_process`. The graphical review panel module is loaded lazily and activates only when QGIS is running with a graphical user interface (`iface`).
:::
