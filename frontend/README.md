# TAM Frontend

Production-grade frontend for TAM (Financial Due Diligence Automation), built with Next.js App Router + TypeScript + Tailwind + reusable shadcn-style components.

## Run locally

1. Install Node.js 20+ and npm.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start dev server:
   ```bash
   npm run dev
   ```
4. Open `http://localhost:3000`.

## Included

- Sidebar routes: Dashboard, Documents, Financial Analysis, Risk Assessment, Customer Analytics, Reports, Inquiry, Notes, Settings
- Topbar selectors: Deal, Period, Basis, Export Pack
- Clickable KPI cards -> Metric trace modal (Lineage + Cell Trace)
- Clickable charts -> Drilldown modal with expanded chart + TAM Build Steps panel
- Mock APIs with Zod validation and simulated latency
- Risk scoring, tie-outs, inquiry workflow, notes persistence via Zustand + localStorage
- Inquiry Copilot chat in `Inquiry` tab, backed by `/api/inquiry/assistant`

## Optional LLM setup for Inquiry Copilot

If `OPENAI_API_KEY` is set, Inquiry Copilot uses OpenAI Responses API.  
If not set, it falls back to deterministic dashboard-grounded answers.

Create `.env.local`:

```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
```

## Auth and Entry Flow

Authentication is real — it's backed by the FastAPI backend's `/api/v1/auth/*`
endpoints (Argon2id password hashing, JWT session cookie), not a client-side
mock. See the repo-root `README.md`'s Security section for the backend-side
design (password hashing, at-rest encryption, per-deal authorization, TLS,
access logging).

- First page: `/welcome`
- New analyst sign-up: `/signup` (company-domain email required, 2-step wizard)
- Sign in page: `/login`
- Forgot/reset password: `/forgot-password` -> `/reset-password?token=...`
- First-time post-login intake + walkthrough: `/onboarding`
- Final destination after analysis load: `/dashboard`

Behavior:
- First-time user: sign up/sign in -> `/onboarding` -> Generate Analysis -> `/dashboard`
- Returning user: sign in -> directly to `/dashboard`
- Existing analysts can launch a new company intake anytime via `Start New Company Analysis` in the top bar.

There is no seeded demo account — sign up to create one. `middleware.ts` only
checks for the presence of the session cookie (`tam_session`) to decide
whether to redirect between `/login` and the protected routes; the backend is
the actual source of truth and re-verifies the JWT on every API call, so a
forged or expired cookie still gets rejected with 401 there.

The frontend (`localhost:3000`) and backend (`localhost:8000`) are different
origins, so every backend call in `lib/api/fdd-client.ts` sends
`credentials: "include"` to carry the httpOnly session cookie cross-origin;
the backend's CORS config allows credentialed requests from the frontend's
origin explicitly (see `CORS_ORIGINS` in the backend `.env`).
