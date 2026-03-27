# Operational notes

## Supported features

- read-only Components v2 messages
- interactive Components v2 messages managed by the local bridge
- SQLite-backed component registry, queue state, and delivery logs
- worker-based reinjection into OpenClaw
- modal trigger and modal submit handling through the broker
- optional `allowed_users` enforcement for bridge-managed payloads
- user-level service management
- optional interaction status suppression via `DISCORD_COMPONENT_V2_INTERACTION_STATUS`

## Architecture summary

The package is split into four layers:

1. send layer: renders Discord Components v2 messages directly to Discord
2. broker layer: receives interaction events and ACKs them quickly
3. worker layer: normalizes state and decides local dispatch vs OpenClaw reinjection
4. reinjection layer: sends a structured text envelope back into OpenClaw through the CLI

This split is intentional. It reduces dependence on transient in-process component state and gives operators clearer debugging boundaries.

## Important cautions

- `IS_COMPONENTS_V2` changes how Discord accepts and renders the message body.
- deferred interaction responses are acknowledgements, not finished action results
- interaction tokens expire, so late completions need a fallback path
- reply routing is pinned to the originating Discord channel, but that is not the same thing as guaranteed session affinity
- direct Discord HTTP calls should use a valid DiscordBot-style User-Agent
- downstream OpenClaw execution currently relies on a structured text envelope, not a native typed bridge event contract

## Routing semantics

Current routing is strongest at the channel level.

- the broker captures the originating Discord channel id
- the worker reinjects back toward that same Discord channel
- this is designed to preserve reply locality

The injector can also use optional hints:

- `agent_hint` -> `openclaw agent --agent ...`
- `session_hint` -> `openclaw agent --session-id ...`
- if `session_hint` is absent, injector falls back to `--to channel:<id>` routing

Current limitation:

- if multiple conversational contexts share one channel, deterministic session affinity still depends on OpenClaw's current routing behavior and on the validity of any supplied session id
- `thread_hint` is currently diagnostic only
- operators should not over-claim that the bridge alone guarantees exact session targeting in every shared-channel scenario

## Completion semantics

There are two different kinds of success to think about:

1. transport success: the interaction was accepted and delivered toward OpenClaw
2. business-action success: the requested task actually completed

The bridge is best at transport success. Business-action success still depends on downstream OpenClaw behavior.

When documenting or presenting status messages, keep that distinction explicit.

## Reconnect semantics

The broker reconnects automatically with backoff.

Current limitation:

- reconnect behavior is recovery-oriented, not a guarantee of event replay
- if the broker is down or restarting while a user clicks a component, that click can still be lost

## Workspace isolation

This package should be treated as workspace-scoped runtime state, not as a single shared global daemon.

Current hardening:

- state directory is namespaced per workspace
- default install directory is namespaced per workspace
- default systemd user service names are namespaced per workspace
- systemd services export a workspace id so broker and worker resolve the same state paths
- broker startup uses a token-based local lock file to reduce duplicate consumers for the same Discord bot token on the same machine

Important limitation:

- the token lock is local-machine coordination, not a distributed lock
- if multiple workspaces intentionally share the same Discord bot token across different hosts, they can still compete for the same Discord interaction stream

## Security and privacy

- treat `DISCORD_BOT_TOKEN` as a secret
- keep the bot in a private or operator-controlled server when possible
- review sample JSON files before adapting them to production data
- the SQLite database stores interaction metadata and delivery attempts locally
