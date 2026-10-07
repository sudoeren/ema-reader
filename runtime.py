"""What the app downloads on its first start: PyTorch for this computer's hardware, and the model.

    status()          # {"ready": False, "choices": [...], "job": {...}, ...}
    start("cuda")     # download in the background; `job` says how far it is

The installers carry the app and a Python of their own, but not PyTorch: the build for NVIDIA
cards alone is larger than a GitHub release file may be, and most computers need another one
anyway. So on its first start the app asks which to use, offering what this computer has (an
NVIDIA card, Apple silicon's GPU or the processor), and installs that PyTorch into the user's data
folder with uv, which ships with the app. The model weights follow from Hugging Face.

A copy run from source usually has PyTorch already, from its own environment; then only the
model is fetched.
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
    pending = folder() / "site.new"
    if pending.is_dir():  # a switch to another kind, downloaded while the app ran
        shutil.rmtree(site(), ignore_errors=True)
        pending.rename(site())
    if site().is_dir() and str(site()) not in sys.path:
        sys.path.insert(0, str(site()))
        importlib.invalidate_caches()


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
    return {"ready": torch and has_model(), "torch": torch, "using": state().get("choice"), "choices": choices(),
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
        switching = has_torch() and state().get("choice") not in (None, choice)
        if not has_torch() or switching:
            install_torch(choice, folder() / ("site.new" if switching else "site"))
            activate()
        if not has_model():
            install_model()
        job.update(state="done", step=None, progress=1)
        if done and not switching:
            done()
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
            command += ["--index-url", index, "--extra-index-url", PYPI]
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
    (folder() / "state.json").write_text(json.dumps({"choice": choice}), encoding="utf-8")


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
