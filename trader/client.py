"""Thin client for the ai4trade.ai paper-trading + market-intel API.

All calls are scoped to the simulated account identified by the bearer token.
The token is loaded from the AI4TRADE_TOKEN environment variable, falling back
to a git-ignored .env.secrets file at the repo root.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "https://ai4trade.ai/api"
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_secret(name: str) -> str:
    """Return an env var, falling back to a KEY=value line in .env.secrets."""
    val = os.getenv(name)
    if val:
        return val.strip()
    secrets = _REPO_ROOT / ".env.secrets"
    if secrets.exists():
        for line in secrets.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip()
    return ""


class Ai4TradeError(RuntimeError):
    pass


class Ai4TradeClient:
    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = (base_url or _load_secret("AI4TRADE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.token = token or _load_secret("AI4TRADE_TOKEN")
        if not self.token:
            raise Ai4TradeError(
                "No ai4trade token. Set AI4TRADE_TOKEN or add it to .env.secrets."
            )
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {self.token}"})

    # -- low level -------------------------------------------------------
    def _get(self, path: str, **params: Any) -> dict:
        resp = self._session.get(f"{self.base_url}{path}", params=params or None, timeout=self.timeout)
        return self._parse(resp)

    def _post(self, path: str, payload: dict) -> dict:
        resp = self._session.post(f"{self.base_url}{path}", json=payload, timeout=self.timeout)
        return self._parse(resp)

    @staticmethod
    def _parse(resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except ValueError:
            raise Ai4TradeError(f"Non-JSON response ({resp.status_code}): {resp.text[:200]}")
        if resp.status_code >= 400:
            raise Ai4TradeError(f"HTTP {resp.status_code}: {data}")
        return data

    # -- account ---------------------------------------------------------
    def me(self) -> dict:
        """Agent profile: cash, points, reputation."""
        return self._get("/claw/agents/me")

    def positions(self) -> dict:
        """Open positions plus cash balance."""
        return self._get("/positions")

    # -- market intelligence (read-only) ---------------------------------
    def market_overview(self) -> dict:
        return self._get("/market-intel/overview")

    def featured_stocks(self) -> list[dict]:
        data = self._get("/market-intel/stocks/featured")
        return data.get("items", []) if isinstance(data, dict) else []

    def stock_analysis(self, symbol: str) -> dict:
        return self._get(f"/market-intel/stocks/{symbol}/latest")

    # -- execution (paper only) ------------------------------------------
    def place_trade(
        self,
        symbol: str,
        action: str,
        quantity: float,
        market: str = "us-stock",
        content: str = "",
        price: float = 0,
    ) -> dict:
        """Place a simulated trade. price=0 lets the platform fill at market.

        action: buy | sell | short | cover
        """
        payload = {
            "market": market,
            "action": action,
            "symbol": symbol,
            "price": price,
            "quantity": quantity,
            "content": content,
            "executed_at": "now",
        }
        return self._post("/signals/realtime", payload)
