"""Render img-src/flow.drawio to img/flow.png with draw.io's own viewer engine.

usage (inside deck/):  ../satyapatra/backend/.venv/bin/python img-src/render_drawio.py
Needs Google Chrome and an internet connection (the viewer script loads from viewer.diagrams.net).
"""
import html
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

DECK = Path(__file__).resolve().parents[1]
xml = (DECK / "img-src/flow.drawio").read_text()
cfg = {"xml": xml, "highlight": "none", "nav": False, "resize": False, "toolbar": "", "zoom": 1, "border": 0, "lightbox": False}
page = Path(tempfile.gettempdir()) / "ns-flow.html"
page.write_text('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}.mxgraph{width:1440px}</style>'
                f'</head><body><div class="mxgraph" data-mxgraph="{html.escape(json.dumps(cfg), quote=True)}"></div>'
                '<script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script></body></html>')
raw = Path(tempfile.gettempdir()) / "ns-flow-raw.png"
subprocess.run([sys.executable, str(DECK / "cdp_clip.py"), page.as_uri(), str(raw), ".mxgraph svg", "8", "0"], check=True)
im = Image.open(raw).convert("RGB")
im = im.resize((2800, round(im.height * 2800 / im.width)), Image.LANCZOS)
im.save(DECK / "img/flow.png", optimize=True)
print("img/flow.png", im.size)
