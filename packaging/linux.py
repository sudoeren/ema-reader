"""Builds the Linux packages: a .deb for Ubuntu and Debian, an .rpm for Fedora and a pacman package
for Arch Linux, all three holding the same app.

    python3 packaging/linux.py          # as root; writes dist/EMA-Reader.deb, .rpm and .pkg.tar.zst

The build workflow runs it in an Ubuntu 24.04 container, the oldest system it supports, so that
what it compiles runs on the newer ones too. The app goes to /opt/ema-reader with a Python of its
own (from uv) and the packages it needs to start, but neither PyTorch nor the model: the first
start downloads those for the computer's hardware (see runtime.py), with the uv that comes along.
GTK 4, libadwaita and WebKitGTK come from the system. PyGObject, which connects Python to them, is
built here for the app's own Python, so the package does not depend on the system's Python and
keeps working when the system moves to a newer one.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from build import BASE, EMA, PYTHON, SOURCES  # noqa: E402  the same app as the Windows and macOS builds
from desktop import APP_ID, LAUNCHER  # noqa: E402

PREFIX = Path("/opt/ema-reader")
HOMEPAGE = "https://github.com/sudoeren/ema-reader"
MAINTAINER = "Eren Çakar <hey@erencakar.com>"
SUMMARY = "Kitapları ve makaleleri Türkçe sesli okur"
DESCRIPTION = ("EMA Reader, EPUB, PDF, metin ve Markdown dosyalarını ve web'deki makaleleri EMA Lightning "
               "modeliyle Türkçe okur. Her şey bilgisayarın kendisinde olur.")
# what the app takes from the system, by package manager: the window, and the libraries PyGObject is built against
NEEDS = {
    "deb": ["gir1.2-gtk-4.0", "gir1.2-adw-1", "gir1.2-webkit-6.0", "libgirepository-2.0-0", "libcairo2", "libcairo-gobject2"],
    "rpm": ["gtk4", "libadwaita", "webkitgtk6.0", "glib2", "gobject-introspection", "cairo", "cairo-gobject"],
    "pkg.tar.zst": ["gtk4", "libadwaita", "webkitgtk-6.0", "glib2", "gobject-introspection-runtime", "cairo"],
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
Requires: {needs}
# the app in /opt carries its own Python and libraries: nothing in it is to be required, provided or touched
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


def version():
    return re.search(r'^VERSION = "(.+)"', (ROOT / "app.py").read_text(encoding="utf-8"), re.M).group(1)


def put_app():
    """The app at /opt/ema-reader, where it is installed, because a Python environment cannot be moved."""
    shutil.rmtree(PREFIX, ignore_errors=True)
    PREFIX.mkdir(parents=True)
    for source in SOURCES:
        (shutil.copytree if (ROOT / source).is_dir() else shutil.copy2)(ROOT / source, PREFIX / source)
    env = {**os.environ, "UV_CACHE_DIR": tempfile.mkdtemp(prefix="uv-"), "UV_COMPILE_BYTECODE": "1",
           "UV_PYTHON_INSTALL_DIR": str(PREFIX / "python")}
    python = PREFIX / "venv" / "bin" / "python"
    run("uv", "python", "install", PYTHON, env=env)
    run("uv", "venv", PREFIX / "venv", "--python", PYTHON, "--managed-python", env=env)
    run("uv", "pip", "install", "--python", python, *BASE, "pygobject", env=env)
    run("uv", "pip", "install", "--python", python, "--no-deps", EMA, env=env)  # without PyTorch, which comes later
    shutil.rmtree(env["UV_CACHE_DIR"])
    # the uv the first start downloads PyTorch with
    (PREFIX / "bin").mkdir()
    shutil.copy2(shutil.which("uv"), PREFIX / "bin" / "uv")
    # compiled now, since the app cannot write next to itself once installed
    run(python, "-m", "compileall", "-q", *(PREFIX / f for f in SOURCES if f.endswith(".py")))
    run(python, "-c", "import gi, numpy, pypdf, trafilatura, soundfile, huggingface_hub, normalizer_tr")


def put_launcher(root):
    """The command, the applications menu entry, the icon and the software centre's description, under `root`."""
    files = {
        "usr/bin/ema-reader": f'#!/bin/sh\nexec {PREFIX}/venv/bin/python {PREFIX}/desktop.py "$@"\n',
        f"usr/share/applications/{APP_ID}.desktop": LAUNCHER.format(exec="ema-reader", id=APP_ID, hidden="false"),
        f"usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg": (ROOT / "static" / "logo.svg").read_text(encoding="utf-8"),
        f"usr/share/metainfo/{APP_ID}.metainfo.xml": METAINFO.format(id=APP_ID, summary=SUMMARY, description=DESCRIPTION,
                                                                     homepage=HOMEPAGE, version=version()),
    }
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    (root / "usr/bin/ema-reader").chmod(0o755)


def staged(name):
    """The files of one package in a folder of their own, named after it so that the app knows how it is updated."""
    stage = Path(tempfile.mkdtemp(prefix="ema-reader-"))
    shutil.copytree(PREFIX, stage / PREFIX.relative_to("/"), symlinks=True)
    (stage / PREFIX.relative_to("/") / "package").write_text(name + "\n", encoding="utf-8")  # see update.py
    put_launcher(stage)
    return stage


def size(stage):
    return sum(f.stat().st_size for f in stage.rglob("*") if f.is_file() and not f.is_symlink())


def deb(stage, path):
    (stage / "DEBIAN").mkdir()
    (stage / "DEBIAN" / "control").write_text(
        f"Package: ema-reader\nVersion: {version()}\nArchitecture: amd64\nMaintainer: {MAINTAINER}\n"
        f"Installed-Size: {size(stage) // 1024}\nDepends: {', '.join(NEEDS['deb'])}\n"
        "Recommends: pkexec\n"  # the app installs its updates with it
        f"Section: sound\nPriority: optional\nHomepage: {HOMEPAGE}\nDescription: {SUMMARY}\n {DESCRIPTION}\n",
        encoding="utf-8")
    run("dpkg-deb", "--root-owner-group", "--build", stage, path)


def rpm(stage, path):
    top = Path(tempfile.mkdtemp(prefix="rpmbuild-"))
    spec = top / "ema-reader.spec"
    spec.write_text(SPEC.format(version=version(), summary=SUMMARY, description=DESCRIPTION, homepage=HOMEPAGE, id=APP_ID,
                                needs=", ".join(NEEDS["rpm"]), stage=stage), encoding="utf-8")
    run("rpmbuild", "-bb", "--define", f"_topdir {top}", spec)
    shutil.copy(next((top / "RPMS").rglob("*.rpm")), path)
    shutil.rmtree(top)


def pacman(stage, path):
    """A pacman package is a compressed tar of the files with two descriptions in front: .PKGINFO says
    what the package is and needs, .MTREE lists every file with its checksum, as makepkg writes them."""
    info = ["pkgname = ema-reader", "pkgbase = ema-reader", f"pkgver = {version()}-1", f"pkgdesc = {SUMMARY}",
            f"url = {HOMEPAGE}", f"builddate = {int(time.time())}", f"packager = {MAINTAINER}", f"size = {size(stage)}",
            "arch = x86_64", "license = MIT", *(f"depend = {need}" for need in NEEDS["pkg.tar.zst"])]
    (stage / ".PKGINFO").write_text("\n".join(info) + "\n", encoding="utf-8")
    entries = sorted(e.name for e in stage.iterdir() if not e.name.startswith("."))
    env = {**os.environ, "LANG": "C"}
    run("bsdtar", "-czf", ".MTREE", "--format=mtree",
        "--options=!all,use-set,type,uid,gid,mode,time,size,md5,sha256,link", ".PKGINFO", *entries, cwd=stage, env=env)
    run("bsdtar", "--zstd", "--options=zstd:compression-level=19", "-cf", path, ".MTREE", ".PKGINFO", *entries, cwd=stage, env=env)


def main():
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    put_app()
    for kind, make in (("deb", deb), ("rpm", rpm), ("pkg.tar.zst", pacman)):
        name = f"EMA-Reader.{kind}"
        stage = staged(name)
        make(stage, out / name)
        shutil.rmtree(stage)
        print(f"hazır: {out / name} ({(out / name).stat().st_size / 1e6:.0f} MB)", flush=True)
    shutil.rmtree(PREFIX)


if __name__ == "__main__":
    main()
