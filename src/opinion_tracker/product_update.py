from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal


def update_status(repository: Path) -> str:
    subprocess.run(["git", "fetch", "origin", "main"], cwd=repository, check=True, capture_output=True)
    local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    remote = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=repository, text=True).strip()
    if local == remote:
        return "current"
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", local, remote],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if ancestry.returncode == 0:
        return "update_available"
    raise RuntimeError("产品 main 分支领先或已经分叉，拒绝定时自动更新")


def require_clean_repository(repository: Path) -> None:
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repository, text=True).strip():
        raise RuntimeError("产品仓库存在未提交改动，拒绝自动更新")


def update_product(repository: Path) -> None:
    require_clean_repository(repository)
    subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=repository, check=True)


def install_product(repository: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", f"{repository.resolve()}[mcp]"],
        check=True,
    )


def ensure_latest_product(
    repository: Path,
    executable: Path,
    argv: list[str],
    *,
    installer: Callable[[Path], None] = install_product,
    reexec: Callable[[str, list[str]], object] = os.execv,
) -> Literal["current", "updated"]:
    """Fail closed unless the scheduled process runs clean, current product code."""
    require_clean_repository(repository)
    if update_status(repository) == "current":
        return "current"
    update_product(repository)
    installer(repository)
    executable_text = str(executable)
    reexec(executable_text, [executable_text, *argv])
    return "updated"
