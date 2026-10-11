/* GitHub side of the editor: sign-in with a pasted token (memory only) and "submit for approval" = open a pull request.
   Why a pasted token: GitHub's OAuth device flow endpoints (github.com/login/device/code) send no CORS headers, so a static
   page cannot call them, and the web OAuth flow needs a client secret (= a server). api.github.com DOES allow browser calls,
   so a user-supplied token works. The token lives only in this closure: never stored, never logged, never sent anywhere
   except api.github.com. */
window.CescoGH = (function () {
  const REPO = "methgamage/cescopedia", API = "https://api.github.com";
  let token = null, login = null;

  async function api(method, path, body, tok) {
    const r = await fetch(API + path, {
      method, headers: Object.assign({ "Authorization": "Bearer " + (tok || token), "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" },
        body ? { "Content-Type": "application/json" } : {}),
      body: body ? JSON.stringify(body) : undefined });
    let data = null; try { data = await r.json(); } catch (e) {}
    if (!r.ok) { const e = new Error((data && data.message) || ("GitHub error " + r.status)); e.status = r.status; throw e; }
    return data;
  }
  async function signIn(t) {
    t = (t || "").trim();
    if (!t) throw new Error("Paste a GitHub token first.");
    let u;
    try { u = await api("GET", "/user", null, t); }
    catch (e) { throw new Error(e.status === 401 ? "GitHub rejected that token." : e.message); }
    token = t; login = u.login; return login;
  }
  function signOut() { token = null; login = null; }
  const b64 = async (blob) => {
    const buf = new Uint8Array(await blob.arrayBuffer()); let s = "";
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return btoa(s);
  };
  const utf8b64 = (str) => { const u = new TextEncoder().encode(str); let s = ""; u.forEach((c) => (s += String.fromCharCode(c))); return btoa(s); };
  const pad = (n) => String(n).padStart(2, "0");
  function stamp() { const d = new Date(); return d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) + "-" + pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds()); }
  function files(p, id, imgs) {
    const meta = { format: 1, article: p.article, base_version: p.base_version, title: p.title, dek: p.dek, description: p.description,
                   summary: p.summary, proposer: login || "anonymous", author_type: "human", created_at: new Date().toISOString(), images: p.images };
    const out = [{ path: "proposals/" + id + "/proposal.json", text: JSON.stringify(meta, null, 2) + "\n" },
                 { path: "proposals/" + id + "/body.html", text: p.body_html + "\n" }];
    p.images.forEach((n) => out.push({ path: "proposals/" + id + "/uploads/" + n, blob: imgs[n] }));
    return out;
  }
  async function submit(p, imgs, progress) {
    if (!token) throw new Error("Not signed in.");
    progress = progress || (() => {});
    const id = p.article + "-" + stamp(), branch = "proposals/" + id;
    progress("Checking access…");
    const repo = await api("GET", "/repos/" + REPO);
    let target = REPO, forked = false;
    if (!(repo.permissions && repo.permissions.push)) {            // not the owner: use a fork
      progress("You cannot push to " + REPO + ", so a fork is used (this needs a token that may create forks)…");
      let f = await api("POST", "/repos/" + REPO + "/forks", { default_branch_only: true });
      target = f.full_name; forked = true;
      for (let i = 0; i < 30; i++) { try { await api("GET", "/repos/" + target + "/branches/" + repo.default_branch); break; } catch (e) { await new Promise((r) => setTimeout(r, 2000)); } }
    }
    progress("Reading the latest version…");
    const base = await api("GET", "/repos/" + REPO + "/git/ref/heads/" + repo.default_branch);
    const baseSha = base.object.sha;
    const baseCommit = await api("GET", "/repos/" + target + "/git/commits/" + baseSha).catch(() => null);
    if (!baseCommit) throw new Error("Your fork is not up to date with " + REPO + " yet. Wait a minute or sync it, then submit again.");
    const tree = [];
    for (const f of files(p, id, imgs)) {
      progress("Uploading " + f.path.split("/").pop() + "…");
      const blob = await api("POST", "/repos/" + target + "/git/blobs", f.blob ? { content: await b64(f.blob), encoding: "base64" } : { content: f.text, encoding: "utf-8" });
      tree.push({ path: f.path, mode: "100644", type: "blob", sha: blob.sha });
    }
    const t = await api("POST", "/repos/" + target + "/git/trees", { base_tree: baseCommit.tree.sha, tree });
    const c = await api("POST", "/repos/" + target + "/git/commits", { message: "Proposal: " + p.article + " — " + p.summary.split("\n")[0].slice(0, 100), tree: t.sha, parents: [baseSha] });
    await api("POST", "/repos/" + target + "/git/refs", { ref: "refs/heads/" + branch, sha: c.sha });
    progress("Opening the pull request…");
    const body = "**Article:** `" + p.article + "` (based on live v" + p.base_version + ")\n**Proposed by:** @" + login + " (human, via the web editor)\n\n## Change summary\n\n" + p.summary +
      "\n\n---\nFiles: `proposals/" + id + "/` (`body.html` is the proposed article body; `uploads/` are new pictures).\n" +
      "**Merging this pull request approves the change.** After the merge a workflow archives the old version, updates the change log and publishes. Closing it discards the proposal. Nothing on the live site changes before the merge.";
    const pr = await api("POST", "/repos/" + REPO + "/pulls", { title: "Edit " + p.article + ": " + p.summary.split("\n")[0].slice(0, 80), head: forked ? login + ":" + branch : branch,
      base: repo.default_branch, body, maintainer_can_modify: true });
    return { url: pr.html_url, number: pr.number, forked };
  }
  function saveBlob(name, blob) { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); }
  let lastId = null;
  function download(p, imgs) {
    lastId = p.article + "-" + stamp();
    files(p, lastId, imgs).forEach((f, i) => setTimeout(() => saveBlob(f.path.split("/").pop(), f.blob || new Blob([f.text], { type: "text/plain" })), i * 400));
  }
  const uploadUrl = () => "https://github.com/" + REPO + "/upload/main/proposals/" + (lastId || "");
  return { signIn, signOut, user: () => login, submit, download, uploadUrl, files, repo: REPO };
})();
