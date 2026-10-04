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

## Phase 2 (next)
- Task 11: apply for IP Australia API access; verify field mapping against real responses; record fixtures.
- Task 12: TMGnS picklist sync script (full picklist to `data/picklist.json`).
- Task 13: Manual ingestion (crawl manuals.ipaustralia.gov.au politely, chunk by Part/section, keep URL) into
  pgvector.
- Task 14: LLM explanation layer: input = deterministic findings + retrieved Manual chunks; output must cite chunks;
  refuses to change the risk band.

## Phase 3
- Task 15: Examination report helper.

## Phase 4 (after legal advice, design §7)
- Accounts, saved checks, payments, attorney referral with per-report consent.
