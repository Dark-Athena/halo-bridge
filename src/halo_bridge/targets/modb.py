from __future__ import annotations

import logging

import httpx

from halo_bridge.exceptions import TargetError
from halo_bridge.models import Article, ModbConfig, SyncResult
from halo_bridge.targets import PlatformAdapter, register_adapter

logger = logging.getLogger(__name__)


@register_adapter
class ModbAdapter(PlatformAdapter):
    """modb.pro (墨天轮) adapter."""

    name = "modb"

    SAVE_URL = "https://www.modb.pro/api/knowledges/save"

    def __init__(self, config: ModbConfig) -> None:
        self.config = config

    def check_auth(self) -> None:
        """Verify modb.pro auth is valid. Raises TargetError if not."""
        try:
            resp = httpx.get(
                "https://www.modb.pro/api/knowledge/user/info",
                headers=self._headers(),
                timeout=10,
            )
        except httpx.RequestError as e:
            raise TargetError("modb", f"Network error: {e}")
        if resp.status_code in (401, 403):
            raise TargetError("modb", "登录已过期，请更新 config.yaml 中的 authorization 和 cookie")

    def _headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {
            "Cookie": self.config.cookie,
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/132.0.0.0 Safari/537.36"
            ),
            "Origin": "https://www.modb.pro",
            "Referer": "https://www.modb.pro/",
        }
        if self.config.authorization:
            headers["Authorization"] = self.config.authorization
        return headers

    def publish(self, article: Article, content: str | None = None) -> SyncResult:
        """Publish an article to modb.pro."""
        markdown_content = content or article.raw_markdown

        import markdown as md

        html_content = md.markdown(
            markdown_content,
            extensions=["tables", "fenced_code", "codehilite"],
        )

        payload = {
            "id": None,
            "title": article.title,
            "type": 1,
            "askMd": "",
            "tags": article.tags if article.tags else [],
            "answerMd": markdown_content,
            "answer": html_content,
            "isOriginal": True,
            "source": "",
            "brief": article.excerpt or "",
            "encryptLevel": "PUBLIC",
            "imageUrl": article.cover_image or "",
            "url": None,
            "sourceId": "",
            "status": 1,  # 0=draft, 1=published
        }

        try:
            resp = httpx.post(
                self.SAVE_URL,
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
        except httpx.RequestError as e:
            return SyncResult(target="modb", success=False, error=f"Network error: {e}")

        if resp.status_code != 200:
            return SyncResult(
                target="modb",
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        data = resp.json()
        if not data.get("success"):
            return SyncResult(
                target="modb",
                success=False,
                error=f"API error: {data.get('operateMessage', str(data)[:200])}",
            )

        obj = data.get("operateCallBackObj", {})
        post_id = str(obj.get("id", "")) if obj else ""
        post_url = f"https://www.modb.pro/knowledge?id={post_id}" if post_id else ""

        return SyncResult(
            target="modb",
            success=True,
            post_id=post_id,
            post_url=post_url,
        )
