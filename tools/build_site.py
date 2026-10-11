#!/usr/bin/env python3
"""Rebuild the public Cescopedia pages from the content store.
  build_site.py            rebuild in place into the configured site dir
  build_site.py --out DIR  build a full copy into DIR (assets copied) without touching the live site"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from core import Cfg, store_lock
import build

ap = argparse.ArgumentParser()
ap.add_argument("--out")
ap.add_argument("--config")
a = ap.parse_args()
cfg = Cfg(a.config)
with store_lock(cfg):
    files = build.build_site(cfg, Path(a.out) if a.out else None)
print(f"built {len(files)} files into {a.out or cfg.site_dir}")
