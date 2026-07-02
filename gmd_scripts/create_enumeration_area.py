from qgis.PyQt.QtCore import Qt

def show_create_ea_dialog(iface, on_finished_callback=None):
    from ..references.create_enumeration_area.dialog import EALauncherDialog

    dlg = EALauncherDialog(iface.mainWindow())
    dlg.setAttribute(Qt.WA_DeleteOnClose)
    dlg.setWindowFlags(Qt.Dialog)

    dlg.show()

    if on_finished_callback:
        dlg.finished.connect(on_finished_callback)

    return dlg
