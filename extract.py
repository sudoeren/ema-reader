"""Turns a book or an article into chapters of paragraphs of sentences.

    extract_file("kitap.epub", data)   # .epub, .pdf, .txt, .md, .html
    extract_url("https://...")

Both return {"title", "author", "chapters": [{"title", "paragraphs": [[sentence, ...], ...]}],
"about": {"description", "publisher", "language", "date", "subjects"}, "cover": (bytes, type) or None}.
A chapter without a name of its own has the title None.
"""

import io
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

BLOCKS = {"p", "div", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "section", "article", "pre"}
HEADINGS = {"h1", "h2", "h3"}
SKIPPED = {"script", "style", "head", "nav", "svg", "figure", "table", "sup"}

# a sentence ends at . ! ? … (plus closing quotes) when the next one starts with a capital, digit or quote
SENTENCE_END = re.compile(r"""(?<=[.!?…])["”’')\]]*\s+(?=["“‘'(\[]?[A-ZÇĞİÖŞÜ0-9])""")
ABBREVIATIONS = ("Dr.", "Prof.", "Doç.", "Av.", "Sn.", "St.", "No.", "Bkz.", "bkz.", "Hz.", "Alb.", "Yrd.", "Mr.", "Mrs.")
PAGES_PER_CHAPTER = 10


def sentences(paragraph):
    parts = []
    for piece in SENTENCE_END.split(paragraph):
        # "Dr. Ali" is one sentence, and so is a lone initial such as "A. Kadir"
        if parts and (parts[-1].endswith(ABBREVIATIONS) or re.search(r"(^|\s)[A-ZÇĞİÖŞÜ]\.$", parts[-1])):
            parts[-1] += " " + piece
        else:
            parts.append(piece)
    return parts


# reference markers and wiki edit links, which should not be read aloud
NOISE = re.compile(r"\[(\d+|değiştir[^\]]*|edit[^\]]*|kaynak belirtilmeli|citation needed)\]")


def chapter(title, paragraphs):
    paragraphs = [" ".join(NOISE.sub("", p).split()) for p in paragraphs]
    paragraphs = [p for p in paragraphs if p]
    title = " ".join(title.split()) if title else None  # None: the reader shows "N. bölüm"
    if paragraphs and paragraphs[0] == title:
        paragraphs = paragraphs[1:]  # the heading is already shown as the chapter title
    return {"title": title, "paragraphs": [sentences(p) for p in paragraphs]}


class TextParser(HTMLParser):
    """Collects the readable paragraphs of an HTML page and its first heading."""

    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.heading = None
        self.buffer = []
        self.skip = 0
        self.in_heading = False

    def flush(self):
        text = " ".join("".join(self.buffer).split())
        self.buffer = []
        if text:
            self.paragraphs.append(text)
            if self.in_heading and self.heading is None:
                self.heading = text

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED:
            self.skip += 1
        elif tag in BLOCKS:
            self.flush()
            self.in_heading = tag in HEADINGS

    def handle_endtag(self, tag):
        if tag in SKIPPED:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCKS:
            self.flush()
            self.in_heading = False

    def handle_data(self, data):
        if not self.skip:
            self.buffer.append(data)


def parse_html(html):
    parser = TextParser()
    parser.feed(html)
    parser.flush()
    return parser.heading, parser.paragraphs


def local(tag):
    return tag.rsplit("}", 1)[-1]


def plain(html):
    """Text of a short HTML fragment, such as a book description."""
    return " ".join(" ".join(parse_html(html or "")[1]).split()) or None


def epub_titles(book, opf_dir, manifest, items):
    """Chapter names from the table of contents, by the file they point at."""
    titles = {}

    def note(href, base, label):
        path = posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0])))
        label = " ".join((label or "").split())
        if label:
            titles.setdefault(path, label)

    for item in items:
        href, kind, properties = item.get("href"), item.get("media-type"), item.get("properties") or ""
        path = posixpath.normpath(posixpath.join(opf_dir, unquote(href or "")))
        try:
            if "nav" in properties.split():  # EPUB 3
                tree = ElementTree.fromstring(book.read(path))
                for link in tree.iter():
                    if local(link.tag) == "a" and link.get("href"):
                        note(link.get("href"), posixpath.dirname(path), "".join(link.itertext()))
            elif kind == "application/x-dtbncx+xml":  # EPUB 2
                tree = ElementTree.fromstring(book.read(path))
                for point in tree.iter():
                    if local(point.tag) == "navPoint":
                        label = next(("".join(e.itertext()) for e in point if local(e.tag) == "navLabel"), "")
                        target = next((e.get("src") for e in point if local(e.tag) == "content"), None)
                        if target:
                            note(target, posixpath.dirname(path), label)
        except (KeyError, ElementTree.ParseError):
            continue
    return titles


def extract_epub(data):
    book = zipfile.ZipFile(io.BytesIO(data))
    container = ElementTree.fromstring(book.read("META-INF/container.xml"))
    opf_path = next(e for e in container.iter() if local(e.tag) == "rootfile").get("full-path")
    opf_dir = posixpath.dirname(opf_path)
    opf = ElementTree.fromstring(book.read(opf_path))

    def metas(name):
        return [e.text.strip() for e in opf.iter() if local(e.tag) == name and e.text and e.text.strip()]

    def meta(name):
        return next(iter(metas(name)), None)

    items = [e for e in opf.iter() if local(e.tag) == "item"]
    manifest = {e.get("id"): e.get("href") for e in items}
    spine = [e.get("idref") for e in opf.iter() if local(e.tag) == "itemref"]
    titles = epub_titles(book, opf_dir, manifest, items)

    chapters = []
    for idref in spine:
        if idref not in manifest:
            continue
        path = posixpath.normpath(posixpath.join(opf_dir, unquote(manifest[idref])))
        try:
            html = book.read(path).decode("utf-8", errors="replace")
        except KeyError:
            continue
        heading, paragraphs = parse_html(html)
        if paragraphs:
            chapters.append(chapter(titles.get(path) or heading, paragraphs))

    # the cover: marked as such in EPUB 3, named by a <meta> in EPUB 2, else an image called "cover"
    images = [e for e in items if (e.get("media-type") or "").startswith("image/")]
    named = next((e.get("content") for e in opf.iter() if local(e.tag) == "meta" and e.get("name") == "cover"), None)
    candidates = (
        (e for e in images if "cover-image" in (e.get("properties") or "").split()),
        (e for e in images if e.get("id") == named),
        (e for e in images if "cover" in f"{e.get('id')} {e.get('href')}".lower()),
    )
    cover = next((e for found in candidates for e in found), None)  # not `or`: an element without children is falsy
    picture = None
    if cover is not None:
        try:
            picture = (book.read(posixpath.normpath(posixpath.join(opf_dir, unquote(cover.get("href"))))), cover.get("media-type"))
        except KeyError:
            pass

    about = {"description": plain(meta("description")), "publisher": meta("publisher"), "language": meta("language"),
             "date": (meta("date") or "")[:10] or None, "subjects": metas("subject")}
    return {"title": meta("title"), "author": ", ".join(metas("creator")) or None, "chapters": chapters, "about": about, "cover": picture}


def pdf_paragraphs(text):
    text = re.sub(r"-\n(?=\w)", "", text)  # words hyphenated across lines
    blocks = re.split(r"\n\s*\n", text)
    if len(blocks) < 3:
        # no blank lines between paragraphs: a line that ends a sentence ends the paragraph
        blocks = re.split(r"(?<=[.!?…:])\n", text)
    return [b.replace("\n", " ") for b in blocks]


def extract_pdf(data):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    info = reader.metadata or {}

    # use the top level of the outline as chapters when the PDF has one
    starts = []
    try:
        for item in reader.outline:
            if not isinstance(item, list):
                starts.append((reader.get_destination_page_number(item), item.title.strip()))
    except Exception:
        starts = []
    starts = sorted(set(s for s in starts if s[0] is not None))
    if len(starts) < 2:
        starts = [(i, f"{i + 1}–{min(i + PAGES_PER_CHAPTER, len(pages))}")
                  for i in range(0, len(pages), PAGES_PER_CHAPTER)]
    elif starts[0][0] > 0:
        starts.insert(0, (0, None))

    chapters = []
    for (start, title), (end, _) in zip(starts, starts[1:] + [(len(pages), None)]):
        paragraphs = pdf_paragraphs("\n".join(pages[start:end]))
        if any(p.strip() for p in paragraphs):
            chapters.append(chapter(title, paragraphs))
    # a first page that is one picture is taken as the cover
    picture = None
    try:
        images = list(reader.pages[0].images)
        if len(images) == 1 and len(images[0].data) > 20_000:
            kind = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(images[0].name.rsplit(".", 1)[-1].lower())
            if kind:
                picture = (images[0].data, kind)
    except Exception:
        pass
    about = {"description": info.get("/Subject") or None, "publisher": None, "language": None,
             "date": None, "subjects": [k.strip() for k in (info.get("/Keywords") or "").split(",") if k.strip()]}
    return {"title": info.get("/Title") or None, "author": info.get("/Author") or None, "chapters": chapters,
            "about": about, "cover": picture}


def extract_text(text):
    """Plain text or Markdown: '#' headings start chapters, blank lines separate paragraphs."""
    chapters, title, lines = [], None, []

    def close():
        paragraphs = re.split(r"\n\s*\n", "\n".join(lines))
        if any(p.strip() for p in paragraphs):
            chapters.append(chapter(title, paragraphs))

    for line in text.splitlines():
        heading = re.match(r"#{1,3}\s+(.*)", line)
        if heading:
            close()
            title, lines = heading.group(1).strip(), []
        else:
            lines.append(re.sub(r"[*_`]+", "", line))
    close()
    return {"title": None, "author": None, "chapters": chapters}


def extract_html(html):
    import trafilatura

    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not text:
        raise ValueError("Sayfada okunacak metin bulunamadı.")
    meta = trafilatura.extract_metadata(html)
    title = meta.title if meta else None
    if title:
        # "Meddah - Vikipedi" -> "Meddah": drop a short site name after the last separator
        parts = re.split(r"\s[-–—|]\s", title)
        if len(parts) > 1 and len(parts[-1].split()) <= 3:
            title = title[: title.rindex(parts[-1])].rstrip(" -–—|")
    about = {"description": (meta.description if meta else None) or None, "publisher": (meta.sitename if meta else None) or None,
             "language": None, "date": (meta.date if meta else None) or None, "subjects": []}
    return {"title": title, "author": None, "chapters": [chapter(title, text.split("\n"))], "about": about,
            "cover": None, "image": (meta.image if meta else None) or None}


def extract_file(name, data):
    suffix = PurePosixPath(name).suffix.lower()
    if suffix == ".epub":
        book = extract_epub(data)
    elif suffix == ".pdf":
        book = extract_pdf(data)
    elif suffix in (".html", ".htm"):
        book = extract_html(data.decode("utf-8", errors="replace"))
    elif suffix in (".txt", ".md", ""):
        book = extract_text(data.decode("utf-8", errors="replace"))
    else:
        raise ValueError("Bu dosya türü desteklenmiyor. EPUB, PDF, metin ya da Markdown ekleyebilirsin.")
    book["title"] = book["title"] or PurePosixPath(name).stem
    return finish(book)


def extract_url(url):
    import trafilatura

    if not url.startswith(("http://", "https://")):
        raise ValueError("Adres http:// ya da https:// ile başlamalı.")
    html = trafilatura.fetch_url(url)
    if not html:
        raise ValueError("Sayfa indirilemedi. Adresi ve internet bağlantını kontrol et.")
    book = extract_html(html)
    book["title"] = book["title"] or url
    book["author"] = urlparse(url).hostname  # page metadata rarely names the author reliably
    book["cover"] = fetch_image(book.get("image"))
    return finish(book)


def fetch_image(url):
    """The page's preview picture, if it has one and it is a reasonable size."""
    import urllib.request

    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (EMA Reader)"})
        with urllib.request.urlopen(request, timeout=8) as response:
            kind = response.headers.get_content_type()
            data = response.read(5_000_001)
        return (data, kind) if kind.startswith("image/") and len(data) <= 5_000_000 else None
    except Exception:
        return None


def finish(book):
    book.pop("image", None)
    book.setdefault("about", {"description": None, "publisher": None, "language": None, "date": None, "subjects": []})
    book.setdefault("cover", None)
    book["chapters"] = [c for c in book["chapters"] if c["paragraphs"]]
    if not book["chapters"]:
        raise ValueError("Burada okunacak metin bulunamadı. Taranmış (resim) PDF'ler okunamaz.")
    return book
