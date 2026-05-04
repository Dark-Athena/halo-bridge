from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from halo_bridge.exceptions import HaloAPIError
from halo_bridge.models import Article, HaloConfig

logger = logging.getLogger(__name__)


class HaloSource:
    """Client for fetching articles from a Halo 2.x blog."""

    def __init__(self, config: HaloConfig) -> None:
        self.base_url = config.base_url
        self.client = httpx.Client(
            base_url=config.base_url,
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=30,
            follow_redirects=True,
        )

    def fetch_article(self, slug: str) -> Article:
        """Fetch a published article by its slug.

        Steps:
        1. Find post metadata by slug via fieldSelector
        2. Get released content
        3. Combine into Article dataclass
        """
        # Step 1: Find post by slug
        post = self._find_post_by_slug(slug)

        name = post["metadata"]["name"]
        spec = post["spec"]
        status = post.get("status", {})

        # Step 2: Get released content
        content = self._get_released_content(name)

        # Step 3: Build permalink
        permalink = status.get("permalink", f"/archives/{spec.get('slug', slug)}")
        if not permalink.startswith("http"):
            permalink = f"{self.base_url}{permalink}"

        # Step 4: Extract categories and tags
        categories = self._resolve_names(spec.get("categories", []), "categories")
        tags = self._resolve_names(spec.get("tags", []), "tags")

        return Article(
            title=spec.get("title", ""),
            slug=spec.get("slug", slug),
            raw_markdown=content.get("raw", ""),
            html_content=content.get("content", ""),
            permalink=permalink,
            categories=categories,
            tags=tags,
            excerpt=spec.get("excerpt", {}).get("raw", ""),
            cover_image=spec.get("cover", ""),
        )

    def _find_post_by_slug(self, slug: str) -> dict:
        """Find a post by its slug using fieldSelector."""
        resp = self.client.get(
            "/apis/api.console.halo.run/v1alpha1/posts",
            params={"fieldSelector": f"spec.slug={slug}"},
        )
        if resp.status_code != 200:
            raise HaloAPIError(
                f"Failed to list posts: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()
        items = data.get("items", [])
        if not items:
            raise HaloAPIError(f"Article with slug '{slug}' not found on {self.base_url}")

        # Console API wraps post under 'post' key
        item = items[0]
        return item.get("post", item)

    def _get_released_content(self, post_name: str) -> dict:
        """Get the released content of a post.

        Uses the console API head-content endpoint which works with PAT auth.
        The public released-content endpoint returns 403 for PATs.
        """
        resp = self.client.get(
            f"/apis/api.console.halo.run/v1alpha1/posts/{post_name}/head-content",
        )
        if resp.status_code != 200:
            raise HaloAPIError(
                f"Failed to get content for post '{post_name}': "
                f"{resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()
        return {
            "raw": data.get("raw", ""),
            "content": data.get("content", ""),
            "rawType": data.get("rawType", "markdown"),
        }

    def _resolve_names(self, refs: list[str], resource_type: str) -> list[str]:
        """Resolve category/tag references to display names."""
        if not refs:
            return []
        names = []
        for ref in refs:
            try:
                resp = self.client.get(
                    f"/apis/content.halo.run/v1alpha1/{resource_type}/{ref}"
                )
                if resp.status_code == 200:
                    display = resp.json().get("spec", {}).get("displayName", ref)
                    names.append(display)
                else:
                    names.append(ref)
            except Exception:
                names.append(ref)
        return names

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def parse_slug(input_str: str, base_url: str) -> str:
    """Extract slug from a URL or return bare slug.

    Accepts:
    - Full URL: https://www.darkathena.top/archives/my-article → my-article
    - Bare slug: my-article → my-article
    """
    if "/" in input_str:
        parsed = urlparse(input_str)
        path = parsed.path.rstrip("/")
        # Extract last segment
        parts = path.split("/")
        if parts:
            slug = parts[-1]
            if slug:
                return slug

    return input_str
