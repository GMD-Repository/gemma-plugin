#!/usr/bin/env python3
"""
Update VitePress config with the latest version number.

This ensures the navbar version badge in docs/.vitepress/config.mts
stays in sync with metadata.txt during releases.
"""

import re
from pathlib import Path


def update_vitepress_version(version: str) -> None:
    """
    Update the version number in docs/.vitepress/config.mts navbar.

    Targets the navbar version dropdown, matching patterns like:
        text: 'v1.0.0',
        text: "v2.1.3",

    The match is anchored by requiring ``items:`` to follow the version
    text on a subsequent line, so sidebar/nav entries like
    ``{ text: 'Home', link: '/' }`` are never touched.

    Args:
        version: Version string (e.g., '1.0.2')

    Raises:
        FileNotFoundError: If config.mts doesn't exist
        ValueError: If version pattern not found in config
    """
    config_file = Path("docs/.vitepress/config.mts")

    if not config_file.exists():
        raise FileNotFoundError(f"VitePress config not found: {config_file}")

    content = config_file.read_text(encoding="utf-8")
    original_content = content

    # ── Early exit: version already matches ───────────────────────────
    # When re-releasing the same version (e.g. custom override of v1.0.0
    # when config already has v1.0.0), the substitution produces identical
    # content and was previously misreported as "pattern not found".
    if re.search(rf"""text:\s*['"]v{re.escape(version)}['"]""", content):
        print(f"✅ VitePress navbar already at v{version} — no update needed")
        return

    # ── Primary pattern (anchored to the version dropdown) ────────────
    # Matches:  text: 'vX.X.X',\n ... items: [
    # The lookahead ensures we only touch the navbar version badge,
    # not other { text: '...', items: [...] } groups like 'Tools'.
    # re.DOTALL lets '.' match newlines inside the lookahead.
    pattern = r"""(text:\s*)'v[\d.]+'(\s*,\s*\n\s*items:\s*\[)"""
    replacement = rf"\g<1>'v{version}'\2"
    updated_content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)

    if updated_content != original_content:
        config_file.write_text(updated_content, encoding="utf-8")
        print(f"✅ Updated VitePress navbar version to: v{version}")
        return

    # ── Fallback: broader pattern without lookahead ───────────────────
    # Handles cases where whitespace or formatting differs slightly.
    fallback = r"""(text:\s*)['"]v[\d.]+['"]"""
    updated_content = re.sub(fallback, rf"\g<1>'v{version}'", content, count=1)

    if updated_content != original_content:
        config_file.write_text(updated_content, encoding="utf-8")
        print(f"✅ Updated VitePress navbar version to: v{version} (fallback pattern)")
        return

    # ── Diagnostic info for debugging ─────────────────────────────────
    # Print lines containing 'text:' and a version-like string to help
    # identify why neither pattern matched.
    diag_lines = [
        f"  L{i + 1}: {line.rstrip()}"
        for i, line in enumerate(content.splitlines())
        if re.search(r"text:\s*['\"]v", line, re.IGNORECASE)
    ]
    diag = "\n".join(diag_lines) if diag_lines else "  (no lines matched 'text: vX.X.X')"

    raise ValueError(
        f"Could not find version pattern in {config_file}.\n"
        f"Expected a line like: text: 'vX.X.X',\n"
        f"Diagnostic — lines containing version-like text entries:\n{diag}"
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python update_vitepress_config.py <version>")
        sys.exit(1)

    version = sys.argv[1]
    update_vitepress_version(version)
