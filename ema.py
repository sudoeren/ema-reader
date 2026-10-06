"""EMA Lightning için minimal CLI: metni Türkçe seslendirir.

    uv run ema.py "Merhaba dünya"            # hoparlörden çal
    uv run ema.py "Merhaba" -o merhaba.wav   # dosyaya yaz
    uv run ema.py -f metin.txt -o klipler    # her satır ayrı klip: 0.wav, 1.wav, ...
    echo "Merhaba" | uv run ema.py           # stdin'den oku
    uv run ema.py                            # etkileşimli mod

    uv run ema.py "Merhaba" --api http://127.0.0.1:8000   # açık duran api.py'yi kullan (hızlı)
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np


def load_model(cpu=False, lightning=False):
    from huggingface_hub import constants, try_to_load_from_cache

    # ağırlıklar diskteyse Hub'a hiç bağlanma: açılış hızlanır, HF_TOKEN uyarısı çıkmaz
    files = ("config.json", "ema.pt", "decoder.pt")
    if all(isinstance(try_to_load_from_cache("canberkkkkkk/ema-lightning", f), str) for f in files):
        constants.HF_HUB_OFFLINE = True

    from ema_lightning import EMA

    tts = EMA(device="cpu" if cpu else "auto")
    if lightning:
        tts.lightning()
    return tts


class Local:
    """Modeli bu süreçte yükler."""

    def __init__(self, cpu, lightning):
        self.tts = load_model(cpu, lightning)

    def stream(self, text, **opts):
        return self.tts.stream(text, **opts)

    def save(self, texts, paths, **opts):
        # hepsi tek seferde, ortak batch'lerde üretilir
        for speech, path in zip(self.tts.say(texts, **opts), paths):
            write_wav(path, speech.audio, speech.sample_rate)


class Remote:
    """Açık duran api.py'ye bağlanır; model yükleme beklemesi olmaz."""

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
    p = argparse.ArgumentParser(description="EMA Lightning Türkçe TTS")
    p.add_argument("text", nargs="*", help="seslendirilecek metin (boşsa stdin ya da etkileşimli mod)")
    p.add_argument("-f", "--file", help="metin dosyası; her satır ayrı seslendirilir")
    p.add_argument("-o", "--out", help="çalmak yerine yaz: tek metin için .wav, birden çok satır için klasör")
    p.add_argument("--speed", type=float, default=1.0, help="0.25 - 4 (varsayılan 1.0)")
    p.add_argument("--seed", type=int, help="aynı seed aynı sesi verir")
    p.add_argument("--rate", type=int, default=48000, choices=[48000, 24000, 16000, 8000], help="örnekleme hızı")
    p.add_argument("--api", default=os.environ.get("EMA_API"), metavar="URL",
                   help="modeli yüklemek yerine açık duran api.py'yi kullan (ya da EMA_API ortam değişkeni)")
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
        texts = None  # etkileşimli mod
    if texts is not None:
        texts = [t.strip() for t in texts if t.strip()]
        if not texts:
            p.error("seslendirilecek metin yok")
    elif args.out:
        p.error("-o için metin, -f ya da stdin gerekli")

    opts = {"speed": args.speed, "sample_rate": args.rate}
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
    where = out if len(texts) == 1 else f"{out}/ ({len(texts)} klip)"
    print(f"{where}: {took * 1000:.0f} ms")


def play(backend, texts, rate, opts):
    import sounddevice as sd

    # hoparlörü bir kez aç: her cümlede yeniden açmak ~100-400 ms sürüyor
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
            print(f"ilk ses {first * 1000:.0f} ms")

    if texts is not None:
        for text in texts:
            speak(text)
        speaker.stop()  # tampondaki sesin bitmesini bekler
        return

    if isinstance(backend, Local):
        for _ in backend.stream("Merhaba."):  # ısınma: ilk cümlenin ~500 ms gecikmesini açılışa taşır
            pass
    print("Metin yazıp Enter'a basın (Ctrl+C: sesi kes, Ctrl+D: çıkış)")
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
