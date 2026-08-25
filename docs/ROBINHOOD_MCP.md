# Robinhood Trading MCP Setup

This project ships a project-scoped MCP configuration (`.mcp.json`) that connects AI agents to Robinhood's official Agentic Trading MCP server:

```
https://agent.robinhood.com/mcp/trading
```

## Prerequisites

- A Robinhood primary individual investing account in good standing.
- A Robinhood Agentic account (onboarding auto-opens the first time you connect to the MCP server). You fund it with a dedicated budget, separate from your main account.
- Onboarding and agent authentication must be completed on a **desktop** device.

## Setup

### Claude Code (CLI)

The `.mcp.json` at the repo root is picked up automatically when you open this project — approve the server when prompted, then run:

```
/mcp
```

and complete the Robinhood OAuth flow in your browser.

Alternatively, register it globally outside this repo:

```bash
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
```

### Claude Desktop / claude.ai

Settings → Connectors → **Add custom connector**, then paste:

```
https://agent.robinhood.com/mcp/trading
```

### Other MCP-compatible agents

Add an HTTP (streamable) MCP server pointing at the same URL. Authentication is OAuth handled by Robinhood — your agent never sees your Robinhood password.

## Notes

- All trades execute against your Agentic account's dedicated budget only.
- Official documentation: https://robinhood.com/us/en/support/agentic-trading
