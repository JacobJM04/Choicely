import { useState } from 'react'
import './DemoControls.css'
import { API_BASE } from './api'

// The time-travel control is a demo aid, not a product feature. It only shows
// when a viewer explicitly opts in with ?demo in the URL, so the normal app
// view stays clean.
function demoEnabled() {
  try {
    return new URLSearchParams(window.location.search).has('demo')
  } catch {
    return false
  }
}

export default function DemoControls({ onAdvance }) {
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState('')

  if (!demoEnabled()) return null

  async function advance(hours, label) {
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/demo/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hours }),
      })
      if (!res.ok) throw new Error('failed')
      setFlash(`${label} passes…`)
      setTimeout(() => setFlash(''), 2200)
      onAdvance?.()
    } catch {
      setFlash('Could not advance time')
      setTimeout(() => setFlash(''), 2200)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="demo-controls">
      {flash && <span className="demo-flash">{flash}</span>}
      <span className="demo-label">demo</span>
      <button disabled={busy} onClick={() => advance(24, 'A day')}>+1d</button>
      <button disabled={busy} onClick={() => advance(72, 'Three days')}>+3d</button>
    </div>
  )
}
