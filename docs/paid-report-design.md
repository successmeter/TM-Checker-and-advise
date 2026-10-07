# TM Advisor: Paid report design

Status: decisions recorded (§11); nothing here is built yet. Legal points are not legal advice; see §10.
Working business name: **Trademark Advisor** (to be registered). Payments are taken by **Success Meter Pty Ltd**
through its Stripe account.

## 1. Goal

Keep the check free. Sell a full, written report for **A$299 (GST inclusive)** that tells a founder which route
gives them the best chance (word mark, composite mark, logo mark, a different name, or narrower goods) and
exactly what to file. Payments go through the founder's existing Stripe account.

What the customer is buying: a dated, specific, plain-English filing plan for *their* mark and *their* goods and
services, built from the live register, IP Australia's picklist and the Trade Marks Manual, that they can act on
themselves through TM Headstart or a standard application.

## 2. Free vs paid

| | Free check | Paid report (A$299) |
|---|---|---|
| Kind of mark, goods & services search, picklist | ✓ | ✓ |
| Overall risk level | ✓ | ✓ |
| Which areas raised concerns (distinctiveness, similar marks, wording) | ✓ as counts only | ✓ in full |
| Recommended route (word / composite / logo / new name / narrower goods) | — | ✓ with full reasoning |
| Similar marks | How many need attention | Every mark, with images, status, owner, why it's similar, overlapping goods, and what to do about each |
| Distinctiveness | Concern or not | Full section 41 assessment of the whole mark: meaning, affected terms, options |
| Goods & services | Picklist yes/no | Recommended specification, ready to paste; terms to drop or narrow (Manual Part 27.3) and why; fee impact |
| Composite / logo guidance | One line | What the design must do to carry descriptive words; what a composite does and doesn't protect |
| Explanation with Trade Marks Manual citations | — | ✓ |
| Filing guide | — | Step-by-step for TM Headstart and standard filing, fees for their classes, what to do with an adverse Headstart report |
| PDF, dated register snapshot | — | ✓ |
| Their own logo in the report (uploaded) | — | ✓ |
| Re-check within 30 days after changing the name or goods | — | ✓ (one free re-run) |

Rule for the free tier: enough to show the problem is real and that the report answers it, never enough to
file from. The free check must stay honest: if the free check shows High risk, the free headline says so. No
attorney review or attorney service is offered (decision §11).

## 3. Customer journey

1. Customer runs the free check (unchanged flow: kind → goods & services → check).
2. Below the free results, a **report preview**: the report's table of contents with the sections they'd get,
   which sections apply to them (e.g. "3 similar marks need attention", "your phrase is likely to be seen as
   descriptive"), a sample page, price, and what's not included (not legal advice, no filing on their behalf).
3. **Get my report — A$299**: customer enters their email, optionally uploads their logo (PNG/JPG/SVG, up to
   5 MB, for composite and logo marks), and ticks the terms checkbox (terms, refund policy, not legal advice).
4. Server creates an *order* (status `pending`) from the application details it holds, not from anything the
   browser computed, and redirects to **Stripe Checkout** (hosted page; card details never touch our server).
5. Stripe redirects back to `/report/{order_id}?t={token}` showing "Preparing your report…".
6. Stripe sends `checkout.session.completed` to our **webhook**; signature verified; order → `paid`.
7. A background job re-runs the full check on the live register, runs the Claude assessments at higher effort,
   builds the report, renders the PDF, stores both, order → `ready`.
8. The report page shows the report and a PDF download. An email with the private link is sent.
9. The customer can come back through the emailed link. "Lost your link?" sends links for every report on that
   email address.

The success redirect is never trusted to mark an order paid; only the verified webhook does.

## 4. The report

Generated once, at payment time, and **frozen**: the PDF states the date and time the register was searched, so
later register changes don't silently alter what was sold.

Sections:
1. **Summary**: mark, kind, classes, overall risk, recommended route in one paragraph, top three actions.
2. **Recommended route**: word / composite / logo / different name / narrower goods, with reasoning tied to the
   findings (section 41 vs section 44), what the chosen route protects and what it doesn't.
3. **Distinctiveness (section 41)**: meaning of the whole mark, each affected term, options, Manual citations.
4. **Similar marks (section 44)**: every relevant mark: image, number (linked), status, owner, classes, why
   similar, overlapping goods, whether narrowing helps, whether it's lapsing or renewable.
5. **Your goods and services**: recommended specification per class, ready to paste into Headstart; terms
   removed or narrowed and why; picklist status and fee effect; industry limitation wording where it helps.
6. **Composite and logo guidance** (when relevant): what the design must contribute; the logo-only caveat.
7. **How to file**: TM Headstart steps, the 5-business-day amendment window, Part 1/Part 2 fees for their
   classes; standard application alternative; what to do with an adverse Headstart report.
8. **When to get an attorney**: the escalation reasons, if any, stated plainly.
9. **About this report**: data sources and dates, method, limitations, not legal advice, no guarantee.

Claude writes sections 1–3 and the narrative parts of 4–8 from the findings only (it cannot add or change
conflicts or risk levels, as today), with Manual citations kept only when retrieved. Everything else is
deterministic.

## 5. Architecture

```
browser ──► FastAPI app ──► IP Australia API (register)      Stripe Checkout (hosted)
              │   │                                              │
              │   └─► Anthropic API (assessments, report text)   │ webhook
              │                                                  ▼
              ├─► orders/reports DB  ◄──────────────  /api/stripe/webhook
              ├─► report worker (thread/queue) ──► PDF renderer ──► file storage
              └─► email provider (report links)
```

New modules (Python, same app):

| Module | Job |
|---|---|
| `tm_advisor/store.py` | Orders and reports in SQLite (one server) with a path to Postgres. |
| `tm_advisor/payments.py` | Create Checkout Sessions; verify and handle webhooks; idempotent. Uses the official `stripe` library. |
| `tm_advisor/report/build.py` | Assemble the full report data from a check + Claude sections. |
| `tm_advisor/report/render.py` | HTML template → PDF. |
| `tm_advisor/report/worker.py` | Background generation with retries; order state machine. |
| `tm_advisor/mailer.py` | Send report links through **Resend** (API key in env vars; sending domain verified with SPF/DKIM). |
| `tm_advisor/static/report.html` | Report page (same design as the PDF). |

Order states: `pending` → `paid` → `generating` → `ready` (or `failed` → retried → staff alert). Refunds:
`refunded` (report stays accessible; no automatic revoke).

### 5.1 Data model

`orders`: id (random), access token hash, email, application JSON (mark, kind, applicant, classes, industry),
price, currency, Stripe Checkout Session id, Stripe Payment Intent id, status, created/paid/ready timestamps.
`reports`: order id, report JSON (frozen), PDF path, register searched at, model used, version of the report
template.

Stored: what's needed to produce and re-send the report, and the customer's uploaded logo (shown in the report;
type and size checked on upload, SVG with scripts refused, never shared; deleted with the order on request). Not stored: card
details (Stripe holds them).

### 5.2 Stripe

- One Product "Trade mark filing report", one Price A$299, `tax_behavior` inclusive.
- Checkout Session per order: `mode=payment`, `customer_email`, `metadata.order_id`, `client_reference_id`,
  success/cancel URLs; invoice/receipt by Stripe.
- Webhook endpoint `/api/stripe/webhook` with the signing secret; handle `checkout.session.completed` (and
  `checkout.session.async_payment_succeeded` if delayed methods are enabled), `charge.refunded`.
- Idempotency: the order id is the key; a repeated event is a no-op.
- Test mode end-to-end first (Stripe test cards, Stripe CLI to forward webhooks locally).
- GST: register for GST when turnover reaches A$75k (or earlier by choice); price shown GST-inclusive; Stripe Tax
  or a fixed inclusive price with Stripe's tax invoice settings. Confirm with an accountant.
- Keys: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID` in environment variables, never in code.

### 5.3 Access to reports

No passwords in v1. Each order has a long random token; the link `/report/{id}?t={token}` opens it (the token is
stored hashed). "Lost your link" emails all links for that address. Accounts can come later if customers ask.

### 5.4 PDF

Render the same HTML template as the report page to PDF on the server (WeasyPrint, or headless Chromium, which
the project already uses for the picklist copier). A4, page numbers, the register snapshot time in the footer.

## 6. Hosting

The app runs on the founder's PC today. Selling requires a public server that is always on (Stripe webhooks,
background data refresh) and has a persistent disk (database, data files, logos, PDFs). The Social Media Suite
runs on Laravel Cloud, which only runs PHP, so this Python app needs its own small host. Lowest-cost options
(prices approximate; check current pricing):

| Option | Cost | Notes |
|---|---|---|
| Oracle Cloud Always Free VM, Sydney region | Free | Generous (ARM, several GB RAM). Sign-up needs a card; free capacity is sometimes unavailable. **Start here for staging.** |
| Small Sydney VPS (Vultr, DigitalOcean, AWS Lightsail) | ~A$7–10/month | Simple and reliable. **Recommended for production.** |
| Free tiers of Render / Fly.io / Railway | Free–A$8 | Free tiers sleep when idle and have no persistent disk: not suitable. |

Deployment on either VM: Docker Compose with the app and Caddy (automatic HTTPS), data folder on the host disk,
nightly backup of the database, logos and reports to object storage, error alerts and an uptime check. The same
setup moves between hosts unchanged.

## 7. Abuse and cost controls (free tier)

The free check costs a few cents in Claude calls. Protect it with: per-IP and per-email rate limits, a
bot check (e.g. Cloudflare Turnstile) before the check runs, caching of identical checks (already in place), and
a monthly Anthropic spend limit. IP Australia API limits apply too; caching helps.

## 8. Privacy

Collects: email, mark, applicant name (optional), goods and services, payment status. Publish a privacy policy
(what's collected, why, where it's stored, retention, deletion on request). Store data in Australia where
practical. Don't send personal data to Claude beyond the mark, goods and services and applicant name.

## 9. Quality before launch

- An evaluation set of real outcomes (TM Headstart and examination reports, e.g. SUCCESS METER → section 41
  adverse) to measure the free check and the report's route recommendation. Target: route matches the real
  outcome in most cases, and never recommends "add a logo" for a section 44 conflict.
- A manual review of the first 20 paid reports before they're released (a review queue switch), then spot checks.

## 10. Legal (get advice before charging)

Not legal advice; these are the questions to put to an Australian IP lawyer or trade marks attorney:
1. **Trade marks work for gain (Trade Marks Act s156):** does a paid, tailored report on registrability and what
   to file amount to work reserved for registered attorneys? Options: attorney review and sign-off of each paid
   report (a selling point), or positioning and wording as an information product, confirmed by the lawyer.
2. **Australian Consumer Law:** claims about chances and outcomes; the refund policy and Headstart promise (§12)
   (consumer guarantees apply regardless).
5. **Business name:** register "Trademark Advisor" with ASIC before trading under it. The name is descriptive and
   "Advisor" may suggest professional advice; ask whether it's suitable given s156, and check it with the tool.
3. **Terms of service, refund policy, privacy policy** wording.
4. **Professional indemnity insurance**, if the attorney-review model is used.

Go-live is blocked on this advice (plan task 4.12).

## 11. Decisions

| Question | Decision |
|---|---|
| Free vs paid | Free check: overall risk and which areas raised concerns. Recommended route and everything else: paid. |
| Attorney review | Not offered at launch. |
| Refund policy | Agreed as in §12; final wording after legal advice. |
| Hosting | Own small host (the Social Media Suite is on Laravel Cloud, PHP only): Oracle Always Free for staging, a ~A$7–10/month Sydney VPS for production (§6). |
| Email | Resend. |
| Names | Brand: Trademark Advisor (working name, to be registered). Stripe and invoices: Success Meter Pty Ltd. |
| Logo upload | Yes, for composite and logo marks, shown in the report. |

## 12. Refund policy (agreed; final wording after legal advice)

A refund "if not happy with the outcome after lodging" was considered and not recommended: examination takes
months and registration at least 7.5 months, the outcome depends on things the report doesn't control (what is
actually filed, later filings, oppositions), "not happy" is open-ended, and it reads as an outcome guarantee.
Instead:
1. **14-day refund before lodging**, no questions asked.
2. **Headstart promise:** if the customer files the report's recommended route and goods and services exactly
   through TM Headstart within 30 days, and the Headstart assessment is adverse on a ground the report rated
   Low risk, full refund on sending the Headstart letter. Headstart answers in about 5 business days, so this is
   quick, objective and checkable.
3. Full refund if the report can't be produced.
Consumer guarantees under the Australian Consumer Law apply in addition. Final wording after legal advice.
