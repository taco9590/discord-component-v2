#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="discord-component-v2"
SERVICE_BROKER="${PACKAGE_NAME}-broker.service"
SERVICE_WORKER="${PACKAGE_NAME}-worker.service"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
INSTALL_DIR="${INSTALL_DIR:-$OPENCLAW_HOME/workspace/skills/$PACKAGE_NAME}"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PURGE=0

if [[ "${1:-}" == "--purge" ]]; then
  PURGE=1
fi

if command -v systemctl >/dev/null 2>&1; then
  echo "Stopping and disabling user services..."
  systemctl --user disable --now "$SERVICE_BROKER" >/dev/null 2>&1 || true
  systemctl --user disable --now "$SERVICE_WORKER" >/dev/null 2>&1 || true

  echo "Removing user service files..."
  rm -f "$SYSTEMD_USER_DIR/$SERVICE_BROKER"
  rm -f "$SYSTEMD_USER_DIR/$SERVICE_WORKER"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
else
  echo "systemctl not found; skipping service cleanup."
fi

if [[ "$PURGE" -eq 1 ]]; then
  echo "Purging install directory: $INSTALL_DIR"
  rm -rf "$INSTALL_DIR"
else
  echo "Keeping installed files at: $INSTALL_DIR"
  echo "Run './uninstall.sh --purge' to remove the package directory, venv, and SQLite state."
fi

echo "Uninstall complete."
