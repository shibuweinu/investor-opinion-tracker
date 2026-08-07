from __future__ import annotations

import subprocess
from pathlib import Path


def update_status(repository: Path) -> str:
    subprocess.run(["git", "fetch", "origin", "main"], cwd=repository, check=True, capture_output=True)
    local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    remote = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=repository, text=True).strip()
    return "current" if local == remote else "update_available"


def update_product(repository: Path) -> None:
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=repository, text=True).strip():
        raise RuntimeError("产品仓库存在未提交改动，拒绝自动更新")
    subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=repository, check=True)
