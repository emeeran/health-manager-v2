# Family Health Manager v2 — Frontend

Phase-1 scaffold for the self-hosted family health records app.

## Stack

- React 19 + TypeScript 5 (strict) + Vite 8
- Tailwind CSS v4 (CSS-first config in `src/globals.css`)
- react-router-dom v7 (`src/router.tsx`, lazy pages)
- SWR 2 for all server state
- Vitest + jsdom + Testing Library
- lucide-react, clsx + tailwind-merge (`cn` in `src/lib/utils.ts`)

## Scripts

```bash
npm run dev       # dev server
npm run build     # type-check (tsc -b) + production build
npm run preview   # preview the production build
npm run lint      # eslint
npm run format    # prettier
npm test          # vitest run
```

## API / dev proxy

The backend talks over httpOnly cookies (`credentials: "include"`, base URL `/api/v1`).
In dev, Vite proxies `/api` to `API_URL` (default `http://localhost:8000`) — see
`vite.config.ts`. On a 401 the API client (`src/lib/api-client.ts`) runs a
single-flight `POST /api/v1/auth/refresh` and retries the request once.
