from __future__ import annotations

import re

# Match markdown image syntax with relative (non-absolute) URLs
# Handles: ![alt](/path), ![alt](path), ![alt](./path)
# Skips: ![alt](http://...), ![alt](https://...)
_MD_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\((?!https?://)(/?.*?)\)"
)

# Match HTML img tags with relative src
# Handles: <img src="/path" ...>, <img src="path" ...>
# Skips: <img src="http://..." ...>, <img src="https://..." ...>
_HTML_IMG_RE = re.compile(
    r'(<img\s+[^>]*src=")(?!https?://)(/?.*?)(")',
    re.IGNORECASE,
)


def fix_image_urls(content: str, base_url: str) -> tuple[str, int]:
    """Prepend base_url to relative image URLs in content.

    Handles both markdown ![alt](url) and HTML <img src="url"> syntax.
    Returns (transformed_content, count_of_replacements).
    """
    count = 0

    def _replace_md(m: re.Match) -> str:
        nonlocal count
        alt = m.group(1)
        path = m.group(2)
        if not path.startswith("/"):
            path = "/" + path
        count += 1
        return f"![{alt}]({base_url}{path})"

    def _replace_html(m: re.Match) -> str:
        nonlocal count
        prefix = m.group(1)
        path = m.group(2)
        suffix = m.group(3)
        if not path.startswith("/"):
            path = "/" + path
        count += 1
        return f"{prefix}{base_url}{path}{suffix}"

    result = _MD_IMAGE_RE.sub(_replace_md, content)
    result = _HTML_IMG_RE.sub(_replace_html, result)
    return result, count
