"""Backtest the strategy's logic over real historical prices.

Data source: daily split-adjusted closes pulled from the Robinhood MCP and
saved to trader/state/history/<SYMBOL>.json (regenerate via the MCP; see
README). The live engine scores off ai4trade's proprietary signal, which can't
be replayed historically, so this backtests a faithful *proxy* of the same
logic — stacked bullish moving averages + controlled momentum, with the same
stop/target discipline. Treat it as a sanity check on the rules, not a promise
of live returns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_HISTORY_DIR = Path(__file__).resolve().parent / "state" / "history"


@dataclass
class BacktestConfig:
    stop_pct: float = 0.08          # hard stop: exit if down this much from entry
    target_pct: float = 0.15        # fixed-target exit (used only when exit_mode='fixed')
    max_entry_momentum: float = 0.15  # skip entries already up > this over 5d
    ma_fast: int = 5
    ma_mid: int = 20
    ma_slow: int = 60
    # exit_mode:
    #   'fixed'    -> exit at +target_pct, -stop_pct, or close < MA_mid
    #   'trend'    -> hold while close >= MA_mid; hard stop at -stop_pct (let winners run)
    #   'trailing' -> exit if price falls trail_pct from its peak since entry; hard stop too
    exit_mode: str = "trend"
    trail_pct: float = 0.10


@dataclass
class BacktestResult:
    symbol: str
    trades: int
    wins: int
    total_return_pct: float       # compounded, strategy
    buy_hold_return_pct: float
    avg_trade_pct: float
    max_drawdown_pct: float

    @property
    def win_rate_pct(self) -> float:
        return (self.wins / self.trades * 100) if self.trades else 0.0


def _load_closes(symbol: str) -> list[float]:
    path = _HISTORY_DIR / f"{symbol}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [b["c"] for b in data.get("bars", []) if b.get("c") is not None]


def _sma(series: list[float], end: int, window: int) -> float | None:
    if end + 1 < window:
        return None
    return sum(series[end + 1 - window : end + 1]) / window


def backtest_symbol(symbol: str, cfg: BacktestConfig | None = None) -> BacktestResult | None:
    cfg = cfg or BacktestConfig()
    closes = _load_closes(symbol)
    if len(closes) < cfg.ma_slow + cfg.ma_fast + 5:
        return None

    in_pos = False
    entry = stop = target = pos_peak = 0.0
    trade_returns: list[float] = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0

    for t in range(cfg.ma_slow, len(closes)):
        price = closes[t]
        ma_f = _sma(closes, t, cfg.ma_fast)
        ma_m = _sma(closes, t, cfg.ma_mid)
        ma_s = _sma(closes, t, cfg.ma_slow)
        if None in (ma_f, ma_m, ma_s):
            continue
        ret5 = price / closes[t - 5] - 1 if closes[t - 5] else 0.0

        if not in_pos:
            stacked = price > ma_m > ma_s and ma_f > ma_m
            momentum_ok = 0 < ret5 <= cfg.max_entry_momentum
            if stacked and momentum_ok:
                in_pos = True
                entry = price
                pos_peak = price
                stop = entry * (1 - cfg.stop_pct)
                target = entry * (1 + cfg.target_pct)
        else:
            pos_peak = max(pos_peak, price)
            if cfg.exit_mode == "fixed":
                exit_now = price <= stop or price >= target or price < ma_m
            elif cfg.exit_mode == "trailing":
                exit_now = price <= stop or price <= pos_peak * (1 - cfg.trail_pct)
            else:  # 'trend': let winners run while trend holds
                exit_now = price <= stop or price < ma_m
            if exit_now:
                r = price / entry - 1
                trade_returns.append(r)
                equity *= 1 + r
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak)
                in_pos = False

    wins = sum(1 for r in trade_returns if r > 0)
    buy_hold = (closes[-1] / closes[cfg.ma_slow] - 1) * 100
    avg = (sum(trade_returns) / len(trade_returns) * 100) if trade_returns else 0.0
    return BacktestResult(
        symbol=symbol,
        trades=len(trade_returns),
        wins=wins,
        total_return_pct=(equity - 1) * 100,
        buy_hold_return_pct=buy_hold,
        avg_trade_pct=avg,
        max_drawdown_pct=max_dd * 100,
    )


def available_symbols() -> list[str]:
    if not _HISTORY_DIR.exists():
        return []
    return sorted(p.stem for p in _HISTORY_DIR.glob("*.json"))


@dataclass
class Variant:
    label: str
    config: BacktestConfig
    avg_return_pct: float       # mean total return across symbols
    avg_buy_hold_pct: float
    avg_drawdown_pct: float
    beat_buy_hold: int          # how many symbols it beat B&H on
    symbols: int

    @property
    def return_over_dd(self) -> float:
        """Risk-adjusted score: return per unit of drawdown."""
        return self.avg_return_pct / self.avg_drawdown_pct if self.avg_drawdown_pct else 0.0


def _variant_configs() -> list[tuple[str, BacktestConfig]]:
    out: list[tuple[str, BacktestConfig]] = [
        ("fixed +15%/-8%", BacktestConfig(exit_mode="fixed")),
        ("trend (hold>MA20)", BacktestConfig(exit_mode="trend")),
    ]
    for trail in (0.08, 0.10, 0.15):
        out.append((f"trailing {int(trail*100)}%", BacktestConfig(exit_mode="trailing", trail_pct=trail)))
    for stop in (0.06, 0.10, 0.12):
        out.append((f"trend stop -{int(stop*100)}%", BacktestConfig(exit_mode="trend", stop_pct=stop)))
    return out


def optimize(symbols: list[str] | None = None) -> list[Variant]:
    """Sweep exit strategies over the saved universe; rank by risk-adjusted return."""
    symbols = symbols or available_symbols()
    variants: list[Variant] = []
    for label, cfg in _variant_configs():
        results = [r for s in symbols if (r := backtest_symbol(s, cfg))]
        if not results:
            continue
        n = len(results)
        variants.append(
            Variant(
                label=label,
                config=cfg,
                avg_return_pct=sum(r.total_return_pct for r in results) / n,
                avg_buy_hold_pct=sum(r.buy_hold_return_pct for r in results) / n,
                avg_drawdown_pct=sum(r.max_drawdown_pct for r in results) / n,
                beat_buy_hold=sum(1 for r in results if r.total_return_pct > r.buy_hold_return_pct),
                symbols=n,
            )
        )
    variants.sort(key=lambda v: v.return_over_dd, reverse=True)
    return variants
