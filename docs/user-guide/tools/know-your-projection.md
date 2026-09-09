# <img src="/icons/projection_finder.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Know Your Projection!

The **Know Your Projection!** tool provides a comprehensive coordinate diagnostics, automated Philippine CRS candidate detection, and 2D affine georeferencing environment for vector datasets with missing, misidentified, or arbitrary local coordinate systems.

## Access

- **Menu:** Gemma → Updating of Boundaries → Know Your Projection!

## When to Use

Use this tool when:
- Vector shapefiles or GeoPackages have missing, missing `.prj` sidecars, or unassigned coordinate reference systems.
- Boundary layers digitized in local CAD units (~0 to ~100,000) need to be georeferenced to standard Philippine CRS grids.
- Layer boundaries fail to overlay correctly onto basemap imagery due to datum offset confusion between WGS 84, PRS92, and Luzon 1911.
- You need to audit and classify coordinate values across municipal datasets before conducting boundary reconciliation.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input vector layer to diagnose** | Feature Source (Any Geometry) | Optional vector layer to audit or diagnose. If omitted, opens the interactive tool for workspace layer selection. |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Diagnostic summary** | String | Detailed coordinate classification, extent metrics, and candidate CRS matches logged during processing. |

## How It Works

1. **Coordinate Extent Diagnosis**:
   - Classifies bounding box magnitudes and spans into four distinct coordinate regimes:
     - **Geographic Coordinates (Degrees):** Coordinates within $[-180^\circ, 180^\circ]$ longitude and $[-90^\circ, 90^\circ]$ latitude. Suggests EPSG:4326 (WGS 84), EPSG:4683 (PRS92), or EPSG:4253 (Luzon 1911).
     - **Projected Grid (Metres):** Coordinates within $[100,000, 1,000,000]$ Easting and $[300,000, 2,700,000]$ Northing, matching Philippine transverse Mercator (PTM) or UTM zones.
     - **Web Mercator (EPSG:3857):** Coordinates within $[12,000,000, 14,500,000]$ Easting.
     - **Local / Arbitrary Grid:** Non-georeferenced coordinates digitized from CAD plans or uncalibrated tablet sheets.

2. **Automated Philippine CRS Candidate Scanning**:
   - Tests layer extents across 23 national and regional coordinate definitions (WGS 84, PRS92, Luzon 1911 PTM Zones 1–5, and UTM Zones 50N–52N).
   - Identifies candidate systems that place the layer boundaries fully within the Philippine terrestrial extent ($116.0^\circ\text{E} - 127.5^\circ\text{E}$, $4.0^\circ\text{N} - 21.5^\circ\text{N}$).

3. **2D 6-Parameter Affine Georeferencing**:
   - Calculates a 2D affine transformation matrix via Ordinary Least Squares (OLS) between digitized local coordinate pairs $(x, y)$ and verified control point coordinates $(X, Y)$:
     $$\begin{aligned} X &= a \cdot x + b \cdot y + c \\ Y &= d \cdot x + e \cdot y + f \end{aligned}$$
   - Resolves translation $(c, f)$, independent $X$ and $Y$ scale factors, rotation angles, and shear anisotropy to absorb non-uniform digitizing distortion.
   - Evaluates root-mean-square (RMS) residuals in metres across all control points to verify positional fit before applying changes.

4. **Visual Basemap Inspection**:
   - Automatically loads Google Satellite, Hybrid, or Streets imagery at the bottom of the QGIS layer tree to visually confirm boundary alignment without obscuring vector geometry.

## Supported Coordinate Systems Matrix

| CRS Identifier | Name / Grid System | Typical Area of Use |
|----------------|-------------------|---------------------|
| **EPSG:4326** | WGS 84 (Geographic) | Global GPS default, web portals, interchange |
| **EPSG:4683** | PRS92 (Geographic) | National standard Philippine geographic datum |
| **EPSG:32651** | WGS 84 / UTM Zone 51N | Nationwide projected default in metres (Zones 50N/52N for Palawan/Mindanao East) |
| **ESRI:102457** | PRS92 / UTM Zone 51N | National PRS92 projected coverage |
| **EPSG:3121 – 3125** | PRS92 / Philippines Zones I – V | Official national PTM municipal survey grids |
| **EPSG:25391 – 25395** | Luzon 1911 / Philippines Zones I – V | Historical cadastral and NAMRIA topographic maps |
| **EPSG:3857** | WGS 84 / Pseudo-Mercator | Web tiling, OpenStreetMap, and Google basemaps |

::: tip
For boundary delineation and census verification, **EPSG:32651** (WGS 84 / UTM Zone 51N) is the recommended export format because projected planar units (metres) yield reliable area and distance metrics, and seamlessly match satellite basemaps.
:::
