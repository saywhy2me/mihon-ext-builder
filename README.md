# Mihon Extension Builder

A developer tool for creating and maintaining extensions for [Mihon](https://mihon.app) (the Tachiyomi fork). Instead of reading through HTML manually to figure out why an extension broke, this tool analyzes a manga source website, identifies its CMS type, tests its CSS selectors, and generates a ready-to-build Kotlin/Gradle extension project.

---

## The Problem It Solves

Mihon extensions break frequently because manga websites change their HTML structure without warning. When that happens:

- The manga list stops loading
- Chapter lists go blank
- Images fail to appear

Finding the broken selector and knowing what to replace it with currently requires manually fetching pages, reading raw HTML, and understanding the site's specific CMS. This tool automates that workflow.

---

## Features

| Feature | Description |
|---|---|
| **Site Analyzer** | Fetches a URL and fingerprints the CMS type (Madara, MangaNow, MangaDex, etc.) |
| **Health Checker** | Tests known CSS selectors page-by-page and reports exactly what broke |
| **Extension Scaffolder** | Generates a complete Kotlin/Gradle project ready to drop into mihon-extensions |
| **Template Library** | Pre-built Kotlin source templates per site type with CloudflareInterceptor wired where needed |

---

## Supported Site Types

| Type | Detection method | Template |
|---|---|---|
| **Madara** | `wp-content/themes/madara`, `wp-manga`, `manga-chapters` | `Madara()` multisrc subclass |
| **MangaNow.to** | `anisc-detail`, `manga_list-sbs`, `reading-item chapter-item` | Full `HttpSource` (verified live) |
| **MangaDex** | Domain match `mangadex.org` | Placeholder + API docs pointer |
| **ComicK** | Domain match `comick.io / comick.app` | `HttpSource` |
| **Manga Reader** | `manga-info`, `listing`, `manga-chapters-holder` | `HttpSource` |
| **Webtoon** | `viewer-cont`, `data-episode`, `manhwa` | `Webtoons()` multisrc subclass |
| **Custom / Unknown** | Fallback | `HttpSource` with TODO placeholders |

---

## Get an APK with zero setup (GitHub Actions)

**The easiest path of all — no Python, no install, nothing on your computer.**

1. Open this repository on GitHub and click the **Actions** tab.
2. Select **"Build Extension APK"** in the left sidebar.
3. Click **Run workflow**, paste the manga site URL (e.g. `https://manganow.to`), and run it.
4. When the run finishes (a few minutes), open it and download the **APK** from the **Artifacts** section at the bottom.
5. Install the APK on your device and add it in Mihon.

That's it — the workflow fingerprints the site, generates the extension, compiles it, and hands you an installable APK.

> Sites with an unknown/custom layout may need their `TODO:` selectors filled in before they compile — the run logs will say so. Known site types (MangaNow, Madara, Webtoon, etc.) build as-is.

---

## Quick Start (local, easiest)

**You only need [Python 3.11+](https://www.python.org/downloads/) installed.** Download this project, then:

| Your computer | What to do |
|---|---|
| **Windows** | Double-click **`run.bat`** |
| **macOS / Linux** | Run **`./run.sh`** in a terminal (`chmod +x run.sh` the first time) |

The launcher sets up everything automatically on first run (it creates an isolated environment and installs dependencies — no `pip` commands to type), then opens an **interactive wizard**:

```
  ==================================================
           Mihon Extension Builder - Wizard
  ==================================================

  Manga site URL: manganow.to

    Detected type : manganow
    Health        : alive
    Confidence    : 80%
    Template      : manganow

  Generate the extension project now? [Y/n]: y
  Output folder [generated]:
  Mark this extension as NSFW (adult content)? [y/N]: n

  [OK] Extension generated: generated\en.manganow
```

Just paste a website URL and answer a few questions — the wizard fingerprints the
site, generates the extension project, and (optionally) tests its selectors live.
When it finishes, open the generated folder and follow its **`SETUP.md`** to build
the installable APK.

> You can launch the wizard manually any time with `python main.py` (no arguments)
> or `python main.py wizard`.

---

## Manual Installation (advanced)

```bash
git clone https://github.com/saywhy2me/mihon-ext-builder.git
cd mihon-ext-builder
pip install -r requirements.txt
```

**Python 3.11+ required.**

---

## Usage (CLI)

Beyond the wizard, the `main.py` command-line interface exposes three commands for scripting — `analyze`, `scaffold`, and `check`.

```bash
python main.py --help          # list commands
python main.py COMMAND --help  # flags for a specific command
```

### `analyze` — fingerprint a site

```bash
python main.py analyze https://manganow.to
```

```
  Name       : MangaNow
  Type       : manganow
  Health     : alive
  Confidence : 80%
  Template   : manganow
  Cloudflare : yes
  Response   : 619ms
```

| Flag | Description |
|---|---|
| `--json` | Emit the result as JSON instead of the formatted report. |

Exits non-zero if the site is detected as **dead**.

### `scaffold` — generate an extension project

```bash
python main.py scaffold https://manganow.to -o generated
```

| Flag | Description |
|---|---|
| `-o, --output DIR` | Parent directory for the generated project (default `generated`). |
| `--lang CODE` | Language code override (e.g. `en`, `ja`, `zh`). Auto-detected otherwise. |
| `--class-name NAME` | Override the generated Kotlin class name. |
| `--nsfw` | Mark the extension NSFW in `build.gradle`. |
| `--version-code N` | Initial `extVersionCode` (default `1`). |
| `--skip-analyze` | Skip live analysis and use the generic `http_source` template (offline). |

### `check` — health-check a live extension

```bash
# full check (manga + chapter pages)
python main.py check https://manganow.to \
  -m /manga/noblesse \
  -c /manga/noblesse/chapter-1

# homepage-only quick check
python main.py check https://manganow.to --quick
```

| Flag | Description |
|---|---|
| `-m, --manga PATH` | Path to a manga detail page (e.g. `/manga/noblesse`). |
| `-c, --chapter PATH` | Path to a chapter page. |
| `--site-type TYPE` | Force a selector profile (`madara`, `manganow`, …). Auto-detected otherwise. |
| `-o, --output FILE` | Save the plain-text report to a file. |
| `--quick` | Homepage-only check (no `--manga`/`--chapter` needed). |

Exits non-zero when one or more selectors fail, so it works in CI.

---

## Usage (Python API)

### 1. Analyze a site

Fingerprints the CMS type, health, Cloudflare status, and recommended template.

```python
from src.analyzer.site_analyzer import analyze

info = analyze("https://manganow.to")
print(info.summary())
```

```
URL          : https://manganow.to
Type         : manganow
Health       : alive
Confidence   : 80%
Template     : manganow
Cloudflare   : yes
Response     : 619ms
Notes:
  - Cloudflare present but passable — extension may need CloudflareInterceptor
```

---

### 2. Scaffold an extension project

Takes the `SiteInfo` from the analyzer and generates a complete Kotlin/Gradle extension tree.

```python
from src.scaffolder.scaffolder import scaffold

result = scaffold(info, output_root="generated/")
print(result.summary())
```

**Generated structure:**

```
generated/en.manganow/
├── build.gradle              ← extName, pkgNameSuffix, extClass, versionCode
├── AndroidManifest.xml       ← Mihon metadata tags + source domain
├── SETUP.md                  ← Step-by-step build + adb install guide
└── src/
    └── eu/kanade/tachiyomi/extension/en/manganow/
        └── Manganow.kt       ← Full HttpSource implementation
```

**Options:**

```python
scaffold(
    info,
    output_root="generated/",
    nsfw=False,           # adds isNsfw = true to build.gradle
    version_code=1,       # extVersionCode in build.gradle
    override_lang="en",   # override detected language
    override_class_name="MyCustomSource",
)
```

---

### 3. Check a live extension's selectors

Tests CSS selectors against a live site and reports exactly what broke, with suggestions.

```python
from src.checker.health_checker import check_extension

report = check_extension(
    "https://manganow.to",
    site_type="manganow",
    manga_path="/manga/noblesse",
    chapter_path="/manga/noblesse/chapter-1",
)
print(report.format())
```

```
==============================================================
  EXTENSION HEALTH REPORT
==============================================================
  Site     : https://manganow.to
  Type     : manganow
  Passing  : 7
  Failing  : 1
  Status   : NEEDS UPDATE

[Manga Detail] https://manganow.to/manga/noblesse
  [OK]     Title (h2)                     h2.manga-name  (1 matches)
  [OK]     Cover image                    div.anisc-poster img  (1 matches)
  [EMPTY]  Chapter items                  li.item.reading-item.chapter-item
           HINT: Found <li> with classes: ['item', 'item-chapter']
==============================================================
```

The `HINT` line shows the actual class found in the DOM — fixing the selector is a one-line change.

**Quick check (homepage only):**

```python
from src.checker.health_checker import quick_check

report = quick_check("https://manganow.to", site_type="manganow")
```

---

## MangaNow.to Specific Notes

MangaNow.to was analyzed and verified live (2026-05-31).

| Page | Key selectors |
|---|---|
| Listing (`/az-list?page=N`) | `div.item.item-spc` → link, img, title |
| Latest (`/latest-updated?page=N`) | Same structure |
| Manga detail | `h2.manga-name`, `div.anisc-poster img`, `div.genres a`, `li.item.reading-item.chapter-item` |
| Chapter page | **Images are JavaScript-rendered** — the template uses regex to parse embedded `<script>` data |

Because chapter images load via JavaScript, the extension includes a two-step fallback:
1. Try static `<img src>` tags in the reading container
2. Extract image URLs from embedded `<script>` blocks using a regex pattern

If the image pattern changes, inspect the chapter page source and update the regex in `pageListParse`.

---

## Project Structure

```
mihon-ext-builder/
├── main.py                            # CLI entry point (analyze / scaffold / check)
├── requirements.txt
├── src/
│   ├── analyzer/
│   │   └── site_analyzer.py          # CMS fingerprinting, Cloudflare detection, API probing
│   ├── checker/
│   │   └── health_checker.py         # Per-selector health reports (Madara + MangaNow profiles)
│   ├── models/
│   │   └── site_info.py              # SiteInfo, SiteType, HealthStatus dataclasses
│   ├── scaffolder/
│   │   └── scaffolder.py             # Kotlin/Gradle project generator
│   └── templates/
│       └── kotlin_templates.py       # Jinja2 Kotlin source templates per site type
└── tests/
    ├── test_site_analyzer.py         # 9 tests (mocked HTTP)
    ├── test_scaffolder.py            # 14 tests
    └── test_health_checker.py        # 9 tests
```

---

## Running Tests

All 32 tests are offline (mocked HTTP) — no live internet connection needed.

```bash
python tests/test_site_analyzer.py
python tests/test_scaffolder.py
python tests/test_health_checker.py
```

---

## Building the Generated Extension

After scaffolding:

```bash
# 1. Clone the mihon-extensions source repo
git clone https://github.com/mihonapp/extensions-source.git
cd extensions-source

# 2. Copy the generated extension into the repo
cp -r generated/en.manganow/ src/en/manganow/

# 3. Build the APK
./gradlew :en:manganow:assembleDebug

# 4. Install on device
adb install -r src/en/manganow/build/outputs/apk/debug/*.apk
```

Or sideload by placing the APK at a URL and adding it as an extension repo in Mihon.

---

## Roadmap

See [PROGRESS.md](PROGRESS.md) for the detailed development log.

### Done
- [x] Site analyzer — CMS fingerprinting (Madara, MangaNow, MangaDex, ComicK, Webtoon, generic)
- [x] Extension scaffolder — generates build.gradle, AndroidManifest.xml, Kotlin source, SETUP.md
- [x] Template library — Madara, HttpSource, Webtoon, MangaDex, MangaNow.to
- [x] Health checker — per-selector OK/EMPTY/BROKEN reports with fix hints
- [x] MangaNow.to full compatibility (live-verified selectors + JS image fallback)
- [x] CLI entry point (`main.py`) — `analyze`, `scaffold`, `check` commands with flags

### Next Up
- [ ] Bulk health scan — check a list of extension URLs from a JSON/CSV manifest
- [ ] Additional site profiles — add selector profiles for popular sites (e.g. MangaKakalot, MangaSee)
- [ ] Update assistant — diff current selectors against live site and suggest which lines to change
- [ ] PDF/HTML report export — save health check results to a formatted report file

---

## Design Notes

- **No browser required** — the analyzer and checker work from static HTML only; no Playwright/Selenium dependency
- **Offline tests** — all 32 tests mock HTTP, so the test suite runs without internet access
- **Cloudflare-aware** — detected automatically; `cloudflareClient` is wired into Kotlin templates when needed
- **Chapter images caveat** — sites that render images via JavaScript (like MangaNow.to) require script-parsing in the extension; the template handles this with a regex fallback
