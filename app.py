"""EMA Reader: a book and article reader that speaks Turkish text with EMA Lightning.

    uv run app.py                      # opens http://127.0.0.1:8000

Add an EPUB, a PDF, a text file or a web address in the browser, then listen.

The same server also answers plain text-to-speech requests:

    curl "localhost:8000/tts?text=Merhaba" -o merhaba.wav
    curl localhost:8000/tts -d '{"text": "Merhaba", "speed": 1.2}' -o merhaba.wav

Endpoints:
    GET    /                                   the reader
    GET    /api/books                          the library
    POST   /api/books?name=kitap.epub          add a file (the body is the file)
    POST   /api/books                          add an article: {"url": "https://..."}
    GET    /api/books/ID                       one book with its text
    DELETE /api/books/ID
    PUT    /api/books/ID/progress              {"chapter": 0, "sentence": 12}
    GET    /api/books/ID/chapters/N/audio      a chapter as one WAV file
    GET    /tts, POST /tts                     text, speed, seed, sample_rate, stream
"""

import argparse
import io
import json
import mimetypes
import os
import re
import tempfile
import threading
import time
import uuid
import wave
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import numpy as np

from extract import extract_file, extract_url

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
LIBRARY = ROOT / "library"
MAX_UPLOAD = 200 * 1024 * 1024
BOOK = re.compile(r"/api/books/([0-9a-f]{12})(/progress|/chapters/(\d+)/audio)?")

# exported chapters: sentences are generated in batches and joined with short pauses
EXPORT_RATE = 24000
EXPORT_BATCH = 32
SENTENCE_PAUSE = 0.15
PARAGRAPH_PAUSE = 0.5

tts = None
default_speed = 1.0
library_lock = threading.Lock()


def pcm16(audio):
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def parse(params):
    """Convert request parameters to the types EMA expects."""
    text = params.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text is required")
    opts = {"speed": default_speed}
    if params.get("speed") is not None:
        opts["speed"] = float(params["speed"])
    if params.get("seed") is not None:
        opts["seed"] = int(params["seed"])
    if params.get("sample_rate") is not None:
        opts["sample_rate"] = int(params["sample_rate"])
    stream = str(params.get("stream", "")).lower() in ("1", "true")
    return text, opts, stream


def book_path(book_id):
    return LIBRARY / f"{book_id}.json"


def read_book(book_id):
    return json.loads(book_path(book_id).read_text(encoding="utf-8"))


def write_book(book):
    LIBRARY.mkdir(exist_ok=True)
    tmp = book_path(book["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    tmp.replace(book_path(book["id"]))


def summary(book):
    counts = [sum(len(p) for p in c["paragraphs"]) for c in book["chapters"]]
    progress = book["progress"]
    done = sum(counts[: progress["chapter"]]) + progress["sentence"]
    return {
        "id": book["id"],
        "title": book["title"],
        "author": book["author"],
        "source": book["source"],
        "added": book["added"],
        "chapters": len(counts),
        "sentences": sum(counts),
        "done": done,
    }


def chapter_wav(chapter, speed):
    """Write a whole chapter to a temporary WAV file and return it, rewound."""
    sentences = [(s, i == len(p) - 1) for p in chapter["paragraphs"] for i, s in enumerate(p)]
    out = tempfile.TemporaryFile()
    w = wave.open(out, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(EXPORT_RATE)
    for start in range(0, len(sentences), EXPORT_BATCH):
        batch = sentences[start : start + EXPORT_BATCH]
        speeches = tts.say([s for s, _ in batch], speed=speed, sample_rate=EXPORT_RATE)
        for speech, (_, ends_paragraph) in zip(speeches, batch):
            w.writeframes(pcm16(speech.audio))
            pause = PARAGRAPH_PAUSE if ends_paragraph else SENTENCE_PAUSE
            w.writeframes(bytes(2 * int(pause * EXPORT_RATE)))
    w.close()  # patches the sizes in the header; leaves our file open
    out.seek(0)
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        query = dict(parse_qsl(url.query))
        book = BOOK.fullmatch(url.path)
        if url.path == "/":
            self.send_file(STATIC / "index.html")
        elif url.path.startswith("/static/"):
            self.send_file(STATIC / url.path[len("/static/") :])
        elif url.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif url.path == "/tts":
            self.tts(query)
        elif url.path == "/api/books":
            self.list_books()
        elif book and not book.group(2):
            self.with_book(book.group(1), lambda b: self.send_json(200, b))
        elif book and book.group(3):
            self.with_book(book.group(1), lambda b: self.chapter_audio(b, int(book.group(3)), query))
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/tts":
            params = self.read_json()
            if params is not None:
                self.tts(params)
        elif url.path == "/api/books":
            self.add_book(dict(parse_qsl(url.query)))
        else:
            self.send_json(404, {"error": "not found"})

    def do_PUT(self):
        book = BOOK.fullmatch(urlparse(self.path).path)
        if not book or book.group(2) != "/progress":
            return self.send_json(404, {"error": "not found"})
        params = self.read_json()
        if params is not None:
            self.with_book(book.group(1), lambda b: self.set_progress(b, params))

    def do_DELETE(self):
        book = BOOK.fullmatch(urlparse(self.path).path)
        if not book or book.group(2):
            return self.send_json(404, {"error": "not found"})
        with library_lock:
            book_path(book.group(1)).unlink(missing_ok=True)
        self.send_json(200, {"deleted": book.group(1)})

    # library

    def list_books(self):
        books = []
        for path in LIBRARY.glob("*.json"):
            try:
                books.append(summary(json.loads(path.read_text(encoding="utf-8"))))
            except (ValueError, KeyError):
                continue  # not a book file
        books.sort(key=lambda b: b["added"], reverse=True)
        self.send_json(200, books)

    def add_book(self, query):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_UPLOAD:
                raise ValueError("the file is too large")
            body = self.rfile.read(length)
            if query.get("name"):
                source = query["name"]
                book = extract_file(source, body)
            else:
                source = json.loads(body).get("url", "")
                book = extract_url(source)
        except ValueError as e:
            return self.send_json(400, {"error": str(e) or "could not read the request"})
        except Exception as e:  # a damaged file should not take the server down
            return self.send_json(400, {"error": f"could not read it: {e}"})
        book.update(id=uuid.uuid4().hex[:12], source=source, added=time.time(),
                    progress={"chapter": 0, "sentence": 0})
        with library_lock:
            write_book(book)
        self.send_json(201, summary(book))

    def with_book(self, book_id, action):
        try:
            book = read_book(book_id)
        except FileNotFoundError:
            return self.send_json(404, {"error": "no such book"})
        action(book)

    def set_progress(self, book, params):
        try:
            chapter, sentence = int(params["chapter"]), int(params["sentence"])
            if not 0 <= chapter < len(book["chapters"]) or sentence < 0:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return self.send_json(400, {"error": "chapter and sentence must be valid positions"})
        with library_lock:
            book["progress"] = {"chapter": chapter, "sentence": sentence}
            write_book(book)
        self.send_json(200, book["progress"])

    def chapter_audio(self, book, number, query):
        try:
            if not 0 <= number < len(book["chapters"]):
                raise ValueError("no such chapter")
            speed = float(query.get("speed", default_speed))
            wav = chapter_wav(book["chapters"][number], speed)
        except ValueError as e:
            return self.send_json(400, {"error": str(e)})
        with wav:
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(os.fstat(wav.fileno()).st_size))
            self.send_header("Content-Disposition", f'attachment; filename="chapter-{number + 1}.wav"')
            self.end_headers()
            try:
                while data := wav.read(1 << 16):
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    # speech

    def tts(self, params):
        try:
            text, opts, stream = parse(params)
            if stream:
                chunks = tts.stream(text, **opts)
                first = next(chunks, None)  # surface invalid settings before the headers go out
            else:
                speech = tts.say(text, **opts)
        except (ValueError, TypeError) as e:
            return self.send_json(400, {"error": str(e)})

        if not stream:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(speech.sample_rate)
                w.writeframes(pcm16(speech.audio))
            return self.send(200, "audio/wav", buf.getvalue(), {"X-Seed": speech.seed})

        # the length is not known up front, so the body ends when the connection closes
        self.send_response(200)
        self.send_header("Content-Type", "audio/L16")
        self.send_header("X-Sample-Rate", str(opts.get("sample_rate", 48000)))
        self.end_headers()
        try:
            while first is not None:
                self.wfile.write(pcm16(first))
                self.wfile.flush()
                first = next(chunks, None)
        except (BrokenPipeError, ConnectionResetError):
            chunks.close()  # the listener left, drop the rest of the work

    # plumbing

    def read_json(self):
        try:
            params = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if not isinstance(params, dict):
                raise ValueError
            return params
        except ValueError:
            self.send_json(400, {"error": "body must be a JSON object"})

    def send_file(self, path):
        path = path.resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            return self.send_json(404, {"error": "not found"})
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/"):
            content_type += "; charset=utf-8"
        self.send(200, content_type, path.read_bytes())

    def send_json(self, status, obj):
        self.send(status, "application/json", json.dumps(obj, ensure_ascii=False).encode())

    def send(self, status, content_type, body, headers={}):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers.items():
            self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(body)


def main():
    global tts, default_speed
    p = argparse.ArgumentParser(description="EMA Reader: a book and article reader for EMA Lightning")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to expose it to the network")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--speed", type=float, default=os.environ.get("EMA_SPEED", "1.0"),
                   help="speed for requests that do not set one (default 1.0, or set EMA_SPEED)")
    p.add_argument("--cpu", action="store_true", help="use the CPU instead of the GPU")
    p.add_argument("--lightning", action="store_true", help="NVIDIA fast path (startup takes minutes)")
    p.add_argument("--no-browser", action="store_true", help="do not open the reader in the browser")
    args = p.parse_args()
    if not 0.25 <= args.speed <= 4:
        p.error("--speed must be from 0.25 to 4")
    default_speed = args.speed

    from ema import load_model

    tts = load_model(args.cpu, args.lightning)
    tts.say("Merhaba.")  # warm-up: moves the first request's delay to startup

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"ready: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
