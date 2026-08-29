# --- build the frontend -------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# empty base -> the app makes same-origin requests; FastAPI serves this build
ENV VITE_API_BASE=""
RUN npm run build

# --- run the backend (and serve the built frontend) --------------------
FROM python:3.12-slim AS app
WORKDIR /srv/backend

RUN pip install --no-cache-dir -r /dev/stdin <<'EOF'
fastapi
uvicorn[standard]
pydantic
anthropic
pywebpush
EOF

COPY backend/ /srv/backend/
COPY --from=frontend /build/dist /srv/frontend/dist

# data/ holds the SQLite db + the VAPID keypair; mount a volume here to keep
# them across redeploys, or pass CHOICELY_DB / VAPID_* as env vars.
ENV CHOICELY_DB=/srv/data/choicely.db
ENV CHOICELY_DATA=/srv/data
RUN mkdir -p /srv/data

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
