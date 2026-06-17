"""Paper-trading automation engine for AI-Trader.

Drives the ai4trade.ai simulated account through a disciplined, rule-based
loop: pull market intelligence, score candidates, place paper trades, and
track every position on a P&L scorecard.

Real-money execution is intentionally NOT part of this package. The Robinhood
MCP path keeps a human confirmation gate on every live order; this engine only
ever touches the simulated $100k account.
"""

__all__ = ["Ai4TradeClient", "Strategy", "Engine", "Scorecard"]

from .client import Ai4TradeClient
from .strategy import Strategy
from .scorecard import Scorecard
from .engine import Engine
