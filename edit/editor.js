/* Cescopedia WYSIWYG editor — contenteditable + document commands, no external libraries. */
window.cescoStartEditor = function (init) {
  "use strict";
  const ed = document.getElementById("editor");
  const $ = (id) => document.getElementById(id);
  const fTitle = $("f-title"), fDek = $("f-dek"), fDesc = $("f-desc");
  const msg = $("ed-msg");
  let baseVersion = init.version;
  let dirty = false;
  let lastRange = null;
  let selFig = null;
  const panel = $("figpanel");

  try { document.execCommand("styleWithCSS", false, false); document.execCommand("defaultParagraphSeparator", false, "p"); } catch (e) {}

  /* ---------- load / serialise ---------- */
  function prepare() {
    ed.querySelectorAll("details.source-verbatim").forEach((d) => d.setAttribute("contenteditable", "false"));
    ed.querySelectorAll("figure").forEach((f) => {
      f.setAttribute("contenteditable", "false");
      const c = f.querySelector("figcaption");
      if (c) c.setAttribute("contenteditable", "true");
    });
  }
  function load(html) { ed.innerHTML = html; prepare(); selectFig(null); }
  function serialize() {
    const c = ed.cloneNode(true);
    c.querySelectorAll("img[data-src]").forEach((i) => { i.setAttribute("src", i.getAttribute("data-src")); i.removeAttribute("data-src"); });
    c.querySelectorAll("[contenteditable]").forEach((x) => x.removeAttribute("contenteditable"));
    c.querySelectorAll(".ed-selected").forEach((x) => x.classList.remove("ed-selected"));
    c.querySelectorAll("[class='']").forEach((x) => x.removeAttribute("class"));
    c.querySelectorAll("[spellcheck]").forEach((x) => x.removeAttribute("spellcheck"));
    return c.innerHTML;
  }
  load(init.body_html);

  /* ---------- own undo / redo (covers figure and table edits too) ---------- */
  let hist = [ed.innerHTML], pos = 0, timer = null;
  function snap() {
    clearTimeout(timer);
    const h = ed.innerHTML;
    if (h === hist[pos]) return;
    hist = hist.slice(0, pos + 1); hist.push(h); pos = hist.length - 1;
    if (hist.length > 200) { hist.shift(); pos--; }
  }
  function changed() { dirty = true; clearTimeout(timer); timer = setTimeout(snap, 350); }
  function restore(i) {
    if (i < 0 || i >= hist.length) return;
    pos = i; ed.innerHTML = hist[pos]; prepare(); selectFig(null); dirty = true;
  }
  function undo() { snap(); restore(pos - 1); }
  function redo() { restore(pos + 1); }
  ed.addEventListener("input", changed);
  [fTitle, fDek, fDesc].forEach((x) => x.addEventListener("input", () => { dirty = true; }));
  ed.addEventListener("keydown", (e) => {
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && !e.altKey) {
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
    }
    if (k === "enter" && e.target.closest && e.target.closest("figcaption")) e.preventDefault();
    if ((k === "delete" || k === "backspace") && selFig && !(document.activeElement && document.activeElement.closest && document.activeElement.closest("figcaption"))) {
      e.preventDefault(); deleteFig();
    }
  });

  /* ---------- selection helpers ---------- */
  document.addEventListener("selectionchange", () => {
    const s = window.getSelection();
    if (s.rangeCount && ed.contains(s.anchorNode)) {
      lastRange = s.getRangeAt(0).cloneRange();
      const inTable = !!(s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement).closest("table");
      $("toolbar").classList.toggle("in-table", inTable);
    }
  });
  function topBlock(node) {
    while (node && node.parentNode !== ed) node = node.parentNode;
    return node && node.parentNode === ed ? node : null;
  }
  function insertAfterBlock(el) {
    let ref = lastRange && ed.contains(lastRange.startContainer) ? topBlock(lastRange.startContainer) : null;
    if (ref && ref.nodeType === 1 && ref.matches("details.source-verbatim")) ref = ref.previousElementSibling || ref;
    if (ref) ref.after(el); else ed.appendChild(el);
    if (!el.nextElementSibling) { const p = document.createElement("p"); p.innerHTML = "<br>"; el.after(p); }
    prepare(); snap(); dirty = true;
  }
  function currentCell() {
    const s = window.getSelection();
    if (!s.rangeCount) return null;
    const n = s.anchorNode && (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement);
    return n && ed.contains(n) ? n.closest("td,th") : null;
  }

  /* ---------- toolbar ---------- */
  $("toolbar").addEventListener("mousedown", (e) => { if (e.target.closest("button")) e.preventDefault(); }); // keep selection
  $("toolbar").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    ed.focus();
    if (b.dataset.cmd) { document.execCommand(b.dataset.cmd, false, null); changed(); snap(); }
    else if (b.dataset.block) { document.execCommand("formatBlock", false, b.dataset.block.toUpperCase()); changed(); snap(); }
    else if (b.dataset.tbl) tableOp(b.dataset.tbl);
  });
  $("tb-undo").onclick = undo; $("tb-redo").onclick = redo;
  $("tb-clear").onclick = () => {
    ed.focus(); document.execCommand("removeFormat", false, null);
    const s = window.getSelection();
    const n = s.anchorNode && (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement);
    if (n && n.closest("h2,h3")) document.execCommand("formatBlock", false, "P");
    changed(); snap();
  };

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

  /* links */
  $("tb-link").onclick = () => {
    const s = window.getSelection();
    if (s.rangeCount) lastRange = s.getRangeAt(0).cloneRange();
    const a = lastRange && (lastRange.startContainer.nodeType === 1 ? lastRange.startContainer : lastRange.startContainer.parentElement).closest("a");
    $("link-url").value = a ? a.getAttribute("href") : "";
    $("dlg-link").showModal(); $("link-url").focus();
  };
  $("link-cancel").onclick = () => $("dlg-link").close();
  $("link-ok").onclick = () => {
    const url = $("link-url").value.trim();
    $("dlg-link").close();
    if (!url) return;
    if (/^\s*(javascript|data):/i.test(url)) return;
    ed.focus(); restoreRange();
    document.execCommand("createLink", false, url); changed(); snap();
  };
  function restoreRange() {
    if (lastRange) { const s = window.getSelection(); s.removeAllRanges(); s.addRange(lastRange); }
  }

  /* tables */
  $("tb-table").onclick = () => {
    const s = window.getSelection(); if (s.rangeCount && ed.contains(s.anchorNode)) lastRange = s.getRangeAt(0).cloneRange();
    $("dlg-table").showModal();
  };
  $("tbl-cancel").onclick = () => $("dlg-table").close();
  $("tbl-ok").onclick = () => {
    const r = Math.max(1, Math.min(30, +$("tbl-rows").value || 3)), c = Math.max(1, Math.min(12, +$("tbl-cols").value || 3));
    $("dlg-table").close();
    let h = '<div class="table-wrap"><table class="spec-table"><thead><tr>';
    for (let i = 0; i < c; i++) h += '<th scope="col">Heading</th>';
    h += "</tr></thead><tbody>";
    for (let j = 0; j < r; j++) { h += "<tr>"; for (let i = 0; i < c; i++) h += "<td><br></td>"; h += "</tr>"; }
    h += "</tbody></table></div>";
    const t = document.createElement("template"); t.innerHTML = h;
    insertAfterBlock(t.content.firstElementChild);
  };
  function tableOp(op) {
    const cell = currentCell(); if (!cell) return;
    const row = cell.parentElement, table = cell.closest("table"), idx = cell.cellIndex;
    const mk = (tag) => { const c = document.createElement(tag); if (tag === "th") c.setAttribute("scope", "col"); c.innerHTML = tag === "th" ? "Heading" : "<br>"; return c; };
    if (op === "row+") {
      const nr = document.createElement("tr");
      for (let i = 0; i < row.cells.length; i++) nr.appendChild(mk("td"));
      if (row.parentElement.tagName === "THEAD") { let tb = table.tBodies[0] || table.appendChild(document.createElement("tbody")); tb.insertBefore(nr, tb.firstChild); }
      else row.after(nr);
    } else if (op === "col+") {
      Array.from(table.rows).forEach((r) => { const isH = r.parentElement.tagName === "THEAD"; const c = mk(isH ? "th" : "td"); const ref = r.cells[idx]; if (ref) ref.after(c); else r.appendChild(c); });
    } else if (op === "row-") {
      if (table.rows.length <= 1) delTable(table); else row.remove();
    } else if (op === "col-") {
      if (row.cells.length <= 1) delTable(table); else Array.from(table.rows).forEach((r) => r.cells[idx] && r.cells[idx].remove());
    } else if (op === "del") delTable(table);
    changed(); snap();
  }
  function delTable(t) { const w = t.closest(".table-wrap"); (w || t).remove(); }

  /* ---------- figures ---------- */
  const dlg = $("dlg-figure"), fileIn = $("fig-file"), prev = $("fig-preview"), fcap = $("fig-caption"), falt = $("fig-alt"), fmsg = $("fig-msg"), fins = $("fig-insert");
  let figSrc = null;
  function refreshInsert() { fins.disabled = !(figSrc && fcap.value.trim()); }
  function openFigure(file) {
    const s = window.getSelection(); if (s.rangeCount && ed.contains(s.anchorNode)) lastRange = s.getRangeAt(0).cloneRange();
    figSrc = null; prev.hidden = true; fcap.value = ""; falt.value = ""; fmsg.textContent = ""; fmsg.className = "msg"; fileIn.value = ""; refreshInsert();
    if (!dlg.open) dlg.showModal();
    if (file) upload(file);
  }
  let figBlobUrl = null;
  async function upload(file) {
    if (!/^image\//.test(file.type)) { fmsg.className = "msg err"; fmsg.textContent = "That is not a picture."; return; }
    fmsg.className = "msg"; fmsg.textContent = "Resizing and compressing…";
    let r;
    try { r = await CescoImages.process(file); } catch (e) { fmsg.className = "msg err"; fmsg.textContent = e.message || "Could not read that picture."; return; }
    CescoImages.pending[r.name] = r.blob;
    figSrc = "assets/uploads/" + r.name; figBlobUrl = r.url; prev.src = r.url; prev.hidden = false;
    fmsg.className = "msg ok"; fmsg.textContent = r.width + "×" + r.height + " px, " + Math.round(r.bytes / 1024) + " KB (resized and compressed in your browser)";
    refreshInsert();
  }
  $("tb-figure").onclick = () => openFigure(null);
  fileIn.onchange = () => fileIn.files[0] && upload(fileIn.files[0]);
  fcap.oninput = refreshInsert;
  $("fig-cancel").onclick = () => dlg.close();
  const dz = $("dropzone");
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) upload(f); });
  ed.addEventListener("dragover", (e) => { if (e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files")) e.preventDefault(); });
  ed.addEventListener("drop", (e) => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (f && /^image\//.test(f.type)) {
      e.preventDefault();
      const rng = document.caretRangeFromPoint ? document.caretRangeFromPoint(e.clientX, e.clientY) : null;
      if (rng && ed.contains(rng.startContainer)) lastRange = rng;
      openFigure(f);
    }
  });
  ed.addEventListener("paste", (e) => {
    const cd = e.clipboardData; if (!cd) return;
    const f = Array.from(cd.files || []).find((x) => /^image\//.test(x.type));
    if (f) { e.preventDefault(); openFigure(f); return; }
    const html = cd.getData("text/html");
    if (html) { e.preventDefault(); document.execCommand("insertHTML", false, cleanPasted(html)); changed(); }
  });
  function cleanPasted(html) {
    const t = document.createElement("template"); t.innerHTML = html;
    t.content.querySelectorAll("script,style,meta,link,title,iframe,object,embed,img,figure").forEach((n) => n.remove());
    const keep = new Set(["P","BR","STRONG","EM","U","H2","H3","UL","OL","LI","TABLE","THEAD","TBODY","TR","TH","TD","A","B","I"]);
    (function walk(n) {
      Array.from(n.children).forEach((c) => {
        walk(c);
        if (!keep.has(c.tagName)) { c.replaceWith(...Array.from(c.childNodes)); return; }
        Array.from(c.attributes).forEach((a) => { if (!(c.tagName === "A" && a.name === "href") && !["colspan","rowspan"].includes(a.name)) c.removeAttribute(a.name); });
      });
    })(t.content);
    return t.innerHTML;
  }
  fins.onclick = () => {
    const cap = fcap.value.trim().replace(/\s+/g, " "), alt = (falt.value.trim() || cap);
    if (!figSrc || !cap) return;
    dlg.close();
    const id = "fig-" + figSrc.split("/").pop().replace(/\.[a-z]+$/, "");
    const h = '<figure class="source-figure" id="' + esc(id) + '"><a href="' + esc(figSrc) + '"><img src="' + esc(figBlobUrl || figSrc) + '" data-src="' + esc(figSrc) + '" alt="' + esc(alt) + '" loading="lazy"></a><figcaption>' + esc(cap) + "</figcaption></figure>";
    const t = document.createElement("template"); t.innerHTML = h;
    insertAfterBlock(t.content.firstElementChild);
    changed();
  };

  /* figure selection panel: alt text, delete, move */
  function selectFig(f) {
    if (selFig) selFig.classList.remove("ed-selected");
    selFig = f;
    if (!f) { panel.hidden = true; panel.innerHTML = ""; return; }
    f.classList.add("ed-selected");
    const imgs = Array.from(f.querySelectorAll("img"));
    panel.innerHTML = imgs.map((im, i) => '<label>Alt text' + (imgs.length > 1 ? " (picture " + (i + 1) + ")" : "") + '<input data-alt="' + i + '" value="' + esc(im.getAttribute("alt") || "") + '"></label>').join("") +
      '<span class="muted">Edit the caption directly under the picture.</span><button type="button" class="btn small" id="fp-up">Move up</button><button type="button" class="btn small" id="fp-down">Move down</button><button type="button" class="btn small danger" id="fp-del">Delete picture</button>';
    panel.hidden = false;
    panel.querySelectorAll("input[data-alt]").forEach((inp) => inp.addEventListener("input", () => { imgs[+inp.dataset.alt].setAttribute("alt", inp.value); changed(); }));
    $("fp-del").onclick = deleteFig;
    $("fp-up").onclick = () => { const p = f.previousElementSibling; if (p) { p.before(f); changed(); snap(); } };
    $("fp-down").onclick = () => { const n = f.nextElementSibling; if (n) { n.after(f); changed(); snap(); } };
  }
  function deleteFig() { if (selFig) { const f = selFig; selectFig(null); f.remove(); changed(); snap(); } }
  ed.addEventListener("click", (e) => {
    const f = e.target.closest("figure");
    if (f && ed.contains(f)) { if (e.target.closest("a")) e.preventDefault(); selectFig(f); }
    else if (!e.target.closest("figure")) selectFig(null);
  });

  /* ---------- draft / submit ---------- */
  function payload() {
    return { title: fTitle.value, dek: fDek.value, description: fDesc.value, body_html: serialize(), base_version: baseVersion };
  }
  function note(t, cls) { msg.className = "msg " + (cls || ""); msg.textContent = t; }
  function missingCaption() {
    const bad = Array.from(ed.querySelectorAll("figure")).find((f) => !(f.querySelector("figcaption") && f.querySelector("figcaption").textContent.trim()));
    if (bad) { selectFig(bad); bad.scrollIntoView({ block: "center" }); return true; }
    return false;
  }
  function usedImages() {
    const names = new Set();
    serialize().replace(/src="assets\/uploads\/([^"]+)"/g, (m, n) => { if (CescoImages.pending[n]) names.add(n); return m; });
    return Array.from(names);
  }
  function checkReady() {
    if (missingCaption()) { note("Every picture needs a caption before you submit.", "err"); return false; }
    if (!fTitle.value.trim()) { note("The article needs a title.", "err"); return false; }
    return true;
  }
  function proposal(summary) {
    return { article: init.slug, base_version: baseVersion, title: fTitle.value.trim(), dek: fDek.value.trim(), description: fDesc.value.trim(),
             body_html: serialize(), summary: summary, images: usedImages() };
  }
  const dlgSub = $("dlg-submit"), sm = $("sub-msg");
  function subNote(t, cls) { sm.className = "msg " + (cls || ""); sm.textContent = t; }
  $("submit-btn").onclick = () => {
    snap(); if (!checkReady()) return;
    subNote(""); $("sub-result").innerHTML = ""; refreshAuthUi(); dlgSub.showModal(); $("sub-summary").focus();
  };
  $("sub-cancel").onclick = () => dlgSub.close();
  function summaryOk() {
    const s = $("sub-summary").value.trim();
    if (s.length < 5) { subNote("A change summary is required: say what you changed and why.", "err"); $("sub-summary").focus(); return null; }
    return s;
  }
  /* sign-in: a pasted GitHub token, kept in memory only (see gh.js) */
  function refreshAuthUi() {
    const who = CescoGH.user();
    $("auth-out").hidden = !!who; $("auth-in").hidden = !who;
    if (who) $("auth-who").textContent = who;
  }
  $("tok-ok").onclick = async () => {
    subNote("Checking token…");
    try { await CescoGH.signIn($("tok-input").value); $("tok-input").value = ""; subNote(""); refreshAuthUi(); }
    catch (e) { subNote(e.message, "err"); }
  };
  $("tok-out").onclick = () => { CescoGH.signOut(); refreshAuthUi(); };
  $("sub-ok").onclick = async () => {
    const s = summaryOk(); if (!s) return;
    if (!CescoGH.user()) { subNote("Sign in first (paste a GitHub token above), or use “Download proposal files” below.", "err"); return; }
    $("sub-ok").disabled = true;
    try {
      const r = await CescoGH.submit(proposal(s), CescoImages.pending, subNote);
      dirty = false; subNote("");
      $("sub-result").innerHTML = '<div class="notice ok"><strong>Submitted for approval.</strong> Nothing on the live site has changed. A pull request was opened' +
        (r.forked ? " from your fork" : "") + ': <a href="' + esc(r.url) + '" target="_blank" rel="noopener">' + esc(r.url) + "</a>. It goes live only when the owner merges it.</div>";
      note("Submitted: pull request #" + r.number + ".", "ok");
    } catch (e) { subNote(e.message || String(e), "err"); }
    $("sub-ok").disabled = false;
  };
  $("sub-download").onclick = () => {
    const s = summaryOk(); if (!s) return;
    CescoGH.download(proposal(s), CescoImages.pending);
    dirty = false;
    $("sub-result").innerHTML = '<div class="notice info">Files downloaded. Now open <a href="' + esc(CescoGH.uploadUrl()) + '" target="_blank" rel="noopener">the GitHub upload page</a> and drag ALL the downloaded files onto it, then choose “Create a new branch and start a pull request”. (GitHub forks the repository for you if you are not the owner.) Nothing is live until the owner merges the pull request.</div>';
  };
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  window.__cescoEditor = { serialize, load, undo, redo };   // used by the automated tests
};
