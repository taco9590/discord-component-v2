# Release notes

`discord-component-v2` has been hardened from an early prototype into a more realistic release candidate for OpenClaw-based Discord interaction bridging.

## Highlights

- stronger separation between Discord UI rendering, broker ingress, worker handling, and OpenClaw reinjection
- improved interaction status semantics to distinguish transport success from business-action success
- payload-level response policy support for more controlled follow-up behavior
- support for routing hints such as `agent_hint`, `session_hint`, and `thread_hint`
- improved local deterministic action handling for buttons, selects, and modal-driven demo flows
- stronger publish/readiness documentation, including a release checklist, troubleshooting guide, operational notes, and a full test plan

## Runtime hardening

- workspace-scoped namespacing for:
  - install directory
  - runtime state directory
  - service naming
- token-based local broker lock to reduce duplicate same-host consumers for the same Discord bot token
- expanded `manage.sh doctor` output for:
  - workspace identity
  - resolved runtime paths
  - token lock information
  - interaction counters
  - fallback and block statistics
  - recent interaction summaries
  - broker/worker process visibility

## Modal handling

- fixed modal open routing so modal trigger interactions can open modals correctly
- added modal submit ingestion and normalized field extraction
- shifted modal submit handling toward a stability-first strategy to reduce fragile interaction-native follow-up behavior

## Current release position

This package is best described as a **beta / release candidate**:

- suitable for real operator testing
- suitable for controlled deployments
- not yet claiming perfect downstream workflow guarantees or distributed coordination across multiple hosts
