"""Voice memos — local faster-whisper transcription.

``faster-whisper`` is an OPTIONAL dependency: the app never adds it to
``pyproject.toml``. When it is absent, ``whisper_available()`` says so and
the router answers 501 with an install hint — the feature is off, not
broken. The model is loaded lazily on first use and cached module-level by
size, so importing this module (or running the test suite) never pulls it.

Model size comes from the ``WHISPER_MODEL_SIZE`` env var directly rather
than Settings, keeping the optional feature out of core config.

Nothing is stored: transcription is a transform — audio bytes in, text
out. The transcript lands in the client's smart-entry box.

Cloud fallback deliberately does NOT exist: the configured providers are
text/vision LLMs without an audio endpoint, and routing voice PHI to an
unconfigured service would violate the consent model.
"""

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

#: Shown to clients on 501 so self-hosters know the one-liner fix.
INSTALL_HINT = "uv add 'faster-whisper'"

DEFAULT_MODEL_SIZE = "small"

_model_cache: dict[str, object] = {}


def model_size() -> str:
    """Configured Whisper model size (env var, default "small")."""
    return os.environ.get("WHISPER_MODEL_SIZE", DEFAULT_MODEL_SIZE)


def whisper_available() -> bool:
    """True when faster-whisper is importable in this environment."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _get_model():
    """Load (and cache) the configured Whisper model.

    Downloaded on first use — ``faster-whisper`` fetches weights into its
    local cache; nothing is sent anywhere. Never called at import time.
    """
    size = model_size()
    if size not in _model_cache:
        from faster_whisper import WhisperModel

        logger.info("Loading faster-whisper model %s (downloads on first use)", size)
        _model_cache[size] = WhisperModel(size, device="cpu", compute_type="int8")
    return _model_cache[size]


def transcribe(data: bytes, language: str | None = None) -> tuple[str, float]:
    """Transcribe audio bytes → ``(text, duration_seconds)``.

    Raises ``RuntimeError`` when faster-whisper is unavailable. ``language``
    is an ISO code hint ("en"/"hi"/…); None lets Whisper auto-detect.
    """
    if not whisper_available():
        raise RuntimeError(
            "faster-whisper is not installed — voice memos are disabled on this server"
        )
    model = _get_model()
    # faster-whisper wants a file path; write to a temp file and let the
    # OS reclaim it (the model decodes lazily inside transcribe()).
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        segments, info = model.transcribe(
            str(tmp_path),
            language=language or None,
            beam_size=1,
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
        return text, float(getattr(info, "duration", 0.0) or 0.0)
    finally:
        tmp_path.unlink(missing_ok=True)
