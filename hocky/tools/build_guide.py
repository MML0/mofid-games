#!/usr/bin/env python3
"""Render docs/guide/guide_fa.html to docs/MarketHockey_Guide_FA.pdf with headless Chrome/Edge.

    python tools/build_guide.py
Chrome lays out Persian (RTL, joined letters) perfectly, so the guide is written as HTML + CSS.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "guide" / "guide_fa.html"
OUT = ROOT / "docs" / "MarketHockey_Guide_FA.pdf"
CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "google-chrome", "chromium", "chromium-browser",
]


def find_browser():
    for c in CANDIDATES:
        if Path(c).exists() or shutil.which(c):
            return c
    sys.exit("Chrome / Edge not found")


def main():
    browser = find_browser()
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
           "--virtual-time-budget=6000", f"--print-to-pdf={OUT}", SRC.as_uri()]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
