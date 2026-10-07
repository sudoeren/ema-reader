import re
import tomllib
from pathlib import Path

import update

ROOT = Path(__file__).parent.parent
RELEASE = {
    "tag_name": "v1.10.0",
    "html_url": "https://github.com/sudoeren/ema-reader/releases/tag/v1.10.0",
    "body": "## Yenilikler\n\n- **Daha hızlı** açılış\n* Koyu tema",
    "assets": [
        {"name": "EMA-Reader-Setup.exe", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-Setup.exe"},
        {"name": "EMA-Reader.dmg", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader.dmg"},
        {"name": "EMA-Reader.deb", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader.deb"},
        {"name": "EMA-Reader.pkg.tar.zst", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader.pkg.tar.zst"},
    ],
}


def test_versions_compare_as_numbers():
    assert update.number("v1.10.0") > update.number("1.9.3")
    assert update.number("1.0.0") == update.number("v1.0.0")


def test_a_copy_is_updated_with_the_same_kind_of_file_it_came_in(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "PACKAGE", tmp_path / "package")
    assert update.release(RELEASE)["download"] is None  # from source: updated with git instead
    assert update.release(RELEASE)["latest"] == "1.10.0"
    for name in ("EMA-Reader-Setup.exe", "EMA-Reader.dmg", "EMA-Reader.deb", "EMA-Reader.pkg.tar.zst"):
        (tmp_path / "package").write_text(name + "\n", encoding="utf-8")
        assert update.release(RELEASE)["download"].endswith("/" + name)
    (tmp_path / "package").write_text("EMA-Reader.rpm\n", encoding="utf-8")
    assert update.release(RELEASE)["download"] is None  # not published in this release


def test_release_notes_lose_their_markdown():
    assert update.release(RELEASE)["notes"] == "Yenilikler\n\n• Daha hızlı açılış\n• Koyu tema"


def test_links_that_do_not_point_at_github_are_dropped(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "PACKAGE", tmp_path / "package")
    (tmp_path / "package").write_text("x.exe\n", encoding="utf-8")
    found = update.release({**RELEASE, "html_url": "javascript:alert(1)", "assets": [{"name": "x.exe", "browser_download_url": "http://kotu.example/x.exe"}]})
    assert found["page"] is None and found["download"] is None


def test_check_never_fails_and_reports_a_newer_version(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "cache", {"until": 0, "release": None})
    monkeypatch.setattr(update, "URL", (tmp_path / "yok.json").as_uri())
    assert update.check("1.0.0")["newer"] is False

    import json

    (tmp_path / "var.json").write_text(json.dumps(RELEASE), encoding="utf-8")
    monkeypatch.setattr(update, "cache", {"until": 0, "release": None})
    monkeypatch.setattr(update, "URL", (tmp_path / "var.json").as_uri())
    assert update.check("1.0.0")["newer"] is True
    assert update.check("1.10.0")["newer"] is False
    assert update.check("2.0.0")["newer"] is False


def test_changelog_section_of_a_version():
    text = "# Sürüm notları\n\n## 1.1.0\n\n- Yeni\n\n## 1.0.0\n\nİlk sürüm.\n"
    assert update.changelog(text, "1.1.0") == "- Yeni"
    assert update.changelog(text, "1.0.0") == "İlk sürüm."
    assert update.changelog(text, "3.0.0") is None


def test_the_version_is_the_same_everywhere_and_has_notes():
    stated = re.search(r'^VERSION = "(.+)"', (ROOT / "app.py").read_text(encoding="utf-8"), re.M).group(1)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert stated == project
    assert update.changelog((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), stated)
