# -*- coding: utf-8 -*-
"""
Create Enumeration Areas — QGIS Plugin Entry Point
----------------------------------------------------
QGIS calls classFactory(iface) when the plugin is loaded.
"""


def classFactory(iface):
    """
    Load EADelineationPlugin.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    :rtype: EADelineationPlugin
    """
    from .plugin import EADelineationPlugin
    return EADelineationPlugin(iface)
