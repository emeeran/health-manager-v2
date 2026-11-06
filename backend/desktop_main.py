"""PyInstaller sidecar entry for the Tauri desktop shell.

Runs frozen from <resource>/backend/health-manager-backend with CWD set by
the shell to the per-user data dir, so CWD-relative paths (./data/…,
config.env) land there. Generates missing secrets idempotently into
config.env BEFORE importing app.main (whose Settings requires SECRET_KEY).

APP_ENV=desktop deliberately (not production): the httpOnly auth cookie
`secure` flag must stay off for cookies over plain http://127.0.0.1.
"""

import base64
import faulthandler
import os
import secrets
import sys
from pathlib import Path

faulthandler.enable()


def _parse_port() -> int:
    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            return int(arg.split("=", 1)[1])
    return int(os.environ.get("HM_PORT", "8000"))


def _ensure_secrets(config_path: Path) -> None:
    """Idempotently fill missing secrets; same generators as the server
    .deb postinst so keys are interchangeable."""
    values: dict[str, str] = {}
    if config_path.exists():
        for line in config_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()

    changed = False
    if not values.get("SECRET_KEY"):
        values["SECRET_KEY"] = secrets.token_urlsafe(48)
        changed = True
    if not values.get("ENCRYPTION_KEY"):
        values["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        changed = True
    if not values.get("HEALTH_CHECK_SECRET"):
        values["HEALTH_CHECK_SECRET"] = secrets.token_urlsafe(32)
        changed = True

    if changed:
        lines = [
            "# Generated — do not commit.",
            f"SECRET_KEY={values['SECRET_KEY']}",
            f"ENCRYPTION_KEY={values['ENCRYPTION_KEY']}",
            f"HEALTH_CHECK_SECRET={values['HEALTH_CHECK_SECRET']}",
        ]
        config_path.write_text("\n".join(lines) + "\n")
        try:
            config_path.chmod(0o600)
        except OSError:
            pass

    for key, value in values.items():
        os.environ.setdefault(key, value)


def main() -> None:
    port = _parse_port()
    os.environ["APP_ENV"] = "desktop"
    os.environ.setdefault("SERVE_FRONTEND", "true")
    # Frozen layout: data dir is CWD; frontend SPA + prompts + alembic are
    # bundle data next to the executable (onedir → sys._MEIPASS).
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        os.environ.setdefault("FRONTEND_DIST", str(Path(meipass) / "frontend"))
    Path("data").mkdir(exist_ok=True)

    _ensure_secrets(Path("config.env"))

    import uvicorn  # noqa: PLC0415 — after env is finalised

    from app.main import app  # noqa: PLC0415

    # asyncio+h11: avoid uvloop/httptools native deps in the frozen binary.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        workers=1,
        loop="asyncio",
        http="h11",
        access_log=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
