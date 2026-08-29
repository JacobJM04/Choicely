import { summarizeProfile } from './Onboarding'
import { NotificationsPanel } from './Notifications'

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
      </div>
    </div>
  )
}
