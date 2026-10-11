#!/usr/bin/env python3
"""Zip the PUBLIC site only (pages, assets incl. uploads, the static editor). No content store, tools, workflows, proposals or secrets.
  make_zip.py [dest.zip]   default /workspace/cescopedia.zip ; layout: cesco-pedia/..."""
import sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from core import Cfg
from public import public_files

cfg = Cfg(Path(__file__).resolve().parent / "config.json")
dest = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/cescopedia.zip")
files = public_files(cfg.site_dir)
tmp = dest.with_suffix(".zip.tmp")
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
    for rel in files:
        z.write(cfg.site_dir / rel, "cesco-pedia/" + rel.as_posix())
tmp.replace(dest)
bad = [n for n in zipfile.ZipFile(dest).namelist() if any(x in n for x in ("content/", "proposals/", "tools/", ".github", "secrets", "token", ".py", ".json"))]
assert not bad, bad
print(f"wrote {dest}: {len(files)} files")
