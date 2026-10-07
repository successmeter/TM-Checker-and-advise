# TM Advisor: Paid report design

Status: draft for review. Nothing here is built yet. Legal points are not legal advice; see §10.

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
| Recommended route (headline only) | ✓ | ✓ with full reasoning |
| Similar marks | Count, and the top 3 with risk level | Every mark, with images, status, owner, why it's similar, overlapping goods, and what to do about each |
| Distinctiveness | Pass / concern | Full section 41 assessment of the whole mark: meaning, affected terms, options |
| Goods & services | Picklist yes/no | Recommended specification, ready to paste; terms to drop or narrow (Manual Part 27.3) and why; fee impact |
| Composite / logo guidance | One line | What the design must do to carry descriptive words; what a composite does and doesn't protect |
| Explanation with Trade Marks Manual citations | — | ✓ |
| Filing guide | — | Step-by-step for TM Headstart and standard filing, fees for their classes, what to do with an adverse Headstart report |
| PDF, dated register snapshot | — | ✓ |
| Re-check within 30 days after changing the name or goods | — | ✓ (one free re-run) |

Rule for the free tier: enough to show the problem is real and that the report answers it, never enough to
file from. The free check must stay honest: if the free check shows High risk, the free headline says so.

## 3. Customer journey

1. Customer runs the free check (unchanged flow: kind → goods & services → check).
2. Below the free results, a **report preview**: the report's table of contents with the sections they'd get,
   which sections apply to them (e.g. "3 similar marks need attention", "your phrase is likely to be seen as
   descriptive"), a sample page, price, and what's not included (not legal advice, no filing on their behalf).
3. **Get my report — A$299**: customer enters their email and ticks the terms checkbox (terms, refund policy,
   not legal advice).
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
| `tm_advisor/mailer.py` | Send report links (provider API, e.g. Postmark or Resend). |
| `tm_advisor/static/report.html` | Report page (same design as the PDF). |

Order states: `pending` → `paid` → `generating` → `ready` (or `failed` → retried → staff alert). Refunds:
`refunded` (report stays accessible; no automatic revoke).

### 5.1 Data model

`orders`: id (random), access token hash, email, application JSON (mark, kind, applicant, classes, industry),
price, currency, Stripe Checkout Session id, Stripe Payment Intent id, status, created/paid/ready timestamps.
`reports`: order id, report JSON (frozen), PDF path, register searched at, model used, version of the report
template.

Stored: what's needed to produce and re-send the report. Not stored: card details (Stripe holds them), logo
images unless the customer chooses to include their logo in the report.

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

The app runs on the founder's PC today. Selling requires a public server:
- **Option A (recommended to start):** a managed container host with a Sydney region and a persistent disk
  (e.g. Fly.io or Render), about A$15–40/month. Data files (picklist, Manual index, wording list) live on the
  disk; the existing automatic refresh keeps them current.
- **Option B:** AWS (App Runner/ECS + RDS + S3, Sydney). More moving parts; worth it at higher volume.
- Domain + HTTPS, environment secrets, daily backups of the database and report files, error alerts (Sentry or
  similar), uptime check.

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
2. **Australian Consumer Law:** claims about chances and outcomes; refund policy (consumer guarantees apply).
3. **Terms of service, refund policy, privacy policy** wording.
4. **Professional indemnity insurance**, if the attorney-review model is used.

Go-live is blocked on this advice (plan task 4.12).

## 11. Open decisions for the founder

1. Attorney review: included in A$299, an optional add-on, or not offered?
2. Refund policy: e.g. full refund if the report can't be produced; otherwise within 7 days if not downloaded?
3. Hosting: Option A or B (§6)?
4. Email provider and the "from" address/domain.
5. Business entity for Stripe, GST registration status, and the name on the report.
6. Whether customers can upload their logo for inclusion in the report.
