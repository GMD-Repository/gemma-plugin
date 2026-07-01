__author__ = 'Geospatial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geospatial Management Division'

def classFactory(iface):
    """
    Returns an instance of the provider class.
    This function is required by QGIS.
    """
    from .gmd_pipeline import GMDPipeline
    return GMDPipeline()
