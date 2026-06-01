"""Site analyzer for Mihon extension development.

Fetches a manga source URL and fingerprints the site type so the scaffolder
can pick the right extension template. Works without JavaScript execution —
relies on HTML signatures, HTTP headers, and known API endpoint probes.
"""

import time
from urllib.parse import urlparse, urljoin
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.models.site_info import (
    SiteInfo, SiteType, HealthStatus, DetectedFeature
)

_TIMEOUT = 12
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ── detection fingerprints ────────────────────────────────────────────────────

_MADARA_SIGNALS = [
    "wp-content/themes/madara",
    "wp-content/plugins/madara",
    "manga-reading-actions",
    "manga-chapters",
    "wp-manga",
    "\"madara\"",
]

_MANGADEX_SIGNALS = [
    "mangadex.org",
    "api.mangadex.org",
]

_COMICK_SIGNALS = [
    "comick.io",
    "comick.app",
    "api.comick.io",
]

_MANGA_READER_SIGNALS = [
    "class=\"manga-info\"",
    "id=\"manga-chapters-holder\"",
    "class=\"listing\"",
    "readmanga",
    "mangareader",
]

_WEBTOON_SIGNALS = [
    "webtoon",
    "manhwa",
    "class=\"viewer-cont\"",
    "data-episode",
]

# MangaNow.to-specific fingerprints (high confidence, checked before generic webtoon)
_MANGANOW_SIGNALS = [
    "manganow.to",
    "class=\"anisc-detail\"",
    "class=\"reading-item chapter-item\"",
    "class=\"manga_list-sbs\"",
    "class=\"anisc-poster\"",
]

_CLOUDFLARE_SIGNALS = [
    "cloudflare",
    "cf-ray",
    "just a moment",
    "__cf_bm",
    "checking your browser",
]


def _normalise_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _check_cloudflare(response: requests.Response, html: str) -> bool:
    headers_str = " ".join(f"{k}: {v}" for k, v in response.headers.items()).lower()
    html_lower = html.lower()
    return any(sig in headers_str or sig in html_lower for sig in _CLOUDFLARE_SIGNALS)


def _detect_type(html: str, url: str, soup: BeautifulSoup) -> tuple[SiteType, list[DetectedFeature]]:
    features: list[DetectedFeature] = []
    html_lower = html.lower()
    url_lower = url.lower()

    # MangaDex — domain-based, very reliable
    if any(sig in url_lower for sig in _MANGADEX_SIGNALS):
        features.append(DetectedFeature("MangaDex domain", 1.0, "URL matches mangadex.org"))
        return SiteType.MANGADEX, features

    # ComicK
    if any(sig in url_lower for sig in _COMICK_SIGNALS):
        features.append(DetectedFeature("ComicK domain", 1.0, "URL matches comick.io/app"))
        return SiteType.COMICK, features

    # Madara — most common manga WordPress theme
    madara_hits = [sig for sig in _MADARA_SIGNALS if sig in html_lower]
    if madara_hits:
        conf = min(0.6 + len(madara_hits) * 0.1, 1.0)
        features.append(DetectedFeature(
            "Madara theme signals", conf,
            f"Found: {', '.join(madara_hits[:3])}"
        ))
        # Confirm WordPress
        if "wp-content" in html_lower or "wp-json" in html_lower:
            features.append(DetectedFeature("WordPress confirmed", 0.95, "wp-content or wp-json present"))
        return SiteType.MADARA, features

    # MangaNow.to — checked before generic manga reader / webtoon
    manganow_hits = [sig for sig in _MANGANOW_SIGNALS if sig in html_lower or sig in url_lower]
    if manganow_hits:
        conf = min(0.7 + len(manganow_hits) * 0.1, 1.0)
        features.append(DetectedFeature(
            "MangaNow.to signals", conf,
            f"Found: {', '.join(manganow_hits[:3])}"
        ))
        return SiteType.MANGANOW, features

    # Generic manga reader
    reader_hits = [sig for sig in _MANGA_READER_SIGNALS if sig in html_lower]
    if reader_hits:
        conf = min(0.5 + len(reader_hits) * 0.1, 0.9)
        features.append(DetectedFeature("Manga reader signals", conf, f"Found: {', '.join(reader_hits[:3])}"))
        return SiteType.MANGA_READER, features

    # Webtoon/manhwa style
    webtoon_hits = [sig for sig in _WEBTOON_SIGNALS if sig in html_lower]
    if len(webtoon_hits) >= 2:
        features.append(DetectedFeature("Webtoon signals", 0.7, f"Found: {', '.join(webtoon_hits[:3])}"))
        return SiteType.WEBTOON, features

    # WordPress but no Madara — could be a different manga theme
    if "wp-content" in html_lower or "wp-json" in html_lower:
        features.append(DetectedFeature("WordPress (non-Madara)", 0.5, "wp-content present but no Madara theme detected"))
        return SiteType.CUSTOM, features

    features.append(DetectedFeature("No known pattern", 0.0, "Could not match any known manga CMS"))
    return SiteType.UNKNOWN, features


def _probe_api_endpoints(base_url: str) -> Optional[str]:
    """Try common API paths to find a JSON API."""
    probes = [
        "/api/v2/manga",
        "/api/manga",
        "/wp-json/wp/v2/manga",
        "/wp-json/madara/v1/manga",
    ]
    for path in probes:
        try:
            r = requests.get(urljoin(base_url, path), headers=_HEADERS, timeout=6)
            if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
                return urljoin(base_url, path)
        except Exception:
            pass
    return None


def _extract_site_name(soup: BeautifulSoup, url: str) -> str:
    og_title = soup.find("meta", property="og:site_name")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text().split("|")[0].split("-")[0].strip()
    return urlparse(url).netloc


_TEMPLATE_MAP = {
    SiteType.MADARA:       "madara",
    SiteType.MANGADEX:     "mangadex",
    SiteType.COMICK:       "comick",
    SiteType.MANGA_READER: "manga_reader",
    SiteType.WEBTOON:      "webtoon",
    SiteType.MANGANOW:     "manganow",
    SiteType.CUSTOM:       "http_source",
    SiteType.UNKNOWN:      "http_source",
}


def analyze(url: str) -> SiteInfo:
    """Fetch and fingerprint a manga source URL.

    Returns a SiteInfo regardless of whether the site is alive, so callers
    can always inspect health + notes even on failure.
    """
    base_url = _normalise_url(url)
    info = SiteInfo(url=url, site_type=SiteType.UNKNOWN,
                    health=HealthStatus.DEAD, base_url=base_url)

    try:
        start = time.monotonic()
        response = requests.get(base_url, headers=_HEADERS, timeout=_TIMEOUT,
                                allow_redirects=True)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        info.response_time_ms = elapsed_ms
        info.http_status = response.status_code

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        # Health
        info.has_cloudflare = _check_cloudflare(response, html)
        if info.has_cloudflare and response.status_code in (403, 503):
            info.health = HealthStatus.CLOUDFLARE_BLOCKED
            info.notes.append("Site is behind Cloudflare — extension will need CloudflareInterceptor")
        elif response.status_code == 429:
            info.health = HealthStatus.RATE_LIMITED
        elif response.status_code >= 400:
            info.health = HealthStatus.DEAD
            info.notes.append(f"HTTP {response.status_code} on homepage — site may be down")
            return info
        else:
            info.health = HealthStatus.ALIVE
            if info.has_cloudflare:
                info.notes.append("Cloudflare present but passable — extension may need CloudflareInterceptor")

        # Type detection
        site_type, features = _detect_type(html, base_url, soup)
        info.site_type = site_type
        info.features = features
        info.recommended_template = _TEMPLATE_MAP[site_type]
        info.name = _extract_site_name(soup, base_url)

        # Language hint from html[lang]
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            info.language = html_tag["lang"][:2].lower()

        # API probe
        if site_type in (SiteType.MADARA, SiteType.MANGA_READER):
            info.api_base = _probe_api_endpoints(base_url)
            if info.api_base:
                info.notes.append(f"REST API found at {info.api_base}")

        # Login wall
        login_signals = ["login", "sign-in", "register to read"]
        html_lower = html.lower()
        if sum(1 for sig in login_signals if sig in html_lower) >= 2:
            info.has_login_wall = True
            info.notes.append("Possible login wall — extension may need account handling")

        if site_type == SiteType.UNKNOWN:
            info.notes.append("Could not identify CMS — use http_source template and inspect manually")
        elif site_type == SiteType.MADARA:
            info.notes.append("Madara sites use POST /wp-admin/admin-ajax.php for chapter lists")
            info.notes.append("Chapter images are usually in .reading-content img[src]")

    except requests.exceptions.SSLError:
        info.health = HealthStatus.DEAD
        info.notes.append("SSL certificate error — site may have expired cert")
    except requests.exceptions.ConnectionError:
        info.health = HealthStatus.DEAD
        info.notes.append("Connection refused or DNS failure — site is likely down")
    except requests.exceptions.Timeout:
        info.health = HealthStatus.DEAD
        info.notes.append(f"Timed out after {_TIMEOUT}s — site may be very slow or down")
    except Exception as exc:
        info.health = HealthStatus.DEAD
        info.notes.append(f"Unexpected error: {exc}")

    return info
