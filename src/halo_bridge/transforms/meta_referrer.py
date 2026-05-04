from __future__ import annotations

META_TAG = '<meta name="referrer" content="no-referrer" />'


def add_meta_referrer(content: str) -> str:
    """Prepend a meta referrer tag to prevent image hotlink blocking.

    In markdown, raw HTML is valid, so we prepend the tag at the very top.
    """
    return f"{META_TAG}\n\n{content}"


def remove_meta_referrer(content: str) -> str:
    """Remove the meta referrer tag if present.

    Useful when content will be posted to platforms that use CSDN image hosting
    (CSDN images require Referer header to load).
    """
    return content.replace(f"{META_TAG}\n\n", "").replace(f"{META_TAG}\n", "")
