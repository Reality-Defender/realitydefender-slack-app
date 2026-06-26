from __future__ import annotations

import uuid
from dataclasses import dataclass

# Analysis lifecycle states surfaced by /analysis-status.
STATUS_ANALYZING = "analyzing"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


@dataclass
class AnalysisRecord:
    label: str
    team_id: str
    user_id: str
    status: str = STATUS_ANALYZING


class AnalysisTracker:
    """In-memory registry of analyses, powering /analysis-status.

    Best-effort and ephemeral by design: state resets on restart and is not
    shared across instances. Detection results are still delivered via Slack
    messages regardless of what the tracker reports.
    """

    def __init__(self) -> None:
        self._records: dict[str, AnalysisRecord] = {}

    def start(self, team_id: str, user_id: str, label: str) -> str:
        record_id = uuid.uuid4().hex
        self._records[record_id] = AnalysisRecord(
            label=label, team_id=team_id, user_id=user_id
        )
        return record_id

    def finish(self, record_id: str, status: str) -> None:
        record = self._records.get(record_id)
        if record is not None:
            record.status = status

    def for_user(self, team_id: str, user_id: str) -> list[AnalysisRecord]:
        return [
            r
            for r in self._records.values()
            if r.team_id == team_id and r.user_id == user_id
        ]
