"""Export img-src/flow.drawio as SVG and as a one-page vector PDF, using draw.io's own viewer engine.

usage (inside deck/):  ../backend/.venv/bin/python img-src/export_vector.py OUT_DIR
Needs Google Chrome and an internet connection (the viewer script loads from viewer.diagrams.net).
"""
import asyncio
import base64
import html
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DECK = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.gettempdir())


async def cdp(port, steps):
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={TMP / f'ns-export-{port}'}",
                             f"--remote-debugging-port={port}", "--window-size=1500,1000", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                break
            except Exception:
                time.sleep(0.2)
        async with websockets.connect(next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"), max_size=100_000_000) as ws:
            n = 0

            async def call(method, **params):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == n:
                        return m.get("result") or {"error": m.get("error")}
            return await steps(call)
    finally:
        proc.terminate()
        time.sleep(1)


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    cfg = {"xml": (DECK / "img-src/flow.drawio").read_text(), "highlight": "none", "nav": False, "resize": False,
           "toolbar": "", "zoom": 1, "border": 0, "lightbox": False}
    viewer = TMP / "ns-flow-viewer.html"
    viewer.write_text('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}.mxgraph{width:1440px}'
                      f'</style></head><body><div class="mxgraph" data-mxgraph="{html.escape(json.dumps(cfg), quote=True)}"></div>'
                      '<script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script></body></html>')

    async def get_svg(call):
        await call("Page.enable")
        await call("Page.navigate", url=viewer.as_uri())
        await asyncio.sleep(8)
        r = await call("Runtime.evaluate", returnByValue=True, expression="""(() => {
            const s = document.querySelector('.mxgraph svg'); const b = s.getBoundingClientRect();
            const c = s.cloneNode(true); c.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
            c.setAttribute('width', Math.ceil(b.width)); c.setAttribute('height', Math.ceil(b.height));
            c.setAttribute('viewBox', `0 0 ${Math.ceil(b.width)} ${Math.ceil(b.height)}`); c.style.cssText = 'background:#fff';
            return JSON.stringify({w: Math.ceil(b.width), h: Math.ceil(b.height), svg: new XMLSerializer().serializeToString(c)}); })()""")
        return json.loads(r["result"]["value"])

    d = asyncio.run(cdp(9337, get_svg))
    (out / "NidhiSetu_Flowchart.svg").write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + d["svg"])
    page = TMP / "ns-flow-print.html"
    page.write_text(f'<!doctype html><html><head><meta charset="utf-8"><style>@page{{size:{d["w"]}px {d["h"]}px;margin:0}}'
                    f'html,body{{margin:0;background:#fff}}svg{{display:block}}</style></head><body>{d["svg"]}</body></html>')

    async def print_pdf(call):
        await call("Page.enable")
        await call("Page.navigate", url=page.as_uri())
        await asyncio.sleep(3)
        return await call("Page.printToPDF", printBackground=True, preferCSSPageSize=True)

    pdf = asyncio.run(cdp(9338, print_pdf))
    if "data" not in pdf:
        sys.exit(f"PDF export failed: {pdf.get('error')}")
    (out / "NidhiSetu_Flowchart.pdf").write_bytes(base64.b64decode(pdf["data"]))
    print("wrote", out / "NidhiSetu_Flowchart.svg", "and", out / "NidhiSetu_Flowchart.pdf", f"({d['w']}x{d['h']})")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DECK / "export")
