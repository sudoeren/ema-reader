"""Builds the desktop app for the system this runs on.

    uv run build.py

The result is `dist/EMA Reader/`, a folder that contains everything the app needs, including
Python, a CPU-only PyTorch and the model weights; nothing has to be installed to run it.
A build only works on the kind of system it was made on: build on Windows for Windows,
on macOS for macOS, on Linux for Linux.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
BUILD = ROOT / ".build"
VENV = BUILD / "venv"
HF = BUILD / "hf"
NAME = "EMA Reader"
REPO = "canberkkkkkk/ema-lightning"
FILES = ("config.json", "ema.pt", "decoder.pt")

PACKAGES = ["ema-lightning>=1.0.1", "pypdf", "trafilatura", "pywebview>=5", "pyinstaller>=6"]
if sys.platform == "linux":
    PACKAGES.append("pywebview[qt]>=5")
# packages whose data files or lazily imported modules PyInstaller does not find by itself
COLLECT = ["ema_lightning", "normalizer_tr", "trafilatura", "justext", "courlan", "htmldate", "tld", "dateparser", "webview"]


def run(*command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, check=True, **kwargs)


def main():
    python = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        run("uv", "venv", VENV, "--python", "3.12")
    # the GPU build of PyTorch is several gigabytes; the model is fast enough on a CPU
    torch = ["torch"] if sys.platform == "darwin" else ["torch", "--index-url", "https://download.pytorch.org/whl/cpu"]
    run("uv", "pip", "install", "--python", python, *torch)
    run("uv", "pip", "install", "--python", python, *PACKAGES)

    # ship the weights, laid out as a Hugging Face cache, so the app never has to download them
    fetch = f"from huggingface_hub import hf_hub_download\nfor f in {FILES!r}: hf_hub_download({REPO!r}, f)"
    run(python, "-c", fetch, env={**os.environ, "HF_HOME": str(HF), "HF_HUB_DISABLE_SYMLINKS": "1"})

    sep = os.pathsep
    icon = {"win32": "logo.ico", "darwin": "logo.icns"}.get(sys.platform, "logo.png")
    command = [
        python, "-m", "PyInstaller", ROOT / "desktop.py",
        "--name", NAME, "--windowed", "--noconfirm", "--clean",
        "--distpath", ROOT / "dist", "--workpath", BUILD / "work", "--specpath", BUILD,
        "--paths", ROOT,
        "--add-data", f"{ROOT / 'static'}{sep}static",
        "--add-data", f"{HF}{sep}hf",
        "--hidden-import", "app", "--hidden-import", "ema", "--hidden-import", "extract",
    ]
    if (ROOT / "static" / icon).exists():
        command += ["--icon", ROOT / "static" / icon]
    for package in COLLECT:
        command += ["--collect-all", package]
    run(*command)

    out = ROOT / "dist" / (f"{NAME}.app" if sys.platform == "darwin" else NAME)
    exe = out / "Contents" / "MacOS" / NAME if sys.platform == "darwin" else out / (NAME + (".exe" if sys.platform == "win32" else ""))
    run(exe, "--check")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"built {out} ({size:.0f} MB)")
    shutil.rmtree(BUILD / "work", ignore_errors=True)


if __name__ == "__main__":
    main()
