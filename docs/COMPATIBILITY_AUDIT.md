# Compatibility audit

This package was reviewed against current Discord and OpenClaw documentation plus recent OpenClaw Discord issue reports.

## Confirmed alignment

- Component click ACK uses a deferred interaction callback so the click is acknowledged quickly.
- Ephemeral denial for unauthorized or expired clicks uses a standard interaction callback message with flags.
- Read-only cards are sent through OpenClaw's Discord components path. Interactive flows are sent directly to Discord and handled by the local bridge.
- Reply routing stays pinned to the originating Discord channel instead of letting the model choose an arbitrary channel.
- OpenClaw's `components.reusable` and `allowedUsers` ideas are mirrored locally through `reusable` and `allowed_users` / `allowedUsers`.

## Package-specific design decisions

- Critical approval / retry / cancel flows intentionally avoid depending on OpenClaw's current in-process component registry.
- `allowed_users` enforcement is implemented at the broker layer for bridge-managed component payloads.
- Ingress success is not treated as business completion.
- The broker now reconnects with backoff after gateway-level failures instead of assuming a perfect long-lived socket.

## Remaining caveats

- Complex actions still depend on OpenClaw CLI reinjection succeeding and the downstream model / tool flow completing successfully.
- If the interaction token is no longer valid when the worker tries to update the deferred response, the package falls back to a normal channel message unless silent / errors-only mode suppresses it.
- `send_card.py` is intentionally presentation-first. Use `send_action.py` for interactive controls.
