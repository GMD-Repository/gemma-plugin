# Update LGU PSGC Metadata

The **Update LGU PSGC Metadata** tool automatically populates PSGC (Philippine Standard Geographic Code) metadata fields in your barangay boundary layers. It uses a reference PSGC table and fuzzy name matching to fill in region, province, city/municipality codes and names.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Update LGU PSGC Metadata
- **Algorithm ID:** `gmd_pipeline:update_lgu_psgc_metadata`

## When to Use

Use this tool when:

- Barangay boundary layers are missing PSGC code fields
- You need to standardize administrative metadata across layers
- Layer names need to be matched against the official PSGC reference table
- You're preparing layers for official submission and need accurate administrative codes

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input Layer** | Feature Source (Polygon) | The barangay boundary layer to update |
| **PSGC Reference Table** | File / Layer | The PSGC lookup table containing region, province, city/mun, and barangay data |
| **Region** | Cascading Dropdown | Select the region — auto-detected from the input layer name |
| **Province** | Cascading Dropdown | Select the province — filtered by the selected region |
| **City/Municipality** | Cascading Dropdown | Select the city/municipality — filtered by the selected province |

## Key Features

### Auto-Detection
The tool automatically detects the city/municipality from the **input layer name**. It searches the PSGC table for a matching city/municipality name, using:

1. **Exact substring match** — normalized to lowercase, with common suffixes like `_bgy` and `_barangay` stripped
2. **Fuzzy matching fallback** — uses `difflib` fuzzy matching (cutoff = 0.75) for spelling variants

### Cascading Dropdowns
The Region, Province, and City/Municipality parameters are linked as cascading dropdowns:
- Changing the **Region** updates the Province and City/Municipality options
- Changing the **Province** updates the City/Municipality options

### Barangay Name Normalization
The tool normalizes barangay names for robust matching, handling:
- Common abbreviations: `Sta.` → `Santa`, `Sto.` → `Santo`, `Brgy.` → removed
- Roman numerals: `Poblacion III` → `Poblacion 3`
- Punctuation and spacing variations
- Leading zeros in numeric names

## Output

| Output | Description |
|--------|-------------|
| **Updated Layer** | A new layer with PSGC metadata fields populated |

The output layer will contain updated fields with the official PSGC codes, region, province, city/municipality, and barangay information.

::: tip
For best results, name your input layers with the city/municipality name (e.g., `Quezon City_bgy`) — the auto-detection will recognize the name and pre-fill the cascading dropdowns.
:::

::: warning
Always verify the auto-detected values before running the tool. Fuzzy matching may occasionally produce incorrect matches for similarly named municipalities.
:::
