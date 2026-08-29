import { useEffect, useState } from 'react'
import './Reflection.css'
import { API_BASE } from './api'
import { prose } from './text'

const SOURCE_LABEL = { claude: 'written by Claude', heuristic: 'from your patterns', empty: '' }

export default function Reflection({ refreshKey }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    let live = true
    fetch(`${API_BASE}/reflection`)
      .then((res) => (res.ok ? res.json() : null))
      .then((d) => live && setData(d))
      .catch(() => live && setData(null))
    return () => {
      live = false
    }
  }, [refreshKey])

  if (!data || !data.insights || data.insights.length === 0) return null

  return (
    <section className="reflection">
      <div className="reflection-head">
        <p className="kicker">Reflection</p>
        {SOURCE_LABEL[data.source] && (
          <span className="reflection-source">{SOURCE_LABEL[data.source]}</span>
        )}
      </div>
      <p className="reflection-intro">{prose(data.intro)}</p>
      <ul className="reflection-list">
        {data.insights.map((it, i) => (
          <li key={i}>
            <strong>{prose(it.headline)}</strong>
            <span>{prose(it.detail)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
