# ----------------------------------------------------------------------
# MBI Gaps / Overlaps / Disputed Areas Checker
# Last updated: 2026-09-14
# Version: v17
#
# Changelog:
#   v1 - Initial Gaps/Overlaps detection between LGU and PSA polygons.
#   v2 - Added Disputed Areas extraction based on 'boundary' field
#        ('Contested' vs 'Barangay').
#   v3 - Added lgu_bgy_name field to Disputed Areas output.
#   v4 - Changed mbi_status ValueMap dropdown options to
#        '1_Updated' / '2_Pending'.
#   v5 - Renamed output field 'map_uuid' to 'case_uuid'.
#   v6 - Added 'Disputed Areas Only' to the Analysis-to-Run dropdown
#        (now: Overlaps, Gaps, and Disputed Areas / Overlaps Only /
#        Gaps Only / Disputed Areas Only); Disputed Areas output
#        generation is now gated by run_mode instead of always running;
#        re-applied case_uuid rename on top of user's latest label edits.
#   v7 - Bug fix: Gaps/Overlaps detected nothing when only 1 polygon
#        layer was selected. Cause: native:mergevectorlayers behaves
#        unreliably with a single-layer input on some QGIS versions.
#        merge_layers() now skips the merge step and uses the single
#        refactored layer directly when only one polygon layer is
#        selected.
#   v8 - Merged the three separate output layers (Gaps, Overlaps,
#        Disputed Areas) into one combined output layer named
#        'ref_mbi_cases', distinguished by mbi_type. lgu_bgy_name is
#        now a base schema field (populated for Disputed records,
#        NULL for Gaps/Overlaps).
#   v9 - Bug fix: overlaps were silently dropped when the two overlapping
#        polygons belong to the SAME barangay (e.g. adjacent EAs inside
#        one barangay) or carry no barangay/city_mun attributes at all.
#        Cause: get_involved() grouped participants by barangay label, so
#        such a pair collapsed into a single entry and failed the
#        'len(involved) < 2' test. Overlap detection now groups by feature
#        (by_feature=True) so each polygon counts separately; Gap detection
#        keeps the original per-barangay grouping. Also corrected the
#        stale version string in the closing log message.
#   v10 - Fixed 'Analysis to Run' to 'Gaps, Overlaps, and Disputed'.
#         Removed selection choices (Overlaps Only, Gaps Only, Disputed
#         Areas Only); running all three analyses is now mandatory.
#   v11 - Added LGU-vs-PSA boundary precedence resolution, applied before
#         Gaps/Overlaps/Disputed detection: the LGU layer is treated as the
#         latest submission, so for any city_mun where at least one LGU
#         polygon exists, that city_mun's PSA polygon(s) are excluded and
#         only the LGU polygon(s) are used; city_mun with no LGU submission
#         at all still fall back to PSA. The resulting authoritative
#         boundary set is the sole input to the rest of the analysis, and
#         is also loaded into the project as its own layer, '2026_province_boundary',
#         so reviewers can inspect exactly which polygons were kept/dropped.
#   v12 - Bug fix: duplicate barangay polygons (same geocode, same source,
#         identical geometry — e.g. a barangay submitted twice, or the same
#         area present in more than one selected input layer) were passing
#         straight through into the boundary output. dedupe_same_source()
#         now removes them before precedence resolution runs; a barangay
#         legitimately split into multiple disjoint parts is unaffected
#         since each part has different geometry. Also renamed the boundary
#         output layer from 'ref_mbi_boundary' to '2026_province_boundary'.
#   v13 - Bug fix: v12's geometry-equality dedup missed duplicates whose
#         geometry differed slightly between submissions (e.g. re-digitized
#         vertices), so map_uuid still repeated in 2026_province_boundary.
#         dedupe_same_source() now keys primarily on map_uuid — a barangay's
#         PSGC-matched identifier (see update_metadata.py), unique per
#         barangay and NULL only for Contested features — dropping any
#         later feature that repeats an already-seen map_uuid regardless of
#         geometry. Features with no map_uuid still fall back to the v12
#         geocode + source + identical-geometry check.
#   v14 - normalize_source_labels() added, run right after boundary
#         precedence is resolved: any surviving polygon whose source is not
#         LGU (blank/NULL/other) is explicitly stamped 'source' = 'PSA'.
#         Runs on the same poly_layer that feeds both 2026_province_boundary
#         and polygon_infos, so ref_mbi_cases' source field picks up the
#         same explicit 'PSA' label wherever it applies.
#   v15 - Bug fix: barangays with an island or other disjoint piece were
#         losing that piece from the boundary. Cause: v13's dedup keyed on
#         map_uuid and dropped ANY repeat of an already-seen map_uuid with
#         no geometry check — but singleparts() explodes a multipart
#         barangay into several features that all carry the SAME map_uuid,
#         so every piece after the first was discarded as a "duplicate",
#         cutting real islands off the boundary. dedupe_same_source() now
#         keys on geocode + source (the PSGC geocode is the unique
#         identifier per barangay within a source) and only drops a feature
#         whose geometry is IDENTICAL to one already kept, so genuinely
#         distinct pieces always survive while true duplicate submissions
#         are still removed.
#   v16 - Bug fix: geocode repeated across several rows of
#         2026_province_boundary for any barangay with an islet, so the
#         output looked duplicated and de-duplicating it by hand deleted
#         half of that barangay's boundary. Cause: the pipeline ran
#         singleparts() FIRST, so every multipart barangay was already
#         exploded into one row per piece by the time the boundary was
#         resolved and published.
#         The boundary is now resolved on multipart data and published
#         before anything is exploded; singleparts() is applied afterwards
#         to a separate working copy that only Gaps/Overlaps/Disputed
#         detection sees, so detection behaviour is unchanged.
#         dedupe_same_source() is replaced by merge_by_geocode(), which
#         UNIONS every row sharing a geocode + source into one multipart
#         feature instead of dropping all but one. That is lossless in both
#         directions: duplicate submissions of the same area union back to
#         that area, and a barangay whose islet was stored as its own row
#         keeps the islet as a second part. geocode is therefore unique per
#         source in the published boundary, with no area lost.
#         Intermediate boundary layers are now declared MultiPolygon
#         (boundary_memory_layer()), since they carry multipart features.
#   v17 - Progress bar fix: the bar restarted from 0 once per sub-process
#         instead of filling once. Cause: every nested processing.run() was
#         handed this algorithm's own feedback, and each sub-algorithm
#         (refactorfields, mergevectorlayers, reprojectlayer, fixgeometries,
#         multiparttosingleparts, dissolve, deleteholes, difference) reports
#         its own 0-100% on it. Nested calls now get ChildFeedback, which
#         forwards log messages and cancellation but swallows setProgress,
#         so only this algorithm drives the bar. The sweep is also now
#         continuous end to end: boundary resolution reports 2-8, building
#         points/indexes 10-12, Disputed 15, Overlaps 20-55, Gaps 60-95
#         (previously the gap loop reported nothing and jumped straight to
#         100), and 100 is reached only after ref_mbi_cases is written.
#         Gap detection also honours Cancel now, as overlap detection did.
# ----------------------------------------------------------------------

__author__ = 'Geospatial Management Division'
__date__ = '2026-06-15'
__copyright__ = '(C) 2026, Geospatial Management Division'

import os
import uuid as _uuid
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingContext,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingParameterMultipleLayers,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsFeatureRequest,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsSpatialIndex,
    QgsWkbTypes,
    QgsEditorWidgetSetup,
    QgsEditFormConfig,
)
import processing


# ----------------------------------------------------------------------
# Post-processor: applies field editor widgets (dropdowns), QML styling,
# and read-only field locks to ref_mbi_cases after it is loaded into QGIS.
# ----------------------------------------------------------------------
class FieldWidgetPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """
    Applies QgsEditorWidgetSetup configurations, embeds categorized QML styling,
    and locks computed reference attributes as read-only on ref_mbi_cases.

    widget_configs: dict of  field_name -> QgsEditorWidgetSetup
    """
    instance_registry = []   # keep-alive so Python GC doesn't collect them

    def __init__(self, widget_configs: dict):
        super().__init__()
        self.widget_configs = widget_configs
        FieldWidgetPostProcessor.instance_registry.append(self)

    def postProcessLayer(self, layer, context, feedback):
        if layer is None or not layer.isValid():
            return

        # 1. Apply embedded QML style if available
        qml_names = ['ref_mbi_cases.qml', 'MBI Cases.qml']
        qml_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'qml styles')
        qml_path = None
        for qname in qml_names:
            cand = os.path.join(qml_dir, qname)
            if os.path.isfile(cand):
                qml_path = cand
                break

        if qml_path and os.path.isfile(qml_path):
            try:
                res = layer.loadNamedStyle(qml_path)
                success = res[1] if isinstance(res, tuple) else bool(res)
                if success:
                    if feedback:
                        feedback.pushInfo(f"Applied QML style: {os.path.basename(qml_path)}")
                else:
                    msg = res[0] if isinstance(res, tuple) else "loadNamedStyle returned false"
                    if feedback:
                        feedback.pushWarning(f"Notice: QML style load returned: {msg}")
            except Exception as e:
                if feedback:
                    feedback.pushWarning(f"Notice: Could not load QML style ({e})")

        # 2. Ensure field editor widget setups (ValueMap dropdowns, etc.) are applied
        for field_name, setup in self.widget_configs.items():
            idx = layer.fields().indexOf(field_name)
            if idx >= 0:
                layer.setEditorWidgetSetup(idx, setup)

        # 3. Configure field editability: lock reference fields as read-only to avoid accidental edits
        read_only_fields = [
            'case_uuid',
            'region',
            'province',
            'source',
            'mbi_level',
            'involved_areas',
            'involved_bgys',
            'count_involved_areas',
            'mbi_type',
            'num_bldg_pts',
            'mbi_remarks',
        ]
        editable_fields = [
            'geocode',
            'city_mun',
            'barangay',
            'mbi_status',
            'pso_remarks',
            'lgu_bgy_name',
        ]

        if hasattr(layer, 'editFormConfig'):
            form_config = layer.editFormConfig()
            if form_config is not None:
                for f_name in read_only_fields:
                    idx = layer.fields().indexOf(f_name)
                    if idx >= 0:
                        form_config.setReadOnly(idx, True)

                for f_name in editable_fields:
                    idx = layer.fields().indexOf(f_name)
                    if idx >= 0:
                        form_config.setReadOnly(idx, False)

                layer.setEditFormConfig(form_config)

        # 4. Ensure layer allows entering editing mode for the editable fields
        if hasattr(layer, 'setReadOnly'):
            layer.setReadOnly(False)

        # 5. Refresh layer symbology and redraw canvas
        if hasattr(layer, 'emitStyleChanged'):
            layer.emitStyleChanged()
        if hasattr(layer, 'triggerRepaint'):
            layer.triggerRepaint()


def make_mbi_status_setup():
    """ValueMap dropdown for mbi_status field."""
    return QgsEditorWidgetSetup('ValueMap', {
        'map': [
            {'1_Updated': '1_Updated'},
            {'2_Pending': '2_Pending'},
        ]
    })


def make_text_setup():
    """Plain text (TextEdit) widget — default, but explicit."""
    return QgsEditorWidgetSetup('TextEdit', {'IsMultiline': False, 'UseHtml': False})


class ChildFeedback(QgsProcessingFeedback):
    """
    Feedback handed to the nested processing.run() calls.

    Log messages and cancellation still reach the real feedback, but
    setProgress() is swallowed. Each nested algorithm (refactorfields,
    dissolve, difference, ...) reports its own 0-100%, so passing the real
    feedback down made the progress bar restart once per sub-process.
    Only this algorithm drives the bar now, as a single 0-100 run.
    """

    def __init__(self, parent):
        super().__init__()
        self._parent = parent

    def setProgress(self, progress):
        pass

    def isCanceled(self):
        return self._parent.isCanceled()

    def pushInfo(self, info):
        self._parent.pushInfo(info)

    def pushDebugInfo(self, info):
        self._parent.pushDebugInfo(info)

    def pushCommandInfo(self, info):
        self._parent.pushCommandInfo(info)

    def pushConsoleInfo(self, info):
        self._parent.pushConsoleInfo(info)

    def pushWarning(self, warning):
        self._parent.pushWarning(warning)

    def reportError(self, error, fatalError=False):
        self._parent.reportError(error, fatalError)


class RunAnalysisAlgorithm(QgsProcessingAlgorithm):

    INPUT1   = 'INPUT1'
    INPUT2   = 'INPUT2'
    RUN_MODE = 'RUN_MODE'

    def __init__(self):
        super().__init__()
        self._keep_alive = []

    def name(self):
        return 'run_analysis'

    def displayName(self):
        return 'Run Analysis'

    def group(self):
        return '1Map'

    def groupId(self):
        return '1map'

    def createInstance(self):
        return RunAnalysisAlgorithm()

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'run_analysis.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return (
            "<p>Detects boundary findings (gaps, overlaps, and disputed boundaries) "
            "of LGU polygon layers, written into a single combined output layer "
            "named <b>ref_mbi_cases</b>, distinguished by <i>mbi_type</i>.</p>"
            "<h3>Output: 2026_province_boundary</h3>"
            "<p>Before any detection runs: (1) every row sharing a <i>geocode</i> and "
            "<i>source</i> is merged into one multipart feature, so geocode is unique "
            "per source in the output. This covers both a barangay submitted twice "
            "(the rows overlap, so the union is that same area) and a barangay whose "
            "islet was stored as its own row (the rows are disjoint, so the islet is "
            "kept as a second part rather than discarded). "
            "(2) LGU vs PSA precedence is then resolved per <i>city_mun</i>: the LGU "
            "layer is treated as the latest submission, so wherever at least one LGU "
            "polygon exists for a city_mun, that city_mun's PSA polygon(s) are excluded "
            "and only the LGU polygon(s) are used. A city_mun with no LGU submission at "
            "all falls back to PSA.</p>"
            "<p>The resulting authoritative boundary is published as "
            "<b>2026_province_boundary</b> with multipart barangays intact — one row "
            "per geocode per source — so reviewers can inspect which polygons were "
            "kept or superseded, and so de-duplicating the table by geocode can never "
            "delete an islet. Gaps/Overlaps/Disputed detection below runs on a separate "
            "single-part working copy of that same boundary.</p>"
            "<h3>Output: ref_mbi_cases</h3>"
            "<ul>"
            "<li><b>Gaps</b> — Empty slivers between polygons. Disputed polygons are "
            "excluded from the dissolve, and their footprint is subtracted from the "
            "result, so a Disputed area never duplicates as a gap. "
            "<i>mbi_type</i> = <b>1_Gap</b>.</li>"
            "<li><b>Overlaps</b> — Intersecting polygon pairs, including two polygons "
            "of the same barangay (e.g. adjacent EAs). If either polygon is "
            "Disputed, <i>mbi_remarks</i> is set to "
            "<b>'For Review - Involves Disputed Area'</b>. "
            "<i>mbi_type</i> = <b>2_Overlap</b>.</li>"
            "<li><b>Disputed Areas</b> — LGU polygons tagged <i>boundary = Contested</i> "
            "(no confirmed PSA match). <i>mbi_type</i> = <b>3_Disputed</b>; "
            "<i>lgu_bgy_name</i> is populated (NULL for Gaps/Overlaps records).</li>"
            "</ul>"
            "<h3>Output Fields</h3>"
            "<ul>"
            "<li><b>case_uuid</b> — UUID per finding</li>"
            "<li><b>geocode / region / province / city_mun / barangay</b></li>"
            "<li><b>source</b> — LGU/PSA label (NULL for gaps)</li>"
            "<li><b>mbi_level</b> — Inter-Region / Inter-Province / "
            "Inter-City/Municipality / Inter-Barangay / Within-Barangay</li>"
            "<li><b>involved_areas</b> — Comma-separated geocodes</li>"
            "<li><b>involved_bgys</b> — Semicolon-separated barangay+city names</li>"
            "<li><b>count_involved_areas</b></li>"
            "<li><b>mbi_type</b> — 1_Gap / 2_Overlap / 3_Disputed</li>"
            "<li><b>num_bldg_pts</b></li>"
            "<li><b>mbi_status</b> — Dropdown: (blank) / 1_Updated / "
            "2_Pending</li>"
            "<li><b>mbi_remarks</b> — Auto-filled when an overlap involves a Disputed "
            "polygon; otherwise NULL</li>"
            "<li><b>pso_remarks</b> — Free-text field for manual PSO input</li>"
            "<li><b>lgu_bgy_name</b> — LGU-declared barangay name (populated for Disputed, NULL for Gaps/Overlaps)</li>"
            "</ul>"
            "<h3>Styling & Editing Constraints</h3>"
            "<p>The output layer is automatically styled with categorized symbology (1_Gap, 2_Overlap, 3_Disputed) "
            "and pre-configured with read-only locks on reference attributes (case_uuid, region, province, "
            "source, mbi_level, involved_areas, involved_bgys, count_involved_areas, mbi_type, num_bldg_pts, "
            "and mbi_remarks). The geocode, city_mun, barangay, mbi_status, pso_remarks, and lgu_bgy_name "
            "fields remain fully editable for reviewer corrections.</p>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT1,
                'Select Polygon Layer(s)',
                QgsProcessing.TypeVectorPolygon
            )
        )
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT2,
                'Select Building Point Layer(s)',
                QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback: QgsProcessingFeedback):
        self._keep_alive = []

        # Every nested processing.run() gets this instead of `feedback`, so
        # the progress bar is driven only by this algorithm — one 0-100 run
        # instead of restarting for each sub-process. Keep a reference: the
        # C++ side does not own it, so a local would be collected mid-run.
        child_fb = ChildFeedback(feedback)
        self._child_feedback = child_fb

        def keep_layer(layer):
            if layer is not None:
                self._keep_alive.append(layer)
            return layer

        polygon_layers = self.parameterAsLayerList(parameters, self.INPUT1, context)
        building_layers = self.parameterAsLayerList(parameters, self.INPUT2, context)

        if not polygon_layers:
            raise QgsProcessingException("PSA and LGU polygon layer(s) must be selected.")
        if not building_layers:
            raise QgsProcessingException("Building point layer(s) must be selected.")

        # Mandatory analysis: Gaps, Overlaps, and Disputed always run
        run_overlaps = True
        run_gaps     = True
        run_disputed = True

        target_crs       = QgsCoordinateReferenceSystem("EPSG:3857")
        output_crs       = QgsCoordinateReferenceSystem("EPSG:4326")
        transform_to_out = QgsCoordinateTransform(target_crs, output_crs, QgsProject.instance())

        feedback.pushInfo("Processing... Mode: Gaps, Overlaps, and Disputed")

        # ------------------------------------------------------------------
        # Shared editor widget configs applied to every output layer
        # ------------------------------------------------------------------
        widget_configs = {
            'mbi_status':  make_mbi_status_setup(),
            'pso_remarks': make_text_setup(),
            'mbi_remarks': make_text_setup(),
        }

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------
        def get_attr(feat, names):
            if isinstance(names, str):
                names = [names]
            lower_map = {f.name().lower(): f.name() for f in feat.fields()}
            for name in names:
                real = lower_map.get(name.lower())
                if real:
                    try:
                        v = feat[real]
                        if v is not None:
                            return v
                    except Exception:
                        pass
            return None

        def txt(v):
            if v is None:
                return ''
            s = str(v).strip()
            if s.upper() == 'NULL':
                return ''
            return s

        def safe_area(geom):
            if geom is None or geom.isEmpty():
                return 0.0
            try:
                return float(geom.area())
            except Exception:
                return 0.0

        def label_from_info(info):
            brgy = txt(info.get('barangay'))
            city = txt(info.get('city_mun'))
            if brgy and city:
                return f"{brgy}, {city}"
            return brgy or city or 'Unknown'

        def refactor_layer(layer):
            mapping = []
            for f in layer.fields():
                mapping.append({
                    'alias': '', 'comment': '',
                    'expression': f'"{f.name()}"',
                    'length': f.length(), 'name': f.name(),
                    'precision': f.precision(), 'sub_type': 0,
                    'type': f.type(), 'type_name': f.typeName()
                })
            return keep_layer(processing.run(
                'native:refactorfields',
                {'INPUT': layer, 'FIELDS_MAPPING': mapping, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

        def merge_layers(layers, crs):
            refs = [refactor_layer(l) for l in layers]
            # native:mergevectorlayers is unreliable (empty/odd output) on
            # some QGIS versions when given a single-layer list. When only
            # one polygon layer is selected, skip the merge step entirely
            # and use the refactored layer directly — this was the cause
            # of Gaps/Overlaps silently detecting nothing with 1 layer.
            if len(refs) == 1:
                return refs[0]
            return keep_layer(processing.run(
                'native:mergevectorlayers',
                {'LAYERS': refs, 'CRS': crs, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

        def reproject_fix(layer):
            reproj = keep_layer(processing.run(
                'native:reprojectlayer',
                {'INPUT': layer, 'TARGET_CRS': target_crs,
                 'CONVERT_CURVED_GEOMETRIES': False, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])
            return keep_layer(processing.run(
                'native:fixgeometries',
                {'INPUT': reproj, 'METHOD': 1, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

        def singleparts(layer):
            single = keep_layer(processing.run(
                'native:multiparttosingleparts',
                {'INPUT': layer, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])
            return keep_layer(processing.run(
                'native:fixgeometries',
                {'INPUT': single, 'METHOD': 1, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

        def boundary_memory_layer(src_layer, name):
            """
            Empty memory layer mirroring src_layer's CRS and fields.

            Declared MultiPolygon on purpose: the boundary pipeline runs
            BEFORE multiparttosingleparts, so a barangay with an islet is
            still one feature holding several parts. A 'Polygon' layer risks
            losing those extra parts on the way through.
            """
            layer = QgsVectorLayer(
                f'MultiPolygon?crs={src_layer.crs().authid()}', name, 'memory'
            )
            layer.dataProvider().addAttributes(src_layer.fields().toList())
            layer.updateFields()
            return layer

        def merge_by_geocode(layer):
            """
            Collapses every feature sharing a geocode+source into ONE
            multipart feature, so geocode is unique in the published
            boundary and a manual de-duplication can never cost a barangay
            part of its area.

            Rows share a geocode+source for two very different reasons, and
            unioning them is correct for both:
              - the same barangay submitted twice (the rows overlap) — the
                union is that same area, so nothing is double-counted, even
                when the two submissions were digitized slightly
                differently;
              - a barangay whose islet was stored as its own row (the rows
                are disjoint) — the union keeps both as parts of one
                multipolygon, instead of discarding the islet as a
                "duplicate".

            source stays in the key because LGU and PSA both carry the same
            geocode for the same barangay; merging those here would pre-empt
            resolve_boundary_precedence(), which is what decides which of
            the two actually wins.
            """
            order       = []
            grouped     = {}
            passthrough = []

            for feat in layer.getFeatures():
                geocode = txt(get_attr(feat, ['geocode', 'GEOCODE']))
                source  = txt(get_attr(feat, ['source', 'SOURCE', 'Source'])).upper()
                if not geocode:
                    # Nothing to key on — keep the row exactly as it is.
                    passthrough.append(feat)
                    continue
                key = (geocode, source)
                if key not in grouped:
                    grouped[key] = {'feat': feat, 'geoms': []}
                    order.append(key)
                grouped[key]['geoms'].append(QgsGeometry(feat.geometry()))

            out_feats  = []
            merged_cnt = 0
            for key in order:
                entry = grouped[key]
                geoms = entry['geoms']
                feat  = QgsFeature(entry['feat'])
                if len(geoms) > 1:
                    combined = geoms[0]
                    for g in geoms[1:]:
                        try:
                            combined = combined.combine(g)
                        except Exception:
                            pass
                    if combined is not None and not combined.isEmpty():
                        feat.setGeometry(combined)
                    merged_cnt += len(geoms) - 1
                out_feats.append(feat)
            out_feats.extend(passthrough)

            result = boundary_memory_layer(layer, 'merged_by_geocode')
            result.dataProvider().addFeatures(out_feats)
            result.updateExtents()

            feedback.pushInfo(
                f"  {merged_cnt} extra row(s) merged into their geocode; "
                f"{len(out_feats)} barangay feature(s) remain, one per "
                f"geocode + source."
            )
            return keep_layer(result)

        def resolve_boundary_precedence(layer):
            """
            Keeps one authoritative boundary per city_mun before any
            Gap/Overlap/Disputed detection runs. The LGU layer is treated as
            the latest submission: wherever at least one LGU polygon exists
            for a city_mun, that city_mun's PSA polygon(s) are excluded and
            only the LGU polygon(s) are kept; a city_mun with no LGU
            submission at all falls back to PSA.
            """
            def feat_city_mun(feat):
                return txt(get_attr(feat, ['city_mun', 'CITY_MUN', 'city/mun']))

            def feat_is_lgu(feat):
                return 'LGU' in txt(get_attr(feat, ['source', 'SOURCE', 'Source'])).upper()

            lgu_city_muns = {feat_city_mun(f) for f in layer.getFeatures() if feat_is_lgu(f)}

            kept_feats  = []
            dropped_cnt = 0
            for feat in layer.getFeatures():
                if feat_city_mun(feat) in lgu_city_muns and not feat_is_lgu(feat):
                    dropped_cnt += 1
                    continue
                kept_feats.append(feat)

            result = boundary_memory_layer(layer, 'precedence_resolved')
            result.dataProvider().addFeatures(kept_feats)
            result.updateExtents()

            feedback.pushInfo(
                f"  {len(lgu_city_muns)} city_mun(s) have an LGU submission; "
                f"{dropped_cnt} superseded PSA polygon(s) excluded; "
                f"{len(kept_feats)} polygon(s) retained as the authoritative boundary."
            )
            return keep_layer(result)

        def normalize_source_labels(layer):
            """
            Explicitly labels every non-LGU polygon's source as 'PSA' — this
            runs after resolve_boundary_precedence, so it only touches
            polygons that survived: either from a city_mun with no LGU
            submission (falls back to PSA), or an LGU-covered city_mun's
            own LGU polygon (left untouched, since it already contains
            'LGU'). Any blank/NULL/other source value on a non-LGU feature
            is overwritten with 'PSA' so downstream case_uuid records
            (ref_mbi_cases) inherit a clean, explicit label too.
            """
            src_idx = layer.fields().indexOf('source')
            if src_idx < 0:
                for name in ('SOURCE', 'Source'):
                    src_idx = layer.fields().indexOf(name)
                    if src_idx >= 0:
                        break

            result = boundary_memory_layer(layer, 'normalized')

            out_feats  = []
            filled_cnt = 0
            for feat in layer.getFeatures():
                is_lgu = 'LGU' in txt(get_attr(feat, ['source', 'SOURCE', 'Source'])).upper()
                new_feat = QgsFeature(feat)
                if src_idx >= 0 and not is_lgu:
                    if txt(new_feat.attribute(src_idx)).upper() != 'PSA':
                        filled_cnt += 1
                    new_feat.setAttribute(src_idx, 'PSA')
                out_feats.append(new_feat)

            result.dataProvider().addFeatures(out_feats)
            result.updateExtents()

            feedback.pushInfo(f"  {filled_cnt} non-LGU polygon(s) labeled source='PSA'.")
            return keep_layer(result)

        def load_plain_layer(layer, name):
            if layer is None:
                return None
            layer.setName(name)
            details = QgsProcessingContext.LayerDetails(name, context.project(), 'OUTPUT')
            context.temporaryLayerStore().addMapLayer(layer)
            context.addLayerToLoadOnCompletion(layer.id(), details)
            return layer.id()

        # ------------------------------------------------------------------
        # Output layer schema
        # Fields: case_uuid, geocode, region, province, city_mun, barangay,
        #         source, mbi_level, involved_areas, involved_bgys,
        #         count_involved_areas, mbi_type, num_bldg_pts,
        #         mbi_status, mbi_remarks, pso_remarks
        # ------------------------------------------------------------------
        def output_layer(name, extra_fields=None):
            fields = QgsFields()
            fields.append(QgsField('case_uuid',             QVariant.String))
            fields.append(QgsField('geocode',              QVariant.String))
            fields.append(QgsField('region',               QVariant.String))
            fields.append(QgsField('province',             QVariant.String))
            fields.append(QgsField('city_mun',             QVariant.String))
            fields.append(QgsField('barangay',             QVariant.String))
            fields.append(QgsField('source',               QVariant.String))
            fields.append(QgsField('mbi_level',            QVariant.String))
            fields.append(QgsField('involved_areas',       QVariant.String))
            fields.append(QgsField('involved_bgys',        QVariant.String))
            fields.append(QgsField('count_involved_areas', QVariant.Int))
            fields.append(QgsField('mbi_type',             QVariant.String))
            fields.append(QgsField('num_bldg_pts',         QVariant.Int))
            fields.append(QgsField('mbi_status',           QVariant.String))
            fields.append(QgsField('mbi_remarks',          QVariant.String))
            fields.append(QgsField('pso_remarks',          QVariant.String))
            fields.append(QgsField('lgu_bgy_name',         QVariant.String))
            # Any further layer-specific extra fields appended at the end.
            for f in (extra_fields or []):
                fields.append(f)
            layer = QgsVectorLayer('Polygon?crs=EPSG:4326', name, 'memory')
            layer.dataProvider().addAttributes(fields)
            layer.updateFields()
            return keep_layer(layer)

        def load_layer(layer, name):
            if layer is None:
                return None
            layer.setName(name)
            details = QgsProcessingContext.LayerDetails(name, context.project(), 'OUTPUT')

            # Attach the post-processor so dropdowns are applied after load
            pp = FieldWidgetPostProcessor(widget_configs)
            details.setPostProcessor(pp)

            context.temporaryLayerStore().addMapLayer(layer)
            context.addLayerToLoadOnCompletion(layer.id(), details)
            return layer.id()

        results = {}

        # ------------------------------------------------------------------
        # Prepare input layers
        # ------------------------------------------------------------------
        feedback.pushInfo("Merging and fixing polygon layers...")
        feedback.setProgress(2)
        merged_poly = merge_layers(polygon_layers, polygon_layers[0].crs())
        fixed_poly  = reproject_fix(merged_poly)

        # The boundary is resolved on MULTIPART data, before anything is
        # exploded into single parts. A barangay with an islet therefore
        # stays ONE feature with several parts, so geocode remains unique in
        # 2026_province_boundary — exploding first produced several rows
        # sharing a geocode, which read as duplicates and cost the barangay
        # half its boundary when de-duplicated by hand.
        feedback.pushInfo("Merging rows that share a geocode...")
        feedback.setProgress(4)
        boundary_layer = merge_by_geocode(fixed_poly)

        feedback.pushInfo("Resolving LGU vs PSA boundary precedence by city_mun...")
        feedback.setProgress(6)
        boundary_layer = resolve_boundary_precedence(boundary_layer)

        feedback.pushInfo("Labeling PSA-sourced polygons...")
        feedback.setProgress(7)
        boundary_layer = normalize_source_labels(boundary_layer)

        boundary_display = keep_layer(processing.run(
            'native:reprojectlayer',
            {'INPUT': boundary_layer, 'TARGET_CRS': output_crs,
             'CONVERT_CURVED_GEOMETRIES': False, 'OUTPUT': 'memory:'},
            context=context, feedback=child_fb
        )['OUTPUT'])
        results['OUTPUT_BOUNDARY'] = load_plain_layer(boundary_display, '2026_province_boundary')

        # Detection needs one geometry per polygon, so the exploded copy is
        # derived from the resolved boundary and used ONLY from here down —
        # it never reaches the published layer above.
        feedback.setProgress(8)
        poly_layer = singleparts(boundary_layer)

        feedback.pushInfo("Merging and fixing building point layers...")
        feedback.setProgress(10)
        merged_bldg = merge_layers(building_layers, building_layers[0].crs())
        bldg_layer  = reproject_fix(merged_bldg)

        # ------------------------------------------------------------------
        # Build caches and spatial indexes
        # ------------------------------------------------------------------
        feedback.pushInfo("Building spatial indexes...")
        feedback.setProgress(12)

        polygon_infos = {}
        polygon_index = QgsSpatialIndex()

        for feat in poly_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            info = {
                'fid':        feat.id(),
                'geometry':   QgsGeometry(geom),
                'whole_area': safe_area(geom),
                'geocode':    get_attr(feat, ['geocode',  'GEOCODE']),
                'region':     get_attr(feat, ['region',   'REGION',   'Region']),
                'province':   get_attr(feat, ['province', 'PROVINCE', 'Province']),
                'city_mun':   get_attr(feat, ['city_mun', 'CITY_MUN', 'city/mun']),
                'barangay':   get_attr(feat, ['barangay', 'BARANGAY', 'brgy', 'BRGY']),
                'source':     get_attr(feat, ['source',   'SOURCE',   'Source']),
                'boundary':   get_attr(feat, ['boundary', 'BOUNDARY', 'Boundary']),
                'lgu_bgy_name': get_attr(feat, ['lgu_bgy_name', 'LGU_BGY_NAME', 'lgu_bgy_nam']),
            }
            polygon_infos[feat.id()] = info
            polygon_index.addFeature(feat)

        bldg_geoms = {}
        bldg_index = QgsSpatialIndex()
        for feat in bldg_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            bldg_geoms[feat.id()] = QgsGeometry(geom)
            bldg_index.addFeature(feat)

        if not polygon_infos:
            raise QgsProcessingException("No valid polygon features found.")

        # Partition fids: Disputed (boundary = 'Contested') vs normal
        disputed_fids      = {
            fid for fid, info in polygon_infos.items()
            if txt(info.get('boundary')).strip().lower() == 'contested'
        }
        non_disputed_fids  = set(polygon_infos.keys()) - disputed_fids

        feedback.pushInfo(
            f"  {len(disputed_fids)} Disputed polygon(s) found; "
            f"{len(non_disputed_fids)} non-Disputed polygon(s)."
        )

        # ------------------------------------------------------------------
        # Spatial helpers
        # ------------------------------------------------------------------
        def count_points(poly_geom):
            cnt = 0
            for fid in bldg_index.intersects(poly_geom.boundingBox()):
                pt = bldg_geoms.get(fid)
                if pt is None or pt.isEmpty():
                    continue
                try:
                    if poly_geom.intersects(pt) or poly_geom.contains(pt):
                        cnt += 1
                except Exception:
                    pass
            return cnt

        def get_involved(finding_geom, gap_mode=False, by_feature=False):
            """
            List the polygons that take part in a finding.

            by_feature=False groups them by barangay label, so one barangay
            counts once no matter how many of its polygons touch the finding.
            by_feature=True keeps every polygon as its own entry — required for
            overlaps, where two polygons of the SAME barangay (e.g. adjacent
            EAs, or polygons with no barangay attributes at all) share a label
            and would otherwise collapse into a single entry and be discarded
            by the 'len(involved) < 2' test.
            """
            search_geom = finding_geom.buffer(0.50, 5) if gap_mode else finding_geom
            grouped = {}
            for fid in polygon_index.intersects(search_geom.boundingBox()):
                info = polygon_infos.get(fid)
                if not info:
                    continue
                poly_geom = info['geometry']
                try:
                    if gap_mode:
                        if not search_geom.intersects(poly_geom):
                            continue
                        covered = 0.0
                    else:
                        if not finding_geom.intersects(poly_geom):
                            continue
                        inter   = finding_geom.intersection(poly_geom)
                        covered = safe_area(inter)
                        if covered <= 0.01:
                            continue
                except Exception:
                    continue
                label = label_from_info(info)
                key   = fid if by_feature else label
                if key not in grouped:
                    grouped[key] = {'info': info, 'label': label, 'covered_area': 0.0}
                grouped[key]['covered_area'] += covered

            if gap_mode and grouped:
                share = safe_area(finding_geom) / len(grouped)
                for key in grouped:
                    grouped[key]['covered_area'] = share

            out = [
                {'label': data['label'], 'info': data['info'],
                 'covered_area': data['covered_area']}
                for data in grouped.values()
            ]
            out.sort(key=lambda x: x['label'])
            return out

        def derive_mbi_level(involved):
            regions   = set(txt(x['info'].get('region'))   for x in involved)
            provinces = set(txt(x['info'].get('province'))  for x in involved)
            cities    = set(txt(x['info'].get('city_mun'))  for x in involved)
            brgys     = set(txt(x['info'].get('barangay'))  for x in involved)
            if len(regions)   > 1: return '1_Inter-Region'
            if len(provinces) > 1: return '2_Inter-Province'
            if len(cities)    > 1: return '3_Inter-City/Municipality'
            if len(brgys)     > 1: return '4_Inter-Barangay'
            return '5_Within-Barangay'

        def choose_overlap_reference(info1, info2):
            s1 = txt(info1.get('source')).upper()
            s2 = txt(info2.get('source')).upper()
            if 'LGU' in s1 and 'PSA' in s2: return info1
            if 'LGU' in s2 and 'PSA' in s1: return info2
            if s1 and not s2: return info1
            if s2 and not s1: return info2
            return info2

        def involves_disputed(involved):
            """Return True if any feature in the involved list is Disputed."""
            return any(
                txt(x['info'].get('boundary')).strip().lower() == 'contested'
                for x in involved
            )

        def build_feature(geom_3857, involved, kind, out_fields,
                          reference_info=None, map_uuid=None,
                          lgu_bgy_name=None, extra_attrs=None):
            """
            Build a single QgsFeature for the output layer.

            kind:
                'Overlap'  -> mbi_type 2_Overlap
                              mbi_remarks flagged if any involved is Disputed
                'Gap'      -> mbi_type 1_Gap
                'Disputed' -> mbi_type 3_Disputed
            """
            if not involved:
                return None

            geom_out = QgsGeometry(geom_3857)
            try:
                geom_out.transform(transform_to_out)
            except Exception:
                pass

            ref = (reference_info if reference_info is not None
                   else max(involved, key=lambda x: x['covered_area'])['info'])

            # --- mbi_type ---
            if kind == 'Gap':
                mbi_type    = '1_Gap'
                source_val  = txt(ref.get('source')) or None
                mbi_remarks = None

            elif kind == 'Disputed':
                mbi_type    = '3_Disputed'
                source_val  = txt(ref.get('source')) or None
                mbi_remarks = None

            else:
                # Overlap — mbi_type is now a fixed label; the
                # minor/major/full mismatch-percentage computation has
                # been removed since it is no longer needed.
                mbi_type   = '2_Overlap'
                source_val = txt(ref.get('source')) or None

                # Flag in mbi_remarks if any involved polygon is Disputed
                mbi_remarks = (
                    'For Review - Involves Disputed Area'
                    if involves_disputed(involved) else None
                )

            involved_areas = ','.join(txt(x['info'].get('geocode')) for x in involved)
            involved_bgys  = ';'.join(x['label'] for x in involved)
            count_inv      = len(involved)
            mbi_level      = derive_mbi_level(involved)
            bldg_count     = count_points(geom_3857)
            uuid_val       = map_uuid if map_uuid else str(_uuid.uuid4())

            feat = QgsFeature(out_fields)
            feat.setGeometry(geom_out)
            feat.setAttributes([
                uuid_val,                    # case_uuid
                txt(ref.get('geocode')),     # geocode
                txt(ref.get('region')),      # region
                txt(ref.get('province')),    # province
                txt(ref.get('city_mun')),    # city_mun
                txt(ref.get('barangay')),    # barangay
                source_val,                  # source
                mbi_level,                   # mbi_level
                involved_areas,              # involved_areas
                involved_bgys,               # involved_bgys
                count_inv,                   # count_involved_areas
                mbi_type,                    # mbi_type
                bldg_count,                  # num_bldg_pts
                None,                        # mbi_status  — NULL (user fills via dropdown)
                mbi_remarks,                 # mbi_remarks — auto-flagged or NULL
                None,                        # pso_remarks — NULL (free-text, user fills)
                lgu_bgy_name,                # lgu_bgy_name — set for Disputed, NULL otherwise
            ] + list(extra_attrs or []))
            return feat

        all_feats = []

        out_layer  = output_layer('ref_mbi_cases')
        out_fields = out_layer.fields()

        # ==================================================================
        # DISPUTED AREAS
        # Runs when run_mode is 'Overlaps, Gaps, and Disputed Areas' or
        # 'Disputed Areas Only'. (disputed_fids/non_disputed_fids above are
        # still always computed since Gaps/Overlaps rely on them.)
        # Polygons with boundary = 'Contested' -> mbi_type = '3_Disputed'
        # ==================================================================
        if run_disputed:
            feedback.pushInfo("Extracting Disputed Areas...")
            feedback.setProgress(15)

            disp_count = 0
            for fid in disputed_fids:
                info = polygon_infos[fid]
                geom = info['geometry']
                if geom is None or geom.isEmpty():
                    continue

                self_involved = [{
                    'label':        label_from_info(info),
                    'info':         info,
                    'covered_area': info['whole_area'],
                }]
                lgu_bgy_val = txt(info.get('lgu_bgy_name')) or label_from_info(info)
                out_feat = build_feature(
                    geom, self_involved, 'Disputed', out_fields,
                    reference_info=info, lgu_bgy_name=lgu_bgy_val
                )
                if out_feat:
                    all_feats.append(out_feat)
                    disp_count += 1

            feedback.pushInfo(f"  {disp_count} Disputed feature(s) prepared.")

        # ==================================================================
        # OVERLAP DETECTION
        # Scans ALL polygons (including Disputed) so that overlaps between a
        # matched Barangay and a Disputed polygon are captured.
        # Participants are collected per FEATURE (by_feature=True) so that an
        # overlap between two polygons of the same barangay — adjacent EAs,
        # or polygons with no barangay attributes — is still reported.
        # mbi_remarks is auto-set inside build_feature when involved contains
        # a Disputed polygon.
        # ==================================================================
        if run_overlaps:
            feedback.pushInfo("Detecting overlaps...")
            feedback.setProgress(20)

            ovl_count = 0

            checked_pairs = set()
            ids   = list(polygon_infos.keys())
            total = len(ids)

            for i, fid1 in enumerate(ids):
                if feedback.isCanceled():
                    return {}

                info1 = polygon_infos[fid1]
                geom1 = info1['geometry']

                for fid2 in polygon_index.intersects(geom1.boundingBox()):
                    if fid1 == fid2:
                        continue
                    pair_key = tuple(sorted((fid1, fid2)))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    info2 = polygon_infos.get(fid2)
                    if not info2:
                        continue
                    geom2 = info2['geometry']

                    try:
                        if not geom1.intersects(geom2):
                            continue
                        inter = geom1.intersection(geom2)
                        if inter is None or inter.isEmpty():
                            continue

                        parts = []
                        if QgsWkbTypes.geometryType(inter.wkbType()) == QgsWkbTypes.PolygonGeometry:
                            parts = inter.asGeometryCollection() if inter.isMultipart() else [inter]
                        elif inter.isMultipart():
                            parts = [
                                p for p in inter.asGeometryCollection()
                                if QgsWkbTypes.geometryType(p.wkbType()) == QgsWkbTypes.PolygonGeometry
                            ]

                        for part in parts:
                            if part is None or part.isEmpty():
                                continue
                            if safe_area(part) <= 0.10:
                                continue

                            involved = get_involved(part, gap_mode=False, by_feature=True)
                            if len(involved) < 2:
                                continue

                            ref_for_output = choose_overlap_reference(info1, info2)
                            out_feat = build_feature(
                                part, involved, 'Overlap', out_fields,
                                reference_info=ref_for_output
                            )
                            if out_feat:
                                all_feats.append(out_feat)
                                ovl_count += 1

                    except Exception:
                        continue

                if total:
                    feedback.setProgress(20 + int((i / total) * 35))

            feedback.pushInfo(f"  {ovl_count} overlap feature(s) prepared.")
            feedback.setProgress(55)

        # ==================================================================
        # GAP DETECTION
        # Disputed polygons are EXCLUDED from the dissolve so their footprint
        # also registers as a geographic gap — complementing the Disputed
        # Areas records.
        # ==================================================================
        if run_gaps:
            feedback.pushInfo(
                "Detecting gaps (Disputed polygons excluded from dissolve)..."
            )
            feedback.setProgress(60)

            # Build a filtered memory layer with only non-Disputed polygons
            non_disp_layer = QgsVectorLayer(
                f'Polygon?crs={target_crs.authid()}', 'non_disputed', 'memory'
            )
            non_disp_layer.dataProvider().addAttributes(poly_layer.fields().toList())
            non_disp_layer.updateFields()
            non_disp_feats = [
                f for f in poly_layer.getFeatures()
                if f.id() in non_disputed_fids
            ]
            non_disp_layer.dataProvider().addFeatures(non_disp_feats)
            non_disp_layer.updateExtents()
            keep_layer(non_disp_layer)

            dissolved = keep_layer(processing.run(
                'native:dissolve',
                {'INPUT': non_disp_layer, 'FIELD': [],
                 'SEPARATE_DISJOINT': False, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

            no_holes = keep_layer(processing.run(
                'native:deleteholes',
                {'INPUT': dissolved, 'MIN_AREA': 0, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

            cleaned = keep_layer(processing.run(
                'native:dissolve',
                {'INPUT': no_holes, 'FIELD': [],
                 'SEPARATE_DISJOINT': False, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

            gap_diff = keep_layer(processing.run(
                'native:difference',
                {'INPUT': cleaned, 'OVERLAY': dissolved,
                 'GRID_SIZE': None, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

            gap_single = keep_layer(processing.run(
                'native:multiparttosingleparts',
                {'INPUT': gap_diff, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

            gap_fixed = keep_layer(processing.run(
                'native:fixgeometries',
                {'INPUT': gap_single, 'METHOD': 1, 'OUTPUT': 'memory:'},
                context=context, feedback=child_fb
            )['OUTPUT'])

            gap_count = 0

            # Build a unified EPSG:3857 geometry of all Disputed polygons so
            # their footprint can be subtracted from gap geometries — preventing
            # duplicate coverage between Gaps and Disputed Areas records.
            # NOTE: polygon_infos geometries are stored in EPSG:3857 (target_crs),
            # which matches the gap_fixed layer CRS — so NO transform is applied here.
            disputed_geom_union = None
            for fid in disputed_fids:
                info = polygon_infos[fid]
                d_geom = info['geometry']
                if d_geom is None or d_geom.isEmpty():
                    continue
                d_geom_3857 = QgsGeometry(d_geom)   # already in EPSG:3857
                if disputed_geom_union is None:
                    disputed_geom_union = d_geom_3857
                else:
                    disputed_geom_union = disputed_geom_union.combine(d_geom_3857)

            gap_total = gap_fixed.featureCount()
            for g_i, feat in enumerate(gap_fixed.getFeatures()):
                if feedback.isCanceled():
                    return {}
                if gap_total:
                    feedback.setProgress(60 + int((g_i / gap_total) * 35))

                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                if safe_area(geom) <= 0.10:
                    continue

                # Subtract Disputed polygon footprints from this gap geometry
                # so Gaps and Disputed Areas records do not overlap.
                if disputed_geom_union is not None and not disputed_geom_union.isEmpty():
                    try:
                        geom = geom.difference(disputed_geom_union)
                        if geom is None or geom.isEmpty():
                            continue
                    except Exception:
                        pass

                # Explode multipart results from the subtraction into single parts
                parts = geom.asGeometryCollection() if geom.isMultipart() else [geom]

                for part in parts:
                    if part is None or part.isEmpty():
                        continue
                    if safe_area(part) <= 0.10:
                        continue

                    involved = get_involved(part, gap_mode=True)
                    if not involved:
                        continue

                    out_feat = build_feature(part, involved, 'Gap', out_fields)
                    if out_feat:
                        all_feats.append(out_feat)
                        gap_count += 1

            feedback.pushInfo(f"  {gap_count} gap feature(s) prepared.")
            feedback.setProgress(95)

        # ==================================================================
        # WRITE COMBINED OUTPUT — 'ref_mbi_cases'
        # Gaps, Overlaps, and Disputed Areas are written into a single
        # output layer/table (distinguished by the mbi_type field).
        # ==================================================================
        if all_feats:
            out_layer.dataProvider().addFeatures(all_feats)
            out_layer.updateExtents()
            results['OUTPUT'] = load_layer(out_layer, 'ref_mbi_cases')
            feedback.pushInfo(f"  {len(all_feats)} total feature(s) written to ref_mbi_cases.")
        else:
            feedback.pushInfo("No Gap/Overlap/Disputed features found.")
            results['OUTPUT'] = None

        feedback.setProgress(100)
        feedback.pushInfo("Finished LGU vs PSA Boundary Gap and Overlap Checker v17.")
        return results


# Backwards-compatible alias
GapsOverlaps = RunAnalysisAlgorithm
