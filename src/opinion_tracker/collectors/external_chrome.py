from __future__ import annotations

import json
import random
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

    def __init__(
        self,
        runner: Runner = _default_runner,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = lambda: random.uniform(0.25, 0.75),
    ):
        self.runner = runner
        self.sleeper = sleeper
        self.jitter = jitter
        self._has_requested = False

    def _pace(self, qps: float) -> None:
        if self._has_requested:
            self.sleeper((1 / qps) + max(0.0, self.jitter()))
        self._has_requested = True

    def _page(self, user_id: str, page: int) -> dict[str, Any]:
        script = (
            "(async()=>{const r=await fetch("
            f"'https://xueqiu.com/v4/statuses/user_timeline.json?page={page}&user_id={user_id}&count=20',"
            "{headers:{'Accept':'application/json, text/plain, */*','X-Requested-With':'XMLHttpRequest'},"
            "credentials:'include'});const text=await r.text();try{return JSON.parse(text)}catch(e){"
            "return {__tracker_error:/访问验证|滑块/.test(text)?'risk_verification':'invalid_response',"
            "__http_status:r.status}}})()"
        )
        return cast(dict[str, Any], json.loads(self.runner(["eval", script])))

    @staticmethod
    def _warning(payload: dict[str, Any]) -> str | None:
        description = str(payload.get("error_description") or payload.get("error") or "")
        if payload.get("__tracker_error") == "risk_verification" or re.search(
            r"访问验证|滑块|人机验证|风控", description
        ):
            return "雪球访问验证：需要人工完成滑块，已停止采集"
        if payload.get("login_required") or re.search(r"需要登录|请先登录|登录失效", description):
            return "雪球登录失效：请在任务使用的浏览器中重新登录"
        if payload.get("__tracker_error") or payload.get("error_code"):
            status = payload.get("__http_status") or payload.get("error_code")
            return f"雪球接口异常：状态 {status}"
        return None

    def collect(self, request: RunRequest, cursor: str | None = None) -> CollectionResult:
        if not request.authorization_confirmed:
            return CollectionResult(status="failed", warnings=["缺少授权声明"])
        self.runner(["open", str(request.user_url)])
        cutoff = (request.as_of or datetime.now(UTC)) - timedelta(days=request.lookback_days)
        if request.since is not None:
            cutoff = max(cutoff, request.since)
        cutoff_ms = cutoff.timestamp() * 1000
        page = int(cursor or 1)
        ordered: list[NormalizedPost] = []
        seen: set[str] = set()
        try:
            while True:
                self._pace(request.qps)
                payload = self._page(request.user_id, page)
                warning = self._warning(payload)
                if warning:
                    return CollectionResult(
                        status="incomplete" if ordered else "failed",
                        posts=ordered,
                        next_cursor=str(page),
                        warnings=[warning],
                    )
                statuses = payload.get("statuses", [])
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
