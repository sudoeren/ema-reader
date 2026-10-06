"""EMA Reader as a desktop app: the reader in its own window, with no terminal or browser.

    uv run --extra desktop desktop.py

The window opens at once with a loading screen while the model loads, then shows the reader.
Books are kept in the user's data folder. `--check` starts everything without a window, makes
one sentence of audio and exits, which is how a packaged build is tested.
"""

import os
import socket
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).parent
NAME = "EMA Reader"
PORT = 47800  # fixed, so that settings the page stores in the browser survive a restart

SPLASH = """<!doctype html><meta charset="utf-8"><style>
html,body{height:100%;margin:0}body{display:grid;place-items:center;font-family:system-ui,sans-serif;color:#6b6b75;background:#fff}
div{text-align:center}img{width:72px;height:72px;display:block;margin:0 auto 18px;animation:p 1.6s ease-in-out infinite}
@keyframes p{50%{opacity:.45}}</style><div><img src="data:image/svg+xml;base64,LOGO" alt=""><span></span></div>
<script>document.querySelector("span").textContent=(navigator.language||"tr").toLowerCase().startsWith("tr")?"EMA Reader açılıyor…":"Starting EMA Reader…"</script>"""


def data_dir():
    """The per-user folder for the library and settings."""
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return base / NAME


def free_port():
    """PORT if it is free, otherwise any free port."""
    for port in (PORT, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue


def prepare():
    data = data_dir()
    os.environ.setdefault("EMA_READER_LIBRARY", str(data / "library"))
    # a packaged build ships the model weights, so the first start needs no download
    if (ROOT / "hf").is_dir():
        os.environ["HF_HOME"] = str(ROOT / "hf")
        os.environ["HF_HUB_OFFLINE"] = "1"
    return data


def check():
    prepare()
    import app

    server = app.start(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    from urllib.request import urlopen

    port = server.server_address[1]
    page = urlopen(f"http://127.0.0.1:{port}/").read()
    wav = urlopen(f"http://127.0.0.1:{port}/tts?text=Merhaba").read()
    assert b"EMA Reader" in page and wav[:4] == b"RIFF", "the app did not answer as expected"
    print(f"ok: page {len(page)} bytes, audio {len(wav)} bytes")


def main():
    if "--check" in sys.argv:
        return check()
    data = prepare()

    import base64

    import webview

    logo = base64.b64encode((ROOT / "static" / "logo.svg").read_bytes()).decode()
    window = webview.create_window(NAME, html=SPLASH.replace("LOGO", logo), width=1220, height=820, min_size=(420, 560))

    def load():
        import app

        server = app.start(port=free_port())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        window.load_url(f"http://127.0.0.1:{server.server_address[1]}/")

    webview.settings["ALLOW_DOWNLOADS"] = True  # "download chapter"
    webview.start(load, private_mode=False, storage_path=str(data / "webview"), icon=str(ROOT / "static" / "logo.png"))


if __name__ == "__main__":
    main()
