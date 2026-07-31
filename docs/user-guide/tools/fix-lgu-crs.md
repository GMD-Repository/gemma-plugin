# <img src="/icons/crs.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Fix LGU CRS

The **Fix LGU CRS** tool batch-corrects or repositions vector layers digitized in local arbitrary grid coordinates (~0 to ~100,000) to true WGS84 coordinates (**EPSG:4326**). It fits a 2D Affine transformation matrix via Ordinary Least Squares (OLS) based on control points and transforms all geometry vertices to standard WGS 84.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Fix LGU CRS
- **Algorithm ID:** `gmd_pipeline:fixlgucrs`

## Layer Roles & Setup

| Role | Layer Parameter | Description |
|------|-----------------|-------------|
| **Input Local Grid Layer** | `Input Local Grid Layer (LGU Layer)` | Local arbitrary grid layer (LGU layer) digitized in ~0 to ~100,000 coordinates to be repositioned |
| **Reference Layer** | `Reference WGS84 Layer (_bgy / Control Points)` | Standard WGS84 reference layer (e.g. `02934_bgy` in EPSG:4326) providing target control point coordinates |

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input Local Grid Layer (LGU Layer)** | Feature Source (Any Geometry) | Local grid layer to be corrected |
| **Reference WGS84 Layer (_bgy / Control Points)** | Feature Source (Any Geometry) | Reference layer in EPSG:4326 used for target coordinates (e.g. `02934_bgy`) |
| **Local X Field** | Field (Numeric) | Optional manual selection for Local X field (overrides auto-detection) |
| **Local Y Field** | Field (Numeric) | Optional manual selection for Local Y field (overrides auto-detection) |
| **WGS84 Longitude Field** | Field (Numeric) | Optional manual selection for WGS84 Longitude field (overrides auto-detection) |
| **WGS84 Latitude Field** | Field (Numeric) | Optional manual selection for WGS84 Latitude field (overrides auto-detection) |
| **Input Match Field** | Field (Any) | Optional manual attribute field from the input layer used to match reference features |
| **Reference Match Field** | Field (Any) | Optional manual attribute field from the reference layer used to match input features |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Corrected Layer** | Feature Sink | The transformed geometry layer in EPSG:4326 |

## How It Works

1. **Smart Cross-Column Attribute & Feature Matching**:
   - Evaluates cross-column candidate pairs across layers, supporting common LGU and PSA/DENR reference headers (`geocode`, `bgy_geocode`, `psgc_bgy`, `psgc`, `bgy_code`, `brgy_code`, `code`, `barangay_n`, `barangay_name`, `bgy_name`, `brgy_name`, `name`, `barangay`, `bgy`, `bgy_id`, `adm4_en`, `id`, `fid`).
   - Normalizes digit-based PSGC geocodes automatically (e.g. matching 9-digit local codes like `02934001` with 14-digit PSGC geocodes like `02934001000000`).
   - Automatically selects the candidate attribute pair yielding the maximum number of unique matched control points (minimum 3).
   - Pre-computes relative spatial centroid proximity mapping as a fallback if attribute matching is partial or unavailable.

2. **Coordinate Extraction**:
   - Automatically auto-detects `XI`, `YI`, `LongitudeI`, `LatitudeI` fields if present in input feature attributes.
   - Falls back to feature geometry centroids for local $(X, Y)$ if local coordinate columns are absent.
   - Maps WGS84 target coordinates from matched features in the `_bgy` reference layer.

3. **2D Affine OLS Matrix Computation**:
   - Fits a 2D affine transformation matrix via Ordinary Least Squares:
     $$\text{Longitude} = a \cdot X + b \cdot Y + c$$
     $$\text{Latitude} = d \cdot X + e \cdot Y + f$$
   - Auto-corrects swapped axis orientation (X/Y diagonal inversion) if necessary.

4. **Residual Reporting & Transformation**:
   - Filters outlier control points if sample size $N > 4$.
   - Reports fitted transformation matrix and maximum Euclidean residual errors in the QGIS Processing Log.
   - Transforms all vertices to **EPSG:4326** (WGS 84).

## Supported Geometry Types

The tool handles all vector geometry types:
- **Point** and **MultiPoint**
- **LineString** and **MultiLineString**
- **Polygon** and **MultiPolygon**

::: tip Quick Setup Tip
Select your LGU layer as **Input Local Grid Layer (LGU Layer)** and your `_bgy` layer as **Reference WGS84 Layer (_bgy / Control Points)**. The tool automatically cross-matches fields like `geocode` or `barangay_n` across both layers!
:::
