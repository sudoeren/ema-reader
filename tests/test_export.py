import zipfile

import pytest

import export

BOOK = {"title": 'Liman: "Hikâyeler"?', "chapters": [
    {"title": "Giriş", "paragraphs": [["Bir.", "İki."], ["Üç."]]},
    {"title": None, "paragraphs": [["Dört."]]},
]}


def finish(job):
    job.run()  # in the test's own thread
    assert job.state == "ready", job.error
    return job


def test_names_are_safe_for_every_system():
    assert export.safe('a/b\\c:d*e?"f<g>h|') == "a b c d e f g h"
    assert export.safe("   ...   ") == "EMA Reader"
    assert export.chapter_name(BOOK, 0) == "01 Giriş"
    assert export.chapter_name(BOOK, 1) == "02"


def test_text_of_one_chapter():
    job = finish(export.Job(None, BOOK, "chapter", 0, "txt", False, 1.0))
    assert job.name == "Liman Hikâyeler - 01 Giriş.txt"
    assert job.path.read_text(encoding="utf-8") == "Giriş\n\nBir. İki.\n\nÜç."
    job.clean()
    assert not job.folder.exists()


def test_text_of_a_book_split_into_chapters():
    job = finish(export.Job(None, BOOK, "book", 0, "txt", True, 1.0))
    assert job.name == "Liman Hikâyeler.zip"
    with zipfile.ZipFile(job.path) as z:
        assert z.namelist() == ["01 Giriş.txt", "02.txt"]
        assert z.read("02.txt").decode() == "Dört."
    job.clean()


@pytest.mark.parametrize("options", [{"kind": "aac"}, {"scope": "page"}, {"chapter": 5}, {"speed": 9}])
def test_bad_requests_are_refused(options):
    with pytest.raises(ValueError):
        export.start(None, BOOK, **options)
