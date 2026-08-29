import { useEffect, useState } from 'react'
import './RegretForecast.css'
import { API_BASE } from './api'
import { prose } from './text'

const OUTCOME_COLOR = {
  good: 'var(--m-good)',
  neutral: 'var(--m-neutral)',
  regret: 'var(--m-regret)',
}

const pct = (v) => `${Math.round((v ?? 0) * 100)}%`

// A plain horizontal scale: 0% on the left, 100% on the right, a tick for the
// population rate and a tick for the reader's own estimate. No axes, no lines,
// no legend — just "most people are here, you are here."
function RegretBar({ population, estimate }) {
  const clamp = (v) => Math.max(2, Math.min(98, v * 100))
  const est = clamp(estimate)
  const pop = clamp(population)
  const higher = estimate >= population
  const edge = (v) => (v < 12 ? 'edge-l' : v > 88 ? 'edge-r' : '')
  return (
    <div className="rb">
      <div className="rb-above">
        <span className={`rb-label rb-label-pop ${edge(pop)}`} style={{ left: `${pop}%` }}>
          everyone <b className="num">{pct(population)}</b>
        </span>
      </div>
      <div className="rb-track">
        <div className="rb-fill" style={{ width: `${est}%` }} />
        <div className="rb-tick rb-tick-pop" style={{ left: `${pop}%` }} />
        <div className="rb-tick rb-tick-you" style={{ left: `${est}%` }} />
      </div>
      <div className="rb-below">
        <span className={`rb-label rb-label-you ${edge(est)}`} style={{ left: `${est}%` }}>
          you <b className="num">{pct(estimate)}</b>
          {!higher && <span className="rb-drop"> ↓</span>}
        </span>
      </div>
    </div>
  )
}

const STRIP_CAP = 30

function OutcomeStrip({ outcomes }) {
  if (!outcomes.length) return null
  const shown = outcomes.length > STRIP_CAP ? outcomes.slice(-STRIP_CAP) : outcomes
  const hidden = outcomes.length - shown.length
  return (
    <div className="fc-strip">
      <span className="fc-strip-label">your outcomes</span>
      <div className="fc-strip-cells">
        {hidden > 0 && <span className="fc-strip-more">+{hidden}</span>}
        {shown.map((o) => (
          <span
            key={o.n}
            className="fc-cell"
            style={{ background: OUTCOME_COLOR[o.outcome] }}
            title={`${o.outcome} — ${o.text}`}
          />
        ))}
      </div>
    </div>
  )
}

function caption(f) {
  if (f.data_points === 0) {
    return `${pct(f.population_prior)} of people regret this. Log an outcome or two and Choicely starts tailoring the number to you.`
  }
  const dir =
    Math.abs(f.blended_now - f.population_prior) < 0.03
      ? 'kept your estimate close, at'
      : f.blended_now > f.population_prior
        ? 'pushed your estimate up to'
        : 'pulled your estimate down to'
  const s = f.data_points === 1 ? '' : 's'
  return `${pct(f.population_prior)} of people regret this. Your ${f.data_points} recorded outcome${s} ${dir} ${pct(f.blended_now)}.`
}

function trustLine(f) {
  if (f.data_points === 0) return null
  if (f.confidence >= 1) return 'Now based entirely on your own history.'
  const share = f.confidence < 0.5 ? 'still mostly the general pattern' : 'now mostly your own history'
  return `${f.data_points} of ${f.saturation_points} outcomes — ${share}.`
}

function ForecastCard({ forecast }) {
  return (
    <div className="forecast-card">
      <div className="forecast-card-head">
        <div>
          <span className="forecast-type">{forecast.decision_type}</span>
          <h3>{forecast.category_label}</h3>
        </div>
        <div className="forecast-now-stat">
          <span className="forecast-now-value num">{pct(forecast.blended_now)}</span>
          <span className="forecast-now-label">chance you'll regret it</span>
        </div>
      </div>

      <p className="forecast-verdict">{prose(forecast.verdict)}</p>

      <RegretBar population={forecast.population_prior} estimate={forecast.blended_now} />
      <OutcomeStrip outcomes={forecast.outcomes} />

      <p className="forecast-caption">{caption(forecast)}</p>
      {trustLine(forecast) && <p className="forecast-trust">{trustLine(forecast)}</p>}
    </div>
  )
}

export default function RegretForecast() {
  const [forecasts, setForecasts] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`${API_BASE}/insights`)
      .then((res) => {
        if (!res.ok) throw new Error('Request failed')
        return res.json()
      })
      .then(setForecasts)
      .catch(() => setError('Could not load your regret forecasts.'))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (!forecasts) return <p className="empty-state">Loading…</p>
  if (forecasts.length === 0) {
    return (
      <p className="empty-state">
        No forecasts yet. Log a few decisions and record how they went — the estimate builds itself
        from your outcomes.
      </p>
    )
  }

  return (
    <div className="forecast-list">
      <div className="forecast-intro">
        <h2>Regret forecast</h2>
        <p>
          Each kind of decision starts at the average for everyone. As you record how things go, the
          number moves toward <em>your</em> pattern.
        </p>
      </div>
      {forecasts.map((f) => (
        <ForecastCard key={f.category_label} forecast={f} />
      ))}
    </div>
  )
}
