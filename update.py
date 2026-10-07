"""Finds out whether a newer EMA Reader has been published.

    check("1.0.0")
    # {"current": "1.0.0", "latest": "1.1.0", "newer": True, "notes": "...", "page": "https://...",
    #  "download": "https://..." or None, "packaged": False}

A version is published by pushing a tag such as v1.1.0: the build workflow then makes a GitHub
release with the installers and that version's section of CHANGELOG.md as its notes. This asks
GitHub for the latest release, at most once every few hours, and never fails: without a network
or a release, `latest` is None and `newer` is False.
"""

import json
import os
import re
import sys
import time
import urllib.request

REPO = "sudoeren/ema-reader"
URL = os.environ.get("EMA_READER_UPDATE_URL") or f"https://api.github.com/repos/{REPO}/releases/latest"
FRESH = 6 * 3600  # how long an answer is kept
RETRY = 600  # how soon to ask again after a failure
INSTALLERS = {"win32": ".exe", "darwin": ".dmg"}  # on Linux the app runs from source and is updated with git

cache = {"until": 0, "release": None}


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


def release(data, platform=sys.platform):
    """What the reader needs from GitHub's description of a release."""
    def link(url):
        return url if isinstance(url, str) and url.startswith("https://github.com/") else None

    suffix = INSTALLERS.get(platform)
    installers = (a.get("browser_download_url") for a in data.get("assets") or [] if suffix and str(a.get("name", "")).endswith(suffix))
    return {"latest": ".".join(map(str, number(data["tag_name"]))), "notes": tidy(data.get("body")),
            "page": link(data.get("html_url")), "download": link(next(installers, None))}


def changelog(text, version):
    """The section of CHANGELOG.md for one version, without its heading; None when there is none."""
    found = re.search(rf"^## {re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return found.group(1).strip() if found else None


def check(current):
    now = time.time()
    if now >= cache["until"]:
        try:
            request = urllib.request.Request(URL, headers={"Accept": "application/vnd.github+json", "User-Agent": f"EMA Reader/{current}"})
            with urllib.request.urlopen(request, timeout=6) as response:
                cache["release"] = release(json.load(response))
            cache["until"] = now + FRESH
        except Exception:  # no network, no release yet, an answer that is not a release
            cache["until"] = now + RETRY
    found = cache["release"] or {"latest": None, "notes": "", "page": None, "download": None}
    return {"current": current, **found, "newer": bool(found["latest"]) and number(found["latest"]) > number(current),
            "packaged": bool(getattr(sys, "frozen", False))}


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
