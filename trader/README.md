# Paper-Trading Engine

A disciplined, rule-based automation layer that trades the **ai4trade.ai
simulated account** ($100k of paper capital, real market prices). It pulls
market intelligence, scores candidates on transparent rules, places paper
trades, and tracks every position on a P&L scorecard.

> **This package never touches real money.** Live trading goes through the
> Robinhood MCP, which keeps a human confirmation gate on every order. The
> intent is to prove a strategy here first, then mirror only what works.

## Setup

The engine authenticates with an ai4trade bearer token, read from
`AI4TRADE_TOKEN` (env) or the git-ignored `.env.secrets` at the repo root.

```bash
pip install -r service/requirements.txt   # provides `requests`
```

## Usage

```bash
python -m trader.cli status         # current scorecard: equity, cash, positions, P&L
python -m trader.cli scan           # rank featured candidates + show why each passed/failed
python -m trader.cli run            # DRY-RUN: print the buys it would place
python -m trader.cli run --execute  # place those paper trades (simulated $)
```

## How decisions are made

`trader/strategy.py` holds a `StrategyConfig` with explicit, tunable rules:

- platform signal must be a **buy** with score ≥ `min_signal_score`
- trend must be bullish, with at least `min_room_to_resistance_pct` upside to
  resistance, and not already extended past `max_return_5d_pct` over 5 days
- stand down entirely when the macro regime reads **bearish**
- size each new position at `position_pct_of_cash` of cash, cap at
  `max_positions` concurrent holdings
- every accepted candidate gets a derived **stop** (structural support, else
  −8%) and **target** (resistance, else +15%)

Every accept/reject prints its reasons, so the logic is auditable rather than a
black box. This is a baseline to backtest and tune — not a finished alpha.

## Layout

| File | Role |
|------|------|
| `client.py` | ai4trade API client (account, positions, market-intel, place trade) |
| `strategy.py` | candidate scoring + position sizing rules |
| `engine.py` | research → rank → decide → (paper) trade → record |
| `scorecard.py` | live portfolio snapshot, P&L, append-only trade journal |
| `cli.py` | `status` / `scan` / `run [--execute]` |
| `state/` | local journals (git-ignored) |
