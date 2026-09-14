import { useState } from 'react'
import './Debrief.css'
import { API_BASE } from './api'
import { prose } from './text'

const CONFIDENCE_LABEL = { low: 'low confidence', medium: 'moderate confidence', high: 'high confidence' }
const OUTCOME_DOT = { good: 'good', neutral: 'neutral', regret: 'regret' }

function GroundedRead({ read, onLog, logging, logged }) {
  return (
    <div className="debrief-read">
      <div className="debrief-read-head">
        <p className="kicker">The real question</p>
      </div>
      <p className="debrief-realq">{prose(read.real_question)}</p>

      {read.in_decision_debt && (
        <p className="debrief-debt">
          You&rsquo;ve logged this one before without ever settling it.
        </p>
      )}

      <dl className="debrief-grid">
        <dt>What's at stake</dt>
        <dd>{prose(read.whats_at_stake)}</dd>
        {read.avoiding && (
          <>
            <dt>What you're circling</dt>
            <dd>{prose(read.avoiding)}</dd>
          </>
        )}
      </dl>

      {read.options?.length > 0 && (
        <ul className="debrief-options">
          {read.options.map((o, i) => (
            <li key={i}>
              <strong>{prose(o.label)}</strong>
              {o.note && <span>{prose(o.note)}</span>}
            </li>
          ))}
        </ul>
      )}

      <div className="debrief-readout">
        <p className="kicker">Grounded read</p>
        <p className="debrief-read-body">{prose(read.grounded_read)}</p>
        <div className="debrief-estimate">
          <span className="num">{Math.round((read.regret_estimate ?? 0) * 100)}%</span>
          <span>
            regret estimate
            {read.personal_data_points > 0
              ? ` · from ${read.personal_data_points} of your outcomes`
              : ' · population rate, no history yet'}
            {' · '}
            {CONFIDENCE_LABEL[read.confidence] ?? read.confidence}
          </span>
        </div>
      </div>

      {read.related?.length > 0 && (
        <div className="debrief-related">
          <p className="kicker">From your log</p>
          <ul>
            {read.related.map((r, i) => (
              <li key={i}>
                {r.outcome && <span className={`dot ${OUTCOME_DOT[r.outcome] ?? ''}`} />}
                <span className="debrief-related-text">{r.text}</span>
                <span className="debrief-related-meta">
                  {r.outcome_word ? `${r.outcome_word}, ` : ''}
                  {r.when}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="debrief-recommend">
        <p className="kicker">Recommendation</p>
        <p>{prose(read.recommendation)}</p>
      </div>

      <div className="debrief-actions">
        <button className="debrief-log" onClick={onLog} disabled={logging || logged}>
          {logging && <span className="btn-spinner" aria-hidden="true" />}
          {logged ? 'Logged ✓' : logging ? 'Logging…' : 'Log this decision'}
        </button>
      </div>
    </div>
  )
}

export default function Debrief({ onClose, onLogged }) {
  const [text, setText] = useState('')
  const [read, setRead] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [logging, setLogging] = useState(false)
  const [logged, setLogged] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (text.trim().length < 8) return
    setLoading(true)
    setError('')
    setRead(null)
    setLogged(false)
    try {
      const res = await fetch(`${API_BASE}/debrief`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.trim() }),
      })
      if (!res.ok) throw new Error('failed')
      const data = await res.json()
      if (data.source === 'flagged_crisis') {
        setError('That looks like something to talk through with a person, not a regret model.')
      } else {
        setRead(data)
      }
    } catch {
      setError('Could not reach the debrief. Try again.')
    } finally {
      setLoading(false)
    }
  }

  async function logIt() {
    setLogging(true)
    try {
      const res = await fetch(`${API_BASE}/decisions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: read.real_question || text.trim() }),
      })
      if (!res.ok) throw new Error('failed')
      const created = await res.json()
      setLogged(true)
      onLogged?.(created)
    } catch {
      setError('Could not log that. Try again.')
    } finally {
      setLogging(false)
    }
  }

  return (
    <div className="debrief anim-rise" style={{ '--i': 1 }}>
      <form className="debrief-composer" onSubmit={submit}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Talk through a decision you've been stuck on. Everything you're weighing — dump it here, messy is fine."
          rows={4}
          disabled={loading}
        />
        <div className="debrief-composer-actions">
          <button type="button" className="debrief-cancel" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={loading || text.trim().length < 8}>
            {loading && <span className="btn-spinner" aria-hidden="true" />}
            {loading ? 'Reading…' : 'Read it back to me'}
          </button>
        </div>
      </form>

      {error && <p className="error debrief-error">{error}</p>}

      {read && (
        <GroundedRead read={read} onLog={logIt} logging={logging} logged={logged} />
      )}
    </div>
  )
}
