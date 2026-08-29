// Single source of truth for the backend origin.
//   - unset (local dev)         -> talk to the dev backend on :8000
//   - VITE_API_BASE="" (deploy) -> same-origin relative requests, because the
//     FastAPI container serves this build itself
//   - VITE_API_BASE="https://api.example.com" -> a split deploy
const raw = import.meta.env.VITE_API_BASE
export const API_BASE = raw === undefined ? 'http://localhost:8000' : raw
