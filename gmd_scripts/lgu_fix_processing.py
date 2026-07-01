import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsFeatureSink,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsProcessingOutputNumber,
)


class FixLGUCRSAlgorithm(QgsProcessingAlgorithm):

    INPUT  = "INPUT"
    REF    = "REF"
    OUTPUT = "OUTPUT"
    SCALE  = "SCALE"
    TX     = "TX"
    TY     = "TY"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def createInstance(self):
        return FixLGUCRSAlgorithm()

    def name(self) -> str:
        return "fixlgucrs"

    def displayName(self) -> str:
        return self.tr("Fix LGU CRS / Geometry")
    def icon(self):
            return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons/crs.png'))

    def group(self) -> str:
        return self.tr("1Map")

    def groupId(self) -> str:
        return "1map"

    def shortHelpString(self) -> str:
        return self.tr("""<html><body>
<p>Repositions an LGU layer to match a reference layer using scale and translation based on bounding box comparison. Output is saved in <b>EPSG:4326</b>.</p>

<h3>Inputs</h3>
<ul>
  <li><b>LGU Layer</b> – the layer to be corrected</li>
  <li><b>Reference Layer</b> – a correctly positioned layer to align to</li>
</ul>

<h3>Outputs</h3>
<ul>
  <li><b>Fixed Layer</b> – corrected geometry in EPSG:4326</li>
  <li><b>Scale, TX, TY</b> – computed transform values (visible in Results panel)</li>
</ul>

<p><i>Both layers must be loaded in the QGIS project before running.</i></p>
</body></html>""")

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr("LGU Layer"),
                [QgsProcessing.SourceType.TypeVectorAnyGeometry],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.REF,
                self.tr("Reference Layer"),
                [QgsProcessing.SourceType.TypeVectorAnyGeometry],
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr("Fixed Layer"),
            )
        )
        self.addOutput(QgsProcessingOutputNumber(self.SCALE, self.tr("Scale factor")))
        self.addOutput(QgsProcessingOutputNumber(self.TX,    self.tr("Translation X")))
        self.addOutput(QgsProcessingOutputNumber(self.TY,    self.tr("Translation Y")))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        ref    = self.parameterAsSource(parameters, self.REF,   context)

        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        if ref is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.REF))

        lgu_ext = source.sourceExtent()
        ref_ext = ref.sourceExtent()
        lgu_width = lgu_ext.width()

        if lgu_width == 0:
            raise QgsProcessingException(
                self.tr("LGU layer has zero-width bounding box — cannot compute scale.")
            )

        scale = ref_ext.width() / lgu_width
        lgu_center = lgu_ext.center()
        ref_center = ref_ext.center()
        tx = ref_center.x() - (lgu_center.x() * scale)
        ty = ref_center.y() - (lgu_center.y() * scale)

        feedback.pushInfo(f"Transform — scale: {scale:.8f}  tx: {tx:.6f}  ty: {ty:.6f}")

        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context,
            source.fields(), source.wkbType(), target_crs,
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        feature_count = source.featureCount()
        total = 100.0 / feature_count if feature_count else 0

        for current, feature in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            new_geom = self._transform_geom(feature.geometry(), scale, tx, ty)
            out_feature = QgsFeature(feature)
            out_feature.setGeometry(new_geom)
            sink.addFeature(out_feature, QgsFeatureSink.Flag.FastInsert)
            feedback.setProgress(int(current * total))

        feedback.pushInfo(self.tr(f"Done. {feature_count} feature(s) written to output."))

        return {
            self.OUTPUT: dest_id,
            self.SCALE:  scale,
            self.TX:     tx,
            self.TY:     ty,
        }

    def _transform_geom(self, geom: QgsGeometry, scale: float, tx: float, ty: float) -> QgsGeometry:
        if geom is None or geom.isNull() or geom.isEmpty():
            return geom

        def _xform_point(pt) -> QgsPointXY:
            return QgsPointXY(pt.x() * scale + tx, pt.y() * scale + ty)

        wkb_type = geom.wkbType()

        if QgsWkbTypes.geometryType(wkb_type) == QgsWkbTypes.PolygonGeometry:
            rings = []
            for part in geom.asGeometryCollection() or [geom]:
                poly = part.asPolygon()
                if not poly:
                    continue
                rings.extend([[_xform_point(pt) for pt in ring] for ring in poly])
            return QgsGeometry.fromPolygonXY(rings) if rings else geom

        if QgsWkbTypes.geometryType(wkb_type) == QgsWkbTypes.MultiPolygonGeometry:
            multi = []
            for part in geom.asGeometryCollection():
                poly = part.asPolygon()
                if not poly:
                    continue
                multi.append([[_xform_point(pt) for pt in ring] for ring in poly])
            return QgsGeometry.fromMultiPolygonXY(multi)

        clone = QgsGeometry(geom)

        def _map_vertex(pt, vertex_id):
            return QgsPoint(pt.x() * scale + tx, pt.y() * scale + ty)

        clone.mapToVertex(_map_vertex)
        return clone