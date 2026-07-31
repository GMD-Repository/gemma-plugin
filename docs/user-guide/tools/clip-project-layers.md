# <img src="/icons/clip_layers.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Clip Project Layers by Extent

The **Clip Project Layers by Extent** algorithm batch clips multiple vector layers to a target administrative polygon boundary (such as an EA or Barangay boundary polygon) with an optional buffer margin and exports clean clipped GeoPackage files to a target output folder.

## Access

- **Processing Toolbox:** GMD Pipeline → GMD Toolkits → Clip Project Layers by Extent
- **Algorithm ID:** `gmd_pipeline:clipprojectlayers`

## When to Use

Use this algorithm when:

- Preparing vector mapping layers for field deployment trimmed to specific **EA** or **Barangay** boundaries.
- Batch clipping multiple vector layers against a single mask boundary polygon without running manual clipping commands layer by layer.
- Exporting clipped project vector datasets into a self-contained folder.

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input Vector Layers** | Multiple Vector Layers | Vector layers to clip in batch |
| **Mask Layer / Boundary Polygon** | Polygon Feature Source | Target administrative boundary polygon (supports native QGIS "Selected features only") |
| **Mask Buffer Distance** | Distance / Number | Optional buffer margin in layer units around mask polygon (e.g., `50.0` meters) |
| **Output Folder for Clipped GeoPackages** | Folder Destination | Destination directory where output `.gpkg` layers will be saved |
| **Overwrite Existing Files** | Boolean | Overwrite existing clipped files in the destination directory |

## Output

Creates clean, self-contained GeoPackage (`.gpkg`) files named `{layer_name}_clipped.gpkg` in the specified destination folder.
