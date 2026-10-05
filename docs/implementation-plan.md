# TM Advisor: Implementation plan

**Design:** `docs/design.md`.

Every task is test-first: write the test, see it fail for the stated reason, implement, see it pass, run the whole
suite, commit. IP Australia is never called in tests.

## Phase 1: MVP (this branch)

### Task 1: Project skeleton
- `pyproject.toml` (fastapi, httpx, pydantic; pytest for dev), package `tm_advisor`, README with run steps for
  Windows and Linux.

### Task 2: Models
- Pydantic: `ClassSpec{class_number 1..45, terms[]}`, `Application{mark, classes[]}` (classes unique, terms
  trimmed, non-empty), `RegisterMark`, `Conflict`, `PicklistResult`, `DistinctivenessFlag`, `Report`.
- Tests: validation rejects class 0/46, empty mark, empty terms; duplicate classes rejected.

### Task 3: Text utilities
- `normalise`, `squash`, `words`, `stem` (plural strip), `edit_similarity` (Levenshtein ratio), `phonetic_key`.
- Tests: "Eco-Knit" == "ECO KNIT" squashed; "Kwik"/"Quick" share a phonetic key; similarity bounds.

### Task 4: Mark similarity
- `compare(user_mark, cited_mark) -> MarkSimilarity{score, reasons}`.
- Tests: identical; spacing/punctuation only; one-letter change; sound-alike; containment (ECOKNIT in ECO KNITWEAR);
  unrelated marks score low.

### Task 5: Picklist
- Load JSON `[{id, class_number, description}]`; `match(class, term)` exact (case/plural insensitive);
  `suggest(class, term, n)` by token overlap; `search(query, class?)`.
- Tests on `data/picklist_sample.json`.

### Task 6: Goods similarity
- `relate(user_class, user_terms, cited_class, cited_terms) -> GoodsRelation{level, overlapping_terms, note}`;
  related-class table.
- Tests: "sweaters" vs "knitted sweaters" same; "clothing" vs "knitted sweaters" same (broad term); class 25 vs 35
  "retail services in relation to clothing" related; 25 vs 9 none.

### Task 7: Distinctiveness screen
- Flags: word describes the goods (appears in user terms), laudatory/descriptive lexicon, mark entirely
  descriptive.
- Tests.

### Task 8: Register clients
- `RegisterClient` protocol; `FixtureRegisterClient` (search by similarity over fixture); `IpAustraliaRegisterClient`
  (token, quick search, get by number; injectable transport; mapping isolated).
- Tests: fixture search; IPA client with `httpx.MockTransport` asserts the token call, the search body and mapping.

### Task 9: Analysis and escalation
- `check(application, register, picklist) -> Report`; banding; escalation triggers; disclaimers.
- Tests: the EcoKnit example is High with "sweaters"/"clothing" as overlapping terms and escalates; a clean mark is
  Low; lapsed marks are informational only.

### Task 10: API and page
- `POST /api/check` (requires `consent: true`), `GET /api/picklist/search`, `GET /` static page with consent box,
  results, disclaimers. Register chosen by env (`TM_REGISTER=fixture|ipaustralia`).
- Tests: 422 without consent; happy path; picklist search.

## Phase 2
- Task 11 (**founder**): apply for IP Australia API access (Trade Mark Search API and TMGnS API); then verify the
  field mapping against real responses and record fixtures from them. *Open.*
- Task 12: TMGnS picklist sync (`python -m tm_advisor.picklist_sync`): CSV/JSON/zip, loose column matching,
  inactive and duplicate rows dropped. *Done; check against the first real download.*
- Task 13: Manual ingestion (`python -m tm_advisor.manual crawl`): robots.txt, 1 request/second, pages kept as
  JSON lines, split by heading into ~350-word chunks with overlap, URL kept. Indexed with SQLite FTS5 (BM25)
  instead of pgvector, see design §4.3. *Done; run on the founder's PC (the cloud dev environment can't reach
  manuals.ipaustralia.gov.au).*
- Task 14: explanation layer (`POST /api/explain`, page button): findings + retrieved chunks to Claude with a
  JSON schema; citations not in the retrieved set and conflicts not in the report are dropped; refusals, missing
  keys and API errors become a friendly message while the check still works. *Done.*
- Also: mark similarity now spots a distinctive word inside the other mark when extra words are added
  ("Best EcoKnit" vs ECO KNITWEAR).
- Headstart-style flow (kind of mark → goods & services → check → summary), "describe your business" search,
  picklist from the public classification search (`picklist_site`). *Done.*
- Data freshness: `python -m tm_advisor.refresh` refreshes the picklist and the Manual; keeps the current copy if a
  download looks incomplete (< 70% of the previous size); reports terms/pages added, removed, changed; the server
  reloads new data live; the page shows data dates; Manual "Date Published" is kept and shown with citations;
  weekly Windows scheduled task. *Done.*
- Next: an evaluation set of real examination outcomes to measure the screen and the explanations before launch.

## Phase 3
- Task 15: Examination report helper.

## Phase 4 (after legal advice, design §7)
- Accounts, saved checks, payments, attorney referral with per-report consent.
