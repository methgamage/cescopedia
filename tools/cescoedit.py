#!/usr/bin/env python3
"""cescoedit — Grok's command-line tool for Cescopedia (GitHub-native; propose-only).

It LISTS / SHOWS / DIFFS articles and PROPOSES edits by opening a pull request on GitHub (branch proposals/<article>-<timestamp>,
label 'grok'). It has NO merge / approve / publish command and never touches main. A human approves by merging the PR on GitHub.
It uses the `gh` CLI that is already logged in; it never reads, prints or stores a token.

  cescoedit.py list
  cescoedit.py show --article mudguards [--field body|title|dek|description|json] [--out FILE]
  cescoedit.py proposals                         (open proposal pull requests)
  cescoedit.py status --pr 12                    (OPEN / MERGED = approved and published / CLOSED = rejected)
  cescoedit.py diff --article X --content-file FILE        (what a proposal WOULD change; nothing is sent)
  cescoedit.py propose --article X --summary "what changed and why" --content-file FILE
  cescoedit.py propose --article X --summary "..." --patch-file patch.json
  cescoedit.py propose --article X --summary "..." --figure pic.jpg --caption "..." --alt "..." --after-heading "Heading"

--instruction "…" records the user's original request in the PR (for the approver). cescoedit does not write content by
itself: Grok produces the new body (or a patch) from the user's text / supplied sources first. See GROK-USAGE.md."""
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import sys
import subprocess
import time
import base64
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import htmlutil  # noqa: E402


REPO_DIR = HERE.parent
sys.path.insert(0, str(HERE / "lib"))
from core import Cfg  # noqa: E402
import ops  # noqa: E402
import store  # noqa: E402

CFG = Cfg(HERE / "config.json")
REPO = CFG.data["repo"]


def die(msg, code=1):
    print("cescoedit: " + msg, file=sys.stderr)
    sys.exit(code)


def gh(*args, input_json=None, check=True):
    """Run the gh CLI (already logged in as the repo owner). Never prints or handles the token."""
    r = subprocess.run(["gh", *args], input=json.dumps(input_json) if input_json is not None else None, capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def gh_api(method, path, body=None):
    args = ["api", "-X", method, path]
    if body is not None:
        args += ["--input", "-"]
    out = gh(*args, input_json=body)
    return json.loads(out) if out.strip() else {}


def sync():
    """Fast-forward the local clone so 'live' content is current (best effort; never changes anything on GitHub)."""
    subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only", "-q"], capture_output=True)


# ---- patch ops (applied locally to the HTML body) ---------------------------------------------------------------
def apply_patch(content: dict, ops: list) -> dict:
    c = dict(content)
    body = c["body_html"]
    for i, op in enumerate(ops, 1):
        k = op.get("op")
        if k == "replace_text":
            f, r = op["find"], op["replace"]
            n = body.count(f)
            if n == 0:
                die(f"patch op {i}: text not found in the article: {f[:60]!r}")
            if n > 1 and not op.get("all"):
                die(f"patch op {i}: text found {n} times; make 'find' longer/unique or set \"all\": true")
            body = body.replace(f, r)
        elif k == "append_html":
            body = body.rstrip() + "\n" + op["html"]
        elif k in ("insert_after_heading", "insert_before_heading"):
            m = None
            for mm in re.finditer(r"<h([23])[^>]*>(.*?)</h\1>", body, re.S):
                if op["heading"].strip().lower() in html.unescape(re.sub(r"<[^>]+>", "", mm.group(2))).lower():
                    m = mm
                    break
            if not m:
                die(f"patch op {i}: heading not found: {op['heading']!r}")
            if k == "insert_before_heading":
                body = body[:m.start()] + op["html"] + "\n" + body[m.start():]
            else:  # after the end of that section's first block run: place right before the next heading, or at end
                nxt = re.search(r"<h[23][ >]", body[m.end():])
                at = m.end() + nxt.start() if nxt else len(body)
                body = body[:at].rstrip("\n") + "\n" + op["html"] + "\n" + body[at:]
        elif k == "delete_block_containing":
            pat = re.compile(r"<(p|li)[ >](?:(?!</\1>).)*?" + re.escape(op["text"]) + r"(?:(?!</\1>).)*?</\1>", re.S)
            body, n = pat.subn("", body, count=1)
            if not n:
                die(f"patch op {i}: no paragraph/list item containing {op['text'][:50]!r}")
        elif k in ("set_title", "set_dek", "set_description"):
            c[k[4:]] = op["value"]
        else:
            die(f"patch op {i}: unknown op {k!r}")
    c["body_html"] = body
    return c


def figure_html(src, caption, alt):
    import hashlib
    fid = "fig-" + re.sub(r"\.[a-z]+$", "", src.rsplit("/", 1)[-1])
    return (f'<figure class="source-figure" id="{html.escape(fid)}"><a href="{html.escape(src)}"><img src="{html.escape(src)}" '
            f'alt="{html.escape(alt or caption, quote=True)}" loading="lazy"></a><figcaption>{html.escape(caption)}</figcaption></figure>')


def load_current(a, slug):
    if not getattr(a, "no_pull", False):
        sync()
    try:
        art = store.load_article(CFG, slug)
    except KeyError:
        die(f"unknown article: {slug}. Run: cescoedit.py list")
    return art


def content_from_args(a, cur):
    c = {k: cur.get(k, "") for k in ("title", "dek", "description", "body_html")}
    if a.content_file:
        p = Path(a.content_file)
        t = p.read_text(encoding="utf-8")
        if p.suffix == ".json":
            d = json.loads(t)
            c.update({k: d[k] for k in ("title", "dek", "description", "body_html") if k in d})
        else:
            c["body_html"] = t
    if a.patch_file:
        ops = json.loads(Path(a.patch_file).read_text(encoding="utf-8"))
        c = apply_patch(c, ops if isinstance(ops, list) else [ops])
    if a.title:
        c["title"] = a.title
    if a.dek:
        c["dek"] = a.dek
    if a.figure:
        fp = Path(a.figure)
        if not fp.is_file():
            die(f"figure file not found: {fp}")
        if not a.caption:
            die("--figure needs --caption")
        up = ops.process_upload(CFG, fp.read_bytes(), fp.name)     # resize + compress; kept in the git-ignored staging dir
        fh = figure_html(up["src"], a.caption, a.alt)
        if a.after_heading:
            c = apply_patch(c, [{"op": "insert_after_heading", "heading": a.after_heading, "html": fh}])
        else:
            c = apply_patch(c, [{"op": "append_html", "html": fh}])
    return c


def text_diff(old: dict, new: dict) -> str:
    d = htmlutil.diff_content(old, new)
    out = [f"== {d['summary']['text']}"]
    for k in ("title", "dek", "description"):
        if old.get(k, "") != new.get(k, ""):
            out.append(f"~ {k}: {old.get(k,'')!r} -> {new.get(k,'')!r}")
    for o in d["ops"]:
        if o["op"] == "equal":
            continue
        for b in o["old"]:
            if o["op"] in ("delete", "replace"):
                out.append("- " + (f"[figure {b['key']}] " if b["kind"] == "figure" else "") + b["text"])
        for b in o["new"]:
            if o["op"] in ("insert", "replace"):
                out.append("+ " + (f"[figure {b['key']}] " if b["kind"] == "figure" else "") + b["text"])
    return "\n".join(out)


def open_proposals():
    out = gh("pr", "list", "--repo", REPO, "--state", "open", "--limit", "100", "--json", "number,title,headRefName,author,labels,url,createdAt")
    return [p for p in json.loads(out) if p["headRefName"].startswith("proposals/") or p["title"].startswith("Edit ")]


def create_pr(slug, content, base_version, summary, instruction, agent, images):
    """Branch + commit + PR through the GitHub API (no local checkout is touched). Returns the PR."""
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    pid = f"{slug}-{ts}"
    branch = f"proposals/{pid}"
    meta = {"format": 1, "article": slug, "base_version": base_version, "title": content["title"], "dek": content["dek"],
            "description": content["description"], "summary": summary, "proposer": agent, "author_type": "grok",
            "instruction": instruction or None, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "images": [p.name for p in images]}
    files = [(f"proposals/{pid}/proposal.json", json.dumps(meta, indent=2, ensure_ascii=False) + "\n", False),
             (f"proposals/{pid}/body.html", content["body_html"] + "\n", False)]
    files += [(f"proposals/{pid}/uploads/{p.name}", base64.b64encode(p.read_bytes()).decode(), True) for p in images]
    ref = gh_api("GET", f"repos/{REPO}/git/ref/heads/main")["object"]["sha"]
    base_tree = gh_api("GET", f"repos/{REPO}/git/commits/{ref}")["tree"]["sha"]
    tree = []
    for path, data, is_b64 in files:
        b = gh_api("POST", f"repos/{REPO}/git/blobs", {"content": data, "encoding": "base64" if is_b64 else "utf-8"})
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": b["sha"]})
    t = gh_api("POST", f"repos/{REPO}/git/trees", {"base_tree": base_tree, "tree": tree})
    c = gh_api("POST", f"repos/{REPO}/git/commits", {"message": f"Proposal (grok): {slug} — {summary.splitlines()[0][:100]}", "tree": t["sha"], "parents": [ref]})
    gh_api("POST", f"repos/{REPO}/git/refs", {"ref": f"refs/heads/{branch}", "sha": c["sha"]})
    body = (f"**Article:** `{slug}` (based on live v{base_version})\n**Proposed by:** {agent} (**Grok**, via cescoedit)\n\n## Change summary\n\n{summary}\n\n"
            + (f"## User's request\n\n{instruction}\n\n" if instruction else "")
            + f"---\nFiles: `proposals/{pid}/`. **Merging this pull request approves the change** (only the repository owner can merge). "
              "Grok never merges. After the merge a workflow archives the old version, updates the change log and publishes. Closing it discards the proposal.")
    pr = gh_api("POST", f"repos/{REPO}/pulls", {"title": f"Edit {slug}: {summary.splitlines()[0][:80]}", "head": branch, "base": "main", "body": body})
    subprocess.run(["gh", "api", "-X", "POST", f"repos/{REPO}/labels", "-f", "name=grok", "-f", "color=6f42c1", "-f", "description=Proposed by Grok"], capture_output=True)
    gh_api("POST", f"repos/{REPO}/issues/{pr['number']}/labels", {"labels": ["grok"]})
    return pr


def main():
    ap = argparse.ArgumentParser(description="Grok's propose-only client for Cescopedia (opens pull requests; never merges).")
    ap.add_argument("--no-pull", action="store_true", help="do not fast-forward the local clone first")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("--article", required=True); s.add_argument("--field", default="body"); s.add_argument("--out")
    sub.add_parser("proposals")
    s = sub.add_parser("status"); s.add_argument("--pr", required=True, type=int)
    for name in ("diff", "propose"):
        s = sub.add_parser(name)
        s.add_argument("--article")
        s.add_argument("--content-file"); s.add_argument("--patch-file")
        s.add_argument("--title"); s.add_argument("--dek")
        s.add_argument("--figure"); s.add_argument("--caption"); s.add_argument("--alt")
        s.add_argument("--after-heading"); s.add_argument("--at-end", action="store_true")
        s.add_argument("--summary"); s.add_argument("--instruction"); s.add_argument("--agent", default="grok")
        s.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.cmd == "list":
        if not a.no_pull:
            sync()
        pend: dict = {}
        for p in open_proposals():
            m = re.match(r"proposals/(.+)-\d{8}-\d{6}$", p["headRefName"])
            if m:
                pend[m.group(1)] = pend.get(m.group(1), 0) + 1
        for slug in store.article_slugs(CFG):
            x = store.load_article(CFG, slug)
            print(f"{slug:24s} v{x['version']:<3d} {'approved' if x.get('approval') else 'unapproved':10s} open_proposals={pend.get(slug, 0)}  {x['title']}")
    elif a.cmd == "show":
        c = load_current(a, a.article)
        f = a.field
        txt = json.dumps(c, indent=2, ensure_ascii=False) if f == "json" else {"body": c["body_html"], "title": c["title"], "dek": c["dek"], "description": c["description"]}[f]
        if a.out:
            Path(a.out).write_text(txt, encoding="utf-8"); print(f"wrote {a.out} (live v{c['version']})")
        else:
            print(txt)
    elif a.cmd == "proposals":
        for p in open_proposals():
            lab = ",".join(l["name"] for l in p["labels"])
            print(f"#{p['number']:<4d} {p['headRefName']:46s} by {p['author']['login']:12s} [{lab}] {p['title'][:60]}  {p['url']}")
    elif a.cmd == "status":
        p = json.loads(gh("pr", "view", str(a.pr), "--repo", REPO, "--json", "state,mergedAt,mergedBy,title,url"))
        meaning = {"OPEN": "waiting for human approval", "MERGED": "approved and published", "CLOSED": "closed without merging (not approved)"}[p["state"]]
        print(f"PR #{a.pr}: {p['state']} — {meaning}\n{p['title']}\n{p['url']}")
        if p["state"] == "MERGED":
            print(f"merged {p['mergedAt']} by {(p.get('mergedBy') or {}).get('login')}")
    elif a.cmd in ("diff", "propose"):
        if not a.article:
            die("--article is required")
        cur = load_current(a, a.article)
        if not (a.content_file or a.patch_file or a.figure or a.title or a.dek):
            if a.instruction:
                die("cescoedit does not write content itself. Produce the new text yourself from the user's words or the supplied sources, "
                    "then pass it with --content-file or --patch-file (or --figure / --title / --dek). See GROK-USAGE.md.", 2)
            die("nothing to propose: give --content-file, --patch-file, --figure, --title or --dek", 2)
        new = content_from_args(a, cur)
        try:
            norm = ops.normalise_content(CFG, cur, new)            # same sanitising and checks the workflow applies
        except ops.OpError as ex:
            die(str(ex))
        print(text_diff(cur, norm))
        if a.cmd == "diff" or a.dry_run:
            return
        if not (a.summary and len(a.summary.strip()) >= 5):
            die("--summary is required: say what changed and why (a human reads it when approving).", 2)
        if htmlutil.diff_content(ops.live_fields(cur), norm)["summary"]["no_change"]:
            die("no changes to submit.")
        imgs = []
        for f in htmlutil.figures_of(norm["body_html"]):
            for src in f["srcs"]:
                if src.startswith("assets/uploads/") and not (CFG.site_dir / src).exists():
                    imgs.append(CFG.staging / src.rsplit("/", 1)[-1])
        pr = create_pr(a.article, norm, cur["version"], a.summary.strip(), a.instruction, a.agent, imgs)
        print(f"opened pull request #{pr['number']}: {pr['html_url']}\nstatus=OPEN. It is waiting for human approval (Meth merging it). It is NOT live.")


if __name__ == "__main__":
    main()
