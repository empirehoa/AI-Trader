"""Track positions, realized/unrealized P&L, and a running trade journal.

State lives in trader/state/ (git-ignored). Two files:
  - trades.jsonl : append-only journal of every order the engine places
  - The live portfolio is always read back from the platform, not cached, so
    the scorecard reflects the broker of record rather than local guesses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_STATE_DIR = Path(__file__).resolve().parent / "state"
_JOURNAL = _STATE_DIR / "trades.jsonl"


class Scorecard:
    def __init__(self, client) -> None:
        self.client = client
        _STATE_DIR.mkdir(parents=True, exist_ok=True)

    # -- journal ---------------------------------------------------------
    def record(self, entry: dict) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        with _JOURNAL.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")

    def journal(self) -> list[dict]:
        if not _JOURNAL.exists():
            return []
        return [json.loads(line) for line in _JOURNAL.read_text().splitlines() if line.strip()]

    # -- live portfolio --------------------------------------------------
    def snapshot(self, live_prices: dict[str, float] | None = None) -> dict:
        """Portfolio as the platform reports it.

        The platform's positions feed can lag (it re-marks positions on a
        delay). When ``live_prices`` is supplied (symbol -> fresh price from
        the live analysis feed), those override the stale portfolio marks so
        valuation, P&L, and exit checks reflect the current price. Falls back
        to the broker mark for any symbol without a live price.
        """
        me = self.client.me()
        pos = self.client.positions()
        positions = pos.get("positions", [])
        cash = float(pos.get("cash", me.get("cash", 0)) or 0)

        invested = 0.0
        unrealized = 0.0
        rows = []
        for p in positions:
            qty = float(p.get("quantity") or 0)
            entry = float(p.get("entry_price") or 0)
            current = float(p.get("current_price") or entry)
            live = (live_prices or {}).get(p.get("symbol"))
            if live:
                current = float(live)
                pnl = (current - entry) * qty
            else:
                pnl = p.get("pnl")
                pnl = float(pnl) if pnl is not None else (current - entry) * qty
            invested += entry * qty
            unrealized += pnl
            rows.append(
                {
                    "symbol": p.get("symbol"),
                    "qty": qty,
                    "entry": entry,
                    "current": current,
                    "pnl": pnl,
                    "pnl_pct": ((current - entry) / entry * 100) if entry else 0.0,
                    "source": p.get("source", "self"),
                }
            )

        market_value = sum(r["current"] * r["qty"] for r in rows)
        return {
            "cash": cash,
            "points": me.get("points", 0),
            "reputation": me.get("reputation_score", 0),
            "positions": rows,
            "invested_cost": invested,
            "market_value": market_value,
            "unrealized_pnl": unrealized,
            "equity": cash + market_value,
        }

    # -- rendering -------------------------------------------------------
    def render(self, live_prices: dict[str, float] | None = None) -> str:
        s = self.snapshot(live_prices=live_prices)
        lines = []
        lines.append("=" * 60)
        lines.append("  AI-TRADER PAPER SCORECARD")
        lines.append("=" * 60)
        lines.append(f"  Equity (cash + positions): ${s['equity']:,.2f}")
        lines.append(f"  Cash:                      ${s['cash']:,.2f}")
        lines.append(f"  Market value of holdings:  ${s['market_value']:,.2f}")
        sign = "+" if s["unrealized_pnl"] >= 0 else ""
        lines.append(f"  Unrealized P&L:            {sign}${s['unrealized_pnl']:,.2f}")
        lines.append(f"  Platform points:           {s['points']}")
        lines.append("-" * 60)
        if not s["positions"]:
            lines.append("  (no open positions)")
        else:
            lines.append(f"  {'SYMBOL':<8}{'QTY':>8}{'ENTRY':>10}{'NOW':>10}{'P&L':>12}{'P&L%':>9}")
            for r in s["positions"]:
                ps = "+" if r["pnl"] >= 0 else ""
                lines.append(
                    f"  {r['symbol']:<8}{r['qty']:>8.0f}{r['entry']:>10.2f}"
                    f"{r['current']:>10.2f}{ps + format(r['pnl'], ',.2f'):>12}"
                    f"{ps + format(r['pnl_pct'], '.1f'):>8}%"
                )
        lines.append("=" * 60)
        return "\n".join(lines)
