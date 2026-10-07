# Paid reports: setup and testing

How to run the paid report flow on your PC in **Stripe test mode** (no real money), then what changes for live.
Design: `paid-report-design.md`. Everything below is set with environment variables; never put keys in code or
send them in chat.

## 1. Install the new parts (once)

```
cd "C:\Users\saura\TM Checker & Advise tool"
git pull --no-edit
py -m pip install -e .
py -m playwright install chromium
```

## 2. Try it without Stripe first

Reports can be produced without payment for testing (never set this on a public server):

```
set TM_DEV_FREE_REPORTS=1
py -m uvicorn tm_advisor.api:app --port 8000
```

Run a check, then "Get my report". You go straight to the report page; it fills in after a minute or two, with a
PDF download. Without a Resend key the "report ready" email is printed in the server window instead.

`set TM_FREE_FULL=1` shows the full check results (as before the paid report) for your own testing.

## 3. Stripe test mode

1. In the Stripe Dashboard switch on **Test mode**. Developers → API keys: copy the **Secret key** (`sk_test_...`).
2. Install the Stripe CLI: from https://github.com/stripe/stripe-cli/releases/latest download the
   `windows_x86_64.zip`, unzip, and put `stripe.exe` in the project folder (it's git-ignored). Then `stripe login`.
3. In a second cmd window, forward Stripe's events to your PC:
   ```
   stripe listen --events checkout.session.completed,checkout.session.async_payment_succeeded,charge.refunded --forward-to localhost:8000/api/stripe/webhook
   ```
   It prints a webhook signing secret (`whsec_...`).
4. In the server window (one line at a time; your own values):
   ```
   set STRIPE_SECRET_KEY=sk_test_...
   set STRIPE_WEBHOOK_SECRET=whsec_...
   set TM_PUBLIC_URL=http://127.0.0.1:8000
   py -m uvicorn tm_advisor.api:app --port 8000
   ```
   (Leave `TM_DEV_FREE_REPORTS` unset.)
5. Run a check, click "Get my report", pay with the test card **4242 4242 4242 4242**, any future expiry, any CVC.
   You're sent back to the report page; it shows "Confirming your payment…" until the webhook arrives, then
   "Preparing your report…", then the report.
6. Refund it in the Dashboard: the order is marked refunded (the report stays available).

Optional: create a Product "Trade mark filing report" with a A$299 GST-inclusive Price and set
`STRIPE_PRICE_ID=price_...`; without it the amount comes from `TM_REPORT_PRICE_CENTS` (default 29900).

## 4. Email (Resend)

1. Create a Resend account, add and verify your sending domain (DNS records), create an API key.
2. `set RESEND_API_KEY=re_...` and `set TM_EMAIL_FROM=Trademark Advisor <reports@your-domain>`.

## 5. Looking after orders

```
py -m tm_advisor.orders list
py -m tm_advisor.orders link TA-XXXXXXXX
py -m tm_advisor.orders approve TA-XXXXXXXX
```

With `TM_REVIEW_REPORTS=1`, finished reports wait for `approve` before the customer sees them (recommended for
the first 20). Failed reports are retried automatically when the server restarts.

## 6. All settings

| Variable | What it's for |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe secret key (`sk_test_` in test mode, `sk_live_` when live). Without it, ordering is switched off. |
| `STRIPE_WEBHOOK_SECRET` | Signing secret of the webhook endpoint `/api/stripe/webhook`. |
| `STRIPE_PRICE_ID` | Optional Price for the report. |
| `TM_REPORT_PRICE_CENTS` | Price when no Price id is set (default 29900 = A$299). |
| `TM_PUBLIC_URL` | The site's address, used in report links and Stripe return links. |
| `TM_SECRET` | Secret for private report links. If unset, one is created in `data/secret.key`: back it up; changing it breaks existing links. |
| `RESEND_API_KEY`, `TM_EMAIL_FROM` | Report emails. |
| `TM_REVIEW_REPORTS=1` | Hold reports for approval. |
| `TM_DB`, `TM_REPORTS_DIR` | Where orders and PDFs are kept (default `data/`). |
| `TM_CHROMIUM_PATH` | Chromium to use for PDFs, if not Playwright's own. |
| `TM_DEV_FREE_REPORTS=1` | Testing only: reports without payment. |
| `TM_FREE_FULL=1` | Testing only: full check results instead of the free summary. |

## 7. Going live (plan task 4.12)

Legal advice reflected in `/terms` (remove the draft banner) and the report wording; business name registered;
Stripe live keys and a live webhook endpoint (`https://<your-domain>/api/stripe/webhook`, events
`checkout.session.completed`, `checkout.session.async_payment_succeeded`, `charge.refunded`); hosting per
`paid-report-design.md` §6; backups of `data/` (orders, PDFs, secret.key).
