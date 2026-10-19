# BizImprint: risk assessment

Prepared 19 October 2026 from the product as built (branch `claude/nifty-heisenberg-9e7hkp`), the founder's
ChatGPT research, and spot checks of that research. **Not legal advice**: this is the brief to take to an Australian
trade marks lawyer before launch.

## 1. Verdict

The product is viable, but **as built it sits in the most sensitive part of the spectrum**: a paid, personalised
report that tells a named person which route to file, rates their chances, and gives wording "ready to paste". The
search, retrieval and explanation parts are low risk. The **recommendation and the price tag together** are what
need a lawyer's sign-off and, most likely, a change in wording and structure before launch.

Biggest risks, in order:
1. **Reserved "trade marks work" and unqualified legal practice** (§3.1). Paid, tailored registrability advice may
   be work only registered trade marks attorneys or lawyers can do for others.
2. **Consumer law** (§3.2): risk levels, "likely objection", the TM Headstart promise and the name "Advisor" all
   create impressions the product must be able to back up.
3. **Value against free and cheap official tools** (§5): TM Checker is free and AI-assisted; TM Headstart gives an
   actual examiner's view for A$200 per class. A$299 needs a clear reason to exist.
4. **Accuracy** (§3.4): the first real report recommended the wrong route (own application cited) until fixed.
   There is no evaluation set yet.

## 2. Checking the research

| Claim in the research | Status | Notes |
|---|---|---|
| IP Australia's TM Checker is free and AI-assisted (similarity and distinctiveness), and its results don't guarantee outcomes | **Confirmed** | Live since 2022; about 760,000 checks to mid-2025; also part of TM Headstart. |
| Professional clearance searches cost far more | **Confirmed** | Published law-firm prices of roughly A$500–1,050 + GST per search; full clearance about A$2,000–3,000. |
| Trade Marks Act controls attorney work | **Partly confirmed** | s156: offence to describe yourself or hold yourself out as a trade marks attorney if not registered. "Trade marks work" is defined in s157A(8); its exact wording couldn't be read here. Have the lawyer confirm whether a paid registrability report and drafted specification for a customer fall within it. |
| State legal-profession laws prohibit unqualified legal practice | **Plausible, not checked** | The Legal Profession Uniform Law (NSW, Vic, WA) prohibits unqualified entities engaging in legal practice. Whether automated, personalised registrability guidance is "legal practice" is the core question for the lawyer. |
| Markster, brandU Legal, Signify IP as Australian competitors; Markster A$1,185 per class | **Not confirmed** | Searches found no trace of Markster or brandU Legal. Verify before using in any pitch. |
| IP Australia bulk data A$1,200; API terms allow derivatives | **Not confirmed** | Couldn't reach IP Australia's terms from here. Also check **IPGOD** (IP Government Open Data), which is free but periodic, not live. |
| Suggested pricing A$29–99 | **Opinion** | Not market data. See §5. |

## 3. Risk register

Likelihood and impact: H/M/L. "Today" says where the product stands now.

### 3.1 Regulated professional work

| # | Risk | Today | L | I | Mitigation |
|---|---|---|---|---|---|
| R1 | A paid, personalised registrability recommendation is "trade marks work" done for another person for gain | Report says "File as a composite mark", rates objections "likely", gives a filing plan; A$299 | M–H | H | Legal opinion **before charging**. Options: (a) reword outputs as research and options, not instructions (§4); (b) have a registered attorney supervise or sign off the paid tier; (c) both. |
| R2 | Drafting the goods and services specification "ready to paste" is preparing documents for a filing | Section 5 "Recommended wording, ready to paste" | M | M | Present it as *the customer's own selected terms, checked against the picklist*, not drafted by us. The customer already chooses every term; say so. |
| R3 | Holding out as an attorney or adviser | "advise" in copy (brand was "Trademark Advisor") | M | H | Done: renamed to BizImprint. Never use "attorney", "agent", "legal advice", "clearance". |
| R4 | Referral fees to attorneys | Not built | L | M | If a referral tier is added, structure fees with legal advice; get consent per report. |

### 3.2 Consumer law (Australian Consumer Law)

| # | Risk | Today | L | I | Mitigation |
|---|---|---|---|---|---|
| C1 | Risk labels read as predictions ("Objection likely", "High risk") | Throughout | M | M | Say what each label is based on and what it doesn't mean (a "confidence boundary" per finding). |
| C2 | TM Headstart promise ties the refund to an examiner outcome, implying we predict outcomes | Refund policy item 2 | M | M | Reconsider with the lawyer; at least word it as a goodwill refund, not an accuracy guarantee. |
| C3 | Disclaimers can't cure an overall misleading impression | Disclaimers present | M | M | Fix the impression itself (wording, name, labels); upgrade the disclaimer (§4.3). |
| C4 | Consumer guarantees (services fit for purpose, due care) can't be excluded | Terms say so | L | M | Keep the wording; limit liability only as far as the law allows; professional indemnity insurance. |
| C5 | Claims in marketing ("file with confidence", "everything you need") | Offer box copy | M | L | Tone down; substantiate any claim with the evaluation set. |

### 3.3 Data and IP

| # | Risk | Today | L | I | Mitigation |
|---|---|---|---|---|---|
| D1 | Trade Mark Search API licence may restrict commercial or customer-facing use, or redistribution | Production API used for paid reports | M | H | Read the current API terms; ask IP Australia in writing whether a paid report built on API data is permitted. |
| D2 | Picklist copied from the class pages by browser automation | `picklist_browser.py`, 143,000 terms | M | M | Confirm the content licence (IP Australia content is often CC BY, but check) and website terms on automated access; attribute. Ask IP Australia for the picklist file or TMGnS access. |
| D3 | Trade Marks Manual crawled and quoted | Excerpts and citations | L | L | Check its licence and attribute; quote briefly with links. |
| D4 | Test environment data is stale and wrong | Warning shown | L | M | Refuse to sell reports when the register is the test environment. |
| D5 | Register data errors or gaps (class "All", missing marks, late updates) | Handled case by case | M | M | Show the search time; state that later filings and unpublished marks aren't covered (done). |

### 3.4 Accuracy and AI

| # | Risk | Today | L | I | Mitigation |
|---|---|---|---|---|---|
| A1 | Wrong route or missed conflict | First real report cited the customer's own mark; fixed | M | H | Evaluation set of real outcomes before launch (plan 4.11); human review of the first 20 reports (`TM_REVIEW_REPORTS=1`). |
| A2 | AI invents facts or citations | Risk levels and conflicts are deterministic; citations limited to retrieved passages | L | M | Keep: Claude never decides risk; drop unknown citations (done). Add spot checks. |
| A3 | Similarity scoring misjudges common words, derived words, logos | Several fixes made (SUCCESS, SUCCESSION) | M | M | Evaluation set; track changes to scoring by version. |
| A4 | Logo marks can't be compared by image | Logo-only path says so | L | M | Keep the explicit limitation; point to image search. |

### 3.5 Privacy and security

| # | Risk | Today | L | I | Mitigation |
|---|---|---|---|---|---|
| P1 | Unlaunched brand names are confidential | Stored with orders | M | M | Privacy policy: purpose, retention period, deletion on request; don't use for anything else. |
| P2 | Overseas disclosure (Anthropic, Stripe, Resend are outside Australia) | Mentioned partly | M | L | List each provider and country in the privacy policy (APP 8), even if the small-business exemption applies. |
| P3 | Report link leaks | HMAC links; no login | L | M | Links are long and unguessable; add expiry or re-send options if needed; back up `secret.key`. |
| P4 | Abuse of the free check (Claude and IP Australia costs) | Rate limits | M | M | Bot check (Turnstile) at hosting; monthly Anthropic spend limit. |

### 3.6 Business

| # | Risk | Today | L | I | Mitigation |
|---|---|---|---|---|---|
| B1 | Price vs free TM Checker and A$200 Headstart | A$299 | H | H | Test lower price points and a clear "why us" (§5). |
| B2 | Business name not registered | "BizImprint" chosen | H | M | Register it with ASIC; consider a trade mark application after reviewing IMPRINT and 4IMPRINT (class 42). |
| B3 | Dependence on IP Australia API access | Production access granted | L | H | Keep the terms satisfied; cache sensibly; have a fallback message. |
| B4 | Professional indemnity / liability | None | M | M | PI insurance quote; liability cap in terms (as far as the ACL allows). |

## 4. Recommended product changes

### 4.1 From instruction to options (addresses R1, C1)
- "Recommended route: File as a composite mark" → **"Options worth considering, based on what we found"**, with the
  option that fits the findings first and the reasons, plus what each option protects and doesn't.
- "High / Medium / Low risk" → **"Review priority: High / Medium / Low"**, each with *why it was flagged* and *what
  this doesn't mean* ("This doesn't decide whether your mark can be registered or used").
- "Objection likely" → **"Likely to be raised as an issue (section 41)"** with the same boundary text.
- "What to do next" → **"Things to consider"**; never "you should", "safe", "will be accepted", "no risk".

### 4.2 Specification (R2)
- "Recommended wording, ready to paste" → **"Your goods and services, as you selected them"**, picklist status, and
  *questions to consider* (do you offer this? does it overlap a cited mark?), not rewritten wording.

### 4.3 Disclaimer (C3)
Use a fuller statement on the check page, the offer, the report cover and the terms, for example:
> This tool provides automated research and decision-support information based on publicly available Australian
> trade mark data and IP Australia materials. It does not provide legal advice, a legal opinion, or a determination of
> whether a trade mark is registrable or infringes another person's rights. Results are indicative only and may be
> incomplete or inaccurate. For advice on your circumstances, consult a registered Australian trade marks attorney or
> lawyer.

### 4.4 Structure (R1, B1)
- Free: search results with marks, classes, status and owners (closer to ATMS and TM Checker), plus where the
  concerns are.
- Paid: the research report (explanations, goods and services analysis, Manual citations, options).
- Optional: **attorney review** through a partner, which is also the cleanest answer to R1.

### 4.5 Operations
- Refuse paid reports on the test register (D4).
- Evaluation set and human review before launch (A1).
- Bot check and spend limit (P4).

### 4.6 Status (19 October 2026)
Done in the product: options instead of instructions (route headlines, "Things to consider", Claude prompt rules),
"Review priority" labels with "what this doesn't mean" boundaries, "Likely to be raised as an issue" for section 41,
the specification shown as the customer's own selected terms with points to think about, the fuller disclaimer on the
check page, offer, report and terms, the Headstart refund worded as a goodwill refund, "research report" instead of
"filing report", and no paid reports while connected to the test register. A test fails if instruction phrases
("you should", "file as", "ready to paste", "safe to", "will be accepted") appear in a report.
Still open: brand name, price, attorney-review tier, bot check, evaluation set, privacy policy detail, legal review.

## 5. Competition and price

- **Free official tools:** ATMS (search), TM Checker (AI similarity and distinctiveness), and TM Headstart (an
  examiner's view for A$200 per class, Part 1).
- **Professional searches:** about A$500–3,000 from law firms and attorneys.
- **Where this product fits:** between the two: faster and cheaper than a professional search, more explanation
  than the free tools. Its strengths today: goods and services search over the full picklist, class-aware conflict
  search, explanations tied to Trade Marks Manual passages, the whole-mark distinctiveness assessment, and the
  composite-mark guidance. It is not a substitute for Headstart's examiner view, and should say so.
- **Price:** A$299 is above Headstart Part 1 for one class. Test, for example, A$79–149 for the report, with an
  attorney-review upgrade at a higher price.

## 6. Questions for the lawyer

1. Does a paid, automated report on registrability, similar marks and filing options, sold to the person filing,
   amount to "trade marks work" (Trade Marks Act s157A) or legal practice under the Legal Profession Uniform Law? Does
   wording it as research and options (§4) change that? Would attorney supervision or sign-off resolve it?
2. Is presenting the customer's own selected goods and services, checked against the picklist, "preparing documents"?
3. Is the brand "BizImprint" and the site copy acceptable (s156 holding out; ACL)?
4. Review the disclaimer, terms, refund policy (especially the TM Headstart promise) and privacy policy.
5. Liability cap and professional indemnity insurance: what's appropriate?
6. Attorney referral or partnership: how to structure fees and consent.

## 7. Sources checked

- IP Australia, TM Checker results news: https://www.ipaustralia.gov.au/news-and-community/news/TM-Checker-results-are-in-its-a-success
- IP Australia, TM Checker: https://ipaustralia.gov.au/trade-marks/search-existing-trade-marks/tm-checker
- APSC, Trade Mark Checker simplifies IP for business: https://www.apsc.gov.au/node/3164
- Gilbert + Tobin, TM Checker and strategy: https://www.gtlaw.com.au/insights/ip-australias-tm-checker-how-to-balance-automation-and-strategy-in-trade-mark-registration
- The Loft Legal, fees: https://theloft.legal/fees
- Trade Marks Act 1995 (compilation, 2019): https://www.legislation.gov.au/C2004A04969/2019-02-24/2019-02-24/text/original/epub/OEBPS/document_1/document_1.html
- IP Australia API terms (portal copy): https://anypoint.mulesoft.com/exchange/portals/ip-australia-3/pages/Terms%20%26%20Conditions/
