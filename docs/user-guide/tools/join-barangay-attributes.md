# <img src="/icons/upload.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Join Barangay Attributes

The **Join Barangay Attributes** tool performs enhanced spatial-attribute matching between city/municipality vector layers and official PSGC reference tables. It replaces standard exact join limitations with Python-based fuzzy matching, Roman-to-Arabic numeral normalization, and detailed status/error diagnostic reporting.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Join Barangay Attributes
- **Algorithm ID:** `gmd_pipeline:join_barangay_attributes`

## When to Use

Use this tool when:

- Barangay names in digitized vector layers contain spelling variations, typos, or abbreviation discrepancies
- Layer feature attributes use Roman numerals (e.g. `Poblacion III`) while reference tables use Arabic numbers (`Poblacion 3`), or vice versa
- You need a comprehensive match audit report showing exact matches, fuzzy suggestions, multiple candidate collisions, and unmatched records
- You are running batch processing or single-run pipeline join tasks where scratch memory output layers are preferred

## Parameters

### Inputs

| Parameter | Type | Description |
|-----------|------|-------------|
| **city/mun** | Vector Layer (Polygon / Any Geometry) | Input city/municipality vector layer containing barangay features |
| **field** | Field (String) | Attribute field containing local barangay names |
| **psgc** | Vector Layer / Table | Official PSGC reference dataset containing standard codes and barangay names |
| **Max Levenshtein Distance** | Integer `[1-10]` (Advanced, Default: `3`) | Maximum character edit distance allowed for fuzzy candidate matching |
| **Generate temporary layer of filtered PSGC data** | Boolean (Default: `False`) | Optionally exports the filtered PSGC reference subset as a separate scratch layer |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| **Matched Barangays** | Feature Sink | Transformed polygon layer containing matched attributes and diagnostic columns |
| **Unmatched Barangays List** | Feature Sink (Table) | Scratch table listing features where no matching PSGC reference was found |

## How It Works

1. **Automatic Field Normalization & Title-Casing**:
   - Converts source barangay names to standard title-case while expanding common Philippine administrative abbreviations (`Brgy.` → `Barangay`, `Sto.` → `Santo`, `Pob.` → `Poblacion`).

2. **PSGC Filter by City/Municipality Code**:
   - Extracts the 5-digit LGU code prefix from the input layer name/attributes (`province_code + city_mun_code`) to isolate only relevant reference barangays.

3. **Multi-Stage Match Engine**:
   - **Exact Match:** Performs 1:1 string comparison.
   - **Roman Numeral Normalization:** Converts Roman numeral words (`I`, `II`, `III`, etc.) to Arabic numbers (`1`, `2`, `3`) to pair equivalent names automatically.
   - **Levenshtein Distance Fuzzy Match:** Calculates minimum character insertion, deletion, and substitution edits for remaining unjoined features.

4. **Diagnostic Columns**:
   The output layer is enriched with diagnostic reporting attributes:
   - `barangay name (Final Name)` — Resolved standard name
   - `match_status` — Match classification (`EXACT`, `FUZZY_MATCH`, `ROMAN_NUMERAL_FIX`, `MULTIPLE_MATCHES`, `NO_MATCH`)
   - `match_distance` — Edit distance score ($0 = \text{exact}$)
   - `all_candidates` — Pipe-separated list of potential fuzzy candidates within threshold
   - `error_detail` — Actionable audit description for manual GIS inspection

## Supported Geometry Types

- **Polygon** and **MultiPolygon**
- **LineString** and **MultiLineString**
- **Point** and **MultiPoint**

::: tip
Both **Matched Barangays** and **Unmatched Barangays List** outputs are automatically scheduled as temporary memory scratch layers. You can run single or batch runs safely without cluttering your local disk!
:::
