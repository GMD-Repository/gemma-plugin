# -*- coding: utf-8 -*-
"""
Create Enumeration Areas — Processing Provider
------------------------------------------------
Registers algorithms from this plugin under the "GMD Toolkits"
group in the QGIS Processing Toolbox.
"""

import os
from qgis.core import QgsProcessingProvider


class EADelineationProvider(QgsProcessingProvider):
    """
    Processing provider that exposes the CreateEAAlgorithm to the
    QGIS Processing Toolbox under the 'GMD Toolkits' group.
    """

    def id(self):
        """
        Unique, lowercase provider identifier.
        Must match the groupId() returned by algorithms in this provider.
        """
        return "eadelineation"

    def name(self):
        """Short display name shown in the Processing Toolbox."""
        return "GMD Pipeline"

    def longName(self):
        """Full provider name shown in provider details."""
        return "GMD Pipeline Tools"

    def icon(self):
        """
        Returns the provider icon.
        Falls back to the default Processing icon if no custom icon is found.
        """
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            from qgis.PyQt.QtGui import QIcon
            return QIcon(icon_path)
        return super().icon()

    def loadAlgorithms(self):
        """
        Register all algorithms this provider exposes.
        Called automatically by QGIS when the provider is added to the registry.
        """
        from .algorithm import CreateEAAlgorithm
        self.addAlgorithm(CreateEAAlgorithm())
