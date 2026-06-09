import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from src.models.site_info import SiteInfo, SiteType, HealthStatus, DetectedFeature
from src.scaffolder.scaffolder import scaffold, _to_class_name, _to_package_name


def make_site_info(site_type=SiteType.MADARA, name="Test Manga", lang="en",
                   base_url="https://testmanga.com", cloudflare=False):
    return SiteInfo(
        url=base_url,
        site_type=site_type,
        health=HealthStatus.ALIVE,
        name=name,
        language=lang,
        base_url=base_url,
        has_cloudflare=cloudflare,
        recommended_template={
            SiteType.MADARA: "madara",
            SiteType.MANGADEX: "mangadex",
            SiteType.CUSTOM: "http_source",
            SiteType.UNKNOWN: "http_source",
            SiteType.WEBTOON: "webtoon",
        }.get(site_type, "http_source"),
    )


def test_creates_output_directory():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp)
        assert result.output_dir.exists()


def test_build_gradle_uses_keiyoushi_legacy_format():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp)
        gradle = result.output_dir / "build.gradle"
        assert gradle.exists()
        content = gradle.read_text()
        assert "TestManga" in content
        assert "extVersionCode" in content
        # Current keiyoushi format: legacy plugin, no pkgNameSuffix/common.gradle.
        assert 'apply plugin: "kei.plugins.extension.legacy"' in content
        assert "pkgNameSuffix" not in content
        assert "common.gradle" not in content


def test_no_hand_written_android_manifest():
    # The legacy plugin generates the manifest; we must NOT ship our own.
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp)
        assert not (result.output_dir / "AndroidManifest.xml").exists()


def test_launcher_icons_generated_for_all_densities():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp)
        for density in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
            icon = result.output_dir / "res" / f"mipmap-{density}" / "ic_launcher.png"
            assert icon.exists(), f"missing {density} icon"
            # Valid PNG signature.
            assert icon.read_bytes()[:8] == bytes.fromhex("89504e470d0a1a0a")


def test_kotlin_source_created():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp)
        kt_files = list(result.output_dir.rglob("*.kt"))
        assert len(kt_files) == 1
        content = kt_files[0].read_text()
        assert "TestManga" in content
        assert "Madara" in content


def test_http_source_template_for_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(SiteType.UNKNOWN), output_root=tmp)
        kt_files = list(result.output_dir.rglob("*.kt"))
        content = kt_files[0].read_text()
        assert "HttpSource" in content
        assert "TODO" in content


def test_cloudflare_interceptor_in_source():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(cloudflare=True), output_root=tmp)
        kt_files = list(result.output_dir.rglob("*.kt"))
        content = kt_files[0].read_text()
        assert "cloudflareClient" in content


def test_no_cloudflare_when_not_detected():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(cloudflare=False), output_root=tmp)
        kt_files = list(result.output_dir.rglob("*.kt"))
        content = kt_files[0].read_text()
        assert "cloudflareClient" not in content


def test_http_site_warns_about_cleartext():
    info = make_site_info(base_url="http://insecure-site.com")
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(info, output_root=tmp)
        assert any("cleartext" in w.lower() or "http" in w.lower()
                   for w in result.warnings)


def test_https_site_has_no_cleartext_warning():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp)
        assert not any("cleartext" in w.lower() for w in result.warnings)


def test_setup_md_created():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp)
        setup = result.output_dir / "SETUP.md"
        assert setup.exists()
        assert "gradlew" in setup.read_text()


def test_ext_id_format():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(name="CoolManga", lang="ja"), output_root=tmp)
        assert result.ext_id.startswith("eu.kanade.tachiyomi.extension.ja.")


def test_class_name_helpers():
    assert _to_class_name("my manga site") == "MyMangaSite"
    assert _to_class_name("MangaDex") == "Mangadex"
    assert _to_class_name("site-name_test") == "SiteNameTest"


def test_package_name_helpers():
    assert _to_package_name("My Manga Site") == "mymangasite"
    assert _to_package_name("MangaDex") == "mangadex"


def test_nsfw_flag_in_gradle():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold(make_site_info(), output_root=tmp, nsfw=True)
        content = (result.output_dir / "build.gradle").read_text()
        assert "isNsfw = true" in content


if __name__ == "__main__":
    tests = [
        test_creates_output_directory,
        test_build_gradle_uses_keiyoushi_legacy_format,
        test_no_hand_written_android_manifest,
        test_launcher_icons_generated_for_all_densities,
        test_kotlin_source_created,
        test_http_source_template_for_unknown,
        test_cloudflare_interceptor_in_source,
        test_no_cloudflare_when_not_detected,
        test_http_site_warns_about_cleartext,
        test_https_site_has_no_cleartext_warning,
        test_setup_md_created,
        test_ext_id_format,
        test_class_name_helpers,
        test_package_name_helpers,
        test_nsfw_flag_in_gradle,
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
