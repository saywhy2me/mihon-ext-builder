"""Extension scaffolder.

Given a SiteInfo (from the analyzer), generates a complete Mihon extension
directory tree that can be dropped into the mihon-extensions repository.
"""

import hashlib
import re
import struct
import textwrap
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jinja2 import Environment, BaseLoader

from src.models.site_info import SiteInfo, SiteType
from src.templates.kotlin_templates import TEMPLATE_MAP

# Launcher-icon densities required by every keiyoushi extension (px per side).
_ICON_DENSITIES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_class_name(name: str) -> str:
    """'My Manga Site' → 'MyMangaSite'"""
    return re.sub(r"[^a-zA-Z0-9]", " ", name).title().replace(" ", "")


def _to_package_name(name: str) -> str:
    """'My Manga Site' → 'mymangasite'"""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _to_ext_id(lang: str, package_name: str) -> str:
    return f"eu.kanade.tachiyomi.extension.{lang}.{package_name}"


_jinja = Environment(loader=BaseLoader(), keep_trailing_newline=True)


@dataclass
class ScaffoldResult:
    output_dir: Path
    files_created: list[Path]
    class_name: str
    package_name: str
    ext_id: str
    warnings: list[str]

    def summary(self) -> str:
        lines = [
            f"Output dir   : {self.output_dir}",
            f"Extension ID : {self.ext_id}",
            f"Class name   : {self.class_name}",
            f"Files created: {len(self.files_created)}",
        ]
        for f in self.files_created:
            lines.append(f"  {f.relative_to(self.output_dir)}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ! {w}")
        return "\n".join(lines)


# ── file content generators ───────────────────────────────────────────────────

def _build_gradle(ext_name: str, class_name: str,
                  nsfw: bool, version_code: int = 1) -> str:
    # Current keiyoushi/extensions-source format. The package id is derived from
    # the src/<lang>/<name>/ path, so no pkgNameSuffix is needed, and the legacy
    # plugin generates the AndroidManifest from extClass/isNsfw.
    safe_name = ext_name.replace("'", "")
    return textwrap.dedent(f"""\
        ext {{
            extName = '{safe_name}'
            extClass = '.{class_name}'
            extVersionCode = {version_code}
            isNsfw = {str(nsfw).lower()}
        }}

        apply plugin: "kei.plugins.extension.legacy"
    """)


def _solid_png(size: int, rgba: tuple[int, int, int, int]) -> bytes:
    """Encode a solid-colour RGBA PNG of the given side length (no external deps)."""
    row = bytes(rgba) * size
    raw = bytearray()
    for _ in range(size):
        raw.append(0)          # PNG filter type 0 (None) per scanline
        raw += row

    def _chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


def _icon_color(seed: str) -> tuple[int, int, int, int]:
    """Deterministic, reasonably bright colour derived from the source name."""
    h = hashlib.sha1(seed.encode("utf-8")).digest()
    return (80 + h[0] % 150, 80 + h[1] % 150, 80 + h[2] % 150, 255)


def _write_icons(res_root: Path, seed: str) -> list[Path]:
    """Write placeholder ic_launcher.png at all required densities."""
    color = _icon_color(seed)
    created: list[Path] = []
    for density, size in _ICON_DENSITIES.items():
        d = res_root / f"mipmap-{density}"
        d.mkdir(parents=True, exist_ok=True)
        path = d / "ic_launcher.png"
        path.write_bytes(_solid_png(size, color))
        created.append(path)
    return created


def _setup_instructions(site_info: SiteInfo, class_name: str, pkg_suffix: str,
                         output_dir: Path) -> str:
    lang = site_info.language or "en"
    pkg = pkg_suffix.split('.')[-1]
    return textwrap.dedent(f"""\
        # Setup Instructions for {site_info.name or site_info.url}

        ## Easiest: build the APK on GitHub (no local tools)
        If this project lives in the mihon-ext-builder repository on GitHub:
        open the **Actions** tab, pick **"Build Extension APK"**, click
        **Run workflow**, paste the site URL, and download the finished APK
        from the run's **Artifacts** when it completes.

        ---

        ## Build it yourself

        ### 1. Get the extensions-source repository
        ```
        git clone https://github.com/keiyoushi/extensions-source.git
        cd extensions-source
        ```

        ### 2. Copy this extension into the repo
        ```
        cp -r "{output_dir}" src/{lang}/{pkg}/
        ```

        ### 3. Build the APK
        ```
        ./gradlew src:{lang}:{pkg}:assembleDebug
        ```
        The APK will be at:
        `src/{lang}/{pkg}/build/outputs/apk/debug/`

        ## 4. Install on device
        ```
        adb install -r path/to/extension.apk
        ```
        Or sideload via Mihon Settings → Browse → Add extension repo.

        ## 5. Key files to customise
        - **{class_name}.kt** — main source class; fill in `TODO:` selectors
        - **build.gradle** — bump `extVersionCode` each release
        - **AndroidManifest.xml** — update domain if the site URL changes

        ## Site analysis notes
        {chr(10).join('- ' + n for n in site_info.notes) if site_info.notes else '- None'}

        ## Detected type: {site_info.site_type.value}
        Template used : {site_info.recommended_template}
        Cloudflare    : {'YES — CloudflareInterceptor is already wired in' if site_info.has_cloudflare else 'No'}
    """)


# ── main scaffolder ───────────────────────────────────────────────────────────

def scaffold(
    site_info: SiteInfo,
    output_root: str | Path = "generated",
    nsfw: bool = False,
    version_code: int = 1,
    override_class_name: Optional[str] = None,
    override_lang: Optional[str] = None,
) -> ScaffoldResult:
    """Generate a Mihon extension project from a SiteInfo.

    Args:
        site_info: Analysis result from site_analyzer.analyze()
        output_root: Parent directory for generated projects.
        nsfw: Mark this extension as NSFW in build.gradle.
        version_code: Initial versionCode for the APK.
        override_class_name: Use this class name instead of auto-derived.
        override_lang: Use this language code instead of what was detected.

    Returns:
        ScaffoldResult with paths of all created files and any warnings.
    """
    warnings: list[str] = []

    site_name = site_info.name or "UnknownSite"
    lang = override_lang or site_info.language or "en"
    class_name = override_class_name or _to_class_name(site_name)
    package_name = _to_package_name(site_name)
    pkg_suffix = f"{lang}.{package_name}"
    ext_id = _to_ext_id(lang, package_name)
    base_url = (site_info.base_url or site_info.url).rstrip("/")
    template_key = site_info.recommended_template or "http_source"

    # Directory layout matching an individual keiyoushi extension folder.
    output_dir = Path(output_root) / f"{lang}.{package_name}"
    kt_dir = output_dir / "src" / "eu" / "kanade" / "tachiyomi" / "extension" / lang / package_name
    res_dir = output_dir / "res"

    kt_dir.mkdir(parents=True, exist_ok=True)

    files_created: list[Path] = []

    # ── build.gradle (keiyoushi legacy-plugin format) ──────────────────────
    gradle_path = output_dir / "build.gradle"
    gradle_path.write_text(
        _build_gradle(site_name, class_name, nsfw, version_code),
        encoding="utf-8",
    )
    files_created.append(gradle_path)

    # ── launcher icons (required; the build links @mipmap/ic_launcher) ─────
    files_created.extend(_write_icons(res_dir, seed=package_name))

    if base_url.startswith("http://"):
        warnings.append(
            "HTTP (non-HTTPS) site — add a network_security_config and reference it "
            "from the source, or the app will block cleartext traffic."
        )

    # ── Kotlin source ─────────────────────────────────────────────────────
    template_str = TEMPLATE_MAP.get(template_key, TEMPLATE_MAP["http_source"])
    kt_source = _jinja.from_string(template_str).render(
        lang=lang,
        package_name=package_name,
        class_name=class_name,
        site_name=site_name,
        base_url=base_url,
        has_cloudflare=site_info.has_cloudflare,
        nsfw=nsfw,
        override_manga_url_directory=(site_info.site_type == SiteType.MADARA),
    )
    kt_path = kt_dir / f"{class_name}.kt"
    kt_path.write_text(kt_source, encoding="utf-8")
    files_created.append(kt_path)

    # ── setup instructions ────────────────────────────────────────────────
    readme_path = output_dir / "SETUP.md"
    readme_path.write_text(
        _setup_instructions(site_info, class_name, pkg_suffix, output_dir),
        encoding="utf-8",
    )
    files_created.append(readme_path)

    if site_info.site_type.value in ("unknown", "custom"):
        warnings.append(
            "Site type is unknown/custom — the generated HttpSource has TODO placeholders "
            "that must be filled in manually by inspecting the site's HTML."
        )
    if site_info.has_cloudflare:
        warnings.append("Cloudflare detected — CloudflareInterceptor is wired in but may need tuning")

    return ScaffoldResult(
        output_dir=output_dir,
        files_created=files_created,
        class_name=class_name,
        package_name=package_name,
        ext_id=ext_id,
        warnings=warnings,
    )
