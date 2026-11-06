# Packaging

| Script | Produces |
|---|---|
| `build-deb.sh` | Server `.deb`: app under `/opt/health-manager`, systemd units, Caddy config |
| `build-desktop-deb.sh` | Desktop `.deb`: Tauri shell + PyInstaller onedir sidecar |
| `update-manifest.sh` | Updater feed `latest.json` from a signed desktop `.deb` + `.deb.sig` |
| `sync-version.sh` | Propagate `backend/pyproject.toml` version to frontend + desktop |
| `restore-archive.sh` | Restore a backup archive produced by the app's nightly backup |
| `config.env` | Conffile template installed to `/etc/health-manager` |
| `systemd/`, `Caddyfile` | Service units + reverse-proxy config |

Both `.deb` builds refuse a dirty git tree (`HM_ALLOW_DIRTY=1` overrides).
Server quick start after install:

```bash
sudo apt install ./health-manager_<version>_all.deb
curl -fsS http://127.0.0.1:8000/health/ready
```

Release flow: see `docs/RELEASE.md`. Updater env contract:
`TAURI_SIGNING_PRIVATE_KEY` (build-time signing), `FHM_UPDATE_MANIFEST_URL`
+ `FHM_UPDATE_PUBKEY` (runtime, inert when unset).
