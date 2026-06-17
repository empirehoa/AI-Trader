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
from .loop import Loop
from .research import search_events


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


def _cmd_events(topic: str) -> None:
    events = search_events(topic)
    if not events:
        print(f"No active Polymarket events found for '{topic}'.")
        return
    print(f"Polymarket odds for '{topic}' (live, real-money probabilities):\n")
    for ev in events:
        print(f"  {ev.title}")
        for mk in ev.markets:
            vol = f"${mk.volume_24h:,.0f}/24h" if mk.volume_24h else "thin"
            print(f"      - {mk.headline}   [{vol}]")
        print()


def _cmd_loop(engine: Engine, args) -> None:
    loop = Loop(
        engine=engine,
        interval_seconds=args.interval,
        max_cycles=args.max_cycles,
        max_new_trades_per_day=args.daily_cap,
    )
    loop.run(execute=args.execute)


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
    ev_p = sub.add_parser("events", help="live Polymarket odds for a topic (no API key)")
    ev_p.add_argument("topic", nargs="+", help="topic to search, e.g. fed rate cuts")
    run_p = sub.add_parser("run", help="evaluate and (optionally) place paper trades")
    run_p.add_argument("--execute", action="store_true", help="actually place paper trades")
    loop_p = sub.add_parser("loop", help="autonomous paper loop (exits + entries on an interval)")
    loop_p.add_argument("--execute", action="store_true", help="place paper trades (else dry-run)")
    loop_p.add_argument("--interval", type=int, default=900, help="seconds between cycles (default 900)")
    loop_p.add_argument("--max-cycles", type=int, default=0, dest="max_cycles", help="stop after N cycles (0 = until killed)")
    loop_p.add_argument("--daily-cap", type=int, default=5, dest="daily_cap", help="max new buys per UTC day")
    args = parser.parse_args(argv)

    if args.command == "events":
        _cmd_events(" ".join(args.topic))
        return 0

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
    elif args.command == "loop":
        _cmd_loop(engine, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
