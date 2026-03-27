# discord-component-v2

**Current status:** beta / release candidate

Use this package when you need Discord Components v2 with a more reliable bridge than the default in-process component registry path.

It is intended for OpenClaw setups that want:
- bridge-managed Discord Components v2 messages
- fast interaction acknowledgement for buttons, selects, and modal flows
- SQLite-backed interaction state
- worker/downstream reinjection into OpenClaw
- better runtime isolation and operator diagnostics

## What this package includes

- `scripts/send_card.py` for presentation-first read-only cards
- `scripts/send_action.py` for bridge-managed interactive Components v2 messages
- button clicks
- string / user / role / mentionable / channel selects
- modal trigger buttons
- modal submit events
- local deterministic actions for smoke tests
- routing hints such as `agent_hint`, `session_hint`, and `thread_hint`
- `manage.sh doctor` diagnostics

## Quick start

Make scripts executable and install:

```bash
chmod +x install.sh manage.sh uninstall.sh validate.sh
./install.sh
```

Verify the local environment:

```bash
./manage.sh doctor
./validate.sh
```

Service templates are packaged under `scripts/systemd/` so service registration does not depend on root-level directories that may be omitted by external packaging systems.

If user systemd is unavailable or service registration is skipped, you can still run the bridge manually:

```bash
./.venv/bin/python scripts/broker_gateway.py
./.venv/bin/python scripts/worker.py
```

## First test

Send a demo interactive message:

```bash
./.venv/bin/python scripts/send_action.py demo-hello --channel-id <CHANNEL_ID>
```

Send a JSON-defined bridge action message:

```bash
./.venv/bin/python scripts/send_action.py file \
  --channel-id <CHANNEL_ID> \
  --json-file examples/action_approve_cancel.json
```

## Recommended usage rules

1. ACK fast, then process.
2. Keep replies pinned to the originating Discord channel.
3. Treat bridge transport success separately from downstream action success.
4. Prefer structured payloads, for example:
   ```json
   {"kind":"dispatch","target":"workflow.retry_last_job","args":{"job_id":"job-001"}}
   ```
5. Keep actions short, explicit, and preferably idempotent.

## Important notes

- Modal submit handling currently favors stability over richer interaction-native follow-up replies.
- Duplicate-consumer protection is local to one host and does not coordinate across multiple machines using the same Discord bot token.
- Workspace-scoped runtime isolation is built in for install paths, state paths, and service naming.

## Learn more

For full details, see:
- `README.md`
- `docs/TEST_PLAN.md`
- `docs/TROUBLESHOOTING.md`
- `docs/OPERATIONAL_NOTES.md`

## Do not publish

- real tokens
- real channel IDs
- `.venv`
- runtime SQLite state
- runtime lock files
- `__pycache__`
