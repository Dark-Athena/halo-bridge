from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from halo_bridge.config import (
    DEFAULT_CONFIG_PATH,
    EXAMPLE_CONFIG,
    generate_example_config,
    load_config,
)
from halo_bridge.exceptions import ConfigError, HaloAPIError, UnknownTargetError
from halo_bridge.models import Article, BridgeConfig, SyncResult
from halo_bridge.source.halo import HaloSource, parse_slug
from halo_bridge.targets import get_adapter, list_adapters
from halo_bridge.transforms.copyright import append_copyright
from halo_bridge.transforms.image_urls import fix_image_urls
from halo_bridge.transforms.meta_referrer import add_meta_referrer

logger = logging.getLogger("halo_bridge")


@click.group()
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v=INFO, -vv=DEBUG).")
@click.version_option(package_name="halo-bridge")
def main(verbose: int) -> None:
    """Halo-Bridge: Sync articles from Halo blog to CSDN, cnblogs, and modb.pro."""
    level = logging.WARNING
    if verbose >= 2:
        level = logging.DEBUG
    elif verbose >= 1:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )


@main.command()
@click.argument("article_id")
@click.option(
    "--to",
    required=True,
    help="Comma-separated target platforms (e.g. csdn,cnblogs,modb).",
)
@click.option("-c", "--config", "config_path", default=None, help="Path to config file.")
@click.option("--dry-run", is_flag=True, help="Preview without publishing.")
@click.option(
    "--no-csdn-proxy",
    is_flag=True,
    help="Skip CSDN image proxy; publish original content directly to other targets.",
)
def sync(
    article_id: str,
    to: str,
    config_path: str | None,
    dry_run: bool,
    no_csdn_proxy: bool,
) -> None:
    """Sync an article from Halo to target platforms.

    ARTICLE_ID can be a slug or a full URL (e.g. https://www.darkathena.top/archives/my-post).
    """
    # Ensure all target adapters are imported
    _import_adapters()

    targets = [t.strip() for t in to.split(",") if t.strip()]
    if not targets:
        click.echo("Error: no targets specified in --to", err=True)
        sys.exit(1)

    # Load config
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Validate targets
    for t in targets:
        try:
            get_adapter(t)
        except UnknownTargetError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    # Fetch article from Halo
    slug = parse_slug(article_id, cfg.halo.base_url)
    click.echo(f"Fetching article '{slug}' from Halo...")
    try:
        with HaloSource(cfg.halo) as source:
            article = source.fetch_article(slug)
    except HaloAPIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"  Title: {article.title}")
    click.echo(f"  Tags:  {', '.join(article.tags) or '(none)'}")

    # Determine if we need CSDN proxy
    need_csdn_proxy = (
        not no_csdn_proxy
        and cfg.csdn is not None
        and any(t != "csdn" for t in targets)
    )

    # Validate auth for all targets before doing any work
    for target_name in targets:
        target_cfg = _get_target_config(cfg, target_name)
        if target_cfg is None:
            continue
        adapter = get_adapter(target_name)(target_cfg)
        if hasattr(adapter, "check_auth"):
            try:
                adapter.check_auth()
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)

    # Apply content transforms (fix image URLs, add copyright, etc.)
    content = apply_transforms(article, cfg, add_referrer=True)

    # If CSDN proxy is needed, convert external images to CSDN CDN first
    if need_csdn_proxy and cfg.csdn:
        click.echo("\nConverting images to CSDN CDN...")
        csdn_adapter = get_adapter("csdn")(cfg.csdn)
        content = csdn_adapter.convert_images(content)
        click.echo("  Done.")

    if dry_run:
        click.echo("\n--- Content Preview (first 500 chars) ---")
        click.echo(content[:500])
        click.echo("--- End Preview ---")
        click.echo(f"\nWould publish to: {', '.join(targets)}")
        if need_csdn_proxy:
            click.echo("(CSDN image proxy enabled)")
        click.echo("\nDry run -- no requests sent.")
        return

    # Publish to all targets
    results: list[SyncResult] = []
    for i, target_name in enumerate(targets):
        adapter_cls = get_adapter(target_name)
        target_cfg = _get_target_config(cfg, target_name)
        if target_cfg is None:
            results.append(SyncResult(
                target=target_name,
                success=False,
                error=f"Config for '{target_name}' missing.",
            ))
            continue

        adapter = adapter_cls(target_cfg)
        total = len(targets)
        click.echo(f"\n[{i + 1}/{total}] Publishing to {target_name}...")
        result = adapter.publish(article, content)
        results.append(result)

        if result.success:
            click.echo(f"  OK (id: {result.post_id}, url: {result.post_url or 'N/A'})")
        else:
            click.echo(f"  FAILED: {result.error}")

    # Summary
    succeeded = sum(1 for r in results if r.success)
    total = len(results)
    click.echo(f"\nSummary: {succeeded}/{total} targets succeeded.")

    if succeeded < total:
        sys.exit(1)


def apply_transforms(
    article: Article,
    config: BridgeConfig,
    add_referrer: bool = True,
) -> str:
    """Apply all content transforms and return the final markdown."""
    content = article.raw_markdown

    # 1. Fix image URLs to absolute
    content, img_count = fix_image_urls(content, config.halo.base_url)
    logger.info("Fixed %d relative image URLs", img_count)

    # 2. Add meta referrer (only for content going to CSDN or direct-to-source)
    if add_referrer:
        content = add_meta_referrer(content)

    # 3. Append copyright
    copyright_template = config.defaults.get("copyright", "")
    if copyright_template:
        content = append_copyright(content, copyright_template, article)

    return content


def _get_target_config(cfg: BridgeConfig, target_name: str):
    """Get the config object for a specific target."""
    return {
        "csdn": cfg.csdn,
        "cnblogs": cfg.cnblogs,
        "modb": cfg.modb,
    }.get(target_name)


def _import_adapters() -> None:
    """Import all adapter modules to trigger registration."""
    import halo_bridge.targets.csdn  # noqa: F401
    import halo_bridge.targets.cnblogs  # noqa: F401
    import halo_bridge.targets.modb  # noqa: F401


@main.group()
def config() -> None:
    """Manage configuration."""


@config.command("init")
@click.option(
    "-o",
    "--output",
    "output_path",
    default=None,
    help="Output path (default: ~/.halo-bridge/config.yaml).",
)
def config_init(output_path: str | None) -> None:
    """Generate an example config file."""
    dest = Path(output_path) if output_path else DEFAULT_CONFIG_PATH
    if dest.exists():
        click.echo(f"Config already exists: {dest}")
        click.echo("Use -o to specify a different path.")
        return
    generate_example_config(dest)
    click.echo(f"Example config written to: {dest}")


@config.command("show")
@click.option("-c", "--config", "config_path", default=None, help="Path to config file.")
def config_show(config_path: str | None) -> None:
    """Show loaded config (secrets are redacted)."""
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Halo:     {cfg.halo.base_url}")
    click.echo(f"  Token:  {cfg.halo.token[:8]}...{cfg.halo.token[-4:]}")
    click.echo(f"CSDN:     {'configured' if cfg.csdn else 'not configured'}")
    click.echo(f"cnblogs:  {'configured' if cfg.cnblogs else 'not configured'}")
    click.echo(f"modb:     {'configured' if cfg.modb else 'not configured'}")
    click.echo(f"Defaults: {cfg.defaults.get('targets', [])}")


@config.command("list-targets")
def config_list_targets() -> None:
    """List available target platforms."""
    _import_adapters()
    for name in list_adapters():
        click.echo(f"  {name}")
