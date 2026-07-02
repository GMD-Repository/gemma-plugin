# -*- coding: utf-8 -*-
"""
Create Enumeration Areas -- Plugin Main Class
----------------------------------------------
Registers the Processing provider and adds a toolbar button + menu entry
so users can open "Create Enumeration Areas" directly from the QGIS UI.
"""

import os
from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from .provider import EADelineationProvider


class EADelineationPlugin:
    """
    Main plugin class instantiated by classFactory().

    Lifecycle:
      - __init__  : store iface reference
      - initGui   : register provider + add toolbar button + menu item
      - unload    : remove toolbar button + menu item + deregister provider
    """

    MENU_LABEL = "&Create Enumeration Areas"
    ACTION_LABEL = "Create Enumeration Areas"
    ALGORITHM_ID = "eadelineation:createea"

    def __init__(self, iface):
        """
        :param iface: QGIS interface instance (QgsInterface).
        """
        self.iface = iface
        self.provider = None
        self.action = None

    # ------------------------------------------------------------------
    # Icon resolution
    # ------------------------------------------------------------------
    def _icon(self):
        """
        Returns the plugin icon.
        Priority:
          1. icon.png shipped alongside this file
          2. QGIS built-in Processing algorithm icon (always available)
        """
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QgsApplication.getThemeIcon("/processingAlgorithm.svg")

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------
    def initGui(self):
        """
        Called by QGIS when the plugin is enabled.
        Registers the Processing provider and adds the toolbar + menu action.
        """
        # 1. Register Processing provider (makes algorithm visible in Toolbox)
        self.provider = EADelineationProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        # 2. Create toolbar / menu action
        self.action = QAction(
            self._icon(),
            self.ACTION_LABEL,
            self.iface.mainWindow(),
        )
        self.action.setToolTip(
            "Open the Create Enumeration Areas dialog"
        )
        self.action.setStatusTip(
            "Create Enumeration Areas -- splits/merges EAs to meet household thresholds"
        )
        self.action.triggered.connect(self._open_dialog)

        # 3. Add to QGIS main toolbar and Plugins menu
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.MENU_LABEL, self.action)

    def unload(self):
        """
        Called when the plugin is disabled or QGIS exits.
        Removes the toolbar icon, menu entry, and deregisters the provider.
        """
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu(self.MENU_LABEL, self.action)
            self.action = None

        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------
    def _open_dialog(self):
        """
        Shows the branded EA Launcher dialog.
        The user can then click "Open Algorithm" to proceed to the
        full Processing parameter dialog.
        """
        from .dialog import EALauncherDialog
        dlg = EALauncherDialog(self.iface.mainWindow())
        dlg.exec_()
