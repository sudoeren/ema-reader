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
        {"name": "EMA-Reader-1.10.0-Setup.exe", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-1.10.0-Setup.exe"},
        {"name": "EMA-Reader-1.10.0.dmg", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-1.10.0.dmg"},
        {"name": "EMA-Reader-1.10.0.deb", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-1.10.0.deb"},
        {"name": "EMA-Reader-1.10.0.pkg.tar.zst", "browser_download_url": "https://github.com/sudoeren/ema-reader/releases/download/v1.10.0/EMA-Reader-1.10.0.pkg.tar.zst"},
    ],
}


def test_versions_compare_as_numbers():
    assert update.number("v1.10.0") > update.number("1.9.3")
    assert update.number("1.0.0") == update.number("v1.0.0")


def test_a_copy_is_updated_with_the_same_kind_of_file_it_came_in(monkeypatch, tmp_path):
    monkeypatch.setattr(update, "PACKAGE", tmp_path / "package")
    assert update.release(RELEASE)["download"] is None  # from source: updated with git instead
    assert update.release(RELEASE)["latest"] == "1.10.0"
    for name in ("EMA-Reader-{version}-Setup.exe", "EMA-Reader-{version}.dmg", "EMA-Reader-{version}.deb", "EMA-Reader-{version}.pkg.tar.zst"):
        (tmp_path / "package").write_text(name + "\n", encoding="utf-8")
        assert update.release(RELEASE)["download"].endswith("/" + name.replace("{version}", "1.10.0"))
    (tmp_path / "package").write_text("EMA-Reader-{version}.rpm\n", encoding="utf-8")
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


def test_the_folder_build_is_swapped_for_the_new_one(monkeypatch, tmp_path):
    import tarfile

    app = tmp_path / "home" / "ema-reader"
    app.mkdir(parents=True)
    (app / "desktop.py").write_text("old")
    (app / "gone.py").write_text("")
    new = tmp_path / "new" / "ema-reader"
    new.mkdir(parents=True)
    (new / "desktop.py").write_text("new")

    def download(found, name):
        folder = tmp_path / "download"
        folder.mkdir()
        with tarfile.open(folder / name, "w:gz") as archive:
            archive.add(new, "ema-reader")
        return folder / name

    restarted = []
    monkeypatch.setattr(update, "ROOT", app)
    monkeypatch.setattr(update, "PACKAGE", app / "package")
    (app / "package").write_text("EMA-Reader-{version}.tar.gz\n", encoding="utf-8")
    monkeypatch.setattr(update, "download", download)
    monkeypatch.setattr(update, "restart", lambda: restarted.append(True))
    update.install({"latest": "1.2.3"})
    assert restarted and (app / "desktop.py").read_text() == "new" and not (app / "gone.py").exists()
    assert sorted(p.name for p in app.parent.iterdir()) == ["ema-reader"] and not (tmp_path / "download").exists()


def test_without_the_api_the_releases_page_says_which_is_the_latest(monkeypatch, tmp_path):
    class Answer:
        url = "https://github.com/sudoeren/ema-reader/releases/tag/v1.4.0"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def refuse(request, timeout=None):
        if "api.github.com" in request.full_url:
            raise OSError("rate limit")  # GitHub answers only sixty questions an hour from one address
        return Answer()

    monkeypatch.setattr(update.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(update, "cache", {"until": 0, "release": None})
    monkeypatch.setattr(update, "PACKAGE", tmp_path / "package")
    (tmp_path / "package").write_text("EMA-Reader-{version}.deb\n", encoding="utf-8")
    found = update.check("1.0.0")
    assert found["newer"] and found["latest"] == "1.4.0"
    assert found["download"] == "https://github.com/sudoeren/ema-reader/releases/download/v1.4.0/EMA-Reader-1.4.0.deb"
