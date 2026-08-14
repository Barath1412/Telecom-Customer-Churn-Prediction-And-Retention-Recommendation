# Retention Console — frontend

Agent-facing console for the telecom customer churn retention system.

## Setup Instructions

### 1 — Run with NO backend at all (recommended for development)

```bash
cd frontend
npm install
npx msw init public --save          # one-off: writes public/mockServiceWorker.js
cp .env.example .env.local          # VITE_USE_MSW=true
npm run dev                         # http://localhost:5173
```

Every screen works against `src/mocks/fixtures/*.json`. Those files are **generated**
by `python -m src.api_fixtures` in the repository root, from the real model, catalog
v3 and knowledge base v4 — they are not hand-written, so a screen built against them
is a screen built against the real contract.

### 2 — Run against the API

```bash
# in the repo root
uvicorn app.main:app --reload --port 8000

# here
npm run dev                         # VITE_USE_MSW unset; Vite proxies /api -> :8000
```

### 3 — Production Build & Deployment

```bash
npm run build                       # tsc -b && vite build  ->  dist/
npm run preview                     # serve dist locally to smoke-test
```

**Deployment Notes:**
`dist/` is static, served behind the same origin as the API so the session cookie stays first-party (no CORS needed). The host must rewrite unknown paths to `index.html` for client-side routing. Set `Cache-Control: max-age=31536000, immutable` on `/assets/*` (filenames are content-hashed) and `no-cache` on `index.html`.

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Dev server with HMR |
| `npm run build` | Typecheck then production build to `dist/` |
| `npm run typecheck` | Strict TypeScript check (`tsc --noEmit`) |
| `npm run lint` | ESLint, zero warnings allowed (`eslint . --max-warnings 0`) |
| `npm test` | Vitest + Testing Library + MSW + vitest-axe |

## Rules Enforced at the Token & Tooling Layer

- **Design Tokens in CSS Only:** All colors, fonts, sizing, spacing, and shadows live exclusively in `src/index.css` under `@theme`. No hex codes allowed in components.
- **No Raw `toFixed`:** ESLint blocks `Number.prototype.toFixed` outside `lib/format.ts` so money/probability formatting remains consistent across screens.
- **Strict Accessibility:** Single `:focus-visible` ring, skip-to-main link as first tabbable element, focus shift to `<main id="main" tabIndex={-1}>` on route changes, zero `axe` violations in automated tests.
- **Three Policy States:** `not_evaluable` must never render as a pass.
- **Control-Arm Labeling:** Control-arm customers are explicitly flagged to prevent agents from calling held-back customers.
