from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .market import TdxClient, TdxQuote
from .schemas import FactEvidence, MarketSnapshot, Opinion, VerificationSummary


class QuoteClient(Protocol):
    def quotes(self, codes: list[str]) -> list[TdxQuote]: ...


def verify_research(
    opinions: list[Opinion],
    fact_evidence: list[FactEvidence],
    client: QuoteClient | None = None,
) -> VerificationSummary:
    symbols = sorted(
        {
            opinion.symbol
            for opinion in opinions
            if opinion.formal and opinion.symbol and opinion.symbol.startswith(("SH", "SZ"))
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
    covered_ids = {opinion_id for evidence in fact_evidence for opinion_id in evidence.opinion_ids}
    uncovered = sorted(formal_ids - covered_ids)
    if uncovered:
        errors.append(f"缺少独立事实证据的观点：{', '.join(uncovered)}")
    return VerificationSummary(
        market_status=market_status,  # type: ignore[arg-type]
        fact_status="verified" if not uncovered else "unverified",
        market_snapshots=snapshots,
        fact_evidence=fact_evidence,
        errors=errors,
        uncovered_opinion_ids=uncovered,
    )
