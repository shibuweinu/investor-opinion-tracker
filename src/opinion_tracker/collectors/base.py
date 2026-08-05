from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from ..schemas import CollectionResult, RunRequest


class Collector(Protocol):
    def collect(self, request: RunRequest, cursor: str | None = None) -> CollectionResult: ...


class PaginationState:
    @staticmethod
    def should_continue(items: list[dict[str, Any]], start_at: datetime) -> bool:
        regular = [item for item in items if not item.get("pinned", False)]
        if not regular:
            return False
        final = datetime.fromisoformat(str(regular[-1]["published_at"]).replace("Z", "+00:00"))
        return final >= start_at
