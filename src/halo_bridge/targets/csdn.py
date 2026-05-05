from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import time
import uuid

import httpx

from halo_bridge.exceptions import TargetError
from halo_bridge.models import Article, CsdnConfig, SyncResult
from halo_bridge.targets import PlatformAdapter, register_adapter

logger = logging.getLogger(__name__)

# Match image URLs in markdown: ![alt](url)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# Match image URLs in HTML: <img src="url" ...>
_HTML_IMG_RE = re.compile(r'<img\s+[^>]*src="([^"]+)"[^>]*>', re.IGNORECASE)

# CSDN API Gateway signing config (extracted from csdn-http.js / app.chunk.js)
_CSDN_APP_KEY = "203803574"
_CSDN_APP_SECRET = "9znpamsyl2c7cdrr9sas0le9vbc3r6ba"


def _generate_signature(
    method: str,
    url: str,
    accept: str,
    content_type: str,
    date: str,
    ca_key: str,
    ca_nonce: str,
) -> str:
    """Generate X-Ca-Signature for CSDN API Gateway.

    Algorithm (from csdn-http.js):
    StringToSign = METHOD + \n + ACCEPT + \n + \n + CONTENT_TYPE + \n + DATE + \n
                   + CanonicalizedHeaders + CanonicalizedResource
    Signature = Base64(HmacSHA256(StringToSign, appSecret))
    """
    # Strip domain, split path and query
    stripped = re.sub(r"https?://[^/]+", "", url)
    if "?" in stripped:
        path, query = stripped.split("?", 1)
        # Parse and sort query params
        params = sorted(query.split("&"))
        resource = path + "?" + "&".join(params)
    else:
        resource = stripped

    # CanonicalizedHeaders: x-ca-* headers sorted
    headers_str = f"x-ca-key:{ca_key}\nx-ca-nonce:{ca_nonce}\n"

    string_to_sign = (
        f"{method}\n"
        f"{accept}\n"
        f"\n"
        f"{content_type}\n"
        f"{date}\n"
        f"{headers_str}"
        f"{resource}"
    )

    return base64.b64encode(
        hmac.new(
            _CSDN_APP_SECRET.encode(),
            string_to_sign.encode(),
            hashlib.sha256,
        ).digest()
    ).decode()


@register_adapter
class CsdnAdapter(PlatformAdapter):
    """CSDN blog adapter with image proxy support."""

    name = "csdn"

    SAVE_URL = "https://bizapi.csdn.net/blog-console-api/v3/mdeditor/saveArticle"
    GET_URL = "https://bizapi.csdn.net/blog-console-api/v3/editor/getArticle"
    IMG_CONVERT_URL = "https://imgservice.csdn.net/img-convert/external/storage"

    def __init__(self, config: CsdnConfig) -> None:
        self.config = config

    def check_auth(self) -> None:
        """Verify CSDN cookie is valid. Raises TargetError if not."""
        # Use the image convert endpoint to check auth (lightweight, no side effects)
        try:
            resp = httpx.post(
                self.IMG_CONVERT_URL,
                json={"art_id": "undefined", "imgUrl": "https://example.com/test.png", "uuid": "test"},
                headers=self._cookie_headers(),
                timeout=10,
            )
        except httpx.RequestError as e:
            raise TargetError("csdn", f"Network error: {e}")
        if resp.status_code in (401, 403):
            raise TargetError("csdn", "登录已过期，请运行 `halo-bridge login csdn` 更新 cookie")

    def _cookie_headers(self) -> dict[str, str]:
        """Basic headers with cookie for non-signed endpoints."""
        return {
            "Cookie": self.config.cookie,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0"
            ),
            "Content-Type": "application/json",
        }

    def convert_image(self, image_url: str) -> str | None:
        """Convert an external image URL to CSDN CDN URL.

        Returns the CSDN CDN URL, or None if conversion fails.
        """
        img_uuid = f"img-{uuid.uuid4().hex[:8]}-{int(time.time() * 1000)}"
        payload = {
            "art_id": "undefined",
            "imgUrl": image_url,
            "uuid": img_uuid,
        }

        try:
            resp = httpx.post(
                self.IMG_CONVERT_URL,
                json=payload,
                headers=self._cookie_headers(),
                timeout=30,
            )
        except httpx.RequestError as e:
            logger.warning("Image convert network error for %s: %s", image_url, e)
            return None

        if resp.status_code != 200:
            logger.warning("Image convert HTTP %d for %s: %s", resp.status_code, image_url, resp.text[:200])
            return None

        data = resp.json()
        if data.get("code") != 200:
            logger.warning("Image convert error for %s: %s", image_url, data.get("msg", ""))
            return None

        cdn_url = data.get("data", {}).get("url", "")
        if not cdn_url:
            logger.warning("Image convert returned empty URL for %s", image_url)
            return None

        return cdn_url

    def convert_images(self, markdown_content: str) -> str:
        """Convert all external image URLs to CSDN CDN URLs.

        Handles both markdown ![alt](url) and HTML <img src="url"> syntax.
        Returns the content with URLs replaced. Images that fail to convert
        are left as-is.
        """
        # Collect all external image URLs (both markdown and HTML)
        url_map: dict[str, str] = {}  # old_url -> new_url

        # Markdown images
        for match in _IMAGE_RE.finditer(markdown_content):
            url = match.group(2)
            if not url.startswith("https://img-blog.csdnimg.cn") and url not in url_map:
                url_map[url] = ""  # placeholder

        # HTML img tags
        for match in _HTML_IMG_RE.finditer(markdown_content):
            url = match.group(1)
            if not url.startswith("https://img-blog.csdnimg.cn") and url not in url_map:
                url_map[url] = ""

        if not url_map:
            return markdown_content

        # Make relative URLs absolute
        for url in list(url_map.keys()):
            if url.startswith("/"):
                url_map[url] = ""  # will be converted below

        logger.info("Converting %d external images to CSDN CDN...", len(url_map))

        # Convert each URL
        converted = 0
        for old_url in url_map:
            # Make relative URLs absolute
            full_url = old_url
            if old_url.startswith("/"):
                # Need base URL - extract from config or use Halo URL
                # For now, skip relative URLs (they should have been fixed by fix_image_urls)
                logger.debug("Skipping relative URL: %s", old_url)
                continue

            new_url = self.convert_image(full_url)
            if new_url:
                url_map[old_url] = new_url
                converted += 1
                logger.debug("Converted: %s -> %s", old_url, new_url)

        # Replace URLs in content
        result = markdown_content
        for old_url, new_url in url_map.items():
            if new_url:
                result = result.replace(old_url, new_url)

        logger.info("Converted %d/%d images to CSDN CDN", converted, len(url_map))
        return result

    def _signed_headers(self, method: str, url: str, content_type: str = "application/json") -> dict[str, str]:
        """Generate signed headers for a CSDN API request."""
        ca_nonce = str(uuid.uuid4())
        signature = _generate_signature(
            method=method,
            url=url,
            accept="*/*",
            content_type=content_type,
            date="",
            ca_key=_CSDN_APP_KEY,
            ca_nonce=ca_nonce,
        )
        headers = {
            "Cookie": self.config.cookie,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0"
            ),
            "Origin": "https://editor.csdn.net",
            "Referer": "https://editor.csdn.net/",
            "X-Ca-Key": _CSDN_APP_KEY,
            "X-Ca-Nonce": ca_nonce,
            "X-Ca-Signature": signature,
            "X-Ca-Signature-Headers": "x-ca-key,x-ca-nonce",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def publish(self, article: Article, content: str | None = None) -> SyncResult:
        """Publish an article to CSDN."""
        markdown_content = content or article.raw_markdown

        # CSDN requires HTML content field; convert markdown if needed
        import markdown as md

        html_content = md.markdown(
            markdown_content,
            extensions=["tables", "fenced_code", "codehilite"],
        )

        payload = {
            "id": 0,
            "title": article.title,
            "markdowncontent": markdown_content,
            "content": html_content,
            "readType": "public",
            "level": 0,
            "tags": ",".join(article.tags),
            "status": 2,
            "categories": ",".join(article.categories) if article.categories else "",
            "type": "original",
            "original_link": "",
            "authorized_status": False,
            "not_auto_saved": "1",
            "source": "pc_mdeditor",
            "cover_images": [],
            "cover_type": 1,
            "is_new": 1,
            "vote_id": 0,
            "resource_id": "",
            "pubStatus": "publish",
            "creation_statement": 0,
            "creator_activity_id": "",
        }

        headers = self._signed_headers("POST", self.SAVE_URL)

        try:
            resp = httpx.post(self.SAVE_URL, json=payload, headers=headers, timeout=30)
        except httpx.RequestError as e:
            return SyncResult(target="csdn", success=False, error=f"Network error: {e}")

        if resp.status_code != 200:
            return SyncResult(
                target="csdn",
                success=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        data = resp.json()
        if data.get("code") != 200:
            return SyncResult(
                target="csdn",
                success=False,
                error=f"API error: {data.get('message', resp.text[:200])}",
            )

        resp_data = data.get("data", {})
        article_id = resp_data.get("id", "")
        article_url = resp_data.get("url", "")

        return SyncResult(
            target="csdn",
            success=True,
            post_id=str(article_id),
            post_url=article_url,
        )

    def fetch_article_content(self, article_id: str) -> str:
        """Fetch the article markdown content from CSDN by article ID."""
        url = f"{self.GET_URL}?id={article_id}&not_article=false"
        headers = self._signed_headers("GET", url, content_type="")

        try:
            resp = httpx.get(url, headers=headers, timeout=30)
        except httpx.RequestError as e:
            raise TargetError("csdn", f"Network error fetching article: {e}")

        if resp.status_code != 200:
            raise TargetError(
                "csdn",
                f"HTTP {resp.status_code} fetching article: {resp.text[:200]}",
            )

        data = resp.json()
        if data.get("code") != 200:
            raise TargetError(
                "csdn",
                f"API error: {data.get('message', resp.text[:200])}",
            )

        markdown = data.get("data", {}).get("markdowncontent", "")
        if not markdown:
            raise TargetError("csdn", "Empty markdowncontent in response")

        return markdown
