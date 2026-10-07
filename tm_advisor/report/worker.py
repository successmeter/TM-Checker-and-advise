"""Produces a paid report in the background: check → report → PDF → email (design §3, §5).

Runs in a small thread pool inside the server. Unfinished orders are picked up again when the server starts. With
TM_REVIEW_REPORTS=1 finished reports wait for a person to approve them (py -m tm_advisor.orders approve ...) before
the customer can see them.
"""

import base64
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from ..mailer import Mailer
from ..models import Application
from ..store import Store
from .build import build_report
from .render import render_pdf
from .schema import ReportDoc

log = logging.getLogger("uvicorn.error")


def local_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Australia/Sydney"))
    except Exception:  # no time zone data (install tzdata on Windows): fall back to UTC
        return datetime.now(timezone.utc)


def nice_date(dt: datetime) -> str:
    return f"{dt.day} {dt:%B %Y}"


def nice_time(dt: datetime) -> str:
    return f"{dt.day} {dt:%B %Y, %H:%M %Z}".strip()


class ReportWorker:
    def __init__(self, store: Store, make: Callable[[Application, str, str | None, str], ReportDoc], pdf_dir: Path,
                 mailer: Mailer, link: Callable[[str], str], pdf: Callable[[ReportDoc, Path], Path] | None = None,
                 review: bool | None = None, threads: int = 2):
        self.store, self.make, self.pdf_dir, self.mailer, self.link = store, make, pdf_dir, mailer, link
        self.pdf = pdf or (lambda doc, out: render_pdf(doc, out, executable_path=os.environ.get("TM_CHROMIUM_PATH")))
        self.review = os.environ.get("TM_REVIEW_REPORTS") == "1" if review is None else review
        self._pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="report")

    def submit(self, order_id: str) -> None:
        self._pool.submit(self.process, order_id)

    def resume(self) -> None:
        for order_id in self.store.unfinished():
            self.submit(order_id)

    def process(self, order_id: str) -> bool:
        if not self.store.claim(order_id):
            return False  # not paid, or another worker has it
        order = self.store.get(order_id)
        try:
            application = Application.model_validate(order.application)
            logo = (f"data:{order.logo_type};base64,{base64.b64encode(order.logo).decode()}"
                    if order.logo and order.logo_type else None)
            doc = self.make(application, order_id, logo, order.industry)
            pdf_path = self.pdf(doc, self.pdf_dir / f"{order_id}.pdf")
            self.store.save_report(order_id, doc.model_dump(mode="json"), str(pdf_path), hold_for_review=self.review)
        except Exception as e:
            log.exception("Report %s failed", order_id)
            self.store.mark_failed(order_id, f"{type(e).__name__}: {e}")
            return False
        if not self.review:
            self.notify(order_id)
        return True

    def notify(self, order_id: str) -> bool:
        order = self.store.get(order_id)
        return self.mailer.report_ready(order.email, order.application.get("mark", ""),
                                        [(f"Report {order_id}: {order.application.get('mark', '')}", self.link(order_id))])
