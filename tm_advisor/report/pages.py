"""Small pages around the report: preparing, problems, and the free-check summary sent to the browser."""

import html

STATUS_TEXT = {
    "pending": ("Confirming your payment…", "This usually takes a few seconds."),
    "paid": ("Preparing your report…", "We're searching the register and writing your report. This takes a minute or two."),
    "generating": ("Preparing your report…", "We're searching the register and writing your report. This takes a minute or two."),
    "review": ("Your report is being checked", "A person checks each report before it's released. We'll email you the "
                                                "link as soon as it's ready."),
    "failed": ("Your report is taking longer than usual", "We're on it and will email you the link as soon as it's ready."),
}


def status_page(order_id: str, status: str, email: str) -> str:
    title, detail = STATUS_TEXT.get(status, ("Preparing your report…", ""))
    refresh = '<meta http-equiv="refresh" content="5">' if status in ("pending", "paid", "generating") else ""
    return f"""<!doctype html><html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{refresh}<title>{html.escape(title)}</title>
<style>body{{margin:0;font:16px/1.5 system-ui,"Segoe UI",Roboto,sans-serif;background:#f3f1f5;color:#1c1b1f}}
main{{max-width:560px;margin:12vh auto;background:#fff;border-radius:12px;padding:28px 24px;box-shadow:0 1px 3px #0001}}
h1{{font-size:22px;margin:0 0 8px}} .muted{{color:#5d5a63}}</style></head>
<body><main><p class="muted">Trademark Advisor · Report {html.escape(order_id)}</p><h1>{html.escape(title)}</h1>
<p>{html.escape(detail)}</p><p class="muted">We'll also email the link to {html.escape(email)}. Keep that email: the
link is private and is how you open your report again.</p></main></body></html>"""
