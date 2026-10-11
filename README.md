# Cescopedia

Public, open knowledge base for CESCO truck-mounting information. Live: https://methgamage.github.io/cescopedia/
Everything here is public plain HTML. There is no password and no encryption.

## How editing works (all inside GitHub, no server)
1. **Edit**: every article page has "Edit this article" → `/edit/?article=<slug>` (a static page, rich-text editor bundled in `edit/`).
   It loads the current text from `content/`, lets you edit text, tables, links and pictures (with captions + alt text; pictures are resized
   and compressed in your browser) and requires a change summary.
2. **Sign in**: paste a GitHub personal access token (kept in page memory only; see below why not OAuth). 
3. **Submit for approval**: opens a **pull request** (branch `proposals/<article>-<timestamp>`) containing `proposals/<id>/proposal.json`,
   `body.html` and `uploads/`. The live site does not change.
4. **Approve = the owner merges the pull request** on GitHub. Nobody else can merge (see "Enforcement").
5. **After the merge** `.github/workflows/apply-proposals.yml` runs `tools/apply_proposals.py`: archives the previous version in
   `content/versions/<article>/vNNN/` (date + approver = the merger), writes the change-log entry (summary + automatic diff counts), rebuilds
   all pages / archive pages / history / `changelog.html` / homepage "Last edits" with `tools/build_site.py`, and commits to `main` with `GITHUB_TOKEN`.
6. **Grok** proposes through `tools/cescoedit.py` (pull request labelled `grok`); it can never merge. See `GROK-USAGE.md`.

## Layout
    *.html, assets/, favicon.svg   generated site (served by Pages from main, root)
    edit/                           static editor (index.html, editor.js, images.js, gh.js, start.js, editor.css)
    content/                        content store: articles/<slug>/{article.json,body.html}, versions/, changelog*.json, site.json, home-template.html
    proposals/                      pending proposals live on PR branches only; merged ones are consumed by the workflow
    tools/                          build_site.py, apply_proposals.py, cescoedit.py, make_zip.py, lib/, tests
    .github/workflows/              apply-proposals.yml (runs on push to main only, never on a PR)

## Rebuild locally
    python3 tools/build_site.py      # needs only the Python standard library (Pillow for apply_proposals / cescoedit images)

## Secrets
None are stored here. The editor never persists a token. The old admin passphrase / Grok token files of the legacy local server are not in this repo.

## Why a pasted token and not "Sign in with GitHub" (OAuth)
* OAuth **device flow**: `https://github.com/login/device/code` and `/login/oauth/access_token` return no CORS headers (verified: OPTIONS → 404, no
  `Access-Control-Allow-Origin`), so a browser page cannot call them.
* OAuth **web flow** needs a client secret on a server. Not available on static hosting.
* `api.github.com` does allow cross-origin calls with a bearer token, so a user-supplied token works with no server.
