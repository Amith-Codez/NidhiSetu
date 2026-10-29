#!/bin/zsh
# Render img-src/<name>.html to img/<name>.png at 2x, then trim trailing white space.
# usage (inside deck/): ./render.sh name width height
C="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
P="${TMPDIR:-/tmp}/sp-render-profile"; PY="${0:A:h}/../backend/.venv/bin/python"
n=$1; w=$2; h=$3
perl -e 'alarm 15; exec @ARGV' "$C" --headless=new --disable-gpu --hide-scrollbars --user-data-dir=$P --force-device-scale-factor=2 \
  --window-size=$w,$((h+300)) --screenshot="$PWD/img/$n.png" "file://$PWD/img-src/$n.html" >/dev/null 2>&1
pkill -f sp-render-profile 2>/dev/null
"$PY" - "$n" "$w" "$h" <<'PYEOF'
import sys
from PIL import Image, ImageChops
n, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
im = Image.open(f"img/{n}.png").convert("RGB").crop((0, 0, w * 2, h * 2))
box = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
if box: im = im.crop((0, 0, w * 2, min(h * 2, box[3] + 20)))
im.save(f"img/{n}.png", optimize=True); print(n, im.size)
PYEOF
