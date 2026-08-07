from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol

from .market import TdxClient, TdxDailyBar, TdxQuote
from .schemas import (
    FactEvidence,
    MarketSnapshot,
    NormalizedPost,
    Opinion,
    ResearchClaim,
    VerificationSummary,
)

MARKET_SYMBOL = re.compile(r"(?:SH|SZ)\d{6}", re.I)


class MarketClient(Protocol):
    def quotes(self, codes: list[str]) -> list[TdxQuote]: ...

    def daily_closes(self, codes: list[str], as_of: datetime) -> list[TdxDailyBar]: ...


def verify_research(
    opinions: list[Opinion],
    research_claims: list[ResearchClaim],
    fact_evidence: list[FactEvidence],
    client: MarketClient | None = None,
    posts: list[NormalizedPost] | None = None,
    market_as_of: datetime | None = None,
) -> VerificationSummary:
    formal_ids = {opinion.opinion_id for opinion in opinions if opinion.formal}
    known_ids = {opinion.opinion_id for opinion in opinions}
    classified_ids = {
        opinion_id
        for claim in research_claims
        for opinion_id in claim.opinion_ids
        if opinion_id in known_ids
    }
    uncovered_opinions = sorted(formal_ids - classified_ids)
    factual_ids = {claim.claim_id for claim in research_claims if claim.kind == "factual"}
    evidenced_ids = {claim_id for evidence in fact_evidence for claim_id in evidence.claim_ids}
    uncovered_claims = sorted(factual_ids - evidenced_ids)
    unsupported_opinion_ids = {
        opinion_id
        for claim in research_claims
        if claim.claim_id in uncovered_claims
        for opinion_id in claim.opinion_ids
    }
    excluded_opinion_ids = sorted(set(uncovered_opinions) | unsupported_opinion_ids)
    included_opinion_ids = sorted(formal_ids - set(excluded_opinion_ids))
    included_post_ids = {
        opinion.post_id for opinion in opinions if opinion.opinion_id in included_opinion_ids
    }
    included_claims = [
        claim
        for claim in research_claims
        if claim.claim_id not in uncovered_claims
        and any(opinion_id in included_opinion_ids for opinion_id in claim.opinion_ids)
    ]
    symbols = sorted(
        {
            symbol
            for opinion in opinions
            for symbol in ([opinion.symbol] if opinion.symbol else [])
            if opinion.opinion_id in included_opinion_ids and symbol.startswith(("SH", "SZ"))
        }
        | {
            symbol.upper()
            for claim in included_claims
            for symbol in claim.symbols
            if symbol.upper().startswith(("SH", "SZ"))
        }
        | {
            symbol.upper()
            for post in posts or []
            if post.platform_post_id in included_post_ids
            for symbol in MARKET_SYMBOL.findall(post.text)
        }
    )
    snapshots: list[MarketSnapshot] = []
    errors: list[str] = []
    market_status = "not_required"
    if symbols:
        market_status = "failed"
        try:
            active_client = client or TdxClient()
            by_code: dict[str, TdxDailyBar | TdxQuote]
            if market_as_of is not None:
                bars = active_client.daily_closes(
                    [symbol[2:] for symbol in symbols], market_as_of
                )
                by_code = {bar.code: bar for bar in bars}
            else:
                quotes = active_client.quotes([symbol[2:] for symbol in symbols])
                by_code = {quote.code: quote for quote in quotes}
            missing = [symbol for symbol in symbols if symbol[2:] not in by_code]
            if missing:
                errors.append(f"TDX 未返回行情：{', '.join(missing)}")
            else:
                verified_at = datetime.now().astimezone()
                for symbol in symbols:
                    item = by_code[symbol[2:]]
                    price = item.close if isinstance(item, TdxDailyBar) else item.price
                    change_pct = (
                        (price / item.previous_close - 1) * 100 if item.previous_close else 0.0
                    )
                    snapshots.append(
                        MarketSnapshot(
                            symbol=symbol,
                            price=price,
                            previous_close=item.previous_close,
                            change_pct=round(change_pct, 2),
                            volume_hands=item.volume_hands,
                            source="TDX daily" if isinstance(item, TdxDailyBar) else "TDX quote",
                            market_time=item.time if isinstance(item, TdxDailyBar) else verified_at,
                            verified_at=verified_at,
                        )
                    )
                market_status = "verified"
        except Exception as exc:  # network and upstream payload errors are recoverable
            errors.append(f"TDX 行情核验失败：{exc}")
    if uncovered_opinions:
        errors.append(f"缺少语义归类的正式观点：{', '.join(uncovered_opinions)}")
    if uncovered_claims:
        errors.append(f"缺少独立事实证据的事实主张：{', '.join(uncovered_claims)}")
    covered_count = len(formal_ids) - len(uncovered_opinions)
    semantic_status = (
        "verified"
        if not uncovered_opinions
        else "partially_verified"
        if covered_count
        else "unverified"
    )
    supported_factual_count = len(factual_ids) - len(uncovered_claims)
    fact_status = (
        "verified"
        if not uncovered_claims
        else "partially_verified"
        if supported_factual_count
        else "unverified"
    )
    exclusion_reasons = {
        opinion_id: "缺少语义归因，已从观点分析、共识和候选中排除"
        for opinion_id in uncovered_opinions
    }
    for opinion_id in unsupported_opinion_ids:
        exclusion_reasons[opinion_id] = "关联事实主张缺少独立证据，已从候选中排除"
    return VerificationSummary(
        market_status=market_status,  # type: ignore[arg-type]
        semantic_status=semantic_status,
        fact_status=fact_status,
        market_snapshots=snapshots,
        research_claims=research_claims,
        fact_evidence=fact_evidence,
        errors=errors,
        uncovered_opinion_ids=uncovered_opinions,
        uncovered_claim_ids=uncovered_claims,
        included_opinion_ids=included_opinion_ids,
        excluded_opinion_ids=excluded_opinion_ids,
        excluded_claim_ids=uncovered_claims,
        exclusion_reasons=exclusion_reasons,
    )
