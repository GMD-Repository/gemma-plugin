# Export Preliminary Polygons

The **Export Preliminary Polygons** tool merges resolved barangay boundary layers into a consolidated output for 1Map preliminary submission. After you've resolved all overlaps and gaps, use this tool to produce the final merged dataset.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Export Preliminary Polygons
- **Algorithm ID:** `gmd_pipeline:export_preliminary_polygons`

## When to Use

Use this tool when:

- All overlaps and gaps have been resolved for a municipality's barangay boundaries
- You need to merge multiple barangay layers into a single consolidated output
- You're preparing the preliminary polygon submission for 1Map

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| **Barangay Polygon Layer(s)** | Multiple Vector Layers (Polygon) | Select one or more resolved barangay boundary polygon layers to merge |

## How It Works

1. **Layer Selection** — Select all the resolved barangay polygon layers that need to be merged.
2. **Field Harmonization** — The tool refactors field schemas across all selected layers so they can be merged consistently.
3. **Merging** — All selected layers are merged into a single polygon layer.
4. **Styling** — The output layer is automatically styled using the MBI checker QML style.
5. **Export** — The merged result is exported as a GeoPackage to `C:\PSA-GIS\2026 1Map\Preliminary Output`.

## Output

- A merged polygon layer added to your QGIS project with MBI styling applied
- A GPKG file saved to the preliminary output directory

::: tip
Run the [MBI Checker](/tools/mbi-checker) one final time on the exported merged layer to confirm there are no remaining overlaps or gaps before submission.
:::

## Workflow

The typical workflow for 1Map boundary preparation is:

1. Load barangay boundary layers into QGIS
2. Run **MBI Checker** → identify overlaps and gaps
3. Fix overlaps manually in QGIS
4. Run **Fill Polygon Gaps** → assign gaps to correct barangays
5. Re-run **MBI Checker** → verify all issues resolved
6. Run **Export Preliminary Polygons** → produce final merged output
