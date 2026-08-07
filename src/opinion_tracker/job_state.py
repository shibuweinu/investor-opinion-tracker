from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .sync_models import PortableConfigV2, ReportJob


class JobWindow(BaseModel):
    since: datetime | None
    until: datetime


class JobStore:
    def __init__(self, workspace: Path):
        self.root = workspace / ".investor-opinion-tracker" / "jobs"

    def materialize(self, config: PortableConfigV2) -> None:
        for job_id, job in config.report_jobs.items():
            directory = self.root / job_id
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def list(self) -> list[ReportJob]:
        return [
            ReportJob.model_validate_json(path.read_text()) for path in sorted(self.root.glob("*/job.json"))
        ]

    def window(self, job_id: str, until: datetime) -> JobWindow:
        path = self.root / job_id / "checkpoint.json"
        since = datetime.fromisoformat(json.loads(path.read_text())["cutoff"]) if path.exists() else None
        return JobWindow(since=since, until=until)

    def mark_success(self, job_id: str, cutoff: datetime) -> None:
        path = self.root / job_id / "checkpoint.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cutoff": cutoff.isoformat()}, indent=2), encoding="utf-8")
