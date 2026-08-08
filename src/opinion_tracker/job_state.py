from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .execution import Collector, execute_confirmed
from .run_state import RunIdentity, RunStateStore
from .schemas import RunResult, TaskDraft
from .sync_models import PortableConfigV2, ReportJob
from .task_state import TaskStore


class JobWindow(BaseModel):
    since: datetime | None
    until: datetime


class DueJob(BaseModel):
    job: ReportJob
    scheduled_cutoff: datetime


class JobStore:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.root = workspace / ".investor-opinion-tracker" / "jobs"

    def materialize(self, config: PortableConfigV2, *, trusted: bool = False) -> None:
        for job_id, job in config.report_jobs.items():
            directory = self.root / job_id
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
            urls = [str(account.url).rstrip("/") for account in config.tracked_accounts]
            lookbacks = {
                str(account.url).rstrip("/"): job.lookback_days_by_role[account.role]
                for account in config.tracked_accounts
            }
            user_qps = {
                str(account.url).rstrip("/"): 0.4 if account.role == "auxiliary_news" else 1.0
                for account in config.tracked_accounts
            }
            draft = TaskDraft.model_validate(
                {
                    "user_urls": urls,
                    "lookback_days": max(lookbacks.values()),
                    "qps": 1,
                    "report_type": "weekly" if job.kind == "weekly" else "daily",
                    "trader_profile": config.trader_profile,
                    "include_position_sizing": config.report_preferences.include_position_sizing,
                    "user_lookback_days": lookbacks,
                    "user_qps": user_qps,
                }
            )
            task_store = TaskStore(directory)
            if trusted:
                task_store.confirm_auto_applied(draft, config.revision)
            else:
                task_store.save_draft(draft)

    def list_jobs(self) -> list[ReportJob]:
        return [
            ReportJob.model_validate_json(path.read_text()) for path in sorted(self.root.glob("*/job.json"))
        ]

    def get(self, job_id: str) -> ReportJob:
        path = self.root / job_id / "job.json"
        if not path.exists():
            raise ValueError(f"未知任务：{job_id}")
        return ReportJob.model_validate_json(path.read_text())

    def due(self, now: datetime) -> list[ReportJob]:
        return [item.job for item in self.due_runs(now, grace_minutes=0)]

    def due_runs(self, now: datetime, *, grace_minutes: int = 15) -> list[DueJob]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("调度时间必须包含时区")
        due = []
        for job in self.list_jobs():
            timezone = ZoneInfo(job.timezone)
            local_now = now.astimezone(timezone)
            scheduled_cutoff = local_now.replace(
                hour=job.hour, minute=job.minute, second=0, microsecond=0
            )
            weekday = (scheduled_cutoff.weekday() + 1) % 7
            delay = local_now - scheduled_cutoff
            if (
                job.enabled
                and weekday in job.weekdays
                and timedelta(0) <= delay <= timedelta(minutes=grace_minutes)
            ):
                due.append(DueJob(job=job, scheduled_cutoff=scheduled_cutoff))
        return due

    def window(self, job_id: str, until: datetime) -> JobWindow:
        job = ReportJob.model_validate_json((self.root / job_id / "job.json").read_text())
        source = {"previous_evening": "evening", "same_day_morning": "morning"}.get(
            job.incremental_from, job_id
        )
        path = self.root / source / "checkpoint.json"
        since = datetime.fromisoformat(json.loads(path.read_text())["cutoff"]) if path.exists() else None
        return JobWindow(since=since, until=until)

    def mark_success(self, job_id: str, cutoff: datetime) -> None:
        path = self.root / job_id / "checkpoint.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cutoff": cutoff.isoformat()}, indent=2), encoding="utf-8")

    def task_store(self, job_id: str) -> TaskStore:
        return TaskStore(self.root / job_id)

    def confirm(self, job_id: str) -> None:
        self.task_store(job_id).confirm()

    def run(
        self, job_id: str, output: Path, until: datetime, collector: Collector | None = None
    ) -> RunResult:
        window = self.window(job_id, until)
        run_store = RunStateStore(
            self.workspace, RunIdentity(job_id=job_id, cutoff=until)
        )
        result = execute_confirmed(
            self.root / job_id,
            output,
            collector,
            since=window.since,
            until=until,
            complete_state=False,
            run_store=run_store,
        )
        analyze = output / "ANALYZE.md"
        context = (
            "早报：侧重隔夜变化、开盘前风险和观察项。"
            if job_id == "morning"
            else "晚报：侧重盘中观点、收盘核验和次日观察项。"
            if job_id == "evening"
            else "周报：总结七天观点变化、一致与分歧。"
        )
        analyze.write_text(
            f"# 报告类型\n\n{context}\n\n"
            f"行情核验调用 `analyze-file` 时必须传入 "
            f"`--market-as-of {until.isoformat()}`，只使用该截止时间之前最近一根完整日线。\n\n"
            + analyze.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return result

    def complete(self, job_id: str, cutoff: datetime, *, verified: bool) -> None:
        if not verified:
            raise ValueError("核验未通过，不得推进检查点")
        self.mark_success(job_id, cutoff)
