from tm_advisor.manual import ManualChange
from tm_advisor.picklist_sync import PicklistChange
from tm_advisor.refresh import run


def test_refresh_runs_both_and_logs_the_changes(tmp_path):
    log = tmp_path / "refresh.log"
    steps = {"picklist": lambda force: PicklistChange(before=10, after=11, added=["Class 9: Smart rings"]),
             "manual": lambda force: ManualChange(before=5, after=5, changed=["https://example/27.3"])}
    printed = []
    assert run(steps=steps, log_file=log, out=printed.append)
    text = log.read_text()
    assert "Goods & services picklist: updated. 11 terms (was 10): 1 added" in text
    assert "Class 9: Smart rings" in text
    assert "Trade Marks Manual: updated. 5 pages (was 5): 0 new, 0 removed, 1 changed" in text


def test_one_failure_does_not_stop_the_other_and_is_reported(tmp_path):
    log = tmp_path / "refresh.log"

    def broken(force):
        raise SystemExit("The new picklist has 3 terms, far fewer than the current 60000.")

    def offline(force):
        raise ConnectionError("network down")

    calls = []
    steps = {"picklist": broken, "manual": lambda force: calls.append(force) or ManualChange(1, 1)}
    assert not run(steps=steps, log_file=log, out=lambda _: None)
    assert calls == [False]
    assert "picklist: NOT updated, current copy kept. The new picklist has 3 terms" in log.read_text()

    assert not run(only="manual", steps={"picklist": broken, "manual": offline}, log_file=log, out=lambda _: None)
    assert "Trade Marks Manual: NOT updated, current copy kept. ConnectionError: network down" in log.read_text()


def test_force_is_passed_through(tmp_path):
    seen = []
    run(force=True, steps={"picklist": lambda force: seen.append(force) or PicklistChange(1, 1)},
        log_file=tmp_path / "l.log", out=lambda _: None)
    assert seen == [True]
