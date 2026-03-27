# Test plan

## Goal

Verify that the bridge behaves correctly across the full interaction lifecycle:

- render
- click / select / modal ingress
- fast ACK
- queueing
- local dispatch or OpenClaw reinjection
- completion / fallback behavior
- routing diagnostics

This plan is written for operator testing before public release.

---

## Baseline prerequisites

Before running interaction tests:

- install the package successfully
- confirm broker and worker services are running
- confirm Discord bot has access to the target test channel
- confirm `openclaw` CLI is available on `PATH`
- confirm the bridge can send at least one test message into the channel

Recommended commands:

```bash
./manage.sh doctor
./manage.sh status
./manage.sh logs
```

---

## Test 1: basic button transport

### Send

```bash
./.venv/bin/python scripts/send_action.py demo-hello --channel-id <CHANNEL_ID>
```

### Verify

- the message renders correctly
- button click does not immediately show `This interaction failed`
- worker handles the click
- a visible completion or silent completion occurs according to policy

### Record

- broker logs
- worker logs
- `./manage.sh doctor` interaction counters

---

## Test 2: local deterministic action

Use a button that maps to local dispatch such as `say_hello` or `discord.reply_text`.

### Verify

- no OpenClaw downstream dependency is required for the success path
- the visible result matches `local_success_text` or the local reply text
- bridge marks the interaction `done`

---

## Test 3: transport success vs action success wording

Use a payload that routes to OpenClaw rather than local dispatch.

### Verify

- success text reflects delivery toward OpenClaw, not guaranteed business completion
- README and docs wording matches real behavior
- operators can distinguish bridge success from downstream task success

---

## Test 4: string select normalization

Send `examples/action_select_and_modal.json`.

### Verify

- select renders correctly
- selected values appear in bridge payload context
- worker preserves value data for reinjection
- no immediate component expiry occurs

---

## Test 5: modal trigger and submit behavior

Send `examples/action_select_and_modal.json`.

### Verify

- clicking the modal trigger opens the modal without expiry
- modal trigger interactions are not processed a second time by the worker after the broker opens the modal
- modal submit is ACKed quickly
- modal fields are normalized and preserved in the reinjected envelope
- `trigger_reusable` and `submit_single_use` behave as documented

### Specific checks

- trigger can be reopened when configured reusable
- submit becomes unavailable after first successful single-use submit
- interaction rows marked `modal-opened` do not produce duplicate follow-up replies

---

## Test 6: single-use button enforcement

Use a non-reusable button example such as `examples/action_approve_cancel.json`.

### Verify

- first click succeeds
- second click gets a clean already-used response
- SQLite state shows the component as `used`

---

## Test 7: restricted user enforcement

Use `examples/action_restricted_button.json`.

### Verify

- allowed user can click successfully
- non-allowed user receives a clean denial message
- no downstream action is executed for denied users

---

## Test 8: delayed completion / fallback behavior

Simulate a downstream problem such as:

- temporary `openclaw` CLI failure
- gateway unavailable
- invalid session hint

### Verify

- interaction is still ACKed quickly
- worker falls back cleanly
- fallback behavior matches status policy
- logs and inbox fallback records capture the failure cause

---

## Test 9: broker restart window

### Procedure

1. send an interactive message
2. restart broker service
3. click during restart window and after recovery

### Verify

- after recovery, normal clicks work again
- docs correctly describe reconnect as best-effort, not guaranteed replay
- no false claims remain in docs about loss-proof recovery

---

## Test 10: channel routing fallback

Send a payload with no `session_hint`.

### Verify

- injector uses `--to channel:<id>`
- reply remains pinned to the originating Discord channel
- delivery diagnostics show fallback channel routing clearly

---

## Test 11: session hint routing

Send a payload with `session_hint`.

### Verify

- injector uses `--session-id ...`
- reply target still points at the originating Discord channel
- delivery logs contain the hint metadata
- operators can tell whether the intended session id was actually valid

---

## Test 12: agent hint routing

Send a payload with `agent_hint`.

### Verify

- injector includes `--agent ...`
- delivery attempts record the chosen agent hint
- behavior remains understandable when both `agent_hint` and `session_hint` are provided

---

## Test 13: doctor observability

Run:

```bash
./manage.sh doctor
```

### Verify

- message / component / interaction counts are readable
- recent interaction rows help diagnose current state quickly
- operators can see queued / processing / done / failed trends without opening SQLite manually

---

## Release gate recommendation

Before publishing, require at least:

- passing validation
- one successful basic button test
- one successful select test
- one successful modal test
- one verified single-use test
- one verified restricted-user test
- one verified delayed/fallback test
- one verified session-hint delivery test
- one broker restart / recovery check

If any of those fail, publish only as preview / beta rather than stable.
