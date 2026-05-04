from __future__ import annotations

import os
from pathlib import Path

import yaml

from halo_bridge.exceptions import ConfigError
from halo_bridge.models import (
    BridgeConfig,
    CnblogsConfig,
    CsdnConfig,
    HaloConfig,
    ModbConfig,
)

DEFAULT_CONFIG_PATH = Path.home() / ".halo-bridge" / "config.yaml"
ENV_PREFIX = "HALO_BRIDGE_"


def load_config(config_path: str | Path | None = None) -> BridgeConfig:
    """Load and validate config from YAML file with env var overrides."""
    path = Path(config_path) if config_path else _resolve_config_path()

    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}\n"
            f"Run 'halo-bridge config init' to generate an example config."
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Apply environment variable overrides
    _apply_env_overrides(raw)

    return _build_config(raw)


def _resolve_config_path() -> Path:
    """Resolve config file path from env or default."""
    env_path = os.environ.get(f"{ENV_PREFIX}CONFIG")
    if env_path:
        return Path(env_path)
    return DEFAULT_CONFIG_PATH


def _apply_env_overrides(raw: dict) -> None:
    """Override config values from environment variables."""
    env_map = {
        f"{ENV_PREFIX}HALO_BASE_URL": ("halo", "base_url"),
        f"{ENV_PREFIX}HALO_TOKEN": ("halo", "token"),
        f"{ENV_PREFIX}CSDN_COOKIE": ("csdn", "cookie"),
        f"{ENV_PREFIX}CNBLOGS_COOKIE": ("cnblogs", "cookie"),
        f"{ENV_PREFIX}CNBLOGS_XSRF": ("cnblogs", "xsrf_token"),
        f"{ENV_PREFIX}MODB_AUTH": ("modb", "authorization"),
        f"{ENV_PREFIX}MODB_COOKIE": ("modb", "cookie"),
    }
    for env_key, (section, key) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            raw.setdefault(section, {})
            raw[section][key] = val


def _build_config(raw: dict) -> BridgeConfig:
    """Build BridgeConfig from raw dict."""
    halo_raw = raw.get("halo")
    if not halo_raw or not halo_raw.get("base_url") or not halo_raw.get("token"):
        raise ConfigError(
            "Missing 'halo.base_url' or 'halo.token' in config.\n"
            "These are required to fetch articles from your Halo blog."
        )

    halo = HaloConfig(
        base_url=halo_raw["base_url"].rstrip("/"),
        token=halo_raw["token"],
    )

    csdn = None
    csdn_raw = raw.get("csdn")
    if csdn_raw and csdn_raw.get("cookie"):
        csdn = CsdnConfig(cookie=csdn_raw["cookie"])

    cnblogs = None
    cnblogs_raw = raw.get("cnblogs")
    if cnblogs_raw and cnblogs_raw.get("cookie"):
        cnblogs = CnblogsConfig(
            cookie=cnblogs_raw["cookie"],
            xsrf_token=cnblogs_raw.get("xsrf_token", ""),
        )

    modb = None
    modb_raw = raw.get("modb")
    if modb_raw and (modb_raw.get("authorization") or modb_raw.get("cookie")):
        modb = ModbConfig(
            authorization=modb_raw.get("authorization", ""),
            cookie=modb_raw.get("cookie", ""),
        )

    defaults = raw.get("defaults", {})

    return BridgeConfig(
        halo=halo,
        csdn=csdn,
        cnblogs=cnblogs,
        modb=modb,
        defaults=defaults,
    )


def generate_example_config(dest: Path) -> None:
    """Write example config file to dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(EXAMPLE_CONFIG)


EXAMPLE_CONFIG = """\
# halo-bridge 配置文件
# 请将此文件复制到 ~/.halo-bridge/config.yaml 并填入你的凭据

halo:
  base_url: "https://www.darkathena.top"
  token: "pat-xxxxxxxxxxxx"           # Halo 个人访问令牌 (Personal Access Token)

csdn:
  cookie: "UserToken=xxx; dc_sid=xxx; ..."  # 从浏览器 DevTools 复制完整 Cookie 字符串

cnblogs:
  cookie: ".CNBlogsCookie=xxx; .Cnblogs.AspNetCore.Cookies=xxx; ..."  # 从浏览器 DevTools 复制完整 Cookie
  xsrf_token: "CfDJ8xxxx"            # 从请求头 X-XSRF-TOKEN 获取（可选，自动从 cookie 解析）

modb:
  # 墨天轮认证信息（需从浏览器抓包获取）
  authorization: "Bearer xxxxxx"
  # cookie: "session=xxxxx"

defaults:
  targets: ["csdn", "cnblogs"]        # 默认同步目标
  copyright: |
    ---
    > - **本文作者：** [DarkAthena](https://www.darkathena.top)
    > - **本文链接：** [{permalink}]({permalink})
    > - **版权声明：** 本博客所有文章除特别声明外，均采用[CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) 许可协议。转载请注明出处
"""
