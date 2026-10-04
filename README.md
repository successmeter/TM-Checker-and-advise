# TM Advisor

A brand filing check for Australian founders who want to file their own trade mark. It screens a proposed word
mark against the register, the IP Australia goods & services picklist and common section 41 / section 44
problems, explains the result in plain English, and says when to speak to a registered trade marks attorney.

TM Advisor is software, not a law firm or a trade marks attorney, and does not give legal advice.

- Design: [docs/design.md](docs/design.md)
- Implementation plan: [docs/implementation-plan.md](docs/implementation-plan.md)

## Status

Phase 1 (MVP) works end to end against a **fixture register** of invented marks and a **sample picklist**.
The IP Australia client is written and unit-tested, but its request filters and response mapping still have to be
checked against a real response once API access is approved (see `tm_advisor/register/ipaustralia.py`).

## Run it

Windows (PowerShell), from the project folder, e.g. `C:\Users\saura\TM Checker & Advise tool`:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
uvicorn tm_advisor.api:app --reload
```

macOS / Linux:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn tm_advisor.api:app --reload
```

Open http://127.0.0.1:8000 for the page, or http://127.0.0.1:8000/docs for the API.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `TM_REGISTER` | `fixture` | `fixture` or `ipaustralia` |
| `TM_REGISTER_FIXTURE` | `data/register_fixture.json` | Fixture register file |
| `TM_PICKLIST` | `data/picklist.json` if present, else `data/picklist_sample.json` | Picklist file |
| `IPA_CLIENT_ID`, `IPA_CLIENT_SECRET` | | From the IP Australia API portal |
| `IPA_TOKEN_URL` | | OAuth2 token endpoint shown on the portal |
| `IPA_BASE_URL` | production Trade Mark Search API | Use the test base URL while developing |

## Getting real data

1. **Register access**: register on the IP Australia API portal and request access to the *Australian Trade Mark
   Search API* (manual approval). Access uses OAuth2 client credentials.
2. **Picklist**: request access to the *Trade Mark Goods and Services (TMGnS) API* and save the full picklist as
   `data/picklist.json` in the same shape as `data/picklist_sample.json`.

## Layout

```
tm_advisor/
  models.py            request and report shapes
  text.py              normalising, plurals, edit distance, sound-alike key
  mark_similarity.py   how alike two marks look and sound
  goods_similarity.py  overlap between goods/services (same class, broad headings, related classes)
  distinctiveness.py   section 41 screen
  picklist.py          picklist match, suggestions, search
  register/            fixture and IP Australia register clients
  analysis.py          runs every check and builds the report
  api.py, static/      FastAPI app and the page
```
