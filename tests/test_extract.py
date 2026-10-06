import io
import zipfile

import pytest

from extract import extract_file, sentences


def test_sentences_split_on_endings():
    assert sentences("Liman uyanmamıştı. Martılar dönüyordu! Peki yeter miydi? Hayır.") == [
        "Liman uyanmamıştı.", "Martılar dönüyordu!", "Peki yeter miydi?", "Hayır."]


def test_sentences_keep_titles_initials_and_numbers_together():
    assert sentences("Dr. Kemal Bey saat 06:30'da geldi. A. Kadir 1.250 lira kazandı.") == [
        "Dr. Kemal Bey saat 06:30'da geldi.", "A. Kadir 1.250 lira kazandı."]


def test_sentences_keep_a_closing_quote_with_its_sentence():
    assert sentences("“Bugün hava güzel olacak,” dedi. Kimse cevap vermedi.") == [
        "“Bugün hava güzel olacak,” dedi.", "Kimse cevap vermedi."]


def test_markdown_headings_become_chapters():
    book = extract_file("kitap.md", "# Bir\n\nİlk paragraf. İkinci cümle.\n\n# İki\n\nSon paragraf.".encode())
    assert book["title"] == "kitap"
    assert [c["title"] for c in book["chapters"]] == ["Bir", "İki"]
    assert book["chapters"][0]["paragraphs"] == [["İlk paragraf.", "İkinci cümle."]]


def test_text_without_headings_is_one_unnamed_chapter():
    book = extract_file("not.txt", "Tek bir paragraf.".encode())
    assert [c["title"] for c in book["chapters"]] == [None]


def epub(chapters, nav=None, cover=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>')
        items = "".join(f'<item id="c{i}" href="text/c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(len(chapters)))
        if nav:
            items += '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            links = "".join(f'<li><a href="text/c{i}.xhtml#top">{name}</a></li>' for i, name in enumerate(nav))
            z.writestr("OPS/nav.xhtml", f'<html xmlns="http://www.w3.org/1999/xhtml"><body><nav><ol>{links}</ol></nav></body></html>')
        if cover:
            items += '<item id="img" href="kapak.png" media-type="image/png" properties="cover-image"/>'
            z.writestr("OPS/kapak.png", cover)
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
        z.writestr("OPS/book.opf", '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   "<dc:title>Liman</dc:title><dc:creator>Bir Yazar</dc:creator><dc:publisher>Yayınevi</dc:publisher>"
                   "<dc:description>&lt;p&gt;Kısa bir &lt;b&gt;tanıtım&lt;/b&gt;.&lt;/p&gt;</dc:description><dc:date>2020-05-01T00:00:00Z</dc:date>"
                   f"</metadata><manifest>{items}</manifest><spine>{spine}</spine></package>")
        for i, body in enumerate(chapters):
            z.writestr(f"OPS/text/c{i}.xhtml", f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title><style>p{{}}</style></head><body>{body}</body></html>')
    return data.getvalue()


def test_epub_reads_details_and_chapters_in_spine_order():
    book = extract_file("liman.epub", epub(["<h2>Giriş</h2><p>İlk bölüm.</p>", "<p>İkinci bölüm.</p>"]))
    assert (book["title"], book["author"]) == ("Liman", "Bir Yazar")
    assert book["about"]["publisher"] == "Yayınevi"
    assert book["about"]["description"] == "Kısa bir tanıtım."
    assert book["about"]["date"] == "2020-05-01"
    assert [c["title"] for c in book["chapters"]] == ["Giriş", None]
    assert book["chapters"][0]["paragraphs"] == [["İlk bölüm."]]  # the heading is not repeated as text
    assert book["cover"] is None


def test_epub_chapter_names_come_from_the_table_of_contents():
    book = extract_file("liman.epub", epub(["<p>Bir.</p>", "<h1>Başlık</h1><p>İki.</p>"], nav=["Birinci", "İkinci"]))
    assert [c["title"] for c in book["chapters"]] == ["Birinci", "İkinci"]


def test_epub_cover_is_found():
    book = extract_file("liman.epub", epub(["<p>Bir.</p>"], cover=b"\x89PNG fake"))
    assert book["cover"] == (b"\x89PNG fake", "image/png")


def test_reference_marks_are_not_read():
    book = extract_file("a.txt", "Meddah hikâye anlatır.[1] Kahvehanede oturur.[kaynak belirtilmeli]".encode())
    assert book["chapters"][0]["paragraphs"] == [["Meddah hikâye anlatır.", "Kahvehanede oturur."]]


@pytest.mark.parametrize("name, data", [("a.docx", b"x"), ("bos.txt", b"   ")])
def test_unreadable_input_is_a_value_error(name, data):
    with pytest.raises(ValueError):
        extract_file(name, data)
