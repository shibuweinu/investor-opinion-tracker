from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol

from .market import TdxClient, TdxQuote
from .schemas import (
    FactEvidence,
    MarketSnapshot,
    NormalizedPost,
    Opinion,
    ResearchClaim,
    VerificationSummary,
)

MARKET_SYMBOL = re.compile(r"(?:SH|SZ)\d{6}", re.I)


class QuoteClient(Protocol):
    def quotes(self, codes: list[str]) -> list[TdxQuote]: ...


def verify_research(
    opinions: list[Opinion],
    research_claims: list[ResearchClaim],
    fact_evidence: list[FactEvidence],
    client: QuoteClient | None = None,
    posts: list[NormalizedPost] | None = None,
) -> VerificationSummary:
    symbols = sorted(
        {
            symbol
            for opinion in opinions
            for symbol in ([opinion.symbol] if opinion.symbol else [])
            if symbol.startswith(("SH", "SZ"))
        }
        | {
            symbol.upper()
            for claim in research_claims
            for symbol in claim.symbols
            if symbol.upper().startswith(("SH", "SZ"))
        }
        | {
            symbol.upper()
            for post in posts or []
            for symbol in MARKET_SYMBOL.findall(post.text)
        }
    )
    snapshots: list[MarketSnapshot] = []
    errors: list[str] = []
    market_status = "not_required"
    if symbols:
        market_status = "failed"
        try:
            quotes = (client or TdxClient()).quotes([symbol[2:] for symbol in symbols])
            by_code = {quote.code: quote for quote in quotes}
            missing = [symbol for symbol in symbols if symbol[2:] not in by_code]
            if missing:
                errors.append(f"TDX 未返回行情：{', '.join(missing)}")
            else:
                verified_at = datetime.now().astimezone()
                for symbol in symbols:
                    quote = by_code[symbol[2:]]
                    change_pct = (
                        (quote.price / quote.previous_close - 1) * 100 if quote.previous_close else 0.0
                    )
                    snapshots.append(
                        MarketSnapshot(
                            symbol=symbol,
                            price=quote.price,
                            previous_close=quote.previous_close,
                            change_pct=round(change_pct, 2),
                            volume_hands=quote.volume_hands,
                            verified_at=verified_at,
                        )
                    )
                market_status = "verified"
        except Exception as exc:  # network and upstream payload errors are recoverable
            errors.append(f"TDX 行情核验失败：{exc}")
    formal_ids = {opinion.opinion_id for opinion in opinions if opinion.formal}
    classified_ids = {opinion_id for claim in research_claims for opinion_id in claim.opinion_ids}
    uncovered_opinions = sorted(formal_ids - classified_ids)
    if uncovered_opinions:
        errors.append(f"缺少语义归类的正式观点：{', '.join(uncovered_opinions)}")
    factual_ids = {claim.claim_id for claim in research_claims if claim.kind == "factual"}
    evidenced_ids = {claim_id for evidence in fact_evidence for claim_id in evidence.claim_ids}
    uncovered_claims = sorted(factual_ids - evidenced_ids)
    if uncovered_claims:
        errors.append(f"缺少独立事实证据的事实主张：{', '.join(uncovered_claims)}")
    return VerificationSummary(
        market_status=market_status,  # type: ignore[arg-type]
        semantic_status="verified" if research_claims and not uncovered_opinions else "unverified",
        fact_status="verified" if not uncovered_claims else "unverified",
        market_snapshots=snapshots,
        research_claims=research_claims,
        fact_evidence=fact_evidence,
        errors=errors,
        uncovered_opinion_ids=uncovered_opinions,
        uncovered_claim_ids=uncovered_claims,
    )
