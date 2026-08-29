import { useEffect, useState } from 'react'
import './MentalLoad.css'
import { API_BASE } from './api'
import { prose } from './text'

function Tile({ value, label, tone }) {
  return (
    <div className={`load-tile${tone ? ` ${tone}` : ''}`}>
      <span className="num load-tile-value">{value}</span>
      <span className="load-tile-label">{label}</span>
    </div>
  )
}

export default function MentalLoad({ refreshKey }) {
  const [load, setLoad] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/load`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setLoad)
      .catch(() => setLoad(null))
  }, [refreshKey])

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
        <Tile value={load.offloaded} label="off your plate" tone="lifted" />
        <Tile value={load.closed} label="loops closed" tone="closed" />
        <Tile value={stillOpen} label="still open" tone={stillOpen > 0 ? 'carried' : undefined} />
      </div>
      {footerBits.length > 0 && <p className="load-footer num">{footerBits.join('  ·  ')}</p>}
    </section>
  )
}
