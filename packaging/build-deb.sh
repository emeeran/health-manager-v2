#!/usr/bin/env bash
# Build the server .deb: health-manager_<version>_all.deb
#
# Layout produced:
#   /opt/health-manager/{backend/app, alembic, prompts, frontend, caddy, backend/.venv}
#   /etc/health-manager/{Caddyfile, config.env}   (conffiles)
#   /etc/systemd/system/health-manager{,-caddy}.service
# Refuses a dirty git tree so a .deb traces to a commit.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [ -n "$(git status --porcelain 2>/dev/null | head -1)" ] && [ "${HM_ALLOW_DIRTY:-}" != "1" ]; then
  echo "ERROR: dirty git tree — commit first or set HM_ALLOW_DIRTY=1" >&2
  exit 1
fi

VERSION="$(grep -m1 '^version' backend/pyproject.toml | sed 's/version = "\(.*\)"/\1/')"
STAGING="$(mktemp -d)/health-manager_${VERSION}_all"
mkdir -p "$STAGING/DEBIAN"
trap 'rm -rf "$(dirname "$STAGING")"' EXIT

echo "── building frontend ──"
( cd frontend && npm ci --silent && npm run build )

echo "── staging tree ──"
install -d "$STAGING/opt/health-manager/backend" \
           "$STAGING/opt/health-manager/frontend" \
           "$STAGING/opt/health-manager/prompts" \
           "$STAGING/etc/health-manager" \
           "$STAGING/etc/systemd/system" \
           "$STAGING/opt/health-manager/bin"

cp -r backend/app "$STAGING/opt/health-manager/backend/app"
cp -r backend/alembic "$STAGING/opt/health-manager/backend/alembic"
cp backend/alembic.ini backend/pyproject.toml "$STAGING/opt/health-manager/backend/"
cp -r prompts "$STAGING/opt/health-manager/prompts"
rm -rf "$STAGING/opt/health-manager/prompts/p[0-9]"*  # SDD prompts are not runtime
cp -r frontend/dist "$STAGING/opt/health-manager/frontend/dist"

echo "── building venv (uv → pip, paths rewritten) ──"
VENV="$STAGING/opt/health-manager/backend/.venv"
( cd backend && uv export --no-dev --format requirements-txt --no-hashes > /tmp/hmv2-reqs.txt )
uv venv --python python3 "$VENV" --quiet
uv pip install --python "$VENV/bin/python" -r /tmp/hmv2-reqs.txt --quiet
# Rewrite absolute venv paths so the venv works at /opt.
sed -i "s|$(dirname "$VENV")|/opt/health-manager/backend/.venv|g" "$VENV/pyvenv.cfg"
for bin in "$VENV"/bin/*; do
  if [ -f "$bin" ] && head -1 "$bin" | grep -q "^#!.*python"; then
    sed -i "1s|^#!.*|#!/opt/health-manager/backend/.venv/bin/python3|" "$bin"
  fi
done
find "$STAGING" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "── caddy ──"
CADDY_VERSION=2.9.1
CADDY_TMP="$(mktemp -d)"
curl -sSL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" \
  | tar -xz -C "$CADDY_TMP" caddy
install -m 755 "$CADDY_TMP/caddy" "$STAGING/opt/health-manager/bin/caddy"
rm -rf "$CADDY_TMP"

install -m 644 packaging/Caddyfile "$STAGING/etc/health-manager/Caddyfile"
install -m 600 packaging/config.env "$STAGING/etc/health-manager/config.env"
install -m 644 packaging/systemd/health-manager.service \
               packaging/systemd/health-manager-caddy.service \
               "$STAGING/etc/systemd/system/"

echo "── DEBIAN control ──"
INSTALLED_SIZE="$(du -sk "$STAGING/opt" | cut -f1)"
cat > "$STAGING/DEBIAN/control" <<EOF
Package: health-manager
Version: ${VERSION}
Section: web
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-venv
Installed-Size: ${INSTALLED_SIZE}
Maintainer: Family Health Manager v2 <ops@localhost>
Description: Self-hosted family health record manager (server)
 Privacy-first family health records with AI-powered document
 extraction. Installs systemd services (backend + Caddy) serving
 http://localhost:8080.
EOF

cat > "$STAGING/DEBIAN/conffiles" <<EOF
/etc/health-manager/Caddyfile
/etc/health-manager/config.env
EOF

cat > "$STAGING/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
CONFIG=/etc/health-manager/config.env

ensure_secret() {
  local key="$1" gen="$2"
  if grep -qE "^${key}=$" "$CONFIG" 2>/dev/null || ! grep -qE "^${key}=" "$CONFIG" 2>/dev/null; then
    if grep -qE "^${key}=" "$CONFIG"; then
      sed -i "s|^${key}=.*|${key}=$($gen)|" "$CONFIG"
    else
      echo "${key}=$($gen)" >> "$CONFIG"
    fi
  fi
}

ensure_secret SECRET_KEY "python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
ensure_secret ENCRYPTION_KEY "python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
ensure_secret HEALTH_CHECK_SECRET "python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
chmod 600 "$CONFIG"

if ! id health-manager >/dev/null 2>&1; then
  useradd --system --home /opt/health-manager --shell /usr/sbin/nologin health-manager
fi
install -d -o health-manager -g health-manager -m 755 /var/lib/health-manager/data
install -d -o health-manager -g health-manager -m 700 /var/lib/health-manager/data/backups
install -d -o health-manager -g health-manager -m 755 /var/log/health-manager
# CWD-relative backend paths must land in persistent storage.
[ -e /opt/health-manager/backend/data ] || ln -s /var/lib/health-manager/data /opt/health-manager/backend/data
chown -R health-manager:health-manager /opt/health-manager

systemctl daemon-reload || true
systemctl enable --now health-manager.service || true
systemctl enable --now health-manager-caddy.service || true
echo "health-manager: serving http://localhost:8080"
EOF
chmod 755 "$STAGING/DEBIAN/postinst"

cat > "$STAGING/DEBIAN/prerm" <<'EOF'
#!/bin/bash
systemctl stop health-manager-caddy.service || true
systemctl stop health-manager.service || true
EOF
chmod 755 "$STAGING/DEBIAN/prerm"

cat > "$STAGING/DEBIAN/postrm" <<'EOF'
#!/bin/bash
if [ "$1" = "purge" ]; then
  systemctl disable health-manager health-manager-caddy 2>/dev/null || true
  rm -f /etc/systemd/system/health-manager.service /etc/systemd/system/health-manager-caddy.service
  rm -rf /var/lib/health-manager /var/log/health-manager /opt/health-manager /etc/health-manager
  userdel health-manager 2>/dev/null || true
fi
EOF
chmod 755 "$STAGING/DEBIAN/postrm"

echo "── dpkg-deb ──"
mkdir -p dist
dpkg-deb --build --root-owner-group "$STAGING" "$(pwd)/dist/health-manager_${VERSION}_all.deb"
echo "Built: dist/health-manager_${VERSION}_all.deb"
