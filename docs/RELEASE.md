# Release Checklist

End-to-end release flow for Family Health Manager v2 (server .deb + desktop .deb,
with optional self-hosted desktop auto-update).

## 0. Preconditions

- Working tree is **clean** — both build scripts refuse a dirty tree
  (`HM_ALLOW_DIRTY=1` overrides, but a released .deb should always trace to a commit).
- Version is managed in **one place**: `backend/pyproject.toml` `[project] version`.
  Everything else is derived — never hand-edit the copies.

## 1. Bump version

```bash
# edit backend/pyproject.toml → [project] version = "x.y.z"
make sync-version
git diff --stat   # should touch: frontend/package.json(+lock), desktop/Cargo.toml, desktop/tauri.conf.json
```

`packaging/sync-version.sh` (called by `make sync-version`) propagates the version to:

| Target | Field |
|--------|-------|
| `frontend/package.json` | `"version"` (+ `npm install --package-lock-only` refresh) |
| `desktop/Cargo.toml` | `[package] version` |
| `desktop/tauri.conf.json` | `"version"` |

Dry-run first if unsure: `packaging/sync-version.sh --dry-run`.

Commit the bump: `chore(release): x.y.z`.

## 2. Build the server .deb

```bash
bash packaging/build-deb.sh
```

Output: a `health-manager(-server)_x.y.z_amd64.deb` under the packaging output
directory. Verify with `dpkg -I <deb>` (version matches).

## 3. Build the desktop .deb

```bash
bash packaging/build-desktop-deb.sh
```

Output: `desktop/target/release/bundle/deb/<name>_x.y.z_amd64.deb`
(the script picks the newest bundle).

### With updater artifacts (optional)

Desktop auto-update uses Tauri's signed-updater mechanism. To produce a
signable release you need a minisign keypair **once**:

```bash
cargo tauri signer generate -w ~/.tauri/hm2-update.key
```

Then build with the **private** key in the environment:

```bash
TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/hm2-update.key)" \
  bash packaging/build-desktop-deb.sh
```

- Key **set** → tauri-cli gets `--config '{"bundle":{"createUpdaterArtifacts":true}}`
  and emits a `.deb.sig` next to the `.deb`.
- Key **unset** → plain build, no `.sig`, clean exit. The updater capability in
  the shipped app is **off unless configured** (see §5); `tauri.conf.json`
  keeps `createUpdaterArtifacts: false` by default so unsigned local builds never
  abort after bundling.

Never commit or ship the private key; only the public key ever leaves your machine.

## 4. Verify the desktop .deb

```bash
sudo apt install ./<name>_x.y.z_amd64.deb     # resolves webkit/gtk runtime deps
```

Launch from the application menu (or `health-manager-v2`), confirm the backend
boots and the SPA loads. Uninstall with `sudo apt remove <package-name>`.

## 5. Publish (optional: update manifest)

Only needed if you host desktop auto-updates. Any static file server works.

```bash
packaging/update-manifest.sh \
  --deb  dist/<name>_x.y.z_amd64.deb \
  --sig  dist/<name>_x.y.z_amd64.deb.sig \
  --url-base https://updates.example.com/health-manager-v2 \
  --out  /var/www/updates/latest.json
cp dist/<name>_x.y.z_amd64.deb /var/www/updates/
```

Clients enable updates by launching the desktop app with:

```sh
FHM_UPDATE_MANIFEST_URL=https://updates.example.com/health-manager-v2/latest.json
FHM_UPDATE_PUBKEY=<minisign PUBLIC key>
```

| Env var | Set | Effect |
|---------|-----|--------|
| `FHM_UPDATE_MANIFEST_URL` + `FHM_UPDATE_PUBKEY` | both | Updater active: "check for updates" verifies the manifest signature and offers install + restart |
| either unset/empty | — | Inert: the app reports "not configured", nothing phones home |

`TAURI_SIGNING_PRIVATE_KEY` is a **build-time** variable only — it never reaches
the shipped app.

## 6. Publish + tag

- Copy artifacts to the release location (server deb, desktop deb, `.deb.sig`, `latest.json`).
- `git tag vX.Y.Z && git push origin vX.Y.Z`.

## Quick order recap

pyproject bump → `make sync-version` → commit → `build-deb.sh` →
`build-desktop-deb.sh` (± `TAURI_SIGNING_PRIVATE_KEY`) → verify install →
optional `update-manifest.sh` → publish → tag.
