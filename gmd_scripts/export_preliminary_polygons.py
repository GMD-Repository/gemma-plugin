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


class ExportPreliminaryPolygons(QgsProcessingAlgorithm):
    
    def __init__(self):
        super().__init__()
        self.post_processors = []

    def name(self):
        return 'export_preliminary_polygons'

    def displayName(self):
        return 'Export Preliminary Polygons'

    def group(self):
        return '1Map'

    def groupId(self):
        return '1map'

    def createInstance(self):
        return ExportPreliminaryPolygons()

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons/upload.png'))

    INPUT1 = 'INPUT1'

    def shortHelpString(self):
        return (
            "This tool shall be used to merge the barangay layers after resolving the Topological Layers \n"
            "Changelogs \n"
            "-This is the initial release"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT1,
                'Select Barangay Polygon Layer(s)',
                QgsProcessing.TypeVectorPolygon
            )
        )

    def processAlgorithm(self, parameters, context, feedback: QgsProcessingFeedback):
        bgy_list = self.parameterAsLayerList(parameters, self.INPUT1, context)
        export_folder = r"C:\PSA-GIS\2026 1Map\Preliminary Output"
        
        # Ensure style path is valid
        style_path = r'C:\Users\Admin\OneDrive - Philippine Statistics Authority\GMD\2026\1Map\GMD Plugin\gmd_pipeline\styles\mbi_checker.qml'
        
        self.post_processors = []
        
        if not os.path.exists(export_folder):
            try:
                os.makedirs(export_folder)
                feedback.pushInfo(f"Created directory: {export_folder}")
            except Exception as e:
                feedback.reportError(f"Could not create directory {export_folder}: {str(e)}")
                return {}

        if not bgy_list:
            raise QgsProcessingException("Barangay Polygon Layer(s) must be selected.")

        feedback.pushInfo("Merging Selected Layers...")
        feedback.setProgress(10)

        # Merge for Barangay Polygons
        bgy_layer = processing.run("native:mergevectorlayers", {
            'LAYERS': bgy_list,
            'CRS': bgy_list[0].crs(),
            'OUTPUT': 'memory:'
        }, context=context, feedback=feedback)['OUTPUT']

        feedback.setProgress(40)

        reprojected_bgy_res = processing.run("native:reprojectlayer", {
            'CONVERT_CURVED_GEOMETRIES': False,
            'INPUT': bgy_layer,
            'OUTPUT': 'memory:',
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326')
        }, context=context, feedback=feedback)
        
        if feedback.isCanceled():
            return {}
            
        reprojected_bgy = reprojected_bgy_res['OUTPUT']
        feedback.setProgress(60)
        
        # Dynamic naming logic
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        first_feature = next(reprojected_bgy.getFeatures(), None)
        if first_feature:
            try:
                geocode_idx = reprojected_bgy.fields().lookupField('geocode')
                province_idx = reprojected_bgy.fields().lookupField('province')
                
                geocode_val = str(first_feature.attributes()[geocode_idx])
                province_val = str(first_feature.attributes()[province_idx])
                
                rrppp_provname = f"{geocode_val[:3]}_{province_val}"
            except Exception as e:
                feedback.pushInfo(f"Could not parse attributes for naming: {e}. Using timestamp.")
                rrppp_provname = f"Merged_{timestamp}"
        else:
            rrppp_provname = f"Merged_{timestamp}"


        def export_layer(target, layer_name, set_style=True):
            if target is None:
                feedback.reportError(f"Skipping {layer_name}: Layer target is None.")
                return

            details = QgsProcessingContext.LayerDetails(layer_name, context.project(), "OUTPUT")
            
            if set_style:
                processor = MBIStylePostProcessor(style_path)
                self.post_processors.append(processor)
                details.setPostProcessor(processor)

            if isinstance(target, str):
                context.addLayerToLoadOnCompletion(target, details)
            elif isinstance(target, QgsVectorLayer):
                target.setName(layer_name)
                context.temporaryLayerStore().addMapLayer(target)
                context.addLayerToLoadOnCompletion(target.id(), details)

        # Final Export Path and Execution
        export_file_path = os.path.join(export_folder, f"{rrppp_provname}.gpkg")
        
        feedback.pushInfo(f"Saving merged layer to: {export_file_path}")
        
        refactored_bgy_res = processing.run("native:refactorfields", {
            'FIELDS_MAPPING' : 
                [{'alias': '','comment': '','expression': '"geocode"','length': 0,'name': 'geocode','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Region ','comment': '','expression': '"region"','length': 0,'name': 'region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Province ','comment': '','expression': '"province"','length': 0,'name': 'province','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'City/Municipality','comment': '','expression': '"city_mun"','length': 0,'name': 'city_mun','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Barangay ','comment': '','expression': '"barangay"','length': 0,'name': 'barangay','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Region - RSSO Office','comment': '','expression': '"office_region"','length': 0,'name': 'office_region','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Province - PSO Office','comment': '','expression': '"office_pso"','length': 0,'name': 'office_pso','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Code ','comment': '','expression': '"code"','length': 0,'name': 'code','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Source ','comment': '','expression': '"source"','length': 0,'name': 'source','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': 'Household Count','comment': '','expression': '"hhcount"','length': 0,'name': 'hhcount','precision': 0,'sub_type': 0,'type': 2,'type_name': 'integer'},
                {'alias': 'Building Count','comment': '','expression': '"bldgcount"','length': 0,'name': 'bldgcount','precision': 0,'sub_type': 0,'type': 2,'type_name': 'integer'},
                {'alias': 'SY ','comment': '','expression': '"sy"','length': 0,'name': 'sy','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'},
                {'alias': '','comment': '','expression': '"gmd_uuid"','length': 0,'name': 'gmd_uuid','precision': 0,'sub_type': 0,'type': 10,'type_name': 'text'}],
            'INPUT': reprojected_bgy,
            'OUTPUT': export_file_path
        }, context=context, feedback=feedback)
        
        if feedback.isCanceled():
            return {}
        refactored_bgy = refactored_bgy_res['OUTPUT']

        # Load the saved file into the project group
        export_layer(export_file_path, rrppp_provname, set_style=False)
        
        feedback.setProgress(100)

        return {}