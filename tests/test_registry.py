import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.registry.keiyoushi import normalize_host, find_coverage, covered_hosts


_FAKE_INDEX = [
    {"name": "Tachiyomi: Comix", "pkg": "eu.kanade.tachiyomi.extension.en.comix",
     "version": "1.4.27", "code": 27, "nsfw": 1, "lang": "en",
     "sources": [{"name": "Comix", "lang": "en", "id": "1", "baseUrl": "https://comix.to"}]},
    {"name": "MangaNow", "pkg": "eu.kanade.tachiyomi.extension.en.manganow",
     "version": "1.4.3", "code": 3, "nsfw": 0, "lang": "en",
     "sources": [{"name": "MangaNow", "lang": "en", "id": "2", "baseUrl": "https://manganow.to/"}]},
]


def test_normalize_host_strips_scheme_www_and_path():
    assert normalize_host("https://www.comix.to/title/x") == "comix.to"
    assert normalize_host("comix.to") == "comix.to"
    assert normalize_host("http://Manganow.TO:443/foo") == "manganow.to"
    assert normalize_host("") == ""


def test_find_coverage_matches_regardless_of_path_or_www():
    cov = find_coverage("https://www.comix.to/title/emqg8-solo-leveling", index=_FAKE_INDEX)
    assert len(cov) == 1
    assert cov[0].source_name == "Comix"
    assert cov[0].version == "1.4.27"
    # "Tachiyomi: " prefix stripped from ext_name.
    assert cov[0].ext_name == "Comix"


def test_find_coverage_matches_trailing_slash_baseurl():
    assert find_coverage("https://manganow.to", index=_FAKE_INDEX)


def test_find_coverage_empty_for_uncovered():
    assert find_coverage("https://totally-unknown-site.example", index=_FAKE_INDEX) == []


def test_covered_hosts_set():
    hosts = covered_hosts(index=_FAKE_INDEX)
    assert hosts == {"comix.to", "manganow.to"}


if __name__ == "__main__":
    for fn in [test_normalize_host_strips_scheme_www_and_path,
               test_find_coverage_matches_regardless_of_path_or_www,
               test_find_coverage_matches_trailing_slash_baseurl,
               test_find_coverage_empty_for_uncovered,
               test_covered_hosts_set]:
        fn()
        print(f"  PASS  {fn.__name__}")
    print("ok")
