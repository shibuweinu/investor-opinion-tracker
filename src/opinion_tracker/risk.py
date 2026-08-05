from pydantic import BaseModel


class PositionSizing(BaseModel):
    shares: int
    position_value: float
    planned_loss: float


def size_position(
    account_value: float,
    risk_pct: float,
    entry: float,
    stop: float,
    sector_used_pct: float,
    max_sector_pct: float = 30,
) -> PositionSizing:
    per_share = abs(entry - stop)
    if per_share <= 0:
        raise ValueError("止损价必须不同于入场价")
    risk_cash = account_value * risk_pct / 100
    risk_shares = int(risk_cash / per_share)
    sector_cash = max(0.0, account_value * max_sector_pct / 100 - account_value * sector_used_pct / 100)
    shares = min(risk_shares, int(sector_cash / entry))
    return PositionSizing(
        shares=shares, position_value=round(shares * entry, 2), planned_loss=round(shares * per_share, 2)
    )
