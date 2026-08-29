import { useEffect, useState } from 'react'
import './RegretPatterns.css'
import { API_BASE } from './api'
import { prose } from './text'

const pct = (v) => `${Math.round((v ?? 0) * 100)}%`

const DIMENSION_LABEL = {
  time_of_day: 'time of day',
  time_pressure: 'time pressure',
  load: 'how much was already on your plate',
  back_and_forth: 'going back and forth',
  stakes: 'stakes',
}

function Bar({ value, tone, label }) {
  return (
    <div className="rp-bar-row">
      <span className="rp-bar-label">{label}</span>
      <div className="rp-bar-track">
        <div className={`rp-bar-fill ${tone}`} style={{ width: `${Math.max(2, value * 100)}%` }} />
      </div>
      <span className="rp-bar-val num">{pct(value)}</span>
    </div>
  )
}

function TriggerCard({ trigger }) {
  const worse = trigger.direction === 'worse'
  return (
    <div className="rp-card">
      <div className="rp-card-head">
        <span className={`rp-tag ${worse ? 'worse' : 'better'}`}>
          {worse ? 'raises regret' : 'lowers regret'}
        </span>
        <h4>{prose(trigger.headline)}</h4>
      </div>
      <Bar
        value={trigger.trigger_rate}
        tone={worse ? 'neg' : 'pos'}
        label={trigger.label}
      />
      <Bar value={trigger.contrast_rate} tone="muted" label={trigger.contrast_label} />
      <p className="rp-detail">{prose(trigger.detail)}</p>
    </div>
  )
}

export default function RegretPatterns({ refreshKey }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/triggers`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setData)
      .catch(() => setData(null))
  }, [refreshKey])

  if (!data) return null

  return (
    <section className="rp">
      <p className="kicker">When regret clusters</p>

      {data.verdict === 'early' && (
        <p className="rp-note">
          Choicely needs about {data.min_analyzed} closed decisions before it can look for the
          conditions behind your regrets. {data.analyzed} so far.
        </p>
      )}

      {data.verdict === 'nothing_stood_out' && (
        <p className="rp-note">
          Choicely checked {data.checked.length} conditions ({data.checked.join(', ')}) across{' '}
          {data.analyzed} closed decisions — nothing moved your regret rate enough to call a
          pattern yet.
        </p>
      )}

      {data.triggers.length > 0 && (
        <>
          <div className="rp-cards">
            {data.triggers.map((t) => (
              <TriggerCard key={`${t.dimension}-${t.direction}`} trigger={t} />
            ))}
          </div>
          <p className="rp-footer">
            From {data.analyzed} closed decisions.
            {(() => {
              const shown = new Set(data.triggers.map((t) => t.dimension))
              const rest = data.checked.filter(
                (c) => !Object.entries(DIMENSION_LABEL).some(([d, l]) => l === c && shown.has(d)),
              )
              return rest.length ? ` Also checked: ${rest.join(', ')}.` : ''
            })()}
          </p>
        </>
      )}
    </section>
  )
}
