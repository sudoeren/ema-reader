"""Finds out whether a newer EMA Reader has been published.

    check("1.0.0")
    # {"current": "1.0.0", "latest": "1.1.0", "newer": True, "notes": "...", "page": "https://...",
    #  "download": "https://..." or None, "packaged": False,
    #  "job": {"state": "idle" | "working" | "failed", "step": ..., "progress": 0..1, "error": ...}}
    start("1.0.0")   # install the newer version in the background and start the app again

A version is published by pushing a tag such as v1.1.0: the build workflow then makes a GitHub
release with the installers and that version's section of CHANGELOG.md as its notes. This asks
GitHub for the latest release, at most once every few hours, and never fails: without a network
or a release, `latest` is None and `newer` is False.

Installing needs nothing from the reader. A copy that runs from source (Linux) pulls the new code
with git and syncs its packages with uv. The Windows build downloads the new installer and runs
it quietly; the macOS build downloads the disk image and swaps the application. A Linux package
downloads the new package for the same system and installs it with the system's package manager,
which asks for the password. Each then starts the app again.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

REPO = "sudoeren/ema-reader"
URL = os.environ.get("EMA_READER_UPDATE_URL") or f"https://api.github.com/repos/{REPO}/releases/latest"
FRESH = 6 * 3600  # how long an answer is kept
RETRY = 600  # how soon to ask again after a failure
ROOT = Path(__file__).parent
# written by build.py and packaging/linux.py: the release file this copy was installed from, such as
# EMA-Reader-Setup.exe or EMA-Reader.deb; a copy run from source has none
PACKAGE = ROOT / "package"

cache = {"until": 0, "release": None}
job = {"state": "idle", "step": None, "progress": 0, "error": None}


def number(version):
    """'v1.10.2' -> (1, 10, 2), so that versions compare as numbers."""
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def tidy(notes):
    """Release notes as plain lines: Markdown headings and bullets without their marks."""
    lines = []
    for line in (notes or "").strip().splitlines():
        line = re.sub(r"^\s*#+\s*", "", line.rstrip())
        line = re.sub(r"^\s*[-*]\s+", "• ", line)
        lines.append(re.sub(r"[*_`]+", "", line))
    return "\n".join(lines)


def package():
    """The release file this copy was installed from; None for a copy that runs from source."""
    try:
        return PACKAGE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def release(data):
    """What the reader needs from GitHub's description of a release."""
    def link(url):
        return url if isinstance(url, str) and url.startswith("https://github.com/") else None

    wanted = package()  # the same kind of file this copy came in; None when it is updated with git
    installers = (a.get("browser_download_url") for a in data.get("assets") or [] if wanted and a.get("name") == wanted)
    return {"latest": ".".join(map(str, number(data["tag_name"]))), "notes": tidy(data.get("body")),
            "page": link(data.get("html_url")), "download": link(next(installers, None))}


def changelog(text, version):
    """The section of CHANGELOG.md for one version, without its heading; None when there is none."""
    found = re.search(rf"^## {re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return found.group(1).strip() if found else None


def check(current, fresh=False):
    now = time.time()
    if fresh or now >= cache["until"]:
        try:
            request = urllib.request.Request(URL, headers={"Accept": "application/vnd.github+json", "User-Agent": f"EMA Reader/{current}"})
            with urllib.request.urlopen(request, timeout=6) as response:
                cache["release"] = release(json.load(response))
            cache["until"] = now + FRESH
        except Exception:  # no network, no release yet, an answer that is not a release
            cache["until"] = now + RETRY
    found = cache["release"] or {"latest": None, "notes": "", "page": None, "download": None}
    return {"current": current, **found, "newer": bool(found["latest"]) and number(found["latest"]) > number(current),
            "packaged": bool(package()), "job": dict(job)}


class Failed(Exception):
    """Something the reader can be told, in Turkish."""


def start(current):
    """Begin installing the newer version; `job` then says how far it is."""
    if job["state"] == "working":
        return dict(job)
    found = check(current)
    if not found["newer"]:
        raise ValueError("Zaten en güncel sürümü kullanıyorsun.")
    job.update(state="working", step="preparing", progress=0, error=None)
    threading.Thread(target=install, args=(found,), daemon=True).start()
    return dict(job)


def install(found):
    try:
        name = package()
        if not name:
            from_source()
        elif name.endswith(".exe"):
            with_installer(found)
        elif name.endswith(".dmg"):
            with_disk_image(found)
        else:
            with_package(found)
    except Failed as e:
        job.update(state="failed", error=str(e))
    except Exception as e:
        job.update(state="failed", error=f"Güncelleme yarıda kaldı: {e}")


def last_line(text):
    return next((line.strip() for line in reversed((text or "").splitlines()) if line.strip()), "")


def from_source():
    """A git checkout: pull the new code, bring the packages in line, start again."""
    if not (ROOT / ".git").exists() or not shutil.which("git"):
        raise Failed("Bu kopya git ile kurulmamış. Yeni sürümü sürüm sayfasından indirebilirsin.")
    job["step"] = "downloading"
    pulled = subprocess.run(["git", "-C", str(ROOT), "pull", "--ff-only"], capture_output=True, text=True)
    if pulled.returncode:
        raise Failed(f"Yeni sürüm alınamadı: {last_line(pulled.stderr) or last_line(pulled.stdout)}")
    # the packages, when this Python is the project's own environment and uv is there to sync it
    if shutil.which("uv") and Path(sys.prefix).resolve() == (ROOT / ".venv").resolve():
        job["step"] = "installing"
        desktop = Path(getattr(sys.modules.get("__main__"), "__file__", "")).name == "desktop.py"
        synced = subprocess.run(["uv", "sync", *(["--extra", "desktop"] if desktop else [])], cwd=ROOT, capture_output=True, text=True)
        if synced.returncode:
            raise Failed(f"Kod güncellendi ama gerekli paketler kurulamadı: {last_line(synced.stderr)}")
    restart()


def restart():
    job["step"] = "restarting"
    time.sleep(1.5)  # long enough for the page to hear that the app is about to start again
    os.execv(sys.executable, [sys.executable, *sys.argv])


def download(found, name):
    if not found["download"]:
        raise Failed("Bu sürümün kurulum dosyası henüz yayınlanmamış. Biraz sonra yeniden dene.")
    job["step"] = "downloading"
    path = Path(tempfile.mkdtemp(prefix="ema-reader-update-")) / name
    request = urllib.request.Request(found["download"], headers={"User-Agent": f"EMA Reader/{found['current']}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, open(path, "wb") as out:
            total, done = int(response.headers.get("Content-Length") or 0), 0
            while data := response.read(1 << 16):
                out.write(data)
                done += len(data)
                job["progress"] = done / total if total else 0
    except OSError as e:
        raise Failed(f"Yeni sürüm indirilemedi: {e}") from None
    return path


def with_installer(found):
    """Windows: run the new installer quietly; it replaces the files and starts the app again."""
    setup = download(found, "EMA-Reader-Setup.exe")
    job["step"] = "restarting"
    time.sleep(1.5)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True, creationflags=flags)
    os._exit(0)  # the installer cannot replace a program that is running


def with_package(found):
    """A Linux package: install the new one with the system's package manager, which asks for the password."""
    name = package()
    manager = (["apt-get", "install", "-y"] if name.endswith(".deb") else ["dnf", "install", "-y"] if name.endswith(".rpm")
               else ["pacman", "-U", "--noconfirm"])
    if not shutil.which("pkexec") or not shutil.which(manager[0]):
        raise Failed("Bu sistemde uygulama kendini kuramıyor. Yeni sürümü sürüm sayfasından indirip kurabilirsin.")
    path = download(found, name)
    job["step"] = "installing"
    try:
        done = subprocess.run(["pkexec", *manager, str(path)], capture_output=True, text=True)
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    if done.returncode in (126, 127):  # pkexec: the password was not given, or nothing could ask for it
        raise Failed("Yönetici izni alınamadı, yeni sürüm kurulmadı. Yeniden dene ya da sürüm sayfasından indirip kur.")
    if done.returncode:
        raise Failed(f"Yeni sürüm kurulamadı: {last_line(done.stderr) or last_line(done.stdout)}")
    restart()


SWAP = """#!/bin/sh
# waits for the app to quit, puts the new one from the disk image in its place and opens it;
# the old application stays until the new one is fully copied
app="$1"; image="$2"; pid="$3"
while kill -0 "$pid" 2>/dev/null; do sleep 0.3; done
mount=$(mktemp -d)
if hdiutil attach "$image" -nobrowse -noautoopen -quiet -mountpoint "$mount"; then
  new="$mount/$(basename "$app")"
  if [ -d "$new" ] && rm -rf "$app.new" && ditto "$new" "$app.new"; then
    rm -rf "$app.old"
    mv "$app" "$app.old" && mv "$app.new" "$app" && rm -rf "$app.old"
    [ -d "$app" ] || mv "$app.old" "$app"
  fi
  hdiutil detach "$mount" -quiet
fi
rm -rf "$app.new" "$(dirname "$image")"
open "$app"
"""


def with_disk_image(found):
    """macOS: swap the application for the one in the new disk image, once this one has quit."""
    app = Path(sys.executable).resolve().parents[2]  # EMA Reader.app/Contents/MacOS/python
    if app.suffix != ".app" or not os.access(app.parent, os.W_OK):
        raise Failed("Uygulama bulunduğu yerde değiştirilemiyor. Onu Uygulamalar klasörüne taşıyıp yeniden dene.")
    image = download(found, "EMA-Reader.dmg")
    script = image.with_name("swap.sh")
    script.write_text(SWAP, encoding="utf-8")
    job["step"] = "restarting"
    time.sleep(1.5)
    subprocess.Popen(["/bin/sh", str(script), str(app), str(image), str(os.getpid())], start_new_session=True, close_fds=True)
    os._exit(0)


if __name__ == "__main__":
    # `python update.py 1.1.0` prints that version's notes; the build workflow uses it for the release,
    # and it fails when the tag, app.py and CHANGELOG.md do not agree
    from pathlib import Path

    root = Path(__file__).parent
    wanted = ".".join(map(str, number(sys.argv[1])))
    stated = re.search(r'^VERSION = "(.+)"', (root / "app.py").read_text(encoding="utf-8"), re.M).group(1)
    notes = changelog((root / "CHANGELOG.md").read_text(encoding="utf-8"), wanted)
    if stated != wanted:
        sys.exit(f"etiket {wanted} ama app.py içindeki VERSION {stated}")
    if not notes:
        sys.exit(f"CHANGELOG.md içinde {wanted} bölümü yok")
    sys.stdout.buffer.write((notes + "\n").encode("utf-8"))  # not print: a Windows console is not UTF-8
