# Patch notes — 2026-03-27

## What changed

- `send_action.py`
  - now sends bridge-managed **Discord Components v2** messages directly to Discord
  - supports buttons, select menus, and modal triggers
  - stores bridge-managed component metadata in SQLite
  - keeps backward compatibility with the older `content` + `buttons` JSON shape

- `broker_gateway.py`
  - handles button/select `MESSAGE_COMPONENT` interactions
  - handles `MODAL_SUBMIT` interactions
  - sends fast ACKs and cleaner ephemeral denial messages
  - no longer depends on editing the source message to disable buttons

- `worker.py`
  - builds richer normalized prompts with source message summary + interaction context
  - includes select values and modal field submissions in the event envelope
  - keeps reply routing pinned to the originating Discord channel

- `injector.py`
  - no longer requires `HEARTBEAT_OK` in stdout to consider CLI reinjection successful
  - treats process exit code `0` as transport success

- `schema/init.sql`
  - single-use claims are now keyed by `(message_id, custom_id)` instead of `(message_id, semantic_action)`

- package hygiene
  - removed `__pycache__` / `.pyc` files from the packaged output
  - examples updated to show V2 interactive flows

## Why this matters

This patch is aimed at the practical failure modes seen in current OpenClaw Discord component reports:

- immediate expiry on first click
- component registry instability
- routing not returning to the agent correctly
- missing context when a button is clicked
- brittle success detection tied to `HEARTBEAT_OK`

## Remaining caveats

- `send_card.py` is still presentation-first and strips interactive controls on purpose.
- The bridge-managed modal implementation currently supports text inputs and select-family modal fields, not every Discord modal component variant.
- Complex actions still depend on OpenClaw CLI reinjection and downstream agent/tool execution.
