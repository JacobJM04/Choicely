// Single source of truth for the backend origin. Override with VITE_API_BASE
// in an .env.local when the backend isn't on the default port.
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
