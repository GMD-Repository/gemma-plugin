# <img src="/icons/upload.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Join Barangay Attributes

The **Join Barangay Attributes** tool performs enhanced spatial-attribute matching between city/municipality vector layers and official PSGC reference tables. It replaces standard exact join limitations with Python-based fuzzy matching, Roman-to-Arabic numeral normalization, and streamlined error diagnostic reporting.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Join Barangay Attributes
- **Algorithm ID:** `gmd_pipeline:join_barangay_attributes`

## When to Use

Use this tool when:

- Barangay names in digitized vector layers contain spelling variations, typos, or abbreviation discrepancies
- Layer feature attributes use Roman numerals (e.g. `Poblacion III`) while reference tables use Arabic numbers (`Poblacion 3`), or vice versa
- You need a streamlined output layer retaining only the source name, the resolved PSGC name, and actionable error audit diagnostics
- You are running batch processing or single-run pipeline join tasks where scratch memory output layers are preferred

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **city/mun** | Vector Layer (Polygon / Any Geometry) | Input city/municipality vector layer containing barangay features |
| **field** | Field (String) | Attribute field in the input layer containing local barangay names |
| **psgc** | Vector Layer / Table | Official PSGC reference dataset containing standard codes and barangay names |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Matched Barangays** | Feature Sink | Clean scratch vector layer retaining the original geometry, the source field, the resolved standard name, and audit diagnostics |

## How It Works

1. **Automatic Field Normalization and Title-Casing**:
   - Converts source barangay names to standard title-case while expanding common Philippine administrative abbreviations (`Brgy.` → `Barangay`, `Sto.` → `Santo`, `Sta.` → `Santa`, `Pob.` → `Poblacion`, `Mt.` → `Mount`, `St.` → `Saint`).

2. **PSGC Filter by City/Municipality Code**:
   - Extracts the 5-digit LGU code prefix from the input layer name or attributes (`province_code + city_mun_code`) to isolate only relevant reference barangays.
   - Automatically generates and loads the filtered PSGC reference subset as a separate scratch layer (`<code_filter>_<city_name> (Filtered PSGC)`).

3. **Multi-Stage Match Engine**:
   - **Exact Match:** Performs 1:1 string comparison against the filtered PSGC reference table.
   - **Roman Numeral Normalization:** Converts Roman numeral words (`I`, `II`, `III`, `IV`, etc.) to Arabic numbers (`1`, `2`, `3`, `4`) to pair equivalent names automatically.
   - **Levenshtein Distance Fuzzy Match:** Calculates minimum character insertion, deletion, and substitution edits (up to a distance threshold of 3) for remaining unjoined features.

4. **Output Columns**:
   The output layer is streamlined to retain only three essential columns:
   - `<field_name>` (First column) — Original barangay attribute from the input layer
   - `barangay name (Final Name)` (Second column) — Resolved official PSGC barangay name
   - `error_detail` (Third column) — Actionable audit description for manual GIS inspection:
     - **Empty string (`""`)**: Feature matched cleanly (exact match or clean fuzzy match).
     - **Roman/Arabic normalization note**: e.g., `Matched via Roman/Arabic normalization: "Zone IV" → "Zone 4" (dist=0)`.
     - **Multiple match warning**: e.g., `2 candidates with same distance 1 for "San Jose" — review needed`.
     - **Unmatched notice**: e.g., `No match found within distance 3 for "Unknown"`.

## Supported Geometry Types

- **Polygon** and **MultiPolygon**
- **LineString** and **MultiLineString**
- **Point** and **MultiPoint**

::: tip
The **Matched Barangays** output is automatically generated as a temporary memory scratch layer. You can run single or batch runs safely without cluttering your local disk!
:::
