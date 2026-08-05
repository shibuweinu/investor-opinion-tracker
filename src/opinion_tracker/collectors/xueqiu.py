from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from html import unescape
from typing import Any, Protocol

from ..schemas import CollectionResult, NormalizedPost, RunRequest


class BrowserPort(Protocol):
    def fetch_timeline(self, user_id: str, page: int, count: int) -> dict[str, Any]: ...


def _clean_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value)).strip()


class XueqiuCollector:
    def __init__(self, browser: BrowserPort, sleeper: Callable[[float], None] = time.sleep):
        self.browser, self.sleeper = browser, sleeper

    def collect(self, request: RunRequest, cursor: str | None = None) -> CollectionResult:
        if not request.authorization_confirmed:
            return CollectionResult(status="failed", warnings=["缺少授权声明"])
        start = (request.as_of or datetime.now(UTC)) - timedelta(days=request.lookback_days)
        page = int(cursor or 1)
        posts: list[NormalizedPost] = []
        warnings: list[str] = []
        try:
            while True:
                if page > int(cursor or 1):
                    self.sleeper(1 / request.qps)
                payload = self.browser.fetch_timeline(request.user_id, page, 20)
                if payload.get("login_required"):
                    return CollectionResult(status="failed", next_cursor=str(page), warnings=["需要登录雪球"])
                items = payload.get("list", [])
                for raw in items:
                    published = datetime.fromtimestamp(raw["created_at"] / 1000, tz=UTC)
                    if published < start and not raw.get("pinned"):
                        continue
                    user = raw.get("user", {})
                    posts.append(
                        NormalizedPost(
                            platform="xueqiu",
                            platform_post_id=str(raw["id"]),
                            author_id=str(user.get("id", request.user_id)),
                            author_name=user.get("screen_name", ""),
                            published_at=published,
                            text=_clean_html(raw.get("text", "")),
                            url=f"https://xueqiu.com/{request.user_id}/{raw['id']}",
                            pinned=bool(raw.get("pinned")),
                        )
                    )
                if not payload.get("next_max_id"):
                    break
                page += 1
            unique = {(p.platform, p.platform_post_id): p for p in posts}
            return CollectionResult(status="complete", posts=list(unique.values()), warnings=warnings)
        except Exception as exc:
            return CollectionResult(
                status="incomplete" if posts else "failed",
                posts=posts,
                next_cursor=str(page),
                warnings=[type(exc).__name__],
            )
