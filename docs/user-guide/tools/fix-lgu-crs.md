# <img src="/icons/crs.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Fix LGU CRS

The **Fix LGU CRS** tool batch-corrects or repositions vector layers digitized in local arbitrary grid coordinates (~0 to ~100,000) to true WGS84 coordinates (**EPSG:4326**). It fits a 2D Affine transformation matrix via Ordinary Least Squares (OLS) based on control points and transforms all geometry vertices to standard WGS 84.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Fix LGU CRS
- **Algorithm ID:** `gmd_pipeline:fixlgucrs`

## When to Use

Use this tool when:

- An LGU layer was digitized in a local, arbitrary, or unknown coordinate system (~0 to ~100,000)
- Boundaries appear out of position or offset from geographic coordinates
- You need to transform local grid geometries to standardized WGS 84 (EPSG:4326)
- Control point attributes (`XI`, `YI`, `LongitudeI`, `LatitudeI`) exist in the layer or target coordinates are provided via a reference layer

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input Local Grid Layer** | Feature Source (Any Geometry) | The local grid layer to be corrected |
| **Reference WGS84 Layer** | Feature Source (Any Geometry) [Optional] | Optional reference layer in EPSG:4326 used for target coordinates if attributes are absent |
| **Local X Field** | Field (Numeric) [Optional] | Optional manual selection for Local X field (overrides auto-detection) |
| **Local Y Field** | Field (Numeric) [Optional] | Optional manual selection for Local Y field (overrides auto-detection) |
| **WGS84 Longitude Field** | Field (Numeric) [Optional] | Optional manual selection for WGS84 Longitude field (overrides auto-detection) |
| **WGS84 Latitude Field** | Field (Numeric) [Optional] | Optional manual selection for WGS84 Latitude field (overrides auto-detection) |
| **Input Match Field** | Field (Any) [Optional] | Optional manual attribute field from the input layer used to match reference features |
| **Reference Match Field** | Field (Any) [Optional] | Optional manual attribute field from the reference layer used to match input features |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Corrected Layer** | Feature Sink | The transformed geometry layer in EPSG:4326 |

## How It Works

1. **Smart Feature Field & Matching Auto-Detection**:
   - Supports optional manual field selections for coordinate columns (`Local X`, `Local Y`, `WGS84 Longitude`, `WGS84 Latitude`) and feature matching keys (`Input Match Field`, `Reference Match Field`).
   - If fields are not explicitly selected, automatically auto-detects `XI`, `YI`, `LongitudeI`, `LatitudeI` attribute fields if present in the input layer.
   - Automatically falls back to feature geometry centroids for local $(X, Y)$ if local coordinate fields are absent.
   - Evaluates common attribute candidate pairs (e.g. `bgy_code`, `psgc_bgy`, `name`, `barangay`, `code`), filtering out dummy/null values (like `'0'`, `'0.0'`, `'null'`), and selects the pair yielding the maximum number of unique matched control points (minimum 3).
   - Pre-computes relative spatial centroid proximity mapping as a robust fallback if attribute matching is unavailable or incomplete.

2. **2D Affine OLS Matrix Computation**:
   - Fits a 2D affine transformation matrix via Ordinary Least Squares:
     $$\text{Longitude} = a \cdot X + b \cdot Y + c$$
     $$\text{Latitude} = d \cdot X + e \cdot Y + f$$

3. **Residual Reporting**:
   - Calculates per-point Euclidean distance error across control points and reports the fit matrix and maximum residual to the QGIS Processing Log window.

4. **Geometry Transformation & Output**:
   - Transforms all geometry vertices using the fitted 2D affine matrix.
   - Sets output layer CRS to **EPSG:4326** (WGS 84).

## Supported Geometry Types

The tool handles all vector geometry types:
- **Point** and **MultiPoint**
- **LineString** and **MultiLineString**
- **Polygon** and **MultiPolygon**

::: tip
If your layer already contains `XI`, `YI`, `LongitudeI`, and `LatitudeI` attributes, you can run the tool in 1 click without selecting an extra reference layer!
:::
