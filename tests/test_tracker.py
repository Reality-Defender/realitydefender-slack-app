from reality_defender_slack_app.services.tracker import (
    STATUS_DONE,
    AnalysisTracker,
)


def test_start_and_for_user() -> None:
    tracker = AnalysisTracker()
    tracker.start("T1", "U1", "photo.jpg")

    records = tracker.for_user("T1", "U1")
    assert len(records) == 1
    assert records[0].label == "photo.jpg"
    assert records[0].status == "analyzing"


def test_finish_updates_status() -> None:
    tracker = AnalysisTracker()
    rid = tracker.start("T1", "U1", "photo.jpg")

    tracker.finish(rid, STATUS_DONE)

    assert tracker.for_user("T1", "U1")[0].status == STATUS_DONE


def test_for_user_scopes_by_team_and_user() -> None:
    tracker = AnalysisTracker()
    tracker.start("T1", "U1", "a")
    tracker.start("T1", "U2", "b")
    tracker.start("T2", "U1", "c")

    records = tracker.for_user("T1", "U1")
    assert [r.label for r in records] == ["a"]
