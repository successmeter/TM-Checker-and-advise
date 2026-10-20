"""Refresh IP Australia data: the goods & services picklist, wording from registered marks, and the Manual.

  python -m tm_advisor.refresh                 refresh all three
  python -m tm_advisor.refresh --only picklist
  python -m tm_advisor.refresh --only wording
  python -m tm_advisor.refresh --only manual
  python -m tm_advisor.refresh --force         replace the picklist even if the new one is much smaller

Each part keeps its current copy if the new download looks incomplete. A report of what changed is printed and
appended to data/refresh.log. A running server picks up the new data without a restart. Safe to schedule weekly.
"""

import argparse
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "refresh.log"
LOCK = ROOT / "data" / "refresh.lock"
STALE_LOCK = timedelta(hours=3)


def take_lock(lock: Path = LOCK, now: datetime | None = None) -> bool:
    """One update at a time: the server's automatic updates and this command never overlap."""
    now = now or datetime.now()
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            started = datetime.fromisoformat(lock.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            started = datetime.min
        if now - started < STALE_LOCK:
            return False
    lock.write_text(now.isoformat(timespec="seconds"), encoding="utf-8")
    return True


def _picklist(force: bool):
    from .picklist_api import sync  # needs IPA_CLIENT_ID / IPA_CLIENT_SECRET; explains itself if they're missing
    return sync(force=force)


def _wording(force: bool):
    from .register.wording import harvest  # needs IPA_CLIENT_ID / IPA_CLIENT_SECRET; explains itself if they're missing
    return harvest(force=force)


def _manual(force: bool):
    from .manual.__main__ import refresh
    return refresh()


STEPS: dict[str, Callable] = {"picklist": _picklist, "wording": _wording, "manual": _manual}
NAMES = {"picklist": "Goods & services picklist", "wording": "Registered goods & services wording",
         "manual": "Trade Marks Manual"}


def run(only: str | None = None, force: bool = False, steps: dict[str, Callable] | None = None,
        log_file: Path = LOG, out: Callable[[str], None] = print) -> bool:
    steps = steps or STEPS
    lines = [f"=== Refresh {datetime.now():%Y-%m-%d %H:%M} ==="]
    ok = True
    for key, step in steps.items():
        if only and key != only:
            continue
        out(f"Refreshing the {NAMES.get(key, key)}…")
        try:
            change = step(force)
            lines.append(f"{NAMES.get(key, key)}: updated. {change.summary()}")
        except SystemExit as e:
            ok = False
            lines.append(f"{NAMES.get(key, key)}: NOT updated, current copy kept. {e}")
        except Exception as e:  # network errors and the like: keep going with the other step
            ok = False
            lines.append(f"{NAMES.get(key, key)}: NOT updated, current copy kept. {type(e).__name__}: {e}")
    report = "\n".join(lines)
    out(report)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(report + "\n\n")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tm_advisor.refresh", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=sorted(STEPS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not take_lock():
        sys.exit("An update is already running (the server updates automatically). Try again later.")
    try:
        ok = run(args.only, args.force)
    finally:
        LOCK.unlink(missing_ok=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
