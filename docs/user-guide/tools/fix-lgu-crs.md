# Fix LGU CRS / Geometry

The **Fix LGU CRS / Geometry** tool repositions an LGU (Local Government Unit) boundary layer to align with a correctly positioned reference layer. It computes scale and translation transforms based on bounding box comparison and outputs the corrected layer in **EPSG:4326** (WGS 84).

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Fix LGU CRS / Geometry
- **Algorithm ID:** `gmd_pipeline:fixlgucrs`

## When to Use

Use this tool when:

- An LGU boundary layer is in an unknown or incorrect coordinate reference system
- Boundaries appear in the wrong location or at the wrong scale on the map
- You need to align an LGU layer to a reference layer from a trusted source
- The layer needs to be converted to WGS 84 (EPSG:4326) for standardization

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **LGU Layer** | Feature Source (Any Geometry) | The layer to be corrected — this is the mispositioned or misscaled layer |
| **Reference Layer** | Feature Source (Any Geometry) | A correctly positioned layer to align the LGU layer to |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Fixed Layer** | Feature Sink | The corrected geometry output in EPSG:4326 |
| **Scale** | Number | The computed scale factor applied |
| **TX** | Number | The computed X-axis translation |
| **TY** | Number | The computed Y-axis translation |

## How It Works

1. **Bounding Box Comparison** — The tool compares the bounding boxes of the LGU layer and the reference layer.
2. **Scale Computation** — The scale factor is calculated as the ratio of the reference layer width to the LGU layer width:
   ```
   scale = reference_width / lgu_width
   ```
3. **Translation Computation** — Translation values are computed to align the center points:
   ```
   tx = ref_center_x - (lgu_center_x × scale)
   ty = ref_center_y - (lgu_center_y × scale)
   ```
4. **Geometry Transform** — Each feature's geometry is transformed using the computed scale and translation values.
5. **CRS Assignment** — The output layer is assigned EPSG:4326 as its coordinate reference system.

## Supported Geometry Types

The tool handles:
- **Polygon** and **MultiPolygon** geometries — full ring-by-ring vertex transformation
- **Other geometry types** — vertex-level transformation via geometry mapping

## Output Details

The transform values (Scale, TX, TY) are displayed in the **Processing Results** panel after the algorithm completes. These values can be useful for:

- Documenting the correction applied
- Verifying that the transform was reasonable
- Applying the same correction to other layers from the same source

::: tip
Both the LGU layer and the reference layer must be loaded in your QGIS project before running the tool.
:::

::: warning
This tool assumes both layers represent the same geographic area. The bounding box alignment will produce incorrect results if the layers cover different extents.
:::
