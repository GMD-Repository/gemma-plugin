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
    
    Changes: { text: 'v1.0.1', items: [...] }
    To:      { text: 'v{version}', items: [...] }
    
    Args:
        version: Version string (e.g., '1.0.2')
    
    Raises:
        FileNotFoundError: If config.mts doesn't exist
        ValueError: If version pattern not found in config
    """
    config_file = Path("docs/.vitepress/config.mts")
    
    if not config_file.exists():
        raise FileNotFoundError(f"VitePress config not found: {config_file}")
    
    content = config_file.read_text(encoding='utf-8')
    original_content = content
    
    # Pattern to match: { text: 'vX.X.X', items: [
    # We need to be careful to only replace the navbar version badge
    pattern = r"(\{\s*text:\s*)'v[\d\.]+'"
    replacement = rf"\1'v{version}'"
    
    updated_content = re.sub(pattern, replacement, content)
    
    if updated_content == original_content:
        raise ValueError(
            f"Could not find version pattern in {config_file}. "
            "Expected: {{ text: 'vX.X.X', items: ["
        )
    
    config_file.write_text(updated_content, encoding='utf-8')
    print(f"✅ Updated VitePress navbar version to: v{version}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python update_vitepress_config.py <version>")
        sys.exit(1)
    
    version = sys.argv[1]
    update_vitepress_version(version)
