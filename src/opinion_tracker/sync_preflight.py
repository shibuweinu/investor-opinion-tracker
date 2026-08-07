from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


class PreflightService(Protocol):
    def update(self) -> bool: ...
    def document(self) -> object: ...
    def apply_trusted(self) -> None: ...
    def ensure_local(self, *, trusted: bool) -> None: ...


@dataclass
class PreflightResult:
    action: Literal["run", "confirmation_required", "run_last_confirmed_with_alert"]
    message: str = ""


def preflight_scheduled_run(service: PreflightService, *, locally_trusted: bool) -> PreflightResult:
    try:
        changed = service.update()
        if not changed:
            service.ensure_local(trusted=locally_trusted)
            return PreflightResult("run")
        document = service.document()
        requested = bool(
            getattr(document, "trusted_auto_apply", False)
            or getattr(getattr(document, "sync", None), "trusted_auto_apply", False)
        )
        if requested and locally_trusted:
            service.apply_trusted()
            return PreflightResult("run", "已自动应用可信远端配置")
        return PreflightResult("confirmation_required", "远端执行配置已变化")
    except Exception as exc:
        return PreflightResult("run_last_confirmed_with_alert", f"远端同步失败：{exc}")
