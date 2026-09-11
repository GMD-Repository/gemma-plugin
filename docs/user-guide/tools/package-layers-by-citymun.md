# <img src="/icons/package_layers.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Package Layers by City/Mun

The **Package Layers by City/Mun** tool splits four reference layers — MBI cases, building points, province PSA boundaries, and province LGU boundaries — into one GeoPackage per city/municipality, each written to its own folder. It is built for producing LGU presentation packages: instead of handing a province-wide file to every recipient, each city/mun gets a small, self-contained `.gpkg` with just its own features.

## Access

- **Menu:** Gemma → Others → Package Layers by City/Mun
- **Processing Toolbox:** GMD Pipeline → 1Map → Package Layers by City/Mun
- **Algorithm ID:** `gmd_pipeline:package_layers_by_citymun`

The tool is inherently interactive (pick layers, confirm field names, browse an output folder), so running it from either entry point opens the same dialog.

## When to Use

Use this tool when:

- Preparing per-city/municipality deliverables for LGU presentations or handoffs, instead of a single province-wide dataset.
- You need the same four reference layers (cases, building points, PSA boundary, LGU boundary) split and packaged consistently, city/mun by city/mun.
- You want the packaged layers organized into per-city/mun groups in the Layers panel for quick spot-checking, with styling already applied.

## Naming Convention

| Item | Pattern | Example |
|------|---------|---------|
| Output folder | `pppmm_CITYMUN/` | `01317_Iriga/` |
| GeoPackage | `pppmm_CITYMUN/pppmm_CITYMUN.gpkg` | `01317_Iriga/01317_Iriga.gpkg` |

- `ppp` = 3-digit province code, `mm` = 2-digit city/mun code — together, the first 5 characters of the geocode field.
- `CITYMUN` is the city/municipality name (from the City/Mun name field), sanitized to remove characters that aren't safe in a folder/file name.

Inside each GeoPackage, the four inputs are written as:

| Role | Output table name |
|------|--------------------|
| Cases layer | `ref_mbi_cases` |
| Building points layer | `ref_{citymun}_bldg_point` |
| Province PSA layer | `ref_{citymun}_psa` |
| Province LGU layer | `ref_{citymun}_lgu` |

## Parameters

| Field | Description |
|-------|-------------|
| **Cases layer** | The MBI cases layer to split. |
| **Building points layer** | The province-wide building points layer to split. |
| **Province PSA layer** | The province-wide PSA boundary layer to split. |
| **Province LGU layer** | The province-wide LGU boundary layer to split. |
| **Geocode field name** | Field (on all four layers) whose first 5 characters identify the city/mun. Auto-prefilled from `geocode` / `sa_geocode` when present. |
| **City/Mun name field** | Field supplying the human-readable city/mun name used to build the output folder/file name. Auto-prefilled from `city_mun` / `citymun`. |
| **Output folder** | Destination folder under which every `pppmm_CITYMUN/` folder is created. |
| **Load packaged layers into QGIS after Run** | When checked, adds the freshly written layers back into the project, grouped per city/mun under a top-level **Packaged Layers** group. Off by default — best for spot-checking a handful of city/mun; leave it off for a large, national-scale run, since loading hundreds of groups/layers can slow QGIS down. |
| **Add Google Satellite basemap below the layers** | Only enabled once "Load packaged layers" is checked. Adds the same HCMGIS Google Satellite XYZ basemap the PSA - LGU Boundary Comparison tool uses, placed at the bottom of the layer tree. Requires the HCMGIS plugin. |

The four layer dropdowns and the two field boxes are pre-filled with a best-effort guess from the layers already loaded in the project (matched by name keywords such as `mbi_cases`, `bldg_point`, `province_psa`, `province_lgu`), but any of them can be changed before running.

## How It Works

1. **City/mun code list**: The tool scans the geocode and city/mun-name fields across *all four* selected layers combined, so a city/mun present in only one of the inputs is still packaged — nothing is missed.
2. **Per-city/mun export**: For each city/mun code, the matching features from all four layers (`left(to_string(geocode_field), 5) = 'pppmm'`) are written into that city/mun's own GeoPackage, one output table per role.
3. **Field cleanup on write**: `fid`, `layer` and `path` attributes are dropped from every output table. Dropping `fid` lets GeoPackage assign a fresh, unique primary key per table (avoiding `UNIQUE constraint failed: fid` errors on a filtered subset); `layer`/`path` are merge-leftover provenance columns with no place in a packaged deliverable.
4. **Optional load-back**: With "Load packaged layers" checked, each city/mun's written tables are added to the project under `Packaged Layers → {pppmm_CITYMUN}`, styled from the plugin's bundled QML files where a matching one exists (`_bldg_point`, `_lgu`, `_psa`, `ref_mbi_cases` suffixes/names), and the group tree is expanded automatically.
5. **Session-wide auto-organize**: Once this tool has run once in a session, any layer added afterwards from one of its packaged GeoPackages — including manually via *Add Vector Layer* or the Browser panel — is automatically filed into its city/mun group and has the `<file> — <table>` name QGIS's Add Layer dialog applies by default stripped back to just the table name. Adding the same table a second time replaces the existing copy instead of duplicating it.
6. **Clean up duplicates**: A dedicated button sweeps the existing **Packaged Layers** groups and removes any duplicate copies left over from earlier loads, keeping one of each.

## Output

- One folder per city/mun under the chosen output folder, each containing that city/mun's `.gpkg`.
- The run log lists how many features matched each layer, per city/mun.

::: tip Geocode Text Format
If province codes start with `0` (e.g. `013`), make sure the geocode field is stored as text, not a number — otherwise the leading zero may already be lost, breaking the 5-character city/mun prefix.
:::

::: tip Reading the log
If the matched-feature count for a layer looks the same as that layer's whole feature count for *every* city/mun group, the geocode field picked for that layer doesn't actually vary by city/mun — double-check the field selected for that role.
:::

::: info Headless Execution
The dialog is inherently interactive, so running the algorithm (`gmd_pipeline:package_layers_by_citymun`) without a QGIS Desktop GUI (`qgis_process`, headless) simply reports that a GUI is required rather than opening the dialog.
:::
