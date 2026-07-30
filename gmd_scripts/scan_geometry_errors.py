import os
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingFeedback,
    QgsFeatureSink,
    QgsFeature,
    QgsGeometry,
    QgsFields,
    QgsField,
    QgsWkbTypes,
    QgsPointXY,
    QgsSpatialIndex,
    QgsRectangle
)


def precise_invalidity_point(geom: QgsGeometry) -> QgsGeometry:
    """Find precise error point from GEOS geometry validation if possible."""
    try:
        errors = geom.validateGeometry()
        if errors:
            pt = errors[0].where()
            return QgsGeometry.fromPointXY(pt)
    except Exception:
        pass
    if geom and not geom.isEmpty():
        return geom.centroid()
    return QgsGeometry()


class ScanGeometryErrorsAlgorithm(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm that scans vector polygon layers for specific geometry
    and topology defects and outputs a Point Vector Sink containing error locations and metadata.
    """

    INPUT = 'INPUT'
    CHECK_NULL = 'CHECK_NULL'
    CHECK_EMPTY = 'CHECK_EMPTY'
    CHECK_INVALID = 'CHECK_INVALID'
    CHECK_SELF_INTERSECT = 'CHECK_SELF_INTERSECT'
    CHECK_WRONG_TYPE = 'CHECK_WRONG_TYPE'
    CHECK_DUPLICATE = 'CHECK_DUPLICATE'
    OUTPUT_ERRORS = 'OUTPUT_ERRORS'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ScanGeometryErrorsAlgorithm()

    def name(self):
        return 'scangeometryerrors'

    def displayName(self):
        return self.tr('Scan Geometry Errors')

    def group(self):
        return self.tr('GMD Toolkits')

    def groupId(self):
        return 'gmdtoolkits'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'scan_errors.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return self.tr(
            "Scans an input polygon vector layer for geometry and topology errors such as "
            "Null, Empty, Invalid GEOS geometries, Self-Intersections, Wrong Geometry Types, and "
            "Duplicate Geometries.\n\n"
            "Outputs an Error Point Layer containing exact error locations and descriptive attributes "
            "(source_fid, error_type, description, is_autofixable) for audit and map visualization."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input Polygon Layer'),
                types=[QgsProcessing.TypeVectorPolygon]
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CHECK_NULL,
                self.tr('Check Null Geometries'),
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CHECK_EMPTY,
                self.tr('Check Empty Geometries'),
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CHECK_INVALID,
                self.tr('Check Invalid Geometries (GEOS)'),
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CHECK_SELF_INTERSECT,
                self.tr('Check Self Intersections'),
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CHECK_WRONG_TYPE,
                self.tr('Check Wrong Geometry Types'),
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CHECK_DUPLICATE,
                self.tr('Check Duplicate Geometries'),
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_ERRORS,
                self.tr('Error Locations (Point Layer)'),
                type=QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise Exception(self.invalidSourceError(parameters, self.INPUT))

        chk_null = self.parameterAsBool(parameters, self.CHECK_NULL, context)
        chk_empty = self.parameterAsBool(parameters, self.CHECK_EMPTY, context)
        chk_invalid = self.parameterAsBool(parameters, self.CHECK_INVALID, context)
        chk_self = self.parameterAsBool(parameters, self.CHECK_SELF_INTERSECT, context)
        chk_wrong = self.parameterAsBool(parameters, self.CHECK_WRONG_TYPE, context)
        chk_dup = self.parameterAsBool(parameters, self.CHECK_DUPLICATE, context)

        # Output Fields
        fields = QgsFields()
        fields.append(QgsField('source_fid', QVariant.LongLong))
        fields.append(QgsField('layer_name', QVariant.String))
        fields.append(QgsField('error_type', QVariant.String))
        fields.append(QgsField('description', QVariant.String))
        fields.append(QgsField('is_autofixable', QVariant.Bool))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_ERRORS,
            context,
            fields,
            QgsWkbTypes.Point,
            source.sourceCrs()
        )

        if sink is None:
            raise Exception(self.invalidSinkError(parameters, self.OUTPUT_ERRORS))

        source_name = source.sourceName() if hasattr(source, 'sourceName') else 'Input Layer'
        layer_wkb = source.wkbType()
        geom_type = QgsWkbTypes.geometryType(layer_wkb)

        features = list(source.getFeatures())
        total_feats = len(features)
        spatial_index = QgsSpatialIndex() if chk_dup else None
        feat_map = {}

        error_count = 0

        # Pass 1: Single Feature Checks
        for i, feat in enumerate(features):
            if feedback.isCanceled():
                break

            feedback.setProgress(int((i / max(1, total_feats)) * 70))
            fid = feat.id()
            geom = feat.geometry()

            # Null Check
            if chk_null and (geom is None or geom.isNull()):
                err_feat = QgsFeature(fields)
                err_feat.setAttributes([fid, source_name, 'Null Geometry', 'Feature has no geometry object', True])
                sink.addFeature(err_feat, QgsFeatureSink.FastInsert)
                error_count += 1
                continue

            # Empty Check
            if chk_empty and geom.isEmpty():
                err_feat = QgsFeature(fields)
                err_feat.setAttributes([fid, source_name, 'Empty Geometry', 'Feature geometry has no coordinates or shape', True])
                sink.addFeature(err_feat, QgsFeatureSink.FastInsert)
                error_count += 1
                continue

            # GEOS Invalid Check
            if chk_invalid and not geom.isGeosValid():
                err_pt = precise_invalidity_point(geom)
                err_feat = QgsFeature(fields)
                err_feat.setGeometry(err_pt)
                err_feat.setAttributes([fid, source_name, 'Invalid Geometry', 'Geometry fails GEOS validity test', True])
                sink.addFeature(err_feat, QgsFeatureSink.FastInsert)
                error_count += 1

            # Self Intersection Check
            if chk_self and not geom.isSimple():
                err_pt = precise_invalidity_point(geom)
                err_feat = QgsFeature(fields)
                err_feat.setGeometry(err_pt)
                err_feat.setAttributes([fid, source_name, 'Self Intersection', 'Polygon boundary crosses itself', True])
                sink.addFeature(err_feat, QgsFeatureSink.FastInsert)
                error_count += 1

            # Wrong Type Check
            if chk_wrong and QgsWkbTypes.geometryType(geom.wkbType()) != geom_type:
                err_pt = geom.centroid() if not geom.isEmpty() else QgsGeometry()
                err_feat = QgsFeature(fields)
                err_feat.setGeometry(err_pt)
                err_feat.setAttributes([
                    fid, source_name, 'Wrong-type Geometry',
                    f'Feature geometry ({QgsWkbTypes.displayString(geom.wkbType())}) does not match layer type ({QgsWkbTypes.displayString(layer_wkb)})',
                    True
                ])
                sink.addFeature(err_feat, QgsFeatureSink.FastInsert)
                error_count += 1

            if chk_dup:
                feat_map[fid] = feat
                spatial_index.addFeature(feat)

        # Pass 2: Spatial Index Duplicate Checks
        if chk_dup and not feedback.isCanceled():
            processed_pairs = set()
            for i, feat in enumerate(features):
                if feedback.isCanceled():
                    break
                feedback.setProgress(70 + int((i / max(1, total_feats)) * 30))
                fid = feat.id()
                geom = feat.geometry()
                if geom is None or geom.isNull() or geom.isEmpty():
                    continue

                for cid in spatial_index.intersects(geom.boundingBox()):
                    if cid == fid:
                        continue
                    pair = (min(fid, cid), max(fid, cid))
                    if pair in processed_pairs:
                        continue
                    processed_pairs.add(pair)

                    other_feat = feat_map.get(cid)
                    if other_feat and other_feat.hasGeometry():
                        if geom.equals(other_feat.geometry()):
                            err_feat = QgsFeature(fields)
                            err_feat.setGeometry(geom.centroid())
                            err_feat.setAttributes([
                                fid, source_name, 'Duplicate Geometry',
                                f'Exact duplicate geometry of feature {cid}',
                                False
                            ])
                            sink.addFeature(err_feat, QgsFeatureSink.FastInsert)
                            error_count += 1

        feedback.pushInfo(f'Scan completed. Total errors found: {error_count}')
        return {self.OUTPUT_ERRORS: dest_id}
