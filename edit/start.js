/* Loads the article's CURRENT content from the site itself (content/articles/<slug>/…), then starts the editor. */
(async function () {
  const $ = (id) => document.getElementById(id);
  const slug = new URLSearchParams(location.search).get("article") || "";
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const get = async (p, json) => { const r = await fetch(p + "?t=" + Date.now(), { cache: "no-store" }); if (!r.ok) throw new Error(p + " → " + r.status); return json ? r.json() : r.text(); };
  try {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(slug)) {
      const site = await get("content/site.json", true);
      const li = [];
      for (const s of site.order) { try { const a = await get("content/articles/" + s + "/article.json", true); li.push('<li><a href="edit/?article=' + s + '">' + esc(a.title) + "</a></li>"); } catch (e) {} }
      $("pick-list").innerHTML = li.join(""); $("ed-load").hidden = true; $("ed-pick").hidden = false; return;
    }
    const [a, body] = await Promise.all([get("content/articles/" + slug + "/article.json", true), get("content/articles/" + slug + "/body.html")]);
    document.title = "Edit: " + a.title + " — Cescopedia";
    $("ed-h1").textContent = "Edit: " + a.title;
    $("back-link").href = slug + ".html"; $("back-link").textContent = "← " + a.title;
    $("f-title").value = a.title; $("f-dek").value = a.dek || ""; $("f-desc").value = a.description || "";
    const appr = a.approval;
    $("ed-status").innerHTML = '<span class="badge ' + (appr ? "ok" : "warn") + '">Live v' + a.version + (appr ? " — approved by " + esc(appr.approved_by) : " — seed version") + "</span> " +
      '<a class="muted" href="' + slug + '.html">view live page</a>';
    $("ed-load").hidden = true; $("ed-body").hidden = false;
    window.cescoStartEditor({ slug: slug, version: a.version, title: a.title, dek: a.dek || "", description: a.description || "", body_html: body });
    // open proposals for this article (public API, no token; best effort)
    fetch("https://api.github.com/repos/" + CescoGH.repo + "/pulls?state=open&per_page=50").then((r) => r.ok ? r.json() : []).then((prs) => {
      const mine = prs.filter((p) => p.title.indexOf("Edit " + slug + ":") === 0 || (p.head && p.head.ref.indexOf("proposals/" + slug + "-") === 0));
      if (mine.length) $("ed-pending").innerHTML = '<div class="notice warn"><strong>' + mine.length + " open proposal" + (mine.length > 1 ? "s" : "") + " for this article</strong> (not live yet). If one is merged first, yours will need to be redone on the new version.<ul>" +
        mine.map((p) => '<li><a href="' + esc(p.html_url) + '" target="_blank" rel="noopener">#' + p.number + " " + esc(p.title) + "</a></li>").join("") + "</ul></div>";
    }).catch(() => {});
  } catch (e) {
    $("ed-load").className = "notice bad"; $("ed-load").textContent = "Could not load the article: " + e.message;
  }
})();
