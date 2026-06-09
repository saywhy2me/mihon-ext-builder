import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from unittest.mock import patch, MagicMock
import pytest
from click.testing import CliRunner
from main import cli
from src.models.site_info import SiteInfo, SiteType, HealthStatus, DetectedFeature
from src.registry.keiyoushi import Coverage


@pytest.fixture(autouse=True)
def _no_network_coverage(monkeypatch):
    """Default every test to 'not covered' so the coverage check stays offline.

    Tests that exercise coverage override main.find_coverage themselves.
    """
    monkeypatch.setattr("main.find_coverage", lambda url: [])


def _mock_coverage(name="Comix", version="1.4.27", lang="en"):
    return Coverage(ext_name=name, pkg=f"eu.kanade.tachiyomi.extension.{lang}.{name.lower()}",
                    version=version, version_code=27, nsfw=False,
                    source_name=name, base_url="https://comix.to", lang=lang)


def _mock_site_info(site_type=SiteType.MADARA, health=HealthStatus.ALIVE,
                    cloudflare=False, name="TestSite"):
    return SiteInfo(
        url="https://test.com",
        site_type=site_type,
        health=health,
        name=name,
        language="en",
        base_url="https://test.com",
        has_cloudflare=cloudflare,
        recommended_template={
            SiteType.MADARA: "madara",
            SiteType.MANGANOW: "manganow",
            SiteType.UNKNOWN: "http_source",
        }.get(site_type, "http_source"),
        features=[DetectedFeature("Test", 0.9, "mocked")],
    )


runner = CliRunner()


def test_analyze_basic_output():
    with patch("main.analyze", return_value=_mock_site_info()):
        result = runner.invoke(cli, ["analyze", "https://test.com"])
    assert result.exit_code == 0
    assert "TestSite" in result.output
    assert "madara" in result.output
    assert "alive" in result.output


def test_analyze_json_flag():
    with patch("main.analyze", return_value=_mock_site_info()):
        result = runner.invoke(cli, ["analyze", "https://test.com", "--json"])
    assert result.exit_code == 0
    import json
    # --json outputs pure JSON with no prefix line
    data = json.loads(result.output.strip())
    assert data["type"] == "madara"
    assert data["health"] == "alive"
    assert "template" in data


def test_analyze_dead_site_exits_1():
    with patch("main.analyze", return_value=_mock_site_info(health=HealthStatus.DEAD)):
        result = runner.invoke(cli, ["analyze", "https://dead.com"])
    assert result.exit_code == 1


def test_scaffold_creates_output():
    info = _mock_site_info()
    with patch("main.analyze", return_value=info):
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(cli, ["scaffold", "https://test.com", "--output", tmp])
    assert result.exit_code == 0
    assert "Extension generated" in result.output
    assert "ext_id" in result.output.lower() or "Extension ID" in result.output


def test_scaffold_skip_analyze():
    with tempfile.TemporaryDirectory() as tmp:
        result = runner.invoke(cli, [
            "scaffold", "https://test.com",
            "--skip-analyze", "--output", tmp
        ])
    assert result.exit_code == 0
    assert "http_source" in result.output or "Skipping" in result.output


def test_scaffold_json_output_for_ci():
    """--json must emit a pure-JSON contract the build workflow depends on."""
    import json
    info = _mock_site_info(site_type=SiteType.MANGANOW, name="MangaNow")
    with patch("main.analyze", return_value=info):
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(cli, ["scaffold", "https://manganow.to",
                                         "--output", tmp, "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)  # must parse with no extra prose
    assert data["lang"] == "en"
    assert data["package_name"] == "manganow"
    assert data["gradle_module"] == "src:en:manganow"
    assert data["ext_id"].endswith("en.manganow")
    assert "output_dir" in data and "warnings" in data


def test_analyze_reports_coverage_in_json():
    import json
    with patch("main.analyze", return_value=_mock_site_info()), \
         patch("main.find_coverage", return_value=[_mock_coverage()]):
        result = runner.invoke(cli, ["analyze", "https://comix.to", "--json"])
    data = json.loads(result.output)
    assert data["covered_by"]
    assert data["covered_by"][0]["name"] == "Comix"


def test_scaffold_skips_when_already_covered():
    with patch("main.find_coverage", return_value=[_mock_coverage()]):
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(cli, ["scaffold", "https://comix.to", "--output", tmp])
    assert result.exit_code == 0
    assert "already supported by keiyoushi" in result.output.lower()
    assert "Extension generated" not in result.output


def test_scaffold_force_overrides_coverage():
    info = _mock_site_info()
    with patch("main.find_coverage", return_value=[_mock_coverage()]), \
         patch("main.analyze", return_value=info):
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(cli, ["scaffold", "https://comix.to",
                                         "--output", tmp, "--force"])
    assert result.exit_code == 0
    assert "Extension generated" in result.output


def test_scaffold_json_skip_payload_when_covered():
    import json
    with patch("main.find_coverage", return_value=[_mock_coverage()]):
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(cli, ["scaffold", "https://comix.to",
                                         "--output", tmp, "--json"])
    data = json.loads(result.output)
    assert data["skipped"] is True
    assert data["reason"] == "already_covered"


def test_wizard_warns_when_covered_and_defaults_to_no():
    with patch("main.analyze", return_value=_mock_site_info()), \
         patch("main.find_coverage", return_value=[_mock_coverage()]):
        # Press Enter at the generate prompt -> default (No) because covered.
        result = runner.invoke(cli, ["wizard"], input="comix.to\n\n")
    assert "already supported by keiyoushi" in result.output.lower()
    assert "No project generated" in result.output


def test_scaffold_cloudflare_warning():
    info = _mock_site_info(cloudflare=True)
    with patch("main.analyze", return_value=info):
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.invoke(cli, ["scaffold", "https://cf-site.com", "--output", tmp])
    assert "Cloudflare" in result.output


def test_check_quick_mode():
    from src.checker.health_checker import HealthReport
    mock_report = MagicMock(spec=HealthReport)
    mock_report.format.return_value = "HEALTH REPORT\n[OK]  test selector"
    mock_report.is_healthy = True
    mock_report.total_broken = 0

    with patch("main.analyze", return_value=_mock_site_info()), \
         patch("main.quick_check", return_value=mock_report):
        result = runner.invoke(cli, ["check", "https://test.com", "--quick"])
    assert result.exit_code == 0
    assert "HEALTH REPORT" in result.output
    assert "passing" in result.output.lower()


def test_check_unhealthy_exits_1():
    from src.checker.health_checker import HealthReport
    mock_report = MagicMock(spec=HealthReport)
    mock_report.format.return_value = "REPORT\n[EMPTY] broken selector"
    mock_report.is_healthy = False
    mock_report.total_broken = 2

    with patch("main.analyze", return_value=_mock_site_info()), \
         patch("main.quick_check", return_value=mock_report):
        result = runner.invoke(cli, ["check", "https://test.com", "--quick"])
    assert result.exit_code == 1


def test_check_saves_output_file():
    from src.checker.health_checker import HealthReport
    mock_report = MagicMock(spec=HealthReport)
    mock_report.format.return_value = "SAVED REPORT CONTENT"
    mock_report.is_healthy = True
    mock_report.total_broken = 0

    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "report.txt")
        with patch("main.analyze", return_value=_mock_site_info()), \
             patch("main.quick_check", return_value=mock_report):
            runner.invoke(cli, ["check", "https://test.com", "--quick", "--output", out])
        assert Path(out).exists()
        assert "SAVED REPORT CONTENT" in Path(out).read_text()


def test_check_site_type_override():
    from src.checker.health_checker import HealthReport
    mock_report = MagicMock(spec=HealthReport)
    mock_report.format.return_value = "REPORT"
    mock_report.is_healthy = True
    mock_report.total_broken = 0

    with patch("main.quick_check", return_value=mock_report) as mock_qc:
        runner.invoke(cli, ["check", "https://test.com", "--quick", "--site-type", "manganow"])
    mock_qc.assert_called_once_with("https://test.com", site_type="manganow")


# ── wizard ──────────────────────────────────────────────────────────────────

def test_wizard_full_flow_generates_extension():
    """URL -> analyze -> generate -> skip health check -> next steps."""
    info = _mock_site_info(site_type=SiteType.MANGANOW)
    with patch("main.analyze", return_value=info):
        with tempfile.TemporaryDirectory() as tmp:
            # answers: generate? y | output folder | nsfw? n | health check? n
            result = runner.invoke(cli, ["wizard"],
                                   input=f"test.com\ny\n{tmp}\nn\nn\n")
    assert result.exit_code == 0
    assert "Wizard" in result.output
    assert "Extension generated" in result.output
    assert "Next steps" in result.output


def test_wizard_bare_invocation_launches_wizard():
    """Running with no command should invoke the wizard, then decline to generate."""
    with patch("main.analyze", return_value=_mock_site_info()):
        result = runner.invoke(cli, [], input="test.com\nn\n")
    assert result.exit_code == 0
    assert "Wizard" in result.output
    assert "No project generated" in result.output


def test_wizard_normalizes_bare_domain():
    """A bare domain should be analyzed as https://."""
    with patch("main.analyze", return_value=_mock_site_info()) as mock_an:
        runner.invoke(cli, ["wizard"], input="example.com\nn\n")
    mock_an.assert_called_once_with("https://example.com")


def test_wizard_survives_analyze_failure():
    """If analyze raises, the wizard offers a generic-template fallback."""
    with patch("main.analyze", side_effect=RuntimeError("network down")):
        with tempfile.TemporaryDirectory() as tmp:
            # fallback? y | generate? y | output | nsfw? n | health? n
            result = runner.invoke(cli, ["wizard"],
                                   input=f"test.com\ny\ny\n{tmp}\nn\nn\n")
    assert result.exit_code == 0
    assert "Could not analyze" in result.output
    assert "Extension generated" in result.output


if __name__ == "__main__":
    tests = [
        test_analyze_basic_output,
        test_analyze_json_flag,
        test_analyze_dead_site_exits_1,
        test_scaffold_creates_output,
        test_scaffold_skip_analyze,
        test_scaffold_json_output_for_ci,
        test_analyze_reports_coverage_in_json,
        test_scaffold_skips_when_already_covered,
        test_scaffold_force_overrides_coverage,
        test_scaffold_json_skip_payload_when_covered,
        test_wizard_warns_when_covered_and_defaults_to_no,
        test_scaffold_cloudflare_warning,
        test_check_quick_mode,
        test_check_unhealthy_exits_1,
        test_check_saves_output_file,
        test_check_site_type_override,
        test_wizard_full_flow_generates_extension,
        test_wizard_bare_invocation_launches_wizard,
        test_wizard_normalizes_bare_domain,
        test_wizard_survives_analyze_failure,
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
