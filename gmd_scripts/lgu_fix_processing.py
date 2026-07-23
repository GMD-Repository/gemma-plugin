
import os
import numpy as np
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsFeatureSink,
    QgsProcessingException,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsProcessingFeedback,
    NULL,
)
from qgis import processing


def transform_geometry(geom: QgsGeometry, M: np.ndarray) -> QgsGeometry:
    """Applies a 2D affine transformation matrix M to every vertex of a QgsGeometry."""
    if not geom or geom.isEmpty():
        return QgsGeometry()

    a, c_lon = M[0, 0], M[2, 0]
    b = M[1, 0]
    d, c_lat = M[0, 1], M[2, 1]
    e = M[1, 1]

    # Prefer shapely for fast and robust geometry vertex transformation
    try:
        import shapely
        import shapely.wkb
        from shapely.ops import transform as shapely_transform

        s_geom = shapely.wkb.loads(bytes(geom.asWkb()))

        def _pt_trans(x, y, z=None):
            lon = a * x + b * y + c_lon
            lat = d * x + e * y + c_lat
            if z is not None:
                return (lon, lat, z)
            return (lon, lat)

        trans_s_geom = shapely_transform(_pt_trans, s_geom)
        out_geom = QgsGeometry()
        out_geom.fromWkb(shapely.wkb.dumps(trans_s_geom))
        return out_geom
    except Exception:
        out_geom = QgsGeometry(geom)

        def _transform_point(pt):
            x, y = pt.x(), pt.y()
            new_x = a * x + b * y + c_lon
            new_y = d * x + e * y + c_lat
            return QgsPoint(new_x, new_y)

        try:
            out_geom.transform(_transform_point)
        except Exception:
            pass
        return out_geom


class FixLGUCRSAlgorithm(QgsProcessingAlgorithm):
    """
    Transforms vector layers digitized in local arbitrary grid coordinates (~0 to ~100,000)
    to true WGS84 coordinates (EPSG:4326) using 2D Affine Least Squares transformation.
    """

    # Constants used to refer to parameters and outputs.
    INPUT = 'INPUT'
    REFERENCE_LAYER = 'REFERENCE_LAYER'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return FixLGUCRSAlgorithm()

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm.
        """
        return 'fixlgucrs'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Fix LGU CRS')

    def group(self):
        """
        Returns the name of the group this algorithm belongs to.
        """
        return self.tr('1Map')

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to.
        """
        return '1map'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'crs.png')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()

    def shortHelpString(self):
        """
        Returns a localised short helper string for the algorithm.
        """
        return self.tr(
            "Transforms vector layers digitized in local arbitrary grid coordinates (~0 to ~100,000) "
            "to true WGS84 coordinates (EPSG:4326) using 2D Affine Least Squares transformation.\n\n"
            "Smart Zero-Config Feature Auto-Detection:\n"
            "- Automatically detects XI/YI/LongitudeI/LatitudeI fields from attributes if present.\n"
            "- Automatically falls back to geometry centroids for local X/Y if XI/YI fields are absent.\n"
            "- Uses optional Reference WGS84 Layer for target coordinates if LongitudeI/LatitudeI fields are missing.\n"
            "- Fits 2D affine transformation and reports fit statistics & residual errors in the processing log."
        )

    def initAlgorithm(self, config=None):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                self.tr('Input Local Grid Layer'),
                [QgsProcessing.SourceType.TypeVectorAnyGeometry]
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.REFERENCE_LAYER,
                self.tr('Reference WGS84 Layer / Control Points Layer [Optional]'),
                [QgsProcessing.SourceType.TypeVectorAnyGeometry],
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                self.tr('Corrected Layer (EPSG:4326)')
            )
        )

    def _auto_find_field(self, fields, candidates):
        field_names = [f.name() for f in fields]
        for cand in candidates:
            cand_lower = cand.lower()
            for name in field_names:
                if name.lower() == cand_lower:
                    return name
        return None

    def _clean_val(self, v):
        if v is None or v == NULL or isinstance(v, QVariant):
            return None
        try:
            s = str(v).strip()
            if not s or s.lower() in ('null', 'none', 'nan'):
                return None
            val = float(s)
            return val if np.isfinite(val) else None
        except (ValueError, TypeError):
            return None

    def processAlgorithm(self, parameters, context, feedback: QgsProcessingFeedback):
        """
        Here is where the processing itself takes place.
        """
        source = self.parameterAsSource(
            parameters,
            self.INPUT,
            context
        )

        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))

        reference_source = self.parameterAsSource(
            parameters,
            self.REFERENCE_LAYER,
            context
        )

        fields = source.fields()

        # Auto-detect field names
        xi_field_name = self._auto_find_field(fields, ['XI', 'X_I', 'X_LOCAL', 'LOCAL_X'])
        yi_field_name = self._auto_find_field(fields, ['YI', 'Y_I', 'Y_LOCAL', 'LOCAL_Y'])
        loni_field_name = self._auto_find_field(fields, ['LongitudeI', 'Longitude', 'LongI', 'Long', 'LonI', 'Lon', 'X_WGS84'])
        lati_field_name = self._auto_find_field(fields, ['LatitudeI', 'Latitude', 'LatI', 'Lat', 'Y_WGS84'])

        if xi_field_name:
            feedback.pushInfo(self.tr(f"Detected Local X Field: '{xi_field_name}'"))
        else:
            feedback.pushInfo(self.tr("Local X Field not found; using feature geometry centroids for Local X."))

        if yi_field_name:
            feedback.pushInfo(self.tr(f"Detected Local Y Field: '{yi_field_name}'"))
        else:
            feedback.pushInfo(self.tr("Local Y Field not found; using feature geometry centroids for Local Y."))

        if loni_field_name:
            feedback.pushInfo(self.tr(f"Detected WGS84 Longitude Field: '{loni_field_name}'"))
        if lati_field_name:
            feedback.pushInfo(self.tr(f"Detected WGS84 Latitude Field: '{lati_field_name}'"))

        # Process reference layer features if provided
        ref_records = []  # list of (feature_id, QgsPoint in 4326, dict_attr_values)
        if reference_source:
            crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
            needs_transform = reference_source.sourceCrs() != crs_4326
            ct = QgsCoordinateTransform(reference_source.sourceCrs(), crs_4326, context.transformContext()) if needs_transform else None
            
            ref_fields_list = [f.name() for f in reference_source.fields()]
            for rf in reference_source.getFeatures():
                rg = rf.geometry()
                if rg and not rg.isEmpty():
                    rg_copy = QgsGeometry(rg)
                    if ct:
                        rg_copy.transform(ct)
                    pt = rg_copy.centroid().asPoint()
                    attr_dict = {fn.lower(): rf[fn] for fn in ref_fields_list}
                    ref_records.append((rf.id(), pt, attr_dict))

        # Check for common attribute key to match source & reference features
        match_key_pair = None
        if reference_source and ref_records:
            for candidate in ['bgy_code', 'psgc_bgy', 'code', 'id', 'name', 'barangay', 'bgy_name', 'bgy_id', 'adm4_en']:
                s_cand = self._auto_find_field(fields, [candidate])
                r_cand = self._auto_find_field(reference_source.fields(), [candidate])
                if s_cand and r_cand:
                    match_key_pair = (s_cand, r_cand)
                    feedback.pushInfo(self.tr(f"Matching input & reference features via common attribute: '{s_cand}' <-> '{r_cand}'"))
                    break

        # Spatial Centroid Relative Position Lookup if no common attribute key
        spatial_ref_map = {}
        if reference_source and ref_records and not match_key_pair:
            feedback.pushInfo(self.tr("Matching input & reference features by relative spatial proximity..."))
            s_pts = []
            s_ids = []
            for feat in source.getFeatures():
                g = feat.geometry()
                if g and not g.isEmpty():
                    s_pts.append(g.centroid().asPoint())
                    s_ids.append(feat.id())
            
            if s_pts and ref_records:
                s_xs = np.array([p.x() for p in s_pts])
                s_ys = np.array([p.y() for p in s_pts])
                r_xs = np.array([rec[1].x() for rec in ref_records])
                r_ys = np.array([rec[1].y() for rec in ref_records])

                sx_min, sx_max = np.min(s_xs), np.max(s_xs)
                sy_min, sy_max = np.min(s_ys), np.max(s_ys)
                rx_min, rx_max = np.min(r_xs), np.max(r_xs)
                ry_min, ry_max = np.min(r_ys), np.max(r_ys)

                sx_range = (sx_max - sx_min) if (sx_max > sx_min) else 1.0
                sy_range = (sy_max - sy_min) if (sy_max > sy_min) else 1.0
                rx_range = (rx_max - rx_min) if (rx_max > rx_min) else 1.0
                ry_range = (ry_max - ry_min) if (ry_max > ry_min) else 1.0

                s_norm_x = (s_xs - sx_min) / sx_range
                s_norm_y = (s_ys - sy_min) / sy_range
                r_norm_x = (r_xs - rx_min) / rx_range
                r_norm_y = (r_ys - ry_min) / ry_range

                for i, fid in enumerate(s_ids):
                    dist_sq = (r_norm_x - s_norm_x[i])**2 + (r_norm_y - s_norm_y[i])**2
                    best_idx = int(np.argmin(dist_sq))
                    spatial_ref_map[fid] = ref_records[best_idx][1]

        # Extract control points
        x_list, y_list, lon_list, lat_list = [], [], [], []

        for idx, feature in enumerate(source.getFeatures()):
            geom = feature.geometry()
            centroid_pt = geom.centroid().asPoint() if (geom and not geom.isEmpty()) else None

            # Local X
            vx = feature[xi_field_name] if xi_field_name else None
            x_val = self._clean_val(vx)
            if x_val is None and centroid_pt:
                x_val = centroid_pt.x()

            # Local Y
            vy = feature[yi_field_name] if yi_field_name else None
            y_val = self._clean_val(vy)
            if y_val is None and centroid_pt:
                y_val = centroid_pt.y()

            # WGS84 Longitude
            vlon = feature[loni_field_name] if loni_field_name else None
            lon_val = self._clean_val(vlon)

            # WGS84 Latitude
            vlat = feature[lati_field_name] if lati_field_name else None
            lat_val = self._clean_val(vlat)

            # Auto-correct swapped Lon/Lat attributes (Philippines: Lon ~116..127, Lat ~4..21)
            if lon_val is not None and lat_val is not None:
                if lon_val < 35.0 and lat_val > 90.0:
                    lon_val, lat_val = lat_val, lon_val

            # Fallback to reference layer point if target WGS84 coords not in feature attributes
            if (lon_val is None or lat_val is None) and reference_source:
                ref_pt = None
                if match_key_pair:
                    s_val = str(feature[match_key_pair[0]]).strip().lower()
                    r_cand_key = match_key_pair[1].lower()
                    for rec in ref_records:
                        r_attr_val = str(rec[2].get(r_cand_key, '')).strip().lower()
                        if r_attr_val and r_attr_val == s_val:
                            ref_pt = rec[1]
                            break
                elif feature.id() in spatial_ref_map:
                    ref_pt = spatial_ref_map[feature.id()]
                elif idx < len(ref_records):
                    ref_pt = ref_records[idx][1]

                if ref_pt:
                    lon_val, lat_val = ref_pt.x(), ref_pt.y()

            if (x_val is not None and y_val is not None and lon_val is not None and lat_val is not None):
                x_list.append(x_val)
                y_list.append(y_val)
                lon_list.append(lon_val)
                lat_list.append(lat_val)

        if len(x_list) < 3:
            raise QgsProcessingException(
                self.tr(
                    f"Insufficient valid control points found ({len(x_list)} points). "
                    "At least 3 non-collinear control points are required."
                )
            )

        X = np.array(x_list, dtype=float)
        Y = np.array(y_list, dtype=float)
        LON = np.array(lon_list, dtype=float)
        LAT = np.array(lat_list, dtype=float)

        N = len(X)
        A_normal = np.column_stack([X, Y, np.ones(N)])
        B = np.column_stack([LON, LAT])

        # Test normal vs swapped X/Y to avoid diagonal skew/reflection
        M_normal, _, rank_normal, _ = np.linalg.lstsq(A_normal, B, rcond=None)
        
        A_swapped = np.column_stack([Y, X, np.ones(N)])
        M_swapped, _, rank_swapped, _ = np.linalg.lstsq(A_swapped, B, rcond=None)

        err_norm = np.hypot(A_normal @ M_normal[:, 0] - LON, A_normal @ M_normal[:, 1] - LAT)
        err_swap = np.hypot(A_swapped @ M_swapped[:, 0] - LON, A_swapped @ M_swapped[:, 1] - LAT)

        det_norm = M_normal[0, 0] * M_normal[1, 1] - M_normal[1, 0] * M_normal[0, 1]
        det_swap = M_swapped[0, 0] * M_swapped[1, 1] - M_swapped[1, 0] * M_swapped[0, 1]

        # Select best orientation (prefer positive matrix determinant & lower error)
        if (det_norm < 0 and det_swap > 0) or (np.mean(err_swap) < 0.5 * np.mean(err_norm) and det_swap > 0):
            M = M_swapped
            A = A_swapped
            feedback.pushInfo(self.tr("Auto-corrected Local X/Y axis orientation (swapped X and Y to match WGS84 orientation)."))
        else:
            M = M_normal
            A = A_normal

        # Compute residuals and perform outlier filtering if N > 4
        B_pred = A @ M
        residuals = np.hypot(B_pred[:, 0] - LON, B_pred[:, 1] - LAT)
        med_res = float(np.median(residuals))
        inliers = residuals <= max(3.0 * med_res, 0.05)

        if N > 4 and np.sum(inliers) >= 3 and np.sum(inliers) < N:
            feedback.pushInfo(self.tr(f"Refining transformation: removing {N - np.sum(inliers)} outlier control points..."))
            A_in = A[inliers]
            B_in = B[inliers]
            M_in, _, r_in, _ = np.linalg.lstsq(A_in, B_in, rcond=None)
            if r_in >= 3:
                M = M_in
                B_pred = A @ M
                residuals = np.hypot(B_pred[:, 0] - LON, B_pred[:, 1] - LAT)

        max_residual = float(np.max(residuals))
        max_lon_err = float(np.max(np.abs(B_pred[:, 0] - LON)))
        max_lat_err = float(np.max(np.abs(B_pred[:, 1] - LAT)))

        feedback.pushInfo(self.tr(f"Successfully fit 2D Affine Transform across {N} control points:"))
        feedback.pushInfo(self.tr(f"  Longitude = {M[0, 0]:.10e} * X + {M[1, 0]:.10e} * Y + {M[2, 0]:.10e}"))
        feedback.pushInfo(self.tr(f"  Latitude  = {M[0, 1]:.10e} * X + {M[1, 1]:.10e} * Y + {M[2, 1]:.10e}"))
        feedback.pushInfo(self.tr(f"  Max Euclidean Residual: {max_residual:.8f}°"))
        feedback.pushInfo(self.tr(f"  Max Lon Error: {max_lon_err:.8f}°, Max Lat Error: {max_lat_err:.8f}°"))

        # Output destination CRS: WGS 84 (EPSG:4326)
        output_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            source.fields(),
            source.wkbType(),
            output_crs
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        # Compute the number of steps to display within the progress bar and get features from source
        total = 100.0 / source.featureCount() if source.featureCount() else 0
        features = source.getFeatures()

        for current, feature in enumerate(features):
            if feedback.isCanceled():
                break

            out_feat = QgsFeature(feature)
            orig_geom = feature.geometry()

            if orig_geom and not orig_geom.isEmpty():
                transformed_geom = transform_geometry(orig_geom, M)
                out_feat.setGeometry(transformed_geom)

            sink.addFeature(out_feat, QgsFeatureSink.Flag.FastInsert)
            feedback.setProgress(int(current * total))

        return {self.OUTPUT: dest_id}