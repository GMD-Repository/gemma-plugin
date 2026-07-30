# Writing QGIS Custom Processing Algorithms

This document provides a standard, production-ready template for creating custom geoprocessing tools in QGIS. It enforces the rules of accuracy, validation, maintainability, and feedback reporting required for high-quality algorithms.

## 1. Naming Standards
- Files must use `snake_case.py` (e.g., `buffer_points_algorithm.py`).
- Never invent Algorithm IDs. Use lowercase strings without spaces (e.g., `bufferpoints`).

## 2. Processing Algorithm Template

Every custom processing tool must inherit from `QgsProcessingAlgorithm` and strictly implement the required methods.

```python
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsFeature,
    QgsFeatureSink
)

class BufferPointsAlgorithm(QgsProcessingAlgorithm):
    """
    A custom QGIS Processing Algorithm that buffers point layers.
    Always uses explicit validation and progress tracking.
    """
    
    # Define parameter name constants (avoid magic strings)
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def tr(self, text):
        """Helper method for translating strings."""
        return QCoreApplication.translate('Processing', text)

    def createInstance(self):
        return BufferPointsAlgorithm()

    def name(self):
        """Unique ID (snake_case or lowercased word)."""
        return 'buffer_points'

    def displayName(self):
        """User-visible name in the Toolbox."""
        return self.tr('Buffer Points')

    def group(self):
        return self.tr('Vector Utilities')

    def groupId(self):
        return 'vector_utilities'

    def shortHelpString(self):
        return self.tr("Buffers valid point geometries from an input layer.")

    def initAlgorithm(self, config=None):
        """Define input and output parameters."""
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input Point Layer'),
                [QgsProcessing.TypeVectorPoint] # Explicitly restrict to Points
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Buffered Output')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        The core geoprocessing logic.
        Must validate geometries, CRS, and inputs before execution.
        """
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.tr("Invalid input layer source."))

        # Validate CRS existence
        if not source.crs().isValid():
            feedback.reportError(self.tr("Input layer lacks a valid CRS."))
            raise QgsProcessingException(self.tr("Invalid CRS."))

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            source.fields(),
            source.wkbType(),
            source.crs()
        )

        if sink is None:
            raise QgsProcessingException(self.tr("Invalid output destination sink."))

        total = 100.0 / source.featureCount() if source.featureCount() else 0
        features = source.getFeatures()

        for current, feature in enumerate(features):
            if feedback.isCanceled():
                feedback.pushInfo(self.tr("Processing canceled by user."))
                break

            geom = feature.geometry()

            # Explicit Geometry Validation
            if geom.isNull() or not geom.isGeosValid():
                feedback.pushInfo(self.tr(f"Skipping invalid geometry for feature ID {feature.id()}"))
                continue

            # Geoprocessing action
            out_feature = QgsFeature(feature)
            # e.g., out_feature.setGeometry(geom.buffer(10.0, 5))
            
            sink.addFeature(out_feature, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(current * total))

        return {self.OUTPUT: dest_id}
```

## 3. Best Practices & Never Do's

**Always:**
- Use `QgsProcessingFeedback` for progress and logs (`feedback.pushInfo()`).
- Support cancellation (`feedback.isCanceled()`).
- Validate inputs, geometries, CRS, and layer types before looping over features.
- Handle exceptions using `QgsProcessingException`.
- Route processed data to a `QgsFeatureSink`.

**Never:**
- Use GUI dialogs (`QMessageBox`) inside Processing logic.
- Rely on `iface` inside a `processAlgorithm` method (Processing algorithms must run headless).
- Mix business logic/UI code with geoprocessing.
- Silently reproject layers without explicit instructions.
