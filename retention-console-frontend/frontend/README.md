# Retention Console — frontend

Agent-facing console for the churn retention system. React 18 + TypeScript + Vite.

## Run it with no backend

```bash
npm install
npx msw init public --save     # one-off: writes public/mockServiceWorker.js
cp .env.example .env.local     # VITE_USE_MSW=true
npm run dev                    # http://localhost:5173
```

Every screen works against `src/mocks/fixtures/*.json`. Those files are **generated**
by `python -m src.api_fixtures` in the repository root, from the real model, catalog
v3 and knowledge base v4 — they are not hand-written, so a screen built against them
is a screen built against the real contract.

## Run it against the API

```bash
# in the repo root
uvicorn app.main:app --reload --port 8000
# here
npm run dev                    # VITE_USE_MSW unset; Vite proxies /api -> :8000
```

## Scripts

| command | what it does |
|---|---|
| `npm run dev` | dev server with HMR |
| `npm run build` | typecheck then production build to `dist/` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint, zero warnings allowed |
| `npm test` | Vitest + Testing Library + MSW |

## Rules that are enforced, not suggested

- **No raw `toFixed`.** ESLint blocks it. All money and probabilities go through
  `src/lib/format.ts`, because "$120.5" and "$120.50" are the same number and a
  different sentence when an agent reads it to a customer.
- **A Δ is never rendered without its range.** `deltaWithRange()` returns both in one
  string so a component cannot show half of it.
- **Three policy states, not two.** `not_evaluable` must never render as a pass.
- **Control-arm rows must be labelled.** Contacting a held-back customer destroys the
  only measurement of whether any of this works.
