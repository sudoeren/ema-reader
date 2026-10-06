"""EMA Reader as a desktop app: the reader in its own window, with no terminal or browser.

    uv run --extra desktop desktop.py
    uv run --extra desktop desktop.py kitap.epub     # add a file and open it

The window opens at once with a loading screen while the model loads, then shows the reader.
On Linux it is a GTK 4 / libadwaita window whose header bar holds the app's controls; on
Windows and macOS it is the system's web view.
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
# fixed, so that settings the page stores in the browser survive a restart
PORT = int(os.environ.get("EMA_READER_PORT", 47800))

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


WORDS = {
    "tr": {"back": "Kitaplığa dön", "add": "Kitap ya da makale ekle", "search": "Kitaplığında ara",
           "chapters": "Bölümler", "download": "Bu bölümü ses dosyası olarak indir", "saved": "İndirilenler klasörüne kaydedildi: {}"},
    "en": {"back": "Back to library", "add": "Add a book or article", "search": "Search your library",
           "chapters": "Chapters", "download": "Download this chapter as an audio file", "saved": "Saved to Downloads: {}"},
}


def start_server(ready):
    """Load the model off the main thread, then hand the reader's address to `ready`."""
    def load():
        import app

        server = app.start(port=free_port())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        # a file given on the command line ("open with EMA Reader") is added and opened
        files = [Path(a) for a in sys.argv[1:] if not a.startswith("-") and Path(a).is_file()]
        if files:
            try:
                book = app.store(app.extract_file(files[0].name, files[0].read_bytes()), files[0].name)
                url += f"#book={book['id']}"
            except Exception:
                pass  # an unreadable file just opens the library
        ready(url)

    threading.Thread(target=load, daemon=True).start()


def run_gtk(data, splash):
    """The window on Linux: GTK 4 and libadwaita, with the app's controls in the header bar."""
    import json
    import locale

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk, WebKit

    words = WORDS["tr" if (locale.getlocale()[0] or "").lower().startswith("tr") else "en"]

    def activate(application):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)  # the reader is light
        css = Gtk.CssProvider()
        css.load_from_string("window, headerbar { background: #fff; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # what the page tells the window, and the page itself
        manager = WebKit.UserContentManager()
        manager.register_script_message_handler("shell", None)
        manager.add_script(WebKit.UserScript("window.emaShell = true;", WebKit.UserContentInjectedFrames.TOP_FRAME,
                                             WebKit.UserScriptInjectionTime.START, None, None))
        session = WebKit.NetworkSession.new(str(data / "webview"), str(data / "webview-cache"))  # keeps page settings
        web = WebKit.WebView(user_content_manager=manager, network_session=session,
                             website_policies=WebKit.WebsitePolicies(autoplay=WebKit.AutoplayPolicy.ALLOW))
        web.set_background_color(Gdk.RGBA(1, 1, 1, 1))

        def act(name):
            return lambda *_: web.evaluate_javascript(f"shellAction({json.dumps(name)})", -1, None, None, None, None, None)

        def button(icon, word, side):
            b = Gtk.Button(icon_name=icon, tooltip_text=words[word], visible=False)
            b.connect("clicked", act(word))
            (header.pack_start if side == "start" else header.pack_end)(b)
            return b

        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title=NAME)
        header.set_title_widget(title)
        back = button("go-previous-symbolic", "back", "start")
        add = button("list-add-symbolic", "add", "start")
        chapters = button("view-list-symbolic", "chapters", "end")
        download = button("folder-download-symbolic", "download", "end")
        search = button("system-search-symbolic", "search", "end")

        def on_message(_manager, value):
            # {"view": "library" | "reader", "title", "subtitle", "empty", "chapters"}
            state = json.loads(value.to_json(0))
            reader = state["view"] == "reader"
            title.set_title(state.get("title") or NAME)
            title.set_subtitle(state.get("subtitle") or "")
            back.set_visible(reader)
            download.set_visible(reader)
            chapters.set_visible(reader and state.get("chapters", False))
            add.set_visible(not reader and not state.get("empty", False))
            search.set_visible(not reader and not state.get("empty", False))

        manager.connect("script-message-received::shell", on_message)

        toasts = Adw.ToastOverlay(child=web)

        def on_download(_session, download):
            def decide(download, name):
                folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or str(Path.home())
                target = Path(folder) / name
                number = 1
                while target.exists():
                    number += 1
                    target = Path(folder) / f"{Path(name).stem} ({number}){Path(name).suffix}"
                download.set_destination(str(target))
                download.connect("finished", lambda *_: toasts.add_toast(Adw.Toast(title=words["saved"].format(target.name))))
                return True

            download.connect("decide-destination", decide)

        session.connect("download-started", on_download)

        view = Adw.ToolbarView(content=toasts)
        view.add_top_bar(header)
        window = Adw.ApplicationWindow(application=application, title=NAME, default_width=1220, default_height=820, content=view)
        window.set_size_request(420, 560)
        web.load_html(splash, None)
        window.present()
        start_server(lambda url: GLib.idle_add(web.load_uri, url))

    application = Adw.Application(application_id="io.github.emareader.EMAReader", flags=Gio.ApplicationFlags.NON_UNIQUE)
    application.connect("activate", activate)
    application.run(None)


def run_webview(data, splash):
    """The window everywhere else: the system's own web view, with its normal title bar."""
    import webview

    window = webview.create_window(NAME, html=splash, width=1220, height=820, min_size=(420, 560))
    webview.settings["ALLOW_DOWNLOADS"] = True  # "download chapter"
    webview.start(lambda: start_server(window.load_url), private_mode=False, storage_path=str(data / "webview"),
                  icon=str(ROOT / "static" / "logo.png"))


def main():
    if "--check" in sys.argv:
        return check()
    data = prepare()

    import base64

    splash = SPLASH.replace("LOGO", base64.b64encode((ROOT / "static" / "logo.svg").read_bytes()).decode())
    if sys.platform == "linux":
        try:
            import gi  # noqa: F401
        except ImportError:
            pass  # a build without GTK bindings
        else:
            return run_gtk(data, splash)
    run_webview(data, splash)


if __name__ == "__main__":
    main()
