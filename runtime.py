"""What the app downloads on its first start: PyTorch for this computer's hardware, and the model.

    status()          # {"ready": False, "choices": [...], "job": {...}, ...}
    start("cuda")     # download in the background; `job` says how far it is
    used()            # how many bytes the downloads take
    remove()          # take them away again, when the app next starts

The installers carry the app and a Python of their own, but not PyTorch: the build for NVIDIA
cards alone is larger than a GitHub release file may be, and most computers need another one
anyway. So on its first start the app asks which to use, offering what this computer has (an
NVIDIA card, Apple silicon's GPU or the processor), and installs that PyTorch into the user's data
folder with uv, which ships with the app. The model weights follow from Hugging Face.

A copy run from source usually has PyTorch already, from its own environment; then only the
model is fetched.

What was downloaded can be removed from the settings, to free the room or before the app itself is
uninstalled: no uninstaller reaches into the user's data folder on every system. The files are in
use while the app runs, so they are only marked, and the app that starts next deletes them first.
"""

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
NAME = "EMA Reader"
TORCH = "torch>=2.6"
PYPI = "https://pypi.org/simple"
WHEELS = "https://download.pytorch.org/whl/"
# the CUDA builds to try, the one that runs on the oldest drivers first
CUDA = ("cu126", "cu128", "cu130")

job = {"state": "idle", "step": None, "progress": 0, "error": None, "choice": None}
lock = threading.Lock()
leaving = False  # the downloads are marked for removal: the app that starts next deletes them, not this one


def data_dir():
    """The per-user folder for the library, the settings and what is downloaded."""
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return base / NAME


def folder():
    return Path(os.environ.get("EMA_READER_RUNTIME") or data_dir() / "runtime")


def site():
    """Where the downloaded PyTorch lives; a fresh download goes next to it and takes its place on the next start."""
    return folder() / "site"


def activate():
    """Make the downloaded PyTorch importable; called before anything imports torch."""
    clear()
    pending = folder() / "site.new"
    if pending.is_dir():  # a switch to another kind, downloaded while the app ran
        shutil.rmtree(site(), ignore_errors=True)
        pending.rename(site())
    if site().is_dir() and str(site()) not in sys.path:
        sys.path.insert(0, str(site()))
        importlib.invalidate_caches()


def downloads():
    """The folders of everything the app has downloaded for speech: PyTorch, what is left of fetching it, and
    the model. Only what is in the app's own folder: a PyTorch or a model that was on the computer before, in
    the reader's own Python or in the Hugging Face cache other programs share, is not the app's to remove."""
    return [path for path in (folder() / name for name in ("site", "site.new", "cache", "hf")) if path.exists()]


def used():
    """How many bytes the downloads take on the disk."""
    total = 0
    for path in downloads():
        for file in path.rglob("*"):
            try:
                if not file.is_symlink() and file.is_file():  # the model's cache links to its files
                    total += file.stat().st_size
            except OSError:
                pass
    return total


def remove():
    """Mark the downloads for removal; they go when the app starts again, which the caller sees to."""
    global leaving
    with lock:
        if job["state"] == "working":
            raise ValueError("İndirme sürerken kaldırılamaz. Bitmesini bekleyip yeniden dene.")
        folder().mkdir(parents=True, exist_ok=True)
        (folder() / "remove").write_text("", encoding="utf-8")
        leaving = True


def clear():
    """Delete the downloads if the app that ran before marked them."""
    marker = folder() / "remove"
    if leaving or not marker.exists():
        return
    for _ in range(20):
        for path in downloads():
            shutil.rmtree(path, ignore_errors=True)
        if not downloads():
            break
        time.sleep(0.25)  # on Windows the app that has just closed may still hold a file
    else:
        return  # something would not go: the mark stays, for the next start
    (folder() / "state.json").unlink(missing_ok=True)
    marker.unlink(missing_ok=True)


def nvidia():
    """Whether an NVIDIA driver is installed; PyTorch finds out later whether it is new enough."""
    if shutil.which("nvidia-smi"):
        return True
    if sys.platform == "win32":
        return (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvcuda.dll").exists()
    return Path("/proc/driver/nvidia/version").exists()


def apple_silicon():
    return sys.platform == "darwin" and platform.machine() == "arm64"


def choices():
    """What this computer can use, the best first. `size` is about how much is downloaded, `disk` about
    how much room it takes once unpacked; both are estimates, the second only drives the progress bar."""
    windows = sys.platform == "win32"
    if apple_silicon():
        # the one macOS build of PyTorch uses the GPU and falls back to the processor by itself
        return [{"id": "mps", "size": 90_000_000, "disk": 350_000_000}]
    found = [{"id": "cpu", "size": 200_000_000, "disk": 600_000_000 if windows else 800_000_000}]
    if nvidia():
        found.insert(0, {"id": "cuda", "size": 2_600_000_000 if windows else 3_300_000_000,
                         "disk": 4_500_000_000 if windows else 6_000_000_000})
    return found


def state():
    try:
        return json.loads((folder() / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def remember(**values):
    folder().mkdir(parents=True, exist_ok=True)
    (folder() / "state.json").write_text(json.dumps({**state(), **values}), encoding="utf-8")


def wants_cpu():
    """Whether the reader chose the processor although the PyTorch that is there could use a card."""
    return state().get("use") == "cpu"


def has_torch():
    return importlib.util.find_spec("torch") is not None


def has_model():
    from ema import FILES, REPO
    from huggingface_hub import try_to_load_from_cache

    return all(isinstance(try_to_load_from_cache(REPO, f), str) for f in FILES)


def ready():
    activate()
    return has_torch() and has_model()


def status():
    activate()
    torch = has_torch()
    return {"ready": torch and has_model(), "torch": torch, "using": state().get("use") or state().get("choice"), "choices": choices(),
            "restart": (folder() / "site.new").is_dir(), "job": dict(job)}


def start(choice, done=None):
    """Download what `choice` needs, and the model if it is missing; `done` is called once all is in place."""
    if choice not in {c["id"] for c in choices()}:
        raise ValueError("Bu bilgisayarda kullanılamaz.")
    with lock:
        if job["state"] == "working":
            return dict(job)
        job.update(state="working", step="preparing", progress=0, error=None, choice=choice)
    threading.Thread(target=install, args=(choice, done), daemon=True).start()
    return dict(job)


class Failed(Exception):
    """Something the reader can be told, in Turkish."""


def install(choice, done):
    try:
        activate()
        # another PyTorch is only needed for a card: the one for a card runs on the processor too, and so does
        # whatever a copy run from source came with (which has no "choice")
        switching = has_torch() and choice != "cpu" and state().get("choice") not in (None, choice)
        if not has_torch() or switching:
            install_torch(choice, folder() / ("site.new" if switching else "site"))
            activate()
        if not has_model():
            install_model()
        remember(use=choice)
        job.update(state="done", step=None, progress=1)
        if done and not switching:
            done()  # loads the model, or loads it anew on what was chosen
    except Failed as e:
        job.update(state="failed", error=str(e))
    except Exception as e:
        job.update(state="failed", error=f"İndirme yarıda kaldı: {e}")


def uv():
    """The uv that came with the app, or one on the PATH (from source)."""
    name = "uv.exe" if sys.platform == "win32" else "uv"
    for path in (ROOT / "bin" / name, shutil.which("uv")):
        if path and Path(path).is_file():
            return str(path)
    raise Failed("Uygulamanın indirme aracı (uv) bulunamadı. EMA Reader'ı yeniden kurmayı dene.")


def python():
    """The interpreter PyTorch is installed for. On Windows the app runs as "EMA Reader.exe", a windowless
    Python that uv does not take for one; python.exe sits next to it."""
    here = Path(sys.executable).parent
    for name in ("python.exe", "python3", "python"):
        if (here / name).is_file():
            return str(here / name)
    return sys.executable


def install_torch(choice, target):
    """PyTorch and what it needs, into `target`. uv says little while it downloads, so the progress is
    how much it has unpacked into its cache, against the size that comes to."""
    job["step"] = "torch"
    expected = next((c["disk"] for c in choices() if c["id"] == choice), 3_000_000_000)
    cache = folder() / "cache"
    indexes = [None] if choice == "mps" else [WHEELS + "cpu"] if choice == "cpu" else [WHEELS + c for c in CUDA]
    error = ""
    for index in indexes:
        shutil.rmtree(target, ignore_errors=True)
        command = [uv(), "pip", "install", "--target", str(target), "--python", python(), "--no-progress", TORCH]
        if index:
            # PyTorch's own index goes in as the extra one, which uv asks first: the other way round PyTorch
            # would come from PyPI, whose build is the one for NVIDIA cards on Linux and the processor's on Windows
            command += ["--index-url", PYPI, "--extra-index-url", index]
        env = {**os.environ, "UV_CACHE_DIR": str(cache), "UV_PYTHON_DOWNLOADS": "never"}
        process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
        watch = threading.Thread(target=measure, args=(process, cache, expected), daemon=True)
        watch.start()
        error = process.stderr.read()
        if process.wait() == 0:
            break
    else:
        shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(cache, ignore_errors=True)
        line = next((l.strip() for l in reversed(error.splitlines()) if l.strip()), "")
        raise Failed(f"PyTorch indirilemedi. İnternet bağlantını kontrol edip yeniden dene. ({line})")
    shutil.rmtree(cache, ignore_errors=True)
    remember(choice=choice)


def measure(process, cache, expected):
    while process.poll() is None:
        try:
            size = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file())
        except OSError:
            size = 0
        job["progress"] = min(0.97, size / expected)
        time.sleep(0.5)


def install_model():
    job.update(step="model", progress=0)
    from ema import FILES, REPO
    from huggingface_hub import hf_hub_download

    try:
        for number, name in enumerate(FILES):
            hf_hub_download(REPO, name)
            job["progress"] = (number + 1) / len(FILES)
    except Exception as e:
        raise Failed(f"Ses modeli indirilemedi. İnternet bağlantını kontrol edip yeniden dene. ({e})") from None
