# discord-component-v2

Use this package when you need Discord Components v2 with a more reliable click bridge than the default in-process registry path.

## Use

- `scripts/send_card.py` for presentation-first read-only cards
- `scripts/send_action.py` for bridge-managed interactive Components v2 messages

## Supported bridge-managed interactions

- button clicks
- string / user / role / mentionable / channel selects
- modal trigger buttons
- modal submit events

## Rules

1. Fast ACK first, then process.
2. Keep replies pinned to the originating Discord channel.
3. Treat `HEARTBEAT_OK` only as ingress success, never as business completion.
4. Prefer structured payloads:
   ```json
   {"kind":"dispatch","target":"workflow.retry_last_job","args":{"job_id":"job-001"}}
   ```
5. Keep actions short, explicit, and preferably idempotent.

## Recommended commands

Interactive V2 message:
```bash
python scripts/send_action.py file --channel-id <CHANNEL_ID> --json-file examples/action_approve_cancel.json
```

Presentation card:
```bash
python scripts/send_card.py file --channel-id <CHANNEL_ID> --json-file examples/card_daily_briefing.json
```

Local demo:
```bash
python scripts/send_action.py demo-hello --channel-id <CHANNEL_ID>
```

## Do not publish

- real tokens
- real channel IDs
- `.venv`
- runtime SQLite state
- `__pycache__`
