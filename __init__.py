from __future__ import absolute_import

__author__ = 'Geospatial Management Division'
__date__ = '2025-07-01'
__copyright__ = '(C) 2026, Geospatial Management Division'

import pathlib
import sys

# Add vendor package path (contains gemma_sync) to sys.path
src_dir = pathlib.Path(__file__).parent.resolve()
unzipped_whl = src_dir / "references" / "package_qfield" / "unzipped_whl"
if unzipped_whl.exists() and str(unzipped_whl) not in sys.path:
    sys.path.append(str(unzipped_whl))


def classFactory(iface):
    """
    Returns an instance of the plugin class.
    This function is required by QGIS.
    """
    from .gmd_pipeline import GMDPipeline
    return GMDPipeline(iface)
