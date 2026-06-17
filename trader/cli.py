"""Command-line entrypoint for the paper-trading engine.

    python -m trader.cli status            # show the scorecard
    python -m trader.cli scan              # rank candidates, decide nothing
    python -m trader.cli run               # dry-run: print what it WOULD trade
    python -m trader.cli run --execute     # place the paper trades for real (sim $)
"""

from __future__ import annotations

import argparse
import sys

from .client import Ai4TradeClient, Ai4TradeError
from .engine import Engine


def _cmd_status(engine: Engine) -> None:
    print(engine.scorecard.render())


def _cmd_scan(engine: Engine) -> None:
    cands, macro = engine.scan()
    print(f"Macro regime: {macro or 'unknown'}")
    print(f"{'SYM':<7}{'SCORE':>7}{'SIGNAL':>8}{'TREND':>10}{'5d%':>8}{'20d%':>8}  VERDICT")
    for c in cands:
        verdict = "ACCEPT" if c.accepted else "reject"
        print(
            f"{c.symbol:<7}{c.score:>7.1f}{c.signal:>8}{c.trend:>10}"
            f"{c.return_5d:>8.1f}{c.return_20d:>8.1f}  {verdict}"
        )
        for r in c.reasons:
            print(f"        - {r}")


def _cmd_run(engine: Engine, execute: bool) -> None:
    decisions = engine.run(execute=execute)
    actionable = [d for d in decisions if d.quantity >= 1]
    if not actionable:
        print("No actionable buys this cycle (nothing cleared the rules / no cash / slots full).")
        return
    for d in decisions:
        print(f"  {d.candidate.symbol}: {d.note}")
    if not execute:
        print("\n(dry-run — no orders placed. Re-run with --execute to place paper trades.)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trader", description="AI-Trader paper-trading engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show the paper scorecard")
    sub.add_parser("scan", help="rank candidates without trading")
    run_p = sub.add_parser("run", help="evaluate and (optionally) place paper trades")
    run_p.add_argument("--execute", action="store_true", help="actually place paper trades")
    args = parser.parse_args(argv)

    try:
        engine = Engine(client=Ai4TradeClient())
    except Ai4TradeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.command == "status":
        _cmd_status(engine)
    elif args.command == "scan":
        _cmd_scan(engine)
    elif args.command == "run":
        _cmd_run(engine, execute=args.execute)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
