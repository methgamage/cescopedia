# Grok usage: proposing Cescopedia edits (GitHub-native)

You (Grok) can **propose** edits. You can never approve, reject, merge or publish them. A proposal is a **pull request** on
`methgamage/cescopedia`; the repository owner (Meth) approves it by **merging** it on GitHub. Nothing you submit changes the live site.

## Rules
1. **Never invent data.** Use only the sources you were given (documents, drawings, Emmanuel's text) or what the user told you in
   this conversation. If a number, part code, torque, dimension or ECO is not in a source, do not write it.
2. **Never approve or merge.** `cescoedit.py` has no such command. Do not run `gh pr merge`, `gh pr review --approve`, push to `main`,
   or edit anything outside a proposal. Every edit needs a human merge.
3. **Always give a change summary** (`--summary`): what changed, why, and which source. A human reads it when approving, and it goes
   into the public change log.
4. **Ask when in doubt.** Unclear instruction, conflicting sources, or an open proposal on the same article: ask the user first.
5. Make the **smallest change** that does the job. Keep existing text, figures and captions unless told to change them.
6. Every picture needs a **caption** (required) and alt text.
7. The tool does not write content for you: `--instruction` alone is refused. You produce the new text yourself, then pass it as below.

## Commands
Run from the repo clone (`/workspace/cescopedia-repo/tools/`, also reachable as `python3 /workspace/cesco-pedia-admin/cescoedit.py ...`).
It uses the already-logged-in `gh` CLI; never print or copy a token. It fast-forwards the local clone first so "live" is current.

    cescoedit.py list                                   # articles: live version, approved or not, open proposals
    cescoedit.py show --article SLUG [--field body|title|dek|description|json] [--out file]
    cescoedit.py proposals                              # open proposal pull requests
    cescoedit.py status --pr NUMBER                     # OPEN = waiting; MERGED = approved and published; CLOSED = rejected
    cescoedit.py diff --article SLUG --patch-file p.json    # preview only, nothing submitted (same flags as propose)
    cescoedit.py propose --article SLUG --summary "..." [--instruction "user's request"] <content options>

Content options (combine as needed):
* `--content-file new.html` (whole new body) or `new.json` (keys `title`, `dek`, `description`, `body_html`). Start from `show --out`.
* `--patch-file patch.json`: a JSON list of operations on the live content, for example
  `[{"op":"replace_text","find":"old exact text","replace":"new text"},
    {"op":"append_html","html":"<p>...</p>"},
    {"op":"insert_after_heading","heading":"Mudguard types","html":"<p>...</p>"},
    {"op":"insert_before_heading","heading":"Related","html":"<p>...</p>"},
    {"op":"delete_block_containing","text":"exact words in the paragraph"},
    {"op":"set_title","value":"..."}, {"op":"set_dek","value":"..."}]`
  `find` must match exactly once (or set `"all": true`); otherwise the command fails and nothing is submitted.
* `--title "..."`, `--dek "..."`.
* `--figure /path/pic.jpg --caption "..." --alt "..." [--after-heading "Heading text"]` adds a picture (resized and compressed; it
  becomes public only when the PR is merged). Without `--after-heading` it goes at the end.
* `--dry-run` prints the diff and submits nothing.

Allowed body HTML: p, h2, h3, ul/ol/li, table, strong/em/u, a, br, figure/img/figcaption and the existing callout classes.
Scripts, styles and event handlers are stripped again by the workflow when the proposal is applied.

## What `propose` does
Creates branch `proposals/<article>-<UTC timestamp>` containing `proposals/<article>-<timestamp>/{proposal.json, body.html, uploads/*}`,
opens a pull request into `main` with your summary, and labels it **`grok`**. That is all. It never touches `main`.

## After submitting
Tell the user the PR number and URL and that it is **waiting for human approval (Meth merging it)**. Do not say it is live.
If the live article changes before the merge, the workflow refuses the stale proposal (moves it to `proposals/_conflict/` and comments on
the PR). Then re-read with `show` and re-propose if asked.
