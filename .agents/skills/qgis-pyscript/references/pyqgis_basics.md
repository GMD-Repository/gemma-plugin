# PyQGIS Basics Reference

This document covers strict PyQGIS standards for layer manipulation, feature extraction, geometry modification, transaction safety, and CRS handling, ensuring Senior QGIS Developer quality.

## 1. Project and Layer Management

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

## 2. Accessing & Iterating Features

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

## 3. Editing Layers Safely

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

## 4. CRS Handling Standards

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

## 5. Performance Standards

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