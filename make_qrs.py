#!/usr/bin/env python3
"""
Generate QR codes (SVG) for book summaries — one standalone file per book.

Each book gets TWO new files, and existing books are never touched:
  qr/<slug>.svg          the raw QR code
  qr/<slug>-label.html   a print-and-cut label (QR + title + author), self-contained

Bulk mode (rebuild everything):   python3 make_qrs.py
Single book (used by admin.py):   make_qrs.make_one(book_dict)

SVG output needs NO native image libraries. Requires only: pip3 install qrcode
"""

import json
import os
import re
import qrcode
from qrcode.image.svg import SvgPathImage

# ---- your live site root (no trailing slash) ----
BASE_URL = "https://narulapuneet.github.io/book-summaries"
# --------------------------------------------------
OUT = "qr"
SKIP_SLUGS = {"template"}   # placeholder entries — never get a QR


def _svg_inline(url):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # survives small print
        box_size=12, border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    svg = qr.make_image(image_factory=SvgPathImage).to_string(encoding="unicode")
    return re.sub(r"<\?xml.*?\?>\s*", "", svg, flags=re.DOTALL)  # drop prolog for embedding


def _label_html(book, svg_inline):
    accent = book.get("accent", "#e0762f")
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>{book['title']} — QR label</title>
<style>
 @page {{ margin:12mm; }}
 body {{ font-family:system-ui,-apple-system,sans-serif; color:#12203a; margin:0; }}
 .card {{ width:52mm; border:1px dashed #b9b1a1; border-radius:6px; padding:6mm;
   text-align:center; }}
 .qr {{ width:34mm; height:34mm; margin:0 auto; }}
 .qr svg {{ width:34mm; height:34mm; display:block; }}
 .scan {{ font-size:8pt; letter-spacing:.12em; text-transform:uppercase;
   color:{accent}; font-weight:600; margin-top:3mm; }}
 .title {{ font-size:11pt; font-weight:600; margin-top:1mm; }}
 .author {{ font-size:8.5pt; color:#54617a; }}
 .printbtn {{ display:none; }}
 @media screen {{
   body{{background:#e9e5dd;padding:24px}} .card{{background:#fff}}
   .printbtn{{display:inline-block;margin-top:16px;padding:10px 16px;border:none;
     border-radius:9px;background:{accent};color:#fff;font-weight:600;font-size:.9rem;cursor:pointer}}
 }}
</style></head><body>
 <div class="card">
   <div class="qr">{svg_inline}</div>
   <div class="scan">Scan for summary</div>
   <div class="title">{book['title']}</div>
   <div class="author">{book['author']}</div>
 </div>
 <button class="printbtn" onclick="window.print()">Print label</button>
</body></html>"""


def make_one(book, base_url=BASE_URL, out=OUT):
    """Write qr/<slug>.svg and qr/<slug>-label.html for ONE book. Returns paths."""
    os.makedirs(out, exist_ok=True)
    url = f"{base_url}/#{book['slug']}"
    svg = _svg_inline(url)

    svg_path = os.path.join(out, f"{book['slug']}.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + svg)

    label_path = os.path.join(out, f"{book['slug']}-label.html")
    with open(label_path, "w", encoding="utf-8") as f:
        f.write(_label_html(book, svg))

    return {"url": url, "svg": svg_path, "label": label_path}


def make_all(base_url=BASE_URL, out=OUT):
    with open("books.json", encoding="utf-8") as f:
        books = json.load(f)
    books = [b for b in books if b["slug"] not in SKIP_SLUGS]
    results = [make_one(b, base_url, out) for b in books]
    # clean up any stale QR files for placeholder slugs
    for s in SKIP_SLUGS:
        for fn in (f"{s}.svg", f"{s}-label.html"):
            fp = os.path.join(out, fn)
            if os.path.exists(fp):
                os.remove(fp)
    make_sheet(base_url, out)
    for r in results:
        print(f"  {os.path.basename(r['svg']):<22} {r['url']}")
    print(f"\nDone. {len(results)} books -> qr/<slug>.svg + qr/<slug>-label.html")
    print(f"       combined sheet -> {os.path.join(out, 'all-labels.html')}")
    if "YOURNAME" in base_url:
        print("!! Set BASE_URL to your real site first, then re-run.")
    return results


def _card_html(book, svg_inline):
    accent = book.get("accent", "#e0762f")
    return (f'<div class="card"><div class="qr">{svg_inline}</div>'
            f'<div class="scan" style="color:{accent}">Scan for summary</div>'
            f'<div class="title">{book["title"]}</div>'
            f'<div class="author">{book["author"]}</div></div>')


def make_sheet(base_url=BASE_URL, out=OUT):
    """(Re)build qr/all-labels.html — a contact sheet of EVERY book's QR. Returns path."""
    os.makedirs(out, exist_ok=True)
    with open("books.json", encoding="utf-8") as f:
        books = json.load(f)
    books = [b for b in books if b["slug"] not in SKIP_SLUGS]
    cards = "".join(_card_html(b, _svg_inline(f"{base_url}/#{b['slug']}")) for b in books)
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>All QR codes</title>
<style>
 @page {{ margin:12mm; }}
 body {{ font-family:system-ui,-apple-system,sans-serif; color:#12203a; margin:0; }}
 h1 {{ font-size:13pt; margin:0 0 5mm; }}
 .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8mm; }}
 .card {{ border:1px dashed #b9b1a1; border-radius:6px; padding:5mm; text-align:center; break-inside:avoid; }}
 .qr {{ width:32mm; height:32mm; margin:0 auto; }}
 .qr svg {{ width:32mm; height:32mm; display:block; }}
 .scan {{ font-size:7.5pt; letter-spacing:.1em; text-transform:uppercase; font-weight:600; margin-top:2.5mm; }}
 .title {{ font-size:10pt; font-weight:600; margin-top:1mm; }}
 .author {{ font-size:8pt; color:#54617a; }}
 .printbtn {{ display:none; }}
 @media screen {{
   body{{background:#e9e5dd;padding:24px}}
   .wrap{{background:#fff;padding:22px;border-radius:12px;max-width:900px;margin:0 auto}}
   .card{{background:#fff}}
   .printbtn{{display:inline-block;margin:0 0 16px;padding:10px 16px;border:none;
     border-radius:9px;background:#12203a;color:#fff;font-weight:600;cursor:pointer}}
 }}
</style></head><body>
 <div class="wrap">
   <button class="printbtn" onclick="window.print()">Print all</button>
   <h1>All book QR codes — cut along the dashed lines</h1>
   <div class="grid">{cards}</div>
 </div>
</body></html>"""
    path = os.path.join(out, "all-labels.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    make_all()