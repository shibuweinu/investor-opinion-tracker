from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

Payload = dict[str, Any]
Transport = Callable[[str, dict[str, str], float], Payload]


def _transport(url: str, headers: dict[str, str], timeout: float) -> Payload:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return cast(Payload, json.loads(response.read().decode("utf-8")))


@dataclass(frozen=True)
class TdxQuote:
    code: str
    price: float
    previous_close: float
    open: float
    high: float
    low: float
    volume_hands: int
    amount: int


@dataclass(frozen=True)
class TdxDailyBar:
    code: str
    time: datetime
    close: float
    previous_close: float
    open: float
    high: float
    low: float
    volume_hands: int
    amount: int


class TdxClient:
    """Built-in A-share client; no external tdx-api Skill installation is required."""

    def __init__(
        self,
        base_url: str = "http://tdx.acdzh.xyz",
        timeout: float = 10,
        transport: Transport = _transport,
    ):
        self.base_url, self.timeout, self.transport = base_url.rstrip("/"), timeout, transport
        self.headers = {"User-Agent": "Mozilla/5.0"}

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        suffix = f"?{urlencode(params)}" if params else ""
        payload = self.transport(f"{self.base_url}{path}{suffix}", self.headers, self.timeout)
        if payload.get("code") != 0:
            raise RuntimeError(str(payload.get("message", "TDX API error")))
        return payload["data"]

    def server_status(self) -> Payload:
        return cast(Payload, self._get("/api/server-status"))

    def quotes(self, codes: list[str]) -> list[TdxQuote]:
        rows = self._get("/api/quote", {"code": ",".join(codes)})
        result = []
        for row in rows:
            candle = row["K"]
            result.append(
                TdxQuote(
                    code=str(row["Code"]),
                    price=candle["Close"] / 1000,
                    previous_close=candle["Last"] / 1000,
                    open=candle.get("Open", candle["Close"]) / 1000,
                    high=candle.get("High", candle["Close"]) / 1000,
                    low=candle.get("Low", candle["Close"]) / 1000,
                    volume_hands=int(row.get("TotalHand", 0)),
                    amount=int(row.get("Amount", 0)),
                )
            )
        return result

    def daily_bars(self, code: str) -> list[TdxDailyBar]:
        payload = self._get("/api/kline", {"code": code, "type": "day"})
        rows = payload.get("List", []) if isinstance(payload, dict) else payload
        return [
            TdxDailyBar(
                code=code,
                time=datetime.fromisoformat(row["Time"]),
                close=row["Close"] / 1000,
                previous_close=row["Last"] / 1000,
                open=row["Open"] / 1000,
                high=row["High"] / 1000,
                low=row["Low"] / 1000,
                volume_hands=int(row.get("Volume", 0)),
                amount=int(row.get("Amount", 0)),
            )
            for row in rows
        ]

    def daily_closes(self, codes: list[str], as_of: datetime) -> list[TdxDailyBar]:
        if as_of.tzinfo is None:
            raise ValueError("行情截止时间必须包含时区")
        result = []
        for code in codes:
            eligible = [bar for bar in self.daily_bars(code) if bar.time <= as_of]
            if eligible:
                result.append(max(eligible, key=lambda bar: bar.time))
        return result
