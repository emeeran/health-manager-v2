"""Application settings.

Development derives ENCRYPTION_KEY from SECRET_KEY so a fresh clone works
with a single generated secret. Production hard-requires an explicit
ENCRYPTION_KEY so JWT-key rotation can never render encrypted data
unrecoverable.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"  # development | desktop | production
    SECRET_KEY: str = ""
    DEBUG: bool = True
    ENCRYPTION_KEY: str = ""

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/health.db"
    CORS_ORIGINS: str = "http://localhost:3000"
    # None = per-env default: open in development, closed in production
    # (production users join via household invitations instead).
    ALLOW_REGISTRATION: bool | None = None

    STORAGE_PATH: str = "./data/attachments"
    MAX_FILE_SIZE_MB: int = 25

    # ── AI providers ─────────────────────────────────────
    # Local Ollama (no key needed; model must exist on the host).
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:4b"
    OLLAMA_TIMEOUT: int = 300
    # OpenAI-compatible cloud slots (key empty = provider disabled).
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # Additional OpenAI-compatible cloud slots (same convention: key empty
    # = provider disabled). All speak the /chat/completions dialect via
    # OpenAICompatibleProvider.
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    COHERE_API_KEY: str = ""
    COHERE_BASE_URL: str = "https://api.cohere.ai/compatibility/v1"
    COHERE_MODEL: str = "command-r7b-12-2024"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    MISTRAL_API_KEY: str = ""
    MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    MISTRAL_MODEL: str = "mistral-small-latest"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openrouter/auto"
    HUGGINGFACE_API_KEY: str = ""
    HUGGINGFACE_BASE_URL: str = "https://router.huggingface.co/v1"
    HUGGINGFACE_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    # Cloud attempts abandoned after this many seconds (dead key → next
    # provider); Ollama gets the larger OLLAMA_TIMEOUT.
    EXTRACTION_PROVIDER_TIMEOUT: int = 15
    EXTRACTION_PAGES_PER_CHUNK: int = 5
    EXTRACTION_MAX_TOKENS: int = 4096
    # Second-model verification of extractions + the claim audit agent.
    AI_VERIFICATION_ENABLED: bool = True
    # Audit agent: max claims examined per narrative.
    AUDIT_MAX_CLAIMS: int = 15

    # ── External fact-checking (SearXNG; opt-in per member) ──
    # Disabled unless an instance URL is configured AND the member has
    # web_factcheck_consent — queries are redacted in code before egress.
    WEB_FACTCHECK_ENABLED: bool = False
    SEARXNG_URL: str = ""
    SEARXNG_TIMEOUT: int = 10
    WEB_FACTCHECK_MAX_CLAIMS: int = 5
    WEB_FACTCHECK_MAX_RESULTS: int = 5

    # ── Scheduler ────────────────────────────────────────
    RUN_SCHEDULER: bool = True
    REMINDER_POLL_SECONDS: int = 60

    # ── Web push (VAPID-gated; disabled without keys) ────
    WEB_PUSH_ENABLED: bool = False
    WEB_PUSH_VAPID_PRIVATE_KEY: str = ""
    WEB_PUSH_VAPID_PUBLIC_KEY: str = ""
    WEB_PUSH_VAPID_SUBJECT: str = "mailto:ops@localhost"

    # ── RAG grounding (local FTS5 index; inert until seeded) ──
    RAG_ENABLED: bool = True
    RAG_INDEX_PATH: str = "./data/rag-index.sqlite"
    RAG_TOP_K: int = 4
    RAG_MAX_CHARS: int = 4000

    # ── Frozen desktop build ─────────────────────────────
    # SERVE_FRONTEND=true makes the backend serve the SPA same-origin
    # (desktop sidecar) so httpOnly cookies stay first-party.
    SERVE_FRONTEND: bool = False
    FRONTEND_DIST: str = "frontend"

    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 7

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def registration_open(self) -> bool:
        if self.ALLOW_REGISTRATION is not None:
            return self.ALLOW_REGISTRATION
        return not self.is_production

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        if self.is_production:
            if not self.SECRET_KEY or not self.ENCRYPTION_KEY:
                raise RuntimeError("Production requires SECRET_KEY and ENCRYPTION_KEY to be set.")
            self.DEBUG = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


def env_int(name: str, default: int) -> int:
    """Read an optional integer env var, falling back on unset/garbage."""
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default
