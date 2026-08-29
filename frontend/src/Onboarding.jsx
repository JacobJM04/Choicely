import { useEffect, useState } from 'react'
import { API_BASE } from './api'
import { prose } from './text'

const STEPS = ['You', 'Style', 'Details']

function Stepper({ current }) {
  return (
    <ol className="stepper">
      {STEPS.map((label, i) => (
        <li key={label} className={i === current ? 'now' : i < current ? 'done' : ''}>
          <span className="stepper-dot">{i < current ? '✓' : i + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  )
}

function NameStep({ name, setName, onContinue }) {
  return (
    <div className="onb">
      <div className="onb-brand">
        <span className="brand-mark" />
        Choicely
      </div>
      <h2>A second brain for the decisions you're tired of carrying.</h2>
      <p className="page-sub">
        Log an everyday decision. Choicely estimates how much you'll regret it, answers the easy
        ones outright, and checks back later to see how it went.
      </p>
      <label className="onb-label">What should it call you?</label>
      <input
        type="text"
        className="field"
        placeholder="Your name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter' && name.trim()) onContinue()
        }}
      />
      <button className="btn-primary" disabled={!name.trim()} onClick={onContinue}>
        Get started
      </button>
      <p className="onb-fineprint">
        No account, no password. Everything stays in this browser and on your machine.
      </p>
    </div>
  )
}

function SurveyStep({ questions, answers, setAnswer, onSubmit, onBack, submitting, error, step, title, subtitle, buttonLabel }) {
  const allAnswered = questions.length > 0 && questions.every((q) => answers[q.id] !== undefined)
  return (
    <div className="onb">
      <Stepper current={step} />
      <h2>{title}</h2>
      <p className="page-sub">{subtitle}</p>
      <div className="survey-list">
        {questions.map((q) => (
          <div key={q.id}>
            <p className="survey-q">{prose(q.question)}</p>
            <div className="survey-options">
              {q.options.map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  className={`survey-option${answers[q.id] === opt.value ? ' selected' : ''}`}
                  onClick={() => setAnswer(q.id, opt.value)}
                >
                  {prose(opt.label)}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="onb-actions">
        {onBack && (
          <button className="btn-ghost" onClick={onBack}>
            Back
          </button>
        )}
        <button className="btn-primary" disabled={!allAnswered || submitting} onClick={onSubmit}>
          {submitting ? 'Saving…' : buttonLabel}
        </button>
      </div>
    </div>
  )
}

const CONFLICT_PHRASE = {
  avoidant: 'tends to avoid conflict',
  direct: 'is direct about conflict',
  accommodating: 'tends to smooth things over in conflict',
  competitive: 'holds its ground in conflict',
}

export function summarizeProfile(saved) {
  const bits = [`You're a ${saved.planning_label} decider`]

  if (typeof saved.risk_tolerance_financial === 'number') {
    if (saved.risk_tolerance_financial <= 0.25) bits.push('risk-averse financially')
    else if (saved.risk_tolerance_financial >= 0.75) bits.push('financially bold')
  }
  if (typeof saved.risk_tolerance_social === 'number') {
    if (saved.risk_tolerance_social <= 0.25) bits.push('cautious in social situations')
    else if (saved.risk_tolerance_social >= 0.75) bits.push('a social risk-taker')
  }
  if (saved.conflict_style && CONFLICT_PHRASE[saved.conflict_style]) {
    bits.push(CONFLICT_PHRASE[saved.conflict_style])
  }

  const [first, ...rest] = bits
  const sentence = rest.length ? `${first}, who leans ${rest.join(' and ')}.` : `${first}.`
  return `${sentence} Choicely will factor that into what it suggests.`
}

function ProfileSummaryStep({ saved, onContinue }) {
  return (
    <div className="onb">
      <Stepper current={3} />
      <h2>You're set, {saved.name}.</h2>
      <p className="page-sub">{summarizeProfile(saved)}</p>
      <button className="btn-primary" onClick={onContinue}>
        Go to Choicely
      </button>
    </div>
  )
}

export default function Onboarding({ onComplete, initialName = '' }) {
  const [step, setStep] = useState('name')
  const [name, setName] = useState(initialName)
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [personalityQuestions, setPersonalityQuestions] = useState([])
  const [personalityAnswers, setPersonalityAnswers] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/survey-questions`)
      .then((res) => res.json())
      .then(setQuestions)
      .catch(() => setError('Could not load the survey. Try refreshing.'))
    fetch(`${API_BASE}/personality-questions`)
      .then((res) => res.json())
      .then(setPersonalityQuestions)
      .catch(() => setError('Could not load the survey. Try refreshing.'))
  }, [])

  function setAnswer(questionId, value) {
    setAnswers((prev) => ({ ...prev, [questionId]: value }))
  }

  function setPersonalityAnswer(questionId, value) {
    setPersonalityAnswers((prev) => ({ ...prev, [questionId]: value }))
  }

  async function handleSubmit() {
    setSubmitting(true)
    setError('')
    try {
      const orderedAnswers = questions.map((q) => answers[q.id])
      const res = await fetch(`${API_BASE}/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          answers: orderedAnswers,
          personality_answers: personalityAnswers,
        }),
      })
      if (!res.ok) throw new Error('Request failed')
      const savedProfile = await res.json()
      setSaved(savedProfile)
      setStep('summary')
    } catch {
      setError('Something went wrong saving your answers. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="centered-page">
      {step === 'name' && (
        <NameStep name={name} setName={setName} onContinue={() => setStep('survey')} />
      )}
      {step === 'survey' && (
        <SurveyStep
          step={1}
          questions={questions}
          answers={answers}
          setAnswer={setAnswer}
          onSubmit={() => setStep('personality')}
          onBack={() => setStep('name')}
          submitting={false}
          error={error}
          title="How you tend to decide"
          subtitle="Five quick questions. This lets Choicely make better guesses before it knows your history — there are no right answers."
          buttonLabel="Continue"
        />
      )}
      {step === 'personality' && (
        <SurveyStep
          step={2}
          questions={personalityQuestions}
          answers={personalityAnswers}
          setAnswer={setPersonalityAnswer}
          onSubmit={handleSubmit}
          onBack={() => setStep('survey')}
          submitting={submitting}
          error={error}
          title="A bit more about you"
          subtitle="This shapes the tone and framing of what Choicely suggests. Still no right answers."
          buttonLabel="Finish"
        />
      )}
      {step === 'summary' && saved && (
        <ProfileSummaryStep saved={saved} onContinue={() => onComplete(saved)} />
      )}
    </div>
  )
}
