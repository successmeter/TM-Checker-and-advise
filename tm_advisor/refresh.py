"""Refresh IP Australia data: the goods & services picklist and the Trade Marks Manual.

  python -m tm_advisor.refresh                 refresh both
  python -m tm_advisor.refresh --only picklist
  python -m tm_advisor.refresh --only manual
  python -m tm_advisor.refresh --force         replace the picklist even if the new one is much smaller

Each part keeps its current copy if the new download looks incomplete. A report of what changed is printed and
appended to data/refresh.log. A running server picks up the new data without a restart. Safe to schedule weekly.
"""

import argparse
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "refresh.log"


def _picklist(force: bool):
    from .picklist_site import sync
    return sync(force=force)


def _manual(force: bool):
    from .manual.__main__ import refresh
    return refresh()


STEPS: dict[str, Callable] = {"picklist": _picklist, "manual": _manual}
NAMES = {"picklist": "Goods & services picklist", "manual": "Trade Marks Manual"}


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
    sys.exit(0 if run(args.only, args.force) else 1)


if __name__ == "__main__":
    main()
