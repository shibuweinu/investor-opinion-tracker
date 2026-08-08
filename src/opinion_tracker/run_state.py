from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .schemas import NormalizedPost


class RunIdentity(BaseModel):
    job_id: str
    cutoff: datetime

    @property
    def run_id(self) -> str:
        return f"{self.job_id}@{self.cutoff.isoformat()}"

    @property
    def directory_name(self) -> str:
        stamp = self.cutoff.strftime("%Y%m%dT%H%M%S%z")
        digest = hashlib.sha256(self.run_id.encode()).hexdigest()[:12]
        return f"{self.job_id}-{stamp}-{digest}"


class UserPageState(BaseModel):
    user_id: str
    next_page: int = Field(default=1, ge=1)
    status: Literal["pending", "running", "complete", "incomplete"] = "pending"
    oldest_regular_at: datetime | None = None
    pages_fetched: int = Field(default=0, ge=0)
    request_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    last_http_status: int | None = None


class ScheduledRunState(BaseModel):
    schema_version: Literal[1] = 1
    run_id: str
    job_id: str
    cutoff: datetime
    user_ids: list[str]
    status: Literal["pending", "running", "complete", "incomplete"] = "pending"
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeliveryReceipt(BaseModel):
    status: Literal["sent"] = "sent"
    run_id: str
    job_id: str
    cutoff: datetime
    address: str
    message_id: str
    report_sha256: str
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunAlreadyActive(RuntimeError):
    pass


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class RunStateStore:
    def __init__(self, workspace: Path, identity: RunIdentity):
        self.identity = identity
        self.root = (
            workspace / ".investor-opinion-tracker" / "runs" / identity.directory_name
        )
        self.state_path = self.root / "run.json"
        self.users_dir = self.root / "users"
        self.posts_path = self.root / "posts.jsonl"
        self.delivery_path = self.root / "delivery.json"
        self.lock_path = self.root / "lock"

    def initialize(self, user_ids: list[str]) -> ScheduledRunState:
        if self.state_path.exists():
            current = self.load()
            if current.user_ids != user_ids:
                raise ValueError("运行状态账号清单与当前任务不一致")
            return current
        state = ScheduledRunState(
            run_id=self.identity.run_id,
            job_id=self.identity.job_id,
            cutoff=self.identity.cutoff,
            user_ids=user_ids,
        )
        self.save(state)
        for user_id in user_ids:
            self.save_user(UserPageState(user_id=user_id))
        return state

    def load(self) -> ScheduledRunState:
        try:
            state = ScheduledRunState.model_validate_json(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("无法读取有效的运行状态") from exc
        if (
            state.run_id != self.identity.run_id
            or state.job_id != self.identity.job_id
            or state.cutoff != self.identity.cutoff
        ):
            raise ValueError("运行状态与当前任务标识不一致")
        return state

    def save(self, state: ScheduledRunState) -> None:
        state.updated_at = datetime.now(UTC)
        _atomic_write(self.state_path, state.model_dump_json(indent=2))

    def _user_path(self, user_id: str) -> Path:
        if not user_id.isdigit():
            raise ValueError("雪球用户 ID 必须是数字")
        return self.users_dir / f"{user_id}.json"

    def load_user(self, user_id: str) -> UserPageState:
        try:
            state = UserPageState.model_validate_json(
                self._user_path(user_id).read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ValueError(f"无法读取用户 {user_id} 的分页状态") from exc
        if state.user_id != user_id:
            raise ValueError("用户分页状态标识不一致")
        return state

    def save_user(self, state: UserPageState) -> None:
        _atomic_write(self._user_path(state.user_id), state.model_dump_json(indent=2))

    def posts(self) -> list[NormalizedPost]:
        if not self.posts_path.exists():
            return []
        try:
            return [
                NormalizedPost.model_validate_json(line)
                for line in self.posts_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except ValueError as exc:
            raise ValueError("无法读取有效的运行帖子状态") from exc

    def merge_posts(self, posts: list[NormalizedPost]) -> None:
        merged = {post.platform_post_id: post for post in self.posts()}
        for post in posts:
            merged.setdefault(post.platform_post_id, post)
        content = "".join(f"{post.model_dump_json()}\n" for post in merged.values())
        _atomic_write(self.posts_path, content)

    def record_delivery(self, receipt: DeliveryReceipt) -> None:
        if receipt.run_id != self.identity.run_id:
            raise ValueError("投递回执与运行标识不一致")
        _atomic_write(self.delivery_path, receipt.model_dump_json(indent=2))

    def delivery(self) -> DeliveryReceipt | None:
        if not self.delivery_path.exists():
            return None
        try:
            receipt = DeliveryReceipt.model_validate_json(
                self.delivery_path.read_text(encoding="utf-8")
            )
        except ValueError as exc:
            raise ValueError("无法读取有效的投递回执") from exc
        if receipt.run_id != self.identity.run_id:
            raise ValueError("投递回执与运行标识不一致")
        return receipt


class RunLock:
    def __init__(self, store: RunStateStore):
        self.store = store
        self.acquired = False

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def __enter__(self) -> RunLock:
        self.store.root.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                descriptor = os.open(
                    self.store.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                try:
                    payload = json.loads(self.store.lock_path.read_text(encoding="utf-8"))
                    pid = int(payload["pid"])
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    raise RunAlreadyActive("运行锁无效，需人工检查") from exc
                if self._pid_is_alive(pid):
                    raise RunAlreadyActive(f"相同报告任务已由进程 {pid} 执行") from None
                try:
                    self.store.lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "created_at": datetime.now(UTC).isoformat()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            self.acquired = True
            return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.acquired:
            try:
                self.store.lock_path.unlink()
            except FileNotFoundError:
                pass
            self.acquired = False


def clean_old_runs(
    workspace: Path,
    older_than_days: int,
    *,
    now: datetime | None = None,
) -> list[Path]:
    """Delete only validated run-state directories older than the retention period."""
    if older_than_days < 1:
        raise ValueError("运行状态保留天数必须至少为 1")
    runs_root = workspace / ".investor-opinion-tracker" / "runs"
    if not runs_root.is_dir():
        return []
    threshold = (now or datetime.now(UTC)) - timedelta(days=older_than_days)
    removed: list[Path] = []
    for child in runs_root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        state_path = child / "run.json"
        try:
            state = ScheduledRunState.model_validate_json(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        identity = RunIdentity(job_id=state.job_id, cutoff=state.cutoff)
        if child.name != identity.directory_name or state.run_id != identity.run_id:
            continue
        if state.cutoff.tzinfo is None or threshold.tzinfo is None:
            continue
        if state.cutoff <= threshold:
            shutil.rmtree(child)
            removed.append(child)
    return removed
