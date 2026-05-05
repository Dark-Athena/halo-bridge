from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from halo_bridge.exceptions import TargetError
from halo_bridge.models import Article, CnblogsConfig, SyncResult
from halo_bridge.targets import PlatformAdapter, register_adapter

logger = logging.getLogger(__name__)


@register_adapter
class CnblogsAdapter(PlatformAdapter):
    """cnblogs (博客园) adapter using REST API."""

    name = "cnblogs"

    API_URL = "https://i.cnblogs.com/api/posts"
    # postType: 1=随笔, 2=文章, 3=日记
    POST_TYPE_ARTICLE = 2

    def __init__(self, config: CnblogsConfig) -> None:
        self.config = config

    def _create_client(self) -> httpx.Client:
        """Create an httpx.Client with cnblogs cookies pre-loaded."""
        return httpx.Client(
            headers={
                "Cookie": self.config.cookie,
                "Content-Type": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/132.0.0.0 Safari/537.36"
                ),
                "Origin": "https://i.cnblogs.com",
                "Referer": "https://i.cnblogs.com/articles/edit",
            },
            follow_redirects=False,
            timeout=30,
        )

    def _refresh_xsrf(self, client: httpx.Client) -> None:
        """GET the edit page to get a fresh XSRF-TOKEN, then set the header."""
        resp = client.get("https://i.cnblogs.com/articles/edit")
        if resp.status_code in (401, 403):
            raise TargetError("cnblogs", "登录已过期，请运行 `halo-bridge login cnblogs` 更新 cookie")
        # Extract fresh XSRF-TOKEN from response cookies
        xsrf = ""
        for cookie in client.cookies.jar:
            if cookie.name == "XSRF-TOKEN":
                xsrf = cookie.value
                break
        if xsrf:
            client.headers["x-xsrf-token"] = xsrf
            logger.debug("Refreshed XSRF-TOKEN: %s...", xsrf[:40])

    def check_auth(self) -> None:
        """Verify cnblogs cookie is valid. Raises TargetError if not."""
        with self._create_client() as client:
            self._refresh_xsrf(client)

    def publish(self, article: Article, content: str | None = None) -> SyncResult:
        """Publish an article to cnblogs."""
        markdown_content = content or article.raw_markdown

        payload = {
            "id": None,
            "postType": self.POST_TYPE_ARTICLE,
            "accessPermission": 0,
            "title": article.title,
            "url": None,
            "postBody": markdown_content,
            "categoryIds": None,
            "categories": None,
            "collectionIds": [],
            "inSiteCandidate": False,
            "inSiteHome": False,
            "siteCategoryId": None,
            "blogTeamIds": None,
            "isPublished": True,
            "displayOnHomePage": True,
            "isAllowComments": True,
            "includeInMainSyndication": False,
            "isPinned": False,
            "showBodyWhenPinned": False,
            "isOnlyForRegisterUser": False,
            "isUpdateDateAdded": False,
            "entryName": None,
            "description": None,
            "featuredImage": None,
            "tags": article.tags if article.tags else None,
            "password": None,
            "publishAt": None,
            "datePublished": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "dateUpdated": None,
            "isMarkdown": True,
            "isDraft": False,
            "autoDesc": None,
            "changePostType": False,
            "blogId": 0,
            "author": None,
            "removeScript": False,
            "clientInfo": None,
            "changeCreatedTime": False,
            "canChangeCreatedTime": False,
            "isContributeToImpressiveBugActivity": False,
            "usingEditorId": 6,
            "sourceUrl": None,
        }

        try:
            with self._create_client() as client:
                self._refresh_xsrf(client)
                resp = client.post(self.API_URL, json=payload)
        except TargetError:
            raise
        except httpx.RequestError as e:
            return SyncResult(target="cnblogs", success=False, error=f"Network error: {e}")

        if resp.status_code not in (200, 201):
            return SyncResult(
                target="cnblogs",
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        data = resp.json()
        post_id = data.get("id", "")
        post_url = data.get("url", "")

        if not post_url and post_id:
            post_url = f"https://www.cnblogs.com/DarkAthena/p/{post_id}.html"

        return SyncResult(
            target="cnblogs",
            success=True,
            post_id=str(post_id),
            post_url=post_url,
        )

    def update(self, article: Article, post_id: str) -> SyncResult:
        """Update an existing cnblogs article."""
        payload = {
            "id": int(post_id),
            "postType": self.POST_TYPE_ARTICLE,
            "title": article.title,
            "postBody": article.raw_markdown,
            "tags": article.tags if article.tags else None,
            "isMarkdown": True,
            "isDraft": False,
            "isPublished": True,
        }

        url = f"{self.API_URL}/{post_id}"
        try:
            with self._create_client() as client:
                self._refresh_xsrf(client)
                resp = client.patch(url, json=payload)
        except TargetError:
            raise
        except httpx.RequestError as e:
            return SyncResult(target="cnblogs", success=False, error=f"Network error: {e}")

        if resp.status_code not in (200, 204):
            return SyncResult(
                target="cnblogs",
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        return SyncResult(target="cnblogs", success=True, post_id=post_id)
