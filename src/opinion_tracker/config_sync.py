from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .git_repository import GitRepository
from .schemas import TaskDraft
from .sync_models import PortableConfig, SyncAuditEntry, SyncBinding
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

    def push(self, document: PortableConfig) -> str:
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

    def load_remote(self) -> PortableConfig:
        if self.repository is None:
            raise ValueError("未提供配置仓库")
        return PortableConfig.model_validate_json((self.repository.path / "config.json").read_text())

    def apply_document(
        self, document: PortableConfig, *, report_kind: Literal["daily", "weekly"],
        role: Literal["research", "auxiliary_news"], trusted: bool,
    ) -> TaskRecord:
        schedule = document.reports[report_kind]
        urls = [str(account.url) for account in document.tracked_accounts if account.role == role]
        draft = TaskDraft(
            user_urls=urls, lookback_days=schedule.lookback_days_by_role[role], qps=1,
            report_type=report_kind, trader_profile=document.trader_profile,
            include_position_sizing=document.report_preferences.include_position_sizing,
        )
        store = TaskStore(self.workspace)
        record = store.confirm_auto_applied(draft, document.revision) if trusted else store.save_draft(draft)
        self._audit("auto_apply" if trusted else "pull", None, document)
        return record

    def _audit(self, action: str, commit: str | None, document: PortableConfig) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        entry = SyncAuditEntry(
            occurred_at=datetime.now(UTC), action=action, new_commit=commit,
            revision=document.revision,
        )
        with (self.state_dir / "sync-audit.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")
