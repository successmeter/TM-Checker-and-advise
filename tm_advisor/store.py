"""Orders and reports (design: docs/paid-report-design.md §5.1).

SQLite in the data folder; one server. Each order has a random id and a private access token derived from the
order id and a server secret (HMAC), so a report link can be sent again at any time without storing it. Order
states:

  pending ──paid (verified Stripe webhook)──► paid ──► generating ──► ready
                                                          │  └──► review (held for a person to approve) ──► ready
                                                          └──► failed (retried)
  any paid state ──► refunded (the report stays available)
"""

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

STATES = ("pending", "paid", "generating", "review", "ready", "failed", "refunded")
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so ids read clearly over the phone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  application TEXT NOT NULL,
  industry TEXT NOT NULL DEFAULT '',
  logo BLOB,
  logo_type TEXT,
  amount INTEGER NOT NULL,
  currency TEXT NOT NULL,
  status TEXT NOT NULL,
  stripe_session TEXT,
  stripe_payment_intent TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL,
  paid_at TEXT,
  ready_at TEXT
);
CREATE INDEX IF NOT EXISTS orders_email ON orders(email);
CREATE INDEX IF NOT EXISTS orders_session ON orders(stripe_session);
CREATE TABLE IF NOT EXISTS reports (
  order_id TEXT PRIMARY KEY REFERENCES orders(id),
  doc TEXT NOT NULL,
  pdf_path TEXT,
  created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Order:
    id: str
    email: str
    application: dict
    industry: str
    logo: bytes | None
    logo_type: str | None
    amount: int
    currency: str
    status: str
    stripe_session: str | None
    stripe_payment_intent: str | None
    attempts: int
    error: str | None
    created_at: str
    paid_at: str | None
    ready_at: str | None


class Store:
    def __init__(self, path: Path | str = ":memory:", secret: bytes = b"test-secret"):
        self._secret = secret
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA journal_mode=WAL") if path != ":memory:" else None

    # orders -----------------------------------------------------------------------------------------------------
    def create_order(self, email: str, application: dict, amount: int, currency: str, industry: str = "",
                     logo: bytes | None = None, logo_type: str | None = None) -> tuple[Order, str]:
        """A new pending order and its access token (for the report link)."""
        with self._lock:
            while True:
                order_id = "TA-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))
                if not self._db.execute("SELECT 1 FROM orders WHERE id=?", (order_id,)).fetchone():
                    break
            self._db.execute(
                "INSERT INTO orders (id, email, application, industry, logo, logo_type, amount, currency,"
                " status, created_at) VALUES (?,?,?,?,?,?,?,?,'pending',?)",
                (order_id, email.strip().lower(), json.dumps(application), industry, logo, logo_type,
                 amount, currency, _now()))
            self._db.commit()
        return self.get(order_id), self.token_for(order_id)

    def get(self, order_id: str) -> Order | None:
        row = self._db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return _order(row) if row else None

    def by_session(self, session_id: str) -> Order | None:
        row = self._db.execute("SELECT * FROM orders WHERE stripe_session=?", (session_id,)).fetchone()
        return _order(row) if row else None

    def token_for(self, order_id: str) -> str:
        digest = hmac.new(self._secret, order_id.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest[:24]).decode().rstrip("=")

    def check_token(self, order_id: str, token: str | None) -> bool:
        return bool(token) and self.get(order_id) is not None and hmac.compare_digest(self.token_for(order_id), token)

    def orders_for_email(self, email: str) -> list[Order]:
        rows = self._db.execute("SELECT * FROM orders WHERE email=? AND status<>'pending' ORDER BY created_at DESC",
                                (email.strip().lower(),)).fetchall()
        return [_order(r) for r in rows]

    def set_session(self, order_id: str, session_id: str) -> None:
        self._update(order_id, stripe_session=session_id)

    def mark_paid(self, order_id: str, payment_intent: str | None) -> bool:
        """pending -> paid. False if it was already past pending (a repeated webhook)."""
        with self._lock:
            cur = self._db.execute("UPDATE orders SET status='paid', paid_at=?, stripe_payment_intent=? "
                                   "WHERE id=? AND status='pending'", (_now(), payment_intent, order_id))
            self._db.commit()
            return cur.rowcount == 1

    def claim(self, order_id: str) -> bool:
        """paid/failed -> generating, for exactly one worker."""
        with self._lock:
            cur = self._db.execute("UPDATE orders SET status='generating', attempts=attempts+1 "
                                   "WHERE id=? AND status IN ('paid','failed')", (order_id,))
            self._db.commit()
            return cur.rowcount == 1

    def mark_failed(self, order_id: str, error: str) -> None:
        self._update(order_id, status="failed", error=error[:1000])

    def mark_refunded_by_payment(self, payment_intent: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT id FROM orders WHERE stripe_payment_intent=?", (payment_intent,)).fetchone()
            if not row:
                return None
            self._db.execute("UPDATE orders SET status='refunded' WHERE id=?", (row["id"],))
            self._db.commit()
            return row["id"]

    def approve(self, order_id: str) -> bool:
        """review -> ready (a person has checked the report)."""
        with self._lock:
            cur = self._db.execute("UPDATE orders SET status='ready', ready_at=? WHERE id=? AND status='review'",
                                   (_now(), order_id))
            self._db.commit()
            return cur.rowcount == 1

    def unfinished(self) -> list[str]:
        """Paid orders without a report (e.g. after a restart), oldest first."""
        rows = self._db.execute("SELECT id FROM orders WHERE status IN ('paid','generating','failed') AND attempts < 5 "
                                "ORDER BY paid_at").fetchall()
        return [r["id"] for r in rows]

    # reports ----------------------------------------------------------------------------------------------------
    def save_report(self, order_id: str, doc: dict, pdf_path: str | None, hold_for_review: bool = False) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO reports (order_id, doc, pdf_path, created_at) VALUES (?,?,?,?)",
                             (order_id, json.dumps(doc), pdf_path, _now()))
            if hold_for_review:
                self._db.execute("UPDATE orders SET status='review', error=NULL WHERE id=? AND status='generating'",
                                 (order_id,))
            else:
                self._db.execute("UPDATE orders SET status='ready', ready_at=?, error=NULL "
                                 "WHERE id=? AND status='generating'", (_now(), order_id))
            self._db.commit()

    def report(self, order_id: str) -> tuple[dict, str | None] | None:
        row = self._db.execute("SELECT doc, pdf_path FROM reports WHERE order_id=?", (order_id,)).fetchone()
        return (json.loads(row["doc"]), row["pdf_path"]) if row else None

    def _update(self, order_id: str, **fields) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._db.execute(f"UPDATE orders SET {cols} WHERE id=?", (*fields.values(), order_id))
            self._db.commit()


def _order(row: sqlite3.Row) -> Order:
    data = dict(row)
    data["application"] = json.loads(data["application"])
    return Order(**data)
