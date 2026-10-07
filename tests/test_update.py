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
        {"name": "EMA-Reader-debian-13.deb", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-debian-13.deb"},
        {"name": "EMA-Reader-ubuntu-24.04.deb", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-ubuntu-24.04.deb"},
        {"name": "EMA-Reader-arch.pkg.tar.zst", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-arch.pkg.tar.zst"},
    ],
}


def test_versions_compare_as_numbers():
    assert update.number("v1.10.0") > update.number("1.9.3")
    assert update.number("1.0.0") == update.number("v1.0.0")


def test_release_gives_the_installer_for_the_system(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "PACKAGE", tmp_path / "package")
    assert update.release(RELEASE, "win32")["download"].endswith("EMA-Reader-Setup.exe")
    assert update.release(RELEASE, "darwin")["download"].endswith("EMA-Reader.dmg")
    assert update.release(RELEASE, "linux")["download"] is None  # updated with git instead
    assert update.release(RELEASE, "linux")["latest"] == "1.10.0"


def test_a_linux_package_is_updated_with_the_package_for_the_same_system(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "PACKAGE", tmp_path / "package")
    (tmp_path / "package").write_text("EMA-Reader-ubuntu-24.04.deb\n", encoding="utf-8")
    assert update.release(RELEASE, "linux")["download"].endswith("/EMA-Reader-ubuntu-24.04.deb")
    (tmp_path / "package").write_text("EMA-Reader-arch.pkg.tar.zst\n", encoding="utf-8")
    assert update.release(RELEASE, "linux")["download"].endswith("/EMA-Reader-arch.pkg.tar.zst")
    (tmp_path / "package").write_text("EMA-Reader-fedora-44.rpm\n", encoding="utf-8")
    assert update.release(RELEASE, "linux")["download"] is None  # not published for this system


def test_release_notes_lose_their_markdown():
    assert update.release(RELEASE)["notes"] == "Yenilikler\n\n• Daha hızlı açılış\n• Koyu tema"


def test_links_that_do_not_point_at_github_are_dropped():
    found = update.release({**RELEASE, "html_url": "javascript:alert(1)", "assets": [{"name": "x.exe", "browser_download_url": "http://kotu.example/x.exe"}]}, "win32")
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
