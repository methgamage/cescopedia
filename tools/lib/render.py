"""Page rendering for Cescopedia. Reproduces the existing generated layout exactly (same markup, same Cesco CSS),
adding only: footer 'Change log' link, versioned rail, archived-version / history / diff / change-log pages and the
filled 'Last edits' shell."""
from __future__ import annotations

import html
import re

import htmlutil
from core import Cfg
import store

e = lambda s: html.escape(s, quote=True)

HEAD_TMPL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta name="theme-color" content="#1e3a5f">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
{extra}  <link rel="icon" href="favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
"""

HEADER_TMPL = """  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header" id="site-header">
    <div class="header-inner">
      <a class="wordmark" href="index.html"><img class="wordmark-logo" src="assets/logo/cesco-logo-colour.png" alt="CESCO" width="52" height="62"><span class="wordmark-text">Cescopedia</span></a>
      <div class="search-wrap">
        <form id="site-search" role="search" autocomplete="off">
          <div class="search" data-filled="0">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.25"/><path d="m10.4 10.4 3.1 3.1" stroke-linecap="round"/></svg>
            <input id="site-search-input" type="text" role="searchbox" placeholder="Search" aria-label="Search Cescopedia" aria-autocomplete="list" aria-controls="site-search-menu" aria-expanded="false" autocomplete="off" spellcheck="false">
            <kbd data-kbd>Ctrl K</kbd>
            <button type="button" class="search-clear" aria-label="Clear search"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3.5 3.5 10.5 10.5M10.5 3.5 3.5 10.5" stroke-linecap="round"/></svg></button>
          </div>
          <div id="site-search-menu" class="search-menu" role="listbox" hidden></div>
        </form>
      </div>
      <div class="header-right">
        <button type="button" class="ghost" id="sections-btn" aria-expanded="false" aria-controls="sections-menu" aria-haspopup="true">Sections</button>
        <nav id="sections-menu" class="sections-menu" aria-label="Sections" hidden>
{nav}
        </nav>
      </div>
    </div>
  </header>
"""

FOOTER = """  <footer class="colophon">
    <a href="index.html">Cescopedia</a>
    <a href="changelog.html">Change log</a>
    <span>Shop reference</span>
  </footer>
  <script src="assets/site.js"></script>
</body>
</html>
"""

SEED_NOTE_NEW = "Each approved revision is archived and linked here. Pending edits wait in the approval queue and do not change this page."


def nav_html(site: dict, current: str | None) -> str:
    rows = []
    for s in site["sections"]:
        cur = ' aria-current="page"' if current and s["href"] == current else ""
        rows.append(f'        <a href="{e(s["href"])}"{cur}>{e(s["title"])}</a>')
    return "\n".join(rows)


def head(title: str, desc: str, canonical: str | None = None, noindex: bool = False) -> str:
    extra = ""
    if noindex:
        extra += '  <meta name="robots" content="noindex">\n'
    if canonical:
        extra += f'  <link rel="canonical" href="{e(canonical)}">\n'
    return HEAD_TMPL.format(title=e(title), desc=e(desc), extra=extra)


def header(site, current):
    return HEADER_TMPL.format(nav=nav_html(site, current))


def indent(body: str, n: int) -> str:
    pad = " " * n
    return "\n".join((pad + l) if l.strip() else l for l in body.split("\n"))


def toc_html(art: dict) -> str:
    toc = art.get("toc", "auto")
    if toc == "auto":
        toc = [{"id": m.group(1), "label": m.group(2), "raw": True} for m in re.finditer(r'<h2 id="([^"]+)">(.*?)</h2>', art["body_html"])]
    items = "\n".join(f'            <li><a class="toc-link" href="#{e(t["id"])}">{t["label"] if t.get("raw") else e(t["label"])}</a></li>' for t in toc)
    return f"""    <aside class="toc">
      <p class="toc-label" id="toc-label">On this page</p>
      <nav class="toc-nav" aria-labelledby="toc-label">
        <div class="toc-hair" aria-hidden="true"></div>
        <div class="toc-indicator" aria-hidden="true"></div>
        <ol class="toc-list">
{items}
        </ol>
      </nav>
    </aside>
"""


def crumbs_html(art: dict) -> str:
    rows = []
    cs = art["crumbs"]
    for i, c in enumerate(cs):
        if i:
            rows.append('        <span aria-hidden="true">/</span>')
        if c.get("href"):
            rows.append(f'        <a href="{e(c["href"])}">{e(c["label"])}</a>')
        else:
            rows.append(f'        <span aria-current="page">{e(c["label"])}</span>')
    return "\n".join(rows)


def ver_href(slug: str, n: int) -> str:
    return f"archive-{slug}-v{n:03d}.html"


def diff_href(slug: str, a: int, b: int) -> str:
    return f"diff-{slug}-v{a:03d}-v{b:03d}.html"


def history_href(slug: str) -> str:
    return f"history-{slug}.html"


def approval_text(appr: dict | None, version: int) -> str:
    if not appr:
        return "Pending Meth / EA"
    return f'Approved — {appr["approved_by"]}, {appr["approved_at"][:10]} (v{version})'


def version_entries(cfg: Cfg, art: dict) -> list[dict]:
    """All versions of an article, newest first: archived metas + the live one."""
    slug = art["slug"]
    metas = store.archived_versions(cfg, slug)
    live = art
    entries = [{"n": live["version"], "current": True, "date": (live.get("approval") or {}).get("approved_at", "")[:10] or live.get("seed_date", ""),
                "approved_by": (live.get("approval") or {}).get("approved_by"), "summary": (live.get("approval") or {}).get("summary", ""),
                "href": None}]
    for m in metas:
        entries.append({"n": m["version"], "current": False, "date": m.get("date", ""), "approved_by": m.get("approved_by"),
                        "summary": m.get("summary", ""), "href": ver_href(slug, m["version"]),
                        "superseded_by": m.get("superseded_by")})
    return sorted(entries, key=lambda x: -x["n"])


def short(s: str, n=110) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def rail_history(cfg: Cfg, art: dict, viewing: int, entries: list[dict]) -> str:
    rail = art["rail"]
    seed = rail["seed_history"]
    if len(entries) == 1 and not art.get("approval"):
        lis = "\n".join("            " + x for x in seed)
        note = f'<p class="rail-note">{e(SEED_NOTE_NEW)}</p>'
        return f"""        <section class="rail-card">
          <h2 class="rail-heading">Version history</h2>
          <ul class="rail-list">
{lis}
          </ul>
          {note}
        </section>"""
    lis = []
    for en in entries:
        who = f'Approved by {e(en["approved_by"])}' if en["approved_by"] else "Seed — not approved"
        label = f'v{en["n"]}'
        if en["current"]:
            head_ = f'<strong>{label} — current</strong>'
        elif en["n"] == viewing:
            head_ = f'<a href="{e(en["href"])}" aria-current="page">{label}</a> (viewing)'
        else:
            head_ = f'<a href="{e(en["href"])}">{label}</a>'
        s = f' — {e(short(en["summary"]))}' if en["summary"] and not en["summary"].startswith("Seed") else ""
        lis.append(f'            <li>{head_} · <time datetime="{e(en["date"])}">{e(en["date"])}</time> — {who}{s}</li>')
    lis.append("            " + seed[0])
    note = (f'<p class="rail-note"><a href="{history_href(art["slug"])}">Full history &amp; changes</a> · '
            f'<a href="changelog.html">Site change log</a></p>')
    return f"""        <section class="rail-card">
          <h2 class="rail-heading">Version history</h2>
          <ul class="rail-list">
{chr(10).join(lis)}
          </ul>
          {note}
        </section>"""


def rail_byline(art: dict, appr: dict | None, version: int) -> str:
    extra = ""
    if appr:
        who = appr.get("proposer") or ""
        kind = "Grok" if appr.get("author_type") == "grok" else "human"
        extra = f"""
            <div>
              <dt>Last edit</dt>
              <dd>{e(who)} ({kind})</dd>
            </div>"""
    return f"""        <section class="rail-card rail-byline">
          <h2 class="rail-heading">Author / Approved</h2>
          <dl class="rail-meta">
            <div>
              <dt>Author</dt>
              <dd>{e(art["rail"]["author"])}</dd>
            </div>
            <div>
              <dt>Approved</dt>
              <dd>{e(approval_text(appr, version))}</dd>
            </div>{extra}
          </dl>
        </section>"""


def chapter_nav(site: dict, slug: str, arts_meta: dict) -> str:
    ch = site["chapters"]
    if slug not in ch:
        return ""
    i = ch.index(slug)
    pn = []
    if i > 0:
        pn.append(f'<a class="chapter-prev" href="{ch[i-1]}.html">← {e(arts_meta[ch[i-1]]["crumb"])}</a>')
    if i + 1 < len(ch):
        pn.append(f'<a class="chapter-next" href="{ch[i+1]}.html">{e(arts_meta[ch[i+1]]["crumb"])} →</a>')
    return f'<nav class="chapter-nav" aria-label="Chapters">{"".join(pn)}</nav>'


def archive_banner(cfg: Cfg, art: dict, meta: dict, live: dict) -> str:
    slug, n = art["slug"], art["version"]
    nxt = meta["superseded_by"]
    who = f' · approved by {e(meta["approved_by"])}' if meta.get("approved_by") else " · seed version, never approved"
    return (f'<div class="archive-banner" role="status"><strong>Archived version v{n}</strong> · {e(meta["date"])}{who} · '
            f'superseded by v{nxt} on {e(meta["superseded_at"][:10])}. This is a read-only copy. '
            f'<a href="{slug}.html">View the current version</a> · <a href="{diff_href(slug, n, nxt)}">What changed in v{nxt}</a> · '
            f'<a href="{history_href(slug)}">History</a></div>')


def render_article(cfg: Cfg, site: dict, art: dict, arts_meta: dict, *, archive_meta: dict | None = None,
                   live: dict | None = None, preview_note: str | None = None, canonical: str | None = None,
                   assets_prefix: str = "") -> str:
    """Render one article page. archive_meta is set when rendering an archived version snapshot."""
    slug = art["slug"]
    appr = art.get("approval")
    title = art["title"]
    page_title = f'{title} — Cescopedia'
    if archive_meta:
        page_title = f'{title} — v{art["version"]} (archived) — Cescopedia'
    out = head(page_title, art["description"], canonical or art.get("canonical"), noindex=bool(archive_meta))
    out += header(site, art.get("nav_current"))
    entries = version_entries(cfg, live or art)
    edit_html = "" if archive_meta else edit_link(slug)
    banner = archive_banner(cfg, art, archive_meta, live or art) if archive_meta else ""
    if preview_note:
        banner = f'<div class="archive-banner preview-banner" role="status">{preview_note}</div>' + banner
    if art["template"] == "mounting":
        approved = "true" if appr else "false"
        ribbon = '<div class="approval-ribbon" role="status">Unapproved</div>\n\n        ' if not appr else ""
        # ribbon is always emitted in the original markup; CSS hides it once data-approved="true"
        ribbon = '<div class="approval-ribbon" role="status">Unapproved</div>'
        ban = (banner + "\n        ") if banner else ""
        rail = "\n\n".join([
            rail_history(cfg, art if not archive_meta else art, art["version"], entries),
            f"""        <section class="rail-card">
          <h2 class="rail-heading">Applicable ECOs</h2>
          {art["rail"]["ecos_html"]}
        </section>""",
            f"""        <section class="rail-card">
          <h2 class="rail-heading">Applicable Bulletins</h2>
          {art["rail"]["bulletins_html"]}
        </section>""",
            rail_byline(art, appr, art["version"])])
        nav = chapter_nav(site, slug, arts_meta)
        out += f"""  <main id="main" class="page page-article" data-approved="{approved}">
    <header class="article-head article-head-wide">
      <nav class="crumbs" aria-label="Breadcrumb">
{crumbs_html(art)}
      </nav>
      <div class="article-title-row">
        <h1 class="article-title">{e(title)}</h1>
        <p class="article-kicker">{e(art["kicker"])}</p>
      </div>
      <p class="dek">{e(art["dek"])}</p>
      {edit_html}
    </header>

    <div class="article-layout">
      <div class="article-main">
        {ban}{ribbon}

        <article class="prose prose-article">
{art["body_html"]}
{nav}
        </article>
      </div>

      <aside class="article-rail" aria-label="Article metadata">
{rail}
      </aside>
    </div>
  </main>
"""
    else:
        vnote = ""
        if appr or entries[0]["n"] > 1 or archive_meta:
            vnote = (f'\n      <p class="version-note">Version {art["version"]}'
                     + (f' · Approved by {e(appr["approved_by"])}, {e(appr["approved_at"][:10])}' if appr else " · Seed, not approved")
                     + f' · <a href="{history_href(slug)}">Version history</a> · <a href="changelog.html">Change log</a></p>')
        ban = (banner + "\n") if banner else ""
        out += f"""  <main id="main" class="page">
    <header class="article-head">
      <nav class="crumbs" aria-label="Breadcrumb">
{crumbs_html(art)}
      </nav>
      <h1 class="article-title">{e(title)}</h1>
      <p class="dek">{e(art["dek"])}</p>
      {edit_html}
    </header>
{ban}{toc_html(art)}    <article class="prose">
{indent(art["body_html"], 6)}{vnote}
    </article>
  </main>
"""
    out += FOOTER
    return out


# ---- new pages --------------------------------------------------------------------------------------------------
def simple_page(site, title, dek, crumbs, inner, desc="", current=None, noindex=False) -> str:
    cr = []
    for i, (label, href) in enumerate(crumbs):
        if i:
            cr.append('        <span aria-hidden="true">/</span>')
        cr.append(f'        <a href="{e(href)}">{e(label)}</a>' if href else f'        <span aria-current="page">{e(label)}</span>')
    return (head(f"{title} — Cescopedia", desc or dek, None, noindex) + header(site, current) + f"""  <main id="main" class="page">
    <header class="article-head">
      <nav class="crumbs" aria-label="Breadcrumb">
{chr(10).join(cr)}
      </nav>
      <h1 class="article-title">{e(title)}</h1>
      <p class="dek">{e(dek)}</p>
    </header>
    <article class="prose history-page">
{inner}
    </article>
  </main>
""" + FOOTER)


def pr_link(en: dict) -> str:
    url = en.get("pr_url") or ""
    if url.startswith("https://github.com/"):
        return f' · <a href="{e(url)}">pull request #{e(str(en.get("pr_number", "")))}</a>'
    return ""


def edit_link(slug: str) -> str:
    return (f'<p class="edit-link"><a href="edit/?article={slug}" rel="nofollow">&#9998; Edit this article</a>'
            f' <span>· changes go to the approval queue and appear only after Meth approves them</span></p>')


def entry_li(en: dict, article_titles: dict, with_article=True) -> str:
    slug, a, b = en["article"], en["from_version"], en["to_version"]
    t = e(article_titles.get(slug, slug))
    ds = en["diff_summary"]["text"]
    who = e(en["approved_by"])
    prop = f'{e(en["proposer"])} ({"Grok" if en["author_type"] == "grok" else "human"})'
    art_link = f'<a href="{slug}.html">{t}</a>' if with_article else f'<strong>v{b}</strong>'
    return f"""<li class="cl-entry">
  <div class="cl-head"><time datetime="{e(en["date"])}">{e(en["date"])}</time> {art_link} <span class="cl-ver">v{a} → v{b}</span></div>
  <p class="cl-summary">{e(en["summary"])}</p>
  <p class="cl-meta">{e(ds)} · approved by {who} · proposed by {prop}{pr_link(en)}</p>
  <p class="cl-links"><a href="{ver_href(slug, a)}">Archived v{a}</a> · <a href="{diff_href(slug, a, b)}">What changed (diff)</a> · <a href="{slug}.html">Current article</a> · <a href="{history_href(slug)}">Article history</a></p>
</li>"""


def changelog_page(site, entries: list[dict], titles: dict) -> str:
    entries = sorted(entries, key=lambda x: x["approved_at"], reverse=True)
    if entries:
        inner = f'<p>Every approved change, newest first. {len(entries)} approved edit{"s" if len(entries) != 1 else ""} so far.</p>\n<ol class="cl-list">\n' + "\n".join(entry_li(x, titles) for x in entries) + "\n</ol>"
    else:
        inner = '<p class="last-edits-empty">No approved edits yet.</p>'
    return simple_page(site, "Change log", "Every approved edit to Cescopedia, newest first, with links to the archived version and the diff.",
                       [("Cescopedia", "index.html"), ("Change log", None)], inner)


def history_page(cfg, site, art: dict, entries_log: list[dict], titles: dict) -> str:
    slug = art["slug"]
    vs = version_entries(cfg, art)
    rows = []
    for v in vs:
        who = f'Approved by {e(v["approved_by"])}' if v["approved_by"] else "Seed — not approved"
        link = f'<a href="{slug}.html">v{v["n"]} (current)</a>' if v["current"] else f'<a href="{e(v["href"])}">v{v["n"]}</a>'
        rows.append(f'<tr><td>{link}</td><td>{e(v["date"])}</td><td>{who}</td><td>{e(v["summary"]) or "—"}</td></tr>')
    table = ('<div class="table-wrap"><table class="spec-table"><thead><tr><th scope="col">Version</th><th scope="col">Date</th>'
             '<th scope="col">Approval</th><th scope="col">Summary</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")
    log = sorted(entries_log, key=lambda x: x["approved_at"], reverse=True)
    lst = ('<ol class="cl-list">\n' + "\n".join(entry_li(x, titles, with_article=False) for x in log) + "\n</ol>") if log else '<p class="last-edits-empty">No approved edits yet.</p>'
    inner = f'<h2 id="versions">Versions</h2>\n{table}\n<h2 id="changes">Change log for this article</h2>\n{lst}'
    return simple_page(site, f'{art["title"]} — history', "Archived versions and approved changes for this article.",
                       [("Cescopedia", "index.html"), (art["title"], f"{slug}.html"), ("History", None)], inner,
                       current=art.get("nav_current"))


def diff_page(cfg, site, slug: str, old: dict, new: dict, log: dict | None, titles: dict) -> str:
    a, b = old["version"], new["version"]
    d = htmlutil.diff_content(old, new)
    bits = ""
    if log:
        bits = (f'<p class="cl-summary"><strong>Summary:</strong> {e(log["summary"])}</p>'
                f'<p class="cl-meta">{e(log["diff_summary"]["text"])} · approved by {e(log["approved_by"])} on {e(log["date"])} · '
                f'proposed by {e(log["proposer"])} ({"Grok" if log["author_type"] == "grok" else "human"})</p>')
    inner = (f'{bits}<p class="cl-links"><a href="{ver_href(slug, a)}">Archived v{a}</a> · <a href="{slug}.html">Current article</a> · '
             f'<a href="{history_href(slug)}">Article history</a> · <a href="changelog.html">Change log</a></p>\n'
             + htmlutil.render_diff(d, f"v{a} (before)", f"v{b} (after)", old_fields=old, new_fields=new))
    return simple_page(site, f'{old["title"]}: v{a} → v{b}', "Differences between two versions. Additions in green, deletions in red.",
                       [("Cescopedia", "index.html"), (new["title"], f"{slug}.html"), (f"Changes v{a} → v{b}", None)], inner,
                       current=new.get("nav_current"))


def last_edits_html(entries: list[dict], titles: dict, limit=5) -> str:
    entries = sorted(entries, key=lambda x: x["approved_at"], reverse=True)[:limit]
    if not entries:
        return ('      <ul class="last-edits-list"></ul>\n'
                '      <p class="last-edits-empty">No approved edits yet</p>')
    lis = []
    for en in entries:
        slug, a, b = en["article"], en["from_version"], en["to_version"]
        lis.append(f'        <li><a href="{slug}.html"><time datetime="{e(en["date"])}">{e(en["date"])}</time><span class="last-edit-text">— {e(titles.get(slug, slug))} — v{b} — {e(short(en["summary"], 120))}</span></a>'
                   f'<span class="last-edit-links"><a href="{ver_href(slug, a)}">Archived v{a}</a><a href="{diff_href(slug, a, b)}">What changed</a></span></li>')
    return ('      <ul class="last-edits-list">\n' + "\n".join(lis) + "\n      </ul>\n"
            '      <p class="last-edits-empty">No approved edits yet</p>')
