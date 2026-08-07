from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from .schemas import NormalizedPost

Kind = Literal["opinion", "reply_opinion", "trade_disclosure", "forward", "question", "context"]
SIGNALS = (
    "看好",
    "看空",
    "利好",
    "利空",
    "机会",
    "风险",
    "反弹",
    "筑底",
    "增长",
    "景气",
    "估值",
    "毛利",
    "扩张",
    "内卷",
    "强度",
    "趋势",
)
TRADES = ("买了", "买入", "卖了", "卖出", "仓位", "持有", "增持", "减持")
TOPICS = ("创新药", "医药", "软件", "硬件", "消费", "红利", "黄金", "云服务", "CPO", "AI", "半导体", "机器人")
SYMBOL = re.compile(r"(?:SH|SZ)\d{6}|HK\d{5}", re.I)


class ClassifiedPost(BaseModel):
    kind: Kind
    formal: bool
    reason: str


class EvidenceItem(BaseModel):
    post_id: str
    author_id: str
    published_at: str
    source_url: str
    text: str
    kind: Kind
    explicit_symbols: list[str] = Field(default_factory=list)
    topic_hints: list[str] = Field(default_factory=list)
    classification_reason: str


class EvidencePack(BaseModel):
    total_posts: int
    data_complete: bool
    author_counts: dict[str, int]
    evidence: list[EvidenceItem]
    context_posts: int
    include_position_sizing: bool = False


def classify_post(post: NormalizedPost) -> ClassifiedPost:
    text = post.text.strip()
    if not text:
        return ClassifiedPost(kind="context", formal=False, reason="空文本")
    if text in {"转发", "转发微博"}:
        return ClassifiedPost(kind="forward", formal=False, reason="纯转发")
    if any(word in text for word in TRADES):
        return ClassifiedPost(kind="trade_disclosure", formal=True, reason="包含交易或持仓披露")
    has_signal = any(word in text for word in SIGNALS)
    if text.startswith("回复@") and has_signal:
        return ClassifiedPost(kind="reply_opinion", formal=True, reason="回复中包含明确投资判断")
    if has_signal:
        return ClassifiedPost(kind="opinion", formal=True, reason="包含明确方向或基本面判断")
    if ("？" in text or "?" in text) and any(word in text for word in ("怎么", "可以", "是不是", "请教")):
        return ClassifiedPost(kind="question", formal=False, reason="提问而非作者判断")
    return ClassifiedPost(kind="context", formal=False, reason="未检测到足够明确的投资判断")


def build_evidence_pack(
    posts: list[NormalizedPost], complete: bool, include_position_sizing: bool = False
) -> EvidencePack:
    evidence = []
    for post in posts:
        classified = classify_post(post)
        if not classified.formal:
            continue
        evidence.append(
            EvidenceItem(
                post_id=post.platform_post_id,
                author_id=post.author_id,
                published_at=post.published_at.isoformat(),
                source_url=post.url,
                text=post.text,
                kind=classified.kind,
                explicit_symbols=sorted(set(item.upper() for item in SYMBOL.findall(post.text))),
                topic_hints=[topic for topic in TOPICS if topic.lower() in post.text.lower()],
                classification_reason=classified.reason,
            )
        )
    return EvidencePack(
        total_posts=len(posts),
        data_complete=complete,
        author_counts=dict(Counter(post.author_id for post in posts)),
        evidence=evidence,
        context_posts=len(posts) - len(evidence),
        include_position_sizing=include_position_sizing,
    )
