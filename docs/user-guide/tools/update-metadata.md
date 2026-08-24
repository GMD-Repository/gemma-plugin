# <img src="/icons/update.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Update Metadata

The **Update Metadata** tool automatically enriches an input LGU boundary polygon layer with standardized administrative metadata from an official PSGC (Philippine Standard Geographic Code) Excel spreadsheet. Matched and unmatched features are combined into a single permanent GeoPackage output layer, clearly categorized by a `boundary` classification field (`Barangay` vs `Contested`).

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Update Metadata
- **Algorithm ID:** `gmd_pipeline:update_metadata`

## When to Use

Use this tool when:

- Barangay boundary layers are missing PSGC geocodes or standardized geographic metadata.
- You need to standardize region, province, city/municipality, and barangay attributes before official submission.
- You want to cleanly identify contested boundary areas while maintaining complete topological coverage.
- You need to generate an auto-formatted, permanent GeoPackage file for downstream validation.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **LGU boundary layer** | Feature Source (Polygon) | The spatial polygon layer whose attributes you wish to update. |
| **LGU join field** | Layer Field (String) | Field containing barangay names to match against PSGC. Features with NULL are classified as Contested. |
| **Raw barangay name field** | Layer Field (Optional) | Secondary column (e.g. original BARANGAY name) used to populate `lgu_bgy_name` when the join field is NULL. |
| **PSGC xlsx file / table** | File / Table | Official PSGC Excel spreadsheet containing geocodes, map UUIDs, and admin hierarchies. |
| **Region** | Cascading Dropdown | Region filter populated dynamically from the PSGC sheet. |
| **Province** | Cascading Dropdown | Province filter filtered dynamically by selected region. |
| **City/Municipality** | Cascading Dropdown | City/Municipality filter filtered dynamically by selected province. |
| **Output Directory** | Folder Destination | Destination folder where the resulting GeoPackage will be permanently saved. |

## Key Features

### Smart Name Normalization & Fuzzy Matching
The algorithm normalizes barangay strings to ensure high-accuracy joining against PSGC records:
- **Abbreviations**: Expands prefixes such as `Sta.` → `Santa`, `Sto.` → `Santo`, `San.` → `San`, `St.` → `Saint`.
- **Roman Numerals**: Standardizes Roman numerals and alphanumeric barangay names (e.g. `Poblacion III` ↔ `Poblacion 3`, `Zone 1` ↔ `Zone I`).
- **Whitespace & Punctuation**: Strips special characters, trailing zeroes, and inconsistent spacing.

### Cascading Administrative Hierarchy
Selecting a **Region** updates available **Provinces**, and selecting a **Province** dynamically populates the **City/Municipality** list. When layer names match standard naming conventions, administrative filters auto-detect corresponding values.

### Unified Single-Layer Classification
Rather than splitting output files, all features are saved into a single permanent GeoPackage with a dedicated `boundary` attribute:
- **`Barangay`**: Successfully matched to an official PSGC record.
- **`Contested`**: Unmatched, NULL, or disputed boundary polygons.

## Output Schema

| Field Name | Type | Description |
|------------|------|-------------|
| `fid` | Integer | Feature unique integer identifier |
| `map_uuid` | String | Standardized Map UUID code |
| `geocode` | String | Complete 9- or 10-digit PSGC geocode |
| `region` | String | Region name |
| `province` | String | Province name |
| `city_mun` | String | City or Municipality name |
| `barangay` | String | Official standardized barangay name |
| `code` | String | Administrative boundary code |
| `boundary` | String | Boundary classification (`Barangay` or `Contested`) |
| `remarks` | String | Audit notes, match quality, or dispute comments |
| `source` | String | Data source attribution |
| `hhcount` | Integer | Total household count |
| `bldgcount` | Integer | Total building point count |

::: tip
Specify a dedicated target directory under **Output Directory**. The tool automatically creates the output `.gpkg` file with standardized naming conventions based on the selected LGU.
:::
