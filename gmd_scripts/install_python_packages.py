__author__ = 'Geosptial Management Division'
__date__ = '2025-12-5'
__copyright__ = '(C) 2025, Geosptial Management Division'

import subprocess
import pip
import importlib
from .gmd_scripts import gmdhelpers

required_packages = ["gspread",
                     "google-oauth",
                     "geopandas",
                     "shapely"]

for i in required_packages:
    install_package(i)