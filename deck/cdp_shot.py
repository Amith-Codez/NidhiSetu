"""Real-time screenshot via Chrome DevTools Protocol: load a URL, wait in real seconds, capture at 2x.
usage: python cdp_shot.py URL OUT.png WIDTH HEIGHT WAIT_SECONDS
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


async def main(url, out, w, h, wait):
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={PROFILE}",
                             "--remote-debugging-port=9333", f"--window-size={w},{h}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json"))
                break
            except Exception:
                time.sleep(0.2)
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            n = 0

            async def call(method, **params):
                nonlocal n
                n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == n:
                        return m.get("result", {})
            await call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2, mobile=False)
            await call("Page.enable")
            await call("Page.navigate", url=url)
            await asyncio.sleep(wait)
            shot = await call("Page.captureScreenshot", format="png")
            open(out, "wb").write(base64.b64decode(shot["data"]))
    finally:
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])))
