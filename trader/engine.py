"""Orchestration: research -> rank -> (paper) trade -> record.

Default mode is dry-run: the engine prints exactly what it WOULD do and
changes nothing. Pass execute=True to actually place paper trades.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    def __init__(
        self,
        client: Ai4TradeClient | None = None,
        strategy: Strategy | None = None,
    ) -> None:
        self.client = client or Ai4TradeClient()
        self.strategy = strategy or Strategy()
        self.scorecard = Scorecard(self.client)

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

    def manage_exits(self, execute: bool = False) -> list[ExitAction]:
        """Sell positions that have hit their recorded stop or target."""
        snap = self.scorecard.snapshot()
        levels = self._stops_targets()
        actions: list[ExitAction] = []
        for p in snap["positions"]:
            sym = p["symbol"]
            stop, target = levels.get(sym, (None, None))
            cur = p["current"]
            qty = p["qty"]
            reason = None
            if stop is not None and cur <= stop:
                reason = "stop"
            elif target is not None and cur >= target:
                reason = "target"
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
                action.note = f"SOLD {qty:.0f} {sym} @ ${fill} ({reason})"
            else:
                action.note = f"DRY-RUN: would sell {qty:.0f} {sym} @ ~${cur:.2f} ({reason})"
            actions.append(action)
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
        items = self.client.featured_stocks()
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
