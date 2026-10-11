"""HTML helpers: sanitiser, block/figure extraction, diffing, diff rendering. Standard library only."""
from __future__ import annotations

import difflib
import html
import re
from html.parser import HTMLParser

VOID = {"br", "img", "hr"}
# tag -> allowed attributes
ALLOWED = {
    "p": {"class"}, "br": set(), "hr": set(), "strong": set(), "em": set(), "u": set(), "code": {"class"},
    "h2": {"id", "class"}, "h3": {"id", "class"},
    "ul": {"class"}, "ol": {"class", "type", "start"}, "li": {"class"},
    "table": {"class"}, "thead": set(), "tbody": set(), "tr": set(),
    "th": {"scope", "colspan", "rowspan", "class"}, "td": {"colspan", "rowspan", "class"},
    "div": {"class", "id"}, "span": {"class"},
    "a": {"href", "class", "id"},
    "figure": {"class", "id"}, "figcaption": {"class"}, "img": {"src", "alt", "loading"},
    "aside": {"class", "role", "aria-label"},
    "details": {"class", "id", "open"}, "summary": set(),
    "time": {"datetime"}, "sup": set(), "sub": set(), "blockquote": set(),
}
REWRITE = {"b": "strong", "i": "em", "strike": "s", "s": None, "del": None}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript", "template", "svg", "math"}
CLASS_OK = re.compile(r"^[A-Za-z0-9_\- ]{0,120}$")
ID_OK = re.compile(r"^[A-Za-z0-9_\-:.]{1,120}$")
HREF_OK = re.compile(r"^(https?://|mailto:|#|[A-Za-z0-9_./\-]+(\.html)?(#[A-Za-z0-9_\-]+)?$)", re.I)
SRC_OK = re.compile(r"^assets/[A-Za-z0-9_./\-]+$")


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip = 0
        self.skip_tag = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip:
            if tag == self.skip_tag:
                self.skip += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.skip, self.skip_tag = 1, tag
            return
        tag = REWRITE.get(tag, tag) if tag in REWRITE else tag
        if tag is None or tag not in ALLOWED:
            return
        at = dict((k.lower(), v if v is not None else "") for k, v in attrs)
        keep = []
        for k in at:
            if k not in ALLOWED[tag]:
                continue
            v = at[k]
            if k == "class" and not CLASS_OK.match(v):
                continue
            if k in ("id",) and not ID_OK.match(v):
                continue
            if k == "href" and not HREF_OK.match(v.strip()):
                continue
            if k == "src" and not SRC_OK.match(v.strip()):
                continue
            if k in ("start", "colspan", "rowspan") and not v.isdigit():
                continue
            if k == "type" and v not in ("a", "A", "i", "I", "1"):
                continue
            if k == "scope" and v not in ("row", "col"):
                continue
            if k == "loading":
                v = "lazy"
            keep.append((k, v.strip() if k in ("href", "src") else v))
        if tag == "img" and not any(k == "src" for k, _ in keep):
            return
        if tag == "span" and not any(k == "class" and v.strip() for k, v in keep):
            return  # unwrap style-only spans created by browsers
        s = "<" + tag + "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in keep) + ">"
        self.out.append(s)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip:
            if tag == self.skip_tag:
                self.skip -= 1
                if not self.skip:
                    self.skip_tag = None
            return
        tag = REWRITE.get(tag, tag) if tag in REWRITE else tag
        if tag is None or tag not in ALLOWED or tag in VOID:
            return
        if tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def close_all(self):
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")


def sanitize(src: str) -> str:
    p = _Sanitizer()
    p.feed(src or "")
    p.close()
    p.close_all()
    out = "".join(p.out)
    out = out.replace("\u00a0", " ") if False else out
    # tidy: editors leave empty paragraphs / stray <br>-only paragraphs
    out = re.sub(r'<p class="source-added">\s*<span class="source-added-tag">[^<]*</span>\s*[\u201c\u201d"]*\s*</p>', "", out)
    out = re.sub(r"<(p|li|h2|h3)\b[^>]*>(?:\s|<br>)*</\1>", "", out)
    return out.strip()


# ---------------------------------------------------------------------------------------------------------------
class _Blocks(HTMLParser):
    """Flatten HTML to an ordered list of text blocks: headings, paragraphs (p/li/td/th/summary) and figures."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.bufs: list[list] = []  # [tag, [text...]]
        self.fig: dict | None = None
        self.in_cap = False
        self.cap: list[str] = []

    def _flush_top(self):
        if self.bufs:
            tag, txt = self.bufs[-1]
            t = norm("".join(txt))
            if t:
                self.emit(tag, t)
            self.bufs[-1][1] = []

    def emit(self, tag, t):
        if tag in ("h2", "h3"):
            self.blocks.append({"kind": "heading", "level": int(tag[1]), "text": t})
        else:
            self.blocks.append({"kind": "para", "tag": tag, "text": t})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "figure":
            self.fig = {"kind": "figure", "srcs": [], "alts": [], "caption": "", "id": a.get("id", "")}
        elif tag == "img" and self.fig is not None:
            self.fig["srcs"].append(a.get("src", ""))
            self.fig["alts"].append(a.get("alt", ""))
        elif tag == "figcaption" and self.fig is not None:
            self.in_cap, self.cap = True, []
        elif self.fig is not None:
            return
        elif tag in ("p", "li", "td", "th", "h2", "h3", "summary"):
            self.bufs.append([tag, []])
        elif tag in ("ul", "ol") and self.bufs and self.bufs[-1][0] == "li":
            self._flush_top()
        elif tag == "br" and self.bufs:
            self.bufs[-1][1].append(" ")

    def handle_endtag(self, tag):
        if tag == "figcaption" and self.fig is not None:
            self.fig["caption"] = norm("".join(self.cap))
            self.in_cap = False
        elif tag == "figure" and self.fig is not None:
            f = self.fig
            self.blocks.append({"kind": "figure", "key": "|".join(f["srcs"]), "srcs": f["srcs"], "alt": " / ".join(f["alts"]),
                                "caption": f["caption"], "text": f["caption"]})
            self.fig = None
        elif self.fig is not None:
            return
        elif tag in ("p", "li", "td", "th", "h2", "h3", "summary") and self.bufs:
            # close to the matching open tag
            while self.bufs:
                t, txt = self.bufs.pop()
                s = norm("".join(txt))
                if s:
                    self.emit(t, s)
                if t == tag:
                    break

    def handle_data(self, data):
        if self.in_cap:
            self.cap.append(data)
        elif self.fig is None and self.bufs:
            self.bufs[-1][1].append(data)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip()


def blocks_of(body_html: str) -> list[dict]:
    p = _Blocks()
    p.feed(body_html or "")
    p.close()
    while p.bufs:
        t, txt = p.bufs.pop()
        s = norm("".join(txt))
        if s:
            p.emit(t, s)
    return p.blocks


def figures_of(body_html: str) -> list[dict]:
    return [{"src": b["srcs"][0] if b["srcs"] else "", "srcs": b["srcs"], "alt": b["alt"], "caption": b["caption"]}
            for b in blocks_of(body_html) if b["kind"] == "figure"]


def plain_text(body_html: str) -> str:
    return " ".join(b["text"] for b in blocks_of(body_html))


def bkey(b: dict):
    if b["kind"] == "figure":
        return ("figure", b["key"])
    if b["kind"] == "heading":
        return ("heading", b["level"], b["text"])
    return ("para", b["text"])


def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def diff_content(old: dict, new: dict) -> dict:
    """Structured diff between two article dicts (needs title, dek, description, body_html)."""
    ob, nb = blocks_of(old.get("body_html", "")), blocks_of(new.get("body_html", ""))
    sm = difflib.SequenceMatcher(None, [bkey(b) for b in ob], [bkey(b) for b in nb], autojunk=False)
    ops: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append({"op": "equal", "old": ob[i1:i2], "new": nb[j1:j2]})
        elif tag == "delete":
            ops.append({"op": "delete", "old": ob[i1:i2], "new": []})
        elif tag == "insert":
            ops.append({"op": "insert", "old": [], "new": nb[j1:j2]})
        else:  # replace: pair similar blocks of the same kind, rest are plain add / remove
            a, b = ob[i1:i2], nb[j1:j2]
            used_b = set()
            pairs = {}
            for ia, x in enumerate(a):
                best, bj = 0.0, None
                for jb, y in enumerate(b):
                    if jb in used_b or x["kind"] != y["kind"]:
                        continue
                    if x["kind"] == "figure":
                        r = 1.0 if x["key"] == y["key"] else 0.0
                    else:
                        r = _sim(x["text"], y["text"])
                    if r > best:
                        best, bj = r, jb
                if bj is not None and best >= (0.99 if x["kind"] == "figure" else 0.45):
                    pairs[ia] = bj
                    used_b.add(bj)
            # emit in an order that keeps both sides readable (monotonic pairs only)
            ia = jb = 0
            last_b = -1
            seq = []
            for ia, x in enumerate(a):
                if ia in pairs and pairs[ia] > last_b:
                    j = pairs[ia]
                    for jj in range(last_b + 1, j):
                        if jj not in used_b:
                            seq.append({"op": "insert", "old": [], "new": [b[jj]]})
                    seq.append({"op": "replace", "old": [x], "new": [b[j]]})
                    last_b = j
                else:
                    if ia in pairs:
                        used_b.discard(pairs[ia])
                    seq.append({"op": "delete", "old": [x], "new": []})
            for jj in range(last_b + 1, len(b)):
                seq.append({"op": "insert", "old": [], "new": [b[jj]]})
            ops.extend(seq)
    # counts
    pa = pr = pc = fa = fr = fc = 0
    h_added, h_removed, h_renamed = [], [], []
    for o in ops:
        if o["op"] == "insert":
            for b in o["new"]:
                if b["kind"] == "figure":
                    fa += 1
                elif b["kind"] == "heading":
                    h_added.append(b["text"])
                else:
                    pa += 1
        elif o["op"] == "delete":
            for b in o["old"]:
                if b["kind"] == "figure":
                    fr += 1
                elif b["kind"] == "heading":
                    h_removed.append(b["text"])
                else:
                    pr += 1
        elif o["op"] == "replace":
            x, y = o["old"][0], o["new"][0]
            if x["kind"] == "figure":
                if (x["caption"], x["alt"]) != (y["caption"], y["alt"]):
                    fc += 1
                else:
                    o["op"] = "equal"
            elif x["kind"] == "heading":
                h_renamed.append([x["text"], y["text"]])
            else:
                pc += 1
    # headings that moved between kinds of ops are fine; also level change
    meta = {k: (old.get(k, "") != new.get(k, "")) for k in ("title", "dek", "description")}
    changed_headings = ([f"+ {h}" for h in h_added] + [f"- {h}" for h in h_removed]
                        + [f"{a} → {b}" for a, b in h_renamed])
    summary = {
        "paragraphs": {"added": pa, "removed": pr, "changed": pc},
        "figures": {"added": fa, "removed": fr, "changed": fc},
        "headings": {"added": h_added, "removed": h_removed, "renamed": h_renamed},
        "changed_headings": changed_headings,
        "fields_changed": [k for k, v in meta.items() if v],
    }
    summary["text"] = describe(summary)
    nothing = not (pa or pr or pc or fa or fr or fc or changed_headings or summary["fields_changed"])
    body_same = norm(sanitize(old.get("body_html", ""))) == norm(sanitize(new.get("body_html", "")))
    summary["no_change"] = nothing and body_same
    if nothing and not body_same:
        summary["text"] = "formatting / markup changes only (no text, heading or figure changes)"
    return {"ops": ops, "summary": summary}


def describe(s: dict) -> str:
    bits = []
    p, f = s["paragraphs"], s["figures"]
    for label, d in (("paragraph", p), ("figure", f)):
        parts = []
        for k in ("added", "removed", "changed"):
            if d[k]:
                parts.append(f"{d[k]} {k}")
        if parts:
            bits.append(f"{label}s " + ", ".join(parts))
    if s["changed_headings"]:
        bits.append("headings: " + "; ".join(s["changed_headings"]))
    if s["fields_changed"]:
        bits.append("fields changed: " + ", ".join(s["fields_changed"]))
    return " · ".join(bits) if bits else "no content changes"


# ---- rendering -------------------------------------------------------------------------------------------------
E = lambda s: html.escape(s, quote=True)


def _words(s):
    return re.findall(r"\s+|[^\s]+", s)


def word_diff(a: str, b: str) -> tuple[str, str]:
    wa, wb = _words(a), _words(b)
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    ha, hb = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        ta, tb = E("".join(wa[i1:i2])), E("".join(wb[j1:j2]))
        if tag == "equal":
            ha.append(ta), hb.append(tb)
        else:
            if ta:
                ha.append(f'<del class="d-del">{ta}</del>')
            if tb:
                hb.append(f'<ins class="d-ins">{tb}</ins>')
    return "".join(ha), "".join(hb)


def _blk(b: dict, text_html: str | None = None, img_prefix: str = "") -> str:
    if b["kind"] == "figure":
        imgs = "".join(f'<img src="{E(img_prefix + s)}" alt="{E(b["alt"])}">' for s in b["srcs"])
        cap = text_html if text_html is not None else E(b["caption"])
        return f'<div class="d-fig">{imgs}<div class="d-cap">Caption: {cap or "<em>(none)</em>"}</div></div>'
    if b["kind"] == "heading":
        return f'<div class="d-h d-h{b["level"]}"><span class="d-tag">H{b["level"]}</span> {text_html if text_html is not None else E(b["text"])}</div>'
    return f'<div class="d-p">{text_html if text_html is not None else E(b["text"])}</div>'


def render_diff(diff: dict, old_label="Before", new_label="After", img_prefix="", old_fields=None, new_fields=None) -> str:
    """Side-by-side diff (additions green, deletions red)."""
    rows = []
    if old_fields is not None and new_fields is not None:
        for k, lab in (("title", "Title"), ("dek", "Subtitle"), ("description", "Description")):
            if old_fields.get(k, "") != new_fields.get(k, ""):
                a, b = word_diff(old_fields.get(k, ""), new_fields.get(k, ""))
                rows.append(f'<tr class="d-row d-replace"><td class="d-old"><span class="d-tag">{lab}</span> {a}</td>'
                            f'<td class="d-new"><span class="d-tag">{lab}</span> {b}</td></tr>')
    for o in diff["ops"]:
        if o["op"] == "equal":
            n = len(o["old"])
            if n <= 3:
                for b in o["old"]:
                    h = _blk(b, img_prefix=img_prefix)
                    rows.append(f'<tr class="d-row d-equal"><td class="d-old">{h}</td><td class="d-new">{h}</td></tr>')
            else:
                inner = "".join(f'<div class="d-eq-item">{_blk(b, img_prefix=img_prefix)}</div>' for b in o["old"])
                rows.append(f'<tr class="d-row d-equal d-collapsed"><td colspan="2"><details><summary>{n} unchanged blocks</summary>{inner}</details></td></tr>')
        elif o["op"] == "delete":
            for b in o["old"]:
                rows.append(f'<tr class="d-row d-delete"><td class="d-old">{_blk(b, img_prefix=img_prefix)}</td><td class="d-new d-empty"></td></tr>')
        elif o["op"] == "insert":
            for b in o["new"]:
                rows.append(f'<tr class="d-row d-insert"><td class="d-old d-empty"></td><td class="d-new">{_blk(b, img_prefix=img_prefix)}</td></tr>')
        else:
            x, y = o["old"][0], o["new"][0]
            if x["kind"] == "figure":
                ca, cb = word_diff(x["caption"], y["caption"])
                ha, hb = _blk(x, ca, img_prefix), _blk(y, cb, img_prefix)
            else:
                ta, tb = word_diff(x["text"], y["text"])
                ha, hb = _blk(x, ta, img_prefix), _blk(y, tb, img_prefix)
            rows.append(f'<tr class="d-row d-replace"><td class="d-old">{ha}</td><td class="d-new">{hb}</td></tr>')
    if not rows:
        rows.append('<tr class="d-row"><td colspan="2"><em>No differences.</em></td></tr>')
    return (f'<table class="diff-table"><thead><tr><th>{E(old_label)}</th><th>{E(new_label)}</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _slugify(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t).lower()
    t = re.sub(r"&[a-z]+;", "", t)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60].rstrip("-") or "section"


def ensure_heading_ids(body: str) -> str:
    """Give every h2/h3 an id (anchors, contents list, search catalogue)."""
    used = set(re.findall(r'\bid="([^"]+)"', body))

    def fix(m):
        lvl, inner = m.group(1), m.group(2)
        base = _slugify(inner)
        cand, i = base, 2
        while cand in used:
            cand = f"{base}-{i}"
            i += 1
        used.add(cand)
        return f'<h{lvl} id="{cand}">{inner}</h{lvl}>'
    return re.sub(r"<h([23])>(.*?)</h\1>", fix, body, flags=re.S)
