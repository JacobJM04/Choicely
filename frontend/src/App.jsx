import { useEffect, useState } from 'react'
import './App.css'
import Onboarding from './Onboarding'
import Settings from './Settings'
import RegretForecast from './RegretForecast'
import TrackRecord from './TrackRecord'
import MentalLoad from './MentalLoad'
import CheckIns from './CheckIns'
import Reflection from './Reflection'
import DemoControls from './DemoControls'
import ThemeToggle from './ThemeToggle'
import { NotifyNudge } from './Notifications'
import { API_BASE } from './api'
import { prose, when } from './text'

const OUTCOME_LABELS = { good: 'Went well', neutral: 'Fine', regret: 'Regret it' }
const OUTCOME_PAST = { good: 'Went well', neutral: 'Was fine', regret: 'Regretted it' }

function Pct({ value }) {
  return <span className="num">{Math.round((value ?? 0) * 100)}%</span>
}

function PredictionBox({ decision }) {
  if (decision.auto_resolution) {
    return (
      <div className="prior-box auto-resolve">
        <span className="prior-tag">Answered</span>
        <p>{prose(decision.auto_resolution)}</p>
      </div>
    )
  }

  if (decision.source === 'cold_start') {
    return (
      <div className="prior-box">
        <span className="prior-tag">Logged</span>
        <p>First one on record. Choicely will follow up once this has played out.</p>
      </div>
    )
  }

  if (decision.source === 'dataset_prior') {
    return (
      <div className="prior-box">
        <span className="prior-tag">Population</span>
        <p>{prose(decision.prior_description)}</p>
      </div>
    )
  }

  if (decision.source === 'profile_prior' || decision.source === 'personality_prior') {
    const tuned =
      (decision.source === 'personality_prior'
        ? decision.personality_adjusted_regret_rate
        : decision.profile_adjusted_regret_rate) ?? decision.prior_regret_rate
    return (
      <div className="prior-box profile-prior">
        <span className="prior-tag">Tuned</span>
        <div className="prior-stat">
          <span className="num">{Math.round(tuned * 100)}%</span>
          <span>chance you'll regret it</span>
        </div>
        <p className="prior-note">
          Population <Pct value={decision.prior_regret_rate} />, adjusted for your onboarding
          answers. No history in this category yet.
        </p>
      </div>
    )
  }

  const settled = decision.source === 'personal'
  const n = decision.personal_data_points
  return (
    <div className="prior-box personal">
      <span className="prior-tag">{settled ? 'Personal' : 'Blended'}</span>
      <div className="prior-stat">
        <span className="num">{Math.round((decision.blended_regret_estimate ?? 0) * 100)}%</span>
        <span>chance you'll regret it</span>
      </div>
      <p className="prior-note">
        {settled
          ? `From ${n} of your own outcomes.`
          : `${n} of your outcome${n === 1 ? '' : 's'} + the population average.`}
      </p>
    </div>
  )
}

const BREAKDOWN_ROWS = [
  ['your_want', 'You want'],
  ['their_likely_want', 'They want'],
  ['if_they_react_well', 'If it lands well'],
  ['if_they_react_poorly', 'If it lands badly'],
]

function BreakdownBox({ breakdown }) {
  if (!breakdown) return null
  return (
    <div className="breakdown-box">
      <span className="prior-tag">The two sides</span>
      <dl>
        {BREAKDOWN_ROWS.flatMap(([key, label]) => [
          <dt key={`${key}-t`}>{label}</dt>,
          <dd key={`${key}-d`}>{prose(breakdown[key])}</dd>,
        ])}
      </dl>
    </div>
  )
}

function OptionsBox({ decision, onRecordOutcome }) {
  const { items, lean_idx, clear } = decision.options
  const resolved = decision.chosen_option_idx != null
  const [picked, setPicked] = useState(null)
  const best = items[lean_idx]
  const runnerUp = items
    .map((o, i) => ({ o, i }))
    .filter((x) => x.i !== lean_idx)
    .sort((a, b) => a.o.regret_estimate - b.o.regret_estimate)[0]

  return (
    <div className="options-box">
      <span className="prior-tag">
        {resolved ? 'You compared' : 'Comparing'} {items.length} options
      </span>

      <ul className="option-list">
        {items.map((o, i) => {
          const isChosen = resolved && decision.chosen_option_idx === i
          const isLean = i === lean_idx && !resolved
          return (
            <li key={i} className={`option-row${isChosen ? ' chosen' : ''}${isLean ? ' lean' : ''}`}>
              <div className="option-main">
                <span className="option-text">
                  {o.text}
                  {isLean && <span className="option-flag">lowest regret</span>}
                  {isChosen && (
                    <span className="option-flag chosen-flag">
                      you went with this
                      {decision.outcome ? ` · ${OUTCOME_PAST[decision.outcome].toLowerCase()}` : ''}
                    </span>
                  )}
                </span>
                <span className="option-pct num">{Math.round(o.regret_estimate * 100)}%</span>
              </div>
              <div className="option-bar">
                <div className="option-bar-fill" style={{ width: `${Math.max(3, o.regret_estimate * 100)}%` }} />
              </div>
            </li>
          )
        })}
      </ul>

      {!resolved && (
        <p className="option-lean-note">
          {clear
            ? `Choicely leans toward "${best.text}" — the lowest regret of the ${items.length}.`
            : `"${best.text}" edges it, but it's close with "${runnerUp.o.text}".`}
        </p>
      )}

      {!resolved && picked === null && (
        <div className="outcome-prompt option-pick">
          <span>Which did you go with?</span>
          <div className="outcome-buttons">
            {items.map((o, i) => (
              <button key={i} onClick={() => setPicked(i)}>
                {o.text}
              </button>
            ))}
          </div>
        </div>
      )}

      {!resolved && picked !== null && (
        <div className="outcome-prompt">
          <span>“{items[picked].text}” — how did it land?</span>
          <div className="outcome-buttons">
            {Object.entries(OUTCOME_LABELS).map(([key, label]) => (
              <button key={key} onClick={() => onRecordOutcome(decision.id, key, picked)}>
                {label}
              </button>
            ))}
            <button className="option-back" onClick={() => setPicked(null)}>
              change
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function SafetyBox({ safety }) {
  return (
    <div className={`safety-box safety-${safety.tier}`}>
      <span className="prior-tag">{safety.tier === 'crisis' ? 'Choicely stepped back' : 'Worth a second opinion'}</span>
      <p>{prose(safety.message)}</p>
      {safety.resources?.length > 0 && (
        <ul className="safety-resources">
          {safety.resources.map((r, i) => (
            <li key={i}>
              {r.url ? (
                <a href={r.url} target="_blank" rel="noopener noreferrer">
                  {r.label}
                </a>
              ) : (
                <span className="safety-resource-label">{r.label}</span>
              )}
              {r.detail && <span className="safety-resource-detail"> — {r.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function DecisionCard({ decision, onRecordOutcome }) {
  const isOptions = !!decision.options
  const crisis = decision.safety?.tier === 'crisis'

  return (
    <div className="decision-card">
      <div className="decision-card-top">
        <p className="decision-text">
          {decision.text}
          {decision.reopened_count > 1 && (
            <span className="reopened-badge">&nbsp;reopened {decision.reopened_count}×</span>
          )}
        </p>
        <div className="badges">
          {isOptions && !crisis && <span className="badge badge-compare">compare</span>}
          {!crisis && <span className="badge">{decision.decision_type}</span>}
          {!crisis && <span className="badge">{decision.stakes}</span>}
          {!crisis && decision.urgency === 'high' && <span className="badge badge-urgent">urgent</span>}
        </div>
      </div>

      {crisis ? (
        <SafetyBox safety={decision.safety} />
      ) : (
        <>
          {decision.safety && <SafetyBox safety={decision.safety} />}

          {isOptions ? (
            <OptionsBox decision={decision} onRecordOutcome={onRecordOutcome} />
          ) : (
            <>
              <PredictionBox decision={decision} />
              <BreakdownBox breakdown={decision.breakdown} />

              {decision.outcome ? (
                <div className="outcome-recorded">
                  <span className={`dot ${decision.outcome}`} />
                  {OUTCOME_PAST[decision.outcome] ?? decision.outcome}
                </div>
              ) : (
                <div className="outcome-prompt">
                  <span>How did it go?</span>
                  <div className="outcome-buttons">
                    {Object.entries(OUTCOME_LABELS).map(([key, label]) => (
                      <button key={key} onClick={() => onRecordOutcome(decision.id, key)}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}

      <div className="timestamp">{when(decision.timestamp)}</div>
    </div>
  )
}

function riskLabel(value) {
  if (typeof value !== 'number') return null
  if (value <= 0.25) return 'cautious'
  if (value >= 0.75) return 'bold'
  return null
}

function ProfilePanel({ profile, onOpenSettings }) {
  const chips = [
    riskLabel(profile.risk_tolerance_financial) && `${riskLabel(profile.risk_tolerance_financial)} w/ money`,
    riskLabel(profile.risk_tolerance_social) && `${riskLabel(profile.risk_tolerance_social)} socially`,
    profile.conflict_style && `${profile.conflict_style} in conflict`,
  ].filter(Boolean)

  return (
    <div>
      <p className="kicker">Profile</p>
      <p className="rail-name">{profile.name}</p>
      <p className="rail-sub">{profile.planning_label} decider</p>
      {chips.length > 0 && (
        <div className="chips">
          {chips.map((c) => (
            <span key={c} className="chip">{c}</span>
          ))}
        </div>
      )}
      <button className="rail-link" onClick={onOpenSettings}>Retake survey</button>
    </div>
  )
}

function StatsPanel({ total, resolved }) {
  return (
    <div>
      <p className="kicker">Activity</p>
      <div className="stat-row">
        <span className="num">{total}</span>
        <span>decisions logged</span>
      </div>
      <div className="stat-row">
        <span className="num">{resolved}</span>
        <span>outcomes recorded</span>
      </div>
    </div>
  )
}

function DecisionDebt({ items, decisiveness }) {
  if (!items || items.length === 0) return null
  const prominent = typeof decisiveness === 'number' && decisiveness >= 0.6
  return (
    <div className="debt">
      <h3>Decision debt</h3>
      {prominent && <p className="debt-lead">You tend to deliberate. Still unresolved:</p>}
      <div className="debt-list">
        {items.map((item) => (
          <div key={item.topic_id} className="debt-item">{prose(item.callout)}</div>
        ))}
      </div>
    </div>
  )
}

const PREDICTION_TIERS = [
  { label: 'Population', text: 'The average for this kind of decision.' },
  { label: 'Tuned', text: 'That average, nudged by your onboarding answers.' },
  { label: 'Blended', text: 'Mixed with your own outcomes as they accumulate.' },
  { label: 'Personal', text: '10+ of your outcomes — predicts from your history alone.' },
]

function PredictionExplainer() {
  return (
    <div>
      <p className="kicker">How the estimate is built</p>
      <ol className="tier-list">
        {PREDICTION_TIERS.map((t) => (
          <li key={t.label}>
            <strong>{t.label}.</strong> {t.text}
          </li>
        ))}
      </ol>
    </div>
  )
}

function App() {
  const [profile, setProfile] = useState(undefined) // undefined = checking, null = none yet
  const [view, setView] = useState('main') // 'main' | 'settings' | 'retake'
  const [mainTab, setMainTab] = useState('timeline') // 'timeline' | 'forecast' | 'record'
  const [showAllDecisions, setShowAllDecisions] = useState(false)
  const [decisions, setDecisions] = useState([])
  const [debtItems, setDebtItems] = useState([])
  const [text, setText] = useState('')
  const [compareMode, setCompareMode] = useState(false)
  const [options, setOptions] = useState(['', ''])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [refreshTick, setRefreshTick] = useState(0)
  const bumpRefresh = () => setRefreshTick((t) => t + 1)

  function refreshDashboard() {
    fetch(`${API_BASE}/dashboard`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then(setDebtItems)
      .catch(() => console.error('Could not load the decision-debt dashboard.'))
  }

  useEffect(() => {
    fetch(`${API_BASE}/profile`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setProfile)
      .catch(() => setProfile(null))
  }, [])

  useEffect(() => {
    if (!profile) return
    fetch(`${API_BASE}/decisions`)
      .then((res) => res.json())
      .then(setDecisions)
      .catch(() => setError('Could not reach the Choicely server.'))
    refreshDashboard()
  }, [profile, refreshTick])

  async function handleSubmit(e) {
    e.preventDefault()
    const compareOpts = options.map((o) => o.trim()).filter(Boolean)
    const trimmed = text.trim()
    if (compareMode ? compareOpts.length < 2 : !trimmed) return
    setLoading(true)
    setError('')
    try {
      const body = compareMode ? { text: trimmed, options: compareOpts } : { text: trimmed }
      const res = await fetch(`${API_BASE}/decisions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error('Request failed')
      const created = await res.json()
      setDecisions((prev) => [created, ...prev])
      setText('')
      setOptions(['', ''])
      setCompareMode(false)
      bumpRefresh()
    } catch {
      setError('Something went wrong logging that. Try again.')
    } finally {
      setLoading(false)
    }
  }

  async function handleRecordOutcome(decisionId, outcome, chosenOption) {
    setError('')
    try {
      const body = { outcome }
      if (chosenOption != null) body.chosen_option = chosenOption
      const res = await fetch(`${API_BASE}/decisions/${decisionId}/outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      // 409 = an outcome was already recorded (double-tap / another tab). The
      // decision is in a valid state; just resync rather than showing an error.
      if (!res.ok && res.status !== 409) throw new Error('Request failed')
      if (res.ok) {
        const updated = await res.json()
        setDecisions((prev) => prev.map((d) => (d.id === decisionId ? updated : d)))
      }
      bumpRefresh()
    } catch {
      setError('Could not save that outcome. Try again.')
    }
  }

  if (profile === undefined) return <div className="app-shell" />
  if (profile === null) return <Onboarding onComplete={setProfile} />

  if (view === 'settings') {
    return <Settings profile={profile} onRetake={() => setView('retake')} onBack={() => setView('main')} />
  }
  if (view === 'retake') {
    return (
      <Onboarding
        initialName={profile.name}
        onComplete={(saved) => {
          setProfile(saved)
          setView('main')
        }}
      />
    )
  }

  const resolved = decisions.filter((d) => d.outcome).length

  // A standing question logged many times without a decision shouldn't fill the
  // timeline with near-identical cards — collapse each unresolved topic to its
  // most recent entry (the list is newest-first, so the first one wins).
  const seenTopics = new Set()
  const timelineDecisions = decisions.filter((d) => {
    if (d.outcome || !d.topic_id || d.reopened_count <= 1) return true
    if (seenTopics.has(d.topic_id)) return false
    seenTopics.add(d.topic_id)
    return true
  })

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="brand">
          <span className="brand-mark" />
          Choicely
        </span>
        <nav className="topbar-nav">
          <button className={mainTab === 'timeline' ? 'active' : ''} onClick={() => setMainTab('timeline')}>
            Timeline
          </button>
          <button className={mainTab === 'forecast' ? 'active' : ''} onClick={() => setMainTab('forecast')}>
            Regret forecast
          </button>
          <button className={mainTab === 'record' ? 'active' : ''} onClick={() => setMainTab('record')}>
            Track record
          </button>
        </nav>
        <span className="topbar-spacer" />
        <div className="topbar-actions">
          <ThemeToggle />
          <button className="topbar-who" onClick={() => setView('settings')}>
            <span className="avatar">{profile.name.slice(0, 1).toUpperCase()}</span>
            {profile.name}
          </button>
        </div>
      </header>

      <div className="app-grid">
        <main className="col-main">
          {mainTab === 'timeline' && (
            <>
              <div className="section-head">
                <p className="kicker">Timeline</p>
                <h1>What's on your mind, {profile.name}?</h1>
                <p>Log a decision. Choicely classifies it, estimates the regret, and follows up.</p>
              </div>

              {compareMode ? (
                <form className="composer-compare" onSubmit={handleSubmit}>
                  <input
                    type="text"
                    className="compare-context"
                    placeholder="what's the decision? (optional)"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    disabled={loading}
                  />
                  {options.map((o, i) => (
                    <div key={i} className="compare-opt">
                      <span className="compare-opt-n">{String.fromCharCode(65 + i)}</span>
                      <input
                        type="text"
                        placeholder={`option ${String.fromCharCode(65 + i)}`}
                        value={o}
                        onChange={(e) =>
                          setOptions((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))
                        }
                        disabled={loading}
                      />
                      {options.length > 2 && (
                        <button
                          type="button"
                          className="compare-opt-x"
                          onClick={() => setOptions((prev) => prev.filter((_, j) => j !== i))}
                          aria-label="Remove option"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
                  <div className="compare-actions">
                    {options.length < 4 && (
                      <button
                        type="button"
                        className="compare-add"
                        onClick={() => setOptions((prev) => [...prev, ''])}
                      >
                        + option
                      </button>
                    )}
                    <span className="compare-actions-spacer" />
                    <button
                      type="button"
                      className="compare-cancel"
                      onClick={() => {
                        setCompareMode(false)
                        setOptions(['', ''])
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || options.filter((o) => o.trim()).length < 2}
                    >
                      Compare
                    </button>
                  </div>
                </form>
              ) : (
                <form className="composer" onSubmit={handleSubmit}>
                  <input
                    type="text"
                    placeholder="should I skip leg day today"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    disabled={loading}
                  />
                  <button type="submit" disabled={loading || !text.trim()}>
                    Log it
                  </button>
                </form>
              )}

              {!compareMode && (
                <button className="compare-toggle" onClick={() => setCompareMode(true)}>
                  …or compare a few options
                </button>
              )}

              {error && <p className="error">{error}</p>}

              <CheckIns refreshKey={refreshTick} onResolved={bumpRefresh} />
              <NotifyNudge decisionCount={decisions.length} />
              <MentalLoad refreshKey={refreshTick} />
              <Reflection refreshKey={refreshTick} />

              {timelineDecisions.length === 0 ? (
                <p className="empty-state">Nothing logged yet. Type your first decision above.</p>
              ) : (
                <>
                  <div className="timeline">
                    {(showAllDecisions ? timelineDecisions : timelineDecisions.slice(0, 6)).map((d) => (
                      <DecisionCard key={d.id} decision={d} onRecordOutcome={handleRecordOutcome} />
                    ))}
                  </div>
                  {timelineDecisions.length > 6 && (
                    <button className="show-all-btn" onClick={() => setShowAllDecisions((v) => !v)}>
                      {showAllDecisions
                        ? 'Show less'
                        : `${timelineDecisions.length - 6} earlier decision${timelineDecisions.length - 6 !== 1 ? 's' : ''}`}
                    </button>
                  )}
                </>
              )}
            </>
          )}

          {mainTab === 'forecast' && <RegretForecast key={refreshTick} />}
          {mainTab === 'record' && <TrackRecord refreshKey={refreshTick} />}
        </main>

        <aside className="rail">
          <ProfilePanel profile={profile} onOpenSettings={() => setView('settings')} />
          <StatsPanel total={decisions.length} resolved={resolved} />
          <DecisionDebt items={debtItems} decisiveness={profile.decisiveness} />
          <PredictionExplainer />
        </aside>
      </div>

      <DemoControls onAdvance={bumpRefresh} />
    </div>
  )
}

export default App
