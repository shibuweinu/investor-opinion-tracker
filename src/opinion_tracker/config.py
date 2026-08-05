from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .schemas import TraderProfile


class Settings(BaseModel):
    timezone: str = "Asia/Shanghai"
    default_lookback_days: int = 5
    xueqiu_qps: float = 1.0
    authorization_confirmed: bool = True
    trader_profile: TraderProfile = TraderProfile()

    @classmethod
    def load(cls, workspace: Path) -> Settings:
        path = workspace / ".investor-opinion-tracker" / "config.json"
        return cls.model_validate_json(path.read_text()) if path.exists() else cls()

    def save(self, workspace: Path) -> Path:
        directory = workspace / ".investor-opinion-tracker"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "config.json"
        path.write_text(json.dumps(self.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
