from __future__ import annotations

import re

# Match markdown image syntax with relative (non-absolute) URLs
# Handles: ![alt](/path), ![alt](path), ![alt](./path)
# Skips: ![alt](http://...), ![alt](https://...)
_MD_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\((?!https?://)(/?.*?)\)"
)


def fix_image_urls(content: str, base_url: str) -> tuple[str, int]:
    """Prepend base_url to relative image URLs in markdown content.

    Returns (transformed_content, count_of_replacements).
    """
    count = 0

    def _replace(m: re.Match) -> str:
        nonlocal count
        alt = m.group(1)
        path = m.group(2)
        # Normalize: ensure path starts with /
        if not path.startswith("/"):
            path = "/" + path
        count += 1
        return f"![{alt}]({base_url}{path})"

    result = _MD_IMAGE_RE.sub(_replace, content)
    return result, count
