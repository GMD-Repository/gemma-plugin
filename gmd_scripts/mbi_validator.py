import os
import re
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
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
    NULL,
)


# =====================================================
# CONFIG
# =====================================================

STATUS_FIELD = "mbi_status"
REMARKS_FIELD = "mbi_remarks"
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
    given case_type ('GAP' or 'OVERLAP'), based on the mbi_type field.
    Case-insensitive substring match, so '1_Gap', '2_Overlap', etc. all work.
    """
    keyword = TYPE_KEYWORDS[case_type]
    if not layer_has_field(reference_layer, TYPE_FIELD):
        # No type field at all -> can't distinguish, treat everything as unfiltered
        return list(reference_layer.getFeatures())

    expr = f"lower(\"{TYPE_FIELD}\") LIKE '%{keyword}%'"
    request = QgsFeatureRequest().setFilterExpression(expr)
    return list(reference_layer.getFeatures(request))


def spatial_match(checker_layer, reference_features, reference_crs):
    """
    For every checker feature, find all reference features (from the
    already-filtered reference_features list) whose geometry intersects it.
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
            if rf and rf.geometry() and rf.geometry().intersects(g):
                matched_refs.append(rf)

        results.append((cf, matched_refs))
    return results


def evaluate_reference_case(rf, spatially_confirmed):
    """
    Runs attribute-based rules on a single reference feature.
    Returns (category, reason) where category is one of:
      "status_mismatch", "still_active", "confirmed_resolved", "no_status"
    """
    status = safe_get(rf, STATUS_FIELD)
    bp = get_num_bldg_pts(rf)
    rem = rf[REMARKS_FIELD] if layer_has_field(rf, REMARKS_FIELD) else None

    reasons = []

    # Rule A: claimed resolved, but checker still finds it
    if status in RESOLVED_STATUSES and spatially_confirmed:
        reasons.append(f"Status='{status}' but case still detected by Checker.")

    # Rule B: 2_Pending, zero building points, no justification remarks
    if status == "2_Pending" and bp == 0 and not meaningful(rem):
        reasons.append("Status='2_Pending' with 0 num_bldg_pts and no justifying remarks.")

    # Rule C: 1_Updated but still has building points
    if status == "1_Updated" and bp != 0:
        reasons.append(f"Status='1_Updated' but num_bldg_pts={bp} (should be 0 if resolved).")

    if reasons:
        return "status_mismatch", "; ".join(reasons)

    if status == "":
        return "no_status", "Reference case has no status value."

    if status in RESOLVED_STATUSES and not spatially_confirmed:
        return "confirmed_resolved", f"Status='{status}' and no longer detected by Checker."

    # anything else (e.g. 2_Pending with valid justification)
    return "still_active", f"Status='{status}', case remains open (Remaining Case)."


def classify(checker_layer, reference_features, reference_crs):
    """
    Classifies cases into:
      - status_mismatch: attribute rules failed (see evaluate_reference_case)
      - no_status: reference case has a blank/missing status
      - still_active: matched or unmatched, but legitimately still open (Remaining Case)
      - new_cases: checker case has no reference match at all
      - ambiguous: checker case matches more than one reference feature (Manual Review)
      - confirmed_resolved: reference marked resolved, checker no longer detects it
    """
    matches = spatial_match(checker_layer, reference_features, reference_crs)

    status_mismatch, still_active, new_cases, ambiguous, no_status = [], [], [], [], []
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
        elif category == "confirmed_resolved":
            confirmed_resolved.append((rf, reason))
        elif category == "no_status":
            no_status.append((None, rf, reason))
        else:
            still_active.append((None, rf, reason))

    return {
        "status_mismatch": status_mismatch,
        "still_active": still_active,
        "new_cases": new_cases,
        "ambiguous": ambiguous,
        "confirmed_resolved": confirmed_resolved,
        "no_status": no_status,
    }


def output_fields():
    fields = QgsFields()
    fields.append(QgsField("case_uuid", QVariant.String, len=100))
    fields.append(QgsField("case_type", QVariant.String, len=20))
    fields.append(QgsField("audit_flag", QVariant.String, len=40))
    fields.append(QgsField("gmd_remarks", QVariant.String, len=255))
    fields.append(QgsField("ref_status", QVariant.String, len=60))
    fields.append(QgsField("ref_remarks", QVariant.String, len=255))
    fields.append(QgsField("ref_involved_bgys", QVariant.String, len=255))
    return fields


def make_feature(fields, geometry, case_type, audit_flag, remarks, case_uuid="", ref_feature=None):
    nf = QgsFeature(fields)
    nf.setGeometry(QgsGeometry(geometry))
    final_uuid = case_uuid or safe_get(ref_feature, CASE_UUID_FIELD)
    nf.setAttribute("case_uuid", final_uuid)
    nf.setAttribute("case_type", case_type)
    nf.setAttribute("audit_flag", audit_flag)
    nf.setAttribute("gmd_remarks", remarks)
    if ref_feature is not None:
        nf.setAttribute("ref_status", safe_get(ref_feature, STATUS_FIELD))
        nf.setAttribute("ref_remarks", safe_get(ref_feature, REMARKS_FIELD))
        nf.setAttribute("ref_involved_bgys", safe_get(ref_feature, INVOLVED_BGYS_FIELD))
    return nf


# =====================================================
# PROCESSING ALGORITHM
# =====================================================

class MBIStatusAuditAlgorithm(QgsProcessingAlgorithm):

    REF_LAYER = "REF_LAYER"
    CHK_GAP = "CHK_GAP"
    CHK_OVERLAP = "CHK_OVERLAP"

    OUT_MISMATCH = "OUT_MISMATCH"
    OUT_NEW = "OUT_NEW"
    OUT_STILL = "OUT_STILL"
    OUT_RESOLVED = "OUT_RESOLVED"
    OUT_MANUAL_REVIEW = "OUT_MANUAL_REVIEW"
    OUT_NOSTATUS = "OUT_NOSTATUS"

    def tr(self, string):
        return QCoreApplication.translate("MBIStatusAuditAlgorithm", string)

    def createInstance(self):
        return MBIStatusAuditAlgorithm()

    def name(self):
        return "mbi_validator"

    def displayName(self):
        return self.tr("MBI Validator for PMDR")

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
            "Reference layer is required. Leave a Checker input empty if "
            "that case type doesn't apply.\n\n"
            "Outputs (only generated when they contain at least one feature):\n"
            "- Status Mismatch: claimed resolved but still detected, or fails "
            "attribute rules (Pending w/ 0 bldg pts & no remarks; Updated "
            "w/ nonzero bldg pts)\n"
            "- New Cases: Checker case with no Reference match\n"
            "- Remaining Cases: known, legitimately unresolved\n"
            "- Confirmed Resolved: claimed resolved and Checker agrees\n"
            "- No Status: Reference case with blank status\n"
            "- Manual Review: one Checker case overlaps multiple Reference cases"
        )

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

        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_MISMATCH, self.tr("Status Mismatch"), optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_NEW, self.tr("New Cases"), optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_STILL, self.tr("Remaining Cases"), optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_RESOLVED, self.tr("Confirmed Resolved"), optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_MANUAL_REVIEW, self.tr("Manual Review"), optional=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUT_NOSTATUS, self.tr("No Status"), optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        ref_layer = self.parameterAsVectorLayer(parameters, self.REF_LAYER, context)
        chk_g = self.parameterAsVectorLayer(parameters, self.CHK_GAP, context)
        chk_o = self.parameterAsVectorLayer(parameters, self.CHK_OVERLAP, context)

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

        crs = chk_g.sourceCrs() if chk_g else chk_o.sourceCrs()
        wkb = chk_g.wkbType() if chk_g else chk_o.wkbType()
        fields = output_fields()
        ref_crs = ref_layer.sourceCrs()

        # --- collect classified results across GAP/OVERLAP without writing yet ---
        # each entry: (geometry, case_type, audit_flag, remarks, case_uuid, ref_feature)
        collected = {
            "status_mismatch": [],
            "new_cases": [],
            "still_active": [],
            "confirmed_resolved": [],
            "ambiguous": [],
            "no_status": [],
        }

        pairs = []
        if chk_g is not None:
            pairs.append(("GAP", chk_g))
        if chk_o is not None:
            pairs.append(("OVERLAP", chk_o))

        total = len(pairs) or 1
        step = 0

        for case_type, chk_layer in pairs:
            if feedback.isCanceled():
                break

            ref_features = get_reference_subset(ref_layer, case_type)

            result = classify(chk_layer, ref_features, ref_crs)

            for cf, rf, reason in result["status_mismatch"]:
                geom = cf.geometry() if cf is not None else rf.geometry()
                remarks = f"STATUS_MISMATCH: {reason}"
                collected["status_mismatch"].append((geom, case_type, "STATUS_MISMATCH", remarks, "", rf))

            for cf in result["new_cases"]:
                remarks = "NEW_CASE: No matching reference case found."
                chk_uuid = safe_get(cf, CASE_UUID_FIELD)
                collected["new_cases"].append((cf.geometry(), case_type, "NEW_CASE", remarks, chk_uuid, None))

            for cf, rf, reason in result["still_active"]:
                geom = cf.geometry() if cf is not None else rf.geometry()
                remarks = f"REMAINING_CASE: {reason}"
                collected["still_active"].append((geom, case_type, "REMAINING_CASE", remarks, "", rf))

            for cf, rf, reason in result["no_status"]:
                geom = cf.geometry() if cf is not None else rf.geometry()
                remarks = f"NO_STATUS: {reason}"
                collected["no_status"].append((geom, case_type, "NO_STATUS", remarks, "", rf))

            for rf, reason in result["confirmed_resolved"]:
                remarks = f"CONFIRMED_RESOLVED: {reason}"
                collected["confirmed_resolved"].append((rf.geometry(), case_type, "CONFIRMED_RESOLVED", remarks, "", rf))

            for cf, matched_refs in result["ambiguous"]:
                uuids = ", ".join(safe_get(rf, CASE_UUID_FIELD) or str(rf.id()) for rf in matched_refs)
                remarks = f"MANUAL_REVIEW: Matches {len(matched_refs)} reference cases ({uuids}). Review manually."
                chk_uuid = safe_get(cf, CASE_UUID_FIELD)
                collected["ambiguous"].append((cf.geometry(), case_type, "MANUAL_REVIEW", remarks, chk_uuid, None))

            step += 1
            feedback.setProgress(int(100 * step / total))

        # reference-only case types (no matching checker layer provided at all)
        for case_type, chk_layer in (("GAP", chk_g), ("OVERLAP", chk_o)):
            if chk_layer is None:
                for rf in get_reference_subset(ref_layer, case_type):
                    category, reason = evaluate_reference_case(rf, spatially_confirmed=False)
                    if category == "status_mismatch":
                        remarks = f"STATUS_MISMATCH: {reason}"
                        collected["status_mismatch"].append((rf.geometry(), case_type, "STATUS_MISMATCH", remarks, "", rf))
                    elif category == "confirmed_resolved":
                        remarks = f"CONFIRMED_RESOLVED: {reason} (no Checker layer provided.)"
                        collected["confirmed_resolved"].append((rf.geometry(), case_type, "CONFIRMED_RESOLVED", remarks, "", rf))
                    elif category == "no_status":
                        remarks = f"NO_STATUS: {reason}"
                        collected["no_status"].append((rf.geometry(), case_type, "NO_STATUS", remarks, "", rf))
                    else:
                        remarks = f"REMAINING_CASE: {reason}"
                        collected["still_active"].append((rf.geometry(), case_type, "REMAINING_CASE", remarks, "", rf))

        # --- only create sinks / outputs for categories with at least 1 feature ---
        output_map = (
            (self.OUT_MISMATCH, "status_mismatch"),
            (self.OUT_NEW, "new_cases"),
            (self.OUT_STILL, "still_active"),
            (self.OUT_RESOLVED, "confirmed_resolved"),
            (self.OUT_MANUAL_REVIEW, "ambiguous"),
            (self.OUT_NOSTATUS, "no_status"),
        )

        results = {}
        counts = {}

        for out_key, coll_key in output_map:
            items = collected[coll_key]
            counts[coll_key] = len(items)

            if not items:
                # skip creating this output entirely -> keeps Layers panel clean
                continue

            sink, dest_id = self.parameterAsSink(parameters, out_key, context, fields, wkb, crs)
            if sink is None:
                # user didn't set a destination for this optional output -> skip silently
                continue

            for geom, case_type, audit_flag, remarks, case_uuid, ref_feature in items:
                sink.addFeature(
                    make_feature(fields, geom, case_type, audit_flag, remarks,
                                 case_uuid=case_uuid, ref_feature=ref_feature)
                )

            results[out_key] = dest_id

        feedback.pushInfo(
            f"Status Mismatch: {counts['status_mismatch']} | New Cases: {counts['new_cases']} | "
            f"Remaining Cases: {counts['still_active']} | No Status: {counts['no_status']} | "
            f"Confirmed Resolved: {counts['confirmed_resolved']} | Manual Review: {counts['ambiguous']}"
        )

        return results


# Alias for naming consistency
MbiValidatorAlgorithm = MBIStatusAuditAlgorithm
