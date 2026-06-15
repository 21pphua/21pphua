#!/usr/bin/env python3
"""Regenerate the packaged universe files under stockscan/universes/.

S&P 500 constituents are pulled from a public dataset mirror (no key). Class
shares are normalised to Yahoo's ``-`` convention (e.g. BRK.B -> BRK-B).

Usage:
    python scripts/refresh_universes.py
"""

from __future__ import annotations

import csv
import io
import os
import urllib.request

SP500_CSV = (
    "https://raw.githubusercontent.com/datasets/"
    "s-and-p-500-companies/main/data/constituents.csv"
)
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "stockscan", "universes")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8")


def refresh_sp500() -> int:
    rows = list(csv.DictReader(io.StringIO(_fetch(SP500_CSV))))
    syms = sorted({r["Symbol"].strip().upper() for r in rows if r.get("Symbol", "").strip()})
    syms = [s.replace(".", "-") for s in syms]  # BRK.B -> BRK-B for Yahoo
    path = os.path.join(OUT_DIR, "sp500.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# S&P 500 constituents (source: github.com/datasets/s-and-p-500-companies)\n")
        f.write("# Regenerate with: python scripts/refresh_universes.py\n")
        for s in syms:
            f.write(s + "\n")
    print(f"wrote {len(syms)} tickers -> {os.path.relpath(path)}")
    return len(syms)


if __name__ == "__main__":
    refresh_sp500()
