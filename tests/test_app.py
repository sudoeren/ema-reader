import pytest

np = pytest.importorskip("numpy")  # app.py needs it for audio; the tests here do not make any

import app
from extract import extract_file

TEXT = "# Bir\n\nİlk cümle. İkinci cümle.\n\n# İki\n\nSon paragraf.".encode()


def test_preview_describes_a_book_without_adding_it(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "LIBRARY", tmp_path)
    monkeypatch.setattr(app, "pending", {})
    found = app.preview(extract_file("kitap.md", TEXT), "kitap.md")
    assert (found["title"], found["chapters"], found["contents"]) == ("kitap", 2, ["Bir", "İki"])
    assert found["excerpt"] == "İlk cümle. İkinci cümle. Son paragraf."
    assert found["size"] == len("İlk cümle.İkinci cümle.Son paragraf.")
    assert not found["article"] and not found["cover"]
    assert not list(tmp_path.iterdir())  # nothing in the library yet

    stored = app.store(*app.pending.pop(found["token"]))
    assert app.read_book(stored["id"])["title"] == "kitap"


def test_only_a_few_previews_are_kept(monkeypatch):
    monkeypatch.setattr(app, "pending", {})
    tokens = [app.preview(extract_file("a.txt", b"Bir."), "a.txt")["token"] for _ in range(6)]
    assert list(app.pending) == tokens[-4:]


def test_summary_names_the_chapter_being_read(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "LIBRARY", tmp_path)
    book = app.store(extract_file("kitap.md", TEXT), "kitap.md")
    book["progress"] = {"chapter": 1, "sentence": 0}
    assert app.summary(book)["chapter_title"] == "İki"
