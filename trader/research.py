"""Prediction-market research signal (Polymarket).

Reads live, real-money odds from Polymarket's public Gamma search API. No API
key required. This is a *catalyst / awareness* signal — what the market is
pricing for macro and event risk — never a standalone buy trigger.

The public-Gamma approach is adapted from the open-source last30days-skill
(github.com/mvanhorn/last30days-skill, MIT), trimmed to a dependency-light
reader that fits the trader package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

GAMMA_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (AI-Trader research)"}


@dataclass
class MarketOdds:
    question: str
    outcomes: list[tuple[str, float]]  # (label, probability 0..1), sorted desc
    volume_24h: float
    liquidity: float

    @property
    def headline(self) -> str:
        if not self.outcomes:
            return self.question
        label, prob = self.outcomes[0]
        return f"{self.question}  →  {label} {prob * 100:.0f}%"


@dataclass
class EventOdds:
    title: str
    slug: str
    markets: list[MarketOdds]


def _parse_json_array(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return []
    return []


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _parse_market(m: dict) -> MarketOdds | None:
    labels = _parse_json_array(m.get("outcomes"))
    prices = _parse_json_array(m.get("outcomePrices"))
    pairs: list[tuple[str, float]] = []
    for i, label in enumerate(labels):
        if i < len(prices):
            pairs.append((str(label), _safe_float(prices[i])))
    pairs.sort(key=lambda p: p[1], reverse=True)
    if not pairs:
        return None
    return MarketOdds(
        question=str(m.get("question") or m.get("groupItemTitle") or "?"),
        outcomes=pairs,
        volume_24h=_safe_float(m.get("volume24hr")),
        liquidity=_safe_float(m.get("liquidity")),
    )


def search_events(topic: str, limit: int = 5, max_markets: int = 3) -> list[EventOdds]:
    """Return active Polymarket events matching `topic`, with odds.

    Markets within each event are ranked by 24h volume (where the real money
    and price discovery is) and capped at `max_markets`.
    """
    params = {"q": topic, "limit_per_type": limit, "events_status": "active"}
    try:
        resp = requests.get(GAMMA_SEARCH_URL, params=params, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    events: list[EventOdds] = []
    for ev in data.get("events", []) or []:
        markets = [pm for m in (ev.get("markets") or []) if (pm := _parse_market(m))]
        markets.sort(key=lambda mk: mk.volume_24h, reverse=True)
        if not markets:
            continue
        events.append(
            EventOdds(
                title=str(ev.get("title") or "?"),
                slug=str(ev.get("slug") or ""),
                markets=markets[:max_markets],
            )
        )
    return events
