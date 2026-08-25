"""Copy-trading: match ai4trade leaderboard agents on the paper account.

Discover top agents, follow selected leaders, and let the platform mirror
their positions 1:1 onto our simulated account (copied positions show up with
source="copied:<leader_id>"). This is how we "match leaderboard users" —
entirely on the $100k paper account.

Real-money copy-trading (e.g. mirroring on-chain Polymarket wallets) is NOT
wired here: there's no funded wallet or trading connector, and it would bypass
the confirm-every-order rule on real capital.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import Ai4TradeClient


@dataclass
class Leader:
    agent_id: int
    name: str
    signal_count: int
    total_pnl: float


def leaderboard(client: Ai4TradeClient, limit: int = 15) -> list[Leader]:
    rows = client.signals_grouped(limit=limit)
    leaders = [
        Leader(
            agent_id=int(a.get("agent_id", 0)),
            name=str(a.get("agent_name", "?")),
            signal_count=int(a.get("signal_count", 0) or 0),
            total_pnl=float(a.get("total_pnl", 0) or 0),
        )
        for a in rows
    ]
    # Rank by realized PnL where available, else by activity.
    leaders.sort(key=lambda l: (l.total_pnl, l.signal_count), reverse=True)
    return leaders


def follow_leaders(client: Ai4TradeClient, leader_ids: list[int]) -> list[dict]:
    results = []
    for lid in leader_ids:
        try:
            r = client.follow(lid)
            results.append({"leader_id": lid, "ok": bool(r.get("success", True)), "resp": r})
        except Exception as e:  # noqa: BLE001
            results.append({"leader_id": lid, "ok": False, "error": str(e)})
    return results


def copied_positions(client: Ai4TradeClient) -> list[dict]:
    """Positions currently mirrored from a leader (source startswith 'copied')."""
    pos = client.positions().get("positions", [])
    return [p for p in pos if str(p.get("source", "")).startswith("copied")]
