# Troubleshooting

## 403 with Cloudflare-style block or code 1010 / 40333

Likely causes:

- invalid or missing DiscordBot-style `User-Agent`
- proxy/CDN interference
- malformed HTTP client behavior

What this package does:

- uses a valid `DiscordBot (url, version)` style User-Agent on direct Discord HTTP calls

What to check:

- validate that the bot token is correct
- avoid unusual HTTP proxies that rewrite headers
- rerun `./manage.sh doctor`

## 403 missing access / missing permissions

Likely causes:

- bot lacks access to the channel
- wrong bot token or wrong guild
- trying to use a channel ID from a different server

Check:

- bot has View Channels, Send Messages, Read Message History, Embed Links, and Attach Files
- the bot was invited with the expected application

## `This component has expired` on first click

Likely causes:

- interaction was not ACKed inside Discord's time window
- broker was down or restarting during the click window
- the message was not sent through the bridge-managed path
- handler state was lost or the component record is missing

What this package does:

- broker ACKs first, then processes
- component metadata is stored in local SQLite instead of a transient in-process map

Important limitation:

- the broker reconnects automatically, but current recovery is best-effort rather than loss-proof session resume
- a short click-loss window may still exist during restart or reconnect periods

## `This action is no longer available` or `This form is no longer available`

Likely causes:

- no matching component record was found in SQLite
- the original message id was not available during lookup
- the message was created outside the bridge-managed send path
- local state was purged or replaced

What to check:

- verify the message was sent with `scripts/send_action.py`
- inspect service logs with `./manage.sh logs`
- inspect local bridge state before purging it

## `This action was already used` or `This form was already submitted`

Likely causes:

- the component is configured as single-use
- the button was double-clicked
- another user claimed the same component first

Important note:

- single-use applies to the stored bridge component record
- modal trigger and modal submit paths can have different practical UX expectations; document the intended behavior for a given payload

## Deferred response could not be updated

Likely causes:

- interaction token expired before completion
- Discord rejected the update
- the original deferred response is no longer editable

What this package does:

- attempts to complete via the original interaction response first
- falls back to a channel message unless `DISCORD_COMPONENT_V2_INTERACTION_STATUS=silent` suppresses it

Important distinction:

- a successful deferred completion message may only mean the event reached OpenClaw
- it does not necessarily mean the requested business action fully completed

## Interaction was accepted but the requested action did not happen

Likely causes:

- the worker successfully delivered the event to OpenClaw, but downstream agent behavior did not complete the intended task
- the semantic action depends on prompt interpretation rather than a native structured runtime contract
- routing reached the originating channel but not the intended session context

What to check:

- confirm whether the event was delivered to OpenClaw or only queued
- inspect worker logs and any delivery attempt records
- verify whether session / agent affinity matters for the action you are testing

## OpenClaw reinjection did not deliver

Likely causes:

- `openclaw` CLI is not on `PATH`
- the gateway is stopped or draining
- the originating channel target is unavailable
- channel routing succeeded but the desired session context was not the one that handled the event

What to check:

- `openclaw status`
- `./manage.sh doctor`
- `./manage.sh logs`

## Gateway disconnects / WebSocket closes

Likely causes:

- normal Discord gateway disconnects
- network stalls or heartbeats not being acknowledged
- temporary Discord-side issues

What this package does:

- broker reconnects with backoff
- systemd service templates also restart the process if it exits

Important limitation:

- current reconnect logic is designed for recovery, not guaranteed event replay
- if the broker was offline during a click, that click may be lost
