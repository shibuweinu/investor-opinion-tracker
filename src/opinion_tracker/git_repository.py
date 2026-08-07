from __future__ import annotations

import re
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


class GitConflictError(GitError):
    pass


def canonicalize_remote(url: str) -> str:
    value = re.sub(r"^git@([^:]+):", r"\1/", url)
    value = re.sub(r"^https?://", "", value).rstrip("/")
    return value[:-4] if value.endswith(".git") else value


class GitRepository:
    def __init__(self, remote_url: str, path: Path, timeout: int = 15):
        self.remote_url, self.path, self.timeout = remote_url, path, timeout

    def _run(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        try:
            result = subprocess.run(
                ["git", *args], cwd=cwd or self.path, check=check,
                capture_output=True, text=True, timeout=self.timeout,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise GitError(str(exc)) from exc
        return result.stdout.strip()

    def clone_or_open(self) -> None:
        if (self.path / ".git").exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._run("clone", self.remote_url, str(self.path), cwd=self.path.parent)
        self._run("config", "user.name", "Investor Opinion Tracker")
        self._run("config", "user.email", "config-sync@localhost")

    def write(self, relative: str, content: str) -> None:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def head(self) -> str:
        return self._run("rev-parse", "HEAD")

    def remote_head(self) -> str | None:
        output = self._run("ls-remote", "origin", "refs/heads/main")
        return output.split()[0] if output else None

    def commit(self, files: list[str], message: str) -> None:
        self._run("add", "--", *files)
        self._run("commit", "-m", message)

    def fetch(self) -> None:
        self._run("fetch", "origin")

    def is_ancestor(self, older: str, newer: str) -> bool:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer], cwd=self.path,
            capture_output=True, timeout=self.timeout,
        )
        return result.returncode == 0

    def push_fast_forward(self) -> None:
        remote = self.remote_head()
        if remote and not self.is_ancestor(remote, self.head()):
            raise GitConflictError("远端历史已变化，拒绝强制推送")
        try:
            self._run("push", "origin", "HEAD:main")
        except GitError as exc:
            raise GitConflictError("远端拒绝快进推送") from exc

    def update_fast_forward(self) -> bool:
        before = self.head()
        self.fetch()
        remote = self._run("rev-parse", "origin/main")
        if before == remote:
            return False
        if not self.is_ancestor(before, remote):
            raise GitConflictError("本地和远端配置历史已分叉")
        self._run("merge", "--ff-only", "origin/main")
        return True

    def canonical_remote(self) -> str:
        return canonicalize_remote(self.remote_url)
