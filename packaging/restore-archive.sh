#!/usr/bin/env bash
# Privileged disaster-restore: triggered by health-manager-restore.path
# when the app writes an archive name to data/.restore-request.
# Env-overridable so tests can exercise the whole flow unprivileged.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/var/lib/health-manager/data}"
APP_SVC="${APP_SVC:-health-manager.service}"
CADDY_SVC="${CADDY_SVC:-}"
APP_USER="${APP_USER:-health-manager}"

REQUEST="$DATA_DIR/.restore-request"
RESULT="$DATA_DIR/.restore-result"

fail() {
  echo "{\"status\": \"failed\", \"error\": \"$1\"}" > "$RESULT"
  echo "restore failed: $1" >&2
  exit 1
}

[ -f "$REQUEST" ] || fail "no request file"

ARCHIVE="$(cat "$REQUEST")"

# Strict name validation — no traversal, upstream format only.
echo "$ARCHIVE" | grep -qE '^backup_[0-9]{8}_[0-9]{6}\.tar\.gz(\.enc)?$' \
  || fail "invalid archive name"

ARCHIVE_PATH="$DATA_DIR/backups/$ARCHIVE"
[ -f "$ARCHIVE_PATH" ] || fail "archive not found"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# .enc archives: decrypt with the app's ENCRYPTION_KEY from config.env.
TARBALL="$ARCHIVE_PATH"
CONFIG_ENV="${CONFIG_ENV:-/etc/health-manager/config.env}"
if [[ "$ARCHIVE" == *.enc ]]; then
  [ -f "$CONFIG_ENV" ] || fail "config.env missing for encrypted archive"
  # shellcheck disable=SC1090
  . "$CONFIG_ENV"
  [ -n "${ENCRYPTION_KEY:-}" ] || fail "ENCRYPTION_KEY not set"
  export ENCRYPTION_KEY
  python3 - "$ARCHIVE_PATH" "$WORK/restore.tar.gz" <<'PYEOF' || fail "decrypt failed (key mismatch?)"
import os
import sys
from cryptography.fernet import Fernet
src, dst = sys.argv[1], sys.argv[2]
key = os.environ["ENCRYPTION_KEY"]
data = open(src, "rb").read()
open(dst, "wb").write(Fernet(key.encode()).decrypt(data))
PYEOF
  TARBALL="$WORK/restore.tar.gz"
fi

# The tar must contain health.db — validate BEFORE touching live data.
tar -tzf "$TARBALL" > "$WORK/members.txt" || fail "unreadable tarball"
grep -q "^health.db$" "$WORK/members.txt" || fail "no health.db in archive"

# Stage everything, then integrity-check the staged DB BEFORE touching
# live data (extraction into $WORK is harmless).
tar -xzf "$TARBALL" -C "$WORK"
python3 - "$WORK/health.db" <<'PYEOF' || fail "staged DB failed integrity check"
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
result = conn.execute("PRAGMA integrity_check").fetchone()[0]
sys.exit(0 if result == "ok" else 1)
PYEOF

systemctl --no-ask-password stop "$APP_SVC" || true
[ -n "$CADDY_SVC" ] && systemctl --no-ask-password stop "$CADDY_SVC" || true

# Safety net: keep the pre-restore state.
cp "$DATA_DIR/health.db" "$DATA_DIR/backups/backup_prerestore_$(date +%Y%m%d_%H%M%S).db" \
  2>/dev/null || true

# Swap DB (drop WAL/SHM sidecars) and attachments.
cp "$WORK/health.db" "$DATA_DIR/health.db"
rm -f "$DATA_DIR/health.db-wal" "$DATA_DIR/health.db-shm"
if [ -d "$WORK/attachments" ]; then
  rm -rf "$DATA_DIR/attachments"
  cp -r "$WORK/attachments" "$DATA_DIR/attachments"
fi
chown -R "$APP_USER:$APP_USER" "$DATA_DIR" 2>/dev/null || true

systemctl --no-ask-password start "$APP_SVC" || true
[ -n "$CADDY_SVC" ] && systemctl --no-ask-password start "$CADDY_SVC" || true

echo '{"status": "ok"}' > "$RESULT"
rm -f "$REQUEST"
echo "restore complete"
