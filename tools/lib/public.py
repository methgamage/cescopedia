"""What counts as the public site: generated pages + assets only (never _build, admin, drafts, pending, content store)."""
from __future__ import annotations

from pathlib import Path


def public_files(site_dir: Path) -> list[Path]:
    """Relative paths of every file that may be published or zipped."""
    site_dir = Path(site_dir)
    out = []
    for p in sorted(site_dir.iterdir()):
        if p.is_file() and (p.suffix == ".html" or p.name == "favicon.svg"):
            out.append(p.relative_to(site_dir))
    assets = site_dir / "assets"
    for p in sorted(assets.rglob("*")):
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(site_dir).parts):
            out.append(p.relative_to(site_dir))
    edit = site_dir / "edit"
    if edit.is_dir():                      # the static editor is part of the public site
        out += [p.relative_to(site_dir) for p in sorted(edit.rglob("*")) if p.is_file()]
    return out
