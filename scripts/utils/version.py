"""
SemVer parsing, bumping, and tag utilities for the GEMMA release pipeline.
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse a version string into (major, minor, patch).

    Strips leading 'v' and any pre-release suffix before parsing.

    Raises:
        ValueError: If the version string is not valid semver.
    """
    cleaned = version.lstrip("v").strip()
    match = SEMVER_PATTERN.match(cleaned)
    if not match:
        raise ValueError(f"Invalid semver string: {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(version: str, bump_type: str) -> str:
    """Bump a version string by the given type.

    Args:
        version: Current version (e.g. "1.2.3" or "1.2.3-beta1").
        bump_type: One of "major", "minor", "patch".

    Returns:
        Bumped version string without pre-release suffix.
    """
    major, minor, patch = parse_semver(version)

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump_type: {bump_type!r}. Must be major, minor, or patch.")

    result = f"{major}.{minor}.{patch}"
    logger.info("Bumped version (%s): %s -> %s", bump_type, version, result)
    return result


def strip_prerelease(version: str) -> str:
    """Remove pre-release suffix from a version string.

    Examples:
        "1.2.3-beta1" -> "1.2.3"
        "1.2.3" -> "1.2.3"
    """
    cleaned = version.lstrip("v").strip()
    match = SEMVER_PATTERN.match(cleaned)
    if not match:
        return cleaned
    return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"


def has_prerelease(version: str) -> bool:
    """Check if a version string has a pre-release suffix."""
    cleaned = version.lstrip("v").strip()
    match = SEMVER_PATTERN.match(cleaned)
    if not match:
        return False
    return bool(match.group(4))


def make_tag(version: str) -> str:
    """Convert a version string to a git tag.

    Examples:
        "1.5.0" -> "v1.5.0"
        "v1.5.0" -> "v1.5.0"
    """
    v = version.strip()
    if v.startswith("v"):
        return v
    return f"v{v}"


def compare_versions(a: str, b: str) -> int:
    """Compare two semver strings numerically.

    Returns:
        -1 if a < b, 0 if a == b, 1 if a > b.
    """
    a_parts = parse_semver(a)
    b_parts = parse_semver(b)
    if a_parts < b_parts:
        return -1
    elif a_parts > b_parts:
        return 1
    return 0
