"""Report emails through Resend (https://resend.com). Settings in environment variables:

  RESEND_API_KEY   re_...
  TM_EMAIL_FROM    e.g. "Trademark Advisor <reports@your-domain>" (the domain must be verified in Resend)

Without an API key the email is written to the server log instead, so everything works in development.
"""

import html
import logging
import os
from dataclasses import dataclass

import httpx

log = logging.getLogger("uvicorn.error")
RESEND_URL = "https://api.resend.com/emails"


@dataclass
class Mailer:
    api_key: str = ""
    sender: str = "Trademark Advisor <onboarding@resend.dev>"
    http: httpx.Client | None = None

    @classmethod
    def from_env(cls) -> "Mailer":
        return cls(api_key=os.environ.get("RESEND_API_KEY", "").strip(),
                   sender=os.environ.get("TM_EMAIL_FROM", "").strip() or cls.sender)

    def send(self, to: str, subject: str, text: str, html_body: str) -> bool:
        if not self.api_key:
            log.info("Email not sent (no RESEND_API_KEY). To %s: %s\n%s", to, subject, text)
            return False
        http = self.http or httpx.Client(timeout=20)
        try:
            response = http.post(RESEND_URL, headers={"Authorization": f"Bearer {self.api_key}"},
                                 json={"from": self.sender, "to": [to], "subject": subject, "text": text,
                                       "html": html_body})
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            log.warning("Email to %s failed: %s", to, e)
            return False

    def report_ready(self, to: str, mark: str, links: list[tuple[str, str]]) -> bool:
        """links: (label, url) pairs, one per report."""
        lines = "\n".join(f"{label}: {url}" for label, url in links)
        items = "".join(f'<li><a href="{html.escape(url)}">{html.escape(label)}</a></li>' for label, url in links)
        single = len(links) == 1
        subject = f"Your trade mark report for {mark}" if single else "Your trade mark reports"
        text = (f"Your Trademark Advisor report{'' if single else 's'}:\n\n{lines}\n\n"
                "Keep this email: the link is private and is how you open your report again.\n\n"
                "This report is general information produced by software, not legal advice.")
        body = (f"<p>Your Trademark Advisor report{'' if single else 's'}:</p><ul>{items}</ul>"
                "<p>Keep this email: the link is private and is how you open your report again.</p>"
                '<p style="color:#666;font-size:12px">This report is general information produced by software, '
                "not legal advice.</p>")
        return self.send(to, subject, text, body)
