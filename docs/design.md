# TM Advisor: Design

Status: **draft**, from a review of the founder's brainstorm (with Gemini) on 2026-10-04.
Working name: **TM Advisor** (a "brand filing check", never an "attorney").

## 1. Problem

Australian founders pay a trade marks attorney $1,500 to $3,000+ to file a simple mark, mostly for three things:
picking classes and goods/services wording, checking the register for conflicts, and replying to an
examination report. IP Australia already gives away some of this (TM Checker, TM Headstart, the picklist,
the Manual), but the pieces are scattered and written for examiners. TM Advisor puts them in one flow,
explains the result in plain English, and tells the founder when the situation is serious enough to pay
an attorney.

## 2. What the brainstorm got right, and what it got wrong

Kept:
- Use the official register (Australian Trade Mark Search API), the goods & services picklist and the
  Trade Marks Manual of Practice and Procedure as the sources of truth.
- Deterministic checks first, an LLM only to explain, grounded in Manual passages (RAG) with citations.
- Mandatory disclaimers, active consent, a "talk to an attorney" escape hatch.

Corrected:

| Brainstorm said | Reality | Design consequence |
|---|---|---|
| "Integrate with TM Checker's API" | TM Checker has no public API. The **Australian Trade Mark Search API** (quick search + get by number) and the **TMGnS** picklist API exist, behind manual approval on IP Australia's API portal, with OAuth2 client credentials. | Register access sits behind an interface. A fixture register drives dev and tests until access is approved. |
| Exclusions ("all of the foregoing excluding sweaters") get you past s44 | s44 is about marks that are substantially identical or deceptively similar **and** goods that are the same, of the same description, or closely related. Excluding the exact cited goods while keeping "clothing" usually leaves goods of the same description, so the objection stays. | The engine says *which* of your terms create the overlap and whether dropping them could plausibly clear it. If the overlap is broad, it says so and escalates instead of producing a cosmetic exclusion string. |
| Add picklist terms to fix a s41 (distinctiveness) problem | s41 is about the **mark** versus its goods. Adding goods does not make a descriptive mark distinctive. Narrowing helps only when the mark is descriptive of some goods and not others. | s41 output flags descriptive words and suggests changing the mark or getting evidence of use, not padding the spec. |
| "87% probability of objection" | No data supports a calibrated probability. | Risk bands (Low / Medium / High) with the reasons that produced them. |
| Risk is "Legal Practice Boards" | The sharper risk is the Trade Marks Act: only registered attorneys may hold themselves out as trade marks attorneys/agents (s156), and "trade marks work" (preparing applications or documents under the Act **on behalf of someone else, for gain**) is reserved. | The founder fills in and files their own application; TM Advisor informs, it never files or drafts *for* them. Get advice from an IP lawyer on the paid model **before charging** (see §7). |
| Celery, HMAC webhooks to law firms, Stripe, 4 pricing tiers | Not needed to learn whether founders want this. | Deferred. MVP is one stateless service. |

## 3. Scope

MVP (Phase 1, built here):
1. Input: mark text, and per class a list of goods/services terms.
2. **Picklist check**: each term is matched against the picklist; non-picklist terms get the closest picklist
   suggestions and the fee note (picklist-only applications are cheaper than bespoke ones).
3. **Conflict check (s44 screen)**: search the register, score each live mark for mark similarity and goods
   relationship, band the risk, list the user terms causing each overlap.
4. **Distinctiveness screen (s41)**: flag mark words that describe the user's own goods or are common laudatory or
   descriptive words. Word lists can't judge what a *phrase* means, so when an Anthropic API key is set, Claude
   also applies the examiner's two-part test to the whole mark against the chosen goods and services (ordinary
   signification + other traders' need) and returns likely / possible / unlikely, the meaning, affected terms and
   options. A likely objection makes a word mark High risk and escalates (Medium for a logo). Real-world case
   behind this: TM Headstart refused SUCCESS METER for business data analysis, consultancy and SaaS under s41
   ("a quantifiable standard used to measure whether a goal ... has been achieved"), which the word lists missed.
5. **Escalation**: explicit "speak to an attorney" triggers (identical mark + same goods, broad overlap that
   narrowing cannot fix, a wholly descriptive mark).
6. Web page with active consent and in-line disclaimers; JSON API.

Phase 2: Manual search + LLM explanations with Manual citations (built, §4.3); live IP Australia client switched
on with real credentials; full picklist sync from TMGnS (built, awaiting API access).
Phase 3: **Examination report helper**: paste an adverse report, get the cited sections explained, the
options the Manual allows (amend spec, arguments, evidence of use, s44(3) honest concurrent use, etc.) and a
"do this yourself / see an attorney" call.
Phase 4: accounts, saved checks, payments, attorney referral (only after the legal advice in §7).

## 4. Architecture

```
Browser (static page)  ──>  FastAPI  ──>  analysis.check(application)
                                            ├─ picklist.Picklist      (local JSON, synced from TMGnS)
                                            ├─ register.RegisterClient (Fixture | IpAustralia)
                                            ├─ mark_similarity        (string, phonetic, containment)
                                            ├─ goods_similarity       (same class, term overlap, related classes)
                                            └─ distinctiveness        (s41 heuristics)
                                         ──> Report (risk band, findings, suggestions, escalation, disclaimers)
```

Python 3.11 + FastAPI + Pydantic. No database server: the Manual index is a local SQLite file (§4.3).

### 4.1 Register access
`RegisterClient.search(mark_text, classes) -> list[RegisterMark]`.
- `FixtureRegisterClient` reads `data/register_fixture.json`.
- `IpAustraliaRegisterClient` gets a token by client credentials, runs `POST /search/quick` for the mark and its
  words, then `GET /trade-mark/{number}` for each hit. Base URL, token URL and credentials come from env. The
  response field mapping lives in one function and must be checked against a real response once access is
  granted (the public docs do not show the full schema).

### 4.2 Scoring
Mark similarity (0..1) is the max of: exact match on the squashed form, normalised edit similarity, phonetic-key
equality, and containment (one mark's distinctive element inside the other). Each contributes a human-readable
reason.

Goods relation per class: `same` (a user term overlaps a cited term), `related` (same class, no term overlap; or a
curated closely-related class pair such as 25/35 retail of clothing, 9/42 software), `none`.

Band: High = mark ≥ 0.85 and goods `same`; Medium = mark ≥ 0.85 and `related`, or mark ≥ 0.7 and `same`; Low
otherwise. Only live marks (registered, accepted, pending) count; lapsed and removed marks are listed as
information.

### 4.3 Manual search and explanations (Phase 2)
The Manual is downloaded politely (robots.txt, one request per second), split by heading into ~350-word chunks
that keep their Part title, heading and URL, and indexed with SQLite's built-in full-text search (BM25).
Keyword search replaces the pgvector plan: the Manual's vocabulary ("deceptively similar", "goods of the same
description", "inherently adapted to distinguish") is exactly what the findings contain, it needs no embedding
service or database server, and it runs on a founder's Windows PC. Revisit embeddings if evaluation shows
missed passages.

`POST /api/explain` runs the check, builds search queries from the findings (one per Medium/High conflict, one
for distinctiveness flags), and sends the findings plus up to eight excerpts to Claude (default
`claude-opus-5-5`, medium effort, server-side refusal fallback) with a JSON schema. The system prompt forbids
changing risk levels or promising outcomes. Afterwards, citations not in the retrieved set and conflicts not in
the report are discarded. Failures (no key, refusal, API error) return the report with a plain message instead
of an explanation.

## 5. Output contract

`Report { mark, overall_risk, conflicts[], picklist[], distinctiveness[], escalate, escalation_reasons[],
disclaimers[] }`. Each conflict carries the cited mark, its number, status, owner, classes, the score, the reasons,
the user terms causing overlap and a plain-English option ("If you don't sell X, leaving it out removes this
overlap") or "narrowing is unlikely to help".

## 6. Testing

Unit tests per module, an analysis test on the fixture register (the EcoKnit / ECO KNITWEAR example from the
brainstorm), and API tests with FastAPI's TestClient. IP Australia is never called in tests; its client takes an
injectable `httpx` transport.

## 7. Legal guardrails (not legal advice; confirm with an IP lawyer)
- Never call the product or its output an attorney, agent, lawyer, legal advice or a clearance search.
- The user chooses every term and files the application themselves. TM Advisor does not lodge, sign or submit.
- Before charging money, get a written view from an Australian IP lawyer on whether paid, tailored
  recommendations amount to "trade marks work ... for gain". A common safe structure is a partnership where a
  registered attorney supervises the paid tier.
- Disclaimers: global notice, unticked consent box before every check, in-line notes beside suggestions.
- Privacy: Phase 1 stores nothing. Any later attorney handoff needs explicit per-report consent.

## 8. Open questions
1. IP Australia API access: apply on the developer portal (manual approval). Who is the applicant entity?
2. ~~LLM provider for Phase 2~~: Claude via the Anthropic API.
3. ~~Separate repository~~: successmeter/tm-checker-and-advise.
