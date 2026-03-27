# ClawHub-style package summary

**discord-component-v2** adds a safer split-path Discord UX for OpenClaw.

## Best for

- private Discord workspaces
- operator-controlled bots
- approval / retry / confirmation workflows
- deployments that need richer Discord UI without losing debuggability

## Core features

- Components v2 read-only cards
- bridge-managed Components v2 interactive flows
- broker / worker architecture
- SQLite interaction history
- deterministic local smoke-test actions
- OpenClaw reinjection for complex workflows
- systemd-managed background services
- `uv`-first installation with `python3 -m venv` fallback

## Cautions

- Linux-first package
- expects user-level `systemd` for background services
- the Discord bot token must already be configured securely
- OpenClaw reinjection still depends on the local `openclaw` CLI and downstream agent health
- gateway disconnects and delayed completions are mitigated, not eliminated
