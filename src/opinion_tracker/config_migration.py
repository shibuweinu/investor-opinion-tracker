from __future__ import annotations

from typing import Any, Literal

from .sync_models import PortableConfig, PortableConfigV2, ReportJob


def migrate_portable_config(payload: dict[str, Any]) -> PortableConfigV2:
    version = payload.get("schema_version", 1)
    if version == 2:
        return PortableConfigV2.model_validate(payload)
    if version != 1:
        raise ValueError("配置 Schema 较新，请先升级产品")
    old = PortableConfig.model_validate(payload)
    daily, weekly = old.reports["daily"], old.reports["weekly"]
    jobs: dict[Literal["morning", "evening", "weekly"], ReportJob] = {
        "morning": ReportJob(
            job_id="morning",
            kind="morning",
            lookback_days_by_role=daily.lookback_days_by_role,
            weekdays=daily.weekdays,
            hour=9,
            timezone=daily.timezone,
            incremental_from="previous_evening",
        ),
        "evening": ReportJob(
            job_id="evening",
            kind="evening",
            lookback_days_by_role=daily.lookback_days_by_role,
            weekdays=daily.weekdays,
            hour=daily.hour,
            minute=daily.minute,
            timezone=daily.timezone,
            incremental_from="same_day_morning",
        ),
        "weekly": ReportJob(
            job_id="weekly",
            kind="weekly",
            lookback_days_by_role=weekly.lookback_days_by_role,
            weekdays=weekly.weekdays,
            hour=weekly.hour,
            minute=weekly.minute,
            timezone=weekly.timezone,
            incremental_from="previous_success",
        ),
    }
    return PortableConfigV2(
        tracked_accounts=old.tracked_accounts,
        report_jobs=jobs,
        trader_profile=old.trader_profile,
        report_preferences=old.report_preferences,
        sync=old.sync,
        updated_at=old.updated_at,
        revision=old.revision,
    )
