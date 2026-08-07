from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .config_migration import migrate_portable_config
from .git_repository import GitRepository
from .job_state import JobStore
from .schemas import TaskDraft
from .sync_models import PortableConfig, PortableConfigV2, SyncAuditEntry, SyncBinding
from .task_state import TaskRecord, TaskStore


class ConfigSyncService:
    def __init__(self, workspace: Path, repository: GitRepository | None):
        self.workspace, self.repository = workspace, repository
        self.state_dir = workspace / ".investor-opinion-tracker"

    def connect(self) -> SyncBinding:
        if self.repository is None:
            raise ValueError("未提供配置仓库")
        self.repository.clone_or_open()
        binding = SyncBinding(
            remote_url=self.repository.remote_url,
            canonical_remote=self.repository.canonical_remote(),
            base_commit=self.repository.remote_head(),
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "sync-binding.json").write_text(binding.model_dump_json(indent=2))
        return binding

    def push(self, document: PortableConfig | PortableConfigV2) -> str:
        if self.repository is None:
            raise ValueError("未提供配置仓库")
        self.repository.write("config.json", document.model_dump_json(indent=2))
        self.repository.write("README.md", "# Investor Opinion Tracker private configuration\n")
        self.repository.write(".gitignore", "*\n!.gitignore\n!README.md\n!config.json\n")
        self.repository.commit([".gitignore", "README.md", "config.json"], "Update personal configuration")
        self.repository.push_fast_forward()
        commit = self.repository.head()
        self._audit("push", commit, document)
        return commit

    def load_remote(self) -> PortableConfigV2:
        if self.repository is None:
            raise ValueError("未提供配置仓库")
        return migrate_portable_config(json.loads((self.repository.path / "config.json").read_text()))

    def update(self) -> bool:
        if self.repository is None:
            return False
        return self.repository.update_fast_forward()

    def document(self) -> PortableConfigV2:
        return self.load_remote()

    def apply_trusted(self) -> None:
        document = self.load_remote()
        JobStore(self.workspace).materialize(document, trusted=True)
        self._audit("auto_apply", None, document)

    def ensure_local(self, *, trusted: bool) -> None:
        if JobStore(self.workspace).list_jobs():
            return
        JobStore(self.workspace).materialize(self.load_remote(), trusted=trusted)

    def apply_trusted_document(self, document: PortableConfig) -> None:
        document = PortableConfig.model_validate(document.model_dump())
        jobs: list[
            tuple[
                Path,
                Literal["daily", "weekly"],
                tuple[Literal["research", "auxiliary_news"], ...],
            ]
        ] = [
            (self.workspace, "daily", ("research",)),
            (self.workspace.parent / f"{self.workspace.name}-daily-news", "daily", ("auxiliary_news",)),
            (
                self.workspace.parent / f"{self.workspace.name}-weekly",
                "weekly",
                ("research", "auxiliary_news"),
            ),
        ]
        drafts = [
            (workspace, self._draft(document, report_kind, roles)) for workspace, report_kind, roles in jobs
        ]
        for workspace, draft in drafts:
            TaskStore(workspace).confirm_auto_applied(draft, document.revision)
        self._audit("auto_apply", None, document)

    def _draft(
        self,
        document: PortableConfig,
        report_kind: Literal["daily", "weekly"],
        roles: tuple[Literal["research", "auxiliary_news"], ...],
    ) -> TaskDraft:
        schedule = document.reports[report_kind]
        urls = [str(account.url) for account in document.tracked_accounts if account.role in roles]
        lookback = max(schedule.lookback_days_by_role[role] for role in roles)
        return TaskDraft.model_validate(
            {
                "user_urls": urls,
                "lookback_days": lookback,
                "qps": 1,
                "report_type": report_kind,
                "trader_profile": document.trader_profile,
                "include_position_sizing": document.report_preferences.include_position_sizing,
            }
        )

    def apply_document(
        self,
        document: PortableConfig,
        *,
        report_kind: Literal["daily", "weekly"],
        role: Literal["research", "auxiliary_news"],
        trusted: bool,
    ) -> TaskRecord:
        draft = self._draft(document, report_kind, (role,))
        store = TaskStore(self.workspace)
        record = store.confirm_auto_applied(draft, document.revision) if trusted else store.save_draft(draft)
        self._audit("auto_apply" if trusted else "pull", None, document)
        return record

    def _audit(self, action: str, commit: str | None, document: PortableConfig | PortableConfigV2) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        entry = SyncAuditEntry(
            occurred_at=datetime.now(UTC),
            action=action,
            new_commit=commit,
            revision=document.revision,
        )
        with (self.state_dir / "sync-audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")
