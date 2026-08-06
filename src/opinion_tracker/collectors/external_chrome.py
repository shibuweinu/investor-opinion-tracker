from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from html import unescape
from typing import Any, cast

from ..schemas import CollectionResult, NormalizedPost, RunRequest

Runner = Callable[[list[str]], str]


def _default_runner(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["agent-browser", "--cdp", "9222", *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 agent-browser；请先安装并启动外置 Chrome 调试模式") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "agent-browser 调用失败")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return "\n".join(line for line in lines if not line.startswith(("✓", "Done")))


def _clean(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value)).replace(" ", " ").strip()


def _is_pinned(status: dict[str, Any]) -> bool:
    return bool(status.get("pinned") or status.get("is_pinned") or status.get("is_top"))


def should_continue_page(statuses: list[dict[str, Any]], cutoff_ms: float) -> bool:
    regular = [status for status in statuses if not _is_pinned(status)]
    return bool(regular) and regular[-1].get("created_at", 0) >= cutoff_ms


class ExternalChromeXueqiuCollector:
    """Portable Xueqiu collector using the user's authenticated external Chrome session."""

    def __init__(self, runner: Runner = _default_runner, sleeper: Callable[[float], None] = time.sleep):
        self.runner = runner
        self.sleeper = sleeper

    def _page(self, user_id: str, page: int) -> dict[str, Any]:
        script = (
            "(async()=>{const r=await fetch("
            f"'https://xueqiu.com/v4/statuses/user_timeline.json?page={page}&user_id={user_id}&count=20',"
            "{headers:{'Accept':'application/json, text/plain, */*','X-Requested-With':'XMLHttpRequest'},"
            "credentials:'include'});return await r.json()})()"
        )
        return cast(dict[str, Any], json.loads(self.runner(["eval", script])))

    def collect(self, request: RunRequest, cursor: str | None = None) -> CollectionResult:
        if not request.authorization_confirmed:
            return CollectionResult(status="failed", warnings=["缺少授权声明"])
        self.runner(["open", str(request.user_url)])
        cutoff = (request.as_of or datetime.now(UTC)) - timedelta(days=request.lookback_days)
        cutoff_ms = cutoff.timestamp() * 1000
        page, ordered, seen = int(cursor or 1), [], set()
        try:
            while True:
                if page > int(cursor or 1):
                    self.sleeper(1 / request.qps)
                statuses = self._page(request.user_id, page).get("statuses", [])
                if not statuses:
                    break
                for raw in statuses:
                    identity = str(raw.get("id", ""))
                    created_at = raw.get("created_at", 0)
                    if not identity or identity in seen or created_at < cutoff_ms:
                        continue
                    seen.add(identity)
                    ordered.append(
                        NormalizedPost(
                            platform="xueqiu",
                            platform_post_id=identity,
                            author_id=str(raw.get("user_id") or request.user_id),
                            author_name=str(raw.get("user", {}).get("screen_name", "")),
                            published_at=datetime.fromtimestamp(created_at / 1000, tz=UTC),
                            text=_clean(str(raw.get("description") or raw.get("text") or "")),
                            url=f"https://xueqiu.com/{request.user_id}/{identity}",
                            pinned=_is_pinned(raw),
                        )
                    )
                if not should_continue_page(statuses, cutoff_ms):
                    break
                page += 1
            return CollectionResult(status="complete", posts=ordered)
        except Exception as exc:
            return CollectionResult(
                status="incomplete" if ordered else "failed",
                posts=ordered,
                next_cursor=str(page),
                warnings=[f"{type(exc).__name__}: {exc}"],
            )
