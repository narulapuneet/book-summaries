#!/usr/bin/env python3
"""
Generate one QR code per book, each pointing to that book's page on your site.

1. Host the folder (index.html + books.json) somewhere with a real URL.
2. Set BASE_URL below to that URL.
3. Run:  python3 make_qrs.py
   -> writes qr/<slug>.png for every book, plus qr/labels.html to print & cut.

Requires:  pip install "qrcode[pil]"
"""

import json
import os
import qrcode

# ---- EDIT THIS to your live site root (no trailing slash) ----
BASE_URL = "https://YOURNAME.github.io/book-summaries"
# --------------------------------------------------------------

OUT = "qr"


def main():
    with open("books.json", encoding="utf-8") as f:
        books = json.load(f)

    os.makedirs(OUT, exist_ok=True)
    cards = []

    for b in books:
        slug = b["slug"]
        url = f"{BASE_URL}/#{slug}"

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # survives small print
            box_size=12,
            border=3,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#12203a", back_color="white")
        path = os.path.join(OUT, f"{slug}.png")
        img.save(path)
        print(f"  {slug:<16} -> {url}")

        cards.append(
            f'''<div class="card">
      <img src="{slug}.png" alt="QR for {b["title"]}">
      <div class="meta">
        <div class="scan">Scan for summary</div>
        <div class="title">{b["title"]}</div>
        <div class="author">{b["author"]}</div>
      </div>
    </div>'''
        )

    sheet = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Book QR labels</title>
<style>
  @page {{ margin: 12mm; }}
  body {{ font-family: system-ui, sans-serif; color:#12203a; }}
  .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10mm; }}
  .card {{ border:1px dashed #b9b1a1; border-radius:6px; padding:6mm;
           text-align:center; break-inside:avoid; }}
  .card img {{ width:34mm; height:34mm; }}
  .scan {{ font-size:8pt; letter-spacing:.12em; text-transform:uppercase;
           color:#e0762f; font-weight:600; margin-top:3mm; }}
  .title {{ font-size:11pt; font-weight:600; margin-top:1mm; }}
  .author {{ font-size:8.5pt; color:#54617a; }}
  h1 {{ font-size:13pt; font-weight:600; margin-bottom:6mm; }}
</style></head>
<body>
  <h1>Book summary QR labels — cut along the dashed lines</h1>
  <div class="grid">
    {''.join(cards)}
  </div>
</body></html>"""

    with open(os.path.join(OUT, "labels.html"), "w", encoding="utf-8") as f:
        f.write(sheet)

    print(f"\nDone. {len(books)} codes in ./{OUT}/  +  labels.html to print.")
    if "YOURNAME" in BASE_URL:
        print("!! Set BASE_URL to your real site first, then re-run.")


if __name__ == "__main__":
    main()
