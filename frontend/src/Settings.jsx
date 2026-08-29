import { useEffect, useState } from 'react'
import { summarizeProfile } from './Onboarding'
import { NotificationsPanel } from './Notifications'
import { fetchCommunityStats, isContributing, setContributing } from './community'

function CommunityPanel() {
  const [on, setOn] = useState(isContributing())
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetchCommunityStats().then(setStats)
  }, [])

  function toggle() {
    const next = !on
    setOn(next)
    setContributing(next)
  }

  return (
    <div className="notif">
      <p className="kicker">Shared outcomes</p>
      <p className="notif-body">
        The population numbers Choicely quotes start from a reference dataset. Turning this on adds
        your outcomes — just the category and how it went, never the text — so those numbers drift
        toward what people actually report.
      </p>
      <div className="notif-row">
        <span className={`notif-status ${on ? 'on' : ''}`}>{on ? 'Sharing' : 'Not sharing'}</span>
        <button className="notif-btn" onClick={toggle}>
          {on ? 'Stop sharing' : 'Share my outcomes'}
        </button>
      </div>
      {stats && (
        <p className="notif-hint">
          {stats.total.toLocaleString()} outcomes in the pool across {stats.categories} categories
          {stats.contributed > 0 && ` · ${stats.contributed} from this device`}.
        </p>
      )}
    </div>
  )
}

export default function Settings({ profile, onRetake, onBack }) {
  return (
    <div className="centered-page">
      <div>
        <p className="kicker">Settings</p>
        <h2>{profile.name}</h2>
        <p className="page-sub">{summarizeProfile(profile)}</p>
        <button className="btn-primary" onClick={onRetake}>Retake the survey</button>
        <button className="btn-ghost" onClick={onBack}>Back</button>
        <NotificationsPanel />
        <CommunityPanel />
      </div>
    </div>
  )
}
