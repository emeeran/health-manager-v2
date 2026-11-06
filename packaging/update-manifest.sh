#!/usr/bin/env bash
# Generate a Tauri updater `latest.json` manifest from a built .deb.
#
# Usage:
#   ./update-manifest.sh \
#     --deb dist/health-manager-v2_0.1.0_amd64.deb \
#     --sig dist/health-manager-v2_0.1.0_amd64.deb.sig \
#     --url-base https://updates.example.com/health-manager-v2 \
#     --out /var/www/updates/latest.json
#
# The URL base must serve BOTH the .deb itself and the generated manifest.
# Clients are configured with:
#   FHM_UPDATE_MANIFEST_URL=https://updates.example.com/health-manager-v2/latest.json
#   FHM_UPDATE_PUBKEY=<minisign public key>
#
# Prerequisites:
#   * The .deb was built with TAURI_SIGNING_PRIVATE_KEY set
#     (build-desktop-deb.sh then flips bundle.createUpdaterArtifacts on),
#     which produces the .sig file.
#   * The keypair was created once with:
#     cargo tauri signer generate -w ~/.tauri/hm2-update.key
#     NEVER put the private key in the repo or on the update server.
set -euo pipefail

while [[ $# -ge 1 ]]; do
  case "$1" in
    --deb) DEB="$2"; shift 2 ;;
    --sig) SIG="$2"; shift 2 ;;
    --url-base) URL_BASE="${2%/}"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

: "${DEB:?--deb required}" "${SIG:?--sig required}"
: "${URL_BASE:?--url-base required}" "${OUT:?--out required}"

DEB_NAME="$(basename "$DEB")"
VERSION="$(echo "$DEB_NAME" | grep -oP '(?<=_)[0-9]+\.[0-9]+\.[0-9]+(?=_)')" # pkg_1.2.3_arch.deb
PUB_DATE="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
SIG_CONTENT="$(cat "$SIG")"

read -r -d '' MANIFEST <<EOF || true
{
  "version": "$VERSION",
  "pub_date": "$PUB_DATE",
  "platforms": {
    "linux-x86_64": {
      "signature": "$SIG_CONTENT",
      "url": "$URL_BASE/$DEB_NAME"
    }
  }
}
EOF

mkdir -p "$(dirname "$OUT")"
printf '%s\n' "$MANIFEST" > "$OUT"
echo "Manifest written: $OUT (version $VERSION)"
echo "Copy the .deb alongside it:"
echo "  cp \"$DEB\" \"$(dirname "$OUT")/$DEB_NAME\""
