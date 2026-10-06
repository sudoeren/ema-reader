"""A simple HTTP API for EMA Lightning. Loads the model once and keeps it warm.

    uv run api.py                      # http://127.0.0.1:8000

    curl "localhost:8000/tts?text=Merhaba" -o merhaba.wav
    curl localhost:8000/tts -d '{"text": "Merhaba", "speed": 1.2}' -o merhaba.wav

Endpoints:
    GET  /health   status
    GET  /tts      parameters in the query string
    POST /tts      parameters in a JSON body

Parameters: text (required), speed, seed, sample_rate, stream.
The response is a WAV file. With stream=true, raw PCM (16-bit, mono) is sent as it is generated.
"""

import argparse
import io
import json
import os
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

import numpy as np

tts = None
default_speed = 1.0


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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif url.path == "/tts":
            self.tts(dict(parse_qsl(url.query)))
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/tts":
            return self.send_json(404, {"error": "not found"})
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            params = json.loads(body)
            if not isinstance(params, dict):
                raise ValueError
        except ValueError:
            return self.send_json(400, {"error": "body must be a JSON object"})
        self.tts(params)

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
    p = argparse.ArgumentParser(description="EMA Lightning HTTP API")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to expose it to the network")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--speed", type=float, default=os.environ.get("EMA_SPEED", "1.0"),
                   help="speed for requests that do not set one (default 1.0, or set EMA_SPEED)")
    p.add_argument("--cpu", action="store_true", help="use the CPU instead of the GPU")
    p.add_argument("--lightning", action="store_true", help="NVIDIA fast path (startup takes minutes)")
    args = p.parse_args()
    if not 0.25 <= args.speed <= 4:
        p.error("--speed must be from 0.25 to 4")
    default_speed = args.speed

    from ema import load_model

    tts = load_model(args.cpu, args.lightning)
    tts.say("Merhaba.")  # warm-up: moves the first request's delay to startup

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"ready: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
