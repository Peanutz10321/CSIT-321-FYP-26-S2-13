# Frontend — React + Vite voter/organizer/admin UI

This is a navigation page. The full setup and onboarding guide lives in the
[root readme](../readme.md); it is not duplicated here.

React 19, React Router 7, Tailwind CSS 3, built with Vite 8. It is a single-page
app that talks to the FastAPI backend over JSON with a JWT bearer token — the
backend does all encryption; no cryptography runs in the browser.

## Getting started

The frontend needs the backend running to be useful. See
[Running locally](../readme.md#running-locally) for the full sequence.

```bash
cd frontend
npm ci          # lockfile is committed; prefer this over `npm install`
npm run dev     # http://localhost:5173
```

Open <http://localhost:5173>. The backend's port (8000) serves the API and its
Swagger docs, not this UI.

## Configuration

One variable, `VITE_API_BASE_URL`, documented in
[Configuration → Frontend](../readme.md#frontend) and in
[`.env.example`](.env.example).

- **Development:** optional. Falls back to `http://localhost:8000` when unset.
  Copy `.env.example` to `.env.local` if your backend runs elsewhere.
- **Production build:** required, and must be HTTPS. The build **aborts** rather
  than shipping a bundle pointing at localhost.

Vite inlines `VITE_*` at build time, so a bundle carries whatever value was set
when it was built. There is no runtime override.

If the UI loads but every request fails, the usual cause is the backend's
`CORS_ALLOWED_ORIGINS`, not this variable — see
[Common startup problems](../readme.md#common-startup-problems).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server with HMR on port 5173 |
| `npm test` | Vitest run (React Testing Library, jsdom) |
| `npm run test:watch` | Vitest in watch mode |
| `npm run lint` | ESLint |
| `npm run audit` | `better-npm-audit` at `--level high` — the CI gate |
| `npm run build` | Production build; requires an HTTPS `VITE_API_BASE_URL` |
| `npm run preview` | Serve a built bundle locally |

Inline assignment is bash-only; set the variable first on Windows.

```bash
VITE_API_BASE_URL=https://api.example.edu npm run build      # bash
```

```powershell
$env:VITE_API_BASE_URL = "https://api.example.edu"           # PowerShell
npm run build
```

## Layout

```
src/
  components/      # shared UI primitives
  pages/           # route components + co-located *.test.jsx
  utils/           # api.js, apiConfig.js + tests
  test/setup.js    # Vitest setup
eslint.config.js
vite.config.js     # includes the production API-URL build guard
```

All request URLs are built through `buildApiUrl()` in `src/utils/apiConfig.js`; no
component constructs a backend URL of its own.
