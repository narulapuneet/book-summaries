#!/usr/bin/env python3
"""
Book Library — local control panel.

Run it in your book-summaries folder:

    export ANTHROPIC_API_KEY="sk-ant-..."     # your key
    python3 admin.py

Then a browser opens at http://localhost:8000. Enter a title + author (and an
optional YouTube URL), click Generate, review, Save, and Publish.

Zero pip installs — standard library only. Uses git + make_qrs.py already in the folder.
Run this LOCALLY only; it can write files and push to your repo.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- config ----
PORT = 8000
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")  # change if you use another
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BOOKS = "books.json"
PALETTE = ["#e0762f", "#4c9f70", "#3f7a6d", "#c0563f", "#5a6fb0",
           "#b8863b", "#7a5aa8", "#2f8f9e", "#a84a6f", "#57883f"]


# ---------- helpers ----------
def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "book"


def load_books():
    if not os.path.exists(BOOKS):
        return []
    with open(BOOKS, encoding="utf-8") as f:
        return json.load(f)


def pick_accent(books, wanted=""):
    if wanted:
        return wanted
    used = {b.get("accent") for b in books}
    for c in PALETTE:
        if c not in used:
            return c
    return PALETTE[len(books) % len(PALETTE)]


def upsert_book(book):
    """Replace an existing book in place (preserve order), else insert before 'template'."""
    books = load_books()
    idx = next((i for i, b in enumerate(books) if b["slug"] == book["slug"]), None)
    if idx is not None:
        books[idx] = book
    else:
        at = next((i for i, b in enumerate(books) if b["slug"] == "template"), len(books))
        books.insert(at, book)
    with open(BOOKS, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return books


def find_existing(books, title="", slug=""):
    """Find a book by matching slug OR (case-insensitive) title."""
    t = (title or "").strip().lower()
    for b in books:
        if slug and b.get("slug") == slug:
            return b
        if t and b.get("title", "").strip().lower() == t:
            return b
    return None


SYSTEM = """You produce book-summary data for a personal library.
Output ONLY one JSON object (no markdown fences, no commentary) with this schema:
{
 "slug": string, "title": string, "author": string,
 "subtitle": one-line hook (max ~60 chars),
 "accent": hex color, "video": "",
 "chapters": [
   {"num":"01","title": string,"tag": short label or "",
    "items": ["<b>Verb</b> takeaway", ...],
    "mantra": {"label": string, "text": string}   // OPTIONAL, only when justified
   }
 ]
}
Rules:
- 5 to 6 sections that follow the book's real structure or framework, in order (num "01","02",...).
- Every item starts with a bold imperative verb wrapped in <b></b>, then a specific, actionable takeaway. No fluff, no filler, no hedging.
- 5-6 items per section.
- Include a "mantra" only when the book has a signature principle worth boxing, and paraphrase it — never quote the book verbatim.
- Paraphrase everything into actions; do not reproduce sentences from the book.
Return only the JSON object."""


def generate(title, author, slug, accent, video):
    if not API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in your environment.")
    user = (f"Book: {title}\nAuthor: {author}\n"
            f"Use slug \"{slug}\", accent \"{accent}\", video \"{video}\". "
            f"Generate the summary JSON now.")
    payload = {
        "model": MODEL,
        "max_tokens": 3000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(f"Anthropic API {e.code}: {detail}")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    book = json.loads(text)
    # force server-controlled fields
    book["slug"], book["accent"], book["video"] = slug, accent, video
    book["title"], book["author"] = title, author
    return book


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return (p.stdout + p.stderr).strip()


# ---------- youtube search (no API key; parses public results) ----------
def _balanced_json(s, start):
    depth = 0
    in_str = esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
    return None


def youtube_search(title, author, limit=5):
    q = " ".join(x for x in [title, author, "book summary"] if x).strip()
    url = ("https://www.youtube.com/results?search_query="
           + urllib.parse.quote(q) + "&sp=EgIQAQ%253D%253D")  # &sp=... => videos only
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")

    marker = "ytInitialData = "
    idx = html.find(marker)
    if idx == -1:
        idx = html.find('ytInitialData"] = ')
    if idx == -1:
        return []
    raw = _balanced_json(html, html.find("{", idx))
    if not raw:
        return []
    data = json.loads(raw)

    try:
        sections = (data["contents"]["twoColumnSearchResultsRenderer"]
                    ["primaryContents"]["sectionListRenderer"]["contents"])
    except (KeyError, TypeError):
        return []

    vids = []
    for sec in sections:
        for it in sec.get("itemSectionRenderer", {}).get("contents", []):
            vr = it.get("videoRenderer")
            if not vr or not vr.get("videoId"):
                continue
            vid = vr["videoId"]
            truns = vr.get("title", {}).get("runs", [{}])
            oruns = vr.get("ownerText", {}).get("runs", [{}])
            vids.append({
                "id": vid,
                "title": (truns[0].get("text", "") if truns else ""),
                "channel": (oruns[0].get("text", "") if oruns else ""),
                "length": vr.get("lengthText", {}).get("simpleText", ""),
                "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
            if len(vids) >= limit:
                return vids
    return vids


def gen_qr_for(book):
    """Generate QR + label for ONE book only; existing files untouched."""
    import importlib
    mk = importlib.import_module("make_qrs")
    importlib.reload(mk)  # pick up any BASE_URL change
    return mk.make_one(book)


def publish():
    log = []
    log.append(run(["git", "add", "-A"]))
    log.append(run(["git", "commit", "-m", "update book summaries"]))
    log.append(run(["git", "push"]))
    return "\n".join(x for x in log if x)


# ---------- web ----------
PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Library control panel</title>
<style>
 *{box-sizing:border-box;margin:0;padding:0}
 body{font-family:system-ui,-apple-system,sans-serif;background:#12203a;color:#f2ede3;
   min-height:100vh;padding:32px 16px}
 .panel{max-width:720px;margin:0 auto;background:#f7f4ee;color:#12203a;border-radius:18px;
   padding:28px;box-shadow:0 24px 60px rgba(0,0,0,.35)}
 h1{font-size:1.4rem;margin-bottom:2px}
 p.sub{color:#54617a;font-size:.9rem;margin-bottom:22px}
 label{display:block;font-size:.72rem;font-weight:600;text-transform:uppercase;
   letter-spacing:.08em;color:#54617a;margin:14px 0 5px}
 input{width:100%;padding:11px 13px;font-size:1rem;border:2px solid #d6cfc2;border-radius:10px;
   background:#fff;color:#12203a}
 input:focus{outline:none;border-color:#e0762f}
 .row{display:flex;gap:12px}.row>div{flex:1}
 button{padding:12px 18px;font-size:.95rem;font-weight:600;border:none;border-radius:10px;
   cursor:pointer;margin-top:18px}
 .primary{background:#e0762f;color:#fff}.primary:hover{background:#c9651f}
 .ghost{background:#12203a;color:#fff}.ghost:hover{background:#22375f}
 .ghost[disabled],.primary[disabled]{opacity:.5;cursor:not-allowed}
 .openbtn{display:inline-block;text-decoration:none;padding:12px 18px;margin-top:18px;
   border-radius:10px;background:#4c9f70;color:#fff;font-weight:600;font-size:.95rem}
 .openbtn:hover{background:#3f8a5f}
 .bar{display:flex;gap:10px;flex-wrap:wrap}
 pre{background:#12203a;color:#e8eef7;padding:14px;border-radius:10px;font-size:.8rem;
   overflow:auto;max-height:300px;margin-top:16px;white-space:pre-wrap;word-break:break-word}
 .note{font-size:.82rem;color:#54617a;margin-top:8px}
 .status{margin-top:14px;font-size:.9rem;font-weight:600}
 .ok{color:#2f7d4f}.err{color:#c0392b}
 .warn{color:#b5702a}
 .paste-box.disabled{opacity:.45}
 .vidbar{align-items:center;margin-top:18px}
 .vidbar button{margin-top:0}
 .vidbar .status{margin-top:0}
 textarea{width:100%;min-height:220px;margin-top:16px;padding:12px;border-radius:10px;
   border:2px solid #d6cfc2;font-family:ui-monospace,Menlo,monospace;font-size:.8rem}
 #videos{margin-top:6px}
 .vid{display:flex;gap:10px;align-items:center;padding:8px;border:2px solid #d6cfc2;
   border-radius:10px;margin-top:8px;cursor:pointer;background:#fff}
 .vid:hover{border-color:#e0762f}
 .vid.sel{border-color:#e0762f;background:#fdf3ea}
 .vid img{width:104px;height:59px;object-fit:cover;border-radius:6px;flex:none;background:#e9e5dd}
 .vid input{width:18px;height:18px;flex:none;accent-color:#e0762f}
 .vmeta{display:flex;flex-direction:column;min-width:0}
 .vt{font-weight:600;font-size:.9rem;line-height:1.25;overflow:hidden;
   display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
 .vc{font-size:.78rem;color:#54617a;margin-top:2px}
 .paste-box{border-top:1px solid #e2dccf;margin-top:22px;padding-top:6px}
</style></head><body>
<div class="panel">
  <h1>Library control panel</h1>
  <p class="sub">Generate a summary, save it, publish it. Model: __MODEL__</p>

  <label>Book title</label>
  <input id="title" placeholder="Deep Work">
  <label>Author</label>
  <input id="author" placeholder="Cal Newport">
  <div class="status" id="existsmsg"></div>

  <label>YouTube summary URL (optional)</label>
  <input id="video" placeholder="https://youtu.be/… — or search below">
  <div class="bar vidbar">
    <button class="ghost" id="findvid" onclick="findVideos()">Find summary videos</button>
    <span class="status" id="vidstatus"></span>
  </div>
  <div id="videos"></div>

  <div class="bar">
    <button class="primary" id="gen" onclick="gen()">Generate summary</button>
  </div>
  <div class="status" id="keystatus"></div>
  <div class="status" id="status"></div>

  <div class="paste-box" id="pasteBox">
    <label>Or paste a summary (no API key needed)</label>
    <textarea id="paste" style="min-height:150px" placeholder="Paste takeaways here. Section headings on their own line (# Heading, **Heading**, or ending with a colon); points as - bullets. The first word of each point is bolded automatically."></textarea>
    <div class="bar">
      <button class="ghost" id="build" onclick="buildFromPaste()">Build book from pasted text</button>
    </div>
  </div>

  <textarea id="json" placeholder="Book JSON appears here — generated or built from your paste. Edit before saving."></textarea>

  <div class="bar">
    <button class="ghost" id="save" onclick="save()" disabled>Save + make QR for this book</button>
    <a class="openbtn" id="openlabel" target="_blank" rel="noopener" style="display:none">Open QR label ↗</a>
    <button class="ghost" id="pub" onclick="pub()" disabled>Publish to GitHub</button>
  </div>
  <p class="note">Save writes this book to <code>books.json</code> and creates a new <code>qr/&lt;slug&gt;.svg</code> + <code>qr/&lt;slug&gt;-label.html</code> — existing books are left alone. Publish runs git add / commit / push.</p>
  <pre id="log" style="display:none"></pre>
</div>
<script>
const $=id=>document.getElementById(id);
function setStatus(t,cls){const s=$('status');s.textContent=t;s.className='status '+(cls||'');}
function showLog(t){const l=$('log');l.style.display='block';l.textContent=t;}

async function post(path,body){
  const r=await fetch(path,{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify(body||{})});
  const d=await r.json(); if(!r.ok) throw new Error(d.error||'request failed'); return d;
}
async function gen(){
  const title=$('title').value.trim(), author=$('author').value.trim();
  if(!title||!author){setStatus('Enter a title and author first.','err');return;}
  setStatus(bookExists?'Regenerating…':'Generating…'); $('gen').disabled=true;
  try{
    const d=await post('/generate',{title,author,video:$('video').value.trim()});
    $('json').value=JSON.stringify(d.book,null,2);
    setStatus('Draft ready — review and edit, then Save.','ok');
    $('save').disabled=false; $('pub').disabled=true;
  }catch(e){setStatus('Error: '+e.message,'err');}
  $('gen').disabled=false;
}
async function save(){
  let book; try{book=JSON.parse($('json').value);}catch(e){setStatus('JSON is invalid: '+e.message,'err');return;}
  setStatus('Saving + making QR…'); $('save').disabled=true;
  try{
    const d=await post('/save',{book});
    const labelUrl='/'+d.label;                       // e.g. /qr/deep-work-label.html
    const a=$('openlabel'); a.href=labelUrl; a.style.display='inline-block';
    showLog(d.log); $('pub').disabled=false;
    checkExists();                                    // now exists -> flips to Regenerate
    const w=window.open(labelUrl,'_blank');           // pop the label to print
    if(w){ setStatus('Saved "'+book.slug+'". Label opened in a new window.','ok'); }
    else { setStatus('Saved "'+book.slug+'". Popup blocked — click "Open QR label ↗".','ok'); }
  }catch(e){setStatus('Error: '+e.message,'err');}
  $('save').disabled=false;
}
async function pub(){
  setStatus('Publishing…'); $('pub').disabled=true;
  try{const d=await post('/publish',{}); setStatus('Published. Live in ~1 min.','ok'); showLog(d.log);}
  catch(e){setStatus('Error: '+e.message,'err');}
  $('pub').disabled=false;
}

/* ---- API-key gating (change 2) ---- */
const HAS_KEY = __HAS_KEY__;
let bookExists = false;
function setPasteEnabled(on){
  $('paste').disabled=!on; $('build').disabled=!on;
  $('pasteBox').classList.toggle('disabled', !on);
}
function applyGenLabel(){
  $('gen').textContent = bookExists ? 'Regenerate summary' : 'Generate summary';
}
async function checkExists(){
  const title=$('title').value.trim();
  if(!title){ bookExists=false; $('existsmsg').textContent=''; applyGenLabel(); return; }
  try{
    const d=await post('/exists',{title});
    bookExists = !!d.exists;
    if(bookExists){
      $('existsmsg').textContent='Summary already exists — saving will overwrite it and its QR.';
      $('existsmsg').className='status warn';
    }else{
      $('existsmsg').textContent=''; $('existsmsg').className='status';
    }
    applyGenLabel();
  }catch(e){ /* ignore check failures */ }
}
let _existsTimer=null;
function scheduleExistsCheck(){ clearTimeout(_existsTimer); _existsTimer=setTimeout(checkExists,350); }

window.addEventListener('DOMContentLoaded',()=>{
  const ks=$('keystatus');
  if(HAS_KEY){
    ks.textContent='Anthropic API Key available'; ks.className='status ok';
    $('gen').disabled=false;
    setPasteEnabled(false);   // key present -> generate; paste disabled
    $('paste').placeholder='Paste is disabled — API key found, use Generate summary.';
  }else{
    ks.textContent='Anthropic API Key not set'; ks.className='status warn';
    $('gen').disabled=true;   // greyed via [disabled] style
    $('gen').title='Set ANTHROPIC_API_KEY and restart to enable';
    setPasteEnabled(true);    // no key -> paste a summary instead
  }
  $('title').addEventListener('input', scheduleExistsCheck);
  $('title').addEventListener('blur', checkExists);
});

/* ---- YouTube search + single-select (change 1) ---- */
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function setVid(t,cls){const s=$('vidstatus');s.textContent=t;s.className='status '+(cls||'');}
async function findVideos(){
  const title=$('title').value.trim(), author=$('author').value.trim();
  if(!title){setVid('Enter a title first.','err');return;}
  setVid('Searching YouTube…'); $('findvid').disabled=true;
  try{
    const d=await post('/youtube',{title,author});
    renderVideos(d.videos||[]);
    const n=(d.videos||[]).length;
    setVid(n?('Found '+n+' — Select only ONE.'):'No videos found — paste a URL instead.', n?'ok':'err');
  }catch(e){setVid('Video search failed: '+e.message,'err');}
  $('findvid').disabled=false;
}
function renderVideos(vids){
  const box=$('videos');
  box.innerHTML=vids.map(v=>`
    <label class="vid">
      <input type="checkbox" class="vsel" data-url="${esc(v.url)}" onchange="pickVideo(this)">
      <img loading="lazy" src="${esc(v.thumb)}" alt="">
      <span class="vmeta">
        <span class="vt">${esc(v.title)}</span>
        <span class="vc">${esc(v.channel)}${v.length?' · '+esc(v.length):''}</span>
      </span>
    </label>`).join('');
}
function pickVideo(cb){
  document.querySelectorAll('.vsel').forEach(x=>{
    if(x!==cb) x.checked=false;
    x.closest('.vid').classList.toggle('sel', x.checked);
  });
  $('video').value = cb.checked ? cb.dataset.url : '';
}

/* ---- Paste -> book JSON (change 2) ---- */
function slugify(s){return s.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'')||'book';}
function textToBook(text,title,author,video,accent){
  const lines=text.replace(/\r/g,'').split('\n');
  const chapters=[]; let cur=null, n=0;
  const isBullet=l=>/^\s*([-*•]|\d+[.)])\s+/.test(l);
  const stripBullet=l=>l.replace(/^\s*([-*•]|\d+[.)])\s+/,'').trim();
  const isMarkHead=l=>{const t=l.trim();return /^#{1,6}\s+/.test(t)||/^\*\*.+\*\*$/.test(t)||/[:：]$/.test(t);};
  const cleanHead=t=>t.replace(/^#{1,6}\s+/,'').replace(/^\*\*|\*\*$/g,'').replace(/\s*[:：]$/,'').trim();
  const boldFirst=t=>/<b>/.test(t)?t:t.replace(/^(\S+)/,'<b>$1</b>');
  const newChap=t=>{n++;cur={num:String(n).padStart(2,'0'),title:t||'Summary',tag:'',items:[]};chapters.push(cur);};
  const nextNonEmpty=i=>{for(let j=i;j<lines.length;j++){if(lines[j].trim())return lines[j];}return '';};
  for(let i=0;i<lines.length;i++){
    const raw=lines[i], t=raw.trim(); if(!t) continue;
    if(isBullet(raw)){ if(!cur)newChap('Summary'); cur.items.push(boldFirst(stripBullet(raw))); continue; }
    // a plain line that is markdown-styled OR immediately followed by a bullet is a section heading
    if(isMarkHead(raw) || isBullet(nextNonEmpty(i+1))){ newChap(cleanHead(t)); }
    else { if(!cur)newChap('Summary'); cur.items.push(boldFirst(t)); }
  }
  if(!chapters.length) chapters.push({num:'01',title:'Summary',tag:'',items:[boldFirst(text.trim())]});
  return {slug:slugify(title),title,author,subtitle:'',accent:accent||'',video:video||'',chapters};
}
function buildFromPaste(){
  const title=$('title').value.trim(), author=$('author').value.trim();
  if(!title||!author){setStatus('Enter title and author first.','err');return;}
  const text=$('paste').value.trim();
  if(!text){setStatus('Paste a summary first.','err');return;}
  const book=textToBook(text,title,author,$('video').value.trim(),'');
  $('json').value=JSON.stringify(book,null,2);
  setStatus('Built from your paste — review/edit the JSON, then Save.','ok');
  $('save').disabled=false; $('pub').disabled=true;
}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _json_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index"):
            page = (PAGE.replace("__MODEL__", MODEL)
                        .replace("__HAS_KEY__", "true" if API_KEY else "false"))
            self._send(200, page, "text/html; charset=utf-8")
        elif self.path.startswith("/qr/"):
            self._serve_qr(self.path)
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def _serve_qr(self, path):
        rel = urllib.parse.unquote(path.split("?")[0]).lstrip("/")
        safe = os.path.normpath(rel)
        # only allow files inside the qr/ folder — block traversal / absolute paths
        if os.path.isabs(safe) or safe != rel or not (safe == "qr" or safe.startswith("qr" + os.sep)):
            self._send(404, json.dumps({"error": "not found"}))
            return
        if not os.path.isfile(safe):
            self._send(404, json.dumps({"error": "not found"}))
            return
        ctype = ("text/html; charset=utf-8" if safe.endswith(".html")
                 else "image/svg+xml" if safe.endswith(".svg")
                 else "application/octet-stream")
        with open(safe, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_POST(self):
        try:
            body = self._json_body()
            if self.path == "/generate":
                title, author = body["title"], body["author"]
                books = load_books()
                m = find_existing(books, title, slugify(title))
                slug = m["slug"] if m else slugify(title)
                accent = (m.get("accent") if m and m.get("accent") else pick_accent(books))
                video = body.get("video") or (m.get("video", "") if m else "")
                book = generate(title, author, slug, accent, video)
                self._send(200, json.dumps({"book": book}))
            elif self.path == "/youtube":
                vids = youtube_search(body.get("title", ""), body.get("author", ""))
                self._send(200, json.dumps({"videos": vids}))
            elif self.path == "/exists":
                title = body.get("title", "")
                m = find_existing(load_books(), title, slugify(title))
                self._send(200, json.dumps({"exists": m is not None,
                                            "slug": (m["slug"] if m else slugify(title))}))
            elif self.path == "/save":
                book = body["book"]
                books = load_books()
                m = find_existing(books, book.get("title", ""), book.get("slug", ""))
                if m:
                    book["slug"] = m["slug"]                       # overwrite the same entry
                    if not book.get("accent"):
                        book["accent"] = m.get("accent", "")
                    if not book.get("video"):
                        book["video"] = m.get("video", "")
                if not book.get("accent"):
                    book["accent"] = pick_accent(books)
                upsert_book(book)
                res = gen_qr_for(book)
                self._send(200, json.dumps({
                    "svg": res["svg"], "label": res["label"],
                    "log": f"Wrote {res['svg']}\nWrote {res['label']}\nURL: {res['url']}",
                }))
            elif self.path == "/publish":
                self._send(200, json.dumps({"log": publish()}))
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}))


def main():
    if not API_KEY:
        print("!! Set your key first:  export ANTHROPIC_API_KEY=\"sk-ant-...\"")
    url = f"http://localhost:{PORT}"
    print(f"Control panel: {url}   (Ctrl-C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()