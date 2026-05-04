from __future__ import annotations

from halo_bridge.models import Article


def append_copyright(content: str, template: str, article: Article) -> str:
    """Append a copyright declaration block at the end of the content.

    The template supports these placeholders:
    - {title}: article title
    - {slug}: article slug
    - {permalink}: full permalink URL
    """
    if not template:
        return content

    # Build full permalink URL
    base_url = article.permalink
    if base_url and not base_url.startswith("http"):
        # permalink from Halo is relative like /archives/slug
        # We don't have the base_url here, so use it as-is
        # The caller should have already set it as full URL
        pass

    rendered = template.format(
        title=article.title,
        slug=article.slug,
        permalink=article.permalink,
    )

    return f"{content}\n\n{rendered}"
