#!/usr/bin/env bash
# sync-version.sh — propagate the version from the source of truth
# (backend/pyproject.toml [project] version) to every consumer:
#
#   frontend/package.json     "version"          (+ npm lockfile refresh)
#   desktop/Cargo.toml        [package] version  (desktop shell crate)
#   desktop/tauri.conf.json   "version"          (Tauri bundle / updater version)
#
# Usage: packaging/sync-version.sh [--dry-run]
#   --dry-run  print what would change without writing anything
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' \
    "$ROOT/backend/pyproject.toml" | head -n1)"
if [ -z "$VERSION" ]; then
    echo "ERROR: could not read version from backend/pyproject.toml" >&2
    exit 1
fi
echo "Source of truth: backend/pyproject.toml -> $VERSION"

changed=0
sync_file() { # sync_file <path> <sed-expr>
    local file="$1" expr="$2"
    if [ ! -f "$file" ]; then
        echo "ERROR: missing $file" >&2
        exit 1
    fi
    if [ "$DRY" = 1 ]; then
        if sed "$expr" "$file" | cmp -s - "$file"; then
            echo "  ok (already $VERSION): ${file#$ROOT/}"
        else
            echo "  would update: ${file#$ROOT/}"
            changed=1
        fi
    else
        sed -i "$expr" "$file"
        echo "  updated: ${file#$ROOT/}"
    fi
}

echo "── frontend/package.json ──"
sync_file "$ROOT/frontend/package.json" \
    "s/\"version\": \".*\"/\"version\": \"$VERSION\"/"

echo "── desktop/Cargo.toml ──"
sync_file "$ROOT/desktop/Cargo.toml" \
    "0,/^version = \".*\"/s//version = \"$VERSION\"/"

echo "── desktop/tauri.conf.json ──"
if [ "$DRY" = 1 ]; then
    CURRENT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
        "$ROOT/desktop/tauri.conf.json")"
    if [ "$CURRENT" = "$VERSION" ]; then
        echo "  ok (already $VERSION): desktop/tauri.conf.json"
    else
        echo "  would update: desktop/tauri.conf.json ($CURRENT -> $VERSION)"
        changed=1
    fi
else
    python3 - "$VERSION" "$ROOT/desktop/tauri.conf.json" <<'PY'
import json, pathlib, sys
version, path = sys.argv[1], pathlib.Path(sys.argv[2])
conf = json.loads(path.read_text())
conf["version"] = version
path.write_text(json.dumps(conf, indent=2) + "\n")
print(f"  updated: desktop/tauri.conf.json")
PY
fi

if [ "$DRY" = 0 ]; then
    # Keep package-lock.json in sync with the new package.json version.
    # Patched in place (never via npm — `--package-lock-only` resolves every
    # platform variant incl. tailwindcss-oxide-wasm32-wasi, which npm
    # refuses to fetch and would fail the whole build).
    python3 - "$VERSION" <<'PYEOF'
import json, sys
version = sys.argv[1]
path = "frontend/package-lock.json"
with open(path) as f:
    lock = json.load(f)
lock["version"] = version
lock["packages"][""]["version"] = version
with open(path, "w") as f:
    json.dump(lock, f, indent=2)
    f.write("\n")
PYEOF
    # backend/uv.lock carries the project's own version; any `uv` run after
    # a pyproject bump rewrites it — patch it here so trees stay clean for
    # the .deb builds (they refuse dirty trees).
    sed -i 's/^version = ".*"  # health-manager-v2$/version = "'"$VERSION"'"  # health-manager-v2/' \
        backend/uv.lock 2>/dev/null || true
    python3 - "$VERSION" <<'PYEOF'
import re, sys
version = sys.argv[1]
path = "backend/uv.lock"
with open(path) as f:
    text = f.read()
# The project's own entry: the version line right after name = "health-manager-v2".
text = re.sub(
    r'(name = "health-manager-v2"\nversion = ")[^"]+(")',
    r"\g<1>" + version + r"\g<2>",
    text,
    count=1,
)
with open(path, "w") as f:
    f.write(text)
PYEOF
    # desktop/Cargo.lock carries the desktop shell crate's own version; a
    # stale one makes `cargo tauri build` rewrite it mid-build and leave the
    # tree dirty for the NEXT deb build's dirty-tree check.
    python3 - "$VERSION" <<'PYEOF'
import re, sys
version = sys.argv[1]
path = "desktop/Cargo.lock"
with open(path) as f:
    text = f.read()
text = re.sub(
    r'(name = "health-manager-desktop"\nversion = ")[^"]+(")',
    r"\g<1>" + version + r"\g<2>",
    text,
    count=1,
)
with open(path, "w") as f:
    f.write(text)
PYEOF
    echo "✔ Version synced to $VERSION"
else
    if [ "$changed" = 0 ]; then
        echo "✔ Dry run: everything already at $VERSION"
    else
        echo "• Dry run: changes pending (re-run without --dry-run to apply)"
    fi
fi
