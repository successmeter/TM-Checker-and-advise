"""Look after paid reports from the command line (on the server).

  py -m tm_advisor.orders list                 recent orders and their status
  py -m tm_advisor.orders link TA-XXXXXXXX     the customer's private report link
  py -m tm_advisor.orders approve TA-XXXXXXXX  release a report held for review (TM_REVIEW_REPORTS=1) and email it

A report that failed is retried automatically each time the server starts (up to 5 attempts).
"""

import os
import sys
from pathlib import Path

from .api import ROOT, _secret
from .mailer import Mailer
from .store import Store


def main() -> None:
    store = Store(Path(os.environ.get("TM_DB", ROOT / "data" / "orders.sqlite")), secret=_secret())
    public = os.environ.get("TM_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
    link = lambda oid: f"{public}/report/{oid}?t={store.token_for(oid)}"  # noqa: E731
    command, *args = sys.argv[1:] or ["help"]
    if command == "list":
        rows = store._db.execute("SELECT id, status, email, created_at, error FROM orders "
                                 "ORDER BY created_at DESC LIMIT 50").fetchall()
        for r in rows:
            print(f"{r['id']}  {r['status']:<10} {r['email']:<32} {r['created_at']}  {r['error'] or ''}")
        if not rows:
            print("No orders yet.")
    elif command == "link" and args:
        print(link(args[0]))
    elif command == "approve" and args:
        if not store.approve(args[0]):
            sys.exit(f"{args[0]} isn't waiting for review.")
        order = store.get(args[0])
        Mailer.from_env().report_ready(order.email, order.application.get("mark", ""),
                                       [(f"Report {order.id}: {order.application.get('mark', '')}", link(order.id))])
        print(f"Released {order.id} and emailed {order.email}.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
