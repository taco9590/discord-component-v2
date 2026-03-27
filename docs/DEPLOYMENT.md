# Deployment

## Install from a zip archive

```bash
unzip discord-component-v2.zip
cd discord-component-v2
chmod +x install.sh manage.sh uninstall.sh validate.sh
./install.sh
```

If Python virtual environment support is missing on Debian/Ubuntu:

```bash
./install.sh --install-system-deps
```

## Verify

```bash
./manage.sh doctor
./manage.sh status
./manage.sh logs
./validate.sh
```

## Smoke test

```bash
./manage.sh smoke-test
```

## Upgrade after fixing a failed install

If the package was already copied into the OpenClaw workspace during a previous failed install:

```bash
cd ~/.openclaw/workspace/skills/discord-component-v2
./install.sh
```

## No-services install

```bash
./install.sh --skip-services
```

## Purge uninstall

```bash
./uninstall.sh --purge
```

## Interaction status modes

```bash
export DISCORD_COMPONENT_V2_INTERACTION_STATUS=full        # default
export DISCORD_COMPONENT_V2_INTERACTION_STATUS=errors-only # suppress success status
export DISCORD_COMPONENT_V2_INTERACTION_STATUS=silent      # remove deferred placeholder and stay silent
```
