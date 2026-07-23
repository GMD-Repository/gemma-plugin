"""
QGIS plugin repository XML builder for the GEMMA release pipeline.

Generates the XML files (gemma.xml, gemma-beta.xml) that QGIS Plugin Manager
reads to discover and install the plugin.
"""

from __future__ import annotations

import logging
from xml.sax.saxutils import escape as xml_escape_impl

logger = logging.getLogger(__name__)

# Base URL for GitHub Pages
BASE_URL = "https://gmd-repository.github.io/gemma-plugin"

# XML template for a QGIS plugin repository entry
PLUGIN_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href=""?>
<plugins>
  <pyqgis_plugin name="{name}" version="{version}">
    <version>{version}</version>
    <description>{description}</description>
    <about>{about}</about>
    <author>{author}</author>
    <author_name>{author}</author_name>
    <qgis_minimum_version>{qgis_minimum_version}</qgis_minimum_version>
    <homepage>{homepage}</homepage>
    <download_url>{download_url}</download_url>
    <icon>{icon}</icon>
    <file_name>gemma-plugin.zip</file_name>
    <upload_date>{date}</upload_date>
    <update_date>{date}</update_date>
    <experimental>{experimental}</experimental>
    <deprecated>{deprecated}</deprecated>
    <tracker>{tracker}</tracker>
    <repository>{repository}</repository>
    <tags>{tags}</tags>
    <category>{category}</category>
    <server>{server}</server>
  </pyqgis_plugin>
</plugins>"""


def xml_escape(text: str) -> str:
    """Escape special XML characters in text content."""
    return xml_escape_impl(text, entities={
        "'": "&apos;",
        '"': "&quot;",
    })


def build_plugin_xml(
    metadata: dict[str, str],
    version: str,
    download_url: str,
    date: str,
    is_beta: bool = False,
    owner: str = "GMD-Repository",
    repo: str = "gemma-plugin",
) -> str:
    """Build a QGIS plugin repository XML string.

    Args:
        metadata: Parsed metadata.txt fields.
        version: Plugin version string (e.g. "v1.5.0" or "v1.5.0-r160").
        download_url: Full URL to the plugin ZIP file.
        date: ISO date string (e.g. "2026-07-22").
        is_beta: If True, marks as experimental and appends (Beta) to name/description.
        owner: GitHub org/user.
        repo: GitHub repository name.

    Returns:
        Complete XML string for the plugin repository.
    """
    # Ensure version has 'v' prefix
    version_str = version if version.startswith("v") else f"v{version}"

    name = metadata.get("name", "GEMMA")
    description = metadata.get("description", "GIS Extension for Map Management and Analysis")
    about = metadata.get("about", "")
    tags = metadata.get("tags", "")

    if is_beta:
        name = f"{name} (Beta)"
        description = f"{description} (Beta)"
        about = f"{about} (Beta Channel)"
        tags = f"{tags},beta" if tags else "beta"

    return PLUGIN_XML_TEMPLATE.format(
        name=xml_escape(name),
        version=xml_escape(version_str),
        description=xml_escape(description),
        about=xml_escape(about),
        author=xml_escape(metadata.get("author", "Geospatial Management Division")),
        qgis_minimum_version=xml_escape(metadata.get("qgisMinimumVersion", "3.0")),
        homepage=f"{BASE_URL}/",
        download_url=download_url,
        icon=f"{BASE_URL}/icons/icon.png",
        date=date,
        experimental="True" if is_beta else "False",
        deprecated=metadata.get("deprecated", "False"),
        tracker=f"https://github.com/{owner}/{repo}/issues",
        repository=f"https://github.com/{owner}/{repo}",
        tags=xml_escape(tags),
        category=xml_escape(metadata.get("category", "Processing Provider")),
        server=metadata.get("server", "False"),
    )
