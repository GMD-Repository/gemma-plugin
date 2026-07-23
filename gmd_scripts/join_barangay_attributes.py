"""
Join Barangay Attributes — Enhanced Fuzzy Match
Name : Join Barangay Attributes
Group : 
With QGIS : 34013

Enhanced from the original .model3 export:
  - Python-based fuzzy matching (replaces limited QGIS expression)
  - Roman numeral ↔ Arabic number normalization
  - Reports ALL match candidates and error types
  - Adds match_status, all_candidates columns
  - Both outputs (Matched / Unmatched) are always forced to temporary
    scratch layers so Batch Processing behaves the same as a single run
"""

import os
import re
from difflib import SequenceMatcher
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingContext,
    QgsProcessingUtils,
    QgsProcessingOutputLayerDefinition,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
import processing
from qgis.PyQt.QtGui import QIcon


# ─── Roman Numeral Utilities ───────────────────────────────────────────────

ROMAN_TO_INT = {
    'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
    'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
    'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15,
    'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20,
    'XXI': 21, 'XXII': 22, 'XXIII': 23, 'XXIV': 24, 'XXV': 25,
    'XXVI': 26, 'XXVII': 27, 'XXVIII': 28, 'XXIX': 29, 'XXX': 30,
    'XXXI': 31, 'XXXII': 32, 'XXXIII': 33, 'XXXIV': 34, 'XXXV': 35,
    'XXXVI': 36, 'XXXVII': 37, 'XXXVIII': 38, 'XXXIX': 39, 'XL': 40,
    'XLI': 41, 'XLII': 42, 'XLIII': 43, 'XLIV': 44, 'XLV': 45,
    'XLVI': 46, 'XLVII': 47, 'XLVIII': 48, 'XLIX': 49, 'L': 50,
}
INT_TO_ROMAN = {v: k for k, v in ROMAN_TO_INT.items()}

# Regex to detect Roman numerals as standalone words
ROMAN_PATTERN = re.compile(
    r'\b(L|XL(?:IX|IV|V?I{0,3})|XXX(?:IX|IV|V?I{0,3})|XX(?:IX|IV|V?I{0,3})|X(?:IX|IV|V?I{0,3})|IX|IV|V?I{1,3})\b'
)

# Common abbreviations in Philippine barangay names
ABBREVIATIONS = {
    'brgy.': 'barangay', 'brgy': 'barangay',
    'sto.': 'santo', 'sta.': 'santa',
    'sr.': 'senior', 'jr.': 'junior',
    'pob.': 'poblacion',
    'mt.': 'mount', 'st.': 'saint',
}


def normalize_name(name):
    """Normalize a barangay name for comparison.

    - Lowercase
    - Expand abbreviations
    - Normalize whitespace and punctuation
    """
    if not name or str(name).strip() == '' or str(name) == 'NULL':
        return ''

    text = str(name).strip().lower()

    # Expand abbreviations
    for abbr, full in ABBREVIATIONS.items():
        text = text.replace(abbr, full)

    # Normalize hyphens and extra whitespace
    text = re.sub(r'[-–—]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def roman_to_arabic(name):
    """Convert Roman numeral words in a name to Arabic numbers.
    e.g., 'Poblacion III' → 'Poblacion 3'
    """
    if not name:
        return ''

    def replace_roman(match):
        roman = match.group(1).upper()
        if roman in ROMAN_TO_INT:
            return str(ROMAN_TO_INT[roman])
        return match.group(0)

    return ROMAN_PATTERN.sub(replace_roman, str(name).upper()).lower()


def arabic_to_roman(name):
    """Convert Arabic number words in a name to Roman numerals.
    e.g., 'Poblacion 3' → 'Poblacion III'
    """
    if not name:
        return ''

    def replace_arabic(match):
        num = int(match.group(0))
        if num in INT_TO_ROMAN:
            return INT_TO_ROMAN[num]
        return match.group(0)

    return re.sub(r'\b(\d{1,2})\b', replace_arabic, str(name)).lower()


def levenshtein_distance(s1, s2):
    """Compute the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def fuzzy_match_all(source_name, reference_names, max_distance=3):
    """Find ALL matching reference names within the Levenshtein distance threshold.

    Tries multiple normalization strategies:
    1. Direct normalized comparison
    2. Roman → Arabic conversion (with exact number matching)
    3. Arabic → Roman conversion (with exact number matching)

    Returns: list of (ref_name, distance, match_method) sorted by distance
    """
    if not source_name:
        return []

    norm_source = normalize_name(source_name)
    roman_source = roman_to_arabic(norm_source)
    arabic_source = arabic_to_roman(norm_source)

    # Pre-split source for number matching
    src_roman_base, src_roman_num = _split_name_and_number(roman_source)
    src_arabic_base, src_arabic_num = _split_name_and_number(arabic_source)

    candidates = []
    seen = set()

    for ref_name in reference_names:
        norm_ref = normalize_name(ref_name)
        if not norm_ref:
            continue

        # Strategy 1: Direct comparison
        dist = levenshtein_distance(norm_source, norm_ref)
        method = 'DIRECT'

        # Strategy 2: Roman → Arabic (both normalized to Arabic numbers)
        roman_ref = roman_to_arabic(norm_ref)
        ref_roman_base, ref_roman_num = _split_name_and_number(roman_ref)

        if src_roman_num is not None and ref_roman_num is not None:
            # Both have numbers — must match exactly
            if src_roman_num == ref_roman_num:
                dist_roman = levenshtein_distance(src_roman_base, ref_roman_base)
            else:
                dist_roman = max_distance + 1  # Skip — different numbered barangay
        else:
            dist_roman = levenshtein_distance(roman_source, roman_ref)

        if dist_roman < dist:
            dist = dist_roman
            method = 'ROMAN_NUMERAL'

        # Strategy 3: Arabic → Roman (both normalized to Roman numerals)
        arabic_ref = arabic_to_roman(norm_ref)
        ref_arabic_base, ref_arabic_num = _split_name_and_number(arabic_ref)

        if src_arabic_num is not None and ref_arabic_num is not None:
            if src_arabic_num == ref_arabic_num:
                dist_arabic = levenshtein_distance(src_arabic_base, ref_arabic_base)
            else:
                dist_arabic = max_distance + 1
        else:
            dist_arabic = levenshtein_distance(arabic_source, arabic_ref)

        if dist_arabic < dist:
            dist = dist_arabic
            method = 'ROMAN_NUMERAL'

        if dist <= max_distance and ref_name not in seen:
            candidates.append((ref_name, dist, method))
            seen.add(ref_name)

    # Sort by distance (best match first)
    candidates.sort(key=lambda x: x[1])
    return candidates


def _split_name_and_number(name):
    """Split a normalized name into base and numeric suffix.

    e.g., 'poblacion 3' → ('poblacion', '3')
          'barurao'     → ('barurao', None)
          'san jose 2'  → ('san jose', '2')
    """
    match = re.match(r'^(.+?)\s+(\d+)$', name.strip())
    if match:
        return match.group(1).strip(), match.group(2)
    return name.strip(), None


def fuzzy_match_roman_only(source_name, reference_names, max_distance=3):
    """Match specifically using Roman numeral ↔ Arabic number normalization.

    Both source and reference names are normalized to Arabic numbers before
    comparison. When BOTH names contain a trailing number, the numbers must
    match EXACTLY — only the base name is fuzzy-matched.

    This prevents wrong matches like:
      ✗ 'Barurao 1' → 'Barurao II' (different barangay!)
      ✓ 'Barurao 1' → 'Barurao I'  (same barangay, Roman numeral)
      ✓ 'Barurao 2' → 'Barurao II' (same barangay, Roman numeral)

    Returns: (best_ref_name, distance) or (None, None) if no match
    """
    if not source_name:
        return None, None

    # When neither name has a trailing number, only accept near-identical
    # matches (abbreviation/accent-level differences like "Sto. Nino" ->
    # "Santo Niño"). This is intentionally much tighter than max_distance
    # so it doesn't degrade into a general fuzzy matcher for unrelated
    # names (e.g. "Manawe" vs "Magaud").
    NO_NUMBER_MAX_DISTANCE = min(max_distance, 2)

    norm_source = normalize_name(source_name)
    arabic_source = roman_to_arabic(norm_source)
    source_base, source_num = _split_name_and_number(arabic_source)

    best_name = None
    best_dist = max_distance + 1

    for ref_name in reference_names:
        norm_ref = normalize_name(ref_name)
        if not norm_ref:
            continue

        arabic_ref = roman_to_arabic(norm_ref)
        ref_base, ref_num = _split_name_and_number(arabic_ref)

        # If both have numbers, they must match exactly
        if source_num is not None and ref_num is not None:
            if source_num != ref_num:
                continue  # Skip — different numbered barangay
            # Numbers match — fuzzy compare base names only
            dist = levenshtein_distance(source_base, ref_base)
        elif source_num is not None and ref_num is None:
            # Source has number, ref doesn't — compare full strings
            dist = levenshtein_distance(arabic_source, arabic_ref)
        elif source_num is None and ref_num is not None:
            # Source has no number, ref has number — compare full strings
            dist = levenshtein_distance(arabic_source, arabic_ref)
        else:
            # Neither source nor ref has a trailing number — this is not a
            # Roman/Arabic numeral situation, but normalize_name() already
            # expands common abbreviations (sto./sta./brgy./etc.) and this
            # branch is what legitimately resolves names like "STO. NINO" ->
            # "Santo Niño" or "STA. TERESA" -> "Santa Teresa". Those are
            # near-identical after normalization (distance 0-1, just accents
            # or leftover punctuation). A full open-ended fuzzy compare here
            # is too loose though — it also let unrelated names like
            # "Manawe" match "Magaud" at distance 3. So cap this branch to a
            # tight distance instead of disabling it outright.
            dist = levenshtein_distance(arabic_source, arabic_ref)
            if dist > NO_NUMBER_MAX_DISTANCE:
                continue

        if dist < best_dist:
            best_dist = dist
            best_name = ref_name

    if best_dist <= max_distance:
        return best_name, best_dist
    return None, None


def title_case_smart(name):
    """Apply title case, preserving Roman numerals and handling ALL CAPS.
    Same logic as the original model's field calculator CASE expression.
    """
    if not name or str(name).strip() == '':
        return name

    text = str(name).strip()

    # Check if ALL CAPS (with optional parentheses/hyphens)
    all_caps_pattern = r'^([(-]?(?:[A-Z][^ ]*|[IVXLCDM]+))( [(-]?(?:[A-Z][^ ]*|[IVXLCDM]+))*$'
    strict_caps_pattern = r'^([(-]?[A-Z]+)([ -()][(-]?[A-Z]+)*$'

    if re.match(all_caps_pattern, text):
        if re.match(strict_caps_pattern, text):
            # Pure ALL CAPS → Title Case
            return text.lower().title()
        else:
            # Mixed with Roman numerals → keep as-is
            return text
    else:
        # Not ALL CAPS → Title Case
        return text.lower().title()


class JoinBarangayAttributes(QgsProcessingAlgorithm):

    @staticmethod
    def _static_sink_value(param):
        """Return the plain destination string for a sink parameter, whether
        it was passed as a raw string or wrapped in a QgsProcessingOutputLayerDefinition."""
        if isinstance(param, QgsProcessingOutputLayerDefinition):
            return param.sink.staticValue()
        return param

    @classmethod
    def _is_temp_dest(cls, param):
        """True if a sink parameter is left on its temporary/in-memory default
        (i.e. no explicit file path was given), whether in a single run or a
        Batch Processing row."""
        val = cls._static_sink_value(param)
        return val in (None, '', 'TEMPORARY_OUTPUT') or (
            isinstance(val, str) and val.lower().startswith('memory:'))

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            'citymun', 'city/mun', defaultValue=None))
        self.addParameter(QgsProcessingParameterField(
            'field', 'field',
            type=QgsProcessingParameterField.Any,
            parentLayerParameterName='citymun',
            allowMultiple=False, defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer(
            'psgc', 'psgc',
            types=[QgsProcessing.TypeVector], defaultValue=None))
        max_distance_param = QgsProcessingParameterNumber(
            'max_distance', 'Max Levenshtein Distance',
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=3, minValue=1, maxValue=10)
        max_distance_param.setHelp(
            'Maximum number of character edits (insertions, deletions, '
            'substitutions) allowed between a source barangay name and a '
            'PSGC reference name for them to be considered a fuzzy match. '
            'Higher = more lenient (catches more typos/variants, but risks '
            'matching unrelated names). Lower = stricter (fewer false '
            'positives, but may miss real typos). This only affects the '
            '"psgc_bgy (fuzzy matched)" / "match_status" / "all_candidates" '
            'suggestion columns and the numbered Roman-numeral matching; it '
            'does NOT loosen the abbreviation-only matching used for '
            '"barangay name (Final Name)", which is capped at a distance '
            'of 2 regardless of this setting. Tuned and fixed at 3 by '
            'default — change only if you understand this trade-off.')
        # This value has been tuned and is no longer meant to be changed
        # in day-to-day use. Flagging it Advanced tucks it under the
        # "Advanced Parameters" section of the dialog instead of removing
        # it outright, so it stays adjustable if ever genuinely needed.
        max_distance_param.setFlags(
            max_distance_param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(max_distance_param)

        self.addParameter(QgsProcessingParameterBoolean(
            'generate_filtered_psgc', 'Generate temporary layer of filtered PSGC data',
            defaultValue=False))

        self.addParameter(QgsProcessingParameterFeatureSink(
            'Bgy_name', 'Matched Barangays',
            type=QgsProcessing.TypeVectorAnyGeometry,
            createByDefault=True, supportsAppend=True,
            defaultValue='TEMPORARY_OUTPUT'))

        self.addParameter(QgsProcessingParameterFeatureSink(
            'Unmatched_bgy', 'Unmatched Barangays List',
            type=QgsProcessing.TypeVector,
            createByDefault=True, supportsAppend=True,
            defaultValue='TEMPORARY_OUTPUT'))

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(7, model_feedback)
        results = {}
        outputs = {}

        # Force both outputs to ALWAYS be temporary/scratch memory layers,
        # regardless of what the Processing dialog or the Batch Processing
        # table has filled in for them. This makes single-run and batch-run
        # behave identically, and nothing gets written to disk unless you
        # deliberately remove these two lines.
        parameters['Bgy_name'] = QgsProcessing.TEMPORARY_OUTPUT
        parameters['Unmatched_bgy'] = QgsProcessing.TEMPORARY_OUTPUT

        max_distance = self.parameterAsInt(parameters, 'max_distance', context)
        field_name = parameters['field']
        generate_filtered = self.parameterAsBool(parameters, 'generate_filtered_psgc', context)

        # ── Step 1: Title-case the barangay field ───────────────────
        # NOTE: The original model used attribute(@feature, @field) which only works
        # inside the graphical model. In Python, we reference the field directly.
        alg_params = {
            'FIELD_LENGTH': 254,
            'FIELD_NAME': field_name,
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 2,  # Text (string)
            'FORMULA': (
                f'CASE\n'
                f'  WHEN regexp_match(\n'
                f'    "{field_name}",\n'
                f'    \'^([(-]?(?:[A-Z][^ ]*|[IVXLCDM]+))( [(-]?(?:[A-Z][^ ]*|[IVXLCDM]+))*$\'\n'
                f'  )\n'
                f'  THEN\n'
                f'    CASE\n'
                f'      WHEN regexp_match(\n'
                f'        "{field_name}",\n'
                f'        \'^([(-]?[A-Z]+)([ -()][(-]?[A-Z]+)*$\'\n'
                f'      )\n'
                f'      THEN title(lower("{field_name}"))\n'
                f'      ELSE "{field_name}"\n'
                f'    END\n'
                f'  ELSE title(lower("{field_name}"))\n'
                f'END'
            ),
            'INPUT': parameters['citymun'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FieldCalculator'] = processing.run(
            'native:fieldcalculator', alg_params,
            context=context, feedback=feedback, is_child_algorithm=True)

        feedback.pushInfo(f'Step 1 done. Checking title-case output...')
        step1_layer = QgsProcessingUtils.mapLayerFromString(
            outputs['FieldCalculator']['OUTPUT'], context)
        if step1_layer:
            first = next(step1_layer.getFeatures(), None)
            if first:
                feedback.pushInfo(f'  Step 1 first feature {field_name}: {first[field_name]}')

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # ── Step 2: Calculate lgu_code on PSGC table ────────────────────
        alg_params = {
            'FIELD_LENGTH': 254,
            'FIELD_NAME': 'lgu_code',
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 2,  # Text (string)
            'FORMULA': 'concat("province_code","city_mun_code")',
            'INPUT': parameters['psgc'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['LguCode'] = processing.run(
            'native:fieldcalculator', alg_params,
            context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # ── Step 3: Extract by expression (Filter PSGC by city/mun code) ─────────────
        citymun_layer = QgsProcessingUtils.mapLayerFromString(parameters['citymun'], context)
        citymun_name = citymun_layer.name() if citymun_layer else ''
        code_filter = citymun_name[:5]

        feedback.pushInfo(f"Filtering PSGC layer where lgu_code = '{code_filter}'")

        alg_params = {
            'EXPRESSION': f"\"lgu_code\" = '{code_filter}'",
            'INPUT': outputs['LguCode']['OUTPUT'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractByExpression'] = processing.run(
            'native:extractbyexpression', alg_params,
            context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Detect actual barangay field name in PSGC layer (may be uppercase)
        extract_layer_tmp = QgsProcessingUtils.mapLayerFromString(
            outputs['ExtractByExpression']['OUTPUT'], context)
        psgc_bgy_field_for_join = 'barangay'  # default fallback
        if extract_layer_tmp:
            for f in extract_layer_tmp.fields():
                if f.name().lower() == 'barangay':
                    psgc_bgy_field_for_join = f.name()
                    break
            feedback.pushInfo(f'PSGC barangay field for join: "{psgc_bgy_field_for_join}"')

        # ── Step 4: Join by barangay name (exact match) ─────────────────
        alg_params = {
            'DISCARD_NONMATCHING': False,
            'FIELD': field_name,
            'FIELDS_TO_COPY': [psgc_bgy_field_for_join],
            'FIELD_2': psgc_bgy_field_for_join,
            'INPUT': outputs['FieldCalculator']['OUTPUT'],
            'INPUT_2': outputs['ExtractByExpression']['OUTPUT'],
            'METHOD': 1,
            'PREFIX': 'psgc_',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['JoinAttributesByBarangayName'] = processing.run(
            'native:joinattributestable', alg_params,
            context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # ── Step 7: Python-based fuzzy match with Roman numeral support ─
        feedback.pushInfo('Starting enhanced fuzzy matching...')

        # Load the reference barangay names from ExtractByExpression output
        extract_layer_id = outputs['ExtractByExpression']['OUTPUT']
        feedback.pushInfo(f'Extract layer ID: {extract_layer_id}')
        extract_layer = QgsProcessingUtils.mapLayerFromString(extract_layer_id, context)
        if extract_layer is None:
            feedback.reportError(f'Cannot load reference layer from ExtractByExpression (ID: {extract_layer_id})')
            return {}

        # ── Determine actual city/mun name from the filtered PSGC layer ─────
        # (computed here, right after filtering, so it's available both for
        #  labeling the Filtered PSGC Layer below and for the Matched/
        #  Unmatched output names further down)
        actual_city_name = ""
        if extract_layer and extract_layer.featureCount() > 0:
            feat = next(extract_layer.getFeatures())
            # Look for common field names indicating city/municipality
            for fname in ['city_mun', 'citymun', 'city_municipality', 'city', 'municipality', 'name', 'city_name', 'mun_name']:
                idx = extract_layer.fields().indexOf(fname)
                if idx != -1:
                    actual_city_name = str(feat[idx]).strip()
                    break

            # Fallback: look for any column containing 'city' or 'mun' but NOT 'code'
            if not actual_city_name:
                for field in extract_layer.fields():
                    fname_lower = field.name().lower()
                    if ('city' in fname_lower or 'mun' in fname_lower) and 'code' not in fname_lower:
                        actual_city_name = str(feat[field.name()]).strip()
                        break

        # Ultimate fallback if still not found
        if not actual_city_name:
            raw_name = citymun_name[5:].strip() if len(citymun_name) > 5 else citymun_name
            actual_city_name = raw_name if raw_name else "Unknown"

        # If user checked the box, load the Filtered PSGC output into the project,
        # labeled with the city/mun code so it's identifiable across batch runs
        if generate_filtered:
            if code_filter:
                filtered_name = f"{code_filter}_{actual_city_name} (Filtered PSGC)"
            else:
                filtered_name = f"{actual_city_name} (Filtered PSGC)"
            details = QgsProcessingContext.LayerDetails(filtered_name, context.project(), 'Filtered_PSGC_Output')
            context.addLayerToLoadOnCompletion(extract_layer_id, details)
            feedback.pushInfo(f'Filtered PSGC layer scheduled to load on completion as "{filtered_name}".')

        feedback.pushInfo(f'Extract layer fields: {[f.name() for f in extract_layer.fields()]}')
        feedback.pushInfo(f'Extract layer feature count: {extract_layer.featureCount()}')

        # Detect the actual barangay field name (may be 'barangay', 'BARANGAY', etc.)
        psgc_bgy_field = None
        for f in extract_layer.fields():
            if f.name().lower() == 'barangay':
                psgc_bgy_field = f.name()
                break
        if psgc_bgy_field is None:
            feedback.reportError('Could not find a "barangay" field in the PSGC layer (checked case-insensitively)')
            return {}
        feedback.pushInfo(f'Detected PSGC barangay field name: "{psgc_bgy_field}"')

        reference_names = []
        for feat in extract_layer.getFeatures():
            bgy_val = feat[psgc_bgy_field]
            if bgy_val and str(bgy_val).strip() and str(bgy_val) != 'NULL':
                reference_names.append(str(bgy_val).strip())

        feedback.pushInfo(f'Loaded {len(reference_names)} reference barangay names')
        if reference_names:
            feedback.pushInfo(f'Sample references: {reference_names[:5]}')

        # Load the joined layer (input for fuzzy matching)
        joined_layer_id = outputs['JoinAttributesByBarangayName']['OUTPUT']
        feedback.pushInfo(f'Joined layer ID: {joined_layer_id}')
        joined_layer = QgsProcessingUtils.mapLayerFromString(joined_layer_id, context)
        if joined_layer is None:
            feedback.reportError(f'Cannot load joined layer (ID: {joined_layer_id})')
            return {}

        feedback.pushInfo(f'Joined layer fields: {[f.name() for f in joined_layer.fields()]}')
        feedback.pushInfo(f'Joined layer feature count: {joined_layer.featureCount()}')

        # The joined field will have the prefix 'psgc_' added during the join step
        expected_joined_name = f'psgc_{psgc_bgy_field_for_join}'
        joined_bgy_field = expected_joined_name

        # Verify it exists in the joined layer
        field_found = False
        for f in joined_layer.fields():
            if f.name().lower() == expected_joined_name.lower():
                joined_bgy_field = f.name()
                field_found = True
                break

        if not field_found:
            feedback.pushWarning(f'Could not find expected joined field {expected_joined_name}')
        feedback.pushInfo(f'Detected joined barangay field name: "{joined_bgy_field}"')

        # Debug: show first feature's values
        first_feat = next(joined_layer.getFeatures(), None)
        if first_feat:
            feedback.pushInfo(f'First feature {field_name}: {first_feat[field_name]}')
            feedback.pushInfo(f'First feature barangay: {first_feat[joined_bgy_field]}')
        else:
            feedback.reportError('Joined layer has no features!')
            return {}

        # Build output fields in the desired column order:
        #   1. [input field_name]  (e.g. BARANGAY — the original input barangay name)
        #   2. barangay name (Final Name)
        #   3. barangay (Exact Matched)
        #   4. psgc_bgy_2 (fuzzy matched)
        #   5. AREA
        #   6. match_status
        #   7. psgc_bgy (fuzzy matched)
        #   8. match_distance
        #   9. all_candidates
        #  10. error_detail

        # Collect original field definitions we need (by lowercase name)
        orig_field_defs = {f.name().lower(): f for f in joined_layer.fields()}

        out_fields = QgsFields()

        # 1. Input barangay field
        if field_name.lower() in orig_field_defs:
            f = orig_field_defs[field_name.lower()]
            out_fields.append(QgsField(f.name(), f.type(), f.typeName(), f.length(), f.precision()))

        # 2. barangay name (Final Name) — new computed field
        out_fields.append(QgsField('barangay name (Final Name)', QVariant.String, len=254))

        # 3. barangay (Exact Matched) — renamed from the joined barangay field
        if joined_bgy_field.lower() in orig_field_defs:
            f = orig_field_defs[joined_bgy_field.lower()]
            out_fields.append(QgsField('barangay (Exact Matched)', f.type(), f.typeName(), f.length(), f.precision()))
        else:
            out_fields.append(QgsField('barangay (Exact Matched)', QVariant.String, len=254))

        # 4. psgc_bgy_2 (fuzzy matched) — new computed field
        out_fields.append(QgsField('psgc_bgy_2 (fuzzy matched)', QVariant.String, len=254))

        # 5. AREA
        area_field_name = None
        for f in joined_layer.fields():
            if f.name().lower() == 'area':
                area_field_name = f.name()
                out_fields.append(QgsField(f.name(), f.type(), f.typeName(), f.length(), f.precision()))
                break

        # 6. match_status
        out_fields.append(QgsField('match_status', QVariant.String, len=50))

        # 7. psgc_bgy (fuzzy matched)
        out_fields.append(QgsField('psgc_bgy (fuzzy matched)', QVariant.String, len=254))

        # 8. match_distance
        out_fields.append(QgsField('match_distance', QVariant.Int))

        # 9. all_candidates
        out_fields.append(QgsField('all_candidates', QVariant.String, len=500))

        # 10. error_detail
        out_fields.append(QgsField('error_detail', QVariant.String, len=500))

        # Create output sink
        (sink, dest_id) = self.parameterAsSink(
            parameters, 'Bgy_name', context,
            out_fields, joined_layer.wkbType(), joined_layer.sourceCrs())

        if sink is None:
            feedback.reportError('Could not create output layer')
            return {}

        # Counters for summary
        stats = {
            'total': 0, 'exact': 0, 'fuzzy': 0,
            'multiple': 0, 'roman': 0, 'no_match': 0
        }

        features = list(joined_layer.getFeatures())
        total = len(features)

        unmatched_list = []

        for i, feature in enumerate(features):
            if feedback.isCanceled():
                return {}

            stats['total'] += 1
            source_name = feature[field_name]
            exact_match = feature[joined_bgy_field]

            # Create output feature with all original attributes
            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(feature.geometry())
            # Copy only the original fields we kept in the output
            out_feat.setAttribute(field_name, feature[field_name])
            out_feat.setAttribute('barangay (Exact Matched)', feature.attribute(joined_bgy_field))
            if area_field_name:
                out_feat.setAttribute(area_field_name, feature.attribute(area_field_name))

            # ── psgc_bgy_2 (fuzzy matched): Roman numeral ↔ Arabic number match ─────────
            roman_match, roman_dist = fuzzy_match_roman_only(
                source_name, reference_names, max_distance)
            out_feat.setAttribute('psgc_bgy_2 (fuzzy matched)', roman_match)

            # Check if exact match already exists
            has_exact = (exact_match and str(exact_match).strip() != ''
                         and str(exact_match) != 'NULL')

            # ── barangay name (Final Name): coalesce exact match and psgc_bgy_2 ─────────
            final_name = str(exact_match) if has_exact else roman_match
            out_feat.setAttribute('barangay name (Final Name)', final_name)

            if not final_name or str(final_name).strip() == '' or str(final_name).upper() == 'NULL':
                if source_name:
                    unmatched_list.append(str(source_name).strip())

            if has_exact:
                # Exact match found — no fuzzy needed
                out_feat.setAttribute('psgc_bgy (fuzzy matched)', str(exact_match))
                out_feat.setAttribute('match_distance', 0)
                out_feat.setAttribute('match_status', 'EXACT')
                out_feat.setAttribute('all_candidates', str(exact_match))
                out_feat.setAttribute('error_detail', '')
                stats['exact'] += 1
            else:
                # No exact match — run fuzzy matching
                candidates = fuzzy_match_all(
                    source_name, reference_names, max_distance)

                if not candidates:
                    # No match found at all
                    out_feat.setAttribute('psgc_bgy (fuzzy matched)', None)
                    out_feat.setAttribute('match_distance', None)
                    out_feat.setAttribute('match_status', 'NO_MATCH')
                    out_feat.setAttribute('all_candidates', '')
                    out_feat.setAttribute('error_detail',
                        f'No match found within distance {max_distance} '
                        f'for "{source_name}"')
                    stats['no_match'] += 1

                elif len(candidates) == 1:
                    # Single best match
                    best_name, best_dist, method = candidates[0]
                    out_feat.setAttribute('psgc_bgy (fuzzy matched)', best_name)
                    out_feat.setAttribute('match_distance', best_dist)

                    if method == 'ROMAN_NUMERAL':
                        out_feat.setAttribute('match_status', 'ROMAN_NUMERAL_FIX')
                        out_feat.setAttribute('error_detail',
                            f'Matched via Roman/Arabic normalization: '
                            f'"{source_name}" → "{best_name}" (dist={best_dist})')
                        stats['roman'] += 1
                    else:
                        out_feat.setAttribute('match_status', 'FUZZY_MATCH')
                        out_feat.setAttribute('error_detail', '')
                        stats['fuzzy'] += 1

                    out_feat.setAttribute('all_candidates',
                        f'{best_name} (dist={best_dist})')

                else:
                    # Multiple candidates found
                    best_name, best_dist, method = candidates[0]
                    out_feat.setAttribute('psgc_bgy (fuzzy matched)', best_name)
                    out_feat.setAttribute('match_distance', best_dist)

                    # Check if top candidates have same distance (ambiguous)
                    same_dist = [c for c in candidates if c[1] == best_dist]

                    if len(same_dist) > 1:
                        out_feat.setAttribute('match_status', 'MULTIPLE_MATCHES')
                        out_feat.setAttribute('error_detail',
                            f'{len(same_dist)} candidates with same distance '
                            f'{best_dist} for "{source_name}" — review needed')
                        stats['multiple'] += 1
                    elif method == 'ROMAN_NUMERAL':
                        out_feat.setAttribute('match_status', 'ROMAN_NUMERAL_FIX')
                        out_feat.setAttribute('error_detail',
                            f'Matched via Roman/Arabic normalization: '
                            f'"{source_name}" → "{best_name}" (dist={best_dist})')
                        stats['roman'] += 1
                    else:
                        out_feat.setAttribute('match_status', 'FUZZY_MATCH')
                        out_feat.setAttribute('error_detail', '')
                        stats['fuzzy'] += 1

                    # List ALL candidates
                    cand_str = ', '.join(
                        f'{c[0]} (dist={c[1]})' for c in candidates[:10])
                    out_feat.setAttribute('all_candidates', cand_str)

            sink.addFeature(out_feat)
            feedback.setProgress(int((i + 1) / total * 100))

        results['Bgy_name'] = dest_id

        # ── Output Unmatched List ───────────────────────────────────────
        udest_id = None
        if unmatched_list:
            unmatched_str = "Unmatched Barangay List: " + ", ".join(unmatched_list)
            unmatched_fields = QgsFields()
            unmatched_fields.append(QgsField('unmatched_list', QVariant.String))

            (usink, udest_id) = self.parameterAsSink(
                parameters, 'Unmatched_bgy', context,
                unmatched_fields, QgsWkbTypes.NoGeometry, joined_layer.sourceCrs())

            if usink:
                u_feat = QgsFeature(unmatched_fields)
                u_feat.setAttribute('unmatched_list', unmatched_str)
                usink.addFeature(u_feat)
                results['Unmatched_bgy'] = udest_id

        # ── Adjust Attribute Table Column Widths ────────────────────────
        out_layer = QgsProcessingUtils.mapLayerFromString(dest_id, context)
        if out_layer:
            config = out_layer.attributeTableConfig()
            widths = {
                'barangay name (Final Name)': 170,
                'barangay (Exact Matched)': 170,
                'psgc_bgy (fuzzy matched)': 185,
                'psgc_bgy_2 (fuzzy matched)': 185,
                'match_distance': 100,
                'match_status': 100,
                'all_candidates': 120,
                'error_detail': 120
            }
            # Set minimum width of 150 for all columns, override with specific widths
            for i, col in enumerate(config.columns()):
                f_name = col.name
                config.setColumnWidth(i, widths.get(f_name, 150))
            out_layer.setAttributeTableConfig(config)
            # actual_city_name was already computed earlier (also used to label
            # the Filtered PSGC Layer output above)

            # Format name: 06506_buti (Matched)
            if code_filter:
                new_name = f"{code_filter}_{actual_city_name} (Matched)"
                unmatched_name = f"{code_filter}_{actual_city_name} (Unmatched)"
            else:
                new_name = f"{actual_city_name} (Matched)"
                unmatched_name = f"{actual_city_name} (Unmatched)"

            out_layer.setName(new_name)

            # ── Schedule Matched Barangays to load into the project ─────
            # Scheduled unconditionally so it loads whether run as a single
            # process or as a Batch Processing row, since both output
            # destinations are now always forced to temporary scratch layers.
            details = QgsProcessingContext.LayerDetails(
                new_name, context.project(), 'Bgy_name')
            context.addLayerToLoadOnCompletion(dest_id, details)

            # ── Schedule Unmatched Barangays List the same way ──────────
            if udest_id:
                u_details = QgsProcessingContext.LayerDetails(
                    unmatched_name, context.project(), 'Unmatched_bgy')
                context.addLayerToLoadOnCompletion(udest_id, u_details)

        # ── Summary Report ──────────────────────────────────────────────
        feedback.pushInfo('')
        feedback.pushInfo('━' * 45)
        feedback.pushInfo('  FUZZY MATCH SUMMARY')
        feedback.pushInfo('━' * 45)
        feedback.pushInfo(f"  ✅ Exact matches:        {stats['exact']}")
        feedback.pushInfo(f"  🔄 Fuzzy matches:        {stats['fuzzy']}")
        feedback.pushInfo(f"  🔢 Roman numeral fixes:  {stats['roman']}")
        feedback.pushInfo(f"  ⚠️ Multiple matches:     {stats['multiple']}")
        feedback.pushInfo(f"  ❌ No match found:        {stats['no_match']}")
        feedback.pushInfo('━' * 45)
        feedback.pushInfo(f"  Total features:          {stats['total']}")
        feedback.pushInfo('━' * 45)

        return results

    def name(self):
        return 'join_barangay_attributes'

    def displayName(self):
        return 'Join Barangay Attributes'

    def group(self):
        return '1Map'

    def groupId(self):
        return '1map'

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons/upload.png'))

    def shortHelpString(self):
        return (
            'Enhanced Join Barangay Attributes with fuzzy matching.\n\n'
            'Matches barangay names from a city/municipality layer against '
            'a PSGC reference table using:\n'
            '  • Exact name matching\n'
            '  • Levenshtein distance fuzzy matching\n'
            '  • Roman numeral ↔ Arabic number normalization\n\n'
            'Parameters:\n'
            '  • Max Levenshtein Distance (Advanced) — Maximum number of '
            'character edits allowed between a source name and a PSGC '
            'reference name to still count as a fuzzy match. Controls how '
            'lenient the "psgc_bgy (fuzzy matched)" suggestion column and '
            'the numbered Roman-numeral matching are. Fixed at 3 by '
            'default and tucked under Advanced Parameters since it rarely '
            'needs changing; raising it finds more variants but risks '
            'false matches, lowering it is stricter but may miss real '
            'typos.\n\n'
            'Output columns:\n'
            '  • psgc_bgy — Best matching PSGC barangay name\n'
            '  • match_distance — Levenshtein distance (0 = exact)\n'
            '  • match_status — EXACT / FUZZY_MATCH / MULTIPLE_MATCHES / '
            'ROMAN_NUMERAL_FIX / NO_MATCH\n'
            '  • all_candidates — All matches within threshold\n'
            '  • error_detail — Description of issues needing review\n\n'
            'Both Matched and Unmatched outputs are always temporary scratch '
            'layers, in a single run and in Batch Processing alike, so they '
            'load straight into the project instead of being written to disk.'
        )

    def createInstance(self):
        return JoinBarangayAttributes()