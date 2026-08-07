# <img src="/icons/update.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Update Metadata (by Geocode)

The **Update Metadata (by Geocode)** tool enriches an input LGU boundary polygon layer by performing a left-join with the standard PSGC Excel spreadsheet using the LGU Geocode field.

## Access

- **Processing Toolbox:** GMD Pipeline → GMD Toolkits → Update Metadata (by Geocode)
- **Algorithm ID:** `gmd_pipeline:update_lgu_by_geocode`

## When to Use

Use this tool when:
- You have an LGU boundary layer containing geocodes and want to standardise its attribute table with official PSGC metadata.
- You need to generate a structured 15-column schema containing PSGC codes, region, province, city/municipality, and barangay details.
- You want to export the enriched spatial layer directly as a GeoPackage (`.gpkg`) in EPSG:4326.

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **LGU boundary layer (polygon)** | Feature Source (Polygon) | The input LGU polygon vector layer to update |
| **LGU geocode field** | Field | Dropdown auto-suggesting the geocode column in the LGU layer |
| **LGU barangay name field** | Field | Dropdown auto-suggesting the barangay column in the LGU layer |
| **PSGC File** | File | Excel spreadsheet file (defaults to `references/PSGC Q4.xlsx`) |
| **Source** | String | Metadata source name (pre-filled with `LGU`) |
| **Source Year** | String | Metadata source year (pre-filled with `2026`) |
| **Output Directory** | Folder | Destination directory (auto-prefilled with input layer location) |
| **Show output file after running** | Boolean | Toggle whether to automatically load the output layer into QGIS |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Updated LGU Layer** | Feature Sink (Polygon, EPSG:4326) | The left-joined LGU layer containing the standard 15-attribute schema |

## How It Works

1. **PSGC Spreadsheet Reading**:
   - Parses sheet `PSGC` from `PSGC Q4.xlsx` extracting `map_uuid`, `geocode`, `region`, `province`, `city_mun`, and `barangay`.

2. **Geocode Left-Join**:
   - Matches each feature in the LGU boundary layer against PSGC records using the normalized geocode.

3. **Schema Structuring & Export**:
   - Populates the 15-attribute schema: `map_uuid`, `geocode`, `region`, `province`, `city_mun`, `barangay`, `code` (`1003`), `remarks`, `source`, `hhcount`, `bldgcount`, `sy`, `boundary` (`Barangay`), `lgu_bgy_name`, `bdry_status`.
   - Reprojects geometries to WGS 84 (EPSG:4326) and saves a GeoPackage file in the specified Output Directory.

## Supported Geometry Types

- **Polygon** and **MultiPolygon**
