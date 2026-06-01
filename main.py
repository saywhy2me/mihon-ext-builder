"""Mihon Extension Builder CLI.

Usage:
  python main.py analyze  <url>                    - Fingerprint a manga source website
  python main.py scaffold <url>                    - Generate a Kotlin/Gradle extension project
  python main.py check    <url>                    - Test extension selectors against a live site
"""

import json
import sys
from pathlib import Path

import click

from src.analyzer.site_analyzer import analyze
from src.checker.health_checker import check_extension, quick_check
from src.models.site_info import HealthStatus, SiteType
from src.scaffolder.scaffolder import scaffold


@click.group()
def cli():
    """Mihon Extension Builder — analyze, scaffold, and health-check manga source extensions."""


# ── analyze ───────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("url")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output result as JSON.")
def analyze_cmd(url: str, as_json: bool):
    """Fingerprint a manga source URL and show its CMS type, health, and recommended template."""
    if not as_json:
        click.echo(f"Analyzing: {url}")
    info = analyze(url)

    if as_json:
        data = {
            "url": info.url,
            "type": info.site_type.value,
            "health": info.health.value,
            "name": info.name,
            "language": info.language,
            "template": info.recommended_template,
            "cloudflare": info.has_cloudflare,
            "confidence": round(info.confidence, 2),
            "http_status": info.http_status,
            "response_ms": info.response_time_ms,
            "notes": info.notes,
        }
        click.echo(json.dumps(data, indent=2))
        return

    # Colour-coded health badge
    health_colour = {
        HealthStatus.ALIVE: "green",
        HealthStatus.DEGRADED: "yellow",
        HealthStatus.DEAD: "red",
        HealthStatus.CLOUDFLARE_BLOCKED: "red",
        HealthStatus.RATE_LIMITED: "yellow",
    }.get(info.health, "white")

    click.echo()
    click.secho(f"  Name       : {info.name or 'unknown'}", bold=True)
    click.secho(f"  Type       : {info.site_type.value}", fg="cyan")
    click.secho(f"  Health     : {info.health.value}", fg=health_colour, bold=True)
    click.echo(f"  Confidence : {info.confidence:.0%}")
    click.echo(f"  Template   : {info.recommended_template or 'none'}")
    click.echo(f"  Language   : {info.language or 'unknown'}")
    click.secho(f"  Cloudflare : {'yes' if info.has_cloudflare else 'no'}",
                fg="yellow" if info.has_cloudflare else "white")
    if info.response_time_ms:
        click.echo(f"  Response   : {info.response_time_ms}ms")
    if info.notes:
        click.echo()
        click.secho("  Notes:", bold=True)
        for note in info.notes:
            click.echo(f"    - {note}")

    if info.health == HealthStatus.DEAD:
        sys.exit(1)


# ── scaffold ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("url")
@click.option("--output", "-o", default="generated", show_default=True,
              help="Parent directory for the generated extension project.")
@click.option("--lang", default=None,
              help="Language code override (e.g. en, ja, zh). Auto-detected if omitted.")
@click.option("--class-name", "class_name", default=None,
              help="Override the generated Kotlin class name.")
@click.option("--nsfw", is_flag=True, default=False,
              help="Mark extension as NSFW in build.gradle.")
@click.option("--version-code", "version_code", default=1, show_default=True,
              help="Initial extVersionCode for the APK.")
@click.option("--skip-analyze", is_flag=True, default=False,
              help="Skip live analysis; use http_source template (faster, offline).")
def scaffold_cmd(url, output, lang, class_name, nsfw, version_code, skip_analyze):
    """Analyze a URL and generate a complete Kotlin/Gradle Mihon extension project."""
    if skip_analyze:
        from src.models.site_info import SiteInfo as _SI
        info = _SI(url=url, site_type=SiteType.UNKNOWN, health=HealthStatus.ALIVE,
                   base_url=url, recommended_template="http_source")
        click.secho("Skipping analysis — using http_source template.", fg="yellow")
    else:
        click.echo(f"Analyzing: {url}")
        info = analyze(url)
        health_col = "green" if info.health == HealthStatus.ALIVE else "red"
        click.secho(f"  Detected  : {info.site_type.value} ({info.health.value})",
                    fg=health_col)
        click.echo(f"  Template  : {info.recommended_template}")
        if info.has_cloudflare:
            click.secho("  Cloudflare: yes — CloudflareInterceptor will be wired in", fg="yellow")

    click.echo()
    result = scaffold(info, output_root=output, nsfw=nsfw, version_code=version_code,
                      override_class_name=class_name, override_lang=lang)

    click.secho(f"Extension generated: {result.output_dir}", fg="green", bold=True)
    click.echo(f"  Extension ID : {result.ext_id}")
    click.echo(f"  Class name   : {result.class_name}")
    click.echo()
    click.echo("  Files:")
    for f in result.files_created:
        click.echo(f"    {f.relative_to(result.output_dir)}")

    if result.warnings:
        click.echo()
        click.secho("  Warnings:", fg="yellow")
        for w in result.warnings:
            click.secho(f"    ! {w}", fg="yellow")

    click.echo()
    click.secho("Next step: see SETUP.md inside the generated directory.", bold=True)


# ── check ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("url")
@click.option("--manga", "-m", default=None,
              help="URL path to a manga detail page (e.g. /manga/noblesse).")
@click.option("--chapter", "-c", default=None,
              help="URL path to a chapter page (e.g. /manga/noblesse/chapter-1).")
@click.option("--site-type", "site_type", default=None,
              help="Override site type for selector profile (madara, manganow, etc.).")
@click.option("--output", "-o", default=None,
              help="Save the plain-text report to this file.")
@click.option("--quick", is_flag=True, default=False,
              help="Homepage-only check (faster; no --manga/--chapter needed).")
def check_cmd(url, manga, chapter, site_type, output, quick):
    """Test CSS selectors of a Mihon extension against a live site."""
    # Auto-detect site type if not overridden
    resolved_type = site_type
    if not resolved_type:
        click.echo(f"Detecting site type for: {url}")
        info = analyze(url)
        resolved_type = info.recommended_template or "generic"
        click.echo(f"  Detected: {info.site_type.value} → using '{resolved_type}' selector profile")
    else:
        click.echo(f"Using site type: {resolved_type}")

    click.echo()

    if quick:
        report = quick_check(url, site_type=resolved_type)
    else:
        report = check_extension(url, site_type=resolved_type,
                                 manga_path=manga, chapter_path=chapter)

    report_text = report.format()
    click.echo(report_text)

    if output:
        Path(output).write_text(report_text, encoding="utf-8")
        click.secho(f"\nReport saved to: {output}", fg="cyan")

    if not report.is_healthy:
        click.secho(f"\n{report.total_broken} selector(s) need fixing.", fg="red", bold=True)
        sys.exit(1)
    else:
        click.secho("\nAll selectors passing.", fg="green", bold=True)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
