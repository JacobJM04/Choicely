import { useEffect, useState } from 'react'
import './MentalLoad.css'
import { API_BASE } from './api'
import { prose } from './text'
import { Count } from './motion'

function Tile({ value, label, tone, i, hint, onClick }) {
  return (
    <button
      type="button"
      className={`load-tile${tone ? ` ${tone}` : ''}`}
      style={{ '--i': i }}
      onClick={onClick}
    >
      <span className="num load-tile-value">
        <Count value={value} />
      </span>
      <span className="load-tile-label">{label}</span>
      <span className="load-tile-go">{hint} →</span>
    </button>
  )
}

export default function MentalLoad({ refreshKey, onNavigate }) {
  const [load, setLoad] = useState(null)
  const [pending, setPending] = useState(true)

  useEffect(() => {
    let live = true
    setPending(true)
    fetch(`${API_BASE}/load`)
      .then((res) => (res.ok ? res.json() : null))
      .then((d) => live && (setLoad(d), setPending(false)))
      .catch(() => live && (setLoad(null), setPending(false)))
    return () => {
      live = false
    }
  }, [refreshKey])

  if (pending && !load) {
    return (
      <section className="mental-load" aria-busy="true">
        <div className="skeleton skeleton-line" style={{ width: '55%', marginBottom: 'var(--s2)' }} />
        <div className="skeleton skeleton-line" style={{ width: '85%' }} />
        <div className="skeleton skeleton-block" style={{ height: 66, marginTop: 'var(--s3)' }} />
      </section>
    )
  }

  // Nothing to account for until at least one decision has ever been logged.
  if (!load || (load.all_time && load.all_time.logged === 0)) return null

  const stillOpen = load.carried + load.open_loops
  const footerBits = []
  if (load.avg_hours_to_close != null && load.avg_hours_to_close >= 1) {
    const h = load.avg_hours_to_close
    footerBits.push(h >= 48 ? `${Math.round(h / 24)}d avg to close` : `${Math.round(h)}h avg to close`)
  }
  if (load.recent_regret_rate != null) {
    footerBits.push(`${Math.round(load.recent_regret_rate * 100)}% recent outcomes regretted`)
  }

  return (
    <section className="mental-load">
      <p className="kicker">Mental load · last {load.window_days} days</p>
      <p className="load-headline">{prose(load.headline)}</p>
      <div className="load-tiles">
        <Tile
          value={load.offloaded}
          label="off your plate"
          tone="lifted"
          i={0}
          hint="Agent"
          onClick={() => onNavigate?.('agent')}
        />
        <Tile
          value={load.closed}
          label="loops closed"
          tone="closed"
          i={1}
          hint="Track record"
          onClick={() => onNavigate?.('record')}
        />
        <Tile
          value={stillOpen}
          label="still open"
          tone={stillOpen > 0 ? 'carried' : undefined}
          i={2}
          hint="Decision log"
          onClick={() => onNavigate?.('open')}
        />
      </div>
      {footerBits.length > 0 && <p className="load-footer num">{footerBits.join('  ·  ')}</p>}
    </section>
  )
}
