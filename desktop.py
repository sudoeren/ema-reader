"""EMA Reader as a desktop app: the reader in its own window, with no terminal or browser.

    uv run --extra desktop desktop.py
    uv run --extra desktop desktop.py kitap.epub     # add a file and open it

The window opens at once with a loading screen while the model loads, then shows the reader.
On Linux it is a GTK 4 / libadwaita window whose header bar holds the app's controls; on
Windows and macOS it is the system's web view.

On Linux, `--install` adds EMA Reader to the applications menu with its icon and offers it
for opening EPUB and PDF files; `--uninstall` removes that again. A copy installed from a .deb or
.rpm package (packaging/linux.py) needs neither: the package brings the launcher and the icon.
Books are kept in the user's data folder. On the first start the page asks what to download for
speech (see runtime.py). `--check` starts everything without a window, downloads what the first
start would (the processor's PyTorch, or the kind EMA_READER_CHECK names), makes one sentence of
audio and exits, which is how a packaged build is tested.
"""

import os
import socket
import sys
import threading
from pathlib import Path

import runtime

ROOT = Path(__file__).parent
NAME = "EMA Reader"
# fixed, so that settings the page stores in the browser survive a restart
PORT = int(os.environ.get("EMA_READER_PORT", 47800))

SPLASH = """<!doctype html><meta charset="utf-8"><style>
html,body{height:100%;margin:0}body{display:grid;place-items:center;font-family:system-ui,sans-serif;color:#6b6b75;background:#fff}
@media(prefers-color-scheme:dark){body{background:#131316;color:#a0a0ab}}
div{text-align:center}img{width:72px;height:72px;display:block;margin:0 auto 18px;animation:p 1.6s ease-in-out infinite}
@keyframes p{50%{opacity:.45}}</style><div><img src="data:image/svg+xml;base64,LOGO" alt="">EMA Reader açılıyor…</div>"""


def free_port():
    """PORT if it is free, otherwise any free port."""
    for port in (PORT, 0):
        with socket.socket() as s:
            if os.name != "nt":
                # as the server itself does: a port whose last connections are still winding down is free.
                # Without this, an app that starts again at once (after an update) lands on another port
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue


def prepare():
    data = runtime.data_dir()
    os.environ.setdefault("EMA_READER_LIBRARY", str(data / "library"))
    # the model goes beside the downloaded PyTorch, so that all the app downloads is in one place
    os.environ.setdefault("HF_HOME", str(runtime.folder() / "hf"))
    runtime.activate()
    return data


def check():
    for stream in (sys.stdout, sys.stderr):
        if stream:
            stream.reconfigure(encoding="utf-8")  # a Windows console is not UTF-8, and the messages are Turkish
    prepare()
    import app

    server = app.start(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not runtime.ready():
        # any kind, also one this computer has no use for: the build workflow downloads the NVIDIA one
        # on machines without a card, to see that it comes and loads (on the processor)
        choice = os.environ.get("EMA_READER_CHECK") or ("mps" if runtime.apple_silicon() else "cpu")
        print(f"indiriliyor: {choice}", flush=True)
        runtime.install(choice, None)
        if runtime.job["state"] == "failed":
            sys.exit(runtime.job["error"])
    app.load()
    from urllib.request import urlopen

    port = server.server_address[1]
    page = urlopen(f"http://127.0.0.1:{port}/").read()
    wav = urlopen(f"http://127.0.0.1:{port}/tts?text=Merhaba").read()
    assert b"EMA Reader" in page and wav[:4] == b"RIFF", "uygulama beklendiği gibi yanıt vermedi"
    if sys.platform == "linux":
        # what the window needs from the system; loading it needs no screen
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_version("WebKit", "6.0")
        from gi.repository import Adw, Gtk, WebKit  # noqa: F401
    else:
        # the same for the window everywhere else: pywebview and what it draws with
        import webview  # noqa: F401

        if sys.platform == "win32":
            import clr  # noqa: F401
        else:
            import AppKit  # noqa: F401
            import WebKit  # noqa: F401
    print(f"tamam: sayfa {len(page)} bayt, ses {len(wav)} bayt, {app.tts.device.type} ile")


WORDS = {"back": "Kitaplığa dön", "add": "Kitap ya da makale ekle", "search": "Kitaplığında ara", "settings": "Ayarlar",
         "info": "Kitap hakkında", "chapters": "Bölümler", "download": "İndir", "saved": "İndirilenler klasörüne kaydedildi: {}"}


APP_ID = "io.github.emareader.EMAReader"
LAUNCHER = """[Desktop Entry]
Type=Application
Name=EMA Reader
Comment=Kitapları ve makaleleri Türkçe dinle
Exec={exec} %f
Icon={id}
Terminal=false
NoDisplay={hidden}
Categories=Office;Viewer;
MimeType=application/epub+zip;application/pdf;text/plain;text/markdown;
StartupWMClass={id}
"""


def launcher_paths():
    share = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return share / "applications" / f"{APP_ID}.desktop", share / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg"


def write_launcher(hidden):
    import shlex

    entry, icon = launcher_paths()
    # a packaged build is one program; from source it is this script run by this Python
    command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    entry.parent.mkdir(parents=True, exist_ok=True)
    icon.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(LAUNCHER.format(exec=" ".join(map(shlex.quote, command)), id=APP_ID, hidden=str(hidden).lower()),
                     encoding="utf-8")
    icon.write_bytes((ROOT / "static" / "logo.svg").read_bytes())
    return entry


def install_launcher():
    """Add this copy of the app to the Linux applications menu, for the current user."""
    print(f"kuruldu: {write_launcher(hidden=False)}")


def ensure_icon():
    """The desktop finds a window's icon through its launcher. Without `--install` there is none and
    the window gets a placeholder, so a launcher that stays out of the menu is written for it."""
    if (ROOT / "package").exists():
        return  # installed from a package, whose launcher this one would hide
    entry, icon = launcher_paths()
    try:
        if not entry.exists():
            write_launcher(hidden=True)
        elif not icon.exists() or icon.read_bytes() != (ROOT / "static" / "logo.svg").read_bytes():
            icon.parent.mkdir(parents=True, exist_ok=True)
            icon.write_bytes((ROOT / "static" / "logo.svg").read_bytes())  # the logo changed since it was installed
    except OSError:
        pass  # a read-only home: the app still works, with the placeholder icon


def uninstall_launcher():
    for path in launcher_paths():
        path.unlink(missing_ok=True)
    print("başlatıcı kaldırıldı")


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
    import re

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk, WebKit

    def activate(application):
        style = Adw.StyleManager.get_default()
        css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        def set_theme(dark, accent=None):
            """The window follows the page: the header bar and the page are one surface, with the page's accent colour."""
            style.set_color_scheme(Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)
            colour, on_accent = ("#131316", "#131316") if dark else ("#ffffff", "#ffffff")
            rules = f"window, headerbar {{ background: {colour}; }}"
            if accent and re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
                rules = (f"@define-color accent_bg_color {accent}; @define-color accent_color {accent}; "
                         f"@define-color accent_fg_color {on_accent}; {rules}")
            css.load_from_string(rules)
            web.set_background_color(Gdk.RGBA(*((0.075, 0.075, 0.086, 1) if dark else (1, 1, 1, 1))))

        # what the page tells the window, and the page itself
        manager = WebKit.UserContentManager()
        manager.register_script_message_handler("shell", None)
        manager.add_script(WebKit.UserScript("window.emaShell = true;", WebKit.UserContentInjectedFrames.TOP_FRAME,
                                             WebKit.UserScriptInjectionTime.START, None, None))
        session = WebKit.NetworkSession.new(str(data / "webview"), str(data / "webview-cache"))  # keeps page settings
        web = WebKit.WebView(user_content_manager=manager, network_session=session,
                             website_policies=WebKit.WebsitePolicies(autoplay=WebKit.AutoplayPolicy.ALLOW))
        set_theme(style.get_dark())

        def run(script):
            web.evaluate_javascript(script, -1, None, None, None, None, None)

        def button(icon, word, side):
            b = Gtk.Button(icon_name=icon, tooltip_text=WORDS[word], visible=False)
            b.connect("clicked", lambda *_: run(f"shellAction({json.dumps(word)})"))
            (header.pack_start if side == "start" else header.pack_end)(b)
            return b

        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title=NAME)
        header.set_title_widget(title)
        # the logo in the top left corner, as on the page; inside a book the back button takes its place
        logo = Gtk.Image(pixel_size=26, margin_start=8, margin_end=4)
        try:
            logo.set_from_paintable(Gdk.Texture.new_from_filename(str(ROOT / "static" / "logo.png")))
        except GLib.Error:
            logo.set_visible(False)
        header.pack_start(logo)
        # some desktops put a small window icon among the title buttons; the logo above already is that
        layout = Gtk.Settings.get_default().get_property("gtk-decoration-layout") or ""
        header.set_decoration_layout(":".join(",".join(b for b in side.split(",") if b != "icon") for side in layout.split(":")))
        buttons = {
            "back": button("go-previous-symbolic", "back", "start"),
            "add": button("list-add-symbolic", "add", "start"),
            "settings": button("preferences-system-symbolic", "settings", "end"),
            "chapters": button("view-list-symbolic", "chapters", "end"),
            "download": button("folder-download-symbolic", "download", "end"),
            "info": button("help-about-symbolic", "info", "end"),
            "search": button("system-search-symbolic", "search", "end"),
        }

        def on_message(_manager, value):
            message = json.loads(value.to_json(0))
            if "view" in message:  # {"view": "setup" | "library" | "reader", "title", "subtitle", "empty", "chapters"}
                reader, empty = message["view"] == "reader", message.get("empty", False)
                title.set_title(message.get("title") or NAME)
                title.set_subtitle(message.get("subtitle") or "")
                shown = {"back": reader, "info": reader, "download": reader, "chapters": reader and message.get("chapters", False),
                         "add": not reader and not empty, "search": not reader and not empty,
                         "settings": message["view"] != "setup"}  # the first start's download comes first
                for name, visible in shown.items():
                    buttons[name].set_visible(visible)
                run(f"shellTop({header.get_height()})")
                logo.set_visible(not reader and logo.get_paintable() is not None)
            if "side" in message:  # a panel stands at the left edge of the page: the header bar makes room for it
                header.set_margin_start(max(0, int(message["side"])))
            if "theme" in message:
                set_theme(message["theme"] == "dark", message.get("accent"))
            if "open" in message and str(message["open"]).startswith(("http://", "https://")):
                Gio.AppInfo.launch_default_for_uri(message["open"], None)
            if "highlight" in message:  # the tour points at one of these buttons
                for name, b in buttons.items():
                    (b.add_css_class if name == message["highlight"] else b.remove_css_class)("suggested-action")
            if message.get("ask") in buttons:  # where a button is, in the page's coordinates
                found, box = buttons[message["ask"]].compute_bounds(web)
                answer = {"left": box.get_x(), "right": box.get_x() + box.get_width()} if found else None
                run(f"shellAnswer({json.dumps(answer)})")

        manager.connect("script-message-received::shell", on_message)

        def on_policy(_web, decision, kind):
            # a link clicked in the page goes to the system's browser, not into this window
            if kind == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION:
                Gio.AppInfo.launch_default_for_uri(decision.get_navigation_action().get_request().get_uri(), None)
                decision.ignore()
                return True
            return False

        web.connect("decide-policy", on_policy)
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
                download.connect("finished", lambda *_: toasts.add_toast(Adw.Toast(title=WORDS["saved"].format(target.name))))
                return True

            download.connect("decide-destination", decide)

        session.connect("download-started", on_download)

        # the page reaches up under the header bar, so that its side panel can stand the full height of the window
        view = Adw.ToolbarView(content=toasts, extend_content_to_top_edge=True)
        view.add_top_bar(header)
        window = Adw.ApplicationWindow(application=application, title=NAME, default_width=1220, default_height=820, content=view)
        window.set_size_request(420, 560)
        web.load_html(splash, None)
        window.present()
        start_server(lambda url: GLib.idle_add(web.load_uri, url))

    ensure_icon()
    GLib.set_prgname(APP_ID)  # the window's class under X11, which is matched against the launcher too
    Gtk.Window.set_default_icon_name(APP_ID)
    application = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
    application.connect("activate", activate)
    application.run(None)


def run_webview(data, splash):
    """The window everywhere else: the system's own web view, with its normal title bar."""
    import webview

    window = webview.create_window(NAME, html=splash, width=1220, height=820, min_size=(420, 560))
    webview.settings["ALLOW_DOWNLOADS"] = True  # "download"
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.start(lambda: start_server(window.load_url), private_mode=False, storage_path=str(data / "webview"),
                  icon=str(ROOT / "static" / "logo.png"))


def main():
    if "--check" in sys.argv:
        return check()
    if "--install" in sys.argv:
        return install_launcher()
    if "--uninstall" in sys.argv:
        return uninstall_launcher()
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
