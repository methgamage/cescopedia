"""Headless-Chrome test of the static editor with a MOCKED api.github.com (no real GitHub calls).
Run: python3 test_editor_browser.py [site_url]   (needs websocket-client and Pillow)"""
import sys, json, time, os
sys.path.insert(0, os.environ.get("CDP_DIR", "/workspace/cesco-pedia-admin/tests"))
from cdp import Chrome
from PIL import Image
import random
base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8790").rstrip("/")
im = Image.new("RGB", (3200, 2000)); px = im.load()
for x in range(0, 3200, 7):
    for y in range(0, 2000, 7): px[x, y] = (random.randint(0, 255), x % 255, y % 255)
im.save("/tmp/big-test.jpg", quality=95)
c = Chrome(9341, (1300, 1000)); ok = True
def check(name, cond, extra=""):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name, extra)
try:
    c.goto(base + "/edit/?article=mudguards", wait=1.5)
    check("editor loads article", c.js("document.getElementById('editor').innerText.length") > 100, c.js("document.getElementById('ed-h1').textContent"))
    c.js("""window.__calls=[];const real=window.fetch;window.fetch=async function(u,o){u=String(u);if(!u.startsWith('https://api.github.com')) return real(u,o);
      const m=(o&&o.method)||'GET',b=o&&o.body?JSON.parse(o.body):null;window.__calls.push([m,u.replace('https://api.github.com',''),b]);
      const J=(d,s)=>new Response(JSON.stringify(d),{status:s||200});
      if(u.endsWith('/user'))return J({login:'tester'});
      if(u.endsWith('/repos/methgamage/cescopedia'))return J({default_branch:'main',permissions:{push:true}});
      if(u.includes('/git/ref/heads/main'))return J({object:{sha:'b'.repeat(40)}});
      if(u.includes('/git/commits/')&&m=='GET')return J({tree:{sha:'t'.repeat(40)}});
      if(u.endsWith('/git/blobs'))return J({sha:'blob'+window.__calls.length});
      if(u.endsWith('/git/trees'))return J({sha:'tree1'});
      if(u.endsWith('/git/commits'))return J({sha:'c'.repeat(40)});
      if(u.endsWith('/git/refs'))return J({});
      if(u.endsWith('/pulls')&&m=='POST')return J({html_url:'https://github.com/methgamage/cescopedia/pull/999',number:999});
      return J({},404)};true""")
    # edit text
    c.js("document.getElementById('editor').insertAdjacentHTML('afterbegin','<p>TEST PARAGRAPH from the browser test.</p>');document.getElementById('editor').dispatchEvent(new Event('input'));true")
    # picture
    c.js("document.getElementById('tb-figure').click();true"); time.sleep(0.3)
    c.set_files("#fig-file", ["/tmp/big-test.jpg"]); time.sleep(2)
    msg = c.js("document.getElementById('fig-msg').textContent"); print("  ", msg)
    check("picture resized", "1600×1000" in msg, msg)
    c.js("document.getElementById('fig-caption').value='Test caption';document.getElementById('fig-caption').dispatchEvent(new Event('input'));document.getElementById('fig-alt').value='Test alt';document.getElementById('fig-insert').click();true"); time.sleep(0.4)
    check("figure in editor", c.js("!!document.querySelector('#editor figure img[data-src^=\"assets/uploads/\"]')"))
    c.js("document.getElementById('submit-btn').click();true"); time.sleep(0.3)
    c.js("document.getElementById('sub-ok').click();true"); time.sleep(0.3)
    check("submit blocked without summary", c.js("document.getElementById('sub-msg').textContent").startswith("A change summary"))
    c.js("document.getElementById('sub-summary').value='Browser test summary';document.getElementById('sub-ok').click();true"); time.sleep(0.3)
    check("submit blocked when signed out", "Sign in" in c.js("document.getElementById('sub-msg').textContent"))
    c.js("document.getElementById('tok-input').value='github_pat_FAKE';document.getElementById('tok-ok').click();true"); time.sleep(0.5)
    check("signed in (memory only)", c.js("document.getElementById('auth-who').textContent")=="tester" and c.js("document.getElementById('tok-input').value")=="" )
    check("token not persisted", c.js("localStorage.length+sessionStorage.length+document.cookie.length")==0)
    c.js("document.getElementById('sub-ok').click();true"); time.sleep(1.5)
    res = c.js("document.getElementById('sub-result').innerText")
    check("PR result shown", "pull/999" in res, res[:80])
    calls = c.js("JSON.stringify(window.__calls)"); calls = json.loads(calls)
    refs = [x for x in calls if x[1].endswith("/git/refs")]
    check("branch proposals/mudguards-<ts>", refs and refs[0][2]["ref"].startswith("refs/heads/proposals/mudguards-2"), refs[0][2]["ref"] if refs else "")
    tree = [x for x in calls if x[1].endswith("/git/trees")][0][2]["tree"]
    paths = [t["path"] for t in tree]; print("  tree:", paths)
    check("tree has proposal.json, body.html, one upload", len(paths)==3 and any(p.endswith("/uploads/"+p.split("/")[-1]) for p in paths))
    blobs = [x[2] for x in calls if x[1].endswith("/git/blobs")]
    body = [b for b in blobs if b["encoding"]=="utf-8" and "TEST PARAGRAPH" in b["content"]]
    check("body.html has edit and plain src (no blob: urls)", body and "blob:" not in body[0]["content"] and 'src="assets/uploads/' in body[0]["content"] and "Test caption" in body[0]["content"])
    meta = json.loads([b for b in blobs if b["encoding"]=="utf-8" and '"format"' in b["content"]][0]["content"]); print("  meta:", {k: meta[k] for k in ("article","base_version","summary","proposer","author_type")})
    check("meta ok", meta["summary"]=="Browser test summary" and meta["proposer"]=="tester" and meta["images"])
    c.goto(base + "/edit/", wait=1.2); check("picker lists articles", c.js("document.querySelectorAll('#pick-list a').length")>=10)
    c.goto(base + "/edit/?article=mudguards", wait=1.2); c.shot("/workspace/cescopedia-shots/_editor-local.png", full=False)
finally:
    c.close()
sys.exit(0 if ok else 1)
