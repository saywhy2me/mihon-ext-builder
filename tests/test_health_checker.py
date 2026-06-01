import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch, MagicMock
from src.checker.health_checker import (
    check_extension, quick_check, CheckStatus, HealthReport
)

_MADARA_HOME_HTML = """
<html><body>
  <div class="page-item-detail">
    <div class="post-title"><h3><a href="/manga/test">Test Manga</a></h3></div>
    <div class="item-thumb"><img src="/covers/test.jpg" /></div>
  </div>
</body></html>
"""

_MADARA_DETAIL_HTML = """
<html><body>
  <div class="post-title"><h1>My Manga Title</h1></div>
  <div class="summary_image"><img src="/cover.jpg" /></div>
  <div class="author-content"><a href="#">Author Name</a></div>
  <div class="description-summary"><div class="summary__content">A great story.</div></div>
  <div class="summary-content">
    <div class="post-status"><div class="summary-content">Ongoing</div></div>
  </div>
  <div class="genres-content"><a>Action</a><a>Drama</a></div>
  <div class="listing-chapters_wrap">
    <li class="wp-manga-chapter"><a href="/ch-1">Chapter 1</a></li>
  </div>
</body></html>
"""

_CHAPTER_HTML = """
<html><body>
  <div class="reading-content">
    <img src="https://cdn.example.com/page1.jpg" />
    <img data-src="https://cdn.example.com/page2.jpg" />
  </div>
</body></html>
"""

_BROKEN_HTML = """<html><body><p>This site has totally changed its structure.</p></body></html>"""


def _mock(html, status=200):
    r = MagicMock()
    r.text = html
    r.status_code = status
    r.headers = {"content-type": "text/html"}
    return r


def test_healthy_madara_homepage():
    with patch("requests.get", return_value=_mock(_MADARA_HOME_HTML)):
        report = quick_check("https://mangasite.com", site_type="madara")
    assert report.total_ok >= 2
    assert report.total_broken == 0
    assert report.is_healthy


def test_broken_selectors_reported():
    with patch("requests.get", return_value=_mock(_BROKEN_HTML)):
        report = quick_check("https://mangasite.com", site_type="madara")
    assert report.total_broken > 0
    assert not report.is_healthy


def test_manga_detail_checks():
    def side_effect(url, **kwargs):
        if "/manga/" in url:
            return _mock(_MADARA_DETAIL_HTML)
        return _mock(_MADARA_HOME_HTML)

    with patch("requests.get", side_effect=side_effect):
        report = check_extension("https://mangasite.com", site_type="madara",
                                 manga_path="/manga/test-title")
    assert len(report.pages) == 2
    detail_page = report.pages[1]
    ok_names = [c.name for c in detail_page.checks if c.status == CheckStatus.OK]
    assert "Manga title" in ok_names


def test_chapter_page_checks():
    def side_effect(url, **kwargs):
        if "chapter" in url:
            return _mock(_CHAPTER_HTML)
        return _mock(_MADARA_HOME_HTML)

    with patch("requests.get", side_effect=side_effect):
        report = check_extension("https://mangasite.com", site_type="madara",
                                 chapter_path="/manga/test/chapter-1")
    chapter_page = report.pages[-1]
    assert any(c.status == CheckStatus.OK for c in chapter_page.checks)


def test_dead_site_reported():
    import requests as req
    with patch("requests.get", side_effect=req.exceptions.ConnectionError("refused")):
        report = quick_check("https://dead.com")
    assert report.pages[0].error is not None
    assert report.pages[0].http_status is None


def test_404_reported():
    with patch("requests.get", return_value=_mock("Not Found", status=404)):
        report = quick_check("https://gone.com")
    assert report.pages[0].http_status == 404
    assert report.pages[0].error is not None


def test_format_output_contains_key_sections():
    with patch("requests.get", return_value=_mock(_MADARA_HOME_HTML)):
        report = quick_check("https://mangasite.com", site_type="madara")
    text = report.format()
    assert "EXTENSION HEALTH REPORT" in text
    assert "Homepage" in text
    assert "[OK]" in text or "[EMPTY]" in text


def test_no_chapter_page_when_path_not_given():
    with patch("requests.get", return_value=_mock(_MADARA_HOME_HTML)):
        report = check_extension("https://mangasite.com", site_type="madara")
    assert all(p.page_name != "Chapter Page" for p in report.pages)


def test_selector_sample_text_captured():
    with patch("requests.get", return_value=_mock(_MADARA_HOME_HTML)):
        report = quick_check("https://mangasite.com", site_type="madara")
    ok_checks = [c for p in report.pages for c in p.checks if c.status == CheckStatus.OK]
    assert any(c.sample_text for c in ok_checks)


if __name__ == "__main__":
    tests = [
        test_healthy_madara_homepage,
        test_broken_selectors_reported,
        test_manga_detail_checks,
        test_chapter_page_checks,
        test_dead_site_reported,
        test_404_reported,
        test_format_output_contains_key_sections,
        test_no_chapter_page_when_path_not_given,
        test_selector_sample_text_captured,
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
