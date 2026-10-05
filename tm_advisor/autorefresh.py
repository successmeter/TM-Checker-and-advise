"""Keeps IP Australia data current while the server runs, with no scheduled task needed.

Every few hours a background thread checks how old the picklist and the Manual are. Anything older than
TM_AUTO_REFRESH_DAYS (default 7; 0 turns this off) is refreshed with the same safe refresh as
`python -m tm_advisor.refresh`: the current copy is kept if a download looks incomplete, and the result is logged to
data/refresh.log. A failed attempt is retried after a day, not every check. Missing data (never downloaded) counts
as out of date, so a fresh install downloads it on its own.
"""

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from . import refresh
from .refresh import take_lock

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "refresh_state.json"
log = logging.getLogger("uvicorn.error")

RETRY_AFTER = timedelta(days=1)


def interval_days() -> int:
    try:
        return max(0, int(os.environ.get("TM_AUTO_REFRESH_DAYS", "7")))
    except ValueError:
        return 7


def data_dates(root: Path = ROOT) -> dict[str, datetime | None]:
    """When each part was last downloaded (None if never)."""
    dates: dict[str, datetime | None] = {"picklist": None, "manual": None}
    picklist = root / "data" / "picklist.json"
    if picklist.exists():
        try:
            updated = json.loads(picklist.read_text(encoding="utf-8")).get("updated")
            dates["picklist"] = datetime.fromisoformat(updated) if updated else datetime.fromtimestamp(picklist.stat().st_mtime)
        except (ValueError, OSError):
            dates["picklist"] = datetime.fromtimestamp(picklist.stat().st_mtime)
    pages = root / "data" / "manual" / "pages.jsonl"
    if pages.exists():
        dates["manual"] = datetime.fromtimestamp(pages.stat().st_mtime)
    return dates


def due(now: datetime, days: int, dates: dict[str, datetime | None], attempts: dict[str, str]) -> list[str]:
    """Parts that are out of date and haven't been attempted in the last day."""
    parts = []
    for part, updated in dates.items():
        if updated and now - updated < timedelta(days=days):
            continue
        last = attempts.get(part)
        if last and now - datetime.fromisoformat(last) < RETRY_AFTER:
            continue
        parts.append(part)
    return parts


def next_due(now: datetime, days: int, dates: dict[str, datetime | None]) -> datetime | None:
    if not days:
        return None
    times = [(d + timedelta(days=days)) if d else now for d in dates.values()]
    return max(now, min(times))


def check_once(now: datetime | None = None, days: int | None = None, root: Path = ROOT,
               run: Callable[..., bool] = refresh.run) -> list[str]:
    """Refresh whatever is due. Returns the parts attempted."""
    now = now or datetime.now()
    days = interval_days() if days is None else days
    if not days:
        return []
    state_file, lock = root / "data" / "refresh_state.json", root / "data" / "refresh.lock"
    attempts = _read_json(state_file)
    parts = due(now, days, data_dates(root), attempts)
    if not parts or not take_lock(lock, now):
        return []
    try:
        for part in parts:
            log.info("Automatic update: refreshing the %s", refresh.NAMES[part])
            attempts[part] = now.isoformat(timespec="seconds")
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(attempts), encoding="utf-8")
            ok = run(only=part, out=lambda line: log.info("%s", line))
            log.info("Automatic update of the %s %s", refresh.NAMES[part], "finished" if ok else "failed; see data/refresh.log")
    finally:
        lock.unlink(missing_ok=True)
    return parts


def start(check_every: float = 6 * 3600, first_check_after: float = 60) -> threading.Thread | None:
    """Start the background checker (does nothing if TM_AUTO_REFRESH_DAYS is 0)."""
    if not interval_days():
        log.info("Automatic data updates are off (TM_AUTO_REFRESH_DAYS=0)")
        return None

    def loop() -> None:
        time.sleep(first_check_after)
        while True:
            try:
                check_once()
            except Exception:  # never let a failed update take the server down
                log.exception("Automatic update failed")
            time.sleep(check_every)

    thread = threading.Thread(target=loop, name="tm-advisor-autorefresh", daemon=True)
    thread.start()
    return thread


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
