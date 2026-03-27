# Publish checklist

## Packaging

- [ ] README is up to date
- [ ] SKILL.md is concise and operational
- [ ] examples contain no private IDs or tokens
- [ ] `.venv`, runtime DB files, inbox logs, token locks, and caches are excluded
- [ ] install, uninstall, and service naming reflect workspace-scoped behavior
- [ ] published artifact includes runtime service templates (`scripts/systemd/*.service.template`)

## Validation

- [ ] `./validate.sh`
- [ ] `python3 -m py_compile scripts/*.py lib/*.py tools/*.py`
- [ ] examples parse correctly as JSON

## Runtime checks

- [ ] button interaction works
- [ ] select interaction works and records normalized values
- [ ] modal opens successfully
- [ ] modal submit reaches the bridge and records normalized fields
- [ ] local deterministic actions behave as expected
- [ ] `manage.sh doctor` reports correct workspace/runtime paths
- [ ] token lock behavior is understood and documented

## Documentation honesty

- [ ] modal submit strategy is documented as stability-first
- [ ] same-host duplicate broker protection is documented
- [ ] cross-host duplicate token coordination is documented as unsupported
- [ ] transport success vs downstream action success is documented clearly
