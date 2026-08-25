"""Social-media research integration (read-only, for signal — never posting).

The actual cross-platform research engine is the open-source last30days-skill
(github.com/mvanhorn/last30days-skill, MIT), which covers Reddit, X/Twitter,
YouTube, TikTok, Instagram, Bluesky, Hacker News, and Polymarket. Each platform
is gated on an API key/credential.

This module does NOT post anywhere. It (1) reports which platforms are
configured, and (2) shells out to a local last30days install for a topic when
one is available (set LAST30DAYS_DIR). Keyless sources already wired directly
into the engine: Polymarket (trader/research.py).

LinkedIn and Facebook are NOT supported by last30days; don't promise them.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .client import _load_secret  # reuses .env.secrets / env loader

# platform -> the credential(s) that unlock it (any listed group enables it)
PLATFORM_KEYS: dict[str, list[str]] = {
    "Reddit / TikTok / Instagram": ["SCRAPECREATORS_API_KEY"],
    "X / Twitter": ["XAI_API_KEY", "AUTH_TOKEN"],
    "Bluesky": ["BSKY_HANDLE"],
    "Truth Social": ["TRUTHSOCIAL_TOKEN"],
    "Web search": ["BRAVE_API_KEY", "EXA_API_KEY", "PARALLEL_API_KEY"],
    "LLM synthesis": ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"],
}
# Always available with no key (public APIs):
KEYLESS = ["YouTube", "Hacker News", "Polymarket (wired into engine)"]


@dataclass
class PlatformStatus:
    name: str
    enabled: bool
    via: str  # which key satisfied it, or "missing"


def status() -> list[PlatformStatus]:
    out: list[PlatformStatus] = []
    for platform, keys in PLATFORM_KEYS.items():
        hit = next((k for k in keys if _load_secret(k)), None)
        out.append(PlatformStatus(platform, bool(hit), hit or "missing"))
    return out


def configured_platforms() -> list[str]:
    return [s.name for s in status() if s.enabled] + KEYLESS


def research(topic: str) -> str:
    """Run last30days for `topic` if a local install is configured.

    Returns the synthesized briefing, or a clear message about what's missing.
    """
    d = os.getenv("LAST30DAYS_DIR") or _load_secret("LAST30DAYS_DIR")
    if not d or not Path(d).exists():
        return (
            "last30days not installed. Clone github.com/mvanhorn/last30days-skill "
            "and set LAST30DAYS_DIR to its path, then add the API keys below."
        )
    script = Path(d) / "scripts" / "last30days.py"
    if not script.exists():
        return f"LAST30DAYS_DIR={d} has no scripts/last30days.py."
    try:
        proc = subprocess.run(
            ["python3", str(script), topic],
            capture_output=True, text=True, timeout=300,
            env={**os.environ},
        )
        return proc.stdout or proc.stderr or "(no output)"
    except subprocess.TimeoutExpired:
        return "last30days timed out (300s)."
    except Exception as e:  # noqa: BLE001
        return f"last30days failed: {e}"
