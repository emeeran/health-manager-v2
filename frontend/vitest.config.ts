import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    // Playwright e2e specs live outside the vitest suite.
    exclude: ["**/node_modules/**", "e2e/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.d.ts",
        "src/main.tsx",
        "src/**/__tests__/**",
        "src/**/*.test.*",
      ],
      // Ratchet: measured 15% lines / 12% branches (2026-11-02, post phase
      // 12; whole-tree counting, same as upstream). Floors sit 1pt under.
      // Raise as coverage grows — never lower.
      thresholds: {
        statements: 14,
        branches: 11,
        functions: 12,
        lines: 14,
      },
    },
  },
});
