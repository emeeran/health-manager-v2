#!/usr/bin/env bash
# Build the desktop .deb (Tauri shell + PyInstaller onedir sidecar).
# Refuses a dirty git tree so a .deb traces to a commit.
#
# Signing: if TAURI_SIGNING_PRIVATE_KEY is set, the .deb.sig updater artifact
# is produced; without it the build still succeeds with no signature (the
# updater itself is runtime-configured via FHM_UPDATE_MANIFEST_URL /
# FHM_UPDATE_PUBKEY and stays off unless configured).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [ -n "$(git status --porcelain 2>/dev/null | head -1)" ] && [ "${HM_ALLOW_DIRTY:-}" != "1" ]; then
  echo "ERROR: dirty git tree — commit first or set HM_ALLOW_DIRTY=1" >&2
  exit 1
fi

VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' \
    backend/pyproject.toml | head -n1)"
[ -n "$VERSION" ] || { echo "ERROR: no version in backend/pyproject.toml" >&2; exit 1; }

echo "── frontend build ──"
( cd frontend && npm ci --silent && npm run build )

echo "── pyinstaller onedir ──"
( cd backend && uv run pyinstaller health-manager-backend.spec --noconfirm --clean )

echo "── stage sidecar ──"
rm -rf desktop/binaries/health-manager-backend
mkdir -p desktop/binaries
cp -r backend/dist/health-manager-backend desktop/binaries/

echo "── sync version ($VERSION) ──"
packaging/sync-version.sh

echo "── cargo tauri build ──"
# Updater artifacts (.deb.sig) need the minisign signing key; without one a
# plain build must still succeed — the updater itself is runtime-configured and
# stays off. The empty plugins.updater block in tauri.conf.json exists because
# tauri-cli refuses updater-artifact bundling without one.
UPDATER_CONF=()
if [ -n "${TAURI_SIGNING_PRIVATE_KEY:-}" ]; then
  UPDATER_CONF=(--config '{"bundle":{"createUpdaterArtifacts":true}}')
  echo "      TAURI_SIGNING_PRIVATE_KEY set — emitting .deb.sig updater artifact."
fi
( cd desktop && cargo tauri build "${UPDATER_CONF[@]}" )

# Pick the newest bundle (older versions linger in the same directory).
DEB="$(find desktop/target -path '*bundle/deb/*.deb' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true)"
if [ -z "$DEB" ]; then
  echo "ERROR: no .deb found under desktop/target/**/bundle/deb/" >&2
  exit 1
fi
echo "Built: $DEB"
