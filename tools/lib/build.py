"""Generate the public site from the content store. One entry point: build_site()."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import htmlutil
import render
import store
from core import Cfg, atomic_write, now_iso

CSS_MARK = "/* === cescopedia editing system v1 (generated; do not edit) === */"
CSS_FILE = Path(__file__).resolve().parent.parent / "static" / "site-history.css"
CATALOG_RE = re.compile(r"var catalog = \[\n.*?\n  \];", re.S)


def js_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def make_catalog(site: dict, arts: dict) -> str:
    rows = []
    for s in site["sections"]:
        rows.append((s["title"], s["href"], "Section"))
    for slug in site["search_order"]:
        a = arts[slug]
        rows.append((a["title"], f"{slug}.html", a["search"]["group"]))
    for slug in site["order"]:
        a = arts[slug]
        if a["search"].get("anchors"):
            for m in re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', a["body_html"]):
                label = re.sub(r"<[^>]+>", "", m.group(2))
                import html as _h
                if m.group(1) == "related":
                    continue
                rows.append((_h.unescape(label).title(), f"{slug}.html#{m.group(1)}", a["search"]["group"]))
    body = "\n".join(f'    {{ title: {js_str(t)}, href: {js_str(h)}, group: {js_str(g)} }},' for t, h, g in rows)
    return "var catalog = [\n" + body + "\n  ];"


def ensure_css_block(css_path: Path):
    s = css_path.read_text(encoding="utf-8")
    if CSS_MARK in s:
        s = s[:s.index(CSS_MARK)].rstrip("\n") + "\n"
    block = CSS_FILE.read_text(encoding="utf-8")
    atomic_write(css_path, s + "\n" + CSS_MARK + "\n" + block.rstrip() + "\n")


def build_site(cfg: Cfg, out: Path | None = None, quiet=True) -> list[str]:
    """Write every generated page. If out is given, the site dir's static assets are copied there first
    (used by tests / comparisons); otherwise pages are written in place into cfg.site_dir."""
    site = store.load_site(cfg)
    out = Path(out) if out else cfg.site_dir
    if out != cfg.site_dir:
        out.mkdir(parents=True, exist_ok=True)
        for item in cfg.site_dir.iterdir():
            if item.name in ("_build",) or item.name.startswith("."):
                continue
            dst = out / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            elif item.suffix != ".html":
                shutil.copy2(item, dst)
    arts = {s: store.load_article(cfg, s) for s in site["order"]}
    meta = {s: {"crumb": a["crumbs"][-1]["label"]} for s, a in arts.items()}
    titles = {s: a["title"] for s, a in arts.items()}
    log_all = store.load_changelog(cfg)
    written: list[str] = []

    def w(name: str, text: str):
        atomic_write(out / name, text)
        written.append(name)

    for slug, art in arts.items():
        w(f"{slug}.html", render.render_article(cfg, site, art, meta))
        for alias, target in site.get("aliases", {}).items():
            if target == slug:
                w(f"{alias}.html", render.render_article(cfg, site, art, meta, canonical=f"{slug}.html"))
        metas = store.archived_versions(cfg, slug)
        if metas or art["version"] > 1:
            alog = {(x["from_version"], x["to_version"]): x for x in store.article_changelog(cfg, slug)}
            for m in metas:
                old = store.load_version(cfg, slug, m["version"])
                w(render.ver_href(slug, m["version"]), render.render_article(cfg, site, old, meta, archive_meta=m, live=art))
                new = store.load_version(cfg, slug, m["superseded_by"])
                w(render.diff_href(slug, m["version"], m["superseded_by"]),
                  render.diff_page(cfg, site, slug, old, new, alog.get((m["version"], m["superseded_by"])), titles))
            w(render.history_href(slug), render.history_page(cfg, site, art, list(alog.values()), titles))
    w("changelog.html", render.changelog_page(site, log_all, titles))
    # homepage
    home = cfg.home_template.read_text(encoding="utf-8")
    home = home.replace("<!--CESCO:LAST_EDITS-->", render.last_edits_html(log_all, titles))
    w("index.html", home)
    # search catalog
    js = out / "assets" / "site.js"
    if js.exists():
        s = js.read_text(encoding="utf-8")
        new = make_catalog(site, arts)
        s2 = CATALOG_RE.sub(lambda m: new, s, count=1)
        if s2 != s:
            atomic_write(js, s2)
        written.append("assets/site.js")
    css = out / "assets" / "styles.css"
    if css.exists():
        ensure_css_block(css)
        written.append("assets/styles.css")
    return written
