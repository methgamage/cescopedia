"""Store operations: proposals, drafts, uploads, approve / reject, change log. All state changes go through here."""
from __future__ import annotations

import hashlib
import io
import re
import shutil
import time
from pathlib import Path

import htmlutil
import store
from build import build_site
from core import (Cfg, atomic_write, now_iso, read_json, store_lock, today, valid_slug, write_json, new_id)

MAX_UPLOAD = 25 * 1024 * 1024


class OpError(Exception):
    """User-facing problem (bad input, conflict, not allowed)."""
    def __init__(self, msg, status=400, extra=None):
        super().__init__(msg)
        self.status, self.extra = status, extra or {}


# ---- uploads ---------------------------------------------------------------------------------------------------
def process_upload(cfg: Cfg, data: bytes, filename: str = "") -> dict:
    """Resize + compress a picture into the staging area. It reaches public assets/uploads/ only when a proposal
    that uses it is approved."""
    if not data or len(data) > MAX_UPLOAD:
        raise OpError("Picture is empty or larger than 25 MB.")
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise OpError("Pillow is required for picture upload (pip install pillow).", 500)
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise OpError("That file is not a readable picture (JPEG, PNG, GIF or WebP).")
    if im.format not in ("JPEG", "PNG", "GIF", "WEBP"):
        raise OpError("Only JPEG, PNG, GIF or WebP pictures are accepted.")
    im = ImageOps.exif_transpose(im)
    maxpx = int(cfg.data.get("max_image_px", 1600))
    if max(im.size) > maxpx:
        im.thumbnail((maxpx, maxpx), Image.LANCZOS)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    buf = io.BytesIO()
    if has_alpha:
        im.convert("RGBA").save(buf, "PNG", optimize=True)
        ext = "png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=int(cfg.data.get("jpeg_quality", 82)), optimize=True, progressive=True)
        ext = "jpg"
    out = buf.getvalue()
    h = hashlib.sha256(out).hexdigest()[:10]
    stem = re.sub(r"[^a-z0-9]+", "-", Path(filename or "picture").stem.lower()).strip("-")[:30] or "picture"
    name = f"{stem}-{h}.{ext}"
    cfg.staging.mkdir(parents=True, exist_ok=True)
    atomic_write(cfg.staging / name, out)
    return {"src": f"assets/uploads/{name}", "width": im.width, "height": im.height, "bytes": len(out)}


def find_image(cfg: Cfg, src: str) -> Path | None:
    """Locate a picture referenced as assets/... in the public site or the staging area."""
    if not re.match(r"^assets/[A-Za-z0-9_./\-]+$", src) or ".." in src:
        return None
    p = cfg.site_dir / src
    if p.is_file():
        return p
    if src.startswith("assets/uploads/"):
        q = cfg.staging / src[len("assets/uploads/"):]
        if q.is_file():
            return q
    return None


# ---- content normalisation -------------------------------------------------------------------------------------
def normalise_content(cfg: Cfg, live: dict, data: dict) -> dict:
    title = (data.get("title") or "").strip()
    if not title:
        raise OpError("The article needs a title.")
    body = htmlutil.ensure_heading_ids(htmlutil.sanitize(data.get("body_html") or ""))
    if not htmlutil.plain_text(body).strip() and "<img" not in body:
        raise OpError("The article body is empty.")
    problems = []
    for f in htmlutil.figures_of(body):
        for s in f["srcs"] or [""]:
            if not s or not find_image(cfg, s):
                problems.append(f"Picture not found: {s or '(missing src)'}")
        if not f["caption"].strip():
            problems.append("Every picture needs a caption" + (f" ({f['srcs'][0].rsplit('/', 1)[-1]})" if f["srcs"] else ""))
    if problems:
        raise OpError("; ".join(dict.fromkeys(problems)))
    return {"title": title, "dek": (data.get("dek") if data.get("dek") is not None else live.get("dek", "")).strip(),
            "description": (data.get("description") if data.get("description") is not None else live.get("description", "")).strip(),
            "body_html": body}


def live_fields(a: dict) -> dict:
    return {k: a.get(k, "") for k in ("title", "dek", "description", "body_html")}


# ---- drafts ----------------------------------------------------------------------------------------------------
def save_draft(cfg: Cfg, slug: str, data: dict, who: str):
    live = store.load_article(cfg, slug)
    d = {"article": slug, "title": data.get("title", ""), "dek": data.get("dek", ""), "description": data.get("description", ""),
         "body_html": htmlutil.sanitize(data.get("body_html") or ""), "saved_by": who, "saved_at": now_iso(),
         "base_version": int(data.get("base_version") or live["version"]), "summary": data.get("summary", "")}
    write_json(cfg.drafts / f"{slug}.json", d)
    return d


def load_draft(cfg: Cfg, slug: str) -> dict | None:
    p = cfg.drafts / f"{slug}.json"
    return read_json(p) if p.exists() else None


def delete_draft(cfg: Cfg, slug: str):
    p = cfg.drafts / f"{slug}.json"
    if p.exists():
        p.unlink()


# ---- proposals -------------------------------------------------------------------------------------------------
def create_proposal(cfg: Cfg, slug: str, data: dict, *, author_type: str, proposer: str, summary: str,
                    instruction: str | None = None, base_version: int | None = None, extra: dict | None = None) -> dict:
    if author_type not in ("human", "grok"):
        raise OpError("author_type must be human or grok")
    summary = (summary or "").strip()
    if len(summary) < 5:
        raise OpError("A change summary is required: say what you changed and why.")
    proposer = (proposer or "").strip()[:80]
    if not proposer:
        raise OpError("Proposer name is required.")
    with store_lock(cfg):
        live = store.load_article(cfg, slug)
        content = normalise_content(cfg, live, data)
        base_v = int(base_version or live["version"])
        try:
            base = store.load_version(cfg, slug, base_v)
        except KeyError:
            raise OpError(f"Unknown base version {base_v}.")
        d = htmlutil.diff_content(live_fields(base), content)
        if d["summary"]["no_change"]:
            raise OpError("No changes to submit: the content is identical to the base version.")
        pid = new_id()
        prop = {"id": pid, "article": slug, "author_type": author_type, "proposer": proposer, "created_at": now_iso(),
                "base_version": base_v, "summary": summary, "instruction": instruction or None,
                "content": dict(content, figures=htmlutil.figures_of(content["body_html"])),
                "diff": {"summary": d["summary"], "ops": d["ops"]}, "status": "pending", "resolution": None,
                "extra": dict(extra or {})}
        write_json(cfg.pending / f"{pid}.json", prop)
        store.append_history(cfg, {"event": "proposed", "id": pid, "article": slug, "author_type": author_type,
                                   "by": proposer, "at": prop["created_at"], "summary": summary})
        if author_type == "human":
            delete_draft(cfg, slug)
        return prop


def pending_for(cfg: Cfg, slug: str) -> list[dict]:
    return store.list_proposals(cfg, "pending", slug)


def publish_staged_images(cfg: Cfg, body_html: str) -> list[Path]:
    """Copy staged pictures used by approved content into the public assets/uploads/. Returns files newly created."""
    made = []
    for f in htmlutil.figures_of(body_html):
        for s in f["srcs"]:
            dst = cfg.site_dir / s
            if dst.exists() or not s.startswith("assets/uploads/"):
                continue
            src = cfg.staging / s[len("assets/uploads/"):]
            if not src.is_file():
                raise OpError(f"Staged picture missing: {s}", 500)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            made.append(dst)
    return made


def resolve_approver(cfg: Cfg, name: str) -> str:
    n = (name or "").strip().lower()
    for a in cfg.approvers:
        if a.lower() == n:
            return a
    raise OpError("You must type the name of an approver: " + ", ".join(cfg.approvers) + ".", 403)


def conflict_info(cfg: Cfg, prop: dict) -> dict | None:
    live = store.load_article(cfg, prop["article"])
    if live["version"] == prop["base_version"]:
        return None
    return {"base_version": prop["base_version"], "live_version": live["version"]}


def approve(cfg: Cfg, pid: str, approver: str, ack_conflict: bool = False) -> dict:
    approver = resolve_approver(cfg, approver)
    with store_lock(cfg):
        prop = read_json(cfg.pending / f"{pid}.json", default=None) if (cfg.pending / f"{pid}.json").exists() else None
        if not prop or prop["status"] != "pending":
            raise OpError("Proposal not found or already resolved.", 404)
        slug = prop["article"]
        live = store.load_article(cfg, slug)
        conf = conflict_info(cfg, prop)
        if conf and not ack_conflict:
            raise OpError(f"Conflict: the live article changed since this proposal was made (it was based on v{conf['base_version']}, "
                          f"live is now v{conf['live_version']}). Review the diff and tick the conflict box to confirm.", 409, {"conflict": conf})
        n = live["version"]
        new_n = n + 1
        content = prop["content"]
        now = now_iso()
        diff = htmlutil.diff_content(live_fields(live), content)
        # --- snapshot for rollback
        art_dir = cfg.articles / slug
        backup = {"article.json": (art_dir / "article.json").read_bytes(), "body.html": (art_dir / "body.html").read_bytes()}
        cl_all_before = cfg.changelog_json.read_bytes() if cfg.changelog_json.exists() else None
        acl = cfg.changelog_dir / f"{slug}.json"
        acl_before = acl.read_bytes() if acl.exists() else None
        vdir = store.version_dir(cfg, slug, n)
        if vdir.exists():
            raise OpError(f"Archive v{n} already exists for {slug}; refusing to overwrite.", 500)
        made_images: list[Path] = []
        try:
            # 1. archive the current live version as vN
            old_appr = live.get("approval")
            snap = dict(live)
            store._write_article_dir(vdir, snap)
            write_json(vdir / "meta.json", {
                "article": slug, "version": n, "date": (old_appr["approved_at"][:10] if old_appr else live.get("seed_date", "")),
                "approved_by": old_appr["approved_by"] if old_appr else None,
                "approved_at": old_appr["approved_at"] if old_appr else None,
                "summary": old_appr["summary"] if old_appr else "Seed import from Emmanuel's Oct 2026 encyclopedia set.",
                "status": "archived", "superseded_by": new_n, "superseded_at": now,
                "superseded_by_approver": approver, "superseded_by_pr": (prop.get("extra") or {}).get("pr_number")})
            # 2. the proposal's content becomes live as vN+1
            made_images = publish_staged_images(cfg, content["body_html"])
            new = dict(live)
            new.update(title=content["title"], dek=content["dek"], description=content["description"], body_html=content["body_html"],
                       figures=[{"src": f["src"], "alt": f["alt"], "caption": f["caption"]} for f in htmlutil.figures_of(content["body_html"])],
                       version=new_n,
                       approval={"approved_by": approver, "approved_at": now, "summary": prop["summary"], "proposal_id": pid,
                                 "author_type": prop["author_type"], "proposer": prop["proposer"], "from_version": n})
            store.save_article(cfg, new)
            # 3. change log (site-wide + per article)
            entry = {"id": f"{slug}-v{new_n:03d}", "article": slug, "title": new["title"], "from_version": n, "to_version": new_n,
                     "date": now[:10], "approved_at": now, "approved_by": approver, "proposer": prop["proposer"],
                     "author_type": prop["author_type"], "proposal_id": pid, "summary": prop["summary"],
                     "diff_summary": diff["summary"], "conflict_acknowledged": bool(conf),
                     "archived_page": f"archive-{slug}-v{n:03d}.html", "diff_page": f"diff-{slug}-v{n:03d}-v{new_n:03d}.html",
                     "article_page": f"{slug}.html"}
            entry.update(prop.get("extra") or {})   # e.g. pr_number, pr_url, branch (GitHub flow)
            write_json(cfg.changelog_json, store.load_changelog(cfg) + [entry])
            write_json(acl, store.article_changelog(cfg, slug) + [entry])
            # 4. rebuild pages (live page, archived page, diff, history, change log, homepage)
            build_site(cfg)
        except BaseException:
            for k, v in backup.items():
                atomic_write(art_dir / k, v)
            shutil.rmtree(vdir, ignore_errors=True)
            for p in made_images:
                p.unlink(missing_ok=True)
            for path, before in ((cfg.changelog_json, cl_all_before), (acl, acl_before)):
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, before)
            try:
                build_site(cfg)
            except Exception:
                pass
            raise
        prop["status"] = "approved"
        prop["resolution"] = {"by": approver, "at": now, "reason": None, "from_version": n, "to_version": new_n,
                              "conflict_acknowledged": bool(conf)}
        write_json(cfg.resolved / f"{pid}.json", prop)
        (cfg.pending / f"{pid}.json").unlink()
        store.append_history(cfg, {"event": "approved", "id": pid, "article": slug, "by": approver, "at": now,
                                   "from_version": n, "to_version": new_n, "summary": prop["summary"]})
        return entry


def reject(cfg: Cfg, pid: str, reviewer: str, reason: str) -> dict:
    reviewer = resolve_approver(cfg, reviewer)
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise OpError("A reason is required to reject a proposal.")
    with store_lock(cfg):
        p = cfg.pending / f"{pid}.json"
        if not p.exists():
            raise OpError("Proposal not found or already resolved.", 404)
        prop = read_json(p)
        now = now_iso()
        prop["status"] = "rejected"
        prop["resolution"] = {"by": reviewer, "at": now, "reason": reason}
        write_json(cfg.resolved / f"{pid}.json", prop)
        p.unlink()
        store.append_history(cfg, {"event": "rejected", "id": pid, "article": prop["article"], "by": reviewer, "at": now,
                                   "reason": reason, "summary": prop["summary"]})
        return prop
