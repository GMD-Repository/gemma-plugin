# Check and Update

The **Check and Update** tool provides a 3-Phase structured workflow for boundary management activities: **Georeferencing**, **Geometry Checking & Repair**, and **Updating Metadata**.

---

## Access

- **Menu:** Gemma → Updating of Boundaries → Check and Update

---

## Workflow Sections

### Georeferencing
- Includes a dedicated action button **Open QGIS Georeferencer** to directly launch QGIS's built-in Georeferencer window for raster basemaps, scanned map sheets, or aerial imagery.

### Geometry Check & Repair (Chronological Workflow)
1. **Target Layer & Check Error Options**: Choose polygon layer and select error check types (Null, Empty, Invalid GEOS, Self-Intersections, Wrong Type, Duplicates).
2. **Step 1: Scan Geometry Errors**: Runs `gmd_pipeline:scangeometryerrors` algorithm, automatically populates an interactive **Detected Errors Table** (`FID`, `Layer`, `Error Type`, `Description`, `Auto-fixable`), and loads the Point Error Layer into QGIS.
3. **Interactive Table Selection & Map Zoom**:
   - **Double-click** any row to zoom the QGIS map canvas directly to that error feature.
   - **Multi-select** specific rows to target specific features for repair.
4. **Step 2: Repair Polygon Geometries**:
   - If specific table rows are highlighted, repairs **only those selected error features**.
   - If no rows are selected, repairs **all detected errors** across the layer.
5. **Step 3: UPSERT Repaired Features to Layer**:
   - Merges the clean repaired geometries back into a complete updated version of the target polygon layer (`Updated_<layer_name>`).
   - Replaces defective features with clean repaired geometries while keeping all untouched valid features preserved.

### Updating Metadata
- Placeholder section prepared for upcoming PSGC metadata auto-population and administrative attribute updates.
