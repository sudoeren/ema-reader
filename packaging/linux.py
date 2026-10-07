"""Builds the Linux package for the system this runs on: a .deb on Ubuntu and Debian, an .rpm on Fedora.

    python3 packaging/linux.py ubuntu-24.04      # writes dist/EMA-Reader-ubuntu-24.04.deb

It runs as root on the system the package is for; the build workflow runs it in a container of
each supported system. The app goes to /opt/ema-reader with a Python environment of its own, made
on the system's Python: a CPU-only PyTorch, the model weights and the other packages, so the first
start needs no download. GTK 4, libadwaita, WebKitGTK and their Python bindings come from the
system. That is why each system gets a package of its own: the environment only works with the
Python it was made with, and the package asks for exactly that one.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from build import FILES, REPO  # noqa: E402  the same weights as the Windows and macOS builds
from desktop import APP_ID, LAUNCHER  # noqa: E402

PREFIX = Path("/opt/ema-reader")
SOURCES = ["app.py", "ema.py", "extract.py", "export.py", "update.py", "desktop.py", "static", "LICENSE", "THIRD_PARTY.md", "CHANGELOG.md"]
PACKAGES = ["ema-lightning>=1.0.1", "pypdf", "trafilatura", "soundfile"]
HOMEPAGE = "https://github.com/sudoeren/ema-reader"
MAINTAINER = "Eren Çakar <hey@erencakar.com>"
SUMMARY = "Kitapları ve makaleleri Türkçe sesli okur"
DESCRIPTION = ("EMA Reader, EPUB, PDF, metin ve Markdown dosyalarını ve web'deki makaleleri EMA Lightning "
               "modeliyle Türkçe okur. Her şey bilgisayarın kendisinde olur.")
# what the window needs from the system, by package manager
NEEDS = {
    "deb": ["python3-gi", "gir1.2-gtk-4.0", "gir1.2-adw-1", "gir1.2-webkit-6.0"],
    "rpm": ["python3-gobject", "gtk4", "libadwaita", "webkitgtk6.0"],
}

METAINFO = """<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{id}</id>
  <name>EMA Reader</name>
  <summary>{summary}</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>MIT</project_license>
  <description><p>{description}</p></description>
  <launchable type="desktop-id">{id}.desktop</launchable>
  <url type="homepage">{homepage}</url>
  <releases><release version="{version}"/></releases>
  <content_rating type="oars-1.1"/>
</component>
"""

SPEC = """Name: ema-reader
Version: {version}
Release: 1
Summary: {summary}
License: MIT
URL: {homepage}
BuildArch: x86_64
Requires: python(abi) = {python}, {needs}
# the environment in /opt carries its own libraries: nothing in it is to be required, provided or touched
AutoReqProv: no
%global debug_package %{{nil}}
%global __os_install_post %{{nil}}
%global _build_id_links none

%description
{description}

%install
cp -a {stage}/. %{{buildroot}}/

%files
/opt/ema-reader
/usr/bin/ema-reader
/usr/share/applications/{id}.desktop
/usr/share/icons/hicolor/scalable/apps/{id}.svg
/usr/share/metainfo/{id}.metainfo.xml
"""


def run(*command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, check=True, **kwargs)


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z]+-[0-9.]+", sys.argv[1]):
        sys.exit("kullanım: python3 packaging/linux.py ubuntu-24.04")
    kind = "deb" if shutil.which("dpkg-deb") else "rpm" if shutil.which("rpmbuild") else sys.exit("dpkg-deb ya da rpmbuild gerekli")
    name = f"EMA-Reader-{sys.argv[1]}.{kind}"
    version = re.search(r'^VERSION = "(.+)"', (ROOT / "app.py").read_text(encoding="utf-8"), re.M).group(1)
    python = f"{sys.version_info.major}.{sys.version_info.minor}"

    # the app is put together where it will be installed, because a Python environment cannot be moved
    shutil.rmtree(PREFIX, ignore_errors=True)
    PREFIX.mkdir(parents=True)
    for source in SOURCES:
        (shutil.copytree if (ROOT / source).is_dir() else shutil.copy2)(ROOT / source, PREFIX / source)
    # tells the app which release file updates it (see update.py)
    (PREFIX / "package").write_text(name + "\n", encoding="utf-8")

    venv = PREFIX / "venv"
    env = {**os.environ, "UV_CACHE_DIR": tempfile.mkdtemp(prefix="uv-"), "UV_COMPILE_BYTECODE": "1"}
    run("uv", "venv", venv, "--python", sys.executable, "--system-site-packages", env=env)
    run("uv", "pip", "install", "--python", venv / "bin" / "python", "torch", "--index-url", "https://download.pytorch.org/whl/cpu", env=env)
    run("uv", "pip", "install", "--python", venv / "bin" / "python", *PACKAGES, env=env)
    shutil.rmtree(env["UV_CACHE_DIR"])
    fetch = f"from huggingface_hub import hf_hub_download\nfor f in {FILES!r}: hf_hub_download({REPO!r}, f)"
    run(venv / "bin" / "python", "-c", fetch, env={**os.environ, "HF_HOME": str(PREFIX / "hf"), "HF_HUB_DISABLE_SYMLINKS": "1"})
    shutil.rmtree(PREFIX / "hf" / "xet", ignore_errors=True)
    # compiled now, since the app cannot write next to itself once installed
    run(venv / "bin" / "python", "-m", "compileall", "-q", *(PREFIX / f for f in SOURCES if f.endswith(".py")))

    stage = Path(tempfile.mkdtemp(prefix="ema-reader-"))
    shutil.copytree(PREFIX, stage / PREFIX.relative_to("/"), symlinks=True)
    shutil.rmtree(PREFIX)
    files = {
        "usr/bin/ema-reader": f'#!/bin/sh\nexec {PREFIX}/venv/bin/python {PREFIX}/desktop.py "$@"\n',
        f"usr/share/applications/{APP_ID}.desktop": LAUNCHER.format(exec="ema-reader", id=APP_ID, hidden="false"),
        f"usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg": (ROOT / "static" / "logo.svg").read_text(encoding="utf-8"),
        f"usr/share/metainfo/{APP_ID}.metainfo.xml": METAINFO.format(id=APP_ID, summary=SUMMARY, description=DESCRIPTION,
                                                                     homepage=HOMEPAGE, version=version),
    }
    for path, text in files.items():
        (stage / path).parent.mkdir(parents=True, exist_ok=True)
        (stage / path).write_text(text, encoding="utf-8")
    (stage / "usr/bin/ema-reader").chmod(0o755)

    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    if kind == "deb":
        size = sum(f.stat().st_size for f in stage.rglob("*") if f.is_file() and not f.is_symlink()) // 1024
        major, minor = sys.version_info[:2]
        (stage / "DEBIAN").mkdir()
        (stage / "DEBIAN" / "control").write_text(
            f"Package: ema-reader\nVersion: {version}\nArchitecture: amd64\nMaintainer: {MAINTAINER}\nInstalled-Size: {size}\n"
            f"Depends: python3 (>= {major}.{minor}), python3 (<< {major}.{minor + 1}), {', '.join(NEEDS['deb'])}\n"
            "Recommends: pkexec\n"  # the app installs its updates with it
            f"Section: sound\nPriority: optional\nHomepage: {HOMEPAGE}\nDescription: {SUMMARY}\n {DESCRIPTION}\n",
            encoding="utf-8")
        run("dpkg-deb", "--root-owner-group", "--build", stage, out / name)
    else:
        top = Path(tempfile.mkdtemp(prefix="rpmbuild-"))
        spec = top / "ema-reader.spec"
        spec.write_text(SPEC.format(version=version, summary=SUMMARY, description=DESCRIPTION, homepage=HOMEPAGE, id=APP_ID,
                                    python=python, needs=", ".join(NEEDS["rpm"]), stage=stage), encoding="utf-8")
        run("rpmbuild", "-bb", "--define", f"_topdir {top}", spec)
        shutil.copy(next((top / "RPMS").rglob("*.rpm")), out / name)
        shutil.rmtree(top)
    shutil.rmtree(stage)
    print(f"hazır: {out / name} ({(out / name).stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
