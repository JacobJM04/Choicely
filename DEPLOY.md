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
| `ANTHROPIC_API_KEY` | switches classification, the game-theory breakdown, the weekly reflection, and the crisis screen from heuristics to the real Claude API. Optional — everything runs without it. |
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

- **Render / Railway / Fly.io**: point at the `Dockerfile`, attach a
  persistent volume mounted at `/srv/data`, set `ANTHROPIC_API_KEY` if you
  want the Claude paths. Fly needs `fly volumes create`; Render's disks
  and Railway's volumes work the same way.
- **Web Push requires HTTPS** (all three platforms terminate TLS for you,
  so this is automatic on a `*.onrender.com` / `*.up.railway.app` /
  `*.fly.dev` URL).
- The image is ~200 MB (python:3.12-slim + deps). Cold start is a second
  or two.
