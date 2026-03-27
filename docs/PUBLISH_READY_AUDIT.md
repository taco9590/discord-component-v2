# Publish-ready audit

## Overall assessment

`discord-component-v2` is already beyond a toy demo. The package has a credible separation between:

- send layer (`scripts/send_action.py`)
- broker layer (`scripts/broker_gateway.py`)
- worker layer (`scripts/worker.py`)
- reinjection layer (`scripts/injector.py`)

That separation is the right shape for a Discord Components v2 bridge intended to work around unstable in-process component handling.

Current state: **usable beta / pre-stable release**.

It is reasonable for real testing and operator use, but a few semantics and operational edges should be tightened before calling it fully stable and publish-ready.

---

## What is strong already

### 1. Fast ACK ownership is in the right place

The broker receives `INTERACTION_CREATE` directly from the Discord Gateway and responds quickly with one of:

- defer (`type=5`)
- ephemeral error (`type=4`)
- modal open (`type=9`)

This is the correct architectural answer to the most common Discord interaction failure mode: late acknowledgement leading to `This component has expired`.

### 2. Presentation and execution are separated cleanly

The package does not overload one path with too many jobs.

- sending UI is separate from
- receiving interactions, which is separate from
- reinjecting into OpenClaw

This makes debugging and future changes more manageable.

### 3. Bridge state lives outside transient OpenClaw memory

SQLite storage for component registrations, message summaries, interaction events, delivery attempts, and single-use claims is a strong choice.

This is materially better than relying on an in-process registry when the main goal is survivable, deterministic interaction handling.

### 4. Local deterministic actions make smoke testing practical

The local dispatch paths in `worker.py` provide a useful split between:

- bridge transport correctness
- downstream OpenClaw reinjection correctness

That is exactly what operators need when diagnosing failures.

---

## Main risks before stable release

## 1. Reinjection is rich, but still text-contract based

The worker builds a strong JSON envelope and sends it back into OpenClaw as a text prompt through the CLI.

That means the bridge has:

- good transport metadata
- good contextual payloads
- but only a **prompt-level execution contract**, not a runtime-level structured contract

### Why this matters

The package can say:

- which component was clicked
- who clicked it
- which channel it came from
- what values were selected
- what semantic action is intended

But OpenClaw still has to interpret that through a model-facing text message rather than a typed native event interface.

### Risk

Changes in prompting, routing, or model behavior can affect what happens after successful reinjection.

### Recommended improvement

Prefer one of these, in order of strength:

1. a native structured ingress path in OpenClaw for bridge events
2. a documented and versioned bridge envelope contract consumed by OpenClaw
3. stronger session / agent hints carried through and used deterministically

## 2. Transport success and action success are not fully separated in UX

The current worker can report success after the interaction has been delivered to OpenClaw, even though the requested business action may not have completed yet.

Current status text such as `✅ Delivered to the agent.` is honest if read carefully, but it still risks being interpreted as completion.

### Recommended improvement

Use explicit phases:

- accepted
- delivered to OpenClaw
- completed locally
- failed to deliver
- business action completed

Treat the current worker success path as **transport success**, not **action success**.

## 3. Follow-up and original-response handling need per-action policy

Right now the package supports broad modes such as:

- `full`
- `errors-only`
- `silent`

That is useful, but too coarse for all real workflows.

### Missing capability

Different actions want different response policies:

- some should stay silent on success
- some should patch the deferred placeholder
- some should post a visible channel message
- some should only surface failures

### Recommended improvement

Allow response policy fields in the component payload, for example:

```json
{
  "interaction": {
    "response": {
      "mode": "silent",
      "success_text": "Queued.",
      "error_text": "Could not process this action.",
      "on_success": "delete_original"
    }
  }
}
```

## 4. Channel routing is present; session affinity is still weak

The reinjection path pins delivery to the originating Discord channel, which is good.

However, channel routing is not the same as deterministic session affinity. If the same channel has multiple active contexts, the current package depends heavily on OpenClaw's channel routing behavior.

### Recommended improvement

Persist and use hints such as:

- `session_hint`
- `agent_hint`
- `thread_hint`
- origin message id / origin session key

The schema already hints at this direction; finishing it would materially strengthen the package.

## 5. Gateway reconnect behavior is good enough for beta, but not loss-proof

The broker reconnects with backoff. That is good.

But it does not currently implement gateway resume semantics or sequence-based recovery.

### Recommended improvement

Either:

- implement sequence tracking + resume where practical, or
- document honestly that reconnect is best-effort and a short click-loss window may exist during restart/reconnect periods

## 6. Modal trigger and modal submit single-use semantics need clarification

The current structure can claim the trigger and the submit as separate components. That may be fine, but the UX expectations vary.

### Recommended improvement

Separate policy for:

- trigger reusability
- submit single-use behavior

A common default is:

- modal trigger reusable
- modal submit single-use

## 7. Completion-path API behavior should be made more consistent

`worker.py` uses different strategies for patching and deleting the original response. That may work, but it makes operational behavior harder to reason about.

### Recommended improvement

Document and standardize the completion API strategy clearly:

- webhook-token only
- bot-token only where allowed
- or a documented hybrid fallback

## 8. Queueing is simple and stable, but not yet burst-oriented

The worker loop is intentionally straightforward. That is good for reliability.

But publish-ready documentation should acknowledge current behavior under burst traffic and large concurrent click volumes.

---

## Recommended release position

Use wording closer to:

- stable enough for operator testing and controlled deployments
- designed to reduce immediate interaction expiry and routing instability
- not a guarantee of business-action completion by itself

Avoid over-claiming:

- perfect delivery
- guaranteed post-restart event recovery
- deterministic session targeting in all channel-sharing scenarios

---

## High-priority patch plan

### P0

- clarify transport-vs-action success in worker status text and docs
- document reconnect limitations honestly
- document channel routing vs session affinity limitations
- document current completion behavior (`@original` patch vs channel fallback)

### P1

- add payload-level response policy
- persist and consume session / agent hints end-to-end
- clarify and refine modal trigger vs modal submit single-use rules
- improve operator observability in `manage.sh doctor` and status views

### P2

- explore stronger structured reinjection into OpenClaw
- add sequence-aware gateway resume if worth the complexity
- add queue lag / delivery metrics for burst diagnostics

---

## Bottom line

The package is well-aimed and structurally sound. The biggest remaining work is not the Discord UI side; it is tightening the semantic boundary between:

- Discord interaction acceptance
- OpenClaw reinjection
- actual business-action completion

Once that boundary is made more explicit in code and docs, this becomes a much stronger public release.
