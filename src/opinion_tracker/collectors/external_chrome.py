from __future__ import annotations

import json
import random
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import unescape
from typing import Any, cast

from ..run_state import RunStateStore, UserPageState
from ..schemas import CollectionResult, NormalizedPost, RunRequest

Runner = Callable[[list[str]], str]


@dataclass(frozen=True)
class RetryPolicy:
    max_wait_seconds: float = 600
    max_pages: int = 300


def retry_delay(
    attempt: int, retry_after: float | None, remaining: float
) -> float | None:
    schedule = (5, 10, 20, 40, 60, 120)
    desired = retry_after if retry_after is not None else schedule[min(attempt, len(schedule) - 1)]
    return desired if 0 <= desired <= remaining else None


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
            "credentials:'include'});const text=await r.text();try{const data=JSON.parse(text);"
            "return {...data,__http_status:r.status,__retry_after:r.headers.get('retry-after')}}catch(e){"
            "return {__tracker_error:/访问验证|滑块/.test(text)?'risk_verification':'invalid_response',"
            "__http_status:r.status,__retry_after:r.headers.get('retry-after')}}})()"
        )
        return cast(dict[str, Any], json.loads(self.runner(["eval", script])))

    @staticmethod
    def _retryable(payload: dict[str, Any]) -> bool:
        status = payload.get("__http_status")
        return isinstance(status, int) and (status in {405, 429} or 500 <= status <= 599)

    @staticmethod
    def _retry_after(payload: dict[str, Any]) -> float | None:
        value = payload.get("__retry_after")
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _normalized_posts(
        statuses: list[dict[str, Any]], request: RunRequest, cutoff_ms: float, seen: set[str]
    ) -> list[NormalizedPost]:
        normalized = []
        for raw in statuses:
            identity = str(raw.get("id", ""))
            created_at = raw.get("created_at", 0)
            if not identity or identity in seen or created_at < cutoff_ms:
                continue
            seen.add(identity)
            normalized.append(
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
        return normalized

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
                ordered.extend(self._normalized_posts(statuses, request, cutoff_ms, seen))
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

    def collect_resumable(
        self,
        request: RunRequest,
        store: RunStateStore,
        user_state: UserPageState,
        policy: RetryPolicy | None = None,
    ) -> CollectionResult:
        if not request.authorization_confirmed:
            return CollectionResult(status="failed", warnings=["缺少授权声明"])
        active_policy = policy or RetryPolicy()
        self.runner(["open", str(request.user_url)])
        cutoff = (request.as_of or datetime.now(UTC)) - timedelta(days=request.lookback_days)
        if request.since is not None:
            cutoff = max(cutoff, request.since)
        cutoff_ms = cutoff.timestamp() * 1000
        existing = [post for post in store.posts() if post.author_id == request.user_id]
        seen = {post.platform_post_id for post in store.posts()}
        page = user_state.next_page
        waited = 0.0
        retry_attempt = 0
        user_state.status = "running"
        store.save_user(user_state)
        try:
            while True:
                if user_state.pages_fetched >= active_policy.max_pages:
                    warning = f"达到单账号最大分页预算 {active_policy.max_pages} 页"
                    user_state.status = "incomplete"
                    user_state.last_error = warning
                    store.save_user(user_state)
                    return CollectionResult(
                        status="incomplete", posts=existing, next_cursor=str(page), warnings=[warning]
                    )
                self._pace(request.qps)
                payload = self._page(request.user_id, page)
                user_state.request_count += 1
                if self._retryable(payload):
                    remaining = active_policy.max_wait_seconds - waited
                    delay = retry_delay(
                        retry_attempt, self._retry_after(payload), remaining
                    )
                    status = int(payload["__http_status"])
                    if delay is None:
                        warning = (
                            f"雪球接口状态 {status}，已耗尽 "
                            f"{active_policy.max_wait_seconds:g} 秒重试预算"
                        )
                        user_state.status = "incomplete"
                        user_state.last_error = warning
                        user_state.last_http_status = status
                        store.save_user(user_state)
                        return CollectionResult(
                            status=user_state.status,
                            posts=existing,
                            next_cursor=str(page),
                            warnings=[warning],
                        )
                    user_state.retry_count += 1
                    user_state.last_error = f"雪球接口状态 {status}，等待后重试"
                    user_state.last_http_status = status
                    store.save_user(user_state)
                    self.sleeper(delay + max(0.0, self.jitter()))
                    waited += delay
                    retry_attempt += 1
                    self.runner(["open", str(request.user_url)])
                    continue
                page_warning = self._warning(payload)
                if page_warning:
                    user_state.status = "incomplete"
                    user_state.last_error = page_warning
                    page_status = payload.get("__http_status")
                    user_state.last_http_status = (
                        page_status if isinstance(page_status, int) else None
                    )
                    store.save_user(user_state)
                    return CollectionResult(
                        status="incomplete" if existing else "failed",
                        posts=existing,
                        next_cursor=str(page),
                        warnings=[page_warning],
                    )
                statuses = payload.get("statuses", [])
                if not statuses:
                    user_state.status = "complete"
                    store.save_user(user_state)
                    return CollectionResult(status="complete", posts=existing)
                new_posts = self._normalized_posts(statuses, request, cutoff_ms, seen)
                store.merge_posts(new_posts)
                existing.extend(new_posts)
                regular = [status for status in statuses if not _is_pinned(status)]
                if regular:
                    user_state.oldest_regular_at = datetime.fromtimestamp(
                        regular[-1].get("created_at", 0) / 1000, tz=UTC
                    )
                user_state.pages_fetched += 1
                page += 1
                user_state.next_page = page
                user_state.last_error = None
                user_state.last_http_status = None
                retry_attempt = 0
                store.save_user(user_state)
                if not should_continue_page(statuses, cutoff_ms):
                    user_state.status = "complete"
                    store.save_user(user_state)
                    return CollectionResult(status="complete", posts=existing)
        except Exception as exc:
            warning = f"{type(exc).__name__}: {exc}"
            user_state.status = "incomplete"
            user_state.last_error = warning
            store.save_user(user_state)
            return CollectionResult(
                status="incomplete" if existing else "failed",
                posts=existing,
                next_cursor=str(page),
                warnings=[warning],
            )
