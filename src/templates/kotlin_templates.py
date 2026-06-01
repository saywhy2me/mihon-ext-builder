"""Jinja2 template strings for Mihon extension Kotlin source files."""

# ── Madara (WordPress + Madara theme) ─────────────────────────────────────────
MADARA_KT = """\
package eu.kanade.tachiyomi.extension.{{ lang }}.{{ package_name }}

import eu.kanade.tachiyomi.multisrc.madara.Madara
{% if has_cloudflare %}
import eu.kanade.tachiyomi.network.interceptor.CloudflareInterceptor
import okhttp3.OkHttpClient
{% endif %}

class {{ class_name }} : Madara(
    "{{ site_name }}",
    "{{ base_url }}",
    "{{ lang }}",
) {
{% if has_cloudflare %}
    override val client: OkHttpClient = network.cloudflareClient
{% endif %}
{% if override_manga_url_directory %}
    // The URL path segment that identifies a manga page (e.g. "manga", "webtoon", "comic")
    override val mangaUrlDirectory = "manga"
{% endif %}
{% if nsfw %}
    override val filterNsfwContent = false
{% endif %}
    // ── Optional overrides ────────────────────────────────────────────────
    // Uncomment and adjust if the default Madara parsing breaks:
    //
    // override fun popularMangaSelector() = "div.page-item-detail"
    // override fun searchMangaSelector() = "div.c-tabs-item__content"
    // override fun chapterListSelector() = "li.wp-manga-chapter"
    // override fun pageListParse(document: Document): List<Page> { ... }
}
"""

# ── Plain HttpSource (no known CMS) ───────────────────────────────────────────
HTTP_SOURCE_KT = """\
package eu.kanade.tachiyomi.extension.{{ lang }}.{{ package_name }}

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.HttpSource
import okhttp3.Request
import okhttp3.Response
import org.jsoup.Jsoup
{% if has_cloudflare %}
import okhttp3.OkHttpClient
{% endif %}

class {{ class_name }} : HttpSource() {

    override val name = "{{ site_name }}"
    override val baseUrl = "{{ base_url }}"
    override val lang = "{{ lang }}"
    override val supportsLatest = true
{% if has_cloudflare %}

    override val client: OkHttpClient = network.cloudflareClient
{% endif %}

    // ── Popular manga ─────────────────────────────────────────────────────

    override fun popularMangaRequest(page: Int): Request {
        return GET("$baseUrl/manga/?page=$page", headers)
    }

    override fun popularMangaParse(response: Response): MangasPage {
        val document = Jsoup.parse(response.body.string())
        val mangas = document.select("TODO: selector for manga cards").map { el ->
            SManga.create().apply {
                title = el.select("TODO: title selector").text()
                setUrlWithoutDomain(el.select("a").attr("href"))
                thumbnail_url = el.select("img").attr("src")
            }
        }
        val hasNextPage = document.select("TODO: next page selector").isNotEmpty()
        return MangasPage(mangas, hasNextPage)
    }

    // ── Latest manga ──────────────────────────────────────────────────────

    override fun latestUpdatesRequest(page: Int): Request {
        return GET("$baseUrl/manga/?page=$page&order=update", headers)
    }

    override fun latestUpdatesParse(response: Response) = popularMangaParse(response)

    // ── Search ────────────────────────────────────────────────────────────

    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
        return GET("$baseUrl/?s=$query&page=$page", headers)
    }

    override fun searchMangaParse(response: Response) = popularMangaParse(response)

    // ── Manga details ─────────────────────────────────────────────────────

    override fun mangaDetailsParse(response: Response): SManga {
        val document = Jsoup.parse(response.body.string())
        return SManga.create().apply {
            title = document.select("TODO: title").text()
            author = document.select("TODO: author").text()
            description = document.select("TODO: synopsis").text()
            thumbnail_url = document.select("TODO: cover img").attr("src")
            status = when (document.select("TODO: status").text().lowercase()) {
                "ongoing" -> SManga.ONGOING
                "completed" -> SManga.COMPLETED
                else -> SManga.UNKNOWN
            }
        }
    }

    // ── Chapter list ──────────────────────────────────────────────────────

    override fun chapterListParse(response: Response): List<SChapter> {
        val document = Jsoup.parse(response.body.string())
        return document.select("TODO: chapter list selector").map { el ->
            SChapter.create().apply {
                name = el.select("TODO: chapter name").text()
                setUrlWithoutDomain(el.select("a").attr("href"))
            }
        }
    }

    // ── Page list ─────────────────────────────────────────────────────────

    override fun pageListParse(response: Response): List<Page> {
        val document = Jsoup.parse(response.body.string())
        return document.select("TODO: image selectors").mapIndexed { i, el ->
            Page(i, imageUrl = el.attr("src").ifEmpty { el.attr("data-src") })
        }
    }

    override fun imageUrlParse(response: Response) = ""

    override fun getFilterList() = FilterList()
}
"""

# ── MangaDex API source ────────────────────────────────────────────────────────
MANGADEX_KT = """\
package eu.kanade.tachiyomi.extension.{{ lang }}.{{ package_name }}

// MangaDex is already included in Mihon as a built-in source.
// If you want a custom MangaDex variant, extend the existing MangaDex source:

// import eu.kanade.tachiyomi.extension.all.mangadex.MangaDex
//
// class {{ class_name }}Custom : MangaDex() {
//     override val lang = "{{ lang }}"
// }

// For a brand-new MangaDex-API-compatible site, use HttpSource and call:
//   GET https://api.mangadex.org/manga?...
// See: https://api.mangadex.org/docs/

class {{ class_name }}Placeholder {
    // Replace this file with a real HttpSource implementation targeting the API.
    // The MangaDex OpenAPI spec is at https://api.mangadex.org/docs/swagger.html
}
"""

# ── Webtoon / vertical strip ──────────────────────────────────────────────────
WEBTOON_KT = """\
package eu.kanade.tachiyomi.extension.{{ lang }}.{{ package_name }}

import eu.kanade.tachiyomi.multisrc.webtoons.Webtoons
{% if has_cloudflare %}
import okhttp3.OkHttpClient
{% endif %}

class {{ class_name }} : Webtoons(
    "{{ site_name }}",
    "{{ base_url }}",
    "{{ lang }}",
) {
{% if has_cloudflare %}
    override val client: OkHttpClient = network.cloudflareClient
{% endif %}
    // Webtoons multisrc handles vertical strip pagination automatically.
    // Override if the chapter URL structure differs:
    // override fun chapterListSelector() = "li._episodeItem"
    // override fun pageListParse(document: Document): List<Page> { ... }
}
"""

TEMPLATE_MAP = {
    "madara":       MADARA_KT,
    "http_source":  HTTP_SOURCE_KT,
    "mangadex":     MANGADEX_KT,
    "manga_reader": HTTP_SOURCE_KT,
    "webtoon":      WEBTOON_KT,
    "comick":       HTTP_SOURCE_KT,
}
