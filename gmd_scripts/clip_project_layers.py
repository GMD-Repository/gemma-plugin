import os
import re
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterDistance,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingFeedback,
    QgsProcessingContext,
    QgsProcessingUtils,
    QgsVectorLayer,
    QgsFeatureSink
)
import processing


class ClipProjectLayersAlgorithm(QgsProcessingAlgorithm):
    """
    QGIS Processing Algorithm that clips multiple vector layers in batch to a target
    administrative or enumeration boundary mask polygon with an optional buffer margin.
    Exports clean clipped GeoPackage files to a target output folder.
    """

    INPUT_VECTORS = 'INPUT_VECTORS'
    MASK = 'MASK'
    BUFFER = 'BUFFER'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    OVERWRITE = 'OVERWRITE'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ClipProjectLayersAlgorithm()

    def name(self):
        return 'clipprojectlayers'

    def displayName(self):
        return self.tr('Clip Project Layers by Extent')

    def group(self):
        return self.tr('GMD Toolkits')

    def groupId(self):
        return 'gmdtoolkits'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'clip_layers.svg')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon(":/images/themes/default/mActionFilter.svg")

    def shortHelpString(self):
        return self.tr(
            "Batch clips multiple vector layers to a target administrative polygon boundary (such as an EA or Barangay) "
            "with an optional buffer margin.\n\n"
            "Exports clipped vector layers as standalone GeoPackage (*.gpkg) files into the target output folder."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_VECTORS,
                self.tr('Input Vector Layers'),
                QgsProcessing.TypeVector
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.MASK,
                self.tr('Mask Layer / Boundary Polygon'),
                [QgsProcessing.TypeVectorPolygon]
            )
        )

        self.addParameter(
            QgsProcessingParameterDistance(
                self.BUFFER,
                self.tr('Mask Buffer Distance'),
                defaultValue=0.0,
                parentParameterName=self.MASK
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr('Output Folder for Clipped GeoPackages')
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.OVERWRITE,
                self.tr('Overwrite Existing Files'),
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.INPUT_VECTORS, context)
        mask_source = self.parameterAsSource(parameters, self.MASK, context)
        buffer_dist = self.parameterAsDouble(parameters, self.BUFFER, context)
        out_dir = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        overwrite = self.parameterAsBool(parameters, self.OVERWRITE, context)

        if not layers:
            raise Exception(self.tr("No input vector layers selected for clipping."))
        if mask_source is None:
            raise Exception(self.tr("Mask layer is invalid or empty."))
        if not out_dir:
            raise Exception(self.tr("Output folder destination must be specified."))

        os.makedirs(out_dir, exist_ok=True)
        feedback.pushInfo(f"Output folder: {out_dir}")
        feedback.pushInfo(f"Input vector layer count: {len(layers)}")

        # Step 1: Prepare Mask / Buffered Overlay
        overlay_param = parameters[self.MASK]
        if buffer_dist > 0.0:
            feedback.pushInfo(f"Applying buffer margin of {buffer_dist} to mask geometry...")
            buffered = processing.run(
                "native:buffer",
                {
                    'INPUT': parameters[self.MASK],
                    'DISTANCE': buffer_dist,
                    'SEGMENTS': 8,
                    'END_CAP_STYLE': 0,
                    'JOIN_STYLE': 0,
                    'MITER_LIMIT': 2,
                    'DISSOLVE': True,
                    'OUTPUT': 'TEMPORARY_OUTPUT'
                },
                context=context,
                feedback=feedback,
                is_child_algorithm=True
            )
            overlay_param = buffered['OUTPUT']

        total_layers = len(layers)
        clipped_count = 0

        # Step 2: Batch Clip Each Input Vector Layer
        for i, layer in enumerate(layers):
            if feedback.isCanceled():
                break

            layer_name = layer.name()
            feedback.pushInfo(f"[{i + 1}/{total_layers}] Clipping layer '{layer_name}'...")

            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', layer_name)
            out_file = os.path.join(out_dir, f"{safe_name}_clipped.gpkg")

            if os.path.exists(out_file) and not overwrite:
                feedback.pushInfo(f"  Skipping '{layer_name}', output file exists: {out_file}")
                continue

            clip_res = processing.run(
                "native:clip",
                {
                    'INPUT': layer,
                    'OVERLAY': overlay_param,
                    'OUTPUT': out_file
                },
                context=context,
                feedback=feedback,
                is_child_algorithm=True
            )

            out_path = clip_res['OUTPUT']
            if os.path.exists(out_path):
                clipped_count += 1
                feedback.pushInfo(f"  Successfully saved clipped layer to '{out_path}'.")

            feedback.setProgress(int((i + 1) / total_layers * 100))

        feedback.pushInfo(f"Batch clipping complete. Successfully processed {clipped_count} / {total_layers} layer(s).")
        return {
            self.OUTPUT_FOLDER: out_dir,
            'CLIPPED_COUNT': clipped_count
        }
