# QGIS Validation & Testing Standards

As a Senior QGIS Developer, you must validate all inputs and environments before processing, and design systems for testability.

## 1. Geometry Validation

Before running spatial algorithms, geometries must be validated to avoid silent failures and corrupt outputs.

### Mandatory Checks
1. **Null Geometries**: Features with `geom.isNull()`.
2. **Invalid Geometries**: Features where `geom.isGeosValid()` returns `False`.
3. **Empty Geometries**: Features where `geom.isEmpty()`.
4. **Multipart Requirements**: Ensure the target supports multipart if inputs are multipart (`geom.isMultipart()`).

```python
def validate_and_process_geometry(feature, feedback):
    geom = feature.geometry()

    if geom.isNull():
        feedback.pushInfo(f"Feature {feature.id()}: Geometry is NULL. Skipping.")
        return None

    if geom.isEmpty():
        feedback.pushInfo(f"Feature {feature.id()}: Geometry is Empty. Skipping.")
        return None

    if not geom.isGeosValid():
        # Optional: Attempt to make valid if requested by architecture
        # geom = geom.makeValid()
        feedback.pushInfo(f"Feature {feature.id()}: Geometry is Invalid. Skipping.")
        return None

    return geom
```

## 2. CRS Validation

Never silently reproject geometries. Always explicitly determine the Source CRS, Processing CRS, and Output CRS.

```python
def validate_crs(source_layer, target_crs, feedback):
    source_crs = source_layer.crs()

    if not source_crs.isValid():
        feedback.reportError("Source layer lacks a valid CRS.")
        raise ValueError("Invalid Source CRS.")

    if source_crs != target_crs:
        feedback.pushInfo(f"Reprojecting geometries from {source_crs.authid()} to {target_crs.authid()}")
        return True # Indicates transformation is required
    return False
```

## 3. Test Plan Standards

Every QGIS implementation must have an associated test plan verifying both expected and edge-case behavior.

Always generate and review the following tests in your planning stage:

1. **Success Test**: The standard, expected workflow succeeds with typical data.
2. **Empty Layer Test**: Input layer has 0 features. The tool should not crash, and should return an empty output sink.
3. **Invalid Geometry Test**: A layer with broken geometries is supplied. The tool should log/skip them appropriately without crashing.
4. **CRS Mismatch Test**: The input layer is in EPSG:4326 but the algorithm requires EPSG:3857.
5. **Missing Field Test**: A required attribute field is absent from the input. Exception should be raised early.
6. **Large Dataset Test**: Ensure algorithms utilize Spatial Indexes or batch processing when feature counts exceed 100,000.
7. **Cancellation Test**: Trigger `feedback.isCanceled()` mid-processing to verify the algorithm stops and cleans up safely.
