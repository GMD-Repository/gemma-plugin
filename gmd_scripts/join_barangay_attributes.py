"""
Join Barangay Attributes — Enhanced Fuzzy Match

Timestamp   : 2026-08-20
Version     : 1.1.0
Changelog   :
  v1.0.0 - Initial enhanced version (Python-based fuzzy matching, Roman
           numeral <-> Arabic number normalization, match_status and
           all_candidates reporting columns, both outputs forced to
           temporary scratch layers so Batch Processing behaves like a
           single run).
  v1.1.0 - Removed "Generate temporary layer of filtered PSGC data"
           checkbox; the filtered PSGC layer is now always generated
           (mandatory, no longer optional).
         - Hid the Advanced Parameters section from the dialog by
           flagging "Max Levenshtein Distance" as FlagHidden (was
           FlagAdvanced) so it no longer appears in the UI at all;
           the value is still fixed internally at its default of 3.
         - Removed the "Unmatched Barangays List" output entirely,
           including its processing parameter, sink creation, and the
           logic that scheduled it to load into the project. Only the
           "Matched Barangays" output remains.
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

ROMAN_PATTERN = re.compile(
    r'\b(L|XL(?:IX|IV|V?I{0,3})|XXX(?:IX|IV|V?I{0,3})|XX(?:IX|IV|V?I{0,3})|X(?:IX|IV|V?I{0,3})|IX|IV|V?I{1,3})\b'
)

ABBREVIATIONS = {
    'brgy.': 'barangay', 'brgy': 'barangay',
    'sto.': 'santo', 'sta.': 'santa',
    'sr.': 'senior', 'jr.': 'junior',
    'pob.': 'poblacion',
    'mt.': 'mount', 'st.': 'saint',
}


def normalize_name(name):
    if not name or str(name).strip() == '' or str(name) == 'NULL':
        return ''
    text = str(name).strip().lower()
    for abbr, full in ABBREVIATIONS.items():
        text = text.replace(abbr, full)
    text = re.sub(r'[-–—]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def roman_to_arabic(name):
    if not name:
        return ''

    def replace_roman(match):
        roman = match.group(1).upper()
        if roman in ROMAN_TO_INT:
            return str(ROMAN_TO_INT[roman])
        return match.group(0)

    return ROMAN_PATTERN.sub(replace_roman, str(name).upper()).lower()


def arabic_to_roman(name):
    if not name:
        return ''

    def replace_arabic(match):
        num = int(match.group(0))
        if num in INT_TO_ROMAN:
            return INT_TO_ROMAN[num]
        return match.group(0)

    return re.sub(r'\b(\d{1,2})\b', replace_arabic, str(name)).lower()


def levenshtein_distance(s1, s2):
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
    if not source_name:
        return []

    norm_source = normalize_name(source_name)
    roman_source = roman_to_arabic(norm_source)
    arabic_source = arabic_to_roman(norm_source)

    src_roman_base, src_roman_num = _split_name_and_number(roman_source)
    src_arabic_base, src_arabic_num = _split_name_and_number(arabic_source)

    candidates = []
    seen = set()

    for ref_name in reference_names:
        norm_ref = normalize_name(ref_name)
        if not norm_ref:
            continue

        dist = levenshtein_distance(norm_source, norm_ref)
        method = 'DIRECT'

        roman_ref = roman_to_arabic(norm_ref)
        ref_roman_base, ref_roman_num = _split_name_and_number(roman_ref)

        if src_roman_num is not None and ref_roman_num is not None:
            if src_roman_num == ref_roman_num:
                dist_roman = levenshtein_distance(src_roman_base, ref_roman_base)
            else:
                dist_roman = max_distance + 1
        else:
            dist_roman = levenshtein_distance(roman_source, roman_ref)

        if dist_roman < dist:
            dist = dist_roman
            method = 'ROMAN_NUMERAL'

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

    candidates.sort(key=lambda x: x[1])
    return candidates


def _split_name_and_number(name):
    match = re.match(r'^(.+?)\s+(\d+)$', name.strip())
    if match:
        return match.group(1).strip(), match.group(2)
    return name.strip(), None


def fuzzy_match_roman_only(source_name, reference_names, max_distance=3):
    if not source_name:
        return None, None

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

        if source_num is not None and ref_num is not None:
            if source_num != ref_num:
                continue
            dist = levenshtein_distance(source_base, ref_base)
        elif source_num is not None and ref_num is None:
            dist = levenshtein_distance(arabic_source, arabic_ref)
        elif source_num is None and ref_num is not None:
            dist = levenshtein_distance(arabic_source, arabic_ref)
        else:
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
    if not name or str(name).strip() == '':
        return name

    text = str(name).strip()

    all_caps_pattern = r'^([(-]?(?:[A-Z][^ ]*|[IVXLCDM]+))( [(-]?(?:[A-Z][^ ]*|[IVXLCDM]+))*$'
    strict_caps_pattern = r'^([(-]?[A-Z]+)([ -()][(-]?[A-Z]+)*$'

    if re.match(all_caps_pattern, text):
        if re.match(strict_caps_pattern, text):
            return text.lower().title()
        else:
            return text
    else:
        return text.lower().title()


class JoinBarangayAttributes(QgsProcessingAlgorithm):

    @staticmethod
    def _static_sink_value(param):
        if isinstance(param, QgsProcessingOutputLayerDefinition):
            return param.sink.staticValue()
        return param

    @classmethod
    def _is_temp_dest(cls, param):
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

        # Max Levenshtein Distance is now fully hidden from the dialog
        # (was previously tucked under "Advanced Parameters"). The value
        # stays fixed at its default of 3 internally.
        max_distance_param = QgsProcessingParameterNumber(
            'max_distance', 'Max Levenshtein Distance',
            type=QgsProcessingParameterNumber.Integer,
            defaultValue=3, minValue=1, maxValue=10)
        max_distance_param.setHelp(
            'Maximum number of character edits (insertions, deletions, '
            'substitutions) allowed between a source barangay name and a '
            'PSGC reference name for them to be considered a fuzzy match. '
            'Fixed at 3 and hidden from the dialog — change only in code '
            'if you understand this trade-off.')
        max_distance_param.setFlags(
            max_distance_param.flags() | QgsProcessingParameterDefinition.FlagHidden)
        self.addParameter(max_distance_param)

        # NOTE: "Generate temporary layer of filtered PSGC data" checkbox
        # has been removed — generating that layer is now mandatory and
        # always happens, so there's no parameter for it anymore.

        self.addParameter(QgsProcessingParameterFeatureSink(
            'Bgy_name', 'Matched Barangays',
            type=QgsProcessing.TypeVectorAnyGeometry,
            createByDefault=True, supportsAppend=True,
            defaultValue='TEMPORARY_OUTPUT'))

        # NOTE: "Unmatched Barangays List" output has been removed entirely.

    def processAlgorithm(self, parameters, context, model_feedback):
        feedback = QgsProcessingMultiStepFeedback(7, model_feedback)
        results = {}
        outputs = {}

        # Force the Matched output to ALWAYS be a temporary/scratch memory
        # layer, regardless of what the Processing dialog or the Batch
        # Processing table has filled in, so single-run and batch-run
        # behave identically.
        parameters['Bgy_name'] = QgsProcessing.TEMPORARY_OUTPUT

        max_distance = self.parameterAsInt(parameters, 'max_distance', context)
        field_name = parameters['field']

        # Generating the filtered PSGC layer is now mandatory (no longer
        # an optional checkbox).
        generate_filtered = True

        # ── Step 1: Title-case the barangay field ───────────────────
        alg_params = {
            'FIELD_LENGTH': 254,
            'FIELD_NAME': field_name,
            'FIELD_PRECISION': 0,
            'FIELD_TYPE': 2,
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
            'FIELD_TYPE': 2,
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

        # ── Step 3: Extract by expression (Filter PSGC by city/mun code) ─
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

        extract_layer_tmp = QgsProcessingUtils.mapLayerFromString(
            outputs['ExtractByExpression']['OUTPUT'], context)
        psgc_bgy_field_for_join = 'barangay'
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

        extract_layer_id = outputs['ExtractByExpression']['OUTPUT']
        feedback.pushInfo(f'Extract layer ID: {extract_layer_id}')
        extract_layer = QgsProcessingUtils.mapLayerFromString(extract_layer_id, context)
        if extract_layer is None:
            feedback.reportError(f'Cannot load reference layer from ExtractByExpression (ID: {extract_layer_id})')
            return {}

        actual_city_name = ""
        if extract_layer and extract_layer.featureCount() > 0:
            feat = next(extract_layer.getFeatures())
            for fname in ['city_mun', 'citymun', 'city_municipality', 'city', 'municipality', 'name', 'city_name', 'mun_name']:
                idx = extract_layer.fields().indexOf(fname)
                if idx != -1:
                    actual_city_name = str(feat[idx]).strip()
                    break

            if not actual_city_name:
                for field in extract_layer.fields():
                    fname_lower = field.name().lower()
                    if ('city' in fname_lower or 'mun' in fname_lower) and 'code' not in fname_lower:
                        actual_city_name = str(feat[field.name()]).strip()
                        break

        if not actual_city_name:
            raw_name = citymun_name[5:].strip() if len(citymun_name) > 5 else citymun_name
            actual_city_name = raw_name if raw_name else "Unknown"

        # Filtered PSGC layer is now always generated and loaded (no
        # longer gated behind a checkbox).
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

        joined_layer_id = outputs['JoinAttributesByBarangayName']['OUTPUT']
        feedback.pushInfo(f'Joined layer ID: {joined_layer_id}')
        joined_layer = QgsProcessingUtils.mapLayerFromString(joined_layer_id, context)
        if joined_layer is None:
            feedback.reportError(f'Cannot load joined layer (ID: {joined_layer_id})')
            return {}

        feedback.pushInfo(f'Joined layer fields: {[f.name() for f in joined_layer.fields()]}')
        feedback.pushInfo(f'Joined layer feature count: {joined_layer.featureCount()}')

        expected_joined_name = f'psgc_{psgc_bgy_field_for_join}'
        joined_bgy_field = expected_joined_name

        field_found = False
        for f in joined_layer.fields():
            if f.name().lower() == expected_joined_name.lower():
                joined_bgy_field = f.name()
                field_found = True
                break

        if not field_found:
            feedback.pushWarning(f'Could not find expected joined field {expected_joined_name}')
        feedback.pushInfo(f'Detected joined barangay field name: "{joined_bgy_field}"')

        first_feat = next(joined_layer.getFeatures(), None)
        if first_feat:
            feedback.pushInfo(f'First feature {field_name}: {first_feat[field_name]}')
            feedback.pushInfo(f'First feature barangay: {first_feat[joined_bgy_field]}')
        else:
            feedback.reportError('Joined layer has no features!')
            return {}

        orig_field_defs = {f.name().lower(): f for f in joined_layer.fields()}

        out_fields = QgsFields()

        if field_name.lower() in orig_field_defs:
            f = orig_field_defs[field_name.lower()]
            out_fields.append(QgsField(f.name(), f.type(), f.typeName(), f.length(), f.precision()))

        out_fields.append(QgsField('barangay name (Final Name)', QVariant.String, len=254))

        if joined_bgy_field.lower() in orig_field_defs:
            f = orig_field_defs[joined_bgy_field.lower()]
            out_fields.append(QgsField('barangay (Exact Matched)', f.type(), f.typeName(), f.length(), f.precision()))
        else:
            out_fields.append(QgsField('barangay (Exact Matched)', QVariant.String, len=254))

        out_fields.append(QgsField('psgc_bgy_2 (fuzzy matched)', QVariant.String, len=254))

        area_field_name = None
        for f in joined_layer.fields():
            if f.name().lower() == 'area':
                area_field_name = f.name()
                out_fields.append(QgsField(f.name(), f.type(), f.typeName(), f.length(), f.precision()))
                break

        out_fields.append(QgsField('match_status', QVariant.String, len=50))
        out_fields.append(QgsField('psgc_bgy (fuzzy matched)', QVariant.String, len=254))
        out_fields.append(QgsField('match_distance', QVariant.Int))
        out_fields.append(QgsField('all_candidates', QVariant.String, len=500))
        out_fields.append(QgsField('error_detail', QVariant.String, len=500))

        (sink, dest_id) = self.parameterAsSink(
            parameters, 'Bgy_name', context,
            out_fields, joined_layer.wkbType(), joined_layer.sourceCrs())

        if sink is None:
            feedback.reportError('Could not create output layer')
            return {}

        stats = {
            'total': 0, 'exact': 0, 'fuzzy': 0,
            'multiple': 0, 'roman': 0, 'no_match': 0
        }

        features = list(joined_layer.getFeatures())
        total = len(features)

        for i, feature in enumerate(features):
            if feedback.isCanceled():
                return {}

            stats['total'] += 1
            source_name = feature[field_name]
            exact_match = feature[joined_bgy_field]

            out_feat = QgsFeature(out_fields)
            out_feat.setGeometry(feature.geometry())
            out_feat.setAttribute(field_name, feature[field_name])
            out_feat.setAttribute('barangay (Exact Matched)', feature.attribute(joined_bgy_field))
            if area_field_name:
                out_feat.setAttribute(area_field_name, feature.attribute(area_field_name))

            roman_match, roman_dist = fuzzy_match_roman_only(
                source_name, reference_names, max_distance)
            out_feat.setAttribute('psgc_bgy_2 (fuzzy matched)', roman_match)

            has_exact = (exact_match and str(exact_match).strip() != ''
                         and str(exact_match) != 'NULL')

            final_name = str(exact_match) if has_exact else roman_match
            out_feat.setAttribute('barangay name (Final Name)', final_name)

            if has_exact:
                out_feat.setAttribute('psgc_bgy (fuzzy matched)', str(exact_match))
                out_feat.setAttribute('match_distance', 0)
                out_feat.setAttribute('match_status', 'EXACT')
                out_feat.setAttribute('all_candidates', str(exact_match))
                out_feat.setAttribute('error_detail', '')
                stats['exact'] += 1
            else:
                candidates = fuzzy_match_all(
                    source_name, reference_names, max_distance)

                if not candidates:
                    out_feat.setAttribute('psgc_bgy (fuzzy matched)', None)
                    out_feat.setAttribute('match_distance', None)
                    out_feat.setAttribute('match_status', 'NO_MATCH')
                    out_feat.setAttribute('all_candidates', '')
                    out_feat.setAttribute('error_detail',
                        f'No match found within distance {max_distance} '
                        f'for "{source_name}"')
                    stats['no_match'] += 1

                elif len(candidates) == 1:
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
                    best_name, best_dist, method = candidates[0]
                    out_feat.setAttribute('psgc_bgy (fuzzy matched)', best_name)
                    out_feat.setAttribute('match_distance', best_dist)

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

                    cand_str = ', '.join(
                        f'{c[0]} (dist={c[1]})' for c in candidates[:10])
                    out_feat.setAttribute('all_candidates', cand_str)

            sink.addFeature(out_feat)
            feedback.setProgress(int((i + 1) / total * 100))

        results['Bgy_name'] = dest_id

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
            for i, col in enumerate(config.columns()):
                f_name = col.name
                config.setColumnWidth(i, widths.get(f_name, 150))
            out_layer.setAttributeTableConfig(config)

            if code_filter:
                new_name = f"{code_filter}_{actual_city_name} (Matched)"
            else:
                new_name = f"{actual_city_name} (Matched)"

            out_layer.setName(new_name)

            details = QgsProcessingContext.LayerDetails(
                new_name, context.project(), 'Bgy_name')
            context.addLayerToLoadOnCompletion(dest_id, details)

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
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'upload.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return (
            'Enhanced Join Barangay Attributes with fuzzy matching.\n\n'
            'Matches barangay names from a city/municipality layer against '
            'a PSGC reference table using:\n'
            '  • Exact name matching\n'
            '  • Levenshtein distance fuzzy matching\n'
            '  • Roman numeral ↔ Arabic number normalization\n\n'
            'Output columns:\n'
            '  • psgc_bgy — Best matching PSGC barangay name\n'
            '  • match_distance — Levenshtein distance (0 = exact)\n'
            '  • match_status — EXACT / FUZZY_MATCH / MULTIPLE_MATCHES / '
            'ROMAN_NUMERAL_FIX / NO_MATCH\n'
            '  • all_candidates — All matches within threshold\n'
            '  • error_detail — Description of issues needing review\n\n'
            'The Matched Barangays output is always a temporary scratch '
            'layer, in a single run and in Batch Processing alike, so it '
            'loads straight into the project instead of being written to '
            'disk. A filtered PSGC layer for the target city/municipality '
            'is always generated and loaded alongside it.'
        )

    def createInstance(self):
        return JoinBarangayAttributes()