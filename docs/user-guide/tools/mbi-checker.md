# MBI Checker

The **MBI Checker** (Map-Based Inventory Checker) is the core quality assurance tool for detecting **gaps** and **overlaps** in barangay polygon boundaries. It cross-references boundary polygons with building point layers to produce a comprehensive topology report.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → MBI Checker
- **Algorithm ID:** `gmd_pipeline:gaps_overlaps_checker`

## When to Use

Use this tool when you need to:

- Verify that barangay boundaries have no overlapping areas
- Check for gaps between adjacent barangay polygons
- Validate boundary integrity before submission
- Generate MBI report layers for review

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| **Barangay Polygon Layer(s)** | Multiple Vector Layers (Polygon) | Select one or more barangay boundary polygon layers to check |
| **Building Point Layer(s)** | Multiple Vector Layers (Point) | Select one or more building point layers for reference |
| **Analysis to Run** | Dropdown | Choose between: `Overlaps and Gaps`, `Overlaps Only`, or `Gaps Only` |
| **Export MBI layers as GPKG** | Checkbox | If checked, exports results to `C:\PSA-GIS\2026 1Map\Preliminary Output` |

## Analysis Modes

### Overlaps and Gaps (Default)
Runs both overlap detection and gap detection in a single pass. Use this for a complete boundary validation.

### Overlaps Only
Only detects areas where two or more barangay polygons overlap. Useful when gaps have already been resolved and you need to focus on overlapping boundaries.

### Gaps Only
Only detects empty areas between barangay polygons. Useful when overlaps have already been resolved and you need to focus on missing boundary coverage.

## How It Works

1. **Layer Merging** — Selected barangay layers are merged into a single dataset, with field schemas harmonized via refactoring.
2. **Overlap Detection** — The tool identifies areas where polygon geometries intersect, producing overlap polygons.
3. **Gap Detection** — The tool computes the boundary extent and identifies uncovered areas between polygons.
4. **Styling** — Output layers are automatically styled using the included MBI checker QML style for easy visual interpretation.
5. **Export** (optional) — Results can be saved as GPKG files for offline review or sharing.

## Output

The tool produces styled layers that are added to your QGIS project:

- **Overlap layers** — Polygons showing areas of overlap between barangay boundaries
- **Gap layers** — Polygons showing areas with no boundary coverage

::: tip
When the **Export MBI** option is enabled, the layers are also saved as GeoPackage files in the output directory. This makes it easy to share results with supervisors or other team members.
:::

## Best Practices

1. **Load all relevant layers first** — Make sure all barangay polygon layers and building point layers are loaded in your QGIS project before running the tool.
2. **Start with "Overlaps and Gaps"** — Run the full analysis first to get a complete picture of boundary issues.
3. **Fix overlaps before gaps** — Overlaps should generally be resolved first, as fixing overlaps can sometimes create or eliminate gaps.
4. **Re-run after fixes** — After making boundary corrections, re-run the checker to verify that all issues have been resolved.
