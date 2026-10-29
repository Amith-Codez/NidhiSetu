# NidhiSetu · SIH 2026 · PS SIH26265 (AICTE Regulation Bureau)

Every security deposit confirmed with the bank, and tracked from submission to release.

**Live demo:** https://nidhisetu-l4et.onrender.com (free plan: the first visit after a quiet spell takes about a minute to wake up)

The PS asks for a portal that tells apart "what the institution submitted" from "what the bank confirmed". NidhiSetu reads each FDR, checks the deposit rules, asks the bank directly (Tier 1 signed e-FDR or QR, Tier 2 term-deposit API, Tier 3 signed branch link), and puts the two side by side. A daily monitor sends reminders at 90, 60, 30 and 7 days and escalates overdue deposits. It also re-checks every active deposit with its bank every 90 days, so an FD closed early is caught within a quarter, not at maturity. Release needs two different officials and ends in a discharge letter asking the bank to remove AICTE's lien.

## What is in this folder

| Path | What it is |
|---|---|
| `deck/NidhiSetu_SIH26265_Idea.pdf` | **The file to upload**: the 6-slide idea deck on the official SIH 2026 template |
| `deck/NidhiSetu_SIH26265_Idea.pptx` | The same deck, editable (fill in [Team Name], [Team ID] and the three links on slide 2) |
| `deck/img-src/flow.drawio` | The slide 3 flowchart as an editable draw.io file; `flow_drawio.py` regenerates it, `render_drawio.py` renders `img/flow.png`, `export_vector.py` writes SVG and PDF |
| `deck/build_deck.py` | Builds the deck from the template, the images in `img/` and `backend/data/eval/results.json` |
| `backend/` | FastAPI portal, the five engines, the lifecycle monitor, releases, bank sandbox, scripts, tests |
| `frontend/` | Officer console (React 18 + TypeScript on UX4G 3.0 tokens, Noto Sans) |
| `downloads/` | Copies of the deck and the flowchart (PNG, SVG, PDF, .drawio) for sharing |

## Run it on a laptop

```bash
cd backend
.venv/bin/python scripts/fdrgen.py pki                               # sandbox bank CA, e-FDR certificate, seals
.venv/bin/uvicorn bank_sandbox.app:app --port 8200 &                  # sandbox bank verification service
.venv/bin/python scripts/seed_demo.py                                 # 24 fictional institutions, 38 deposits
.venv/bin/python scripts/evaluate.py 10                               # 140 labelled receipts -> data/eval/results.json
cd ../frontend && npm ci && npm run build && cd ../backend
.venv/bin/uvicorn app.main:app --port 8300                            # console at http://127.0.0.1:8300
.venv/bin/python -m pytest -q tests                                   # 6 tests
```

(`backend/.venv` and `frontend/node_modules` are links to the SatyaPatra project's environment on this laptop. Elsewhere, create them with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` and `npm install`.)

## Deploy (one container)

The `Dockerfile` builds the console, installs the API, and bakes the demo data into the image (`backend/build_demo.sh`), so the site starts at once and every restart is a clean demo. `backend/start.sh` runs the sandbox bank inside the container and the portal on `$PORT`. It works on any Docker host, for example Render (Web Service, Docker runtime, free plan) or a Hugging Face Space (Docker SDK).

## Two-minute demo script

1. **Overview**: 34 deposits in force, 79% confirmed by the bank, 8 need action.
2. **Deposit FDR-0034**: the receipt says ₹25 lakh; the bank says ₹2.5 lakh. Box 1 is the white patch over the amount.
3. **Deposit FDR-0038** (the live demo deposit): click *Demo: bank closes it*, then *Run monitor now* on the Overview. The quarterly re-check catches the closure and escalates it to the Regulation Bureau.
4. **Release requests**: as Section Officer, try to approve a release you recommended: refused (maker-checker). Switch *Acting as* to Competent authority and approve.
5. **Check an FDR**: run the sample "Receipt the bank never issued".

## Measured (synthetic data, as the PS allows)

- **Detection:** 80 of 80 forged receipts caught across 8 patterns from reported cases, with 0 false alarms on 60 genuine receipts (20 of them phone photos).
- **Speed:** median 0.14 s per PDF and 1.0 s per phone photo, on a laptop CPU.
- **Early closure:** in a 10,000-deposit simulation, checking only at maturity finds an early closure after a median 1,178 days; the 90-day re-check finds it in a median 45 days.

All institutions, banks, people and numbers in the demo are fictional. The bank sandbox stands in for a bank's verification service.
