import os
import re

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingLayerPostProcessorInterface,
    QgsExpression,
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsFillSymbol,
    QgsSingleSymbolRenderer,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings,
)


# Only a field literally named "Geocode" (any case) is auto-detected --
# other spellings/codes (PSGC, brgy_code, etc.) are not guessed, so the
# user is expected to pick those explicitly when auto-detection fails.
GEOCODE_FIELD_HINTS = ["geocode"]


def guess_geocode_field(field_names):
    """Return the field name if one is literally named "Geocode" (case
    insensitive), or None if no such field exists. Tries an exact match
    first, then falls back to a substring match so e.g. "Geocode_10"
    still gets picked up."""
    lower_to_actual = {n.lower(): n for n in field_names}
    for hint in GEOCODE_FIELD_HINTS:
        if hint in lower_to_actual:
            return lower_to_actual[hint]
    for hint in GEOCODE_FIELD_HINTS:
        for lower_name, actual_name in lower_to_actual.items():
            if hint in lower_name:
                return actual_name
    return None


def extract_code(layer_name):
    """Pull the leading pppmm-style code off a layer name like
    "000102_LGU" or "00102_PSA_Boundary" -> "000102" / "00102".
    Falls back to a leading run of digits, and finally to the whole
    name if no code-like prefix is found."""
    if not layer_name:
        return ""
    m = re.match(r"^(.*?)_(PSA|LGU)\b", layer_name, re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.match(r"^(\d+)", layer_name)
    if m2:
        return m2.group(1)
    return layer_name


def style_boundary_outline(layer, color):
    """Style a polygon layer as a transparent-fill, colored-outline
    boundary -- used to tell Matched_PSA (green) and Matched_LGU (blue)
    apart on the map at a glance."""
    symbol = QgsFillSymbol.createSimple({
        "color": "0,0,0,0",       # transparent fill
        "outline_color": color,
        "outline_width": "0.6",
        "outline_width_unit": "MM",
    })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def label_by_field(layer, field_name, source_suffix=None):
    """Turn on map labels for a polygon layer, showing the value of
    field_name for each feature in bold white text with a dark halo so
    it stays readable over any fill color or basemap. The field is
    matched case-insensitively (source data may store it as "barangay",
    "Barangay", "BARANGAY", etc.). Does nothing (and returns False) if
    the layer doesn't actually have that field, so a missing "barangay"
    column on the source data doesn't break the rest of the run.

    When source_suffix is given (e.g. "PSA" or "LGU"), it is appended in
    parentheses -- "Poblacion (PSA)" -- so the two overlaid, same-named
    barangay labels from the PSA and LGU layers can be told apart on the
    map at a glance instead of reading as duplicate text.
    """
    lower_to_actual = {f.name().lower(): f.name() for f in layer.fields()}
    actual_field_name = lower_to_actual.get(field_name.lower())
    if actual_field_name is None:
        return False
    field_name = actual_field_name

    text_format = QgsTextFormat()
    text_format.setColor(QColor(255, 255, 255))  # white text
    font = text_format.font()
    font.setBold(True)
    font.setPointSize(10)
    text_format.setFont(font)

    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(1.0)
    buffer_settings.setColor(QColor(0, 0, 0))  # dark halo for contrast
    text_format.setBuffer(buffer_settings)

    settings = QgsPalLayerSettings()
    if source_suffix:
        settings.fieldName = "{} || {}".format(
            QgsExpression.quotedColumnRef(field_name),
            QgsExpression.quotedString(" ({})".format(source_suffix)),
        )
        settings.isExpression = True
    else:
        settings.fieldName = field_name
    settings.enabled = True
    settings.setFormat(text_format)

    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    return True


def first8(value):
    """First 8 characters of a value's string form. This is the single
    matching rule used everywhere in this tool -- PSA vs LGU boundaries,
    and Building Points vs PSA -- comparing geocode/PSGC-style codes at
    the region-province-municipality-barangay level while ignoring
    trailing digits/suffixes that may differ between layers.

    CAVEAT: if a geocode column is stored as a NUMBER field rather than
    text, leading zeros may already be lost (e.g. "01030200" -> 1030200),
    which would make the first-8 comparison unreliable. Text/string
    geocode columns are recommended.
    """
    if value is None:
        return ""
    s = str(value).strip()
    return s[:8]


class _PanelRunCoordinator:
    """Tracks which of one run's target layers have actually been added to
    the project, and opens the review panel only once every expected one has
    landed.

    QGIS stores layers-to-load-on-completion in a container keyed by layer
    id, not by registration order, so postProcessLayer() can fire for
    MATCHED_PSA, MATCHED_LGU and the Matched Building layer in any order.
    Firing the panel off the first callback alone would mean it sometimes
    opens before the Building layer -- or even the LGU layer -- actually
    exists in the project. Waiting for every expected id makes this order
    independent.
    """

    def __init__(self, psa_layer_id, lgu_layer_id, building_layer_id):
        self.psa_layer_id = psa_layer_id
        self.lgu_layer_id = lgu_layer_id
        self.building_layer_id = building_layer_id
        self.expected = {lid for lid in (psa_layer_id, lgu_layer_id, building_layer_id) if lid}
        self.seen = set()
        self.shown = False

    def mark_seen(self, layer_id, feedback):
        self.seen.add(layer_id)
        if self.shown or not self.expected.issubset(self.seen):
            return
        self.shown = True

        try:
            from qgis.utils import iface
        except ImportError:
            return
        # Headless runs (qgis_process, standalone PyQGIS) have no iface --
        # the algorithm must still complete normally there, just with no GUI.
        if iface is None:
            return
        try:
            from .psa_lgu_comparison_panel import show_comparison_panel
            show_comparison_panel(iface, self.psa_layer_id, self.lgu_layer_id, self.building_layer_id)
        except Exception as exc:
            feedback.pushInfo("Could not open the comparison review panel: {}".format(exc))


class _ComparisonPanelPostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Reports one layer's arrival in the project to a shared coordinator.

    processAlgorithm() runs on a Processing worker thread, where touching
    iface or building widgets is never safe. postProcessLayer() is the
    documented main-thread hook, so the panel is created from here instead.
    """

    def __init__(self, coordinator):
        super().__init__()
        self.coordinator = coordinator

    def postProcessLayer(self, layer, context, feedback):
        self.coordinator.mark_seen(layer.id(), feedback)


# QGIS takes ownership of a post processor, but the Python wrapper can still be
# garbage collected before postProcessLayer() runs; holding a module-level
# reference is the documented workaround. Only the most recent runs are kept
# so repeated runs don't grow this list without bound.
_PANEL_POST_PROCESSORS = []


def _make_panel_post_processors(psa_layer_id, lgu_layer_id, building_layer_id):
    """Return {layer_id: post_processor} for every target id that is not
    None. All share one coordinator, and each layer id gets its own
    processor instance -- QGIS takes ownership per-attachment, so the same
    instance cannot safely be reused across multiple LayerDetails."""
    coordinator = _PanelRunCoordinator(psa_layer_id, lgu_layer_id, building_layer_id)
    processors = {}
    for layer_id in coordinator.expected:
        processor = _ComparisonPanelPostProcessor(coordinator)
        _PANEL_POST_PROCESSORS.append(processor)
        processors[layer_id] = processor
    del _PANEL_POST_PROCESSORS[:-15]
    return processors


class PsaLguComparisonAlgorithm(QgsProcessingAlgorithm):
    """
    Matches PSA and LGU-submitted boundary polygons (and Building Point
    features) by comparing the first 8 characters of a geocode field on
    each layer, then loads styled/labeled Matched and Unmatched output
    layers into the project.
    """

    PSA_LAYER = 'PSA_LAYER'
    PSA_GEOCODE_FIELD = 'PSA_GEOCODE_FIELD'
    LGU_LAYER = 'LGU_LAYER'
    LGU_GEOCODE_FIELD = 'LGU_GEOCODE_FIELD'
    BUILDING_LAYER = 'BUILDING_LAYER'
    BUILDING_GEOCODE_FIELD = 'BUILDING_GEOCODE_FIELD'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return PsaLguComparisonAlgorithm()

    def name(self):
        return 'psalgu_boundary_comparison'

    def displayName(self):
        return self.tr('PSA - LGU Boundary Comparison')

    def group(self):
        return self.tr('1Map')

    def groupId(self):
        return '1map'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'compare_boundaries.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return self.tr(
            "Matches PSA and LGU-submitted boundary polygons (and Building Point features) by "
            "comparing the first 8 characters of a geocode field on each layer -- names are not "
            "used for matching, so spelling differences between the two maps don't matter. If a "
            "barangay is made up of several separate shapes (like islands), they all stay grouped "
            "together as one barangay.\n\n"
            "If a Geocode field is left blank, a field literally named 'Geocode' (any case) is "
            "auto-detected on that layer; other spellings/codes (PSGC, brgy_code, etc.) are not "
            "guessed and must be selected explicitly.\n\n"
            "Output layers (only created when they contain at least one feature):\n"
            "- <code>_PSA_Matched -- green outline, labeled with the PSA layer's 'barangay' field\n"
            "- <code>_LGU_Matched -- blue outline, labeled with the LGU layer's 'barangay' field\n"
            "- <code>_PSA_Unmatched / <code>_LGU_Unmatched\n"
            "- Building Points inside LGU Boundary / Building Points Outside LGU Boundary\n\n"
            "<code> is the pppmm-style prefix parsed from the PSA (or LGU) layer name, e.g. "
            "'000102_PSA' -> '000102'.\n\n"
            "A blank geocode never counts as a match, even blank-vs-blank. If two different "
            "barangays share the same first 8 characters, a building with that code is assigned "
            "to whichever barangay is processed first."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.PSA_LAYER,
                self.tr('PSA Boundary Layer'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.PSA_GEOCODE_FIELD,
                self.tr('Geocode Field (PSA)'),
                parentLayerParameterName=self.PSA_LAYER,
                type=QgsProcessingParameterField.Any,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.LGU_LAYER,
                self.tr('LGU-Submitted Boundary Layer'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.LGU_GEOCODE_FIELD,
                self.tr('Geocode Field (LGU)'),
                parentLayerParameterName=self.LGU_LAYER,
                type=QgsProcessingParameterField.Any,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.BUILDING_LAYER,
                self.tr('Building Point Layer'),
                [QgsProcessing.TypeVectorPoint]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.BUILDING_GEOCODE_FIELD,
                self.tr('Geocode Field (Building Point)'),
                parentLayerParameterName=self.BUILDING_LAYER,
                type=QgsProcessingParameterField.Any,
                optional=True
            )
        )

    def _resolve_geocode_field(self, layer, selected_field, label, feedback):
        """Return the user-selected geocode field, or auto-detect a field
        literally named "Geocode" on the layer if none was selected."""
        if selected_field:
            return selected_field
        guess = guess_geocode_field([f.name() for f in layer.fields()])
        if guess is None:
            raise QgsProcessingException(
                self.tr(f"Could not auto-detect a Geocode field on the {label} layer; "
                        f"please select one explicitly.")
            )
        feedback.pushInfo(self.tr(f"Auto-detected Geocode field ({label}): '{guess}'"))
        return guess

    def processAlgorithm(self, parameters, context, feedback: QgsProcessingFeedback):
        layer_psa = self.parameterAsVectorLayer(parameters, self.PSA_LAYER, context)
        layer_lgu = self.parameterAsVectorLayer(parameters, self.LGU_LAYER, context)
        building_layer = self.parameterAsVectorLayer(parameters, self.BUILDING_LAYER, context)

        if layer_psa is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.PSA_LAYER))
        if layer_lgu is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.LGU_LAYER))
        if building_layer is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.BUILDING_LAYER))

        geocode_field_psa = self._resolve_geocode_field(
            layer_psa, self.parameterAsString(parameters, self.PSA_GEOCODE_FIELD, context),
            'PSA', feedback)
        geocode_field_lgu = self._resolve_geocode_field(
            layer_lgu, self.parameterAsString(parameters, self.LGU_GEOCODE_FIELD, context),
            'LGU', feedback)
        building_field = self._resolve_geocode_field(
            building_layer, self.parameterAsString(parameters, self.BUILDING_GEOCODE_FIELD, context),
            'Building Point', feedback)

        if layer_psa.id() == layer_lgu.id():
            feedback.pushInfo(self.tr("Warning: PSA and LGU layers are the same layer. Continuing anyway."))

        feedback.setProgress(5)

        def load_layer(layer, name, post_processor=None):
            if layer is None:
                return None
            layer.setName(name)
            details = QgsProcessingContext.LayerDetails(name, context.project(), 'OUTPUT')
            if post_processor is not None:
                details.setPostProcessor(post_processor)
            context.temporaryLayerStore().addMapLayer(layer)
            context.addLayerToLoadOnCompletion(layer.id(), details)
            return layer.id()

        feats_psa = list(layer_psa.getFeatures())
        feats_lgu = list(layer_lgu.getFeatures())

        code_psa = [first8(f[geocode_field_psa]) for f in feats_psa]
        code_lgu = [first8(f[geocode_field_lgu]) for f in feats_lgu]

        # Group feature indices by geocode (first 8 chars) within each
        # layer (this is what lets a multi-part barangay travel together
        # as one group).
        group_psa = {}
        for i, c in enumerate(code_psa):
            group_psa.setdefault(c, []).append(i)
        group_lgu = {}
        for j, c in enumerate(code_lgu):
            group_lgu.setdefault(c, []).append(j)

        # A blank geocode never counts as a match, even blank-vs-blank.
        codes_psa = set(c for c in group_psa if c)
        codes_lgu = set(c for c in group_lgu if c)
        matched_codes = sorted(codes_psa & codes_lgu)

        # assign stable match_ids in sorted-code order
        pairs = [(i, code) for i, code in enumerate(matched_codes)]
        matched_code_set = set(code for _, code in pairs)

        matched_polys_psa = sum(len(group_psa[code]) for _, code in pairs)
        matched_polys_lgu = sum(len(group_lgu[code]) for _, code in pairs)
        unmatched_polys_psa = len(feats_psa) - matched_polys_psa
        unmatched_polys_lgu = len(feats_lgu) - matched_polys_lgu

        feedback.pushInfo(self.tr(
            f"Matched barangays: {len(pairs)} | Matched polygons -- PSA: {matched_polys_psa}, "
            f"LGU: {matched_polys_lgu} | Unmatched -- PSA: {unmatched_polys_psa}, LGU: {unmatched_polys_lgu}"
        ))
        feedback.setProgress(20)

        crs_psa = layer_psa.crs().authid()
        crs_lgu = layer_lgu.crs().authid()
        geom_psa = QgsWkbTypes.displayString(layer_psa.wkbType())
        geom_lgu = QgsWkbTypes.displayString(layer_lgu.wkbType())

        # pppmm-style code shared by the PSA and LGU layer names, used to
        # prefix every output layer so outputs from different
        # municipalities/cities don't collide or get confused with each
        # other. Prefer the code parsed from the PSA layer name; fall back
        # to the LGU layer name if the PSA name didn't yield one.
        code_prefix = extract_code(layer_psa.name()) or extract_code(layer_lgu.name())
        name_matched_psa = "{}_PSA_Matched".format(code_prefix)
        name_matched_lgu = "{}_LGU_Matched".format(code_prefix)
        name_unmatched_psa = "{}_PSA_Unmatched".format(code_prefix)
        name_unmatched_lgu = "{}_LGU_Unmatched".format(code_prefix)

        fields_matched_psa = QgsFields(layer_psa.fields())
        fields_matched_psa.append(QgsField("match_id", QVariant.Int))
        fields_matched_psa.append(QgsField("geocode", QVariant.String))

        fields_matched_lgu = QgsFields(layer_lgu.fields())
        fields_matched_lgu.append(QgsField("match_id", QVariant.Int))
        fields_matched_lgu.append(QgsField("geocode", QVariant.String))

        fields_unmatched_psa = QgsFields(layer_psa.fields())
        fields_unmatched_psa.append(QgsField("geocode_first8", QVariant.String))
        fields_unmatched_lgu = QgsFields(layer_lgu.fields())
        fields_unmatched_lgu.append(QgsField("geocode_first8", QVariant.String))

        matched_psa = QgsVectorLayer("{}?crs={}".format(geom_psa, crs_psa), name_matched_psa, "memory")
        matched_lgu = QgsVectorLayer("{}?crs={}".format(geom_lgu, crs_lgu), name_matched_lgu, "memory")
        unmatched_psa = QgsVectorLayer("{}?crs={}".format(geom_psa, crs_psa), name_unmatched_psa, "memory")
        unmatched_lgu = QgsVectorLayer("{}?crs={}".format(geom_lgu, crs_lgu), name_unmatched_lgu, "memory")

        # PSA_Matched gets a green outline, LGU_Matched a blue outline (both
        # transparent fill) so the two boundary sources are easy to tell
        # apart on the map when overlaid.
        style_boundary_outline(matched_psa, "green")
        style_boundary_outline(matched_lgu, "blue")

        matched_psa.dataProvider().addAttributes(fields_matched_psa)
        matched_psa.updateFields()
        matched_lgu.dataProvider().addAttributes(fields_matched_lgu)
        matched_lgu.updateFields()

        # Label matched PSA and LGU shapes with the barangay name from
        # each layer's own "barangay" column -- these are just map
        # labels, not used for matching.
        labeled_psa = label_by_field(matched_psa, "barangay", source_suffix="PSA")
        labeled_lgu = label_by_field(matched_lgu, "barangay", source_suffix="LGU")
        if not labeled_psa or not labeled_lgu:
            missing = []
            if not labeled_psa:
                missing.append("PSA (fields: {})".format(
                    ", ".join(f.name() for f in matched_psa.fields())))
            if not labeled_lgu:
                missing.append("LGU (fields: {})".format(
                    ", ".join(f.name() for f in matched_lgu.fields())))
            feedback.pushInfo(self.tr(
                "Warning: no 'barangay' field on -- {}".format("; ".join(missing))
            ))

        unmatched_psa.dataProvider().addAttributes(fields_unmatched_psa)
        unmatched_psa.updateFields()
        unmatched_lgu.dataProvider().addAttributes(fields_unmatched_lgu)
        unmatched_lgu.updateFields()

        matched_psa_feats, matched_lgu_feats = [], []
        # match_id -> set of distinct PSA geocode-first8 values (for Building Point matching)
        geocode_values_by_match = {}
        for match_id, code in pairs:
            geocode_values_by_match.setdefault(match_id, set()).add(code)
            for i in group_psa[code]:
                fp = feats_psa[i]
                out_f = QgsFeature(matched_psa.fields())
                out_f.setGeometry(fp.geometry())
                out_f.setAttributes(fp.attributes() + [match_id, code])
                matched_psa_feats.append(out_f)
            for j in group_lgu[code]:
                fl = feats_lgu[j]
                out_f = QgsFeature(matched_lgu.fields())
                out_f.setGeometry(fl.geometry())
                out_f.setAttributes(fl.attributes() + [match_id, code])
                matched_lgu_feats.append(out_f)

        unmatched_psa_feats = []
        for code, idxs in group_psa.items():
            if code not in matched_code_set:
                for i in idxs:
                    fp = feats_psa[i]
                    out_f = QgsFeature(unmatched_psa.fields())
                    out_f.setGeometry(fp.geometry())
                    out_f.setAttributes(fp.attributes() + [code])
                    unmatched_psa_feats.append(out_f)

        unmatched_lgu_feats = []
        for code, idxs in group_lgu.items():
            if code not in matched_code_set:
                for j in idxs:
                    fl = feats_lgu[j]
                    out_f = QgsFeature(unmatched_lgu.fields())
                    out_f.setGeometry(fl.geometry())
                    out_f.setAttributes(fl.attributes() + [code])
                    unmatched_lgu_feats.append(out_f)

        matched_psa.dataProvider().addFeatures(matched_psa_feats)
        matched_lgu.dataProvider().addFeatures(matched_lgu_feats)
        unmatched_psa.dataProvider().addFeatures(unmatched_psa_feats)
        unmatched_lgu.dataProvider().addFeatures(unmatched_lgu_feats)

        for lyr in (matched_psa, matched_lgu, unmatched_psa, unmatched_lgu):
            lyr.updateExtents()

        feedback.setProgress(50)

        # --- Building Point matching, using the same first-8-characters ---
        # --- geocode rule.                                              ---
        # first8 code -> match_id (first barangay group wins on a rare collision)
        code8_to_match_id = {}
        for mid, codes in geocode_values_by_match.items():
            for c in codes:
                code8_to_match_id.setdefault(c, mid)
        match_id_to_code = {mid: code for mid, code in pairs}

        crs_building = building_layer.crs().authid()
        geom_building = QgsWkbTypes.displayString(building_layer.wkbType())

        fields_building_matched = QgsFields(building_layer.fields())
        fields_building_matched.append(QgsField("match_id", QVariant.Int))
        fields_building_matched.append(QgsField("geocode", QVariant.String))

        fields_building_unmatched = QgsFields(building_layer.fields())
        fields_building_unmatched.append(QgsField("geocode_first8", QVariant.String))

        matched_building = QgsVectorLayer(
            "{}?crs={}".format(geom_building, crs_building),
            "Building Points inside LGU Boundary", "memory")
        unmatched_building = QgsVectorLayer(
            "{}?crs={}".format(geom_building, crs_building),
            "Building Points Outside LGU Boundary", "memory")

        matched_building.dataProvider().addAttributes(fields_building_matched)
        matched_building.updateFields()
        unmatched_building.dataProvider().addAttributes(fields_building_unmatched)
        unmatched_building.updateFields()

        matched_building_feats, unmatched_building_feats = [], []
        for feat in building_layer.getFeatures():
            if feedback.isCanceled():
                return {}
            code8 = first8(feat[building_field])
            mid = code8_to_match_id.get(code8) if code8 else None
            if mid is not None:
                out_f = QgsFeature(matched_building.fields())
                out_f.setGeometry(feat.geometry())
                out_f.setAttributes(feat.attributes() + [mid, match_id_to_code.get(mid, "")])
                matched_building_feats.append(out_f)
            else:
                out_f = QgsFeature(unmatched_building.fields())
                out_f.setGeometry(feat.geometry())
                out_f.setAttributes(feat.attributes() + [code8])
                unmatched_building_feats.append(out_f)

        matched_building.dataProvider().addFeatures(matched_building_feats)
        unmatched_building.dataProvider().addFeatures(unmatched_building_feats)
        matched_building.updateExtents()
        unmatched_building.updateExtents()

        feedback.pushInfo(self.tr(
            f"Building points -- matched: {len(matched_building_feats)}, "
            f"unmatched: {len(unmatched_building_feats)}"
        ))
        feedback.setProgress(90)

        # Only load layers that actually contain features -- an empty
        # matched/unmatched group is common (e.g. every barangay matched)
        # and would just clutter the Layers panel with nothing to show.
        # The review panel needs both Matched layers (and, when present, the
        # Matched Building layer): each gets its own post processor, all
        # sharing one coordinator, so the panel opens only after every
        # expected one of them has actually landed in the project.
        panel_processors = {}
        if matched_psa_feats and matched_lgu_feats:
            panel_building_id = matched_building.id() if matched_building_feats else None
            panel_processors = _make_panel_post_processors(
                matched_psa.id(), matched_lgu.id(), panel_building_id)

        results = {
            'MATCHED_PSA': load_layer(
                matched_psa, name_matched_psa,
                panel_processors.get(matched_psa.id())) if matched_psa_feats else None,
            'MATCHED_LGU': load_layer(
                matched_lgu, name_matched_lgu,
                panel_processors.get(matched_lgu.id())) if matched_lgu_feats else None,
            'UNMATCHED_PSA': load_layer(unmatched_psa, name_unmatched_psa) if unmatched_psa_feats else None,
            'UNMATCHED_LGU': load_layer(unmatched_lgu, name_unmatched_lgu) if unmatched_lgu_feats else None,
            'MATCHED_BUILDING': load_layer(
                matched_building, "Building Points inside LGU Boundary",
                panel_processors.get(matched_building.id())) if matched_building_feats else None,
            'UNMATCHED_BUILDING': load_layer(
                unmatched_building, "Building Points Outside LGU Boundary") if unmatched_building_feats else None,
        }

        feedback.setProgress(100)
        feedback.pushInfo(self.tr("Finished PSA - LGU Boundary Comparison."))
        return results
