# TM Advisor

A brand filing check for Australian founders who want to file their own trade mark. It screens a proposed word
mark against the register, the IP Australia goods & services picklist and common section 41 / section 44
problems, explains the result in plain English, and says when to speak to a registered trade marks attorney.

TM Advisor is software, not a law firm or a trade marks attorney, and does not give legal advice.

- Design: [docs/design.md](docs/design.md)
- Implementation plan: [docs/implementation-plan.md](docs/implementation-plan.md)

## Status

- **Phase 1 (checks)** works end to end against a **fixture register** of invented marks and a **sample picklist**.
- **Phase 2 (explanations)**: "Explain in plain English" sends the findings plus matching Trade Marks Manual
  passages to Claude and shows the answer with links to the Manual. It needs an Anthropic API key and a local
  Manual index (below); without them the checks still work and the page says explanations aren't set up.
- The IP Australia register and picklist clients are written and unit-tested against simulated responses. Their
  field mapping has to be checked against real responses once API access is approved.

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

### Turn on plain-English explanations

1. Get an API key at https://console.anthropic.com and set it before starting the server:
   - PowerShell: `$env:ANTHROPIC_API_KEY = "sk-ant-..."`
   - macOS / Linux: `export ANTHROPIC_API_KEY=sk-ant-...`
2. Download and index the Trade Marks Manual (once; re-run when the Manual changes). It fetches about one page
   per second and obeys IP Australia's robots.txt, so the first run takes a while:

   ```
   python -m tm_advisor.manual crawl
   ```

   Pages go to `data/manual/pages.jsonl` and the search index to `data/manual/manual.sqlite`. Running `crawl` again
   does nothing once the Manual is downloaded; to pick up Manual updates use `crawl --refresh` (the old copy is kept
   until the new download finishes). To re-index without downloading: `python -m tm_advisor.manual index`.

Each explanation is one Claude call (Claude Opus 5.5 by default, with Anthropic's automatic fallback model if a
request is declined). Claude only explains the findings: it can't change a risk level, and citations to Manual
passages that weren't retrieved are dropped.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `TM_REGISTER` | `fixture` | `fixture` or `ipaustralia` |
| `TM_REGISTER_FIXTURE` | `data/register_fixture.json` | Fixture register file |
| `TM_PICKLIST` | `data/picklist.json` if present, else `data/picklist_sample.json` | Picklist file |
| `IPA_CLIENT_ID`, `IPA_CLIENT_SECRET` | | From the IP Australia API portal |
| `IPA_TOKEN_URL` | | OAuth2 token endpoint shown on the portal |
| `IPA_BASE_URL` | production Trade Mark Search API | Use the test base URL while developing |
| `TMGNS_BASE_URL` | production TMGnS API | Picklist API base URL |
| `ANTHROPIC_API_KEY` | | Turns on explanations |
| `TM_LLM_MODEL` | `claude-opus-5-5` | Model used for explanations |
| `TM_MANUAL_INDEX` | `data/manual/manual.sqlite` | Manual search index |

## Getting real data

1. **Register access**: register on the IP Australia API portal and request access to the *Australian Trade Mark
   Search API* (manual approval). Access uses OAuth2 client credentials.
2. **Picklist (no API access needed)**: `python -m tm_advisor.picklist_site sync` reads IP Australia's public
   classification search, one page per class (https://tmgns.search.ipaustralia.gov.au/descriptions?class=1 to 45),
   about one page per second, into `data/picklist.json`. If it reports no terms, run
   `python -m tm_advisor.picklist_site probe` and send the output: the page is probably built by JavaScript.
   **Or, with API access**: request access to the *Trade Mark Goods and Services (TMGnS) API*, then run
   `python -m tm_advisor.picklist_sync` (same `IPA_*` credentials). It downloads every description into
   `data/picklist.json`, which the app uses instead of the sample. If you download the file another way:
   `python -m tm_advisor.picklist_sync --from-file <file>`.
3. **Manual**: `python -m tm_advisor.manual crawl` (above).

## Layout

```
tm_advisor/
  models.py            request and report shapes
  text.py              normalising, plurals, edit distance, sound-alike key
  mark_similarity.py   how alike two marks look and sound
  goods_similarity.py  overlap between goods/services (same class, broad headings, related classes)
  distinctiveness.py   section 41 screen
  picklist.py          picklist match, suggestions, search
  picklist_sync.py     full picklist download from the TMGnS API
  picklist_site.py     full picklist from IP Australia's public classification search pages
  register/            fixture and IP Australia register clients
  ipa_auth.py          IP Australia OAuth tokens
  analysis.py          runs every check and builds the report
  manual/              Trade Marks Manual download, parsing, chunking, keyword search
  explain.py           plain-English explanations with Claude, grounded in Manual passages
  api.py, static/      FastAPI app and the page
```
