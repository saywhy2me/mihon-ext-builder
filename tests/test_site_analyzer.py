import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch, MagicMock
from src.analyzer.site_analyzer import analyze
from src.models.site_info import SiteType, HealthStatus


def _mock_response(html: str, status: int = 200, headers: dict = None, url: str = "https://example.com"):
    r = MagicMock()
    r.text = html
    r.status_code = status
    r.headers = headers or {"content-type": "text/html"}
    r.url = url
    return r


MADARA_HTML = """
<html lang="en">
<head><title>MangaSite | Read Manga Online</title>
<meta property="og:site_name" content="MangaSite" />
</head>
<body>
<link rel="stylesheet" href="/wp-content/themes/madara/style.css">
<div class="manga-chapters"></div>
<script src="/wp-content/plugins/madara/public/js/madara.js"></script>
</body></html>
"""

GENERIC_HTML = """
<html lang="en"><head><title>Some Site</title></head>
<body><div class="manga-info"><ul class="listing"></ul></div></body>
</html>
"""

CLOUDFLARE_HTML = """
<html><head><title>Just a moment...</title></head>
<body>Checking your browser before accessing</body></html>
"""

MANGADEX_HTML = """<html><head><title>MangaDex</title></head><body>MangaDex reader</body></html>"""


def test_madara_detected():
    with patch("requests.get", return_value=_mock_response(MADARA_HTML)):
        info = analyze("https://mangasite.com")
    assert info.site_type == SiteType.MADARA
    assert info.health == HealthStatus.ALIVE
    assert info.recommended_template == "madara"
    assert info.name == "MangaSite"


def test_mangadex_by_url():
    with patch("requests.get", return_value=_mock_response(MANGADEX_HTML, url="https://mangadex.org")):
        info = analyze("https://mangadex.org")
    assert info.site_type == SiteType.MANGADEX
    assert info.recommended_template == "mangadex"


def test_cloudflare_detected():
    with patch("requests.get", return_value=_mock_response(
        CLOUDFLARE_HTML, status=403, headers={"cf-ray": "abc123", "content-type": "text/html"}
    )):
        info = analyze("https://cf-blocked-site.com")
    assert info.has_cloudflare is True
    assert info.health == HealthStatus.CLOUDFLARE_BLOCKED


def test_dead_site_404():
    with patch("requests.get", return_value=_mock_response("Not Found", status=404)):
        info = analyze("https://dead-site.com")
    assert info.health == HealthStatus.DEAD


def test_generic_manga_reader():
    with patch("requests.get", return_value=_mock_response(GENERIC_HTML)):
        info = analyze("https://reader.com")
    assert info.site_type == SiteType.MANGA_READER
    assert info.health == HealthStatus.ALIVE


def test_connection_error_returns_dead():
    import requests as req
    with patch("requests.get", side_effect=req.exceptions.ConnectionError("refused")):
        info = analyze("https://offline-site.com")
    assert info.health == HealthStatus.DEAD
    assert any("Connection" in n for n in info.notes)


def test_timeout_returns_dead():
    import requests as req
    with patch("requests.get", side_effect=req.exceptions.Timeout("timeout")):
        info = analyze("https://slow-site.com")
    assert info.health == HealthStatus.DEAD
    assert any("Timed out" in n for n in info.notes)


def test_language_extracted():
    html = '<html lang="ja"><head><title>日本語サイト</title></head><body></body></html>'
    with patch("requests.get", return_value=_mock_response(html)):
        info = analyze("https://jp-site.com")
    assert info.language == "ja"


def test_summary_contains_key_fields():
    with patch("requests.get", return_value=_mock_response(MADARA_HTML)):
        info = analyze("https://mangasite.com")
    summary = info.summary()
    assert "madara" in summary
    assert "alive" in summary


if __name__ == "__main__":
    tests = [
        test_madara_detected,
        test_mangadex_by_url,
        test_cloudflare_detected,
        test_dead_site_404,
        test_generic_manga_reader,
        test_connection_error_returns_dead,
        test_timeout_returns_dead,
        test_language_extracted,
        test_summary_contains_key_fields,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
