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
from .backtest import backtest_symbol, available_symbols, optimize
from . import social
from . import copytrade as ct


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


def _cmd_copytrade(engine: Engine, args) -> None:
    client = engine.client
    if args.action == "leaders":
        leaders = ct.leaderboard(client, limit=args.limit)
        print(f"{'AGENT_ID':>9}  {'NAME':<26}{'SIGNALS':>9}{'PNL':>12}")
        for l in leaders:
            print(f"{l.agent_id:>9}  {l.name[:26]:<26}{l.signal_count:>9}{l.total_pnl:>12,.0f}")
        print("\n  Follow one with: python -m trader.cli copytrade follow <AGENT_ID>")
    elif args.action == "follow":
        if not args.ids:
            print("Pass one or more leader agent IDs to follow.")
            return
        for r in ct.follow_leaders(client, [int(i) for i in args.ids]):
            status = "followed" if r["ok"] else f"failed: {r.get('error', r.get('resp'))}"
            print(f"  leader {r['leader_id']}: {status}")
        print("  Their positions will be mirrored onto the paper account (source=copied).")
    elif args.action == "unfollow":
        for i in args.ids:
            client.unfollow(int(i))
            print(f"  unfollowed leader {i}")
    elif args.action == "following":
        subs = client.following()
        if not subs:
            print("  not following anyone yet.")
        for s in subs:
            print(f"  leader {s.get('leader_id')} {s.get('leader_name','?')} | copied={s.get('copied_count')} | {s.get('status')}")
    elif args.action == "copied":
        rows = ct.copied_positions(client)
        if not rows:
            print("  no copied positions yet.")
        for p in rows:
            print(f"  {p.get('symbol')} x{p.get('quantity')} entry {p.get('entry_price')} pnl {p.get('pnl')} ({p.get('source')})")


def _cmd_social(topic: list[str]) -> None:
    print("Social research platforms (read-only, for signal — never posting):\n")
    for s in social.status():
        mark = "✓" if s.enabled else "·"
        detail = f"via {s.via}" if s.enabled else f"needs {' or '.join(social.PLATFORM_KEYS[s.name])}"
        print(f"  {mark} {s.name:<28} {detail}")
    for k in social.KEYLESS:
        print(f"  ✓ {k:<28} (no key needed)")
    print("\n  Note: LinkedIn / Facebook are not supported by the research engine.")
    if topic:
        print(f"\n--- research: {' '.join(topic)} ---")
        print(social.research(" ".join(topic)))
    else:
        print("\n  Add keys to .env.secrets, then: python -m trader.cli social <topic>")


def _cmd_optimize(symbols: list[str]) -> None:
    variants = optimize([s.upper() for s in symbols] or None)
    if not variants:
        print("No history to optimize over. Fetch via the Robinhood MCP first (see README).")
        return
    print(f"{'EXIT STRATEGY':<22}{'AVG RET%':>9}{'B&H%':>8}{'AVG DD%':>9}{'RET/DD':>8}{'BEAT':>7}")
    for v in variants:
        print(f"{v.label:<22}{v.avg_return_pct:>9.1f}{v.avg_buy_hold_pct:>8.1f}"
              f"{v.avg_drawdown_pct:>9.1f}{v.return_over_dd:>8.2f}{v.beat_buy_hold:>4}/{v.symbols}")
    best = variants[0]
    print(f"\nBest risk-adjusted: {best.label} (return/drawdown {best.return_over_dd:.2f}).")
    print("Live engine uses trailing-stop exits accordingly (see StrategyConfig).")


def _cmd_backtest(symbols: list[str]) -> None:
    symbols = [s.upper() for s in symbols] or available_symbols()
    if not symbols:
        print("No history files in trader/state/history/. Fetch via the Robinhood MCP first (see README).")
        return
    print(f"{'SYM':<6}{'TRADES':>7}{'WIN%':>7}{'AVG%':>8}{'TOTAL%':>9}{'B&H%':>9}{'MAXDD%':>8}")
    for sym in symbols:
        r = backtest_symbol(sym)
        if r is None:
            print(f"{sym:<6}  (insufficient history)")
            continue
        print(
            f"{r.symbol:<6}{r.trades:>7}{r.win_rate_pct:>7.0f}{r.avg_trade_pct:>8.1f}"
            f"{r.total_return_pct:>9.1f}{r.buy_hold_return_pct:>9.1f}{r.max_drawdown_pct:>8.1f}"
        )
    print("\n(Strategy = stacked bullish MAs + controlled momentum, stop -8% / target +15%.")
    print(" B&H = buy-and-hold over the same window. Logic proxy of the live rules, not a return promise.)")


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
    bt_p = sub.add_parser("backtest", help="backtest the strategy logic over saved history")
    bt_p.add_argument("symbols", nargs="*", help="symbols to test (default: all saved)")
    opt_p = sub.add_parser("optimize", help="sweep exit strategies, rank by risk-adjusted return")
    opt_p.add_argument("symbols", nargs="*", help="symbols to test (default: all saved)")
    so_p = sub.add_parser("social", help="social-media research status + run (read-only)")
    so_p.add_argument("topic", nargs="*", help="topic/ticker to research")
    cp_p = sub.add_parser("copytrade", help="match leaderboard agents on the paper account")
    cp_p.add_argument("action", choices=["leaders", "follow", "unfollow", "following", "copied"])
    cp_p.add_argument("ids", nargs="*", help="leader agent IDs (for follow/unfollow)")
    cp_p.add_argument("--limit", type=int, default=15, help="leaders to list")
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
    if args.command == "backtest":
        _cmd_backtest(args.symbols)
        return 0
    if args.command == "optimize":
        _cmd_optimize(args.symbols)
        return 0
    if args.command == "social":
        _cmd_social(args.topic)
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
    elif args.command == "copytrade":
        _cmd_copytrade(engine, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
