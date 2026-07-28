__author__ = 'Geospatial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geospatial Management Division'


import os
import sys
import inspect
import processing

from qgis.core import QgsApplication, QgsMessageLog, QgsProcessingProvider, QgsOfflineEditing, QgsProject
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication, Qt

from qgis.PyQt.QtCore import QVariant
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton
from qgis.utils import iface
from .gmd_pipeline_provider import GmdPipelineProvider


class GMDPipeline(object):

    def __init__(self, iface):
        self.iface = iface
        self.gema_menu = None
        self.provider = None
        self.toolbar = None
        self.geometry_toolkit_dlg = None
        self.push_dlg = None
        self.create_ea_action = None
        self.ea_dlg = None
        self.offline_editing = None
        self.ea_provider = None

    def gema_add_submenu(self, submenu, icon):
        if self.gema_menu != None:
            submenu.setIcon(QIcon(icon))
            self.gema_menu.addMenu(submenu)
        else:
            self.iface.addPluginToMenu("&Gemma", submenu.menuAction())


    def initProcessing(self):
        self.provider = GmdPipelineProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

        from .references.create_enumeration_area.provider import EADelineationProvider
        self.ea_provider = EADelineationProvider()
        QgsApplication.processingRegistry().addProvider(self.ea_provider)


    def initGui(self):
        self.initProcessing()

        self.gema_menu = QMenu("Gemma")
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

        # QField submenu
        self.qfield_menu = QMenu(u'QField')
        icon = QIcon(os.path.dirname(__file__) + "/icons/packager.svg")
        self.gema_add_submenu(self.qfield_menu, icon)

        # Package for QField menu action
        packager_icon = QIcon(os.path.dirname(__file__) + "/icons/packager.svg")
        self.package_qfield_action = QAction(packager_icon, "Package for QField", self.iface.mainWindow())
        self.package_qfield_action.triggered.connect(self.show_package_dialog)
        self.package_qfield_action.setShortcut("Ctrl+Alt+Q")
        self.qfield_menu.addAction(self.package_qfield_action)

        create_ea_icon = QIcon(os.path.dirname(__file__) + "/icons/create_ea.png")
        self.create_ea_action = QAction(create_ea_icon, "Create Enumeration Areas", self.iface.mainWindow())
        self.create_ea_action.triggered.connect(self.show_create_ea_dialog)
        self.qfield_menu.addAction(self.create_ea_action)

        # QField toolbar icon
        self.toolbar = self.iface.addToolBar("Gemma Toolbar")
        self.toolbar.setObjectName("Gemma Toolbar")
        self.package_qfield_toolbar_action = QAction(
            packager_icon, "Package for QField", self.iface.mainWindow()
        )
        self.package_qfield_toolbar_action.triggered.connect(self.show_package_dialog)
        self.toolbar.addAction(self.package_qfield_toolbar_action)

        self.create_ea_toolbar_action = QAction(
            create_ea_icon, "Create Enumeration Areas", self.iface.mainWindow()
        )
        self.create_ea_toolbar_action.triggered.connect(self.show_create_ea_dialog)
        self.toolbar.addAction(self.create_ea_toolbar_action)

        # Initialize offline editing for QField packaging
        self.offline_editing = QgsOfflineEditing()


    def unload(self):
        self.iface.mainWindow().menuBar().removeAction(self.gema_menu.menuAction())

        if self.toolbar:
            del self.toolbar
            self.toolbar = None

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

        if self.ea_provider:
            try:
                QgsApplication.processingRegistry().removeProvider(self.ea_provider)
            except Exception as e:
                QgsApplication.instance().messageLog().logMessage(
                    f"Error removing EA Delineation provider: {e}",
                    'GMD')
            finally:
                del self.ea_provider
                self.ea_provider = None

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

    def show_package_dialog(self):
        """
        Package to QField
        """
        from .gmd_scripts.package_qfield import show_package_dialog
        
        # --- COMMENTED OUT PASSWORD FEATURE ---
        #import hashlib
        #from qgis.PyQt.QtWidgets import QInputDialog, QLineEdit, QMessageBox
        
        #SUPERVISOR_PASSWORD = "bf315bbc2404a161fafeb42995c6197ca17d689b33e7082bfbf2aae386ab755b"
        
        #password, ok = QInputDialog.getText(
        #    self.iface.mainWindow(), 
        #    "Supervisor Access Required", 
        #    "Please enter the supervisor password to access Package for QField:", 
        #    QLineEdit.Password
        #)
        
        #if ok and hashlib.sha256(password.encode()).hexdigest() == SUPERVISOR_PASSWORD:
        #    self.push_dlg = show_package_dialog(
        #        self.iface, 
        #        self.offline_editing, 
        #        self.push_dialog_finished
        #    )
        #elif ok:
        #    QMessageBox.warning(self.iface.mainWindow(), "Access Denied", "Incorrect password.")
        #--------------------------------------

        # Directly open the dialog (original behavior)
        self.push_dlg = show_package_dialog(
            self.iface, 
            self.offline_editing, 
            self.push_dialog_finished
        )
    def show_create_ea_dialog(self):
        """Open the Create Enumeration Areas dialog."""
        from .gmd_scripts.create_enumeration_area import show_create_ea_dialog

        self.ea_dlg = show_create_ea_dialog(self.iface)

    def push_dialog_finished(self):
        """
        When the push dialog is closed, make sure it's no longer
        enabled before cleanup.
        """
        try:
            self.push_dlg.setEnabled(False)
        except RuntimeError:
            pass