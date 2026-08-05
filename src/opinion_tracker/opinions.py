from __future__ import annotations

import hashlib
import re
from typing import Literal

from .schemas import NormalizedPost, Opinion, OpinionChange

SYMBOL = re.compile(r"\((?:SH|SZ|HK)(\d{5,6})\)|\b((?:SH|SZ|HK)\d{5,6})\b", re.I)


def extract_opinions(posts: list[NormalizedPost]) -> list[Opinion]:
    results = []
    for post in posts:
        text = post.text
        match = SYMBOL.search(text)
        symbol = None
        if match:
            symbol = match.group(0).strip("()").upper()
        bullish = any(word in text for word in ("看好", "增持", "买入", "机会", "低估"))
        bearish = any(word in text for word in ("看空", "减持", "卖出", "高估", "风险"))
        stance: Literal["bullish", "bearish", "neutral", "ambiguous"] = (
            "bullish" if bullish and not bearish else "bearish" if bearish and not bullish else "ambiguous"
        )
        formal = stance != "ambiguous" and not any(word in text for word in ("转发", "据说", "开玩笑"))
        results.append(
            Opinion(
                opinion_id=hashlib.sha256(
                    f"{post.platform}:{post.platform_post_id}:{symbol}".encode()
                ).hexdigest()[:16],
                post_id=post.platform_post_id,
                symbol=symbol,
                topic=symbol or "未映射主题",
                stance=stance,
                confidence=0.8 if symbol and formal else 0.45,
                source_url=post.url,
                published_at=post.published_at,
                formal=formal,
            )
        )
    return results


def transition(previous: Opinion | None, current: Opinion) -> OpinionChange:
    change: Literal["new", "confirmed", "strengthened", "weakened", "reversed", "invalidated"]
    if previous is None:
        change = "new"
    elif not current.formal:
        change = "invalidated"
    elif previous.stance != current.stance:
        change = "reversed"
    elif current.confidence > previous.confidence:
        change = "strengthened"
    elif current.confidence < previous.confidence:
        change = "weakened"
    else:
        change = "confirmed"
    return OpinionChange(
        change_type=change,
        previous_stance=previous.stance if previous else None,
        current_stance=current.stance,
    )
