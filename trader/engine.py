"""Orchestration: research -> rank -> (paper) trade -> record.

Default mode is dry-run: the engine prints exactly what it WOULD do and
changes nothing. Pass execute=True to actually place paper trades.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .client import Ai4TradeClient
from .scorecard import Scorecard
from .strategy import Strategy, Candidate
from .research import search_events


@dataclass
class Decision:
    candidate: Candidate
    quantity: float
    note: str


@dataclass
class ExitAction:
    symbol: str
    quantity: float
    current: float
    reason: str  # "stop" | "target"
    note: str = ""


class Engine:
    # Liquid names to score each cycle in addition to ai4trade's featured set.
    # Unavailable symbols are skipped silently.
    WATCHLIST = [
        "AMD", "NVDA", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "TSLA",
        "AVGO", "PLTR", "SPY", "QQQ", "MU", "SMCI",
    ]

    def __init__(
        self,
        client: Ai4TradeClient | None = None,
        strategy: Strategy | None = None,
    ) -> None:
        self.client = client or Ai4TradeClient()
        self.strategy = strategy or Strategy()
        self.scorecard = Scorecard(self.client)

    def _candidate_items(self) -> list[dict]:
        """ai4trade featured set + watchlist analyses, deduped by symbol."""
        items: dict[str, dict] = {}
        for it in self.client.featured_stocks():
            sym = it.get("symbol")
            if sym:
                items[sym] = it
        for sym in self.WATCHLIST:
            if sym in items:
                continue
            try:
                d = self.client.stock_analysis(sym)
                if d.get("available"):
                    items[sym] = d
            except Exception:
                continue
        return list(items.values())

    def _macro_verdict(self) -> str | None:
        try:
            return self.client.market_overview().get("macro_verdict")
        except Exception:
            return None

    def _stops_targets(self) -> dict[str, tuple[float | None, float | None]]:
        """Latest recorded stop/target per symbol, from the buy journal."""
        levels: dict[str, tuple[float | None, float | None]] = {}
        for entry in self.scorecard.journal():
            if entry.get("action") == "buy" and entry.get("symbol"):
                levels[entry["symbol"]] = (entry.get("stop"), entry.get("target"))
        return levels

    _PEAKS = Path(__file__).resolve().parent / "state" / "peaks.json"

    def _load_peaks(self) -> dict[str, float]:
        if self._PEAKS.exists():
            try:
                return json.loads(self._PEAKS.read_text())
            except ValueError:
                return {}
        return {}

    def _save_peaks(self, peaks: dict[str, float]) -> None:
        self._PEAKS.parent.mkdir(parents=True, exist_ok=True)
        self._PEAKS.write_text(json.dumps(peaks))

    def manage_exits(self, execute: bool = False) -> list[ExitAction]:
        """Sell positions on a trailing stop (peak-to-now) or hard stop.

        Trailing logic mirrors the backtest-validated 'trailing 10%' variant:
        a per-position peak is tracked across cycles; we exit when price falls
        trail_pct from that peak, or breaches the hard stop below entry.
        """
        snap = self.scorecard.snapshot()
        levels = self._stops_targets()
        peaks = self._load_peaks()
        cfg = self.strategy.config
        held = {p["symbol"] for p in snap["positions"]}
        # forget peaks for positions we no longer hold
        peaks = {k: v for k, v in peaks.items() if k in held}

        actions: list[ExitAction] = []
        for p in snap["positions"]:
            sym = p["symbol"]
            cur = p["current"]
            qty = p["qty"]
            entry = p["entry"]
            peak = max(peaks.get(sym, 0.0), cur, entry)
            peaks[sym] = peak
            hard_stop, _ = levels.get(sym, (None, None))
            if hard_stop is None and entry:
                hard_stop = entry * (1 - cfg.hard_stop_pct)
            trail_level = peak * (1 - cfg.trail_pct)
            reason = None
            if hard_stop is not None and cur <= hard_stop:
                reason = "stop"
            elif cur <= trail_level:
                reason = "trailing"
            if not reason:
                continue
            action = ExitAction(sym, qty, cur, reason)
            if execute:
                resp = self.client.place_trade(
                    symbol=sym, action="sell", quantity=qty,
                    content=f"[auto] exit on {reason} @ ~{cur:.2f}",
                )
                fill = resp.get("price")
                self.scorecard.record(
                    {"action": "sell", "symbol": sym, "qty": qty, "fill_price": fill,
                     "reason": reason, "signal_id": resp.get("signal_id"), "mode": "paper"}
                )
                peaks.pop(sym, None)
                action.note = f"SOLD {qty:.0f} {sym} @ ${fill} ({reason})"
            else:
                action.note = f"DRY-RUN: would sell {qty:.0f} {sym} @ ~${cur:.2f} ({reason})"
            actions.append(action)
        self._save_peaks(peaks)
        return actions

    def macro_context(self, limit: int = 3) -> list[str]:
        """Live prediction-market odds on the rate path — per-cycle awareness."""
        out: list[str] = []
        for ev in search_events("fed rate cuts 2026", limit=1, max_markets=limit):
            for mk in ev.markets:
                out.append(mk.headline)
        return out

    def scan(self) -> tuple[list[Candidate], str | None]:
        macro = self._macro_verdict()
        items = self._candidate_items()
        return self.strategy.rank(items, macro), macro

    def plan(self) -> list[Decision]:
        """Decide which accepted candidates to buy given current portfolio."""
        cands, _ = self.scan()
        snap = self.scorecard.snapshot()
        held = {p["symbol"] for p in snap["positions"]}
        cash = snap["cash"]
        open_slots = self.strategy.config.max_positions - len(held)

        decisions: list[Decision] = []
        for c in cands:
            if open_slots <= 0:
                break
            if not c.accepted:
                continue
            if c.symbol in held:
                continue
            qty = self.strategy.position_size(cash, c.price)
            if qty < 1:
                decisions.append(Decision(c, 0, "skipped: position size < 1 share for available cash"))
                continue
            decisions.append(
                Decision(c, qty, f"buy {qty:.0f} @ ~${c.price:.2f} | stop {c.stop} target {c.target}")
            )
            cash -= qty * c.price
            open_slots -= 1
        return decisions

    def cycle(self, execute: bool = False) -> dict:
        """One full autonomous pass: manage exits, then evaluate entries."""
        exits = self.manage_exits(execute=execute)
        entries = self.run(execute=execute)
        snap = self.scorecard.snapshot()
        return {
            "exits": exits,
            "entries": [d for d in entries if d.quantity >= 1],
            "equity": snap["equity"],
            "cash": snap["cash"],
            "open_positions": len(snap["positions"]),
        }

    def run(self, execute: bool = False) -> list[Decision]:
        decisions = self.plan()
        for d in decisions:
            if d.quantity < 1:
                continue
            thesis = (
                f"score {d.candidate.score:.1f}, trend {d.candidate.trend}, "
                f"{d.candidate.room_to_resistance_pct or 0:.1f}% to resistance; "
                f"stop {d.candidate.stop} target {d.candidate.target}"
            )
            if execute:
                resp = self.client.place_trade(
                    symbol=d.candidate.symbol,
                    action="buy",
                    quantity=d.quantity,
                    content=f"[auto] {thesis}",
                )
                fill = resp.get("price")
                self.scorecard.record(
                    {
                        "action": "buy",
                        "symbol": d.candidate.symbol,
                        "qty": d.quantity,
                        "fill_price": fill,
                        "stop": d.candidate.stop,
                        "target": d.candidate.target,
                        "thesis": thesis,
                        "signal_id": resp.get("signal_id"),
                        "mode": "paper",
                    }
                )
                d.note = f"FILLED {d.quantity:.0f} {d.candidate.symbol} @ ${fill}"
            else:
                d.note = "DRY-RUN: " + d.note
        return decisions
