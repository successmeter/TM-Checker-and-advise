import json
import os
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from tm_advisor import autorefresh
from tm_advisor.refresh import take_lock

NOW = datetime(2026, 10, 12, 9, 0)


def make_data(root, picklist_days_old=None, manual_days_old=None):
    data = root / "data"
    (data / "manual").mkdir(parents=True)
    if picklist_days_old is not None:
        updated = (NOW - timedelta(days=picklist_days_old)).date().isoformat()
        (data / "picklist.json").write_text(json.dumps({"updated": updated, "items": []}))
    if manual_days_old is not None:
        pages = data / "manual" / "pages.jsonl"
        pages.write_text("")
        stamp = (NOW - timedelta(days=manual_days_old)).timestamp()
        os.utime(pages, (stamp, stamp))


def runner(calls, ok=True):
    def run(only, out):
        calls.append(only)
        return ok
    return run


def test_fresh_data_is_left_alone(tmp_path):
    make_data(tmp_path, picklist_days_old=2, manual_days_old=3)
    calls = []
    assert autorefresh.check_once(NOW, 7, tmp_path, runner(calls)) == []
    assert calls == []


def test_old_or_missing_data_is_refreshed(tmp_path):
    make_data(tmp_path, picklist_days_old=8, manual_days_old=None)  # Manual never downloaded
    calls = []
    assert autorefresh.check_once(NOW, 7, tmp_path, runner(calls)) == ["picklist", "manual"]
    assert calls == ["picklist", "manual"]
    assert not (tmp_path / "data" / "refresh.lock").exists()


def test_failed_attempt_is_retried_after_a_day_not_every_check(tmp_path):
    make_data(tmp_path, picklist_days_old=30, manual_days_old=1)
    calls = []
    autorefresh.check_once(NOW, 7, tmp_path, runner(calls, ok=False))
    autorefresh.check_once(NOW + timedelta(hours=6), 7, tmp_path, runner(calls, ok=False))
    assert calls == ["picklist"]
    autorefresh.check_once(NOW + timedelta(days=1, hours=1), 7, tmp_path, runner(calls))
    assert calls == ["picklist", "picklist"]


def test_never_runs_alongside_another_update(tmp_path):
    make_data(tmp_path, picklist_days_old=30, manual_days_old=30)
    lock = tmp_path / "data" / "refresh.lock"
    assert take_lock(lock, NOW)  # e.g. someone ran `python -m tm_advisor.refresh`
    calls = []
    assert autorefresh.check_once(NOW + timedelta(minutes=5), 7, tmp_path, runner(calls)) == []
    assert calls == []
    # a lock left behind by a crash expires
    assert autorefresh.check_once(NOW + timedelta(hours=4), 7, tmp_path, runner(calls)) == ["picklist", "manual"]


def test_zero_days_turns_it_off(tmp_path, monkeypatch):
    make_data(tmp_path)
    calls = []
    assert autorefresh.check_once(NOW, 0, tmp_path, runner(calls)) == []
    monkeypatch.setenv("TM_AUTO_REFRESH_DAYS", "0")
    assert autorefresh.start() is None


def test_next_due_date():
    dates = {"picklist": NOW - timedelta(days=2), "manual": NOW - timedelta(days=5)}
    assert autorefresh.next_due(NOW, 7, dates) == NOW + timedelta(days=2)
    assert autorefresh.next_due(NOW, 7, {"picklist": None, "manual": NOW}) == NOW


def test_server_starts_the_checker_only_when_asked(monkeypatch):
    from pathlib import Path

    from tm_advisor.api import create_app
    from tm_advisor.picklist import Picklist
    from tm_advisor.register import FixtureRegisterClient

    data = Path(__file__).resolve().parents[1] / "data"
    started = []
    monkeypatch.setattr(autorefresh, "start", lambda: started.append(True))

    def app(auto):
        return create_app(FixtureRegisterClient.load(data / "register_fixture.json"),
                          Picklist.load(data / "picklist_sample.json"), auto_refresh=auto)

    with TestClient(app(False)):
        pass
    assert started == []
    with TestClient(app(True)) as client:
        status = client.get("/api/data-status").json()
    assert started == [True]
    assert status["auto_update_days"] == 7 and status["next_auto_update"]
