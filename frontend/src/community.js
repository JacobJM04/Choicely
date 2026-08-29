// Whether the user has opted in to sharing anonymized (category, outcome)
// pairs to the community pool. Stored per-browser; sent with each outcome.
import { API_BASE } from './api'

const KEY = 'choicely.contribute'

export function isContributing() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function setContributing(on) {
  try {
    localStorage.setItem(KEY, on ? '1' : '0')
  } catch {
    /* private mode — the toggle just won't persist */
  }
}

export function fetchCommunityStats() {
  return fetch(`${API_BASE}/community/stats`)
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)
}
