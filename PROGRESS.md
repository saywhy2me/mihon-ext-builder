# Development Progress

## Status: Active — 4/5 core modules complete

---

## Completed

### Iteration 1 — Site Analyzer (commit `d4d3084`)
**Date:** 2026-05-31

Built the core fingerprinting engine that fetches a manga source URL and identifies what CMS it runs on.

**Files:**
- `src/models/site_info.py` — `SiteInfo`, `SiteType`, `HealthStatus`, `DetectedFeature` dataclasses
- `src/analyzer/site_analyzer.py` — CMS detection, Cloudflare check, API probing, site name/language extraction

**Detection signals implemented:**
| Type | Signal method |
|---|---|
| Madara | `wp-content/themes/madara`, `wp-manga`, `manga-chapters` HTML signatures |
| MangaDex | Domain match `mangadex.org` |
| ComicK | Domain match `comick.io / comick.app` |
| Manga Reader | `manga-info`, `listing`, `manga-chapters-holder` HTML signatures |
| Webtoon | `viewer-cont`, `data-episode`, `manhwa` HTML signatures |
| MangaNow.to | `anisc-detail`, `manga_list-sbs`, `reading-item chapter-item` HTML signatures |

**Key design decisions:**
- Tolerant matching — signals checked case-insensitively against the full HTML source
- Cloudflare detected from both HTTP response headers (`cf-ray`) and HTML body (`just a moment`)
- API endpoint probing for WP-JSON and Madara AJAX endpoints
- Returns a `SiteInfo` even on connection failure (so callers can always inspect health + notes)

**Tests:** 9/9 passing (all mocked — no live HTTP needed)

---

### Iteration 2 — Extension Scaffolder (commit `c38f377`)
**Date:** 2026-05-31

Takes a `SiteInfo` and generates a complete Kotlin/Android project structure matching the mihon-extensions repository layout.

**Files:**
- `src/scaffolder/scaffolder.py` — project generator
- `src/templates/kotlin_templates.py` — Jinja2 Kotlin source templates

**Generated files per extension:**
| File | Purpose |
|---|---|
| `build.gradle` | `extName`, `pkgNameSuffix`, `extClass`, `extVersionCode`, `isNsfw` |
| `AndroidManifest.xml` | Mihon metadata tags, source domain declaration |
| `{ClassName}.kt` | Full Kotlin source (template-filled) |
| `SETUP.md` | Step-by-step build + adb install instructions |
| `res/xml/network_security_config.xml` | Auto-generated for HTTP (non-HTTPS) sources only |

**Templates implemented:**
| Template key | Kotlin base class | When used |
|---|---|---|
| `madara` | `Madara(...)` | WordPress + Madara theme sites |
| `webtoon` | `Webtoons(...)` | Vertical strip / manhwa sites |
| `manganow` | `HttpSource()` | MangaNow.to (full impl, live-verified) |
| `http_source` | `HttpSource()` | Generic / unknown sites (TODO stubs) |
| `mangadex` | Comment + API pointer | MangaDex variants |

**Key design decisions:**
- `CloudflareInterceptor` wired into `client` automatically when Cloudflare is detected
- Class name and package name derived from site name (`"My Manga Site"` → `MyMangaSite` / `mymangasite`)
- Both are overridable via `override_class_name` and `override_lang` params
- `network_security_config.xml` generated automatically for `http://` sources

**Tests:** 14/14 passing

---

### Iteration 3 — Health Checker (commit `a60f251`)
**Date:** 2026-05-31

Tests CSS selectors against a live site page-by-page and reports exactly what works, what returns nothing, and what throws errors — so developers know precisely which lines to fix.

**File:** `src/checker/health_checker.py`

**Check flow:**
1. Fetch homepage → test popular manga selectors
2. Fetch manga detail page (if path provided) → test title, cover, genres, chapter list selectors
3. Fetch chapter page (if path provided) → test image container selectors

**Status per selector:**
| Status | Meaning |
|---|---|
| `[OK]` | Selector matched — shows match count and sample text |
| `[EMPTY]` | Selector present in parser but matched nothing — shows DOM hint |
| `[BROKEN]` | Exception during check |

**DOM hints:** When a selector returns empty, the checker looks for the same HTML tag with different classes and surfaces them as `HINT: Found <li> with classes: [...]` — so the fix is usually a one-line change.

**Selector profiles:**
- `madara` — mirrors the defaults of the Madara multisrc library
- `manganow` — verified live against manganow.to (2026-05-31)
- `generic` — fallback for unknown site types

**Tests:** 9/9 passing

---

### MangaNow.to Compatibility (commit `48293e3`)
**Date:** 2026-05-31 (added on request during development)

Live analysis performed against `https://manganow.to` to produce verified selectors.

**What was discovered:**
| Finding | Detail |
|---|---|
| Site type | Custom CMS (not Madara) |
| Cloudflare | Present but passable |
| Homepage | JavaScript-rendered — only nav in initial HTML |
| Listing pages | `/az-list`, `/type/manga`, `/genre/*` → server-side rendered |
| Manga detail | Server-side rendered, full selector set available |
| Chapter images | **JavaScript-rendered** — not in initial HTML |

**Verified selectors:**
| Selector name | CSS selector |
|---|---|
| Manga cards | `div.item.item-spc` |
| Manga link | `div.item.item-spc a[href*='/manga/']` |
| Cover (listing) | `div.item.item-spc img[src]` |
| Title (detail) | `h2.manga-name` |
| Cover (detail) | `div.anisc-poster img, div.manga-poster img` |
| Description | `div.anisc-detail div.description` |
| Genres | `div.anisc-detail div.genres a` |
| Status | `div.anisc-info div.item.item-title span.name` |
| Chapter items | `li.item.reading-item.chapter-item` |
| Chapter link | `li.item.reading-item.chapter-item a[href*='/manga/']` |
| Pagination | `a.page-link[href*='page=']` |

**Chapter image workaround:**
Images load via JavaScript after page render. The `Manganow.kt` template includes:
1. A static `<img src>` check (works if site ever adds SSR)
2. A regex fallback that extracts image URLs from embedded `<script>` tags matching `.jpg/.png/.webp`

If this regex stops working, inspect the chapter page source for the updated JS data pattern.

---

## In Progress / Planned

### Iteration 4 — CLI Entry Point
**Priority: High**

Add `main.py` with `click`-powered commands so the tool is usable without writing Python:

```bash
python main.py analyze https://mangasite.com
python main.py scaffold https://mangasite.com --output generated/ --lang en
python main.py check https://mangasite.com --manga /manga/some-title --chapter /manga/some-title/ch-1
```

**Planned flags:**
| Command | Key flags |
|---|---|
| `analyze` | `--json` for machine-readable output |
| `scaffold` | `--nsfw`, `--lang`, `--class-name`, `--output`, `--version-code` |
| `check` | `--manga`, `--chapter`, `--output` to save report, `--site-type` override |

---

### Iteration 5 — Bulk Health Scanner
**Priority: High**

Reads a JSON/CSV manifest of extension URLs and runs health checks on all of them, producing a summary of which extensions are alive, degraded, or dead.

```json
[
  {"name": "MangaSite A", "url": "https://a.com", "type": "madara", "manga": "/manga/test"},
  {"name": "MangaNow", "url": "https://manganow.to", "type": "manganow", "manga": "/manga/noblesse"}
]
```

Output: table + optional HTML report sorted by severity.

---

### Future — Additional Site Profiles
**Priority: Medium**

Add verified selector profiles for high-traffic sites:
- [ ] MangaKakalot / MangaNato (custom CMS)
- [ ] MangaSee / MangaLife (JavaScript-heavy)
- [ ] Bato.to (modern SPA)
- [ ] ReaperScans / AsuraScans (Madara variants with overrides)
- [ ] Webtoons.com (official, login-gated)

Each profile should include: homepage selectors, manga detail selectors, chapter image selectors, pagination pattern, and a note on any JS-rendering issues.

---

### Future — Update Assistant
**Priority: Medium**

Takes an existing `.kt` extension file and a live site, diffs the current selectors against the DOM, and generates a patch showing exactly which lines need changing:

```
SELECTOR DIFF — MangaSite.kt
  Line 42: chapterListSelector()
    Current : "li.wp-manga-chapter"
    Live DOM: "li.chapter-item"          ← UPDATE THIS
    Confidence: 94%
```

---

### Future — Report Export
**Priority: Low**

Save health check results as:
- Plain text (already supported via `report.format()`)
- HTML with colour-coded status table
- JSON for CI pipeline integration

---

## Test Coverage Summary

| Module | Tests | Status |
|---|---|---|
| Site analyzer | 9 | All passing |
| Scaffolder | 14 | All passing |
| Health checker | 9 | All passing |
| **Total** | **32** | **32/32** |

All tests are offline (mocked HTTP). Running `python tests/test_*.py` requires no internet connection.
