from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingException,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsSpatialIndex,
    QgsFeatureRequest,
    QgsCoordinateTransform,
    QgsProject,
    QgsFields,
    QgsWkbTypes,
    QgsVectorFileWriter,
    QgsVectorLayer,
    NULL,
)
from PyQt5.QtCore import QCoreApplication, QVariant
from PyQt5.QtGui import QIcon
import re
import os
from datetime import datetime


# =====================================================
# CONFIG
# =====================================================

STATUS_FIELD = "mbi_status"
REMARKS_FIELD = "pso_remarks"
CASE_UUID_FIELD = "case_uuid"
INVOLVED_BGYS_FIELD = "involved_bgys"
NUM_BLDG_PTS_FIELD = "num_bldg_pts"
TYPE_FIELD = "mbi_type"          # distinguishes Gap vs Overlap within the single Reference layer

# Keywords used to match mbi_type values case-insensitively (e.g. "1_Gap", "2_Overlap")
TYPE_KEYWORDS = {
    "GAP": "gap",
    "OVERLAP": "overlap",
}

# Statuses that mean "processor claims this case is resolved"
RESOLVED_STATUSES = {"1_Updated"}

CATEGORY_GPKG_LAYER_NAMES = {
    "status_mismatch": "status_mismatch",
    "mismatch_with_remarks": "mismatch_with_remarks",
    "new_cases": "new_cases",
    "still_active": "remaining_cases",
    "confirmed_resolved": "confirmed_resolved",
    "ambiguous": "manual_review",
    "no_status": "no_status",
}

# Base name used for the auto-generated GeoPackage filename.
# Final filename pattern: ref_mbi_reviewed-YYYY-MM-DD_HH-MM-SS.gpkg
# (colons are not valid in Windows filenames, so time uses hyphens instead of ':')
GPKG_BASE_NAME = "ref_mbi_reviewed"


def build_timestamped_gpkg_path(folder):
    """
    Builds the full output path inside the given folder, with the
    filename forced to: ref_mbi_reviewed-YYYY-MM-DD_HH-MM-SS.gpkg
    The processor never gets to type or edit this filename -- the
    input parameter is a folder picker only (see GPKG_OUTPUT below).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{GPKG_BASE_NAME}-{timestamp}.gpkg"
    return os.path.join(folder, filename)


# =====================================================
# UTILITIES
# =====================================================

def normalize(val):
    if val in (None, NULL):
        return ""
    return str(val).strip()


def safe_get(feature, field_name):
    if feature is None:
        return ""
    idx = feature.fields().indexOf(field_name)
    if idx == -1:
        return ""
    return normalize(feature[field_name])


def layer_has_field(layer, field_name):
    return layer.fields().indexOf(field_name) != -1


def meaningful(val):
    if val in (None, NULL):
        return False
    txt = str(val).strip().lower()
    if txt in ("", "null", "none", "nan"):
        return False
    return len(re.findall(r"[a-z0-9]", txt)) >= 3


def get_num_bldg_pts(feature):
    if feature is None:
        return 0
    idx = feature.fields().indexOf(NUM_BLDG_PTS_FIELD)
    if idx == -1:
        return 0
    val = feature[NUM_BLDG_PTS_FIELD]
    try:
        return int(val) if val not in (None, "", NULL) else 0
    except Exception:
        return 0


def get_reference_subset(reference_layer, case_type):
    """
    Returns a materialized list of reference features matching the
    given case_type ('Gap' or 'Overlap'), based on the mbi_type field.
    Case-insensitive substring match, so '1_Gap', '2_Overlap', etc. all work.
    """
    keyword = TYPE_KEYWORDS[case_type.upper()]
    if not layer_has_field(reference_layer, TYPE_FIELD):
        # No type field at all -> can't distinguish, treat everything as unfiltered
        return list(reference_layer.getFeatures())

    expr = f"lower(\"{TYPE_FIELD}\") LIKE '%{keyword}%'"
    request = QgsFeatureRequest().setFilterExpression(expr)
    return list(reference_layer.getFeatures(request))


def spatial_match(checker_layer, reference_features, reference_crs):
    """
    For every checker feature, find all reference features (from the
    already-filtered reference_features list) whose geometry actually
    OVERLAPS it (shares interior area) — not just touches at a shared
    edge or vertex, which would wrongly link an adjacent-but-unrelated
    (genuinely new) case to a neighboring reference case.
    Returns a list of (checker_feat, [ref_feats]).
    """
    idx = QgsSpatialIndex()
    for rf in reference_features:
        idx.addFeature(rf)

    tr = None
    if checker_layer.sourceCrs() != reference_crs:
        tr = QgsCoordinateTransform(checker_layer.sourceCrs(), reference_crs, QgsProject.instance())

    ref_by_id = {rf.id(): rf for rf in reference_features}

    results = []
    for cf in checker_layer.getFeatures():
        g = QgsGeometry(cf.geometry())
        if g.isNull() or g.isEmpty():
            continue
        if tr:
            g.transform(tr)

        matched_refs = []
        for rid in idx.intersects(g.boundingBox()):
            rf = ref_by_id.get(rid)
            if rf is None or not rf.geometry():
                continue

            rgeom = rf.geometry()

            # Adjacent-only (shares boundary/vertex, no interior overlap) ->
            # NOT a real match. This is what previously caused a brand-new
            # case sitting next to a reference polygon to wrongly inherit
            # that reference's status.
            if rgeom.touches(g):
                continue

            if rgeom.intersects(g):
                # Extra safety: confirm the intersection has real area,
                # guarding against near-zero sliver overlaps from snapping.
                overlap_geom = rgeom.intersection(g)
                if overlap_geom and not overlap_geom.isEmpty() and overlap_geom.area() > 0:
                    matched_refs.append(rf)

        results.append((cf, matched_refs))
    return results


def evaluate_reference_case(rf, spatially_confirmed):
    """
    Runs attribute-based rules on a single reference feature.
    Returns (category, reason) where category is one of:
      "status_mismatch", "mismatch_with_remarks", "still_active",
      "confirmed_resolved", "no_status"

    "status_mismatch" vs "mismatch_with_remarks" split:
      - status_mismatch: no justification exists in ref_remarks at all
        (Rule A, or Rule B when remarks are blank/meaningless) -- these
        need someone to actually go fix the case, there's nothing on
        record explaining the discrepancy.
      - mismatch_with_remarks: ref_remarks already has something written
        (Rule C always, since it's flagged "For Review of Remarks"; or
        Rule B when remarks ARE present) -- these need someone to check
        whether the existing remarks actually justify the mismatch,
        rather than starting from nothing.
    """
    status = safe_get(rf, STATUS_FIELD)
    bp = get_num_bldg_pts(rf)
    rem = rf[REMARKS_FIELD] if layer_has_field(rf, REMARKS_FIELD) else None
    has_remarks = meaningful(rem)

    plain_reasons = []
    remarks_reasons = []

    # Rule A: claimed resolved, but checker still finds it
    if status in RESOLVED_STATUSES and spatially_confirmed:
        plain_reasons.append(f"'{status}' but case still detected by Checker.")

    # Rule B: 2_Pending, zero building points
    if status == "2_Pending" and bp == 0:
        if has_remarks:
            remarks_reasons.append(
                "'2_Pending' with 0 num_bldg_pts; remarks present, please verify justification."
            )
        else:
            plain_reasons.append("'2_Pending' with 0 num_bldg_pts and no justifying remarks.")

    # Rule C: 1_Updated but still has building points -- always routed to
    # the "review the remarks" bucket, regardless of whether remarks exist.
    if status == "1_Updated" and bp != 0:
        remarks_reasons.append(f"For Review of Remarks: Status='1_Updated' but has {bp} building point(s) remaining.")

    if plain_reasons:
        return "status_mismatch", "; ".join(plain_reasons + remarks_reasons)

    if remarks_reasons:
        return "mismatch_with_remarks", "; ".join(remarks_reasons)

    if status == "":
        return "no_status", "Reference case has no status value."

    if status in RESOLVED_STATUSES and not spatially_confirmed:
        return "confirmed_resolved", f"Status='{status}' and no longer detected by Checker."

    # anything else (e.g. 2_Pending with valid justification)
    return "still_active", f"Status='{status}', case remains open (Remaining Case)."


def classify(checker_layer, reference_features, reference_crs):
    """
    Classifies cases into:
      - status_mismatch: attribute rules failed, no justification on record
      - mismatch_with_remarks: attribute rules failed, but ref_remarks
        already has something written that needs verification
      - no_status: reference case has a blank/missing status
      - still_active: matched or unmatched, but legitimately still open (Remaining Case)
      - new_cases: checker case has no genuine reference overlap at all
      - ambiguous: checker case overlaps more than one reference feature (Manual Review)
      - confirmed_resolved: reference marked resolved, checker no longer detects it
    """
    matches = spatial_match(checker_layer, reference_features, reference_crs)

    status_mismatch, mismatch_with_remarks, still_active, new_cases, ambiguous, no_status = [], [], [], [], [], []
    matched_ref_ids = set()

    for cf, matched_refs in matches:
        if len(matched_refs) == 0:
            new_cases.append(cf)
        elif len(matched_refs) == 1:
            rf = matched_refs[0]
            matched_ref_ids.add(rf.id())
            category, reason = evaluate_reference_case(rf, spatially_confirmed=True)
            if category == "status_mismatch":
                status_mismatch.append((cf, rf, reason))
            elif category == "mismatch_with_remarks":
                mismatch_with_remarks.append((cf, rf, reason))
            elif category == "no_status":
                no_status.append((cf, rf, reason))
            else:
                still_active.append((cf, rf, reason))
        else:
            for rf in matched_refs:
                matched_ref_ids.add(rf.id())
            ambiguous.append((cf, matched_refs))

    confirmed_resolved = []
    for rf in reference_features:
        if rf.id() in matched_ref_ids:
            continue
        category, reason = evaluate_reference_case(rf, spatially_confirmed=False)
        if category == "status_mismatch":
            status_mismatch.append((None, rf, reason))
        elif category == "mismatch_with_remarks":
            mismatch_with_remarks.append((None, rf, reason))
        elif category == "confirmed_resolved":
            confirmed_resolved.append((rf, reason))
        elif category == "no_status":
            no_status.append((None, rf, reason))
        else:
            still_active.append((None, rf, reason))

    return {
        "status_mismatch": status_mismatch,
        "mismatch_with_remarks": mismatch_with_remarks,
        "still_active": still_active,
        "new_cases": new_cases,
        "ambiguous": ambiguous,
        "confirmed_resolved": confirmed_resolved,
        "no_status": no_status,
    }


def output_fields():
    """
    Column order (fid is auto-managed by the output provider and always
    appears leftmost automatically -- it is intentionally not defined here):
    case_uuid, case_type, remarks, ref_status, ref_remarks,
    ref_involved_bgys, ref_num_bldg_pts
    """
    fields = QgsFields()
    fields.append(QgsField("case_uuid", QVariant.String, len=100))
    fields.append(QgsField("case_type", QVariant.String, len=20))
    fields.append(QgsField("remarks", QVariant.String, len=255))
    fields.append(QgsField("ref_status", QVariant.String, len=60))
    fields.append(QgsField("ref_remarks", QVariant.String, len=255))
    fields.append(QgsField("ref_involved_bgys", QVariant.String, len=255))
    fields.append(QgsField("ref_num_bldg_pts", QVariant.Int))
    return fields


def make_feature(fields, geometry, case_type, remarks, case_uuid="", ref_feature=None):
    nf = QgsFeature(fields)
    nf.setGeometry(QgsGeometry(geometry))
    final_uuid = case_uuid or safe_get(ref_feature, CASE_UUID_FIELD)
    nf.setAttribute("case_uuid", final_uuid)
    nf.setAttribute("case_type", case_type)
    nf.setAttribute("remarks", remarks)
    if ref_feature is not None:
        nf.setAttribute("ref_status", safe_get(ref_feature, STATUS_FIELD))
        nf.setAttribute("ref_remarks", safe_get(ref_feature, REMARKS_FIELD))
        nf.setAttribute("ref_involved_bgys", safe_get(ref_feature, INVOLVED_BGYS_FIELD))
        nf.setAttribute("ref_num_bldg_pts", get_num_bldg_pts(ref_feature))
    return nf


# =====================================================
# PROCESSING ALGORITHM
# =====================================================

class MbiValidatorAlgorithm(QgsProcessingAlgorithm):

    REF_LAYER = "REF_LAYER"
    CHK_GAP = "CHK_GAP"
    CHK_OVERLAP = "CHK_OVERLAP"

    COMBINE_GPKG = "COMBINE_GPKG"
    GPKG_OUTPUT = "GPKG_OUTPUT"

    OUT_MISMATCH = "OUT_MISMATCH"
    OUT_MISMATCH_REMARKS = "OUT_MISMATCH_REMARKS"
    OUT_NEW = "OUT_NEW"
    OUT_STILL = "OUT_STILL"
    OUT_RESOLVED = "OUT_RESOLVED"
    OUT_MANUAL_REVIEW = "OUT_MANUAL_REVIEW"
    OUT_NOSTATUS = "OUT_NOSTATUS"

    def tr(self, string):
        return QCoreApplication.translate("MbiValidatorAlgorithm", string)

    def createInstance(self):
        return MbiValidatorAlgorithm()

    def name(self):
        return "mbi_validator"

    def displayName(self):
        return self.tr("MBI Validator")

    def group(self):
        return self.tr("1Map")

    def groupId(self):
        return "1map"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'mbi_validator.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return self.tr(
            "Cross-checks a single combined Reference MBI layer (Gap and "
            "Overlap cases distinguished by the 'mbi_type' field) against "
            "separate Checker GAP / OVERLAP layers to flag status mismatches.\n\n"
            "A Checker case is only linked to a Reference case when it "
            "genuinely overlaps it in area — merely touching a neighboring "
            "Reference polygon's edge does NOT count as a match, so a truly "
            "new case sitting next to an old one is correctly classified as "
            "a New Case.\n\n"
            "Reference layer is required. Leave a Checker input empty if "
            "that case type doesn't apply.\n\n"
            "Optionally, tick 'Combine all outputs into a single GeoPackage' "
            "and pick a folder — every non-empty category will be written as "
            "a separate layer inside one .gpkg file, automatically named "
            "'ref_mbi_reviewed-YYYY-MM-DD_HH-MM-SS.gpkg' with the current "
            "date and time. The filename is generated automatically and "
            "cannot be edited — only the destination folder is chosen.\n\n"
            "Outputs (only generated when they contain at least one feature):\n"
            "- Status Mismatch: claimed resolved but still detected, or "
            "Pending w/ 0 bldg pts and no remarks at all\n"
            "- Mismatch with Remarks: Pending w/ 0 bldg pts but remarks ARE "
            "present (verify the justification), or Updated w/ nonzero "
            "bldg pts (review remarks either way)\n"
            "- New Cases: Checker case with no genuine Reference overlap\n"
            "- Remaining Cases: known, legitimately unresolved\n"
            "- Confirmed Resolved: claimed resolved and Checker agrees\n"
            "- No Status: Reference case with blank status\n"
            "- Manual Review: one Checker case overlaps multiple Reference cases"
        )

    @staticmethod
    def _hidden_sink(name, description):
        """
        Builds an optional QgsProcessingParameterFeatureSink that behaves
        exactly like before (defaults to a temporary output, skipped
        entirely in processAlgorithm() when its category has no features)
        but is flagged Hidden so it never shows a row -- not even folded
        away under "Advanced Parameters" -- in the algorithm dialog.

        FlagHidden also removes the parameter from the dialog's normal
        "load resulting layer on completion" bookkeeping (that's driven
        by the "Open output file after running algorithm" checkbox,
        which no longer exists once hidden). To compensate, processAlgorithm()
        explicitly calls context.addLayerToLoadOnCompletion(...) for each
        of these sinks itself, so the temporary layers still get added to
        the project after a run even though there's no visible checkbox
        telling QGIS to do so.
        """
        param = QgsProcessingParameterFeatureSink(
            name, description, optional=True,
            defaultValue=QgsProcessing.TEMPORARY_OUTPUT)
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagHidden)
        return param

    def initAlgorithm(self, config=None):
        # Reference layer is REQUIRED — no optional=True here
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.REF_LAYER, self.tr("Reference layer "),
            [QgsProcessing.TypeVectorPolygon]))

        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CHK_GAP, self.tr("Checker GAP layer"),
            [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.CHK_OVERLAP, self.tr("Checker OVERLAP layer"),
            [QgsProcessing.TypeVectorPolygon], optional=True))

        self.addParameter(QgsProcessingParameterBoolean(
            self.COMBINE_GPKG,
            self.tr("Save outputs as GeoPackage"),
            defaultValue=False))

        # Folder picker only -- no filename box, so the auto-generated
        # timestamped filename can never be edited by the processor.
        self.addParameter(QgsProcessingParameterFile(
            self.GPKG_OUTPUT,
            self.tr("Save Path"),
            behavior=QgsProcessingParameterFile.Folder,
            optional=False))

        # --- Individual output sinks: process-wise these are unchanged
        # (still optional QgsProcessingParameterFeatureSink, still created
        # as temporary layers, still skipped when their category is empty
        # in processAlgorithm()). FlagHidden removes their rows from the
        # dialog completely (not even under "Advanced Parameters"), since
        # "Save outputs as GeoPackage" above is now the primary output
        # path. processAlgorithm() manually re-registers each one to load
        # on completion, so they still appear as temporary layers.
        self.addParameter(self._hidden_sink(self.OUT_MISMATCH, self.tr("Status Mismatch")))
        self.addParameter(self._hidden_sink(self.OUT_MISMATCH_REMARKS, self.tr("Mismatch with Remarks")))
        self.addParameter(self._hidden_sink(self.OUT_NEW, self.tr("New Cases")))
        self.addParameter(self._hidden_sink(self.OUT_STILL, self.tr("Remaining Cases")))
        self.addParameter(self._hidden_sink(self.OUT_RESOLVED, self.tr("Confirmed Resolved")))
        self.addParameter(self._hidden_sink(self.OUT_MANUAL_REVIEW, self.tr("Manual Review")))
        self.addParameter(self._hidden_sink(self.OUT_NOSTATUS, self.tr("No Status")))

    def processAlgorithm(self, parameters, context, feedback):
        ref_layer = self.parameterAsVectorLayer(parameters, self.REF_LAYER, context)
        chk_g = self.parameterAsVectorLayer(parameters, self.CHK_GAP, context)
        chk_o = self.parameterAsVectorLayer(parameters, self.CHK_OVERLAP, context)
        combine_gpkg = self.parameterAsBoolean(parameters, self.COMBINE_GPKG, context)
        gpkg_folder = self.parameterAsFile(parameters, self.GPKG_OUTPUT, context)

        if ref_layer is None:
            raise QgsProcessingException(
                self.tr("Reference layer is required.")
            )

        if not chk_g and not chk_o:
            raise QgsProcessingException(
                self.tr("Please provide at least one Checker layer (GAP or OVERLAP).")
            )

        if not layer_has_field(ref_layer, STATUS_FIELD):
            raise QgsProcessingException(
                self.tr(f"Reference layer has no '{STATUS_FIELD}' field.")
            )

        if combine_gpkg and not gpkg_folder:
            raise QgsProcessingException(
                self.tr("Please choose a folder to save the GeoPackage.")
            )

        # Filename is always auto-generated -- never taken from user input.
        gpkg_path = build_timestamped_gpkg_path(gpkg_folder) if combine_gpkg else None

        crs = chk_g.sourceCrs() if chk_g else chk_o.sourceCrs()
        wkb = chk_g.wkbType() if chk_g else chk_o.wkbType()
        fields = output_fields()
        ref_crs = ref_layer.sourceCrs()

        # --- collect classified results across Gap/Overlap without writing yet ---
        # each entry: (geometry, case_type, remarks, case_uuid, ref_feature)
        collected = {
            "status_mismatch": [],
            "mismatch_with_remarks": [],
            "new_cases": [],
            "still_active": [],
            "confirmed_resolved": [],
            "ambiguous": [],
            "no_status": [],
        }

        pairs = []
        if chk_g is not None:
            pairs.append(("Gap", chk_g))
        if chk_o is not None:
            pairs.append(("Overlap", chk_o))

        total = len(pairs) or 1
        step = 0

        for case_type, chk_layer in pairs:
            if feedback.isCanceled():
                break

            ref_features = get_reference_subset(ref_layer, case_type)

            result = classify(chk_layer, ref_features, ref_crs)

            for cf, rf, reason in result["status_mismatch"]:
                geom = cf.geometry() if cf is not None else rf.geometry()
                remarks = reason
                collected["status_mismatch"].append((geom, case_type, remarks, "", rf))

            for cf, rf, reason in result["mismatch_with_remarks"]:
                geom = cf.geometry() if cf is not None else rf.geometry()
                remarks = reason
                collected["mismatch_with_remarks"].append((geom, case_type, remarks, "", rf))

            for cf in result["new_cases"]:
                remarks = "No matching reference case found."
                chk_uuid = safe_get(cf, CASE_UUID_FIELD)
                collected["new_cases"].append((cf.geometry(), case_type, remarks, chk_uuid, None))

            for cf, rf, reason in result["still_active"]:
                geom = cf.geometry() if cf is not None else rf.geometry()
                remarks = reason
                collected["still_active"].append((geom, case_type, remarks, "", rf))

            for cf, rf, reason in result["no_status"]:
                geom = cf.geometry() if cf is not None else rf.geometry()
                remarks = reason
                collected["no_status"].append((geom, case_type, remarks, "", rf))

            for rf, reason in result["confirmed_resolved"]:
                remarks = reason
                collected["confirmed_resolved"].append((rf.geometry(), case_type, remarks, "", rf))

            for cf, matched_refs in result["ambiguous"]:
                uuids = ", ".join(safe_get(rf, CASE_UUID_FIELD) or str(rf.id()) for rf in matched_refs)
                remarks = f"Matches {len(matched_refs)} reference cases ({uuids}). Review manually."
                chk_uuid = safe_get(cf, CASE_UUID_FIELD)
                collected["ambiguous"].append((cf.geometry(), case_type, remarks, chk_uuid, None))

            step += 1
            feedback.setProgress(int(100 * step / total))

        # reference-only case types (no matching checker layer provided at all)
        for case_type, chk_layer in (("Gap", chk_g), ("Overlap", chk_o)):
            if chk_layer is None:
                for rf in get_reference_subset(ref_layer, case_type):
                    category, reason = evaluate_reference_case(rf, spatially_confirmed=False)
                    if category == "status_mismatch":
                        remarks = reason
                        collected["status_mismatch"].append((rf.geometry(), case_type, remarks, "", rf))
                    elif category == "mismatch_with_remarks":
                        remarks = reason
                        collected["mismatch_with_remarks"].append((rf.geometry(), case_type, remarks, "", rf))
                    elif category == "confirmed_resolved":
                        remarks = reason
                        collected["confirmed_resolved"].append((rf.geometry(), case_type, remarks, "", rf))
                    elif category == "no_status":
                        remarks = reason
                        collected["no_status"].append((rf.geometry(), case_type, remarks, "", rf))
                    else:
                        remarks = reason
                        collected["still_active"].append((rf.geometry(), case_type, remarks, "", rf))

        counts = {k: len(v) for k, v in collected.items()}
        results = {}

        # --- temporary-layer sinks: ALWAYS produced for non-empty categories,
        # regardless of whether "Save outputs as GeoPackage" is ticked. This
        # is the same behaviour as before GeoPackage export was added.
        # Layer names double as the label shown in the Layers panel once loaded.
        output_map = (
            (self.OUT_MISMATCH, "status_mismatch", self.tr("Status Mismatch")),
            (self.OUT_MISMATCH_REMARKS, "mismatch_with_remarks", self.tr("Mismatch with Remarks")),
            (self.OUT_NEW, "new_cases", self.tr("New Cases")),
            (self.OUT_STILL, "still_active", self.tr("Remaining Cases")),
            (self.OUT_RESOLVED, "confirmed_resolved", self.tr("Confirmed Resolved")),
            (self.OUT_MANUAL_REVIEW, "ambiguous", self.tr("Manual Review")),
            (self.OUT_NOSTATUS, "no_status", self.tr("No Status")),
        )

        for out_key, coll_key, label in output_map:
            items = collected[coll_key]

            if not items:
                # skip creating this output entirely -> keeps Layers panel clean
                continue

            sink, dest_id = self.parameterAsSink(parameters, out_key, context, fields, wkb, crs)
            if sink is None:
                # user didn't set a destination for this optional output -> skip silently
                continue

            for geom, case_type, remarks, case_uuid, ref_feature in items:
                sink.addFeature(
                    make_feature(fields, geom, case_type, remarks,
                                 case_uuid=case_uuid, ref_feature=ref_feature)
                )

            results[out_key] = dest_id

            # Because these sinks are FlagHidden, the dialog has no checkbox
            # to tell it "load this on completion" -- so we register it
            # ourselves. Without this, the temporary layer would be written
            # but never added to the Layers panel.
            context.addLayerToLoadOnCompletion(
                dest_id,
                QgsProcessingContext.LayerDetails(label, context.project(), out_key)
            )

        if combine_gpkg:
            # --- ADDITIONALLY write every non-empty category as a layer
            # inside one GeoPackage. This happens alongside the temporary
            # layers above, not instead of them.
            first_written = True
            for coll_key, items in collected.items():
                if not items:
                    continue

                layer_name = CATEGORY_GPKG_LAYER_NAMES[coll_key]

                mem_layer = QgsVectorLayer(
                    f"{QgsWkbTypes.displayString(wkb)}?crs={crs.authid()}",
                    layer_name, "memory"
                )
                mem_layer.dataProvider().addAttributes(fields)
                mem_layer.updateFields()

                feats = []
                for geom, case_type, remarks, case_uuid, ref_feature in items:
                    feats.append(
                        make_feature(mem_layer.fields(), geom, case_type, remarks,
                                     case_uuid=case_uuid, ref_feature=ref_feature)
                    )
                mem_layer.dataProvider().addFeatures(feats)
                mem_layer.updateExtents()

                save_options = QgsVectorFileWriter.SaveVectorOptions()
                save_options.driverName = "GPKG"
                save_options.layerName = layer_name
                save_options.fileEncoding = "UTF-8"
                if not first_written:
                    save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

                error = QgsVectorFileWriter.writeAsVectorFormatV3(
                    mem_layer, gpkg_path, QgsProject.instance().transformContext(), save_options
                )
                if error[0] != QgsVectorFileWriter.NoError:
                    raise QgsProcessingException(
                        self.tr(f"Failed to write layer '{layer_name}' to GeoPackage: {error[1]}")
                    )

                first_written = False

            feedback.pushInfo(self.tr(f"GeoPackage saved to: {gpkg_path}"))

        feedback.pushInfo(
            f"Status Mismatch: {counts['status_mismatch']} | Mismatch with Remarks: {counts['mismatch_with_remarks']} | "
            f"New Cases: {counts['new_cases']} | "
            f"Remaining Cases: {counts['still_active']} | No Status: {counts['no_status']} | "
            f"Confirmed Resolved: {counts['confirmed_resolved']} | Manual Review: {counts['ambiguous']}"
        )

        if combine_gpkg:
            results[self.GPKG_OUTPUT] = gpkg_path

        return results


# Backward compatibility alias
MBIStatusAuditAlgorithm = MbiValidatorAlgorithm