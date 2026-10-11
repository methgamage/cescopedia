"""File-based content store: articles (live), versions (archive), pending/resolved proposals, change log."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from core import Cfg, atomic_write, read_json, write_json, valid_slug


def load_site(cfg: Cfg) -> dict:
    return read_json(cfg.site_json)


def article_slugs(cfg: Cfg) -> list[str]:
    return list(load_site(cfg)["order"])


def _read_article_dir(d: Path) -> dict:
    art = read_json(d / "article.json")
    art["body_html"] = (d / "body.html").read_text(encoding="utf-8")
    return art


def _write_article_dir(d: Path, art: dict):
    art = dict(art)
    body = art.pop("body_html", "")
    d.mkdir(parents=True, exist_ok=True)
    atomic_write(d / "body.html", body)
    write_json(d / "article.json", art)


def load_article(cfg: Cfg, slug: str) -> dict:
    if not valid_slug(slug):
        raise KeyError(slug)
    d = cfg.articles / slug
    if not d.is_dir():
        raise KeyError(slug)
    return _read_article_dir(d)


def save_article(cfg: Cfg, art: dict):
    _write_article_dir(cfg.articles / art["slug"], art)


def version_dir(cfg: Cfg, slug: str, n: int) -> Path:
    return cfg.versions / slug / f"v{n:03d}"


def load_version(cfg: Cfg, slug: str, n: int) -> dict:
    """An archived snapshot (article dict + 'archive' meta) or, if n is the live version, the live article."""
    d = version_dir(cfg, slug, n)
    if d.is_dir():
        a = _read_article_dir(d)
        a["archive"] = read_json(d / "meta.json")
        return a
    live = load_article(cfg, slug)
    if live["version"] == n:
        return live
    raise KeyError((slug, n))


def archived_versions(cfg: Cfg, slug: str) -> list[dict]:
    """meta.json of every archived version, oldest first."""
    base = cfg.versions / slug
    out = []
    if base.is_dir():
        for d in sorted(base.iterdir()):
            if (d / "meta.json").exists():
                out.append(read_json(d / "meta.json"))
    return sorted(out, key=lambda m: m["version"])


# ---- change log ------------------------------------------------------------------------------------------------
def load_changelog(cfg: Cfg) -> list[dict]:
    return read_json(cfg.changelog_json, default=[]) if cfg.changelog_json.exists() else []


def article_changelog(cfg: Cfg, slug: str) -> list[dict]:
    p = cfg.changelog_dir / f"{slug}.json"
    return read_json(p, default=[]) if p.exists() else []


# ---- proposals -------------------------------------------------------------------------------------------------
def load_proposal(cfg: Cfg, pid: str) -> dict | None:
    for d in (cfg.pending, cfg.resolved):
        p = d / f"{pid}.json"
        if p.exists():
            return read_json(p)
    return None


def list_proposals(cfg: Cfg, status: str | None = None, article: str | None = None) -> list[dict]:
    out = []
    dirs = [cfg.pending, cfg.resolved] if status in (None, "all") else ([cfg.pending] if status == "pending" else [cfg.resolved])
    for d in dirs:
        if d.is_dir():
            for p in sorted(d.glob("*.json")):
                pr = read_json(p)
                if status in (None, "all") or pr.get("status") == status:
                    if article is None or pr.get("article") == article:
                        out.append(pr)
    return sorted(out, key=lambda x: x["created_at"])


def pending_counts(cfg: Cfg) -> dict:
    c: dict = {}
    for p in list_proposals(cfg, "pending"):
        c[p["article"]] = c.get(p["article"], 0) + 1
    return c


def append_history(cfg: Cfg, rec: dict):
    cfg.history_log.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg.history_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_history(cfg: Cfg) -> list[dict]:
    if not cfg.history_log.exists():
        return []
    return [json.loads(l) for l in cfg.history_log.read_text(encoding="utf-8").splitlines() if l.strip()]
