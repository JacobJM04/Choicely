import { useEffect, useState } from 'react'
import './Reflection.css'
import { API_BASE } from './api'
import { prose } from './text'

export default function Reflection({ refreshKey }) {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | empty

  useEffect(() => {
    let live = true
    fetch(`${API_BASE}/reflection`)
      .then((res) => (res.ok ? res.json() : null))
      .then((d) => {
        if (!live) return
        const has = d && d.insights && d.insights.length > 0
        // keep whatever's on screen if a refresh comes back empty transiently
        if (has) setData(d)
        setStatus(has ? 'ready' : data ? 'ready' : 'empty')
      })
      .catch(() => live && setStatus((s) => (data ? s : 'empty')))
    return () => {
      live = false
    }
  }, [refreshKey])

  // Only the very first load shows a skeleton; refreshes keep the current text.
  if (status === 'loading' && !data) {
    return (
      <section className="reflection" aria-busy="true">
        <div className="skeleton skeleton-line" style={{ width: '45%', marginBottom: 'var(--s2)' }} />
        <div className="skeleton skeleton-line" style={{ width: '70%' }} />
        <div className="skeleton skeleton-line" style={{ width: '92%', marginTop: 'var(--s3)' }} />
        <div className="skeleton skeleton-line" style={{ width: '85%' }} />
        <div className="skeleton skeleton-line" style={{ width: '60%' }} />
      </section>
    )
  }
  if (status !== 'ready') return null

  return (
    <section className="reflection">
      <div className="reflection-head">
        <p className="kicker">Choicely reflections</p>
      </div>
      <p className="reflection-intro">{prose(data.intro)}</p>
      <ul className="reflection-list">
        {data.insights.map((it, i) => (
          <li key={i} style={{ '--i': i }}>
            <strong>{prose(it.headline)}</strong>
            <span>{prose(it.detail)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
