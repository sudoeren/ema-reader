"""Turns a chapter or a whole book into files to keep: audio in several formats, or plain text.

    job = start(tts, book, scope="book", chapter=0, kind="mp3", split=True, speed=1.0)
    job.progress      # 0..1
    job.state         # "working", "ready", "failed" or "cancelled"
    job.path, job.name

A book can take minutes, so the work runs in a thread and the caller polls.
"""

import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path

import numpy as np

# kind: (extension, soundfile format, subtype, sample rate); speech is small and clear at 24 kHz
AUDIO = {
    "mp3": ("mp3", "MP3", "MPEG_LAYER_III", 24000),
    "ogg": ("ogg", "OGG", "VORBIS", 24000),
    "opus": ("opus", "OGG", "OPUS", 24000),
    "flac": ("flac", "FLAC", "PCM_16", 48000),
    "wav": ("wav", "WAV", "PCM_16", 48000),
}
KINDS = (*AUDIO, "txt")
BATCH = 32
SENTENCE_PAUSE = 0.15
PARAGRAPH_PAUSE = 0.5
CHAPTER_PAUSE = 1.2

jobs = {}


def safe(name):
    """A file name that every system accepts."""
    return " ".join(re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name).split()).strip(" .")[:80] or "EMA Reader"


def chapter_name(book, number):
    title = book["chapters"][number]["title"]
    return f"{number + 1:02d} {title}" if title else f"{number + 1:02d}"


def chapter_text(book, number):
    chapter = book["chapters"][number]
    head = [chapter["title"], ""] if chapter["title"] else []
    return "\n\n".join(head[:1] + [" ".join(p) for p in chapter["paragraphs"]])


class Job:
    def __init__(self, tts, book, scope, chapter, kind, split, speed):
        self.id = uuid.uuid4().hex[:12]
        self.tts, self.book, self.kind, self.speed = tts, book, kind, speed
        self.numbers = [chapter] if scope == "chapter" else list(range(len(book["chapters"])))
        self.split = split and len(self.numbers) > 1
        self.folder = Path(tempfile.mkdtemp(prefix="ema-reader-"))
        self.state, self.progress, self.error = "working", 0.0, None
        self.cancelled = threading.Event()
        ext = "txt" if kind == "txt" else AUDIO[kind][0]
        base = safe(book["title"])
        if scope == "chapter" and len(book["chapters"]) > 1:
            base = safe(f"{book['title']} - {chapter_name(book, chapter)}")
        self.name = f"{base}.zip" if self.split else f"{base}.{ext}"
        self.path = self.folder / ("out.zip" if self.split else f"out.{ext}")
        self.total = sum(len(p) for n in self.numbers for p in book["chapters"][n]["paragraphs"]) or 1
        self.done = 0

    def run(self):
        try:
            if self.kind == "txt":
                self.write_text()
            else:
                self.write_audio()
            self.state = "cancelled" if self.cancelled.is_set() else "ready"
            self.progress = 1.0
        except Exception as e:
            self.state, self.error = "failed", str(e)
        if self.state != "ready":
            self.clean()

    def write_text(self):
        ext = "txt"
        if self.split:
            with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as z:
                for n in self.numbers:
                    z.writestr(f"{safe(chapter_name(self.book, n))}.{ext}", chapter_text(self.book, n))
        else:
            self.path.write_text("\n\n\n".join(chapter_text(self.book, n) for n in self.numbers), encoding="utf-8")

    def write_audio(self):
        import soundfile

        ext, fmt, subtype, rate = AUDIO[self.kind]

        def open_file(path):
            return soundfile.SoundFile(str(path), "w", samplerate=rate, channels=1, format=fmt, subtype=subtype)

        def silence(seconds):
            return np.zeros(int(seconds * rate), dtype="float32")

        def speak(out, number):
            chapter = self.book["chapters"][number]
            texts = [(s, i == len(p) - 1) for p in chapter["paragraphs"] for i, s in enumerate(p)]
            if chapter["title"]:
                texts.insert(0, (chapter["title"], True))  # the chapter's name is read out too
                self.total += 1
            for start in range(0, len(texts), BATCH):
                if self.cancelled.is_set():
                    return
                batch = texts[start : start + BATCH]
                speeches = self.tts.say([s for s, _ in batch], speed=self.speed, sample_rate=rate)
                for speech, (_, ends_paragraph) in zip(speeches, batch):
                    out.write(np.clip(speech.audio, -1, 1))
                    out.write(silence(PARAGRAPH_PAUSE if ends_paragraph else SENTENCE_PAUSE))
                self.done += len(batch)
                self.progress = min(0.99, self.done / self.total)

        if self.split:
            parts = self.folder / "parts"
            parts.mkdir()
            with zipfile.ZipFile(self.path, "w", zipfile.ZIP_STORED) as z:
                for n in self.numbers:
                    part = parts / f"{n}.{ext}"
                    with open_file(part) as out:
                        speak(out, n)
                    if self.cancelled.is_set():
                        return
                    z.write(part, f"{safe(chapter_name(self.book, n))}.{ext}")
                    part.unlink()
        else:
            with open_file(self.path) as out:
                for i, n in enumerate(self.numbers):
                    if i:
                        out.write(silence(CHAPTER_PAUSE))
                    speak(out, n)

    def clean(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        jobs.pop(self.id, None)


def start(tts, book, scope="chapter", chapter=0, kind="mp3", split=False, speed=1.0):
    if kind not in KINDS:
        raise ValueError(f"format must be one of {', '.join(KINDS)}")
    if scope not in ("chapter", "book"):
        raise ValueError("scope must be chapter or book")
    if not 0 <= chapter < len(book["chapters"]):
        raise ValueError("no such chapter")
    if not 0.25 <= speed <= 4:
        raise ValueError("speed must be a number from 0.25 to 4")
    job = Job(tts, book, scope, chapter, kind, bool(split), speed)
    jobs[job.id] = job
    threading.Thread(target=job.run, daemon=True).start()
    return job
