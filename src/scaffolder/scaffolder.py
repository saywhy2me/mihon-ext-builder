"""Extension scaffolder.

Given a SiteInfo (from the analyzer), generates a complete Mihon extension
directory tree that can be dropped into the mihon-extensions repository.
"""

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jinja2 import Environment, BaseLoader

from src.models.site_info import SiteInfo, SiteType
from src.templates.kotlin_templates import TEMPLATE_MAP


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

def _build_gradle(ext_name: str, pkg_suffix: str, class_name: str,
                  nsfw: bool, version_code: int = 1) -> str:
    return textwrap.dedent(f"""\
        ext {{
            extName = '{ext_name}'
            pkgNameSuffix = '{pkg_suffix}'
            extClass = '.{class_name}'
            extVersionCode = {version_code}
            isNsfw = {str(nsfw).lower()}
        }}

        apply from: "$rootDir/common.gradle"
    """)


def _android_manifest(ext_id: str, site_name: str, base_url: str) -> str:
    domain = re.sub(r"https?://", "", base_url).rstrip("/")
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <manifest xmlns:android="http://schemas.android.com/apk/res/android">

            <application>
                <meta-data
                    android:name="app.mihon.extension"
                    android:value="true" />
                <meta-data
                    android:name="app.mihon.extension.version"
                    android:value="v1" />
                <!-- Source name shown in Mihon -->
                <meta-data
                    android:name="app.mihon.extension.name"
                    android:value="{site_name}" />
                <!-- Package ID — must be unique across all extensions -->
                <meta-data
                    android:name="app.mihon.extension.id"
                    android:value="{ext_id}" />
                <!-- Source website domain for network-security-config -->
                <meta-data
                    android:name="app.mihon.extension.domain"
                    android:value="{domain}" />
            </application>

        </manifest>
    """)


def _network_security_config(base_url: str) -> Optional[str]:
    """Only needed for HTTP (non-HTTPS) sources."""
    if base_url.startswith("http://"):
        domain = re.sub(r"http://", "", base_url).rstrip("/")
        return textwrap.dedent(f"""\
            <?xml version="1.0" encoding="utf-8"?>
            <network-security-config>
                <domain-config cleartextTrafficPermitted="true">
                    <domain includeSubdomains="true">{domain}</domain>
                </domain-config>
            </network-security-config>
        """)
    return None


def _setup_instructions(site_info: SiteInfo, class_name: str, pkg_suffix: str,
                         output_dir: Path) -> str:
    return textwrap.dedent(f"""\
        # Setup Instructions for {site_info.name or site_info.url}

        ## 1. Get the mihon-extensions repository
        ```
        git clone https://github.com/mihonapp/extensions-source.git
        cd extensions-source
        ```

        ## 2. Copy this extension into the repo
        ```
        cp -r "{output_dir}" src/{site_info.language or "en"}/{pkg_suffix.split('.')[-1]}/
        ```

        ## 3. Build the APK
        ```
        ./gradlew :{pkg_suffix.replace('.', ':')}:assembleDebug
        ```
        The APK will be at:
        `src/{site_info.language or "en"}/{pkg_suffix.split('.')[-1]}/build/outputs/apk/debug/`

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

    # Directory layout matching mihon-extensions repo structure
    output_dir = Path(output_root) / f"{lang}.{package_name}"
    kt_dir = output_dir / "src" / "eu" / "kanade" / "tachiyomi" / "extension" / lang / package_name
    res_dir = output_dir / "res" / "xml"

    for d in [kt_dir, res_dir]:
        d.mkdir(parents=True, exist_ok=True)

    files_created: list[Path] = []

    # ── build.gradle ────────────────────���─────────────────────────────────
    gradle_path = output_dir / "build.gradle"
    gradle_path.write_text(
        _build_gradle(site_name, pkg_suffix, class_name, nsfw, version_code),
        encoding="utf-8",
    )
    files_created.append(gradle_path)

    # ── AndroidManifest.xml ───────────────────────────────────────────────
    manifest_path = output_dir / "AndroidManifest.xml"
    manifest_path.write_text(
        _android_manifest(ext_id, site_name, base_url),
        encoding="utf-8",
    )
    files_created.append(manifest_path)

    # ── network_security_config.xml (HTTP only) ───────────────────────────
    nsc = _network_security_config(base_url)
    if nsc:
        nsc_path = res_dir / "network_security_config.xml"
        nsc_path.write_text(nsc, encoding="utf-8")
        files_created.append(nsc_path)
        warnings.append("HTTP (non-HTTPS) site — network_security_config.xml created")

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
