from dataclasses import dataclass, field


@dataclass
class Article:
    """Canonical article representation fetched from Halo."""

    title: str
    slug: str
    raw_markdown: str
    html_content: str
    permalink: str
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    excerpt: str = ""
    cover_image: str = ""


@dataclass
class SyncResult:
    """Result of publishing to a single target."""

    target: str
    success: bool
    post_id: str | None = None
    post_url: str | None = None
    error: str | None = None


@dataclass
class HaloConfig:
    base_url: str
    token: str


@dataclass
class CsdnConfig:
    cookie: str


@dataclass
class CnblogsConfig:
    cookie: str
    xsrf_token: str = ""


@dataclass
class ModbConfig:
    authorization: str = ""
    cookie: str = ""


@dataclass
class BridgeConfig:
    halo: HaloConfig
    csdn: CsdnConfig | None = None
    cnblogs: CnblogsConfig | None = None
    modb: ModbConfig | None = None
    defaults: dict = field(default_factory=dict)
