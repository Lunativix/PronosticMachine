"""Bankroll paths. Fractional Kelly is capped by max_stake_percent."""

from __future__ import annotations

from dataclasses import dataclass

from app.betting.odds_math import stake_amount, stake_fraction


@dataclass
class BankrollState:
    bankroll: float
    peak: float
    max_drawdown: float

    def mark(self) -> float:
        self.peak = max(self.peak, self.bankroll)
        drawdown = 0.0 if self.peak <= 0 else (self.peak - self.bankroll) / self.peak
        self.max_drawdown = max(self.max_drawdown, drawdown)
        return drawdown


def open_bankroll(initial: float) -> BankrollState:
    return BankrollState(bankroll=initial, peak=initial, max_drawdown=0.0)


def settle(
    state: BankrollState,
    *,
    probability: float,
    odds: float,
    won: bool,
    method: str,
    kelly_fraction: float,
    max_stake_percent: float,
    percent: float = 0.01,
    fixed_stake: float = 10.0,
) -> tuple[float, float]:
    fraction = stake_fraction(
        probability,
        odds,
        method,
        kelly_fraction=kelly_fraction,
        max_stake_percent=max_stake_percent,
        percent=percent,
        fixed_stake=fixed_stake,
        bankroll=state.bankroll,
    )
    amount = stake_amount(state.bankroll, fraction)
    pnl = amount * (odds - 1.0) if won else -amount
    state.bankroll = max(0.0, state.bankroll + pnl)
    state.mark()
    return amount, pnl
