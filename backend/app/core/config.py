"""Application settings.

Development derives ENCRYPTION_KEY from SECRET_KEY so a fresh clone works
with a single generated secret. Production hard-requires an explicit
ENCRYPTION_KEY so JWT-key rotation can never render encrypted data
unrecoverable.
"""

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
    # Per-request context window. The server default (4096) silently
    # truncates multi-page extraction chunks; 8192 holds a full chunk.
    # Keep KV-cache RAM in check with OLLAMA_FLASH_ATTENTION=1 and
    # OLLAMA_KV_CACHE_TYPE=q8_0 on the server (see docs).
    OLLAMA_NUM_CTX: int = 8192
    # OpenAI-compatible cloud slots (key empty = provider disabled).
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # Additional OpenAI-compatible cloud slots (same convention: key empty
    # = provider disabled). All speak the /chat/completions dialect via
    # OpenAICompatibleProvider.
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    ZAI_API_KEY: str = ""
    ZAI_BASE_URL: str = "https://api.z.ai/api/paas/v4"
    ZAI_MODEL: str = "glm-4.6"
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
    HUGGINGFACE_MODEL: str = "google/medgemma-27b-text-it"
    # Cloud attempts abandoned after this many seconds (dead key → next
    # provider); Ollama gets the larger OLLAMA_TIMEOUT.
    EXTRACTION_PROVIDER_TIMEOUT: int = 15
    # Pages per extraction chunk. For vision chunks this is ALSO the number of
    # images in one request — providers cap that per model (verified live:
    # Groq's qwen/qwen3.8-27b rejects a 5-image request with 400 "Too many
    # images provided. This model supports up to 3 images"), so 3 is the
    # highest safe default across current cloud vision models.
    EXTRACTION_PAGES_PER_CHUNK: int = 3
    EXTRACTION_MAX_TOKENS: int = 4096
    # Second-model verification of extractions + the claim audit agent.
    AI_VERIFICATION_ENABLED: bool = True
    # Second LLM pass that restructures each extraction into a consolidated
    # clinical report (markdown, stored in clinical_data.consolidated_report).
    AI_CONSOLIDATED_REPORT_ENABLED: bool = True
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
    BACKUP_ROTATE_HOUR: int = 6
    WEB_PUSH_DISPATCH_SECONDS: int = 300
    AI_PROVIDER_CHECK_MINUTES: int = 15
    ANOMALY_SCAN_HOURS: int = 6
    STAGING_CLEANUP_MINUTES: int = 60
    INTEGRITY_CHECK_HOURS: int = 24
    BACKUP_TICK_MINUTES: int = 60
    MEDICINE_CRAWL_BATCH_MINUTES: int = 30

    # ── Ops tuning ───────────────────────────────────────
    REFILL_ALERT_DAYS: int = 5
    ANOMALY_SCAN_DAYS: int = 7
    STAGING_MAX_AGE_HOURS: int = 24
    INTEGRITY_BATCH: int = 25
    BACKUP_RETENTION_DAYS: int = 30
    # Tiered payload cap: uploads (extract/attachments/backup) get v1's
    # 500MB, general API JSON 50MB.
    MAX_UPLOAD_SIZE_MB: int = 500
    MAX_REQUEST_SIZE_MB: int = 50
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_GENERAL: int = 100
    RATE_LIMIT_AUTH: int = 10

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

    # ── Jan Aushadhi catalog refresh (inert until a dataset URL is set) ──
    JAN_AUSHADHI_DATASET_URL: str = ""
    JAN_AUSHADHI_REFRESH_DAYS: int = 30

    # ── Medicine catalog crawler (1mg/Apollo; toggled at runtime in Settings,
    #    env value is only the default) ──
    MEDICINE_CRAWLER_ENABLED: bool = False
    MEDICINE_CRAWLER_DATA_DIR: str = "./data/medicine-crawler"
    MEDICINE_CRAWLER_BATCH_PAGES: int = 400
    MEDICINE_CRAWLER_TIMEOUT_SECONDS: int = 900

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
