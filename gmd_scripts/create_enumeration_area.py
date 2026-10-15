from qgis.PyQt.QtCore import Qt

def show_create_ea_dialog(iface, on_finished_callback=None):
    try:
        from ..references.create_enumeration_area.dialog import EALauncherDialog
    except (ImportError, ValueError):
        from references.create_enumeration_area.dialog import EALauncherDialog

    dlg = EALauncherDialog(iface.mainWindow() if iface else None)
    dlg.setWindowFlags(
        Qt.Window |
        Qt.WindowTitleHint |
        Qt.WindowMinimizeButtonHint |
        Qt.WindowMaximizeButtonHint |
        Qt.WindowCloseButtonHint
    )

    dlg.show()

    if on_finished_callback:
        dlg.finished.connect(on_finished_callback)

    return dlg
