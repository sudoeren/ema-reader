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
                                               with ?preview=1 (or "preview": true) nothing is added yet: the answer
                                               describes what was found and carries a token
    POST   /api/pending/TOKEN                  add what was previewed
    DELETE /api/pending/TOKEN                  forget it
    GET    /api/pending/TOKEN/cover            its cover picture, if it has one
    GET    /api/books/ID                       one book with its text
    DELETE /api/books/ID
    PUT    /api/books/ID/progress              {"chapter": 0, "sentence": 12}
    GET    /api/books/ID/cover                 the cover picture, if the book has one
    POST   /api/books/ID/export                {"scope": "chapter" | "book", "chapter": 0, "format": "mp3", "split": false, "speed": 1}
    GET    /api/exports/JOB                    {"state": "working" | "ready" | "failed", "progress": 0.4, "name"}
    GET    /api/exports/JOB/file               the finished file
    DELETE /api/exports/JOB                    cancel
    GET    /api/books/ID/chapters/N/audio      a chapter as one WAV file
    GET    /api/update                         {"current", "latest", "newer", "notes", "page", "download", "packaged", "job"}; ?fresh=1 asks again
    POST   /api/update                         install the newer version and start again (from this computer only)
    GET    /api/setup                          what the first start downloads: {"ready", "choices", "using", "device", "job", ...}
    POST   /api/setup                          {"choice": "cuda" | "mps" | "cpu"}: download it (from this computer only)
    POST   /api/restart                        start again, to use what was downloaded (from this computer only)

Until the model is there, speech answers 503 with {"setup": true}; while it loads, requests wait for it.
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

import export
import runtime
import update
from extract import extract_file, extract_url

VERSION = "1.0.0"
ROOT = Path(__file__).parent
STATIC = ROOT / "static"
LIBRARY = Path(os.environ.get("EMA_READER_LIBRARY") or ROOT / "library")
MAX_UPLOAD = 200 * 1024 * 1024
BOOK = re.compile(r"/api/books/([0-9a-f]{12})(/progress|/cover|/export|/chapters/(\d+)/audio)?")
EXPORT = re.compile(r"/api/exports/([0-9a-f]{12})(/file)?")
PENDING = re.compile(r"/api/pending/([0-9a-f]{12})(/cover)?")

# exported chapters: sentences are generated in batches and joined with short pauses
EXPORT_RATE = 24000
EXPORT_BATCH = 32
SENTENCE_PAUSE = 0.15
PARAGRAPH_PAUSE = 0.5

tts = None
loading = threading.Event()  # set when the model starts loading
loaded = threading.Event()  # set when it is loaded, or could not be
load_error = None
options = {"cpu": False, "lightning": False}
default_speed = 1.0
library_lock = threading.Lock()
pending = {}  # what has been read and shown to the reader, but not added yet: token -> (book, source)


class NotReady(Exception):
    """The model is not there yet: it is downloaded on the first start."""


def model():
    """The loaded model; waits while it loads."""
    if not loading.is_set():
        raise NotReady("EMA Reader henüz hazır değil: ses modeli indirilmedi.")
    loaded.wait()
    if load_error:
        raise NotReady(load_error)
    return tts


def load():
    """Load the model; the first request then waits for it instead of failing."""
    global tts, load_error
    if loading.is_set():
        return
    loading.set()
    try:
        from ema import load_model

        tts = load_model(options["cpu"], options["lightning"])
        tts.say("Merhaba.")  # warm-up: moves the first request's delay to startup
    except Exception as e:
        load_error = f"Ses modeli yüklenemedi: {e}"
    loaded.set()


def pcm16(audio):
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def parse(params):
    """Convert request parameters to the types EMA expects."""
    text = params.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text zorunlu")
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


def cover_path(book_id):
    return LIBRARY / f"{book_id}.cover"


def read_book(book_id):
    return json.loads(book_path(book_id).read_text(encoding="utf-8"))


def write_book(book):
    LIBRARY.mkdir(parents=True, exist_ok=True)
    tmp = book_path(book["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    tmp.replace(book_path(book["id"]))


def store(book, source):
    """Put a freshly extracted book in the library; its cover picture goes in a file of its own."""
    picture = book.pop("cover", None)
    book.update(id=uuid.uuid4().hex[:12], source=source, added=time.time(), progress={"chapter": 0, "sentence": 0},
                cover=picture[1] if picture else None)
    with library_lock:
        write_book(book)
        if picture:
            cover_path(book["id"]).write_bytes(picture[0])
    return book


def preview(book, source):
    """Keep a freshly extracted book aside and describe it, so the reader can look before it is added."""
    token = uuid.uuid4().hex[:12]
    while len(pending) >= 4:  # previews nobody answered
        pending.pop(next(iter(pending)))
    pending[token] = (book, source)
    sentences = [s for c in book["chapters"] for p in c["paragraphs"] for s in p]
    excerpt = ""
    for sentence in sentences:
        if excerpt and len(excerpt) + len(sentence) > 320:
            break
        excerpt = f"{excerpt} {sentence}".strip()
    return {
        "token": token,
        "title": book["title"],
        "author": book["author"],
        "article": source.startswith(("http://", "https://")),
        "cover": bool(book.get("cover")),
        "chapters": len(book["chapters"]),
        "contents": [c["title"] for c in book["chapters"][:6]],
        "size": sum(map(len, sentences)),
        "excerpt": excerpt[:480],
    }


def summary(book):
    """What the library shows for a book; sizes are in characters, to estimate listening time."""
    sizes = [[len(s) for p in c["paragraphs"] for s in p] for c in book["chapters"]]
    progress = book["progress"]
    done = sum(map(sum, sizes[: progress["chapter"]])) + sum(sizes[progress["chapter"]][: progress["sentence"]])
    return {
        "id": book["id"],
        "title": book["title"],
        "author": book["author"],
        "article": book["source"].startswith(("http://", "https://")),
        "cover": bool(book.get("cover")),
        "added": book["added"],
        "opened": book.get("opened", 0),
        "chapter": progress["chapter"],
        "chapter_title": book["chapters"][progress["chapter"]]["title"],
        "chapters": len(sizes),
        "size": sum(map(sum, sizes)),
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
        speeches = model().say([s for s, _ in batch], speed=speed, sample_rate=EXPORT_RATE)
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
            self.send_json(200, {"status": "ok", "version": VERSION})
        elif url.path == "/tts":
            self.tts(query)
        elif url.path == "/api/update":
            self.send_json(200, update.check(VERSION, fresh=query.get("fresh") == "1"))
        elif url.path == "/api/setup":
            device = str(tts.device.type) if tts is not None else None
            self.send_json(200, {**runtime.status(), "device": device, "loading": loading.is_set() and not loaded.is_set(),
                                 "error": load_error})
        elif url.path == "/api/books":
            self.list_books()
        elif book and not book.group(2):
            self.with_book(book.group(1), lambda b: self.send_json(200, b))
        elif book and book.group(2) == "/cover":
            self.with_book(book.group(1), self.cover)
        elif EXPORT.fullmatch(url.path):
            self.export_get(*EXPORT.fullmatch(url.path).groups())
        elif PENDING.fullmatch(url.path) and PENDING.fullmatch(url.path).group(2):
            picture = (pending.get(PENDING.fullmatch(url.path).group(1)) or ({},))[0].get("cover")
            if not picture:
                return self.send_json(404, {"error": "Bulunamadı."})
            self.send(200, picture[1] or "application/octet-stream", picture[0])
        elif book and book.group(3):
            self.with_book(book.group(1), lambda b: self.chapter_audio(b, int(book.group(3)), query))
        else:
            self.send_json(404, {"error": "Bulunamadı."})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/tts":
            params = self.read_json()
            if params is not None:
                self.tts(params)
        elif url.path == "/api/update":
            self.update()
        elif url.path == "/api/setup":
            self.start_setup()
        elif url.path == "/api/restart":
            self.restart_app()
        elif url.path == "/api/books":
            self.add_book(dict(parse_qsl(url.query)))
        elif PENDING.fullmatch(url.path) and not PENDING.fullmatch(url.path).group(2):
            found = pending.pop(PENDING.fullmatch(url.path).group(1), None)
            if not found:
                return self.send_json(404, {"error": "Bu önizlemenin süresi dolmuş. Dosyayı yeniden seç."})
            self.send_json(201, summary(store(*found)))
        elif BOOK.fullmatch(url.path) and BOOK.fullmatch(url.path).group(2) == "/export":
            params = self.read_json()
            if params is not None:
                self.with_book(BOOK.fullmatch(url.path).group(1), lambda b: self.export_start(b, params))
        else:
            self.send_json(404, {"error": "Bulunamadı."})

    def do_PUT(self):
        book = BOOK.fullmatch(urlparse(self.path).path)
        if not book or book.group(2) != "/progress":
            return self.send_json(404, {"error": "Bulunamadı."})
        params = self.read_json()
        if params is not None:
            self.with_book(book.group(1), lambda b: self.set_progress(b, params))

    def do_DELETE(self):
        path = urlparse(self.path).path
        if PENDING.fullmatch(path) and not PENDING.fullmatch(path).group(2):
            pending.pop(PENDING.fullmatch(path).group(1), None)
            return self.send_json(200, {"forgotten": PENDING.fullmatch(path).group(1)})
        job = EXPORT.fullmatch(path)
        if job and not job.group(2):
            found = export.jobs.get(job.group(1))
            if found:
                found.cancelled.set()
                if found.state != "working":
                    found.clean()
            return self.send_json(200, {"cancelled": job.group(1)})
        book = BOOK.fullmatch(path)
        if not book or book.group(2):
            return self.send_json(404, {"error": "Bulunamadı."})
        with library_lock:
            book_path(book.group(1)).unlink(missing_ok=True)
            cover_path(book.group(1)).unlink(missing_ok=True)
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
                raise ValueError("Dosya çok büyük.")
            body = self.rfile.read(length)
            look = query.get("preview") in ("1", "true")
            if query.get("name"):
                source = query["name"]
                book = extract_file(source, body)
            else:
                asked = json.loads(body)
                source, look = asked.get("url", ""), look or asked.get("preview") is True
                book = extract_url(source)
        except ValueError as e:
            return self.send_json(400, {"error": str(e) or "İstek okunamadı."})
        except Exception:  # a damaged file should not take the server down
            return self.send_json(400, {"error": "Bu dosya okunamadı; bozuk olabilir."})
        if look:
            return self.send_json(200, preview(book, source))
        self.send_json(201, summary(store(book, source)))

    def with_book(self, book_id, action):
        try:
            book = read_book(book_id)
        except FileNotFoundError:
            return self.send_json(404, {"error": "Böyle bir kitap yok."})
        action(book)

    def set_progress(self, book, params):
        try:
            chapter, sentence = int(params["chapter"]), int(params["sentence"])
            if not 0 <= chapter < len(book["chapters"]) or sentence < 0:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return self.send_json(400, {"error": "chapter ve sentence geçerli konumlar olmalı"})
        with library_lock:
            book["progress"] = {"chapter": chapter, "sentence": sentence}
            book["opened"] = time.time()
            write_book(book)
        self.send_json(200, book["progress"])

    def cover(self, book):
        try:
            self.send(200, book.get("cover") or "application/octet-stream", cover_path(book["id"]).read_bytes(),
                      {"Cache-Control": "max-age=31536000, immutable"})
        except FileNotFoundError:
            self.send_json(404, {"error": "Bu kitabın kapağı yok."})

    def from_app(self):
        """Whether the request comes from the app's own page on this computer: installing and restarting are for the
        reader at this computer only, not for others on the network, and not for a web page open in the browser,
        which cannot send this header to another site."""
        if self.client_address[0] in ("127.0.0.1", "::1") and self.headers.get("X-EMA-Reader") == "update":
            return True
        self.send_json(403, {"error": "Bu yalnızca uygulamanın içinden yapılabilir."})

    def start_setup(self):
        params = self.read_json()
        if params is None or not self.from_app():
            return
        try:
            self.send_json(202, runtime.start(str(params.get("choice")), done=load))
        except ValueError as e:
            self.send_json(400, {"error": str(e)})

    def restart_app(self):
        if self.from_app():
            self.send_json(202, {})
            threading.Thread(target=update.restart, daemon=True).start()

    def update(self):
        if not self.from_app():
            return
        try:
            self.send_json(202, update.start(VERSION))
        except ValueError as e:
            self.send_json(400, {"error": str(e)})

    # keeping: a chapter or a book as audio or text files

    def export_start(self, book, params):
        try:
            job = export.start(model(), book, scope=params.get("scope", "chapter"), chapter=int(params.get("chapter", 0)),
                               kind=params.get("format", "mp3"), split=params.get("split", False),
                               speed=float(params.get("speed", default_speed)))
        except (ValueError, TypeError) as e:
            return self.send_json(400, {"error": str(e)})
        except NotReady as e:
            return self.send_json(503, {"error": str(e), "setup": True})
        self.send_json(202, {"job": job.id, "name": job.name})

    def export_get(self, job_id, wants_file):
        job = export.jobs.get(job_id)
        if not job:
            return self.send_json(404, {"error": "Böyle bir dışa aktarım yok."})
        if not wants_file:
            return self.send_json(200, {"state": job.state, "progress": round(job.progress, 3), "name": job.name, "error": job.error})
        if job.state != "ready":
            return self.send_json(409, {"error": "Dışa aktarım henüz hazır değil."})
        self.send_download(job.path, job.name)
        job.clean()

    def send_download(self, path, name):
        from urllib.parse import quote

        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(os.path.getsize(path)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                while data := f.read(1 << 16):
                    self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def chapter_audio(self, book, number, query):
        try:
            if not 0 <= number < len(book["chapters"]):
                raise ValueError("Böyle bir bölüm yok.")
            speed = float(query.get("speed", default_speed))
            wav = chapter_wav(book["chapters"][number], speed)
        except ValueError as e:
            return self.send_json(400, {"error": str(e)})
        except NotReady as e:
            return self.send_json(503, {"error": str(e), "setup": True})
        with wav:
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(os.fstat(wav.fileno()).st_size))
            self.send_header("Content-Disposition", f'attachment; filename="bolum-{number + 1}.wav"')
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
                chunks = model().stream(text, **opts)
                first = next(chunks, None)  # surface invalid settings before the headers go out
            else:
                speech = model().say(text, **opts)
        except (ValueError, TypeError) as e:
            return self.send_json(400, {"error": str(e)})
        except NotReady as e:
            return self.send_json(503, {"error": str(e), "setup": True})

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
            self.send_json(400, {"error": "Gövde bir JSON nesnesi olmalı."})

    def send_file(self, path):
        path = path.resolve()
        if STATIC.resolve() not in path.parents or not path.is_file():
            return self.send_json(404, {"error": "Bulunamadı."})
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


def start(host="127.0.0.1", port=8000, speed=1.0, cpu=False, lightning=False):
    """Return a server that is ready for serve_forever(). The model loads in the background, if it is there;
    otherwise the page offers to download it."""
    global default_speed
    default_speed = speed
    options.update(cpu=cpu, lightning=lightning)
    if runtime.ready():
        threading.Thread(target=load, daemon=True).start()
    return ThreadingHTTPServer((host, port), Handler)


def main():
    p = argparse.ArgumentParser(description="EMA Reader: EMA Lightning ile kitap ve makale okuyucu")
    p.add_argument("--host", default="127.0.0.1", help="ağa açmak için 0.0.0.0")
    p.add_argument("--port", type=int, default=8000, help="port (varsayılan 8000)")
    p.add_argument("--speed", type=float, default=os.environ.get("EMA_SPEED", "1.0"),
                   help="hız belirtmeyen istekler için hız (varsayılan 1.0, ya da EMA_SPEED)")
    p.add_argument("--cpu", action="store_true", help="GPU yerine CPU kullan")
    p.add_argument("--lightning", action="store_true", help="NVIDIA hızlı yolu (açılış dakikalar sürer)")
    p.add_argument("--no-browser", action="store_true", help="okuyucuyu tarayıcıda açma")
    args = p.parse_args()
    if not 0.25 <= args.speed <= 4:
        p.error("--speed 0.25 ile 4 arasında olmalı")

    server = start(args.host, args.port, args.speed, args.cpu, args.lightning)
    url = f"http://{args.host}:{args.port}"
    print(f"hazır: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
