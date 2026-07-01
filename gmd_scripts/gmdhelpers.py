__author__ = 'Geosptial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geosptial Management Division'

import subprocess
import pip
import importlib


def install_package(package_name):
    try:
        importlib.import_module(package_name)
        print(f"✅ Importing '{package_name}' is successful!")
        return True
    except ImportError:
        print(f"⚠️ '{package_name}' not found. Attempting installation...")
        pip.main(["install", package_name])
        try:
            importlib.import_module(package_name)
            print(f"✅ Installation and import of '{package_name}' succeeded!")
            return True
        except ImportError:
            print(f"❌ Installation of '{package_name}' failed. Please install manually.")
            return False


def uninstall_package(package_name):
    pip.main(["uninstall", package_name])


def remove_layer_lengths(layer):
    field_mapping = []
    for f in layer.fields():
        field_mapping.append({
            'expression': f'"{f.name()}"',
            'length': 0,  # no limit
            'name': f.name(),
            'type': f.type()
        })
    return processing.run("native:refactorfields", {
        'INPUT': layer,
        'FIELDS_MAPPING': field_mapping,
        'OUTPUT': 'memory:'
    }, context=context, feedback=feedback)['OUTPUT']


def set_status_bar(self, status_bar):
    status_bar.setMinimum(0)
    status_bar.setMaximum(100)
    status_bar.setValue(0)
    status_bar.setFormat("Ready")
    self.status_bar = status_bar
