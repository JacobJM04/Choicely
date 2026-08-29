import { useEffect, useState } from 'react'
import './TrackRecord.css'
import { API_BASE } from './api'
import { prose, when } from './text'

const pct = (v) => `${Math.round((v ?? 0) * 100)}%`
const pts = (v) => Math.round((v ?? 0) * 100)

const OUTCOME_COLOR = {
  good: 'var(--m-good)',
  neutral: 'var(--m-neutral)',
  regret: 'var(--m-regret)',
}

// One bucket of the reliability curve: a 0–100% track with a hollow marker at
// what Choicely predicted and a filled one at what actually happened. When the
// two sit on top of each other the prediction was well-calibrated; the gap
// between them is the miscalibration, shown literally.
function ReliabilityRow({ bucket }) {
  const p = Math.max(2, Math.min(98, bucket.predicted * 100))
  const a = Math.max(2, Math.min(98, bucket.actual * 100))
  const gap = Math.abs(bucket.predicted - bucket.actual)
  const tight = gap <= 0.12
  return (
    <div className="tr-rel-row">
      <span className="tr-rel-range num">
        {pts(bucket.lo)}–{pts(bucket.hi)}%
      </span>
      <div className="tr-rel-track">
        <div
          className="tr-rel-link"
          style={{ left: `${Math.min(p, a)}%`, width: `${Math.abs(p - a)}%` }}
          data-tight={tight || undefined}
        />
        <span className="tr-rel-dot tr-rel-pred" style={{ left: `${p}%` }} title="predicted" />
        <span
          className="tr-rel-dot tr-rel-actual"
          style={{ left: `${a}%` }}
          title="actual"
        />
      </div>
      <span className="tr-rel-meta num">
        said {pct(bucket.predicted)}<span className="tr-rel-arrow"> → </span>
        <span className={tight ? 'tr-rel-ok' : 'tr-rel-off'}>{pct(bucket.actual)}</span>
        <span className="tr-rel-n"> · n={bucket.n}</span>
      </span>
    </div>
  )
}

function TierBar({ tier, worst }) {
  const w = Math.max(4, (tier.mae / worst) * 100)
  return (
    <div className="tr-tier">
      <span className="tr-tier-label">
        {tier.label} <span className="tr-tier-n num">n={tier.n}</span>
      </span>
      <div className="tr-tier-bar-wrap">
        <div className="tr-tier-bar" style={{ width: `${w}%` }} />
        <span className="tr-tier-val num">±{pts(tier.mae)} pts</span>
      </div>
    </div>
  )
}

function RecentRow({ item }) {
  const hitSide =
    (item.predicted >= 0.5 && item.actual >= 0.5) ||
    (item.predicted < 0.5 && item.actual < 0.5)
  return (
    <li className="tr-recent-row">
      <span className={`tr-recent-mark ${hitSide ? 'hit' : 'miss'}`} />
      <span className="tr-recent-text">{item.text}</span>
      <span className="tr-recent-nums num">
        said {pct(item.predicted)}
        <span className="tr-recent-arrow">→</span>
        <span className="tr-recent-outcome" style={{ color: OUTCOME_COLOR[item.outcome] }}>
          {item.outcome}
        </span>
      </span>
    </li>
  )
}

export default function TrackRecord({ refreshKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetch(`${API_BASE}/track-record`)
      .then((res) => {
        if (!res.ok) throw new Error('Request failed')
        return res.json()
      })
      .then(setData)
      .catch(() => setError('Could not load the track record.'))
  }, [refreshKey])

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="empty-state">Loading…</p>

  if (data.verdict === 'early') {
    return (
      <div className="tr">
        <div className="tr-intro">
          <h2>Track record</h2>
          <p>Choicely keeps score of its own predictions. Close a few more loops and this fills in.</p>
        </div>
        <p className="empty-state">{prose(data.headline)}</p>
      </div>
    )
  }

  const worstTier = Math.max(...data.by_tier.map((t) => t.mae), 0.01)
  const cc = data.confident_calls
  const ar = data.auto_resolve_calls

  return (
    <div className="tr">
      <div className="tr-intro">
        <h2>Track record</h2>
        <p>
          Every prediction Choicely made, scored against what you later recorded. It only ever
          answers a decision outright where this record is strong.
        </p>
      </div>

      <section className="tr-headline-card">
        <p className="tr-headline">{prose(data.headline)}</p>
        <div className="tr-headline-stats">
          {cc.n > 0 && (
            <div className="tr-stat">
              <span className="num tr-stat-value">
                {cc.hits}/{cc.n}
              </span>
              <span className="tr-stat-label">confident calls borne out</span>
            </div>
          )}
          {ar.n > 0 && (
            <div className="tr-stat">
              <span className="num tr-stat-value">
                {ar.hits}/{ar.n}
              </span>
              <span className="tr-stat-label">auto-answers it got right</span>
            </div>
          )}
          <div className="tr-stat">
            <span className="num tr-stat-value">{data.scored_count}</span>
            <span className="tr-stat-label">predictions scored</span>
          </div>
        </div>
      </section>

      <section className="tr-block">
        <p className="kicker">Reliability — predicted vs. what happened</p>
        <div className="tr-rel">
          {data.reliability.map((b) => (
            <ReliabilityRow key={b.lo} bucket={b} />
          ))}
        </div>
        <p className="tr-legend num">
          <span className="tr-rel-dot tr-rel-pred inline" /> predicted&nbsp;&nbsp;
          <span className="tr-rel-dot tr-rel-actual inline" /> actual regret rate
        </p>
      </section>

      <section className="tr-block">
        <p className="kicker">Typical miss, by how much it knew you</p>
        <div className="tr-tiers">
          {data.by_tier.map((t) => (
            <TierBar key={t.tier} tier={t} worst={worstTier} />
          ))}
        </div>
        <p className="tr-note">
          Per-decision misses are large by nature — a 70% guess against a yes/no outcome is always
          ~30 points off. The reliability curve above is the fairer read.
        </p>
      </section>

      {data.recent?.length > 0 && (
        <section className="tr-block">
          <p className="kicker">Recent calls</p>
          <ul className="tr-recent">
            {data.recent.map((item, i) => (
              <RecentRow key={i} item={item} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
