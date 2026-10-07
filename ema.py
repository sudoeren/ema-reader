"""A minimal CLI for EMA Lightning: speaks Turkish text.

    uv run ema.py "Merhaba dünya"            # play through the speakers
    uv run ema.py "Merhaba" -o merhaba.wav   # write to a file
    uv run ema.py -f text.txt -o clips       # one clip per line: 0.wav, 1.wav, ...
    echo "Merhaba" | uv run ema.py           # read from stdin
    uv run ema.py                            # interactive mode

    uv run ema.py "Merhaba" --api http://127.0.0.1:8000   # use a running app.py (fast)
"""

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np


REPO = "canberkkkkkk/ema-lightning"
FILES = ("config.json", "ema.pt", "decoder.pt")
UPDATE_CHECK_INTERVAL = 24 * 3600


def best_device():
    """An NVIDIA card, else Apple silicon's GPU, else the processor. EMA Lightning's own "auto"
    knows only NVIDIA cards, so on a Mac it would always use the processor."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(cpu=False, lightning=False):
    import logging

    from huggingface_hub import constants, try_to_load_from_cache

    # the Hub answers anonymous requests with a "set a HF_TOKEN" notice; the model is public
    logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)

    # with the weights on disk, load without touching the network so startup stays fast
    cached = [try_to_load_from_cache(REPO, f) for f in FILES]
    offline = all(isinstance(path, str) for path in cached)
    constants.HF_HUB_OFFLINE = constants.HF_HUB_OFFLINE or offline

    # on Apple silicon, an operation the GPU lacks runs on the processor instead of failing
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    from ema_lightning import EMA

    device = "cpu" if cpu else best_device()
    tts = EMA(device=device)
    if device == "mps":
        try:
            tts.say("Merhaba.")
        except Exception:  # the model does not run on this Mac's GPU
            tts = EMA(device="cpu")
    if lightning:
        tts.lightning()

    if offline and not os.environ.get("HF_HUB_OFFLINE"):
        constants.HF_HUB_OFFLINE = False
        threading.Thread(target=update_model, args=(cached,)).start()
    return tts


def update_model(cached):
    """Once a day, fetch newer weights in the background; they are used from the next start."""
    from huggingface_hub import constants, hf_hub_download, model_info

    stamp = Path(constants.HF_HUB_CACHE) / ("models--" + REPO.replace("/", "--")) / ".last-update-check"
    try:
        if time.time() - stamp.stat().st_mtime < UPDATE_CHECK_INTERVAL:
            return
    except OSError:
        pass
    try:
        model_info(REPO)  # raises without network, where hf_hub_download quietly returns the cached files
        latest = [hf_hub_download(REPO, f) for f in FILES]
        stamp.touch()
    except Exception:
        return  # no network: try again on the next start
    if [os.path.realpath(p) for p in latest] != [os.path.realpath(p) for p in cached]:
        print("model güncellendi; yeni sürüm bir sonraki açılışta kullanılacak", file=sys.stderr)


class Local:
    """Loads the model in this process."""

    def __init__(self, cpu, lightning):
        self.tts = load_model(cpu, lightning)

    def stream(self, text, **opts):
        return self.tts.stream(text, **opts)

    def save(self, texts, paths, **opts):
        # all texts are generated together, in shared batches
        for speech, path in zip(self.tts.say(texts, **opts), paths):
            write_wav(path, speech.audio, speech.sample_rate)


class Remote:
    """Talks to a running app.py, so there is no model load to wait for."""

    def __init__(self, url):
        self.url = url.rstrip("/") + "/tts"

    def post(self, text, **opts):
        body = json.dumps({"text": text, **opts}).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            raise ValueError(json.loads(e.read())["error"]) from None
        except urllib.error.URLError as e:
            sys.exit(f"API'ye ulaşılamadı ({self.url}): {e.reason}")

    def stream(self, text, **opts):
        with self.post(text, stream=True, **opts) as resp:
            while data := resp.read(9600):
                yield np.frombuffer(data, "<i2").astype("float32") / 32768

    def save(self, texts, paths, **opts):
        for text, path in zip(texts, paths):
            with self.post(text, **opts) as resp:
                Path(path).write_bytes(resp.read())


def write_wav(path, audio, sample_rate):
    import wave

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    p = argparse.ArgumentParser(description="EMA Lightning ile Türkçe metni seslendirir")
    p.add_argument("text", nargs="*", help="seslendirilecek metin (verilmezse stdin ya da etkileşimli kip)")
    p.add_argument("-f", "--file", help="metin dosyası; her satır ayrı seslendirilir")
    p.add_argument("-o", "--out", help="çalmak yerine yaz: tek metin için bir .wav, birden çok satır için bir klasör")
    p.add_argument("--speed", type=float, default=os.environ.get("EMA_SPEED"),
                   help="0.25 ile 4 arası; 1'in altı daha yavaş (varsayılan 1.0, ya da EMA_SPEED)")
    p.add_argument("--seed", type=int, help="aynı seed aynı sesi verir")
    p.add_argument("--rate", type=int, default=48000, choices=[48000, 24000, 16000, 8000], help="örnekleme hızı")
    p.add_argument("--api", default=os.environ.get("EMA_API"), metavar="URL",
                   help="modeli yüklemek yerine çalışan bir app.py kullan (ya da EMA_API)")
    p.add_argument("--cpu", action="store_true", help="GPU yerine CPU kullan")
    p.add_argument("--lightning", action="store_true", help="NVIDIA hızlı yolu (açılış dakikalar sürer)")
    args = p.parse_args()

    if args.text:
        texts = [" ".join(args.text)]
    elif args.file:
        texts = Path(args.file).read_text(encoding="utf-8").splitlines()
    elif not sys.stdin.isatty():
        texts = sys.stdin.read().splitlines()
    else:
        texts = None  # interactive mode
    if texts is not None:
        texts = [t.strip() for t in texts if t.strip()]
        if not texts:
            p.error("seslendirilecek metin yok")
    elif args.out:
        p.error("-o için bir metin, -f ya da stdin gerekir")

    opts = {"sample_rate": args.rate}
    if args.speed is not None:  # left out so that an API started with its own --speed keeps it
        opts["speed"] = args.speed
    if args.seed is not None:
        opts["seed"] = args.seed

    backend = Remote(args.api) if args.api else Local(args.cpu, args.lightning)

    try:
        if args.out:
            save(backend, texts, Path(args.out), opts)
        else:
            play(backend, texts, args.rate, opts)
    except ValueError as e:
        sys.exit(f"hata: {e}")


def save(backend, texts, out, opts):
    if len(texts) == 1:
        paths = [out]
    else:
        out.mkdir(parents=True, exist_ok=True)
        paths = [out / f"{i}.wav" for i in range(len(texts))]
    start = time.perf_counter()
    backend.save(texts, paths, **opts)
    took = time.perf_counter() - start
    where = out if len(texts) == 1 else f"{out}/ ({len(texts)} ses)"
    print(f"{where}: {took * 1000:.0f} ms")


def play(backend, texts, rate, opts):
    import sounddevice as sd

    # open the speaker once: reopening it for every sentence costs ~100-400 ms
    speaker = sd.OutputStream(samplerate=rate, channels=1, dtype="float32")
    speaker.start()

    def speak(text):
        start = time.perf_counter()
        first = None
        for chunk in backend.stream(text, **opts):
            if first is None:
                first = time.perf_counter() - start
            speaker.write(chunk)
        if first is not None:
            print(f"ilk ses {first * 1000:.0f} ms içinde")

    if texts is not None:
        for text in texts:
            speak(text)
        speaker.stop()  # waits for the buffered audio to finish
        return

    if isinstance(backend, Local):
        for _ in backend.stream("Merhaba."):  # warm-up: moves the first sentence's ~500 ms delay to startup
            pass
    print("Bir metin yazıp Enter'a bas (/speed 0.8: hızı değiştir, Ctrl+C: sesi durdur, Ctrl+D: çık)")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue
        if not line:
            continue
        if line.startswith("/speed"):
            try:
                speed = float(line.split()[1])
                if not 0.25 <= speed <= 4:
                    raise ValueError
                opts["speed"] = speed
            except (IndexError, ValueError):
                print("kullanım: /speed 0.25-4")
            else:
                print(f"hız {speed}")
            continue
        try:
            speak(line)
        except KeyboardInterrupt:
            speaker.abort()
            speaker.start()
            print()
        except ValueError as e:
            print(f"hata: {e}")


if __name__ == "__main__":
    main()
