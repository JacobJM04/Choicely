import { useEffect, useState } from 'react'
import './CheckIns.css'
import { API_BASE } from './api'
import { prose } from './text'

const OUTCOMES = [
  { key: 'good', label: 'Went well' },
  { key: 'neutral', label: 'Fine' },
  { key: 'regret', label: 'Regret it' },
]

export default function CheckIns({ refreshKey, onResolved }) {
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(null)

  useEffect(() => {
    let live = true
    fetch(`${API_BASE}/check-ins`)
      .then((res) => (res.ok ? res.json() : []))
      .then((d) => live && setItems(Array.isArray(d) ? d : []))
      .catch(() => live && setItems([]))
    return () => {
      live = false
    }
  }, [refreshKey])

  async function answer(id, outcome) {
    setBusy(id)
    // Drop it from the list right away; the parent refresh reconciles.
    setItems((prev) => prev.filter((it) => it.id !== id))
    try {
      await fetch(`${API_BASE}/decisions/${id}/outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ outcome }),
      })
    } catch {
      /* the parent refresh will bring it back if it didn't take */
    } finally {
      setBusy(null)
      onResolved?.()
    }
  }

  if (items.length === 0) return null

  return (
    <section className="checkins">
      <div className="checkins-head">
        <span className="checkins-dot" />
        <p className="kicker">
          Checking back on {items.length} decision{items.length !== 1 ? 's' : ''}
        </p>
      </div>
      <div className="checkins-list">
        {items.map((it) => (
          <div key={it.id} className="checkin">
            <p className="checkin-prompt">{prose(it.prompt)}</p>
            <div className="checkin-meta">
              <span>{it.decision_type}</span>
              <span>logged {it.logged_relative}</span>
              {it.predicted_regret != null && (
                <span>{Math.round(it.predicted_regret * 100)}% predicted regret</span>
              )}
            </div>
            <div className="checkin-buttons">
              {OUTCOMES.map((o) => (
                <button key={o.key} disabled={busy === it.id} onClick={() => answer(it.id, o.key)}>
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
