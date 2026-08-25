"""Rule-based strategy for ranking candidates from market-intel snapshots.

Deliberately conservative and transparent: every accept/reject decision is
explainable from the printed reasons. This is a starting baseline meant to be
backtested and tuned, not a black box.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StrategyConfig:
    # Minimum platform signal score (featured analysis is on a -5..+5 scale).
    min_signal_score: float = 3.0
    # Require the featured signal to be an outright "buy".
    require_buy_signal: bool = True
    # Require a bullish trend tag.
    require_bullish_trend: bool = True
    # Skip names already extended: need at least this much room to resistance.
    min_room_to_resistance_pct: float = 3.0
    # Avoid chasing parabolic moves: cap the recent 5-day run-up.
    max_return_5d_pct: float = 15.0
    # Don't buy anything when the macro regime is outright bearish.
    block_when_macro_bearish: bool = True
    # Exit discipline (validated by trader/backtest.optimize: trailing 10% was
    # the best risk-adjusted variant — higher return AND lower drawdown than a
    # fixed target). Winners run; a trailing stop locks in gains.
    trail_pct: float = 0.10        # exit if price falls this far from its peak since entry
    hard_stop_pct: float = 0.08    # absolute floor below entry
    # Portfolio construction.
    max_positions: int = 6
    position_pct_of_cash: float = 5.0  # % of current cash per new position


@dataclass
class Candidate:
    symbol: str
    price: float
    signal: str
    score: float
    trend: str
    return_5d: float
    return_20d: float
    support: float | None
    resistance: float | None
    room_to_resistance_pct: float | None
    accepted: bool = False
    reasons: list[str] = field(default_factory=list)
    # Derived trade plan (only meaningful when accepted).
    stop: float | None = None
    target: float | None = None


class Strategy:
    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()

    @staticmethod
    def _first(values: list | None) -> float | None:
        if values and isinstance(values, list):
            try:
                return float(values[0])
            except (TypeError, ValueError):
                return None
        return None

    def evaluate(self, item: dict, macro_verdict: str | None = None) -> Candidate:
        cfg = self.config
        analysis = item.get("analysis", {}) or {}
        support = self._first(item.get("support_levels"))
        resistance = self._first(item.get("resistance_levels"))
        room = analysis.get("distance_to_resistance_pct")

        cand = Candidate(
            symbol=item.get("symbol", "?"),
            price=float(item.get("current_price") or 0),
            signal=str(item.get("signal", "")),
            score=float(item.get("signal_score") or 0),
            trend=str(item.get("trend_status", "")),
            return_5d=float(analysis.get("return_5d_pct") or 0),
            return_20d=float(analysis.get("return_20d_pct") or 0),
            support=support,
            resistance=resistance,
            room_to_resistance_pct=room,
        )

        reasons: list[str] = []
        ok = True

        if cfg.block_when_macro_bearish and (macro_verdict or "").lower() == "bearish":
            ok = False
            reasons.append("macro regime is bearish — standing down")

        if cfg.require_buy_signal and cand.signal.lower() != "buy":
            ok = False
            reasons.append(f"signal is '{cand.signal}', not a buy")

        if cand.score < cfg.min_signal_score:
            ok = False
            reasons.append(f"score {cand.score:.1f} < min {cfg.min_signal_score:.1f}")
        else:
            reasons.append(f"score {cand.score:.1f} meets threshold")

        if cfg.require_bullish_trend and "bull" not in cand.trend.lower():
            ok = False
            reasons.append(f"trend '{cand.trend}' is not bullish")

        if cand.return_5d > cfg.max_return_5d_pct:
            ok = False
            reasons.append(f"5d run-up {cand.return_5d:.1f}% > {cfg.max_return_5d_pct:.1f}% (too extended)")

        if room is not None and room < cfg.min_room_to_resistance_pct:
            ok = False
            reasons.append(f"only {room:.1f}% to resistance (< {cfg.min_room_to_resistance_pct:.1f}%)")
        elif room is not None:
            reasons.append(f"{room:.1f}% room to resistance")

        cand.accepted = ok
        cand.reasons = reasons
        if ok:
            # Stop below structural support (or -8% fallback); target at resistance.
            cand.stop = round(support, 2) if support else round(cand.price * 0.92, 2)
            cand.target = round(resistance, 2) if resistance else round(cand.price * 1.15, 2)
        return cand

    def rank(self, items: list[dict], macro_verdict: str | None = None) -> list[Candidate]:
        cands = [self.evaluate(it, macro_verdict) for it in items]
        cands.sort(key=lambda c: (c.accepted, c.score), reverse=True)
        return cands

    def position_size(self, cash: float, price: float) -> float:
        """Whole-share quantity for one new position, sized to % of cash."""
        if price <= 0:
            return 0
        budget = cash * (self.config.position_pct_of_cash / 100.0)
        return float(int(budget // price))
