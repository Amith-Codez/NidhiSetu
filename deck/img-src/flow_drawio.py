"""Build the NidhiSetu flow diagram as an editable draw.io file.

usage (inside deck/):  ../satyapatra/backend/.venv/bin/python img-src/architecture_drawio.py
writes img-src/flow.drawio (open it at app.diagrams.net) and img-src/flow.url
(the same diagram as a #R link that opens straight in the draw.io editor).
Icons are the Lucide set the console uses, read from the frontend's node_modules.
"""
import base64
import re
import urllib.parse
import zlib
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
ICONS = HERE.parents[1] / "frontend/node_modules/lucide-react/dist/esm/icons"
W, H = 1400, 866
FONT = "Helvetica"

# role colours (fill, stroke, text) in the style of the reference flowchart
INST = ("#CFE2F3", "#3D85C6", "#0B2A4A")
OFFICER = ("#3C78D8", "#1C4587", "#FFFFFF")
ENGINE = ("#8E7CC3", "#4C3A8C", "#FFFFFF")
DECIDE = ("#5E4AA8", "#3A2A7A", "#FFFFFF")
DATA = ("#F3F3F3", "#8C8C8C", "#262626")
ISSUER = ("#F9CB9C", "#B45F06", "#3D1F00")
STEP = ("#FFD966", "#BF9000", "#3D2E00")
FORWARD = ("#B6D7A8", "#38761D", "#173D0B")
INSPECT = ("#F9CB9C", "#B45F06", "#3D1F00")
CLARIFY = ("#FFE599", "#BF9000", "#3D2E00")

cells, n = [], [1]


def nid():
    n[0] += 1
    return f"c{n[0]}"


def icon_uri(name, color):
    src = (ICONS / f"{name}.js").read_text()
    body = "".join(f"<{tag} " + " ".join(f'{k}="{v}"' for k, v in re.findall(r'(\w+): "([^"]*)"', attrs) if k != "key") + "/>"
                   for tag, attrs in re.findall(r'\[\s*"(\w+)",\s*\{([^}]*)\}\s*\]', src))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    return "data:image/svg+xml," + base64.b64encode(svg.encode()).decode()


def vertex(x, y, w, h, value, style):
    i = nid()
    cells.append(f'<mxCell id="{i}" value={quoteattr(value)} style="{style}" vertex="1" parent="1">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i


def label(title, sub=None, tsize=17, ssize=13):
    t = f'<b style="font-size:{tsize}px">{escape(title)}</b>'
    return t + (f'<br><span style="font-size:{ssize}px">{escape(sub)}</span>' if sub else "")


def node(x, y, w, h, title, sub, colors, icon=None, rounded=True, tsize=17, ssize=13):
    fill, stroke, font = colors
    style = (f"rounded={1 if rounded else 0};arcSize=12;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};"
             f"strokeWidth=2;fontColor={font};fontFamily={FONT};align={'left' if icon else 'center'};verticalAlign=middle;"
             f"spacingLeft={46 if icon else 6};spacingRight=6;")
    i = vertex(x, y, w, h, label(title, sub, tsize, ssize), style)
    if icon:
        vertex(x + 13, y + (h - 24) / 2, 24, 24, "", f"shape=image;image={icon_uri(icon, font)};aspect=fixed;imageAspect=0;")
    return i


def text(x, y, w, h, value, size=12, color="#333333", bold=False, align="center", bg=True):
    style = (f"text;html=1;whiteSpace=wrap;fontFamily={FONT};fontSize={size};fontColor={color};align={align};verticalAlign=middle;"
             f"{'fontStyle=1;' if bold else ''}{'labelBackgroundColor=#FFFFFF;' if bg else ''}")
    return vertex(x, y, w, h, escape(value), style)


def edge(src, dst, pts=(), exit=None, entry=None, dashed=False, both=False, color="#3A3A3A"):
    i = nid()
    style = (f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeWidth=2;strokeColor={color};endArrow=block;endFill=1;endSize=7;"
             f"{'dashed=1;dashPattern=6 4;' if dashed else ''}{'startArrow=block;startFill=1;startSize=7;' if both else ''}")
    if exit:
        style += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
    if entry:
        style += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
    p = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts)
    cells.append(f'<mxCell id="{i}" style="{style}" edge="1" parent="1" source="{src}" target="{dst}">'
                 f'<mxGeometry relative="1" as="geometry">{f"<Array as=\"points\">{p}</Array>" if p else ""}</mxGeometry></mxCell>')


RELEASE = ("#D9D2E9", "#674EA7", "#20124D")

# ---------------------------------------------------------------- top: start and sign-in
start = vertex(668, 2, 64, 64, "<b>START</b>", f"ellipse;whiteSpace=wrap;html=1;fillColor=#8BC48A;strokeColor=#2E7D32;strokeWidth=2;"
                                              f"fontColor=#10381A;fontFamily={FONT};fontSize=14;")
signin = node(580, 86, 240, 60, "Role-based sign-in", "institution · officer · bank branch", STEP, "log-in")
edge(start, signin)
vertex(300, 70, 26, 26, "", f"shape=image;image={icon_uri('school', '#0B2A4A')};aspect=fixed;")
text(330, 70, 150, 26, "Institution sign-in", 13, "#0B2A4A", True, "left", bg=False)
vertex(1030, 70, 26, 26, "", f"shape=image;image={icon_uri('badge-check', '#1C4587')};aspect=fixed;")
text(1060, 70, 160, 26, "AICTE officer sign-in", 13, "#1C4587", True, "left", bg=False)

# ---------------------------------------------------------------- institution column
upload = node(20, 186, 230, 84, "Uploads the FDR", "paper receipt or bank e-FDR · amount, bank, IFSC, maturity", INST, "cloud-upload")
status = node(20, 716, 230, 80, "Reminders, status", "email + SMS at 90, 60, 30 and 7 days", INST, "bell-ring")
edge(signin, upload, [(135, 116)], exit=(0, 0.5), entry=(0.5, 0))
edge(status, upload, exit=(0.9, 0), entry=(0.9, 1))
vertex(234, 380, 24, 250, "uploads the renewed FDR", f"text;html=1;horizontal=0;fontFamily={FONT};fontSize=12;fontColor=#333333;align=center;verticalAlign=middle;")

vertex(20, 318, 178, 206, "", "rounded=1;arcSize=6;fillColor=#FFFFFF;strokeColor=#D0D0D0;strokeWidth=1;")
text(32, 326, 150, 20, "COLOUR KEY", 12, "#555555", True, "left", bg=False)
for k, (name, (fill, stroke, _)) in enumerate([("Institution", INST), ("AICTE officer", OFFICER), ("Engine and monitor", ENGINE),
                                               ("Knowledge and data", DATA), ("Issuing bank", ISSUER), ("Decision step", STEP)]):
    y = 352 + k * 27
    vertex(32, y + 2, 18, 18, "", f"rounded=1;arcSize=20;fillColor={fill};strokeColor={stroke};strokeWidth=2;")
    text(58, y, 135, 22, name, 13, "#262626", False, "left", bg=False)

# ---------------------------------------------------------------- API and the five engines
queue = node(300, 192, 260, 72, "API + job queue", "beside the AICTE portal · FastAPI · original kept by SHA-256", DATA, "server-cog")
edge(upload, queue)
text(252, 202, 46, 18, "upload", 12, bg=False)
vertex(290, 282, 280, 394, "", "rounded=1;arcSize=4;fillColor=#F5F2FC;strokeColor=#8E7CC3;strokeWidth=2;dashed=1;dashPattern=8 5;")
text(300, 287, 210, 20, "VERIFICATION · 0.14 s PER FDR", 12, "#4C3A8C", True, "left", bg=False)
eng = {}
for k, (key, title, sub, ic) in enumerate([
        ("read", "READ", "every field, with its place on the page", "scan-text"),
        ("check", "CHECK", "favour, lien, amount, tenure, IFSC", "list-checks"),
        ("confirm", "CONFIRM", "ask the bank, never the paper", "shield-check"),
        ("detect", "DETECT", "white patch, font, re-saved file", "scan-search"),
        ("decide", "DECIDE", "confirmed · declared · discrepancy", "scale")]):
    eng[key] = node(310, 312 + k * 72, 240, 58, title, sub, DECIDE if key == "decide" else ENGINE, ic, ssize=12)
edge(queue, eng["read"], exit=(0.8462, 1), entry=(0.875, 0))
keys = list(eng)
for a, b in zip(keys, keys[1:]):
    edge(eng[a], eng[b])

# ---------------------------------------------------------------- what the engines consult
ocr = node(610, 312, 250, 58, "Local OCR · RapidOCR", "phone photos read on CPU, on AICTE servers", DATA, "cpu")
rulebook = node(610, 384, 250, 58, "Rulebook · IFSC list", "YAML rules, RBI branch list, pledge registry", DATA, "book-open-check")
bank = node(610, 456, 250, 58, "Issuing banks", "e-FDR signature · term-deposit API · branch link", ISSUER, "landmark")
monitor = node(610, 540, 250, 74, "Lifecycle monitor", "runs daily: reminders, escalation, bank re-check every 90 days", DECIDE, "calendar-clock")
edge(eng["read"], ocr, dashed=True, both=True, color="#7F7F7F")
edge(rulebook, eng["check"], dashed=True, color="#7F7F7F")
edge(eng["confirm"], bank, both=True, color="#B45F06")
edge(monitor, bank, color="#B45F06")
text(742, 516, 120, 22, "re-check", 12, "#B45F06", align="left", bg=False)

# ---------------------------------------------------------------- the database
db_ = vertex(650, 690, 170, 112, '<br><b style="font-size:15px">SYSTEM DATABASE</b><br><span style="font-size:12px">paper values · bank values · history</span>',
             f"shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;size=12;fillColor=#FFFFFF;strokeColor=#434343;strokeWidth=2;"
             f"fontColor=#262626;fontFamily={FONT};verticalAlign=middle;")
vertex(723, 706, 24, 24, "", f"shape=image;image={icon_uri('database', '#262626')};aspect=fixed;")
ledger = node(640, 812, 190, 30, "Audit ledger · SHA-256 chain", None, DATA, None, tsize=12)
edge(eng["decide"], db_, [(430, 730)], exit=(0.5, 1), entry=(0, 0.357))
text(440, 706, 90, 18, "write result", 12, bg=False)
edge(monitor, db_, both=True)
edge(db_, status, exit=(0, 0.732), entry=(1, 0.7))
text(320, 778, 300, 18, "status, reminders and bank answers", 12, bg=False)

# ---------------------------------------------------------------- officer column
register = node(1170, 186, 210, 76, "Deposit register", "6 stages · calendar · CSV reports", OFFICER, "layout-dashboard")
review = node(1170, 300, 210, 76, "Alerts and review", "escalations · paper vs bank, side by side", OFFICER, "search")
edge(signin, register, [(1275, 116)], exit=(1, 0.5), entry=(0.5, 0))
edge(register, review)
edge(db_, review, [(900, 712), (900, 338)], exit=(1, 0.196), entry=(0, 0.5))
edge(monitor, review, [(900, 577), (900, 338)], exit=(1, 0.5), entry=(0, 0.5))
text(912, 316, 250, 18, "register, bank answers and alerts", 12)
decide = vertex(1210, 402, 130, 80, '<b style="font-size:15px">Officer<br>decides</b>',
                f"rhombus;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#1C4587;strokeWidth=2;fontColor=#1C4587;fontFamily={FONT};")
edge(review, decide)
clarify = node(930, 528, 180, 50, "Ask the institution", None, CLARIFY, tsize=14)
release = node(1185, 528, 195, 50, "Release request", None, RELEASE, "undo-2", tsize=14)
edge(decide, clarify, [(1275, 506), (1020, 506)], exit=(0.5, 1), entry=(0.5, 0))
edge(decide, release, [(1275, 506), (1282.5, 506)], exit=(0.5, 1), entry=(0.5, 0))
text(1018, 486, 150, 18, "discrepancy", 12, bg=False)
text(1290, 486, 100, 18, "term over", 12, align="left", bg=False)
approve = node(1185, 600, 195, 50, "Two officials approve", "maker-checker", STEP, None, tsize=14)
discharge = node(1185, 672, 195, 56, "Discharge letter", "bank removes AICTE's lien", FORWARD, "mail-check", tsize=14)
end = vertex(1256, 752, 53, 53, "<b>END</b>", f"ellipse;whiteSpace=wrap;html=1;fillColor=#E06666;strokeColor=#990000;strokeWidth=2;"
                                           f"fontColor=#FFFFFF;fontFamily={FONT};fontSize=13;")
edge(release, approve)
edge(approve, discharge)
edge(discharge, end)
text(1150, 808, 110, 18, "released", 12, align="right", bg=False)
edge(clarify, status, [(1020, 852), (135, 852)], exit=(0.5, 1), entry=(0.5, 1))
text(470, 842, 380, 20, "clarification request → the institution answers", 12)
xml = (f'<mxfile host="app.diagrams.net"><diagram id="nidhisetu-flow" name="NidhiSetu flow">'
       f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" guides="1" page="1" pageWidth="{W}" pageHeight="{H}" background="#FFFFFF">'
       f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{"".join(cells)}</root></mxGraphModel></diagram></mxfile>')
(HERE / "flow.drawio").write_text(xml)
model = xml[xml.index("<mxGraphModel"):xml.index("</diagram>")]
c = zlib.compressobj(9, zlib.DEFLATED, -15)
packed = base64.b64encode(c.compress(urllib.parse.quote(model, safe="~()*!.'").encode()) + c.flush()).decode()
(HERE / "flow.url").write_text("https://app.diagrams.net/?splash=0#R" + urllib.parse.quote(packed, safe=""))
print("cells", n[0], "xml", len(xml), "url", len(packed))
