from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, computed_field


class TraderProfile(BaseModel):
    style: Literal["short_term", "swing", "long_term", "mixed"] = "mixed"
    aggressiveness: Literal["conservative", "balanced", "aggressive"] = "balanced"
    max_loss_per_trade_pct: float = Field(default=0.5, gt=0, le=5)
    max_sector_risk_pct: float = Field(default=3.0, gt=0, le=20)
    account_value: float | None = Field(default=None, gt=0)


class RunRequest(BaseModel):
    user_url: HttpUrl
    lookback_days: int = Field(default=5, ge=1, le=365)
    qps: float = Field(default=1.0, gt=0, le=1.0)
    authorization_confirmed: bool = True
    as_of: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def user_id(self) -> str:
        return str(self.user_url).rstrip("/").split("/")[-1]


class TaskDraft(BaseModel):
    user_urls: list[HttpUrl] = Field(min_length=1)
    lookback_days: int = Field(default=5, ge=1, le=365)
    qps: float = Field(default=1.0, gt=0, le=1.0)
    report_type: Literal["daily", "weekly"] = "daily"
    trader_profile: TraderProfile = Field(default_factory=TraderProfile)
    authorization_confirmed: bool = True
    include_position_sizing: bool = False


class NormalizedPost(BaseModel):
    platform: str
    platform_post_id: str
    author_id: str
    author_name: str = ""
    published_at: datetime
    text: str
    url: str
    pinned: bool = False
    quoted_text: str | None = None


class Opinion(BaseModel):
    opinion_id: str
    post_id: str
    symbol: str | None = None
    topic: str
    stance: Literal["bullish", "bearish", "neutral", "ambiguous"]
    confidence: float = Field(ge=0, le=1)
    source_url: str
    published_at: datetime
    formal: bool = True


class OpinionChange(BaseModel):
    change_type: Literal["new", "confirmed", "strengthened", "weakened", "reversed", "invalidated"]
    previous_stance: str | None = None
    current_stance: str


class TradeCandidate(BaseModel):
    symbol: str | None
    topic: str
    score: float = Field(ge=0, le=100)
    state: Literal["active", "watch", "avoid"]
    evidence_level: Literal["A", "B", "C", "D"]
    rationale: list[str]
    data_complete: bool = True


class MarketSnapshot(BaseModel):
    symbol: str
    price: float
    previous_close: float
    change_pct: float
    volume_hands: int
    source: str = "TDX"
    verified_at: datetime


class FactEvidence(BaseModel):
    claim: str
    opinion_ids: list[str] = Field(min_length=1)
    source_url: HttpUrl
    source_type: Literal["company", "exchange", "regulator", "government", "filing"]
    verified_at: datetime


class VerificationSummary(BaseModel):
    market_status: Literal["verified", "not_required", "failed"] = "failed"
    fact_status: Literal["verified", "unverified"] = "unverified"
    market_snapshots: list[MarketSnapshot] = Field(default_factory=list)
    fact_evidence: list[FactEvidence] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    uncovered_opinion_ids: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ready_for_final(self) -> bool:
        return self.market_status in {"verified", "not_required"} and self.fact_status == "verified"


class CollectionResult(BaseModel):
    status: Literal["complete", "incomplete", "failed"]
    posts: list[NormalizedPost] = Field(default_factory=list)
    next_cursor: str | None = None
    warnings: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    status: Literal["complete", "incomplete", "failed"]
    posts_collected: int
    opinions: list[Opinion] = Field(default_factory=list)
    candidates: list[TradeCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    verification: VerificationSummary = Field(default_factory=VerificationSummary)
