from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .schemas import TraderProfile


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountConfig(StrictModel):
    url: HttpUrl
    display_name: str
    role: Literal["research", "auxiliary_news"] = "research"


class ReportSchedule(StrictModel):
    enabled: bool = True
    lookback_days_by_role: dict[Literal["research", "auxiliary_news"], int]
    weekdays: list[int]
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "Asia/Shanghai"


class ReportPreferences(StrictModel):
    include_position_sizing: bool = False


class SyncPreferences(StrictModel):
    trusted_auto_apply: bool = False


class PortableConfig(StrictModel):
    schema_version: Literal[1] = 1
    tracked_accounts: list[AccountConfig]
    reports: dict[Literal["daily", "weekly"], ReportSchedule]
    trader_profile: TraderProfile
    report_preferences: ReportPreferences = ReportPreferences()
    sync: SyncPreferences = SyncPreferences()
    updated_at: datetime
    revision: str


class SyncBinding(StrictModel):
    remote_url: str
    canonical_remote: str
    base_commit: str | None = None


class SyncAuditEntry(StrictModel):
    occurred_at: datetime
    action: str
    old_commit: str | None = None
    new_commit: str | None = None
    revision: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
