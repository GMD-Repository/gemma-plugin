# <img src="/icons/crs.png" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Fix LGU CRS

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

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Corrected Layer** | Feature Sink | The transformed geometry layer in EPSG:4326 |

## How It Works

1. **Smart Zero-Config Feature Auto-Detection**:
   - Automatically detects `XI`, `YI`, `LongitudeI`, `LatitudeI` attribute fields if present in the input layer.
   - Automatically falls back to feature geometry centroids for local $(X, Y)$ if `XI`/`YI` attributes are absent.
   - Uses the `Reference WGS84 Layer` point centroids for target $(Longitude, Latitude)$ if target attribute fields are missing.

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
