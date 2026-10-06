"""Turns a book or an article into chapters of paragraphs of sentences.

    extract_file("kitap.epub", data)   # .epub, .pdf, .txt, .md, .html
    extract_url("https://...")

Both return {"title", "author", "chapters": [{"title", "paragraphs": [[sentence, ...], ...]}]}.
"""

import io
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote
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


def extract_epub(data):
    book = zipfile.ZipFile(io.BytesIO(data))
    container = ElementTree.fromstring(book.read("META-INF/container.xml"))
    opf_path = next(e for e in container.iter() if local(e.tag) == "rootfile").get("full-path")
    opf = ElementTree.fromstring(book.read(opf_path))

    def meta(name):
        return next((e.text.strip() for e in opf.iter() if local(e.tag) == name and e.text), None)

    manifest = {e.get("id"): e.get("href") for e in opf.iter() if local(e.tag) == "item"}
    spine = [e.get("idref") for e in opf.iter() if local(e.tag) == "itemref"]

    chapters = []
    for idref in spine:
        if idref not in manifest:
            continue
        path = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), unquote(manifest[idref])))
        try:
            html = book.read(path).decode("utf-8", errors="replace")
        except KeyError:
            continue
        heading, paragraphs = parse_html(html)
        if paragraphs:
            chapters.append(chapter(heading or f"Section {len(chapters) + 1}", paragraphs))
    return {"title": meta("title"), "author": meta("creator"), "chapters": chapters}


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
        starts = [(i, f"Pages {i + 1}–{min(i + PAGES_PER_CHAPTER, len(pages))}")
                  for i in range(0, len(pages), PAGES_PER_CHAPTER)]
    elif starts[0][0] > 0:
        starts.insert(0, (0, "Front matter"))

    chapters = []
    for (start, title), (end, _) in zip(starts, starts[1:] + [(len(pages), None)]):
        paragraphs = pdf_paragraphs("\n".join(pages[start:end]))
        if any(p.strip() for p in paragraphs):
            chapters.append(chapter(title, paragraphs))
    return {"title": info.get("/Title"), "author": info.get("/Author"), "chapters": chapters}


def extract_text(text):
    """Plain text or Markdown: '#' headings start chapters, blank lines separate paragraphs."""
    chapters, title, lines = [], None, []

    def close():
        paragraphs = re.split(r"\n\s*\n", "\n".join(lines))
        if any(p.strip() for p in paragraphs):
            chapters.append(chapter(title or "Text", paragraphs))

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
        raise ValueError("no readable text found on the page")
    meta = trafilatura.extract_metadata(html)
    title = meta.title if meta else None
    return {
        "title": title,
        "author": meta.author if meta else None,
        "chapters": [chapter(title or "Article", text.split("\n"))],
    }


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
        raise ValueError(f"unsupported file type: {suffix}")
    book["title"] = book["title"] or PurePosixPath(name).stem
    return finish(book)


def extract_url(url):
    import trafilatura

    if not url.startswith(("http://", "https://")):
        raise ValueError("the address must start with http:// or https://")
    html = trafilatura.fetch_url(url)
    if not html:
        raise ValueError("could not download the page")
    book = extract_html(html)
    book["title"] = book["title"] or url
    return finish(book)


def finish(book):
    book["chapters"] = [c for c in book["chapters"] if c["paragraphs"]]
    if not book["chapters"]:
        raise ValueError("no readable text found")
    return book
