# PyQGIS Basics Reference

This document covers strict PyQGIS standards for PyQt binding compatibility, execution environments, layer manipulation, feature extraction, geometry modification, transaction safety, CRS handling, and spatial indexing, ensuring Senior QGIS Developer quality across all deliverable types.

## 1. Target Compatibility & PyQt Imports (PyQt5 vs. PyQt6)

To maintain compatibility across **QGIS 3.x (PyQt5)** and **QGIS 3.40+/4.0 (PyQt6)**, **always import PyQt modules through `qgis.PyQt`**:

```python
# CORRECT: Always import PyQt modules from qgis.PyQt wrappers
from qgis.PyQt.QtCore import Qt, QCoreApplication, QVariant
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel, QMessageBox
from qgis.PyQt.QtGui import QIcon, QColor

# AVOID: Direct PyQt5 or PyQt6 imports unless specifically required for target version
# from PyQt5.QtWidgets import QDialog  # Breaks on PyQt6 / QGIS 4.0!
```

---

## 2. Environment Setup by Deliverable Type

### A. QGIS Python Console Script
Scripts executed inside the QGIS Python Console Editor tabs have direct access to `iface`.

```python
import os
import logging
from qgis.core import QgsProject, Qgis
from qgis.utils import iface
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

logger = logging.getLogger('QGIS_ConsoleScript')

# 1. Non-blocking user message bar feedback
iface.messageBar().pushMessage(
    "Console Script",
    "Script execution started successfully.",
    level=Qgis.Info,
    duration=3
)

# 2. Idempotent action registration (prevent duplicate buttons when re-running)
ACTION_NAME = "my_custom_console_action"
existing_actions = [a for a in iface.mainWindow().findChildren(QAction) if a.objectName() == ACTION_NAME]
for action in existing_actions:
    iface.removePluginMenu("&My Utilities", action)
    iface.mainWindow().removeAction(action)
    action.deleteLater()

# Load icon dynamically (SVG priority with QGIS theme fallback)
icon_path_svg = os.path.join(os.path.dirname(__file__), "icon.svg")
if os.path.exists(icon_path_svg):
    icon = QIcon(icon_path_svg)
else:
    icon = QIcon(":/images/themes/default/mActionFilter.svg")

new_action = QAction(icon, "Run Utility", iface.mainWindow())
new_action.setObjectName(ACTION_NAME)
new_action.triggered.connect(lambda: logger.info("Utility triggered"))
iface.addPluginToMenu("&My Utilities", new_action)
```

### B. Standalone Headless PyQGIS Script
Command-line scripts executed outside the QGIS desktop application must initialize `QgsApplication` without a GUI.

```python
import sys
import logging
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HeadlessPyQGIS")

def main():
    # 1. Initialize Headless QGIS Application (GUI = False)
    QgsApplication.setPrefixPath("/path/to/qgis", True)
    qgs = QgsApplication([], False)
    qgs.initQgis()

    try:
        # 2. Perform PyQGIS analysis headlessly
        layer = QgsVectorLayer("point_data.gpkg|layername=points", "Points", "ogr")
        if not layer.isValid():
            logger.error("Failed to load layer.")
            return

        logger.info(f"Loaded layer with {layer.featureCount()} features.")
        
        # Optionally initialize Processing framework in headless mode:
        # import processing
        # from processing.core.Processing import Processing
        # Processing.initialize()
        
    finally:
        # 3. Clean application shutdown
        qgs.exitQgis()

if __name__ == "__main__":
    main()
```

### C. QGIS Plugin & Hybrid Plugin Lifecycle
Plugins must implement symmetrical initialization and cleanup methods.

```python
import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

class MyQgisPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        """Setup UI and menus on plugin load."""
        icon_path_svg = os.path.join(os.path.dirname(__file__), "icon.svg")
        if os.path.exists(icon_path_svg):
            icon = QIcon(icon_path_svg)
        else:
            icon = QIcon(":/images/themes/default/mActionFilter.svg")

        self.action = QAction(icon, "My Plugin Action", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        # Menu placement: Plugins Menu & Toolbar
        self.iface.addPluginToMenu("&My Plugin Category", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Symmetrical cleanup on plugin unload."""
        if self.action:
            self.iface.removePluginMenu("&My Plugin Category", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

    def run(self):
        pass
```

### D. Custom Processing Tool (`QgsProcessingAlgorithm`)
Processing algorithms execute headlessly inside processing pipelines.

```python
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink
)

class MyProcessingAlgorithm(QgsProcessingAlgorithm):
    INPUT = 'INPUT'
    OUTPUT = 'OUTPUT'

    def createInstance(self):
        return MyProcessingAlgorithm()

    def name(self):
        return 'my_processing_tool'

    def displayName(self):
        return 'My Processing Tool'

    def group(self):
        return 'Vector Utilities'

    def groupId(self):
        return 'vector_utilities'

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, 'Input Layer'))
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, 'Output Layer'))

    def processAlgorithm(self, parameters, context, feedback):
        # Must run purely headless - NO iface or QMessageBox calls!
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException("Invalid input layer.")

        feedback.pushInfo(f"Processing layer with {source.featureCount()} features.")
        return {self.OUTPUT: None}
```

---

## 3. Project and Layer Management

When loading layers, always validate assumptions (path validity, provider availability).

```python
import logging
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer

logger = logging.getLogger('QGIS_Plugin')

def load_vector_layer(path: str, name: str, provider: str = "ogr") -> QgsVectorLayer:
    """Loads and validates a vector layer."""
    layer = QgsVectorLayer(path, name, provider)
    if not layer.isValid():
        logger.error(f"Failed to load vector layer from {path}")
        raise ValueError(f"Invalid layer: {path}")

    QgsProject.instance().addMapLayer(layer)
    logger.info(f"Successfully loaded {name}")
    return layer
```

---

## 4. Accessing & Iterating Features

Always specify fields or geometry constraints if you do not need all of them to maximize performance. Avoid full scans if indexed alternatives exist.

```python
from qgis.core import QgsFeatureRequest, QgsVectorLayer

def process_highway_features(layer: QgsVectorLayer) -> None:
    """Processes features filtered by attribute to prevent unnecessary loops."""
    request = QgsFeatureRequest().setFilterExpression('"type" = \'highway\'')

    # Only request the attributes we need
    request.setSubsetOfAttributes(['name', 'type'], layer.fields())
    
    for feature in layer.getFeatures(request):
        name = feature['name']
        geom = feature.geometry()
        # Geometry validation
        if geom.isNull() or not geom.isGeosValid():
            logger.warning(f"Feature {feature.id()} has invalid geometry. Skipping.")
            continue

        logger.info(f"Processing highway: {name}")
```

---

## 5. Editing Layers Safely

When modifying geometries or attributes, always wrap the operations inside `startEditing()` and `commitChanges()`. Handle exceptions strictly.

```python
def update_highway_name(layer: QgsVectorLayer, old_name: str, new_name: str) -> None:
    """Safely updates feature attributes within an edit session."""
    layer.startEditing()
    try:
        request = QgsFeatureRequest().setFilterExpression(f'"name" = \'{old_name}\'')
        field_idx = layer.fields().indexOf('name')

        if field_idx == -1:
            raise ValueError("Field 'name' not found in layer.")
            
        for feature in layer.getFeatures(request):
            layer.changeAttributeValue(feature.id(), field_idx, new_name)

        # Commit changes to source
        if not layer.commitChanges():
            logger.error("Failed to commit layer changes.")
            layer.rollBack()
    except Exception as e:
        # Rollback changes if anything goes wrong
        layer.rollBack()
        logger.error(f"Error during editing session: {str(e)}")
        raise
```

---

## 6. CRS Handling Standards

Always determine Input, Processing, and Output CRS. Never silently reproject.

```python
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

def transform_geometry(geom, source_crs: QgsCoordinateReferenceSystem, target_crs: QgsCoordinateReferenceSystem):
    """Explicitly handles CRS transformations."""
    if source_crs == target_crs:
        return geom

    logger.info(f"Reprojecting from {source_crs.authid()} to {target_crs.authid()}")
    transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())

    transformed_geom = geom.clone()
    transformed_geom.transform(transform)
    return transformed_geom
```

---

## 7. Performance Standards & Spatial Indexing

For spatial search queries (e.g., finding the nearest feature), use a `QgsSpatialIndex` for high performance. Avoid unnecessary nested loops.

```python
from qgis.core import QgsSpatialIndex, QgsPointXY, QgsVectorLayer

def find_nearest_features(layer: QgsVectorLayer, search_point: QgsPointXY, neighbors: int = 3):
    """Utilizes a spatial index for fast nearest neighbor lookups."""
    # Build index
    index = QgsSpatialIndex(layer.getFeatures())

    # Fast search
    nearest_ids = index.nearestNeighbor(search_point, neighbors)
    return nearest_ids
```