import { useEffect, useState } from 'react'
import './AgentActivity.css'
import { API_BASE } from './api'
import { prose } from './text'
import { Count } from './motion'

const EVENT_META = {
  auto_resolved: { label: 'Answered', tone: 'answer' },
  logged: { label: 'Logged', tone: 'neutral' },
  reopened: { label: 'Repeat', tone: 'warn' },
  checkin_raised: { label: 'Check-in', tone: 'accent' },
  loop_closed: { label: 'Closed', tone: 'good' },
  pattern_found: { label: 'Pattern', tone: 'warn' },
}

const VERDICT_META = {
  answer_now: { label: 'Ready to answer', tone: 'answer', blurb: "Your history is one-sided enough that Choicely would just tell you." },
  keep_watching: { label: 'Keeping watch', tone: 'accent', blurb: 'Waiting on the outcome or more history before it calls these.' },
  stay_quiet: { label: 'Left alone', tone: 'neutral', blurb: "Low stakes, roughly even — not worth a nudge." },
}

const SUMMARY_CELLS = [
  ['answered', 'answered', 'answered outright', 'Told you the answer straight away — no need to ask.'],
  ['closed', 'loops_closed', 'loops closed', 'You reported back, so it could check its guess against reality.'],
  ['check-ins', 'check_ins_raised', 'check-ins raised', 'Followed up on its own, without you asking.'],
  ['patterns', 'patterns_found', 'patterns found', 'A habit it noticed in when things go well or badly for you.'],
]

function SummaryRow({ s }) {
  return (
    <div className="agent-summary">
      {SUMMARY_CELLS.map(([k, field, label, hint]) => (
        <div key={k} className="agent-summary-cell">
          <span className="num"><Count value={s[field] ?? 0} /></span>
          <span className="agent-summary-label">{label}</span>
          <span className="agent-summary-hint">{hint}</span>
        </div>
      ))}
    </div>
  )
}

function Narrative({ text }) {
  if (!text) return null
  return (
    <div className="agent-narrative">
      <p className="kicker">In plain terms</p>
      <p className="agent-narrative-body">{prose(text)}</p>
    </div>
  )
}

function Backlog({ items }) {
  if (!items || items.length === 0) return null
  const groups = ['answer_now', 'keep_watching', 'stay_quiet']
    .map((v) => [v, items.filter((i) => i.verdict === v)])
    .filter(([, list]) => list.length > 0)

  return (
    <section className="agent-block">
      <div className="agent-block-head">
        <p className="kicker">Open backlog</p>
        <p className="agent-block-sub">What the agent would do with each decision still waiting on you.</p>
      </div>
      {groups.map(([verdict, list]) => {
        const meta = VERDICT_META[verdict]
        return (
          <div key={verdict} className="agent-backlog-group">
            <div className="agent-backlog-grouphead">
              <span className={`agent-tag agent-tone-${meta.tone}`}>{meta.label}</span>
              <span className="agent-backlog-blurb">{meta.blurb}</span>
            </div>
            <ul className="agent-backlog-list">
              {list.map((i) => (
                <li key={i.id}>
                  <span className="agent-backlog-text">{prose(i.text)}</span>
                  <span className="agent-backlog-why">{prose(i.why)}</span>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </section>
  )
}

function EventLog({ events }) {
  if (!events || events.length === 0) {
    return <p className="empty-state">Nothing yet. Log a few decisions and let time pass.</p>
  }
  return (
    <section className="agent-block">
      <div className="agent-block-head">
        <p className="kicker">Recent activity</p>
        <p className="agent-block-sub">Every check-in, answer, and pattern — plus the last few loops closed.</p>
      </div>
      <ol className="agent-events">
        {events.map((e) => {
          const meta = EVENT_META[e.event_type] ?? { label: e.event_type, tone: 'neutral' }
          return (
            <li key={e.id} className="agent-event">
              <div className="agent-event-top">
                <span className={`agent-tag agent-tone-${meta.tone}`}>{meta.label}</span>
                <span className="agent-event-title">{prose(e.title)}</span>
                <span className="agent-event-time">{e.relative}</span>
              </div>
              {e.detail && <p className="agent-event-detail">{prose(e.detail)}</p>}
              {e.reasoning && <p className="agent-event-why">{prose(e.reasoning)}</p>}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

export default function AgentActivity({ refreshKey }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    setFailed(false)
    fetch(`${API_BASE}/agent/activity`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((d) => live && setData(d))
      .catch(() => live && setFailed(true))
    return () => {
      live = false
    }
  }, [refreshKey])

  if (failed) return <p className="empty-state">Could not load the agent activity.</p>
  if (!data) {
    return (
      <div className="agent-activity" aria-busy="true">
        <div className="section-head">
          <div className="skeleton skeleton-line" style={{ width: '45%', height: '1.3em' }} />
          <div className="skeleton skeleton-line" style={{ width: '90%' }} />
          <div className="skeleton skeleton-line" style={{ width: '72%' }} />
        </div>
        <div className="skeleton skeleton-block" style={{ height: 78, margin: 'var(--s5) 0' }} />
        <div className="skeleton skeleton-line" style={{ width: '38%', margin: 'var(--s5) 0 var(--s3)' }} />
        {[92, 84, 88, 76, 90].map((w, i) => (
          <div key={i} className="skeleton-card" style={{ marginBottom: 'var(--s2)', padding: '13px 15px' }}>
            <div className="skeleton skeleton-line" style={{ width: `${w}%` }} />
            <div className="skeleton skeleton-line" style={{ width: `${w - 22}%` }} />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="agent-activity">
      <div className="section-head">
        <p className="kicker">Agent</p>
        <h1>What Choicely handled on its own</h1>
        <p>
          Choicely doesn't wait to be asked. It answers the decisions your history has settled,
          circles back on the ones it can't, and tells you the patterns it finds —{' '}
          {data.llm ? 'with Claude driving the judgment calls.' : 'on plain rules until a Claude key is set.'}
        </p>
      </div>

      <Narrative text={data.narrative} />
      <SummaryRow s={data.summary} />
      <Backlog items={data.backlog} />
      <EventLog events={data.events} />
    </div>
  )
}
