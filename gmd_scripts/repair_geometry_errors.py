import os
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingFeedback,
    QgsProcessingContext,
    QgsProcessingUtils,
    QgsFeatureSink,
    QgsFeature,
    QgsGeometry,
    QgsFields,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsFeatureRequest,
    QgsProject
)
import processing


def resolve_processing_output_layer(output_value, context):
    """Return a QgsVectorLayer whether Processing returns a layer object or a layer id/path string."""
    if isinstance(output_value, QgsVectorLayer):
        return output_value
    return QgsProcessingUtils.mapLayerFromString(output_value, context)


def clean_geom(geom):
    """Extract and validate clean Polygon/MultiPolygon geometry."""
    if geom is None or geom.isEmpty():
        return None
    g = QgsGeometry(geom)
    try:
        if not g.isGeosValid():
            g = g.makeValid()
    except Exception:
        pass
    if QgsWkbTypes.geometryType(g.wkbType()) == QgsWkbTypes.PolygonGeometry:
        return g
    try:
        tmp = QgsGeometry(g)
        if tmp.convertGeometryCollectionToSubclass(QgsWkbTypes.PolygonGeometry):
            return tmp
    except Exception:
        pass
    return None


def force_single(geom):
    if geom is None or geom.isEmpty():
        return None
    g = QgsGeometry(geom)
    if not g.isMultipart():
        return g
    parts = [
        p for p in g.asGeometryCollection()
        if p and not p.isEmpty() and QgsWkbTypes.geometryType(p.wkbType()) == QgsWkbTypes.PolygonGeometry
    ]
    return max(parts, key=lambda x: x.area()) if parts else None


def is_valid_polygon_geom(geom):
    if geom is None or geom.isEmpty():
        return False
    try:
        if QgsWkbTypes.geometryType(geom.wkbType()) != QgsWkbTypes.PolygonGeometry:
            return False
    except Exception:
        return False
    try:
        return geom.isGeosValid()
    except Exception:
        return True


def fit_output_wkb(geom, output_wkb):
    if geom is None or geom.isEmpty():
        return None
    g = QgsGeometry(geom)
    SINGLE = (
        QgsWkbTypes.Polygon, QgsWkbTypes.Polygon25D,
        QgsWkbTypes.PolygonZ, QgsWkbTypes.PolygonM, QgsWkbTypes.PolygonZM
    )
    if output_wkb in SINGLE or QgsWkbTypes.flatType(output_wkb) == QgsWkbTypes.Polygon:
        g = force_single(g)
    else:
        try:
            if QgsWkbTypes.isMultiType(output_wkb) and not g.isMultipart():
                g.convertToMultiType()
        except Exception:
            pass
    return g


def clean_try_makevalid_buffer(geom, output_wkb):
    if geom is None or geom.isEmpty():
        return None
    g = clean_geom(geom)
    if g is None or g.isEmpty():
        return None
    try:
        if not g.isGeosValid():
            mg = g.makeValid()
            if mg and not mg.isEmpty():
                g = clean_geom(mg)
    except Exception:
        pass
    try:
        if g is not None and not g.isEmpty() and not g.isGeosValid():
            bg = g.buffer(0, 8)
            if bg and not bg.isEmpty():
                g = clean_geom(bg)
    except Exception:
        pass
    g = fit_output_wkb(g, output_wkb)
    if is_valid_polygon_geom(g):
        return g
    return None


def repair_micro_self_intersection_spike(geom, output_wkb):
    """Fallback for micro self-intersection spikes/loops on polygon edges using grid snapping."""
    if geom is None or geom.isEmpty():
        return None

    base = QgsGeometry(geom)
    try:
        bb = base.boundingBox()
        diag = ((bb.width() ** 2) + (bb.height() ** 2)) ** 0.5
    except Exception:
        diag = 0
    if not diag or diag <= 0:
        diag = 1.0

    tolerances = [
        diag * f for f in (
            1e-12, 5e-12, 1e-11, 5e-11, 1e-10, 5e-10,
            1e-9, 5e-9, 1e-8, 5e-8, 1e-7, 5e-7, 1e-6
        )
    ]
    tried = []
    for tol in tolerances:
        if tol <= 0:
            continue
        try:
            g1 = QgsGeometry(base)
            g1.removeDuplicateNodes(tol, True)
            tried.append(g1)
        except Exception:
            pass
        try:
            tried.append(base.snappedToGrid(tol, tol))
        except Exception:
            pass
        try:
            tried.append(base.simplify(tol))
        except Exception:
            pass

        for candidate in tried[-3:]:
            fixed = clean_try_makevalid_buffer(candidate, output_wkb)
            if fixed and not fixed.isEmpty():
                return fixed

    return None


def raw_makevalid_last_resort(geom, output_wkb):
    if geom is None or geom.isEmpty():
        return None
    try:
        raw_fix = geom.makeValid()
    except Exception:
        return None
    if not raw_fix or raw_fix.isEmpty():
        return None
    raw_fit = fit_output_wkb(raw_fix, output_wkb)
    if raw_fit and is_valid_polygon_geom(raw_fit):
        return raw_fit
    return None


def finalize_fixed_geom(geom, output_wkb):
    g = clean_try_makevalid_buffer(geom, output_wkb)
    if g and not g.isEmpty():
        return g
    g = repair_micro_self_intersection_spike(geom, output_wkb)
    if g and not g.isEmpty():
        return g
    return None


def qgis_fix_single_feature_fallback(source_crs, fields, source_wkb, feat, context, feedback):
    """Runs QGIS native:fixgeometries on an individual feature record as fallback."""
    try:
        tmp = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(source_wkb)}?crs={source_crs.authid()}",
            "single_fix_input",
            "memory"
        )
        tmp.setCrs(source_crs)
        tmp.dataProvider().addAttributes(fields)
        tmp.updateFields()

        tf = QgsFeature(fields)
        tf.setAttributes(feat.attributes())
        tf.setGeometry(feat.geometry())
        ok, _ = tmp.dataProvider().addFeatures([tf])
        tmp.updateExtents()

        if (not ok) or tmp.featureCount() == 0:
            extracted = clean_geom(feat.geometry())
            if extracted is None or extracted.isEmpty():
                return None
            tmp = QgsVectorLayer(
                f"{QgsWkbTypes.displayString(source_wkb)}?crs={source_crs.authid()}",
                "single_fix_input_extracted",
                "memory"
            )
            tmp.setCrs(source_crs)
            tmp.dataProvider().addAttributes(fields)
            tmp.updateFields()
            tf = QgsFeature(fields)
            tf.setAttributes(feat.attributes())
            tf.setGeometry(extracted)
            ok, _ = tmp.dataProvider().addFeatures([tf])
            tmp.updateExtents()
            if (not ok) or tmp.featureCount() == 0:
                return None

        res = processing.run(
            "native:fixgeometries",
            {"INPUT": tmp, "METHOD": 1, "OUTPUT": "TEMPORARY_OUTPUT"},
            context=context,
            feedback=feedback,
            is_child_algorithm=False
        )
        fixed_layer = resolve_processing_output_layer(res["OUTPUT"], context)
        if fixed_layer is None or fixed_layer.featureCount() == 0:
            return None

        best = None
        for ff in fixed_layer.getFeatures(QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)):
            fg = finalize_fixed_geom(ff.geometry(), source_wkb)
            if fg is None or fg.isEmpty():
                continue
            try:
                if fg.isGeosValid():
                    if best is None or fg.area() > best.area():
                        best = fg
            except Exception:
                if best is None or fg.area() > best.area():
                    best = fg
        return best
    except Exception:
        return None


class RepairGeometryErrorsAlgorithm(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm that repairs invalid, self-intersecting, wrong-type,
    null, or empty polygon geometries using the complete GMD multi-stage polygonize,
    grid-snapping spike removal, and native fixgeometries fallback pipeline.
    """

    INPUT = 'INPUT'
    REPAIR_MODE = 'REPAIR_MODE'
    OUTPUT = 'OUTPUT'

    MODE_ALL = 0
    MODE_INVALID_ONLY = 1
    MODE_NULL_ONLY = 2

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return RepairGeometryErrorsAlgorithm()

    def name(self):
        return 'repairpolygongeometries'

    def displayName(self):
        return self.tr('Repair Polygon Geometries')

    def group(self):
        return self.tr('GMD Toolkits')

    def groupId(self):
        return 'gmdtoolkits'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'repair_geom.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return self.tr(
            "Reconstructs invalid, self-intersecting, or wrong-type polygon geometries and "
            "recovers null/empty polygon shapes into a clean vector output layer.\n\n"
            "Uses the complete GMD repair pipeline (Polygons to Lines -> Polygonize -> Candidate Face "
            "Intersection & UnaryUnion -> Micro Spike Grid-Snapping -> QGIS Fix Geometries Fallback).\n\n"
            "Supports QGIS native 'Selected features only' selection."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input Polygon Layer'),
                types=[QgsProcessing.TypeVectorPolygon]
            )
        )

        modes = [
            self.tr('Auto-Detect & Repair All Issues'),
            self.tr('Reconstruct Invalid / Self-Intersecting / Wrong-Type Geometries Only'),
            self.tr('Recover Null / Empty Geometries Only')
        ]

        self.addParameter(
            QgsProcessingParameterEnum(
                self.REPAIR_MODE,
                self.tr('Repair Mode'),
                options=modes,
                defaultValue=self.MODE_ALL
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Repaired Polygon Layer'),
                type=QgsProcessing.TypeVectorPolygon
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise Exception(self.invalidSourceError(parameters, self.INPUT))

        repair_mode = self.parameterAsEnum(parameters, self.REPAIR_MODE, context)

        source_crs = source.sourceCrs()
        source_wkb = source.wkbType()
        fields = source.fields()

        out_wkb = QgsWkbTypes.multiType(source_wkb)

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            out_wkb,
            source_crs
        )

        if sink is None:
            raise Exception(self.invalidSinkError(parameters, self.OUTPUT))

        features = list(source.getFeatures(QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)))
        total_feats = len(features)

        # Identify features requiring repair vs clean features
        feats_to_fix = []
        clean_feats = []

        for feat in features:
            geom = feat.geometry()
            is_null_empty = geom is None or geom.isNull() or geom.isEmpty()
            is_invalid = not is_null_empty and (not geom.isGeosValid() or not geom.isSimple())

            should_fix_null = is_null_empty and (repair_mode in [self.MODE_ALL, self.MODE_NULL_ONLY])
            should_fix_invalid = is_invalid and (repair_mode in [self.MODE_ALL, self.MODE_INVALID_ONLY])

            if should_fix_invalid or should_fix_null:
                feats_to_fix.append(feat)
            else:
                clean_feats.append(feat)

        feedback.pushInfo(f"Total features: {total_feats}, Features to repair: {len(feats_to_fix)}, Clean features: {len(clean_feats)}")

        # If no features require repair, copy clean features straight to sink
        if not feats_to_fix:
            for f in clean_feats:
                out = QgsFeature(fields)
                out.setAttributes(f.attributes())
                out.setGeometry(f.geometry())
                sink.addFeature(out, QgsFeatureSink.FastInsert)
            return {self.OUTPUT: dest_id}

        # Build temporary layer of features to repair for Polygons to Lines -> Polygonize
        temp_input = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(out_wkb)}?crs={source_crs.authid()}",
            "temp_repair_input",
            "memory"
        )
        temp_input.setCrs(source_crs)
        temp_input.dataProvider().addAttributes(fields)
        temp_input.updateFields()
        temp_input.startEditing()
        for f in feats_to_fix:
            nf = QgsFeature(fields)
            nf.setAttributes(f.attributes())
            nf.setGeometry(f.geometry())
            temp_input.addFeature(nf)
        temp_input.commitChanges()

        # Step 1: Polygons to Lines
        feedback.setProgress(10)
        feedback.pushInfo("Running Polygons to Lines on target features...")
        try:
            lr = processing.run(
                "native:polygonstolines",
                {"INPUT": temp_input, "OUTPUT": "TEMPORARY_OUTPUT"},
                context=context,
                feedback=feedback,
                is_child_algorithm=True
            )
            ll = resolve_processing_output_layer(lr["OUTPUT"], context)
        except Exception as e:
            feedback.pushInfo(f"Polygons to lines failed: {e}")
            ll = None

        # Step 2: Polygonize
        p_lookup = {}
        p_idx = QgsSpatialIndex()
        if ll and ll.featureCount() > 0:
            feedback.setProgress(25)
            feedback.pushInfo("Polygonizing boundary lines into candidate faces...")
            try:
                pr = processing.run(
                    "native:polygonize",
                    {"INPUT": ll, "KEEP_FIELDS": False, "OUTPUT": "TEMPORARY_OUTPUT"},
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True
                )
                pl = resolve_processing_output_layer(pr["OUTPUT"], context)
                if pl:
                    for pf in pl.getFeatures():
                        cg = clean_geom(pf.geometry())
                        if cg and not cg.isEmpty():
                            pf.setGeometry(cg)
                            p_idx.addFeature(pf)
                            p_lookup[pf.id()] = pf
            except Exception as e:
                feedback.pushInfo(f"Polygonize failed: {e}")

        # Step 3: Candidate Face Intersection & Re-Union
        feedback.setProgress(50)
        feedback.pushInfo("Reconstructing geometries and evaluating fallbacks...")

        repaired_count = 0
        touched_attrs = set()

        for i, feat in enumerate(features):
            if feedback.isCanceled():
                break

            feedback.setProgress(50 + int((i / max(1, total_feats)) * 40))
            out = QgsFeature(fields)
            out.setAttributes(feat.attributes())
            orig = feat.geometry()

            is_null_empty = orig is None or orig.isNull() or orig.isEmpty()
            is_invalid = not is_null_empty and (not orig.isGeosValid() or not orig.isSimple())

            should_fix_null = is_null_empty and (repair_mode in [self.MODE_ALL, self.MODE_NULL_ONLY])
            should_fix_invalid = is_invalid and (repair_mode in [self.MODE_ALL, self.MODE_INVALID_ONLY])

            if not should_fix_invalid and not should_fix_null:
                out.setGeometry(orig)
                sink.addFeature(out, QgsFeatureSink.FastInsert)
                continue

            touched_attrs.add(tuple(out.attributes()))
            co = clean_geom(orig)
            if co is None or co.isEmpty():
                try:
                    co = clean_geom(orig.makeValid())
                except Exception:
                    co = None

            if co is None or co.isEmpty():
                qfix = qgis_fix_single_feature_fallback(source_crs, fields, source_wkb, feat, context, feedback)
                if qfix and not qfix.isEmpty():
                    out.setGeometry(fit_output_wkb(qfix, out_wkb))
                    sink.addFeature(out, QgsFeatureSink.FastInsert)
                    repaired_count += 1
                    continue

                raw_fit = raw_makevalid_last_resort(orig, source_wkb)
                if raw_fit:
                    out.setGeometry(fit_output_wkb(raw_fit, out_wkb))
                    sink.addFeature(out, QgsFeatureSink.FastInsert)
                    repaired_count += 1
                    continue

                out.setGeometry(orig)
                sink.addFeature(out, QgsFeatureSink.FastInsert)
                continue

            cands = []
            if p_lookup:
                for cid in p_idx.intersects(co.boundingBox()):
                    pf = p_lookup.get(cid)
                    if not pf:
                        continue
                    pg = pf.geometry()
                    if pg is None or pg.isEmpty():
                        continue
                    try:
                        if pg.intersects(co):
                            inter = pg.intersection(co)
                            if inter and not inter.isEmpty() and inter.area() > 0:
                                cands.append(inter)
                    except Exception:
                        if pg.boundingBox().intersects(co.boundingBox()):
                            try:
                                clipped = pg.intersection(co)
                                cands.append(clipped if clipped and not clipped.isEmpty() else pg)
                            except Exception:
                                cands.append(pg)

            if cands:
                ng = QgsGeometry.unaryUnion(cands)
                ng = finalize_fixed_geom(ng, source_wkb)
                if ng and not ng.isEmpty():
                    out.setGeometry(fit_output_wkb(ng, out_wkb))
                    sink.addFeature(out, QgsFeatureSink.FastInsert)
                    repaired_count += 1
                else:
                    fallback = finalize_fixed_geom(co, source_wkb)
                    if fallback and not fallback.isEmpty():
                        out.setGeometry(fit_output_wkb(fallback, out_wkb))
                        sink.addFeature(out, QgsFeatureSink.FastInsert)
                        repaired_count += 1
                    else:
                        qfix = qgis_fix_single_feature_fallback(source_crs, fields, source_wkb, feat, context, feedback)
                        if qfix and not qfix.isEmpty():
                            out.setGeometry(fit_output_wkb(qfix, out_wkb))
                            sink.addFeature(out, QgsFeatureSink.FastInsert)
                            repaired_count += 1
                        else:
                            raw_fit = raw_makevalid_last_resort(orig, source_wkb)
                            if raw_fit:
                                out.setGeometry(fit_output_wkb(raw_fit, out_wkb))
                                sink.addFeature(out, QgsFeatureSink.FastInsert)
                                repaired_count += 1
                            else:
                                out.setGeometry(orig)
                                sink.addFeature(out, QgsFeatureSink.FastInsert)
            else:
                fallback = finalize_fixed_geom(co, source_wkb)
                if fallback and not fallback.isEmpty():
                    out.setGeometry(fit_output_wkb(fallback, out_wkb))
                    sink.addFeature(out, QgsFeatureSink.FastInsert)
                    repaired_count += 1
                else:
                    qfix = qgis_fix_single_feature_fallback(source_crs, fields, source_wkb, feat, context, feedback)
                    if qfix and not qfix.isEmpty():
                        out.setGeometry(fit_output_wkb(qfix, out_wkb))
                        sink.addFeature(out, QgsFeatureSink.FastInsert)
                        repaired_count += 1
                    else:
                        raw_fit = raw_makevalid_last_resort(orig, source_wkb)
                        if raw_fit:
                            out.setGeometry(fit_output_wkb(raw_fit, out_wkb))
                            sink.addFeature(out, QgsFeatureSink.FastInsert)
                            repaired_count += 1
                        else:
                            out.setGeometry(orig)
                            sink.addFeature(out, QgsFeatureSink.FastInsert)

        feedback.setProgress(100)
        feedback.pushInfo(f"Repair process finished. Total features repaired/processed: {repaired_count}")
        return {self.OUTPUT: dest_id}
