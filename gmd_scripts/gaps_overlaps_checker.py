__author__ = 'Geosptial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geosptial Management Division'

from qgis.PyQt.QtCore import QVariant
import processing
from qgis.core import *
from qgis.utils import iface
import os
import uuid
from datetime import datetime
from qgis.PyQt.QtGui import QIcon


class MBIStylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, style_path):
        super().__init__()
        self.style_path = style_path

    def postProcessLayer(self, layer, context, feedback):
        if layer and os.path.exists(self.style_path):
            processing.run("native:setlayerstyle", {
                'INPUT': layer,
                'STYLE': self.style_path
            }, context=context, feedback=feedback)


class GapsOverlaps(QgsProcessingAlgorithm):
    
    def __init__(self):
        super().__init__()
        self.post_processors = []

    def name(self):
        return 'gaps_overlaps_checker'

    def displayName(self):
        return 'MBI Checker'

    def group(self):
        return '1Map'

    def groupId(self):
        return '1map'

    def createInstance(self):
        return GapsOverlaps()

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons/overlap.png'))

    # Selection ng bgy bdry bldg point at mode
    # Added layer multiple select for PSO's convenience
    # Added selection of mode
    INPUT1 = 'INPUT1'
    INPUT2 = 'INPUT2'
    RUN_MODE = 'RUN_MODE'
    EXPORT_MBI = 'EXPORT_MBI'

    def shortHelpString(self):

        return (
            "This is to check or recheck if there are remaining overlaps or gaps in the barangay polygons\n"
            
            "Changelogs \n"
            
            "-Initial release"
        )

    def initAlgorithm(self, config=None):

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT1,
                'Select Barangay Polygon Layer(s)',
                QgsProcessing.TypeVectorPolygon
            )
        )

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT2,
                'Select Building Point Layer(s)',
                QgsProcessing.TypeVectorPoint
            )
        )

        # Mode to run
        analysis_options = ['Overlaps and Gaps', 'Overlaps Only', 'Gaps Only']
        self.addParameter(
            QgsProcessingParameterEnum(
                self.RUN_MODE,
                'Analysis to Run',
                options=analysis_options,
                defaultValue=0  # Checking Overlaps and Gaps
            )
        )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.EXPORT_MBI,
                'Export MBI layers as GPKG to C:\\PSA-GIS\\2026 1Map\\Preliminary Output',
                defaultValue=False
            )
        )

    def processAlgorithm(self, parameters, context, feedback: QgsProcessingFeedback):

        
        bgy_list = self.parameterAsLayerList(parameters, self.INPUT1, context)
        bldg_list = self.parameterAsLayerList(parameters, self.INPUT2, context)
        run_mode = self.parameterAsEnum(parameters, self.RUN_MODE, context)  # Get the selected mode
        export_folder = r"C:\PSA-GIS\2026 1Map\Preliminary Output"
        style_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),'styles/mbi_checker.qml')
        #style_path = 'C:\\Users\\Admin\\OneDrive - Philippine Statistics Authority\\GMD\\2026\\1Map\\GMD Plugin\\gmd_pipeline\\styles\\mbi_checker.qml'
        export_enabled = self.parameterAsBool(parameters, self.EXPORT_MBI, context)
        self.post_processors = []
        
        # Create directory if it doesn't exist and export is enabled
        if export_enabled:
            if not os.path.exists(export_folder):
                try:
                    os.makedirs(export_folder)
                    feedback.pushInfo(f"Created directory: {export_folder}")
                except Exception as e:
                    feedback.reportError(f"Could not create directory {export_folder}: {str(e)}")
                    export_enabled = False # Disable export if folder creation fails

        
        run_overlaps = (run_mode == 0 or run_mode == 1)
        run_gaps = (run_mode == 0 or run_mode == 2)

        feedback.pushInfo(f'Processing... Mode: {["Both", "Overlaps Only", "Gaps Only"][run_mode]}')
        

        
        # Check for empty lists (which means no layers were selected)
        if not bgy_list:
            raise QgsProcessingException("Barangay Polygon Layer(s) must be selected.")
        if not bldg_list:
            raise QgsProcessingException("Building Point Layer(s) must be selected.")

        feedback.pushInfo("Merging Selected Layers...")
        feedback.setProgress(2)
        
        def refactor_layer(layer):
            field_mapping = []
            for f in layer.fields():
                field_mapping.append({
                    'expression': f'"{f.name()}"',
                    'length': 0,            # no limit
                    'name': f.name(),
                    'type': f.type()
                })
            return processing.run("native:refactorfields", {
                'INPUT': layer,
                'FIELDS_MAPPING': field_mapping,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']

        # Refactor all layers before merging
        bgy_refactored = [refactor_layer(l) for l in bgy_list]
        bldg_refactored = [refactor_layer(l) for l in bldg_list]


        # Merge for Barangay Polygons
        # Use the first layer's CRS for the output of merge
        bgy_layer = processing.run("native:mergevectorlayers", {
            'LAYERS': bgy_refactored,
            'CRS': bgy_refactored[0].crs(),
            'OUTPUT': 'memory:'
        }, context=context, feedback=feedback)['OUTPUT']

        # Perform Merge for Building Points
        bldg_layer = processing.run("native:mergevectorlayers", {
            'LAYERS': bldg_refactored,
            'CRS': bldg_refactored[0].crs(),
            'OUTPUT': 'memory:'
        }, context=context, feedback=feedback)['OUTPUT']

        feedback.setProgress(5)

        reprojected_bgy_res = processing.run("native:reprojectlayer", {
            'CONVERT_CURVED_GEOMETRIES': False,
            'INPUT': bgy_layer,
            'OPERATION': '+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84',
            'OUTPUT': 'memory:',
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:3857')
        }, context=context, feedback=feedback)

        reprojected_bgy_res_fix = processing.run("native:fixgeometries", {
            'INPUT' : reprojected_bgy_res['OUTPUT'], 
            'METHOD' : 1, 
            'OUTPUT' : 'memory:'
        }, context=context, feedback=feedback)

        if feedback.isCanceled():
            return {}
        reprojected_bgy = reprojected_bgy_res_fix['OUTPUT']

        feedback.setProgress(10)

        reprojected_bldg_res = processing.run("native:reprojectlayer", {
            'CONVERT_CURVED_GEOMETRIES': False,
            'INPUT': bldg_layer,
            'OPERATION': '+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84',
            'OUTPUT': 'memory:',
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:3857')
        }, context=context, feedback=feedback)
        
        reprojected_bldg_res_fix = processing.run("native:fixgeometries", {
            'INPUT' : reprojected_bldg_res['OUTPUT'],
            'METHOD' : 1, 
            'OUTPUT' : 'memory:'
        }, context=context, feedback=feedback)

        if feedback.isCanceled():
            return {}
        reprojected_bldg = reprojected_bldg_res_fix['OUTPUT']
        
        
        #root = QgsProject.instance().layerTreeRoot()
        #group_name = "MBI Checker"
        #group = root.findGroup(group_name)
        #if group is None:
        #    group = root.insertGroup(0, group_name)
            
        #group_id = group_name
        #group_id = group.name()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        def export_layer(target, layer_name=f"Gaps and Overlap ({timestamp})", set_style=True):
            
            if target is None:
                feedback.reportError(f"Skipping {layer_name}: Layer target is None.")
                return

            layer_details = QgsProcessingContext.LayerDetails(
                layer_name,
                context.project(),
                "OUTPUT"
            )
            
            #layer_details.destinationGroupId = group_id
            
            # Apply style if True
            if set_style:
                processor = MBIStylePostProcessor(style_path)
                self.post_processors.append(processor)
                layer_details.setPostProcessor(processor)

            if isinstance(target, str):
                # Scenario A: Target is a file path (GPKG/SHP)
                context.addLayerToLoadOnCompletion(target, layer_details)
                feedback.pushInfo(f"Saved layer queued: {target}")
            
            elif isinstance(target, QgsVectorLayer):
                # Scenario B: Target is an in-memory/scratch layer object
                target.setName(layer_name)
                # Register the object so the project can 'see' it after the script ends
                context.temporaryLayerStore().addMapLayer(target)
                # For memory layers, we pass the layer ID to the context
                context.addLayerToLoadOnCompletion(target.id(), layer_details)
                feedback.pushInfo(f"Scratch layer queued: {layer_name}")
            
            else:
                feedback.reportError(f"Unexpected type for {layer_name}: {type(target)}")
              

        # --- Start ng OVERLAP checks---
        if run_overlaps:
            QgsMessageLog.logMessage("Starting Overlap Analysis...")

            progress_start = 10
            progress_end = 100 if run_mode == 1 else 55
            progress_range = progress_end - progress_start

            def update_overlap_progress(step):
                original_range = 55 - 10  # 45 total points for old overlap section
                new_progress = progress_start + (step - 10) * progress_range / original_range
                feedback.setProgress(int(new_progress))

            update_overlap_progress(12)

            singlepart_res = processing.run("native:multiparttosingleparts", {
                'INPUT': reprojected_bgy,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            singlepart_sf = singlepart_res['OUTPUT']

            update_overlap_progress(20)

            # Reconstructed LF Tools' Overlapping Polygon

            Fields = QgsFields()
            itens = {
                'ID1': QVariant.Int,
                'ID2': QVariant.Int,
            }
            for item in itens:
                Fields.append(QgsField(item, itens[item]))

            index = QgsSpatialIndex(singlepart_sf.getFeatures())

            overlap_features_to_add = []
            sobreposicoes = []

            total_features = singlepart_sf.featureCount()
            if total_features == 0:
                feedback.pushInfo("No features in single-part layer to check for overlaps. Skipping Overlap Analysis.")
                if run_mode == 0:
                    feedback.setProgress(55)  
                elif run_mode == 1:
                    feedback.setProgress(100) 
                run_overlaps = False  

            if run_overlaps:  
                total_progress_steps = total_features
                progress_step_size = (progress_end - 20) / total_progress_steps if total_progress_steps else 0

                for current, feat1 in enumerate(singlepart_sf.getFeatures()):
                    ID1 = feat1.id()
                    geom1 = feat1.geometry()
                    linha1 = QgsGeometry.fromPolylineXY(geom1.asPolygon()[0])
                    bbox1 = geom1.boundingBox()
                    feat_ids = index.intersects(bbox1)

                    
                    current_progress = 20 + (current * progress_step_size)
                    feedback.setProgress(int(current_progress))

                    for feat2 in singlepart_sf.getFeatures(QgsFeatureRequest(feat_ids)):
                        ID2 = feat2.id()
                        if ID1 != ID2 and (ID2, ID1) not in sobreposicoes:
                            geom2 = feat2.geometry()
                            if geom1.intersects(geom2):
                                inter = geom1.intersection(geom2)

                                
                                if not inter.isEmpty() and inter.wkbType() != QgsWkbTypes.NoGeometry:
                                    sobreposicoes.append((ID1, ID2))

                                    for item in inter.asGeometryCollection():
                                        if item.type() == 2:  # polygon

                                            if item.isMultipart():
                                                coords = item.asMultiPolygon()
                                                for coord in coords:
                                                    feature = QgsFeature(Fields)
                                                    feature.setGeometry(QgsGeometry.fromPolygonXY(coord))
                                                    feature.setAttributes([ID1, ID2])
                                                    overlap_features_to_add.append(feature)  # Append to list
                                            else:
                                                feature = QgsFeature(Fields)
                                                feature.setGeometry(item)
                                                feature.setAttributes([ID1, ID2])
                                                overlap_features_to_add.append(feature)  # Append to list
                    if feedback.isCanceled():
                        break

                if feedback.isCanceled():
                    return {}

                # --- Create the output layer from the list of features using the data provider ---
                overlapping_sf = QgsVectorLayer(
                    "Polygon?crs=EPSG:3857",
                    "temporary_overlaps",
                    "memory"
                )
                overlapping_sf.dataProvider().addAttributes(Fields)
                overlapping_sf.updateFields()

                # Add the collected features to the data provider
                if overlap_features_to_add:
                    overlapping_sf.dataProvider().addFeatures(overlap_features_to_add)

                # Check if features were actually created before proceeding with the rest of the algorithms
                if overlapping_sf.featureCount() == 0:
                    feedback.pushInfo(
                        "Overlap check finished but no overlapping features were found. Skipping subsequent overlap steps.")
                    if run_mode == 0:
                        feedback.setProgress(55)
                    elif run_mode == 1:
                        feedback.setProgress(100)
                    run_overlaps = False  # Skip the rest of the 'if run_overlaps' block

            if feedback.isCanceled():
                return {}
            # overlapping_sf = overlapping_res['OUTPUT']

            update_overlap_progress(25)

            overlapping_sf_with_uuid_res = processing.run("native:refactorfields", {
                'FIELDS_MAPPING': [
                    {'alias': '', 'comment': '', 'expression': '"ID1"', 'length': 0, 'name': 'ID1', 'precision': 0,
                     'sub_type': 0, 'type': 2, 'type_name': 'integer'},
                    {'alias': '', 'comment': '', 'expression': '"ID2"', 'length': 0, 'name': 'ID2', 'precision': 0,
                     'sub_type': 0, 'type': 2, 'type_name': 'integer'},
                    {'alias': '', 'comment': '', 'expression': 'substr($uuid, 2,36)', 'length': 0, 'name': 'gmd_uuid',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': ' round($area , 2)', 'length': 0, 'name': 'mbi_area',
                     'precision': 0, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}],
                'INPUT': overlapping_sf,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            overlapping_sf_with_uuid = overlapping_sf_with_uuid_res['OUTPUT']

            # UPDATE PROGRESS (28)
            update_overlap_progress(28)

            min_bounding_res = processing.run("qgis:minimumboundinggeometry", {
                'FIELD': 'gmd_uuid',
                'INPUT': overlapping_sf_with_uuid,
                'OUTPUT': 'memory:',
                'TYPE': 1
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            min_bounding_sf = min_bounding_res['OUTPUT']

            # UPDATE PROGRESS (30)
            update_overlap_progress(30)

            overlap_joined_res = processing.run("native:joinattributestable", {
                'DISCARD_NONMATCHING': False,
                'FIELD': 'gmd_uuid',
                'FIELDS_TO_COPY': ['gmd_uuid', 'width', 'height'],
                'FIELD_2': 'gmd_uuid',
                'INPUT': overlapping_sf_with_uuid,
                'INPUT_2': min_bounding_sf,
                'METHOD': 1,
                'OUTPUT': 'memory:',
                'PREFIX': ''
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            overlap_joined = overlap_joined_res['OUTPUT']

            # UPDATE PROGRESS (32)
            update_overlap_progress(32)

            overlap_joined_refactored_res = processing.run("native:refactorfields", {
                'FIELDS_MAPPING': [
                    {'alias': '', 'comment': '', 'expression': '"gmd_uuid"', 'length': 0, 'name': 'gmd_uuid',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"mbi_area"', 'length': 0, 'name': 'mbi_area',
                     'precision': 0, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"width"', 'length': 20, 'name': 'mbi_width',
                     'precision': 6, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"height"', 'length': 20, 'name': 'mbi_height',
                     'precision': 6, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}],
                'INPUT': overlap_joined,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            overlap_joined_refactored = overlap_joined_refactored_res['OUTPUT']

            # UPDATE PROGRESS (38)
            update_overlap_progress(38)

            count_bldg = processing.run("native:countpointsinpolygon", {
                'CLASSFIELD': '',
                'FIELD': 'num_bldg_pts',
                'OUTPUT': 'memory:',
                'POINTS': reprojected_bldg,
                'POLYGONS': overlap_joined_refactored,
                'WEIGHT': ''
            }, context=context, feedback=feedback)



            if feedback.isCanceled():
                return {}
            count_bldg_sf = count_bldg['OUTPUT']

            # UPDATE PROGRESS (42)
            update_overlap_progress(42)

            join_with_bgy_res = processing.run("native:joinattributesbylocation", {
                'DISCARD_NONMATCHING': False,
                'INPUT': count_bldg_sf,
                'JOIN': reprojected_bgy,
                'JOIN_FIELDS': ['geocode', 'region','province', 'city_mun', 'barangay'],
                'METHOD': 0,
                'OUTPUT': 'memory:',
                'PREDICATE': [0],
                'PREFIX': ''
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            join_with_bgy = join_with_bgy_res['OUTPUT']

            # UPDATE PROGRESS (45)
            update_overlap_progress(45)

            join_with_bgy_refactored_res = processing.run("native:refactorfields", {
                'FIELDS_MAPPING': [
                    {'alias': '', 'comment': '', 'expression': '"geocode"', 'length': 0, 'name': 'geocode',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"region"', 'length': 0, 'name': 'region',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"province"', 'length': 0, 'name': 'province',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"city_mun"', 'length': 0, 'name': 'city_mun',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"barangay"', 'length': 0, 'name': 'barangay',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"num_bldg_pts"', 'length': 0, 'name': 'num_bldg_pts',
                     'precision': 0, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"mbi_area"', 'length': 0, 'name': 'mbi_area',
                     'precision': 0, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"mbi_width"', 'length': 20, 'name': 'mbi_width',
                     'precision': 6, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"mbi_height"', 'length': 20, 'name': 'mbi_height',
                     'precision': 6, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"gmd_uuid"', 'length': 0, 'name': 'gmd_uuid',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'}],
                'INPUT': join_with_bgy,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            join_with_bgy_refactored = join_with_bgy_refactored_res['OUTPUT']

            # UPDATE PROGRESS (48)
            update_overlap_progress(48)

            # --- REPROJECTION BACK TO EPSG:4326 ---
            reprojected_overlap_res = processing.run("native:reprojectlayer", {
                'CONVERT_CURVED_GEOMETRIES': False,
                'INPUT': join_with_bgy_refactored,
                'OPERATION': '+proj=pipeline +step +inv +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84 +step +proj=unitconvert +xy_in=rad +xy_out=deg',
                'OUTPUT': 'memory:',
                'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326')
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            reprojected_overlap = reprojected_overlap_res['OUTPUT']

            feedback.pushInfo("Writing Overlap Layer")
            # Add the layer directly to the project as a temporary layer
            
            
            overlap_add_count_res = processing.run("native:refactorfields", {
                'FIELDS_MAPPING': [
                    {'alias': '','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"region"', 'length': 0, 'name': 'region','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"province"', 'length': 0, 'name': 'province','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"city_mun"', 'length': 0, 'name': 'city_mun','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"barangay"', 'length': 0, 'name': 'barangay','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                    {'alias': '','comment': '','expression': 'aggregate(\r\n layer:=@layer,\r\n aggregate:=\'count\',\r\n expression:="gmd_uuid",\r\n filter:="gmd_uuid" = attribute(@parent, \'gmd_uuid\')\r\n)','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                    {'alias': '','comment': '','expression': "'Overlap'",'length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                    ],
                'INPUT': reprojected_overlap,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            overlap_add_count = overlap_add_count_res['OUTPUT']
            
            overlap_add_count_fix_res = processing.run("native:fixgeometries", {
                'INPUT' : overlap_add_count, 
                'METHOD' : 1, 
                'OUTPUT' : 'memory:'
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            overlap_add_count_fix = overlap_add_count_fix_res['OUTPUT']
            
            feedback.pushInfo("Aggregating Layer")
            summary_aggregate_res = processing.run("native:aggregate", {
                'INPUT': overlap_add_count_fix,
                'GROUP_BY': 'gmd_uuid',
                'OUTPUT': 'memory:',
                'AGGREGATES':  [{'aggregate': 'first_value','delimiter': ',','input': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_type"','length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'concatenate','delimiter': ',','input': '"geocode"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'concatenate','delimiter': ';','input': "concat(barangay, ', ',city_mun)",'length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 0,'type_name': ''},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"region"','length': 0,'name': 'distinct_region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"province"','length': 0,'name': 'distinct_province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"city_mun"','length': 0,'name': 'distinct_city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"barangay"','length': 0,'name': 'distinct_barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}]
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            summary_aggregate = summary_aggregate_res['OUTPUT']
            
            
            summary_final_res = processing.run("native:refactorfields", {
                'INPUT': summary_aggregate,
                'OUTPUT': 'memory:',
                'FIELDS_MAPPING': [
                {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'GEOCODE','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Region','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Province','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Barangay','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas','comment': '','expression': '"involved_areas"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Names','comment': '','expression': '"involved_bgys"','length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Count','comment': '','expression': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                {'alias': 'MBI Area','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Width','comment': '','expression': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"distinct_region"','length': 0,'name': 'distinct_region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_province"','length': 0,'name': 'distinct_province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_city_mun"','length': 0,'name': 'distinct_city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_barangay"','length': 0,'name': 'distinct_barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Number of Bldg Points','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Type','comment': '','expression': '"mbi_type"','length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'MBI Level','comment': '','expression': 'CASE\r\n WHEN "distinct_region" > 1 THEN \'1_Inter-Region\'\r\n WHEN "distinct_province" > 1 THEN \'2_Inter-Province\'\r\n WHEN "distinct_city_mun" > 1 THEN \'3_Inter-City/Municipality\'\r\n WHEN "distinct_barangay" > 1 THEN \'4_Inter-Barangay\'\r\n ELSE \'5_Within-Barangay\'\r\nEND','length': 0,'name': 'mbi_level','precision': 0,'sub_type': 0,'type': 0,'type_name': ''},
                {'alias': 'MBI Category','comment': '','expression': '','length': 0,'name': 'mbi_category','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'MBI Status', 'comment': '', 'expression': 'CASE\r\n WHEN "mbi_level" IN (\'1_Inter-Region gap/overlap\', \'2_Inter-Province gap/overlap\') THEN \'2_Pending\'\r\n ELSE NULL\r\nEND', 'length': 0, 'name': 'mbi_status','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'alias': 'MBI Remarks','comment': '','expression': '','length': 0,'name': 'mbi_remarks','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                ]
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            summary_final = summary_final_res['OUTPUT']
            
            feedback.pushInfo("Refactoring Layer")
            
            summary_final_res_status = processing.run("native:refactorfields", {
                'INPUT': summary_final,
                'OUTPUT': 'memory:',
                'FIELDS_MAPPING': [
                {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'GEOCODE','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Region','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Province','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Barangay','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas','comment': '','expression': '"involved_areas"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Names','comment': '','expression': '"involved_bgys"','length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Count','comment': '','expression': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                {'alias': 'MBI Area','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Width','comment': '','expression': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"distinct_region"','length': 0,'name': 'distinct_region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_province"','length': 0,'name': 'distinct_province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_city_mun"','length': 0,'name': 'distinct_city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_barangay"','length': 0,'name': 'distinct_barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Number of Bldg Points','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Type','comment': '','expression': '"mbi_type"','length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'MBI Level','comment': '','expression': '"mbi_level"','length': 255,'name': 'mbi_level','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                #{'alias': 'MBI Category','comment': '','expression': '','length': 255,'name': 'mbi_category','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': 'MBI Status', 'comment': '', 'expression': 'CASE\r\n WHEN "mbi_level" IN (\'1_Inter-Region\', \'2_Inter-Province\') THEN \'2_Pending\'\r\n ELSE NULL\r\nEND', 'length': 255, 'name': 'mbi_status','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                #{'alias': 'MBI Remarks','comment': '','expression': '','length': 0,'name': 'mbi_remarks','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                ]
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            summary_final_status = summary_final_res_status['OUTPUT']

            summary_final_status_filtered_res = processing.run("native:extractbyexpression", {
                'EXPRESSION': 'NOT (mbi_area >= 0 AND mbi_area <= 0.1 AND num_bldg_pts = 0) AND geocode IS NOT NULL',
                'INPUT': summary_final_status,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}

            summary_final_status_filtered = summary_final_status_filtered_res['OUTPUT']
            
            
            feedback.pushInfo("Exporting Overlap Layer")
            export_layer(summary_final_status_filtered, r'Overlaps')
            

            #Tests
            #export_layer(count_bldg_sf, r'count_bldg_sf')
            #reprojected_bldg.setName("reprojected_bldg")
            #QgsProject.instance().addMapLayer(reprojected_bldg)
            #overlap_joined_refactored.setName("overlap_joined_refactored")
            #QgsProject.instance().addMapLayer(overlap_joined_refactored)







            #summary_final_status.setName("Overlaps")
            #QgsProject.instance().addMapLayer(summary_final_status, addToLegend=False)
            #group.addLayer(summary_final_status)



            #processing.run("native:setlayerstyle", {
            # 'INPUT' : summary_final_status,
            # 'STYLE': style_path
            #}, context=context, feedback=feedback)

            # Final progress update for the Overlaps block
            feedback.setProgress(progress_end)

        # --- GAPS ANALYSIS BLOCK ---
        if run_gaps:
            QgsMessageLog.logMessage("Starting Gaps Analysis...")

            # Define a starting point for progress if only Gaps is run
            progress_start = 10 if run_mode == 2 else 55
            progress_end = 100
            progress_range = progress_end - progress_start

            def update_gaps_progress(step):
                # steps are approximately from 60 to 96 (36 steps)
                # Rescale original range (55-96) to the current active range (10-100 or 55-100)
                original_range = 96 - 55  # 41 total points for old gaps section up to the end

                # Check if we are past the initial progress point to avoid dividing by zero or negative range
                if step < 55:
                    # If step is less than 55, it's an issue, but for safety, ensure we don't regress progress.
                    return

                new_progress = progress_start + (step - 55) * progress_range / original_range
                feedback.setProgress(int(new_progress))

            # UPDATE PROGRESS (60)
            update_gaps_progress(60)

            dissolved_bgy = processing.run("native:dissolve", {
                'FIELD': '',
                'INPUT': bgy_layer,
                'OUTPUT': 'memory:',
                'SEPARATE_DISJOINT': False
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            dissolved_bgy_sf = dissolved_bgy['OUTPUT']

            # UPDATE PROGRESS (65)
            update_gaps_progress(65)

            delete_holes = processing.run("native:deleteholes", {
                'INPUT': dissolved_bgy_sf,
                'MIN_AREA': 0,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            delete_holes_sf = delete_holes['OUTPUT']

            # UPDATE PROGRESS (70)
            update_gaps_progress(70)

            dissolved_bgy_cleaned = processing.run("native:dissolve", {
                'FIELD': '',
                'INPUT': delete_holes_sf,
                'OUTPUT': 'memory:',
                'SEPARATE_DISJOINT': False
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            dissolved_bgy_cleaned_sf = dissolved_bgy_cleaned['OUTPUT']


            # UPDATE PROGRESS (72)
            update_gaps_progress(72)

            difference_bgy = processing.run("native:difference", {
                'GRID_SIZE': 'None',
                'INPUT': dissolved_bgy_cleaned_sf,
                'OVERLAY': dissolved_bgy_sf,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            difference_bgy_sf = difference_bgy['OUTPUT']

            # UPDATE PROGRESS (75)
            update_gaps_progress(75)

            reprojected_difference_bgy_sf_res = processing.run("native:reprojectlayer", {
                'CONVERT_CURVED_GEOMETRIES': False,
                'INPUT': difference_bgy_sf,
                'OPERATION': '+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84',
                'OUTPUT': 'memory:',
                'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:3857')
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            reprojected_difference_bgy_sf = reprojected_difference_bgy_sf_res['OUTPUT']


            multi_to_single = processing.run("native:multiparttosingleparts", {
                'INPUT': reprojected_difference_bgy_sf,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            multi_to_single_sf = multi_to_single['OUTPUT']

            # UPDATE PROGRESS (78)
            update_gaps_progress(78)

            multi_to_single_sf_uuid_res = processing.run("native:refactorfields", {
                'FIELDS_MAPPING': [
                    {'alias': '', 'comment': '', 'expression': 'substr($uuid, 2,36)', 'length': 0, 'name': 'gmd_uuid',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'}],
                'INPUT': multi_to_single_sf,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            multi_to_single_sf_uuid = multi_to_single_sf_uuid_res['OUTPUT']

            # UPDATE PROGRESS (80)
            update_gaps_progress(80)

            min_bounding_gap = processing.run("qgis:minimumboundinggeometry", {
                'FIELD': 'gmd_uuid',
                'INPUT': multi_to_single_sf_uuid,
                'OUTPUT': 'memory:',
                'TYPE': 1
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            min_bounding_gap_sf = min_bounding_gap['OUTPUT']

            # UPDATE PROGRESS (82)
            update_gaps_progress(82)

            gap_joined_res = processing.run("native:joinattributestable", {
                'DISCARD_NONMATCHING': False,
                'FIELD': 'gmd_uuid',
                'FIELDS_TO_COPY': ['gmd_uuid', 'width', 'height'],
                'FIELD_2': 'gmd_uuid',
                'INPUT': multi_to_single_sf_uuid,
                'INPUT_2': min_bounding_gap_sf,
                'METHOD': 1,
                'OUTPUT': 'memory:',
                'PREFIX': ''
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            gap_joined = gap_joined_res['OUTPUT']

            # UPDATE PROGRESS (88)
            update_gaps_progress(88)

            gap_joined_refactored_res = processing.run("native:refactorfields", {
                'FIELDS_MAPPING': [
                    {'alias': '', 'comment': '', 'expression': '"gmd_uuid"', 'length': 0, 'name': 'gmd_uuid',
                     'precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': ' round($area , 2)', 'length': 0, 'name': 'mbi_area',
                     'precision': 0, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"width"', 'length': 20, 'name': 'mbi_width',
                     'precision': 6, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'},
                    {'alias': '', 'comment': '', 'expression': '"height"', 'length': 20, 'name': 'mbi_height',
                     'precision': 6, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}],
                'INPUT': gap_joined,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            gap_joined_refactored = gap_joined_refactored_res['OUTPUT']

            # UPDATE PROGRESS (92)
            update_gaps_progress(92)

            count_bldg_gap = processing.run("native:countpointsinpolygon", {
                'CLASSFIELD': '',
                'FIELD': 'num_bldg_pts',
                'OUTPUT': 'memory:',
                'POINTS': reprojected_bldg,
                'POLYGONS': gap_joined_refactored,
                'WEIGHT': ''
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            count_bldg_gap_sf = count_bldg_gap['OUTPUT']

            # UPDATE PROGRESS (96)
            update_gaps_progress(96)

            reprojected_count_bldg_gap_sf_res = processing.run("native:reprojectlayer", {
                'CONVERT_CURVED_GEOMETRIES': False,
                'INPUT': count_bldg_gap_sf,
                'OPERATION': '+proj=pipeline +step +inv +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84 +step +proj=unitconvert +xy_in=rad +xy_out=deg',
                'OUTPUT': 'memory:',
                'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326')
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            reprojected_count_bldg_gap_sf = reprojected_count_bldg_gap_sf_res['OUTPUT']

            reprojected_reprojected_bgy_res = processing.run("native:reprojectlayer", {
                'CONVERT_CURVED_GEOMETRIES': False,
                'INPUT': reprojected_bgy,
                'OPERATION': '+proj=pipeline +step +inv +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84 +step +proj=unitconvert +xy_in=rad +xy_out=deg',
                'OUTPUT': 'memory:',
                'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326')
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            reprojected_reprojected_bgy = reprojected_reprojected_bgy_res['OUTPUT']

            count_bldg_gap_sf_buffered_res = processing.run("native:buffer", {
                'DISSOLVE': False,
                'DISTANCE': 1,
                'END_CAP_STYLE': 2,
                'INPUT': count_bldg_gap_sf,
                'JOIN_STYLE': 2,
                'MITER_LIMIT': 2,
                'OUTPUT': 'memory:',
                'SEGMENTS': 5,
                'SEPARATE_DISJOINT': False
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            count_bldg_gap_sf_buffered = count_bldg_gap_sf_buffered_res['OUTPUT']


            join_with_bgy_gap_res = processing.run("native:joinattributesbylocation", {
                'DISCARD_NONMATCHING': False,
                'INPUT': count_bldg_gap_sf_buffered,
                'JOIN': reprojected_bgy,
                'JOIN_FIELDS': ['geocode', 'region', 'province', 'city_mun', 'barangay'],
                'METHOD': 0,
                'OUTPUT': 'memory:',
                'PREDICATE': [0,3,4],
                'PREFIX': ''
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            join_with_bgy_gap = join_with_bgy_gap_res['OUTPUT']

            # UPDATE PROGRESS (98)
            update_gaps_progress(98)

            join_with_bgy_gap_table_res = processing.run("native:joinattributestable", {
                'DISCARD_NONMATCHING': False,
                'FIELD': 'gmd_uuid',
                'FIELDS_TO_COPY': ['geocode', 'region', 'province', 'city_mun', 'barangay'],
                'FIELD_2': 'gmd_uuid',
                'INPUT': count_bldg_gap_sf,
                'INPUT_2': join_with_bgy_gap,
                'METHOD': 0,
                'OUTPUT': 'TEMPORARY_OUTPUT',
                'PREFIX': ''
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            join_with_bgy_gap = join_with_bgy_gap_table_res['OUTPUT']



            reprojected_gap_res = processing.run("native:reprojectlayer", {
                'CONVERT_CURVED_GEOMETRIES': False,
                'INPUT': join_with_bgy_gap,
                'OPERATION': '+proj=pipeline +step +inv +proj=webmerc +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84 +step +proj=unitconvert +xy_in=rad +xy_out=deg',
                'OUTPUT': 'memory:',
                'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326')
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            reprojected_gap = reprojected_gap_res['OUTPUT']

            feedback.pushInfo("Writing Gaps Layer")
            
            gap_add_count_res = processing.run("native:refactorfields", {
                'FIELDS_MAPPING': [
                    {'alias': '','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"region"', 'length': 0, 'name': 'region','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"province"', 'length': 0, 'name': 'province','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"city_mun"', 'length': 0, 'name': 'city_mun','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '', 'comment': '', 'expression': '"barangay"', 'length': 0, 'name': 'barangay','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                    {'alias': '','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                    {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                    {'alias': '','comment': '','expression': 'aggregate(\r\n layer:=@layer,\r\n aggregate:=\'count\',\r\n expression:="gmd_uuid",\r\n filter:="gmd_uuid" = attribute(@parent, \'gmd_uuid\')\r\n)','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                    {'alias': '','comment': '','expression': "'Gap'",'length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                    ],
                'INPUT': reprojected_gap,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}
            gap_add_count = gap_add_count_res['OUTPUT']
            
            gap_add_count_fix_res = processing.run("native:fixgeometries", {
                'INPUT' : gap_add_count, 
                'METHOD' : 1, 
                'OUTPUT' : 'memory:'
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            gap_add_count_fix = gap_add_count_fix_res['OUTPUT']
            
               
            gap_summary_aggregate_res = processing.run("native:aggregate", {
                'INPUT': gap_add_count_fix,
                'GROUP_BY': 'gmd_uuid',
                'OUTPUT': 'memory:',
                'AGGREGATES':  [{'aggregate': 'first_value','delimiter': ',','input': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                {'aggregate': 'first_value','delimiter': ',','input': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'first_value','delimiter': ',','input': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                {'aggregate': 'first_value','delimiter': ',','input': '"mbi_type"','length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'concatenate','delimiter': ',','input': '"geocode"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'concatenate','delimiter': ';','input': "concat(barangay, ', ',city_mun)",'length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 0,'type_name': ''},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"region"','length': 0,'name': 'distinct_region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"province"','length': 0,'name': 'distinct_province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"city_mun"','length': 0,'name': 'distinct_city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'aggregate': 'count_distinct','delimiter': ',','input': '"barangay"','length': 0,'name': 'distinct_barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}]
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            gap_summary_aggregate = gap_summary_aggregate_res['OUTPUT']
            
            
            gap_summary_final_res = processing.run("native:refactorfields", {
                'INPUT': gap_summary_aggregate,
                'OUTPUT': 'memory:',
                'FIELDS_MAPPING': [
                {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'GEOCODE','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Region','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Province','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Barangay','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas','comment': '','expression': '"involved_areas"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Names','comment': '','expression': '"involved_bgys"','length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Count','comment': '','expression': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                {'alias': 'MBI Area','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Width','comment': '','expression': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"distinct_region"','length': 0,'name': 'distinct_region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_province"','length': 0,'name': 'distinct_province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_city_mun"','length': 0,'name': 'distinct_city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_barangay"','length': 0,'name': 'distinct_barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Number of Bldg Points','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Type','comment': '','expression': '"mbi_type"','length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'MBI Level','comment': '','expression': 'CASE\r\n WHEN "distinct_region" > 1 THEN \'1_Inter-Region\'\r\n WHEN "distinct_province" > 1 THEN \'2_Inter-Province\'\r\n WHEN "distinct_city_mun" > 1 THEN \'3_Inter-City/Municipality\'\r\n WHEN "distinct_barangay" > 1 THEN \'4_Inter-Barangay\'\r\n ELSE \'5_Within-Barangay\'\r\nEND','length': 0,'name': 'mbi_level','precision': 0,'sub_type': 0,'type': 0,'type_name': ''},
                {'alias': 'MBI Category','comment': '','expression': '','length': 0,'name': 'mbi_category','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'MBI Status', 'comment': '', 'expression': 'CASE\r\n WHEN "mbi_level" IN (\'1_Inter-Region\', \'2_Inter-Province\') THEN \'2_Pending\'\r\n ELSE NULL\r\nEND', 'length': 0, 'name': 'mbi_status','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                {'alias': 'MBI Remarks','comment': '','expression': '','length': 0,'name': 'mbi_remarks','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                ]
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            gap_summary_final = gap_summary_final_res['OUTPUT']
            
            gap_summary_final_res_status = processing.run("native:refactorfields", {
                'INPUT': gap_summary_final,
                'OUTPUT': 'memory:',
                'FIELDS_MAPPING': [
                {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'GEOCODE','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Region','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Province','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Barangay','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas','comment': '','expression': '"involved_areas"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Names','comment': '','expression': '"involved_bgys"','length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Involved Areas - Count','comment': '','expression': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                {'alias': 'MBI Area','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Width','comment': '','expression': '"mbi_width"','length': 20,'name': 'mbi_width','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"mbi_height"','length': 20,'name': 'mbi_height','precision': 6,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': '','comment': '','expression': '"distinct_region"','length': 0,'name': 'distinct_region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_province"','length': 0,'name': 'distinct_province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_city_mun"','length': 0,'name': 'distinct_city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': '','comment': '','expression': '"distinct_barangay"','length': 0,'name': 'distinct_barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Number of Bldg Points','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                #{'alias': 'MBI Type','comment': '','expression': '"mbi_type"','length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'MBI Level','comment': '','expression': '"mbi_level"', 'length': 0,'name': 'mbi_level','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                #{'alias': 'MBI Category','comment': '','expression': '','length': 0,'name': 'mbi_category','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                #{'alias': 'MBI Status', 'comment': '', 'expression': 'CASE\r\n WHEN "mbi_level" IN (\'1_Inter-Region gap/overlap\', \'2_Inter-Province gap/overlap\') THEN \'2_Pending\'\r\n ELSE NULL\r\nEND', 'length': 0, 'name': 'mbi_status','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                #{'alias': 'MBI Remarks','comment': '','expression': '','length': 0,'name': 'mbi_remarks','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                ]
            }, context=context, feedback=feedback)
            
            if feedback.isCanceled():
                return {}
            gap_summary_final_status = gap_summary_final_res_status['OUTPUT']

            gap_summary_final_status_filtered_res = processing.run("native:extractbyexpression", {
                'EXPRESSION': 'NOT (mbi_area >= 0 AND mbi_area <= 0.1 AND num_bldg_pts = 0) AND geocode IS NOT NULL',
                'INPUT': gap_summary_final_status,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)

            if feedback.isCanceled():
                return {}

            gap_summary_final_status_filtered = gap_summary_final_status_filtered_res['OUTPUT']
            
            
            #processing.run("native:setlayerstyle", {
            # 'INPUT' : gap_summary_final_status,
            # 'STYLE': style_path
            #}, context=context, feedback=feedback)


            export_layer(gap_summary_final_status_filtered, r'Gaps')
            #export_layer(reprojected_gap, r'reprojected_gap')
            #export_layer(count_bldg_gap_sf, r'count_bldg_gap_sf')
            




            

            #gap_summary_final_status.setName("Gaps")
            #QgsProject.instance().addMapLayer(gap_summary_final_status, addToLegend=False)
            #group.addLayer(gap_summary_final_status)
            
            #group_id = group_name
            #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_file_path = os.path.join(export_folder, f"gaps_overlap_{timestamp}.gpkg")
            
            
            def export_layer_final(overlap_layer, gap_layer, file_path):
                if export_enabled:
                    #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    overlap_layer_refactor = processing.run("native:refactorfields", {
                        'INPUT': overlap_layer,
                        'OUTPUT': 'memory:',
                        'FIELDS_MAPPING': [
                        {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'GEOCODE','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Region','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Province','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Barangay','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas','comment': '','expression': '"involved_areas"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas - Names','comment': '','expression': '"involved_bgys"','length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas - Count','comment': '','expression': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                        {'alias': 'MBI Area','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                        {'alias': 'Number of Bldg Points','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                        {'alias': 'MBI Type','comment': '','expression': "'Overlap'",'length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Level','comment': '','expression': '"mbi_level"','length': 0,'name': 'mbi_level','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Category','comment': '','expression': '"mbi_category"','length': 0,'name': 'mbi_category','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Status', 'comment': '', 'expression': '"mbi_status"', 'length': 0, 'name': 'mbi_status','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                        {'alias': 'MBI Remarks','comment': '','expression': '','length': 0,'name': 'mbi_remarks','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                        ]
                    }, context=context, feedback=feedback)
                
                    gap_layer_refactor = processing.run("native:refactorfields", {
                        'INPUT': gap_layer,
                        'OUTPUT': 'memory:',
                        'FIELDS_MAPPING': [
                        {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'GEOCODE','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Region','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Province','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Barangay','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas','comment': '','expression': '"involved_areas"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas - Names','comment': '','expression': '"involved_bgys"','length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas - Count','comment': '','expression': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                        {'alias': 'MBI Area','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                        {'alias': 'Number of Bldg Points','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                        {'alias': 'MBI Type','comment': '','expression': "'Gap'",'length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Level','comment': '','expression': '"mbi_level"', 'length': 0,'name': 'mbi_level','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Category','comment': '','expression': '"mbi_category"','length': 0,'name': 'mbi_category','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Status', 'comment': '', 'expression': '"mbi_status"', 'length': 0, 'name': 'mbi_status','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                        {'alias': 'MBI Remarks','comment': '','expression': '','length': 0,'name': 'mbi_remarks','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                        ]
                    }, context=context, feedback=feedback)
                    
                    for_export_layer = processing.run("native:mergevectorlayers", {
                        'CRS' : QgsCoordinateReferenceSystem('EPSG:4326'), 
                        'LAYERS' : [
                            overlap_layer_refactor['OUTPUT'],
                            gap_layer_refactor['OUTPUT']], 
                        'OUTPUT' : 'memory:' 
                    }, context=context, feedback=feedback)
                    
                    #file_path = f"'ogr:dbname=\',os.path.join(export_folder, f"gaps_overlap.gpkg"),\' table="gaps_overlap" (geom)'"
                    
                    #file_path = os.path.join(export_folder, "gaps_overlap.gpkg")
                    
                    # Check if file exists and delete it to allow overwriting
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            feedback.pushInfo(f"Existing file {filename} found and removed for overwrite.")
                        except Exception as e:
                            feedback.reportError(f"Could not remove existing file: {str(e)}")
                    
                    for_export_layer_refactor = processing.run("native:refactorfields", {
                        'INPUT': for_export_layer['OUTPUT'],
                        'OUTPUT' : file_path,
                        'FIELDS_MAPPING': [
                        {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': '','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Region ','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Province ','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Barangay ','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas','comment': '','expression': '"involved_areas"','length': 0,'name': 'involved_areas','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas - Names','comment': '','expression': '"involved_bgys"','length': 0,'name': 'involved_bgys','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'Involved Areas - Count','comment': '','expression': '"count_involved_areas"','length': 0,'name': 'count_involved_areas','precision': 0,'sub_type': 0,'type': 4,'type_name': 'int8'},
                        {'alias': 'MBI Area','comment': '','expression': '"mbi_area"','length': 0,'name': 'mbi_area','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                        {'alias': 'Number of Bldg Points','comment': '','expression': '"num_bldg_pts"','length': 0,'name': 'num_bldg_pts','precision': 0,'sub_type': 0,'type': 6,'type_name': 'double precision'},
                        {'alias': 'MBI Type','comment': '','expression': '"mbi_type"','length': 0,'name': 'mbi_type','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Level','comment': '','expression': '"mbi_level"', 'length': 0,'name': 'mbi_level','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Category','comment': '','expression': '"mbi_category"','length': 0,'name': 'mbi_category','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                        {'alias': 'MBI Status', 'comment': '', 'expression': '"mbi_status"', 'length': 0, 'name': 'mbi_status','precision': 0, 'sub_type': 0, 'type': 10, 'type_name': 'text'},
                        {'alias': 'MBI Remarks','comment': '','expression': '','length': 0,'name': 'mbi_remarks','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}
                        ]
                    }, context=context, feedback=feedback)
                    
                    layer_details = QgsProcessingContext.LayerDetails(
                        f"Gaps and Overlap ({timestamp})",
                        context.project(),
                        "OUTPUT"
                    )
                    #layer_details.destinationGroupId = group_id
                    
                    processor = MBIStylePostProcessor(style_path)
                    self.post_processors.append(processor)
                    layer_details.setPostProcessor(processor)
                    
                    context.addLayerToLoadOnCompletion(file_path, layer_details)
                    feedback.pushInfo(f"Layer queued for native loading in group")
            
            if run_mode == 0: # Should be running both gaps and overlaps
                export_layer_final(summary_final_status_filtered, gap_summary_final_status_filtered, export_file_path)
            
            feedback.pushInfo(f"Done setting layer style")

            

            # Add the layer directly to the project as a temporary layer
            #QgsProject.instance().addMapLayer(gap_summary_final.setName("Gaps") or gap_summary_final)

            # Final progress update for the Gaps block
            feedback.setProgress(progress_end)

        # --- 8. RETURN OUTPUT ---
        # Return an empty dictionary since layers are added directly to the project
        return {}