__author__ = 'Geospatial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geospatial Management Division'


import os
import sys
import inspect
import pathlib
import shutil
import datetime
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

# Legacy plugin folder names whose functionality has been merged into GEMMA.
# If these folders are found in the plugins directory they will be automatically
# moved to a quarantine folder so they no longer conflict with GEMMA.
_LEGACY_PLUGINS = {
    'gmd_pipeline': 'GMD Pipeline',
    'qfieldmod':    'QFieldMod',
}


class GMDPipeline(object):

    def __init__(self, iface):
        self.iface = iface
        self.gema_menu = None
        self.updating_boundaries_menu = None
        self.ea_delineation_menu = None
        self.others_menu = None
        self.provider = None
        self.toolbar = None
        self.geometry_toolkit_dlg = None
        self.check_update_dlg = None
        self.push_dlg = None
        self.check_and_update_action = None
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


    def _quarantine_legacy_plugins(self):
        """
        Detect old plugin folders that conflict with GEMMA and move them into
        <gemma-plugin>/_legacy_trash/<timestamp>/<folder>/ so QGIS no longer
        loads them after the next restart.

        Returns a list of display names that were moved, or an empty list if
        nothing needed to be done.
        """
        plugins_dir  = pathlib.Path(__file__).parent.parent   # .../plugins/
        gemma_dir    = pathlib.Path(__file__).parent           # .../gemma-plugin/
        trash_root   = gemma_dir / '_legacy_trash'
        timestamp    = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        trash_target = trash_root / timestamp

        moved = []
        for folder_name, display_name in _LEGACY_PLUGINS.items():
            src = plugins_dir / folder_name
            if src.is_dir():
                trash_target.mkdir(parents=True, exist_ok=True)
                dst = trash_target / folder_name
                try:
                    shutil.move(str(src), str(dst))
                    moved.append(display_name)
                    QgsMessageLog.logMessage(
                        f'GEMMA: moved legacy plugin "{folder_name}" '
                        f'to {dst}',
                        'GEMMA',
                        level=1,  # Qgis.Warning
                    )
                except Exception as exc:
                    QgsMessageLog.logMessage(
                        f'GEMMA: could not move legacy plugin "{folder_name}": {exc}',
                        'GEMMA',
                        level=2,  # Qgis.Critical
                    )
        return moved

    def initGui(self):
        # ── Quarantine legacy plugins ────────────────────────────────────────
        moved = self._quarantine_legacy_plugins()
        if moved:
            names = ', '.join(moved)
            QMessageBox.information(
                self.iface.mainWindow(),
                'GEMMA — Legacy Plugins Removed',
                f'The following old plugin(s) have been automatically moved '
                f'to the trash folder inside GEMMA and will no longer load:\n\n'
                f'  • {chr(10).join(moved)}\n\n'
                f'Their functionality is already built into GEMMA.\n'
                f'Please restart QGIS to complete the cleanup.',
            )
            return  # Let user restart; avoid loading alongside half-unloaded providers
        # ────────────────────────────────────────────────────────────────────

        self.initProcessing()

        self.gema_menu = QMenu("Gemma")
        self.iface.mainWindow().menuBar().insertMenu(self.iface.firstRightStandardMenu().menuAction(), self.gema_menu)

        packager_icon = QIcon(os.path.dirname(__file__) + "/icons/packager.svg")
        create_ea_icon = QIcon(os.path.dirname(__file__) + "/icons/create_ea.svg")
        sync_mbi_icon = QIcon(os.path.dirname(__file__) + "/icons/sync_mbi.svg")
        geom_toolkit_icon = QIcon(os.path.dirname(__file__) + "/icons/repair_geom.svg")
        others_icon = QIcon(os.path.dirname(__file__) + "/icons/others.svg")
        updating_boundaries_icon = QIcon(os.path.dirname(__file__) + "/icons/updating_boundaries.svg")
        check_and_update_icon = QIcon(os.path.dirname(__file__) + "/icons/check_and_update.svg")

        # 1. Updating of Boundaries Submenu
        self.updating_boundaries_menu = QMenu(u'Updating of Boundaries')
        self.gema_add_submenu(self.updating_boundaries_menu, updating_boundaries_icon)

        self.check_and_update_action = QAction(check_and_update_icon, "Check and Update", self.iface.mainWindow())
        self.check_and_update_action.triggered.connect(self.show_check_and_update_dialog)
        self.updating_boundaries_menu.addAction(self.check_and_update_action)

        # 2. EA Delineation Submenu
        self.ea_delineation_menu = QMenu(u'EA Delineation')
        self.gema_add_submenu(self.ea_delineation_menu, create_ea_icon)

        self.create_ea_action = QAction(create_ea_icon, "Create Enumeration Areas", self.iface.mainWindow())
        self.create_ea_action.triggered.connect(self.show_create_ea_dialog)
        self.ea_delineation_menu.addAction(self.create_ea_action)

        # 3. Others Submenu
        self.others_menu = QMenu(u'Others')
        self.gema_add_submenu(self.others_menu, others_icon)

        self.sync_report = QAction(sync_mbi_icon, "Sync MBI Layer", self.iface.mainWindow())
        self.sync_report.triggered.connect(self.sync_report_act)
        self.others_menu.addAction(self.sync_report)

        self.package_qfield_action = QAction(packager_icon, "Package for QField", self.iface.mainWindow())
        self.package_qfield_action.triggered.connect(self.show_package_dialog)
        self.package_qfield_action.setShortcut("Ctrl+Alt+Q")
        self.others_menu.addAction(self.package_qfield_action)

        self.geometry_toolkit_action = QAction(geom_toolkit_icon, "Geometry Repair Toolkit", self.iface.mainWindow())
        self.geometry_toolkit_action.triggered.connect(self.show_geometry_toolkit)
        self.others_menu.addAction(self.geometry_toolkit_action)

        # Gemma Toolbar
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

    def show_check_and_update_dialog(self):
        """Open the Check and Update boundary management dialog."""
        from .gmd_scripts.check_and_update_dialog import CheckAndUpdateDialog

        if self.check_update_dlg is None:
            self.check_update_dlg = CheckAndUpdateDialog(self.iface)

        self.check_update_dlg.show()
        self.check_update_dlg.raise_()
        self.check_update_dlg.activateWindow()

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