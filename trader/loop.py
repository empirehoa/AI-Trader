"""Autonomous paper-trading loop.

Runs the full research -> exits -> entries cycle on a fixed interval, with
hard guardrails so an unattended run can't misbehave:

  - kill switch: create trader/state/STOP to halt before the next cycle
  - daily entry cap: at most `max_new_trades_per_day` new buys per UTC day
  - bounded run: stops after `max_cycles` (0 = until killed)

This loop only ever trades the simulated account. Real-money/options
execution is intentionally not wired here — it stays behind the Robinhood MCP
confirmation gate.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .engine import Engine

_STOP_FILE = Path(__file__).resolve().parent / "state" / "STOP"


class Loop:
    def __init__(
        self,
        engine: Engine | None = None,
        interval_seconds: int = 900,
        max_cycles: int = 0,
        max_new_trades_per_day: int = 5,
    ) -> None:
        self.engine = engine or Engine()
        self.interval = interval_seconds
        self.max_cycles = max_cycles
        self.max_new_trades_per_day = max_new_trades_per_day

    def _entries_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(
            1
            for e in self.engine.scorecard.journal()
            if e.get("action") == "buy"
            and e.get("mode") == "paper"
            and str(e.get("ts", "")).startswith(today)
        )

    def _log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)

    def run(self, execute: bool = False) -> None:
        mode = "EXECUTE (paper $)" if execute else "DRY-RUN"
        self._log(f"loop start | mode={mode} | interval={self.interval}s | daily cap={self.max_new_trades_per_day}")
        cycle = 0
        while True:
            cycle += 1
            if _STOP_FILE.exists():
                self._log("STOP file present — halting.")
                return

            for line in self.engine.macro_context():
                self._log(f"macro: {line}")

            remaining = self.max_new_trades_per_day - self._entries_today()
            if remaining <= 0:
                self._log("daily entry cap reached — managing exits only.")
                exits = self.engine.manage_exits(execute=execute)
                for x in exits:
                    self._log(x.note)
            else:
                result = self.engine.cycle(execute=execute)
                for x in result["exits"]:
                    self._log(x.note)
                acted = False
                for d in result["entries"]:
                    self._log(d.note)
                    acted = True
                if not acted and not result["exits"]:
                    self._log("no actions this cycle.")
                self._log(
                    f"equity ${result['equity']:,.2f} | cash ${result['cash']:,.2f} "
                    f"| positions {result['open_positions']}"
                )

            if self.max_cycles and cycle >= self.max_cycles:
                self._log(f"reached max_cycles={self.max_cycles} — done.")
                return
            time.sleep(self.interval)
