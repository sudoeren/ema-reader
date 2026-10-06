"""EMA Lightning için minimal CLI: metni Türkçe seslendirir.

    uv run ema.py "Merhaba dünya"            # hoparlörden çal
    uv run ema.py "Merhaba" -o merhaba.wav   # dosyaya yaz
    uv run ema.py                            # etkileşimli mod
"""

import argparse
import sys
import time


def main():
    p = argparse.ArgumentParser(description="EMA Lightning Türkçe TTS")
    p.add_argument("text", nargs="*", help="seslendirilecek metin (boşsa etkileşimli mod)")
    p.add_argument("-o", "--out", help="çalmak yerine bu .wav dosyasına yaz")
    p.add_argument("--speed", type=float, default=1.0, help="0.25 - 4 (varsayılan 1.0)")
    p.add_argument("--seed", type=int, help="aynı seed aynı sesi verir")
    p.add_argument("--lightning", action="store_true", help="NVIDIA hızlı yolu (ilk açılış yavaş)")
    args = p.parse_args()

    from ema_lightning import EMA

    tts = EMA()
    if args.lightning:
        tts.lightning()

    opts = {"speed": args.speed}
    if args.seed is not None:
        opts["seed"] = args.seed

    def speak(text):
        start = time.perf_counter()
        if args.out:
            speech = tts.say(text, path=args.out, **opts)
            took = time.perf_counter() - start
            print(f"{args.out}: {speech.duration:.2f} sn ses, {took * 1000:.0f} ms, seed {speech.seed}")
            return
        first = None
        for chunk in tts.stream(text, **opts):
            if first is None:
                first = time.perf_counter() - start
            speaker.write(chunk)
        if first is not None:
            print(f"ilk ses {first * 1000:.0f} ms")

    if not args.out:
        import sounddevice as sd

        # hoparlörü bir kez aç: her cümlede yeniden açmak ~100-400 ms sürüyor
        speaker = sd.OutputStream(samplerate=48000, channels=1, dtype="float32")
        speaker.start()

    if args.text:
        speak(" ".join(args.text))
        if not args.out:
            speaker.stop()  # tampondaki sesin bitmesini bekler
        return

    for _ in tts.stream("Merhaba."):  # ısınma: ilk cümlenin ~500 ms gecikmesini açılışa taşır
        pass
    print("Metin yazıp Enter'a basın (çıkış: Ctrl+D)")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line:
            speak(line)


if __name__ == "__main__":
    sys.exit(main())
