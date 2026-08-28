# <img src="/icons/upload.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Join Barangay Attributes

The **Join Barangay Attributes** tool performs enhanced spatial-attribute matching between city/municipality vector layers and official Philippine Standard Geographic Code (PSGC) reference tables. It embeds the official PSGC reference dataset (`references/PSGC Q4.xlsx`) directly into the processing algorithm, eliminating the need to manually supply a reference table, and features multi-stage fuzzy matching, Roman-to-Arabic numeral normalization, and automated error diagnostics.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Join Barangay Attributes
- **Algorithm ID:** `gmd_pipeline:join_barangay_attributes`

## When to Use

Use this tool when:

- Barangay names in digitized vector layers contain spelling variations, typos, or abbreviation discrepancies
- Layer feature attributes use Roman numerals (e.g., `Poblacion III`) while reference tables use Arabic numbers (`Poblacion 3`), or vice versa
- You need a streamlined output layer retaining only the source name, the resolved PSGC name, and actionable error audit diagnostics
- You are running single or batch processing workflows where automatic scratch memory output layers are preferred
- You want an automated join workflow without having to manually select or load the official PSGC reference table

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **city/mun** | Feature Source (Polygon / Any Geometry) | Input city/municipality vector layer containing barangay boundary features |
| **field** | Field (String) | Attribute field in the input layer containing local barangay names |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Matched Barangays** | Feature Sink (Matching Input Geometry) | Output vector layer retaining original geometry, the source field (title-cased), the resolved standard name, and audit diagnostics |
| **Filtered PSGC Table** | Feature Sink (No Geometry) | Non-spatial attribute table containing all official PSGC reference records filtered for the target city/municipality |

## How It Works

1. **Embedded PSGC Reference Resolution**:
   - Automatically loads and parses the built-in official PSGC reference dataset from `references/PSGC Q4.xlsx` via native OGR and Python readers.
   - Extracts the 5-digit LGU code prefix (`province_code` + `city_mun_code` or geocode prefix) from the input layer name or attributes, filtering only the reference barangays for the target city/municipality.
   - Automatically outputs and loads the filtered PSGC reference subset as `<code_filter>_<city_name> (Filtered PSGC)`.

2. **Automatic Field Normalization and Title-Casing**:
   - Converts source barangay names to smart title-case while expanding common Philippine administrative abbreviations (`Brgy.` → `Barangay`, `Sto.` → `Santo`, `Sta.` → `Santa`, `Pob.` → `Poblacion`, `Mt.` → `Mount`, `St.` → `Saint`).

3. **Multi-Stage Match Engine**:
   - **Exact Match:** Performs direct case-insensitive string comparison against the filtered reference records.
   - **Roman Numeral Normalization:** Converts Roman numeral tokens (`I`, `II`, `III`, `IV`, etc.) to Arabic numbers (`1`, `2`, `3`, `4`) to match equivalent name variations automatically.
   - **Levenshtein Distance Fuzzy Match:** Calculates minimum character insertion, deletion, and substitution edits (within a distance threshold of 3) for remaining unmatched features.

4. **Output Columns**:
   The matched output layer is streamlined to retain only three essential columns:
   - `<field_name>` (First column) — Original barangay attribute from the input layer (converted to smart Title Case)
   - `barangay name (Final Name)` (Second column) — Resolved official PSGC barangay name
   - `error_detail` (Third column) — Actionable audit description for manual GIS inspection:
     - **Empty string (`""`)**: Feature matched cleanly (exact match or clean fuzzy match).
     - **Roman/Arabic normalization note**: e.g., `Matched via Roman/Arabic normalization: "Zone IV" -> "Zone 4" (dist=0)`.
     - **Multiple match warning**: e.g., `2 candidates with same distance 1 for "San Jose" — review needed`.
     - **Unmatched notice**: e.g., `No match found for "Unknown"`.

## Supported Geometry Types

- **Polygon** and **MultiPolygon**
- **LineString** and **MultiLineString**
- **Point** and **MultiPoint**

::: tip
Both **Matched Barangays** and **Filtered PSGC Table** outputs are automatically generated as temporary memory scratch layers. You can execute single runs or batch runs safely without manual file configuration.
:::
