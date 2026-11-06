import { defineConfig } from "@playwright/test";

// Ports are env-overridable so e2e can run beside a busy dev machine
// (the default 8000 is commonly taken by another project's backend).
const FRONT_PORT = process.env.E2E_FRONT_PORT ?? "3000";
const BACK_PORT = process.env.E2E_BACK_PORT ?? "8000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL: `http://localhost:${FRONT_PORT}`,
    // The app's service worker claims pages on first visit and the app then
    // reloads itself — a mid-test reload breaks otherwise-stable flows.
    serviceWorkers: "block",
  },
  webServer: [
    {
      command: `npx vite --port ${FRONT_PORT} --strictPort`,
      port: Number(FRONT_PORT),
      env: { API_URL: `http://localhost:${BACK_PORT}` },
      reuseExistingServer: true,
    },
    {
      command:
        "cd ../backend && uv run uvicorn app.main:app --port " + BACK_PORT,
      port: Number(BACK_PORT),
      env: {
        SECRET_KEY: "e2e-secret-key-not-used-in-prod-32-bytes-min",
        ALLOW_REGISTRATION: "true",
        APP_ENV: "development",
        // Dedicated e2e database: the dev DB sits below head and its next
        // alembic step crashes on SQLite (reported separately), and sharing
        // it would let test data leak into real records anyway. A fresh DB
        // boots cleanly because the baseline is a squashed create_all.
        DATABASE_URL: "sqlite+aiosqlite:///./data/e2e-test.db",
        // Parallel workers register/login many users from one IP — the
        // per-IP sliding-window limiters (10/min auth, 100/min general)
        // would otherwise 429 the suite.
        RATE_LIMIT_AUTH: "1000",
        RATE_LIMIT_GENERAL: "5000",
      },
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
