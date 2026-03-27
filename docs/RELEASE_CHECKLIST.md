# Release checklist

## Before packaging

- [ ] `README.md` reflects the current install flow
- [ ] `SKILL.md` stays short and operational
- [ ] `docs/DEPLOYMENT.md` matches the real scripts
- [ ] `docs/TROUBLESHOOTING.md` reflects real runtime behavior
- [ ] `docs/OPERATIONAL_NOTES.md` matches the real architecture and failure modes
- [ ] `docs/PUBLISH_READY_AUDIT.md` is reviewed and any intentionally deferred issues are noted
- [ ] examples contain only safe sample data
- [ ] no real Discord tokens or channel IDs are present
- [ ] no host-specific absolute paths remain

## Files to exclude

- [ ] `.venv/`
- [ ] `state/bridge.db`
- [ ] `state/openclaw_inbox.jsonl`
- [ ] `__pycache__/`
- [ ] `.install-manifest`
- [ ] backup directories such as `*.bak-*`

## Validation

- [ ] `bash -n install.sh manage.sh uninstall.sh validate.sh`
- [ ] `./validate.sh`
- [ ] `python -m py_compile` passes for package scripts
- [ ] install dry-run succeeds with `--skip-services`
- [ ] sample JSON files parse correctly

## Runtime checks

- [ ] broker service name is `discord-component-v2-broker.service`
- [ ] worker service name is `discord-component-v2-worker.service`
- [ ] broker reconnects after a forced restart
- [ ] `./manage.sh smoke-test` succeeds
- [ ] a demo action message can be sent manually
- [ ] button click ACKs without immediate expiry
- [ ] select interactions normalize values as expected
- [ ] modal submit interactions are accepted and reinjected correctly
- [ ] deferred response fallback behavior is verified for expired / failed completion paths
- [ ] `docs/TEST_PLAN.md` has been exercised against the current build

## Semantics review

- [ ] docs clearly distinguish transport success from business-action success
- [ ] docs clearly describe current reinjection behavior as prompt-based, not native structured runtime delivery
- [ ] docs describe channel pinning and current session-affinity limitations honestly
- [ ] modal trigger vs modal submit single-use behavior is documented
- [ ] completion behavior (`patch @original`, delete placeholder, or channel fallback) is documented accurately

## Public release review

- [ ] package name is consistent across docs and scripts
- [ ] install / update / uninstall paths are consistent
- [ ] limitations are documented honestly
- [ ] supported features are listed clearly
- [ ] release claims do not overstate delivery, completion, or reconnect guarantees
