# discord-component-v2

`discord-component-v2` is an OpenClaw companion package for reliable Discord Components v2 workflows.

It exists to bridge the current gap between:

- pretty Discord Components v2 presentation
- reliable click handling that should not immediately expire

## What this package does

This package keeps the Discord rendering path and the interaction handling path under your control:

- sends bridge-managed Discord Components v2 messages directly to Discord
- ACKs button, select, and modal interactions quickly
- stores interaction metadata in SQLite
- reinjects the interaction into OpenClaw in the originating Discord channel
- supports lightweight local deterministic actions for smoke tests

## Supported interaction surfaces

Bridge-managed interactive V2 messages (`scripts/send_action.py`):

- buttons
- string selects
- user selects
- role selects
- mentionable selects
- channel selects
- modal trigger buttons
- modal submit handling for text + select-family fields

Read-only presentation (`scripts/send_card.py`):

- OpenClaw Components v2 card payloads for presentation-first messages

## Why this exists

Recent OpenClaw Discord issue reports describe several failure modes with built-in component handling, including immediate expiry, missing routing back to the agent, registry loss after restart, and missing original-message context on click. This package avoids depending on OpenClaw's in-process component registry for the critical interaction path and keeps the state in a local SQLite bridge instead.

## Design goals

- use Discord Components v2 for interactive bridge messages
- ACK within Discord's interaction window
- keep reply routing pinned to the originating Discord channel
- keep click handling deterministic even when OpenClaw's built-in component registry is unstable
- avoid treating ingress success as business completion
- keep packaging clean for ClawHub-style distribution

## Requirements

- Linux or Linux-like environment
- Python 3 with `venv` support, or `uv`
- `sqlite3` available to Python
- `openclaw` CLI on `PATH` for card sending and agent reinjection
- a configured Discord bot token in OpenClaw config or `DISCORD_BOT_TOKEN`

## Install

```bash
unzip discord-component-v2.zip
cd discord-component-v2
chmod +x install.sh manage.sh uninstall.sh validate.sh
./install.sh
```

On Debian / Ubuntu, if Python virtual environment support is missing:

```bash
./install.sh --install-system-deps
```

## Verify

```bash
./manage.sh doctor
./manage.sh status
./validate.sh
```

## Quick interactive test

```bash
./manage.sh smoke-test
./.venv/bin/python scripts/send_action.py demo-hello --channel-id <CHANNEL_ID>
```

## Send a V2 interactive message from JSON

```bash
./.venv/bin/python scripts/send_action.py file \
  --channel-id <CHANNEL_ID> \
  --json-file examples/action_approve_cancel.json
```

## Send a presentation card

```bash
./.venv/bin/python scripts/send_card.py file \
  --channel-id <CHANNEL_ID> \
  --json-file examples/card_daily_briefing.json
```

## Interaction status behavior

By default, the broker defers the interaction and the worker edits the interaction response with a short status message.

Important distinction:

- transport success means the interaction was accepted and delivered toward OpenClaw
- business-action success means the requested task actually completed

The default worker success text reflects transport success, not guaranteed business-action completion.

You can change the global default behavior with `DISCORD_COMPONENT_V2_INTERACTION_STATUS`:

- `full` — default; show success, delay, and failure statuses
- `errors-only` — suppress success status, keep delay / failure notices
- `silent` — remove the deferred placeholder and stay silent

You can also override behavior per payload with `interaction.response`, for example:

```json
{
  "interaction": {
    "response": {
      "mode": "errors-only",
      "show_success": false,
      "transport_success_text": "Queued for agent processing.",
      "local_success_text": "Done.",
      "delayed_text": "Accepted, but delivery was delayed.",
      "error_text": "The action could not be completed."
    }
  }
}
```

You can additionally carry optional routing hints in payloads:

```json
{
  "agent_hint": "discord-test",
  "session_hint": "session:project-alpha",
  "thread_hint": "daily-briefing"
}
```

These hints are stored with the component record and included in the reinjected envelope for downstream handling. They are also recorded in delivery attempts and inbox fallback records to make routing diagnostics easier. They improve observability and future routing control, but they do not by themselves guarantee exact session affinity.

Example:

```bash
export DISCORD_COMPONENT_V2_INTERACTION_STATUS=errors-only
```

## Important operational notes

- Discord HTTP requests should use a valid `DiscordBot (url, version)` style User-Agent. This package now does that.
- Discord Components v2 messages require the `IS_COMPONENTS_V2` flag, and once set it cannot be removed from that message.
- Deferred component interactions must be acknowledged quickly; otherwise Discord will show `This component has expired.`
- Interaction tokens are only valid for a limited time, so delayed completion should fall back cleanly.
- This package pins reinjection to the originating Discord channel. That is stronger than ad-hoc routing, but it is not the same thing as guaranteed session affinity in every shared-channel scenario.
- For critical click paths, this package does not rely on OpenClaw's in-process component registry.
- Broker reconnect is automatic, but current recovery is best-effort rather than guaranteed event replay.
- Modal trigger and modal submit single-use behavior can now be controlled separately in payloads.

## Troubleshooting

See `docs/TROUBLESHOOTING.md` for common cases such as:

- 403 / Cloudflare-style blocks
- expired components
- missing channel access
- gateway disconnects and reconnect behavior
- fallback delivery after deferred interaction expiry

## Packaging hygiene

Do not publish:

- real bot tokens
- private channel IDs
- `.venv`
- runtime SQLite state
- `__pycache__` / `.pyc`

## Uninstall

Remove services only:

```bash
./uninstall.sh
```

Remove services and installed files:

```bash
./uninstall.sh --purge
```
