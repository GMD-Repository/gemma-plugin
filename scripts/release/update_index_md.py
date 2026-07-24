#!/usr/bin/env python3
"""
Update index.md download link with the latest version.

This ensures the homepage download button in docs/user-guide/index.md
stays in sync with the latest release during version updates.
"""

import re
from pathlib import Path


def update_index_download_link(version: str, owner: str = "GMD-Repository", repo: str = "gemma-plugin") -> None:
    """
    Update the download link in docs/user-guide/index.md with the latest version.
    
    Changes: link: https://github.com/GMD-Repository/gemma-plugin/releases/download/v1.0.1/gemma-plugin-v1.0.1.zip
    To:      link: https://github.com/GMD-Repository/gemma-plugin/releases/download/v{version}/gemma-plugin-v{version}.zip
    
    Args:
        version: Version string (e.g., '1.0.2')
        owner: Repository owner (default: GMD-Repository)
        repo: Repository name (default: gemma-plugin)
    
    Raises:
        FileNotFoundError: If index.md doesn't exist
        ValueError: If download link pattern not found in index.md
    """
    index_file = Path("docs/user-guide/index.md")
    
    if not index_file.exists():
        raise FileNotFoundError(f"index.md not found: {index_file}")
    
    content = index_file.read_text(encoding='utf-8')
    original_content = content
    
    # Pattern to match the download link in YAML format
    # link: https://github.com/GMD-Repository/gemma-plugin/releases/download/vX.X.X/gemma-plugin-vX.X.X.zip
    # Match: link: https://github.com/{owner}/{repo}/releases/download/vX.X.X/gemma-plugin-vX.X.X.zip
    pattern = r'(link: https://github\.com/[^/]+/[^/]+/releases/download/v)[\d\.]+(/gemma-plugin-v)[\d\.]+\.zip'
    replacement = rf'\g<1>{version}\g<2>{version}.zip'
    
    updated_content = re.sub(pattern, replacement, content)
    
    if updated_content == original_content:
        raise ValueError(
            f"Could not find download link pattern in {index_file}. "
            "Expected: link: https://github.com/.../releases/download/vX.X.X/gemma-plugin-vX.X.X.zip"
        )
    
    index_file.write_text(updated_content, encoding='utf-8')
    print(f"✅ Updated index.md download link to version: v{version}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python update_index_md.py <version> [owner] [repo]")
        sys.exit(1)
    
    version = sys.argv[1]
    owner = sys.argv[2] if len(sys.argv) > 2 else "GMD-Repository"
    repo = sys.argv[3] if len(sys.argv) > 3 else "gemma-plugin"
    
    update_index_download_link(version, owner, repo)
