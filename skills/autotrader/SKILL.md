---
name: autotrader
description: Run the AI-Trader paper-trading loop autonomously inside OpenClaw. Use when an agent (e.g. a Hermes instance) should continuously research, enter, and exit paper positions on the ai4trade simulated account on a schedule.
metadata:
  openclaw:
    emoji: "🤖"
    requires:
      env:
        - AI4TRADE_TOKEN
      optionalEnv:
        - SCRAPECREATORS_API_KEY
        - XAI_API_KEY
      bins:
        - python3
    primaryEnv: AI4TRADE_TOKEN
    files:
      - "trader/*"
---

# AutoTrader (OpenClaw skill)

Runs the `trader/` engine's autonomous loop inside a persistent OpenClaw
gateway, so it keeps trading the ai4trade **paper** account without a human in
the seat — the same way the Hermes agents stay live on the leaderboard.

> Paper only. Real-money and options execution are never wired into this loop;
> those stay behind the Robinhood MCP confirmation gate.

## Why OpenClaw is the right host

This loop must run on something that stays up. The OpenClaw gateway already is
that — a long-lived daemon on your hardware (the Mac Mini) that runs plugins and
polls heartbeat. A bare `claude`/Codex web session is ephemeral and cannot host
a 24/7 loop; OpenClaw can.

## One-time setup on the host

```bash
# in the AI-Trader checkout on the gateway host
pip install "requests>=2.31.0"
echo "AI4TRADE_TOKEN=<token>" >> .env.secrets   # git-ignored
```

## Run modes

**A. Continuous loop (self-scheduling).** The loop sleeps `--interval` seconds
between cycles and runs until stopped:

```bash
python -m trader.cli loop --execute --interval 900 --daily-cap 5
```

Have OpenClaw supervise it (auto-restart) via `deploy/run-loop.sh`, or run it as
a launchd/systemd/Docker unit (see `deploy/README.md`).

**B. One cycle per heartbeat (gateway-driven).** If you'd rather drive cadence
from the OpenClaw scheduler/heartbeat instead of an internal sleep, invoke a
single bounded cycle each tick:

```bash
python -m trader.cli loop --execute --interval 1 --max-cycles 1
```

Wire this to the gateway's scheduled-task / heartbeat hook (same place the
clawtrader copytrade plugin is configured).

## What each cycle does

1. Pull macro context (live Polymarket rate-path odds).
2. Manage exits — trailing 10% stop (backtest-validated) + hard stop.
3. Score candidates and open new paper positions within the daily cap.
4. Record everything to the journal; update the scorecard.

## Controls

- **Kill switch:** `touch trader/state/STOP` halts before the next cycle.
- **Caps:** `--daily-cap` limits new buys/day; `--max-cycles` bounds a run.
- **Dry-run:** drop `--execute` to log decisions without placing trades.

## Status / inspection

```bash
python -m trader.cli status      # equity, cash, positions, P&L
python -m trader.cli optimize    # re-tune exit rules over saved history
python -m trader.cli copytrade leaders   # match leaderboard agents (paper)
```
