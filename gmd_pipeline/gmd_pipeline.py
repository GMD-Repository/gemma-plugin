__author__ = 'Geospatial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geospatial Management Division'


import os
import sys
import inspect
import processing

from qgis.core import QgsApplication, QgsMessageLog, QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication

from qgis.PyQt.QtCore import QVariant
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton
from qgis.utils import iface
from .gmd_pipeline_provider import GmdPipelineProvider


class GMDPipeline(object):

    def __init__(self):
        self.iface = iface
        self.gema_menu = None
        self.provider = None
        self.toolbar = None
        self.geometry_toolkit_dlg = None

    def gema_add_submenu(self, submenu, icon):
        if self.gema_menu != None:
            submenu.setIcon(QIcon(icon))
            self.gema_menu.addMenu(submenu)
        else:
            self.iface.addPluginToMenu("&GeMa", submenu.menuAction())


    def initProcessing(self):
        self.provider = GmdPipelineProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)


    def initGui(self):
        self.initProcessing()

        self.gema_menu = QMenu("GeMa")
        self.iface.mainWindow().menuBar().insertMenu(self.iface.firstRightStandardMenu().menuAction(), self.gema_menu)

        self.reports_menu = QMenu(u'Reports')
        icon = QIcon(os.path.dirname(__file__) + "/icons/reports.png")
        self.gema_add_submenu(self.reports_menu, icon)

        icon = QIcon(os.path.dirname(__file__) + "/icons/reports.png")
        self.sync_report = QAction(icon, "Sync MBI Layer", self.iface.mainWindow())
        self.sync_report.triggered.connect(self.sync_report_act)
        self.reports_menu.addAction(self.sync_report)

        # Tools submenu
        self.tools_menu = QMenu(u'Tools')
        icon = QIcon(os.path.dirname(__file__) + "/icons/reports.png")
        self.gema_add_submenu(self.tools_menu, icon)

        self.geometry_toolkit_action = QAction("Geometry Repair Toolkit", self.iface.mainWindow())
        self.geometry_toolkit_action.triggered.connect(self.show_geometry_toolkit)
        self.tools_menu.addAction(self.geometry_toolkit_action)



    def unload(self):
        self.iface.mainWindow().menuBar().removeAction(self.gema_menu.menuAction())

        if self.provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Error removing GMD Pipeline provider: {e}",
                    'GMD')
            finally:
                del self.provider
                self.provider = None

    def sync_report_act(self):
        from .gmd_scripts import gsheet
        
        gsheet.sync_mbi_layers()

    def show_geometry_toolkit(self):
        """Open the Geometry Repair Toolkit dialog."""
        from .gmd_scripts.geom_repair_toolkit import GeometryToolkit
        
        if self.geometry_toolkit_dlg is None:
            self.geometry_toolkit_dlg = GeometryToolkit()
        
        self.geometry_toolkit_dlg.show()
        self.geometry_toolkit_dlg.raise_()
        self.geometry_toolkit_dlg.activateWindow()