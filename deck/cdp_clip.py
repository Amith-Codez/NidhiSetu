"""Screenshot exactly one part of a live page (by CSS selector) at 2x, after a real-time wait.
usage: python cdp_clip.py URL OUT.png SELECTOR WAIT_SECONDS [PAD]
(clips the union of every element SELECTOR matches)
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE = os.path.join(tempfile.gettempdir(), "sp-capture-profile")


async def main(url, out, sel, wait, pad):
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={PROFILE}",
                             "--remote-debugging-port=9334", "--window-size=1440,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9334/json"))
                break
            except Exception:
                time.sleep(0.2)
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=80_000_000) as ws:
            n = 0

            async def call(method, **params):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == n:
                        return m.get("result", {})
            await call("Emulation.setDeviceMetricsOverride", width=1440, height=1600, deviceScaleFactor=2, mobile=False)
            await call("Page.enable")
            await call("Page.navigate", url=url)
            await asyncio.sleep(wait)
            r = await call("Runtime.evaluate", returnByValue=True,
                           expression=f"""(() => {{ const rs = [...document.querySelectorAll({json.dumps(sel)})].map(e => e.getBoundingClientRect());
                               const x = Math.min(...rs.map(r => r.left)), y = Math.min(...rs.map(r => r.top));
                               return JSON.stringify({{x, y, width: Math.max(...rs.map(r => r.right)) - x, height: Math.max(...rs.map(r => r.bottom)) - y}}); }})()""")
            box = json.loads(r["result"]["value"])
            clip = {"x": max(0, box["x"] - pad), "y": max(0, box["y"] - pad), "width": box["width"] + 2 * pad,
                    "height": box["height"] + 2 * pad, "scale": 2}
            shot = await call("Page.captureScreenshot", format="png", clip=clip)
            open(out, "wb").write(base64.b64decode(shot["data"]))
            print(out, int(clip["width"]), int(clip["height"]))
    finally:
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]) if len(sys.argv) > 5 else 0))
