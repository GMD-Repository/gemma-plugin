"""
dependency_checker.py
---------------------
Automatically ensures that required QGIS plugin dependencies are installed
and up-to-date every time GEMMA loads.

Usage (from gmd_pipeline.py → initGui):
    from .dependency_checker import ensure_plugin_dependencies
    ensure_plugin_dependencies()

To add a new dependency, append a dict to REQUIRED_PLUGINS:
    {
        'key':          '<plugin folder name>',
        'display_name': '<human-readable name>',
        'min_version':  '<minimum version>',   # optional
    }
"""

from qgis.core import Qgis, QgsMessageLog

# ---------------------------------------------------------------------------
# Registry of required plugins.
# Each entry is a dict with:
#   key          – the plugin folder name / pyplugin_installer key
#   display_name – a human-readable label used in log messages
#   min_version  – (optional) minimum required version string, e.g. '1.2.0'.
#                  If set, only updates when installed version < min_version.
#                  If omitted, always updates to the latest available version.
# ---------------------------------------------------------------------------
REQUIRED_PLUGINS = [
    {
        'key': 'HCMGIS',
        'display_name': 'HCMGIS',
        #'min_version': '24.1.12',
    },
    {
        'key': 'SpreadsheetLayers',
        'display_name': 'Spreadsheet Layers',
        #'min_version': '2.1.2',
    },
    # Add more entries here as needed.
]

_LOG_TAG = 'GEMMA'


# ---------------------------------------------------------------------------
# Version comparison helper
# ---------------------------------------------------------------------------
def _parse_version_tuple(version_string):
    """Convert a version string like '1.2.3' into a tuple of ints for
    reliable comparison.  Non-numeric segments are replaced with 0."""
    parts = []
    for segment in version_string.strip().split('.'):
        try:
            parts.append(int(segment))
        except (ValueError, TypeError):
            parts.append(0)
    return tuple(parts)


def _is_outdated(installed_version, available_version):
    """Return True when *available_version* is strictly newer than
    *installed_version*."""
    if not installed_version or not available_version:
        return False
    return _parse_version_tuple(installed_version) < _parse_version_tuple(available_version)


def _below_minimum(installed_version, min_version):
    """Return True when *installed_version* is strictly below
    the required *min_version*."""
    if not installed_version or not min_version:
        return False
    return _parse_version_tuple(installed_version) < _parse_version_tuple(min_version)


def _read_installed_version(plugin_key):
    """Read the version from a locally installed plugin's metadata.txt.

    Returns the version string, or '' if the plugin is not installed or
    its metadata cannot be read.
    """
    import pathlib
    import configparser

    plugins_dir = pathlib.Path(__file__).parent.parent  # .../plugins/
    metadata_path = plugins_dir / plugin_key / 'metadata.txt'

    if not metadata_path.is_file():
        return ''

    try:
        config = configparser.ConfigParser()
        config.read(str(metadata_path), encoding='utf-8')
        return config.get('general', 'version', fallback='')
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def ensure_plugin_dependencies():
    """Check every entry in REQUIRED_PLUGINS.

    * Missing plugins are installed silently.
    * Plugins below the required min_version are uninstalled and reinstalled.
    * When no min_version is set, outdated plugins are updated to the latest.
    * Already-current plugins are skipped with an info log.

    Returns a dict with two lists:
        {'installed': [...], 'updated': [...]}
    Each list contains the display_name strings of affected plugins.
    """
    results = {'installed': [], 'updated': []}

    # ------------------------------------------------------------------
    # 1. Import pyplugin_installer (ships with QGIS, but guard anyway)
    # ------------------------------------------------------------------
    try:
        import pyplugin_installer
        from pyplugin_installer import installer_data
    except ImportError:
        QgsMessageLog.logMessage(
            'pyplugin_installer is not available — '
            'cannot verify plugin dependencies.',
            _LOG_TAG,
            level=Qgis.Warning,
        )
        return results

    # ------------------------------------------------------------------
    # 2. Fetch the latest repository index
    # ------------------------------------------------------------------
    try:
        pyplugin_installer.instance().fetchAvailablePlugins(False)
    except Exception as exc:
        QgsMessageLog.logMessage(
            f'Failed to fetch available plugins from repository: {exc}',
            _LOG_TAG,
            level=Qgis.Warning,
        )
        return results

    # ------------------------------------------------------------------
    # 3. Walk each required dependency
    # ------------------------------------------------------------------
    all_plugins = installer_data.plugins.all()

    for dep in REQUIRED_PLUGINS:
        key = dep['key']
        name = dep['display_name']
        min_version = dep.get('min_version')  # Now acts as exact preferred version if set

        # Read installed version directly from disk (reliable)
        installed_version = _read_installed_version(key)

        # Get available version from the repository index
        plugin_meta = all_plugins.get(key, {})
        available_version = plugin_meta.get('version_available', '')

        QgsMessageLog.logMessage(
            f'Checking "{name}": installed={installed_version or "(none)"}, '
            f'available={available_version or "(unknown)"}, '
            f'required_version={min_version or "(latest)"}',
            _LOG_TAG,
            level=Qgis.Info,
        )

        needs_install = False
        needs_update = False
        reason = ''
        zip_path = None

        if min_version:
            import pathlib
            # We expect the zip file to be in references/plugin_dependencies/
            gemma_dir = pathlib.Path(__file__).parent
            zip_path = gemma_dir / 'references' / 'plugin_dependencies' / f'{key}-{min_version}.zip'

            if not installed_version:
                needs_install = True
                reason = f'missing, will install from zip'
            elif installed_version != min_version:
                needs_update = True
                reason = f'installed {installed_version} does not match required {min_version}'
        else:
            # No specific version pinned — rely on repository
            if not installed_version:
                if not available_version:
                    QgsMessageLog.logMessage(
                        f'Dependency "{name}" (key={key}) is not installed and '
                        'not found in any configured plugin repository — skipping.',
                        _LOG_TAG,
                        level=Qgis.Warning,
                    )
                    continue
                needs_install = True
                reason = f'missing, will install latest'
            elif _is_outdated(installed_version, available_version):
                needs_update = True
                reason = f'{installed_version} -> {available_version}'

        if not needs_install and not needs_update:
            QgsMessageLog.logMessage(
                f'Dependency "{name}" is up-to-date '
                f'(version {installed_version}).',
                _LOG_TAG,
                level=Qgis.Info,
            )
        else:
            # Handle Installation or Update
            try:
                if needs_update:
                    try:
                        QgsMessageLog.logMessage(
                            f'Uninstalling "{name}" ({installed_version}) '
                            f'before reinstalling ({reason}) ...',
                            _LOG_TAG,
                            level=Qgis.Info,
                        )
                        
                        # Silently uninstall to bypass GUI prompt
                        import qgis.utils
                        import shutil
                        import pathlib

                        if qgis.utils.isPluginLoaded(key):
                            qgis.utils.unloadPlugin(key)
                        
                        plugins_dir = pathlib.Path(__file__).parent.parent
                        plugin_dir = plugins_dir / key
                        if plugin_dir.exists() and plugin_dir.is_dir():
                            shutil.rmtree(plugin_dir)

                        action_word = "reinstalled"
                        results_key = "updated"
                    except Exception as exc:
                        QgsMessageLog.logMessage(
                            f'Failed to uninstall "{name}" for update: {exc}',
                            _LOG_TAG,
                            level=Qgis.Critical,
                        )
                        # Cannot proceed if uninstall failed
                        continue
                else:
                    QgsMessageLog.logMessage(
                        f'Installing "{name}" ({reason}) ...',
                        _LOG_TAG,
                        level=Qgis.Info,
                    )
                    action_word = "installed"
                    results_key = "installed"

                # If zip_path is not defined (no min_version), try to find ANY zip for this plugin
                if not zip_path or not zip_path.is_file():
                    if deps_dir.is_dir():
                        matching_zips = list(deps_dir.glob(f'{key}-*.zip'))
                        if matching_zips:
                            # Use the latest/first found zip
                            zip_path = matching_zips[-1]

                # Perform the installation
                if zip_path and zip_path.is_file():
                    QgsMessageLog.logMessage(
                        f'Extracting from local ZIP: {zip_path.name}',
                        _LOG_TAG,
                        level=Qgis.Info,
                    )
                    import zipfile
                    import pathlib
                    plugins_dir = pathlib.Path(__file__).parent.parent
                    with zipfile.ZipFile(str(zip_path), 'r') as zip_ref:
                        zip_ref.extractall(str(plugins_dir))
                else:
                    QgsMessageLog.logMessage(
                        f'No local ZIP found, fetching from QGIS plugin repository...',
                        _LOG_TAG,
                        level=Qgis.Info,
                    )
                    pyplugin_installer.instance().installPlugin(key)
                
                results[results_key].append(name)
                QgsMessageLog.logMessage(
                    f'Successfully {action_word} "{name}".',
                    _LOG_TAG,
                    level=Qgis.Info,
                )
            except Exception as exc:
                QgsMessageLog.logMessage(
                    f'Failed to install/update "{name}" (If it is a core plugin, this is expected): {exc}',
                    _LOG_TAG,
                    level=Qgis.Warning,
                )
                # DO NOT continue here. We still want to try to enable it below 
                # in case it is a core plugin (like Topology Checker) that is already installed.
            
        # ------ Ensure plugin is enabled in QGIS ------
        try:
            from qgis.core import QgsSettings
            import qgis.utils
            
            settings = QgsSettings()
            
            # 1. Ensure the checkbox is checked in the Plugin Manager
            # We set both the Python path and the Core C++ path just in case
            python_key = f"PythonPlugins/{key}"
            core_key = f"Plugins/{key}"
            
            settings.setValue(python_key, True)
            settings.setValue(core_key, True)
            settings.sync() # Flush to registry/ini immediately
            
            QgsMessageLog.logMessage(
                f'Checked (enabled) "{name}" in QGIS settings.',
                _LOG_TAG,
                level=Qgis.Info,
            )
            
            # 2. Ensure it is actively loaded in the current QGIS session
            # (Note: qgis.utils only loads Python plugins. Core C++ plugins are loaded by QGIS itself)
            import pathlib
            plugins_dir = pathlib.Path(__file__).parent.parent
            is_python_plugin = (plugins_dir / key).is_dir()

            if is_python_plugin and not qgis.utils.isPluginLoaded(key):
                try:
                    qgis.utils.loadPlugin(key)
                    qgis.utils.startPlugin(key)
                    QgsMessageLog.logMessage(
                        f'Started python plugin "{name}".',
                        _LOG_TAG,
                        level=Qgis.Info,
                    )
                except Exception as exc:
                    QgsMessageLog.logMessage(
                        f'Could not dynamically start "{name}": {exc}',
                        _LOG_TAG,
                        level=Qgis.Warning,
                    )
        except Exception as exc:
            QgsMessageLog.logMessage(
                f'Could not automatically enable "{name}": {exc}',
                _LOG_TAG,
                level=Qgis.Warning,
            )

    return results
