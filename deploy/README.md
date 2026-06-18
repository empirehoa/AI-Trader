# Deploying the autonomous loop (persistent / 24-7)

The `loop` command runs forever, but a process only survives as long as its host.
To have it "automatically work in a loop" continuously, run it on a machine that
stays up. Pick whichever fits:

| Host | Use | File |
|------|-----|------|
| **Mac Mini (macOS)** | always-on home/office Mac | `com.empirehoa.ai-trader-loop.plist` |
| **Linux server** | VPS / box with systemd | `ai-trader-loop.service` |
| **Anywhere with Docker** | simplest, self-restarting | `Dockerfile` + `docker-compose.yml` |

All three run `deploy/run-loop.sh`, which calls
`python -m trader.cli loop --execute` and logs to `trader/state/logs/loop.log`.

## Prerequisites (once)

1. Clone this repo on the host and `cd` into it.
2. `pip install "requests>=2.31.0"` (or use the Docker option, which handles it).
3. Create `.env.secrets` at the repo root with `AI4TRADE_TOKEN=...`
   (plus any social/research API keys). This file is git-ignored.

## Mac Mini (launchd)

```bash
# edit the CHANGE_ME paths in the plist first
cp deploy/com.empirehoa.ai-trader-loop.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.empirehoa.ai-trader-loop.plist
# stop: launchctl unload ~/Library/LaunchAgents/com.empirehoa.ai-trader-loop.plist
```

## Linux (systemd)

```bash
sudo cp deploy/ai-trader-loop.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-trader-loop
journalctl -u ai-trader-loop -f
```

## Docker (any OS)

```bash
docker compose -f deploy/docker-compose.yml up -d   # start, auto-restarts
docker compose -f deploy/docker-compose.yml logs -f # watch
docker compose -f deploy/docker-compose.yml down    # stop
```

## Controls

- **Kill switch:** `touch trader/state/STOP` halts before the next cycle (works
  under any host). Remove the file to allow restart.
- **Tuning:** set `INTERVAL`, `DAILY_CAP`, `MODE` (env vars) — see `run-loop.sh`.
- **Dry-run:** set `MODE=""` to log decisions without placing paper trades.

## Scope reminder

This loop trades the **simulated** ai4trade account only. Real-money and options
execution stay behind the Robinhood MCP confirmation gate — they are never wired
into this unattended loop.
