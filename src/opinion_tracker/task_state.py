from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .schemas import TaskDraft


class TaskRecord(BaseModel):
    status: Literal["onboarding_required", "draft", "confirmed", "completed"] = "onboarding_required"
    draft: TaskDraft | None = None
    fingerprint: str | None = None
    confirmed_at: datetime | None = None
    confirmation_source: Literal["user", "auto_applied"] | None = None
    source_revision: str | None = None


def task_fingerprint(draft: TaskDraft) -> str:
    content = json.dumps(draft.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()


class TaskStore:
    def __init__(self, workspace: Path):
        self.path = workspace / ".investor-opinion-tracker" / "task.json"

    def load(self) -> TaskRecord:
        if not self.path.exists():
            return TaskRecord()
        return TaskRecord.model_validate_json(self.path.read_text(encoding="utf-8"))

    def _write(self, record: TaskRecord) -> TaskRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    def save_draft(self, draft: TaskDraft) -> TaskRecord:
        previous = self.load()
        fingerprint = task_fingerprint(draft)
        if previous.status == "confirmed" and previous.fingerprint == fingerprint:
            return previous
        return self._write(TaskRecord(status="draft", draft=draft))

    def confirm(self) -> TaskRecord:
        current = self.load()
        if current.draft is None:
            raise ValueError("尚未创建完整的任务草稿")
        return self._write(
            TaskRecord(
                status="confirmed",
                draft=current.draft,
                fingerprint=task_fingerprint(current.draft),
                confirmed_at=datetime.now(UTC),
                confirmation_source="user",
            )
        )

    def confirm_auto_applied(self, draft: TaskDraft, revision: str) -> TaskRecord:
        return self._write(
            TaskRecord(
                status="confirmed",
                draft=draft,
                fingerprint=task_fingerprint(draft),
                confirmed_at=datetime.now(UTC),
                confirmation_source="auto_applied",
                source_revision=revision,
            )
        )

    def require_confirmed(self) -> TaskRecord:
        current = self.load()
        if (
            current.status != "confirmed"
            or current.draft is None
            or current.fingerprint != task_fingerprint(current.draft)
        ):
            raise PermissionError("任务尚未确认或内容已变化，请重新确认")
        return current

    def complete(self) -> TaskRecord:
        current = self.require_confirmed()
        current.status = "completed"
        return self._write(current)
