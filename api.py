"""EMA Lightning için basit HTTP API. Modeli bir kez yükler ve sıcak tutar.

    uv run api.py                      # http://127.0.0.1:8000

    curl "localhost:8000/tts?text=Merhaba" -o merhaba.wav
    curl localhost:8000/tts -d '{"text": "Merhaba", "speed": 1.2}' -o merhaba.wav

Uç noktalar:
    GET  /health   durum
    GET  /tts      parametreler sorgu dizgisinde
    POST /tts      parametreler JSON gövdede

Parametreler: text (zorunlu), speed, seed, sample_rate, stream.
Yanıt bir WAV dosyasıdır. stream=true ise ham PCM (16 bit, mono) üretildikçe akar.
"""

import argparse
import io
import json
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

import numpy as np

tts = None


def pcm16(audio):
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def parse(params):
    """İstek parametrelerini EMA'nın beklediği türlere çevirir."""
    text = params.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text zorunlu")
    opts = {}
    if params.get("speed") is not None:
        opts["speed"] = float(params["speed"])
    if params.get("seed") is not None:
        opts["seed"] = int(params["seed"])
    if params.get("sample_rate") is not None:
        opts["sample_rate"] = int(params["sample_rate"])
    stream = str(params.get("stream", "")).lower() in ("1", "true")
    return text, opts, stream


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif url.path == "/tts":
            self.tts(dict(parse_qsl(url.query)))
        else:
            self.send_json(404, {"error": "bulunamadı"})

    def do_POST(self):
        if urlparse(self.path).path != "/tts":
            return self.send_json(404, {"error": "bulunamadı"})
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            params = json.loads(body)
            if not isinstance(params, dict):
                raise ValueError
        except ValueError:
            return self.send_json(400, {"error": "gövde bir JSON nesnesi olmalı"})
        self.tts(params)

    def tts(self, params):
        try:
            text, opts, stream = parse(params)
            if stream:
                chunks = tts.stream(text, **opts)
                first = next(chunks, None)  # ayar hataları başlıklar gitmeden ortaya çıksın
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

        # uzunluk baştan bilinmediği için gövde bağlantı kapanınca biter
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
            chunks.close()  # dinleyen gitti, kalan işi bırak

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
    global tts
    p = argparse.ArgumentParser(description="EMA Lightning HTTP API")
    p.add_argument("--host", default="127.0.0.1", help="ağa açmak için 0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--cpu", action="store_true", help="GPU yerine CPU kullan")
    p.add_argument("--lightning", action="store_true", help="NVIDIA hızlı yolu (açılış dakikalar sürer)")
    args = p.parse_args()

    from ema_lightning import EMA

    tts = EMA(device="cpu" if args.cpu else "auto")
    if args.lightning:
        tts.lightning()
    tts.say("Merhaba.")  # ısınma: ilk isteğin gecikmesini açılışa taşır

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"hazır: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
