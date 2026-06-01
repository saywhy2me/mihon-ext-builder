"""Extension health checker.

Fetches key pages of a manga source and tests CSS selectors against the live
HTML. Reports which selectors still work, which return empty results, and which
are completely missing — so developers know exactly what to fix in an expired
or broken extension.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models.site_info import SiteType

_TIMEOUT = 15
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
}


# ── result types ──────────────────────────────────────────────────────────────

class CheckStatus(Enum):
    OK = "ok"               # Selector matched and returned non-empty content
    EMPTY = "empty"         # Selector exists in DOM but matched nothing
    BROKEN = "broken"       # Exception or HTTP error prevented the check
    SKIPPED = "skipped"     # Not applicable for this site type


@dataclass
class SelectorResult:
    name: str
    selector: str
    status: CheckStatus
    matched_count: int = 0
    sample_text: Optional[str] = None
    suggestion: Optional[str] = None

    def icon(self) -> str:
        return {"ok": "[OK]", "empty": "[EMPTY]", "broken": "[BROKEN]", "skipped": "[SKIP]"}[self.status.value]


@dataclass
class PageCheckResult:
    page_name: str
    url: str
    http_status: Optional[int]
    response_time_ms: Optional[int]
    checks: list[SelectorResult] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.OK)

    @property
    def broken_count(self) -> int:
        return sum(1 for c in self.checks if c.status in (CheckStatus.EMPTY, CheckStatus.BROKEN))


@dataclass
class HealthReport:
    base_url: str
    site_type: str
    pages: list[PageCheckResult] = field(default_factory=list)

    @property
    def total_ok(self) -> int:
        return sum(p.ok_count for p in self.pages)

    @property
    def total_broken(self) -> int:
        return sum(p.broken_count for p in self.pages)

    @property
    def is_healthy(self) -> bool:
        return self.total_broken == 0

    def format(self) -> str:
        lines = [
            "=" * 62,
            "  EXTENSION HEALTH REPORT",
            "=" * 62,
            f"  Site     : {self.base_url}",
            f"  Type     : {self.site_type}",
            f"  Passing  : {self.total_ok}",
            f"  Failing  : {self.total_broken}",
            f"  Status   : {'HEALTHY' if self.is_healthy else 'NEEDS UPDATE'}",
            "=" * 62,
        ]
        for page in self.pages:
            status_str = f"HTTP {page.http_status}" if page.http_status else "ERROR"
            rt = f" ({page.response_time_ms}ms)" if page.response_time_ms else ""
            lines.append(f"\n[{page.page_name}] {page.url}")
            lines.append(f"  {status_str}{rt}")
            if page.error:
                lines.append(f"  ERROR: {page.error}")
                continue
            for c in page.checks:
                line = f"  {c.icon()}  {c.name:<30} {c.selector}"
                if c.status == CheckStatus.OK:
                    line += f"  ({c.matched_count} matches)"
                    if c.sample_text:
                        line += f'  sample="{c.sample_text[:40]}"'
                elif c.status == CheckStatus.EMPTY:
                    line += "  <- EMPTY"
                    if c.suggestion:
                        line += f"  HINT: {c.suggestion}"
                lines.append(line)
        lines.append("\n" + "=" * 62)
        return "\n".join(lines)


# ── known selector profiles ───────────────────────────────────────────────────

# These mirror the defaults used in the Madara multisrc library.
# If a site uses Madara but overrides these, the checker will report EMPTY.
_MADARA_SELECTORS = {
    "homepage": [
        ("Popular manga cards",       "div.page-item-detail"),
        ("Manga title (popular)",     "div.post-title h3 a, div.post-title h5 a"),
        ("Manga cover (popular)",     "div.item-thumb img"),
    ],
    "manga_detail": [
        ("Manga title",               "div.post-title h1, div.post-title h3"),
        ("Cover image",               "div.summary_image img"),
        ("Author",                    "div.author-content a"),
        ("Description",               "div.description-summary div.summary__content"),
        ("Status",                    "div.summary-content .post-status .summary-content"),
        ("Genres",                    "div.genres-content a"),
        ("Chapter list container",    "div.listing-chapters_wrap"),
        ("Chapter items",             "li.wp-manga-chapter"),
        ("Chapter link",              "li.wp-manga-chapter a"),
    ],
    "chapter_page": [
        ("Reading container",         "div.reading-content"),
        ("Page images",               "div.reading-content img"),
        ("Image src attribute",       "div.reading-content img[src]"),
        ("Lazy-load data-src",        "div.reading-content img[data-src]"),
    ],
}

_GENERIC_SELECTORS = {
    "homepage": [
        ("Manga links",               "a[href*='manga'], a[href*='comic']"),
        ("Manga images",              "img[src*='cover'], img[src*='thumb']"),
    ],
    "manga_detail": [
        ("Page title",                "h1, h2.title"),
        ("Description",               "div.description, div.summary, p.synopsis"),
        ("Chapter links",             "a[href*='chapter'], a[href*='ch-']"),
    ],
    "chapter_page": [
        ("Images",                    "img[src*='.jpg'], img[src*='.png'], img[src*='.webp']"),
        ("Lazy images",               "img[data-src], img[data-lazy-src]"),
    ],
}


# Selector profiles verified against live manganow.to (2026-05-31)
_MANGANOW_SELECTORS = {
    "homepage": [
        ("Manga cards (listing pages)",  "div.item.item-spc"),
        ("Manga link",                   "div.item.item-spc a[href*='/manga/']"),
        ("Cover image",                  "div.item.item-spc img[src]"),
        ("Manga title from alt",         "div.item.item-spc img[alt]"),
    ],
    "manga_detail": [
        ("Title (h2)",                   "h2.manga-name"),
        ("Alt title",                    "div.manga-name-or"),
        ("Cover image",                  "div.anisc-poster img, div.manga-poster img"),
        ("Description",                  "div.anisc-detail div.description"),
        ("Genres",                       "div.anisc-detail div.genres a"),
        ("Status",                       "div.anisc-info div.item.item-title span.name"),
        ("Chapter list container",       "div.tab-pane.active.show"),
        ("Chapter items",                "li.item.reading-item.chapter-item"),
        ("Chapter link",                 "li.item.reading-item.chapter-item a[href*='/manga/']"),
    ],
    "chapter_page": [
        # Images are JS-rendered on manganow.to — these selectors will show EMPTY
        # unless the extension parses the embedded JS data (see template notes)
        ("Reading container",            "div.page-layout.page-read"),
        ("Chapter nav prev",             "a.prev_chapter, a[href*='chapter-'][rel='prev']"),
        ("Chapter nav next",             "a.next_chapter, a[href*='chapter-'][rel='next']"),
    ],
}


def _get_selectors(site_type: str) -> dict:
    if site_type == "madara":
        return _MADARA_SELECTORS
    if site_type == "manganow":
        return _MANGANOW_SELECTORS
    return _GENERIC_SELECTORS


# ── HTTP fetcher ──────────────────────────────────────────────────────────────

def _fetch(url: str) -> tuple[Optional[BeautifulSoup], Optional[int], Optional[int], Optional[str]]:
    """Returns (soup, http_status, response_time_ms, error_message)."""
    try:
        start = time.monotonic()
        r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        elapsed = int((time.monotonic() - start) * 1000)
        if r.status_code >= 400:
            return None, r.status_code, elapsed, f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "lxml")
        return soup, r.status_code, elapsed, None
    except requests.exceptions.Timeout:
        return None, None, None, f"Timed out after {_TIMEOUT}s"
    except requests.exceptions.ConnectionError as e:
        return None, None, None, f"Connection error: {e}"
    except Exception as e:
        return None, None, None, str(e)


def _check_selector(soup: BeautifulSoup, name: str, selector: str) -> SelectorResult:
    try:
        elements = soup.select(selector)
        if not elements:
            # Try to suggest a nearby element
            tag = selector.split(" ")[-1].split("[")[0].split(".")[0].split("#")[0]
            similar = soup.find_all(tag) if tag else []
            suggestion = None
            if similar:
                classes = [" ".join(el.get("class", [])) for el in similar[:3] if el.get("class")]
                if classes:
                    suggestion = f'Found <{tag}> with classes: {classes}'
            return SelectorResult(name, selector, CheckStatus.EMPTY, suggestion=suggestion)

        sample = elements[0].get_text(strip=True)[:60] or elements[0].get("src", "")[:60]
        return SelectorResult(name, selector, CheckStatus.OK,
                              matched_count=len(elements), sample_text=sample)
    except Exception as e:
        return SelectorResult(name, selector, CheckStatus.BROKEN, suggestion=str(e))


# ── public API ────────────────────────────────────────────────────────────────

def check_extension(
    base_url: str,
    site_type: str = "madara",
    manga_path: Optional[str] = None,
    chapter_path: Optional[str] = None,
) -> HealthReport:
    """Run health checks against a live manga source.

    Args:
        base_url: Root URL of the source (e.g. 'https://mangasite.com').
        site_type: 'madara', 'manga_reader', 'webtoon', or 'custom'.
        manga_path: URL path to a specific manga detail page for deeper checks.
                    If None, only homepage checks run.
        chapter_path: URL path to a chapter page for image selector checks.
                      If None, chapter checks are skipped.

    Returns:
        HealthReport with all selector results.
    """
    base_url = base_url.rstrip("/")
    report = HealthReport(base_url=base_url, site_type=site_type)
    selectors = _get_selectors(site_type)

    # ── Homepage ──────────────────────────────────────────────────────────
    soup, status, rt, err = _fetch(base_url)
    page_result = PageCheckResult("Homepage", base_url, status, rt, error=err)
    if soup and not err:
        for name, selector in selectors.get("homepage", []):
            page_result.checks.append(_check_selector(soup, name, selector))
    report.pages.append(page_result)

    # ── Manga detail ──────────────────────────────────────────────────────
    if manga_path:
        manga_url = urljoin(base_url + "/", manga_path.lstrip("/"))
        soup, status, rt, err = _fetch(manga_url)
        page_result = PageCheckResult("Manga Detail", manga_url, status, rt, error=err)
        if soup and not err:
            for name, selector in selectors.get("manga_detail", []):
                page_result.checks.append(_check_selector(soup, name, selector))
        report.pages.append(page_result)

    # ── Chapter page ──────────────────────────────────────────────────────
    if chapter_path:
        chapter_url = urljoin(base_url + "/", chapter_path.lstrip("/"))
        soup, status, rt, err = _fetch(chapter_url)
        page_result = PageCheckResult("Chapter Page", chapter_url, status, rt, error=err)
        if soup and not err:
            for name, selector in selectors.get("chapter_page", []):
                page_result.checks.append(_check_selector(soup, name, selector))
        report.pages.append(page_result)

    return report


def quick_check(base_url: str, site_type: str = "madara") -> HealthReport:
    """Homepage-only health check — fast, no manga/chapter URLs needed."""
    return check_extension(base_url, site_type=site_type)
