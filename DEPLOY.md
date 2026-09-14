# Deploying Choicely

One container runs everything: FastAPI serves the API **and** the built
React app from the same origin, so there's a single service to deploy.

## Build & run locally

```
docker build -t choicely .
docker run -p 8000:8000 -v choicely-data:/srv/data choicely
```

Open http://localhost:8000. The `-v choicely-data:/srv/data` volume keeps
the SQLite DB and the VAPID keypair across restarts — without it, both
reset on every `docker run` (fine for a throwaway demo, not for anything
real).

## Seeding the demo persona on a fresh deploy

The container starts with an empty user DB (the community pool is
auto-seeded). To load "Maya" and her history:

```
docker exec <container> python seed_demo_data.py --reset
```

## Environment variables

| var | purpose |
|-----|---------|
| `ANTHROPIC_API_KEY` | switches the whole Claude seam on: the **grounded debrief**, the **agent's check-in phrasing + backlog triage**, the weekly reflection, classification, the game-theory breakdown, and the crisis screen all move from heuristics to the real API. Optional — everything runs without it. |
| `CHOICELY_LLM_MODEL` | model for every Claude call. Default `claude-sonnet-5`. Set `claude-opus-5` for a judged run. |
| `CHOICELY_LLM_DISABLED` | `1` forces the heuristic path even with a key present (keeps a public demo's spend at exactly zero). |
| `CHOICELY_DB` | SQLite path. Defaults to `/srv/data/choicely.db` in the image. Point at a mounted volume. |
| `CHOICELY_DATA` | dir for the VAPID keypair files. Defaults to `/srv/data`. |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | supply the Web Push keypair directly (PEM contents + base64url app-server key) instead of a file, so push subscriptions survive a redeploy on a platform without a volume. Generate a pair by running the container once with a volume and copying `/srv/data/vapid_*`. |
| `VAPID_SUBJECT` | `mailto:` contact for VAPID claims. Defaults to `mailto:hello@choicely.app`. |
| `CHOICELY_ORIGINS` | comma-separated extra CORS origins. Only needed for a *split* deploy (frontend and API on different domains); unnecessary for the single-container setup. |
| `CHOICELY_DEMO` | `1` (default) keeps the `POST /demo/advance` clock endpoint enabled. Set to `0` on a real deploy so visitors can't time-shift the timeline. |
| `CHOICELY_PUSH_ALLOW_ANY` | `1` disables the push-endpoint allowlist (which otherwise only permits the real FCM / Mozilla / Apple / Windows push hosts). Local testing against a mock push server only — never in production. |

## Split deploy (frontend and API separate)

Build the frontend with `VITE_API_BASE=https://your-api-host` and host
`frontend/dist/` as static files anywhere; run the backend container with
`CHOICELY_ORIGINS=https://your-frontend-host`.

## Platform notes

- **Render (one click)**: `render.yaml` in the repo root is a Blueprint —
  New → Blueprint → pick the repo and it provisions the Docker web service
  + a 1 GB disk at `/srv/data`. Then set `ANTHROPIC_API_KEY` in the
  Environment tab and redeploy; seed the persona from the Shell tab with
  `python seed_demo_data.py --reset`.
- **Railway / Fly.io**: point at the `Dockerfile`, attach a persistent
  volume mounted at `/srv/data`, set `ANTHROPIC_API_KEY`. Fly needs
  `fly volumes create`; Railway's volumes work like Render's disks.
- **Web Push requires HTTPS** (all three platforms terminate TLS for you,
  so this is automatic on a `*.onrender.com` / `*.up.railway.app` /
  `*.fly.dev` URL).
- The image is ~200 MB (python:3.12-slim + deps). Cold start is a second
  or two.
