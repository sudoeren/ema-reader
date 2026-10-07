"""Builds the desktop app for the system this runs on: Windows or macOS.

    uv run build.py

On Windows it writes `dist/EMA Reader/`, which packaging/windows.iss packs into an installer; on
macOS `dist/EMA Reader.app`. Like the Linux packages (packaging/linux.py), the app carries a Python
of its own (python-build-standalone, from uv) with the packages it needs to start, and uv itself,
but neither PyTorch nor the model: the first start downloads those for the computer's hardware
(see runtime.py). The PyTorch for NVIDIA cards alone is larger than a GitHub release file may be.

The app's Python is not a virtual environment, which could not be moved: the packages go into the
Python itself, and its folder can be installed anywhere.

  Windows   EMA Reader/                 app.py, desktop.py, static/ ... and bin/uv.exe
            EMA Reader/python/          the Python, with "EMA Reader.exe": its windowless pythonw.exe
                                        under the app's name and with the app's icon
  macOS     EMA Reader.app/Contents/    the Python (bin/, lib/), and in MacOS/ a copy of it named python
                                        that a small script starts with the app; started from inside
                                        the bundle, it shows the app's name and icon in the Dock
            Contents/Resources/app/     app.py, desktop.py, static/ ... and bin/uv
"""

import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
NAME = "EMA Reader"
APP_ID = "io.github.emareader.EMAReader"

PYTHON = "3.13"  # the Python the app carries
SOURCES = ["app.py", "ema.py", "extract.py", "export.py", "update.py", "desktop.py", "runtime.py", "static",
           "LICENSE", "THIRD_PARTY.md", "CHANGELOG.md"]
# what the app needs to start; PyTorch is downloaded on the first start for the computer's hardware (runtime.py)
BASE = ["pypdf", "trafilatura", "soundfile", "huggingface-hub>=0.20", "normalizer-tr>=0.4,<0.5", "numpy>=1.24"]
EMA = "ema-lightning>=1.0.1"  # installed without its dependencies, which would bring PyTorch along

LAUNCH = """#!/bin/sh
# the app's main program: its Python, which lives next to this script, with the app
here="$(cd "$(dirname "$0")" && pwd)"
exec "$here/python" "$here/../Resources/app/desktop.py" "$@"
"""


def run(*command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, check=True, **kwargs)


def version():
    return re.search(r'^VERSION = "(.+)"', (ROOT / "app.py").read_text(encoding="utf-8"), re.M).group(1)


def standalone_python(into):
    """A copy of python-build-standalone in `into`, ready to have packages installed into it."""
    downloads = Path(tempfile.mkdtemp(prefix="python-"))
    run("uv", "python", "install", PYTHON, env={**os.environ, "UV_PYTHON_INSTALL_DIR": str(downloads)})
    found = next(p for p in downloads.iterdir() if p.is_dir() and not p.is_symlink() and p.name.startswith("cpython-"))
    shutil.copytree(found, into, symlinks=True, dirs_exist_ok=True)
    shutil.rmtree(downloads)
    # uv marks the Pythons it installs as not to be changed with pip; this one is the app's own
    for marker in into.rglob("EXTERNALLY-MANAGED"):
        marker.unlink()
    # how it was built, and Python's own tests: nothing the app uses
    for unused in (into / "BUILD", *into.glob("lib/python3.*/test"), into / "Lib" / "test"):
        shutil.rmtree(unused, ignore_errors=True)


def add_packages(python, *extra):
    env = {**os.environ, "UV_CACHE_DIR": tempfile.mkdtemp(prefix="uv-")}
    run("uv", "pip", "install", "--python", python, "--break-system-packages", *BASE, *extra, env=env)
    run("uv", "pip", "install", "--python", python, "--break-system-packages", "--no-deps", EMA, env=env)
    shutil.rmtree(env["UV_CACHE_DIR"])


def add_sources(into, package):
    into.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        (shutil.copytree if (ROOT / source).is_dir() else shutil.copy2)(ROOT / source, into / source)
    (into / "package").write_text(package + "\n", encoding="utf-8")  # tells update.py how this copy is updated
    (into / "bin").mkdir()
    shutil.copy2(shutil.which("uv"), into / "bin" / Path(shutil.which("uv")).name)  # for the first start's download


def windows(out):
    app = out / NAME
    standalone_python(app / "python")
    python = app / "python" / "python.exe"
    add_packages(python, "pywebview>=5")
    add_sources(app, "EMA-Reader-Setup.exe")
    # the window's program: pythonw.exe under the app's name, and with its icon in the taskbar if rcedit is at hand
    program = app / "python" / f"{NAME}.exe"
    shutil.copy2(app / "python" / "pythonw.exe", program)
    rcedit = os.environ.get("RCEDIT") or shutil.which("rcedit")
    if rcedit:
        run(rcedit, program, "--set-icon", ROOT / "static" / "logo.ico", "--set-version-string", "FileDescription", NAME,
            "--set-version-string", "ProductName", NAME, "--set-file-version", version(), "--set-product-version", version())
    else:
        print("rcedit yok: pencere Python simgesiyle görünecek", flush=True)
    run(python, "-m", "compileall", "-q", app / "app.py", app / "desktop.py", app / "runtime.py")
    return app


def macos(out):
    bundle = out / f"{NAME}.app"
    contents = bundle / "Contents"
    standalone_python(contents)
    python = contents / "bin" / f"python{PYTHON}"
    add_packages(python, "pywebview>=5")
    add_sources(contents / "Resources" / "app", "EMA-Reader.dmg")
    (contents / "MacOS").mkdir()
    shutil.copy2(python, contents / "MacOS" / "python")
    (contents / "MacOS" / NAME).write_text(LAUNCH, encoding="utf-8")
    (contents / "MacOS" / NAME).chmod(0o755)
    icon = ROOT / "static" / "logo.icns"
    if icon.exists():
        shutil.copy2(icon, contents / "Resources" / "logo.icns")
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump({
            "CFBundleName": NAME, "CFBundleDisplayName": NAME, "CFBundleIdentifier": APP_ID, "CFBundleExecutable": NAME,
            "CFBundleIconFile": "logo.icns", "CFBundlePackageType": "APPL", "CFBundleShortVersionString": version(),
            "CFBundleVersion": version(), "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True,
        }, f)
    run(python, "-m", "compileall", "-q", *(contents / "Resources" / "app" / f for f in ("app.py", "desktop.py", "runtime.py")))
    return bundle


def main():
    if sys.platform not in ("win32", "darwin"):
        sys.exit("Linux paketleri packaging/linux.py ile üretilir; kaynaktan çalıştırmak için: uv run --extra desktop desktop.py --install")
    out = ROOT / "dist"
    for old in (out / NAME, out / f"{NAME}.app"):
        shutil.rmtree(old, ignore_errors=True)
    out.mkdir(exist_ok=True)
    made = windows(out) if sys.platform == "win32" else macos(out)
    size = sum(f.stat().st_size for f in made.rglob("*") if f.is_file() and not f.is_symlink()) / 1e6
    print(f"hazır: {made} ({size:.0f} MB)")


if __name__ == "__main__":
    main()
