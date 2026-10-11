#!/usr/bin/env python3
"""Apply merged proposals to the content store and rebuild the site. Run by .github/workflows/apply-proposals.yml AFTER a
pull request has been merged into main (never on the PR itself). Standard library + Pillow.

A proposal is a directory  proposals/<article>-<YYYYMMDD-HHMMSS>/  containing
    proposal.json   {format, article, base_version, title, dek, description, summary, proposer, author_type, created_at, images:[...]}
    body.html       the proposed article body
    uploads/*       pictures used by the body (already resized/compressed by the editor), referenced as assets/uploads/<name>

For every such directory this script:
  1. checks the approver (the person who merged the PR) is listed in tools/config.json "approvers";
  2. refuses (moves to proposals/_conflict/) when the live article moved on since base_version;
  3. sanitises the HTML, copies pictures to assets/uploads/, archives the previous version under
     content/versions/<article>/vNNN/ (with its date and the approver), writes the change-log entry (summary + diff counts),
     regenerates pages, archive pages, history, change log and homepage 'Last edits' with the normal build code;
  4. deletes the proposal directory (git history keeps it).
Result lines go to stdout and to --result-file (JSON) so the workflow can comment on the PR."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import ops  # noqa: E402
import store  # noqa: E402
from core import Cfg, valid_slug, read_json, write_json  # noqa: E402

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}-\d{8}-\d{6}$")
IMG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,80}\.(jpg|png)$")
MAX_IMG = 6 * 1024 * 1024


def check_images(pdir: Path, names: list[str]) -> list[Path]:
    from PIL import Image
    out = []
    up = pdir / "uploads"
    # pictures normally sit in uploads/; the "download and drag onto GitHub's upload page" route puts them next to proposal.json
    srcs = list(up.iterdir()) if up.is_dir() else []
    srcs += [p for p in pdir.iterdir() if p.is_file() and p.suffix in (".jpg", ".png")]
    byname = {p.name: p for p in srcs}
    present = sorted(byname)
    for n in present:
        if not IMG_RE.match(n):
            raise ops.OpError(f"Unacceptable picture file name: {n}")
    for n in names:
        if n not in present:
            raise ops.OpError(f"Picture listed but not uploaded: {n}")
    for n in present:
        f = byname[n]
        if f.stat().st_size > MAX_IMG:
            raise ops.OpError(f"Picture too large: {n}")
        try:
            with Image.open(f) as im:
                im.verify()
            with Image.open(f) as im:
                if im.format not in ("JPEG", "PNG"):
                    raise ValueError(im.format)
        except Exception:
            raise ops.OpError(f"Not a valid JPEG/PNG picture: {n}")
        out.append(f)
    return out


def apply_one(cfg: Cfg, pdir: Path, a) -> dict:
    meta = json.loads((pdir / "proposal.json").read_text(encoding="utf-8"))
    pid = pdir.name
    slug = meta.get("article", "")
    if not ID_RE.match(pid) or not pid.startswith(slug + "-") or not valid_slug(slug):
        raise ops.OpError("Proposal directory name does not match its article.")
    live = store.load_article(cfg, slug)
    base = int(meta.get("base_version") or 0)
    if base != live["version"]:
        raise ops.OpError(f"Conflict: proposal is based on v{base} but the live article is now v{live['version']}. "
                          "Re-open the editor (it loads the latest version), redo the change and submit again.", 409)
    body = (pdir / "body.html").read_text(encoding="utf-8")
    imgs = check_images(pdir, list(meta.get("images") or []))
    made = []
    for f in imgs:                                   # pictures become public only here, on approval
        dst = cfg.site_dir / "assets" / "uploads" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(f, dst)
            made.append(dst)
    author_type = "grok" if (meta.get("author_type") == "grok" or a.grok) else "human"
    proposer = (meta.get("proposer") or a.pr_author or "unknown").strip()[:80]
    extra = {"pr_number": a.pr, "pr_url": a.pr_url, "branch": a.branch, "pr_author": a.pr_author, "proposal_dir": pid}
    try:
        prop = ops.create_proposal(cfg, slug, {"title": meta.get("title"), "dek": meta.get("dek"), "description": meta.get("description"),
                                               "body_html": body}, author_type=author_type, proposer=proposer,
                                   summary=meta.get("summary", ""), base_version=base, extra={k: v for k, v in extra.items() if v})
        entry = ops.approve(cfg, prop["id"], a.approver)
    except BaseException:
        for p in made:
            p.unlink(missing_ok=True)
        raise
    (cfg.resolved / f"{prop['id']}.json").unlink(missing_ok=True)
    shutil.rmtree(pdir)
    return entry


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--approver", required=True, help="GitHub login of the person who merged the pull request")
    ap.add_argument("--pr", type=int); ap.add_argument("--pr-url"); ap.add_argument("--pr-author"); ap.add_argument("--branch")
    ap.add_argument("--grok", action="store_true", help="the PR carries the 'grok' label")
    ap.add_argument("--result-file")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = Cfg(a.config)
    root = cfg.site_dir / "proposals"
    results, rc = [], 0
    for pdir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")) if root.is_dir() else []:
        try:
            e = apply_one(cfg, pdir, a)
            results.append({"id": pdir.name, "ok": True, "article": e["article"], "from": e["from_version"], "to": e["to_version"],
                            "diff": e["diff_summary"]["text"], "approver": e["approved_by"]})
            print(f"APPLIED {pdir.name}: {e['article']} v{e['from_version']} -> v{e['to_version']} ({e['diff_summary']['text']}) approved by {e['approved_by']}")
        except ops.OpError as ex:
            rc = 1
            dst = root / "_conflict" / pdir.name
            dst.parent.mkdir(exist_ok=True)
            shutil.rmtree(dst, ignore_errors=True)
            shutil.move(str(pdir), str(dst))
            write_json(dst / "result.json", {"error": str(ex), "approver": a.approver, "pr": a.pr})
            results.append({"id": pdir.name, "ok": False, "error": str(ex)})
            print(f"NOT APPLIED {pdir.name}: {ex}")
        except Exception as ex:   # malformed proposal
            rc = 1
            dst = root / "_conflict" / pdir.name
            dst.parent.mkdir(exist_ok=True)
            shutil.rmtree(dst, ignore_errors=True)
            shutil.move(str(pdir), str(dst))
            write_json(dst / "result.json", {"error": f"{type(ex).__name__}: {ex}", "approver": a.approver, "pr": a.pr})
            results.append({"id": pdir.name, "ok": False, "error": f"{type(ex).__name__}: {ex}"})
            print(f"NOT APPLIED {pdir.name}: {type(ex).__name__}: {ex}")
    if not results:
        print("No proposals to apply.")
    if a.result_file:
        Path(a.result_file).write_text(json.dumps(results, indent=2))
    sys.exit(rc)


if __name__ == "__main__":
    main()
