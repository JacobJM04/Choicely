import { useCallback, useEffect, useState } from 'react'
import './Notifications.css'
import {
  disablePush,
  enablePush,
  getPushState,
  pushSupported,
  sendTestPush,
} from './push'

const NUDGE_DISMISSED = 'choicely.notifyNudgeDismissed'

function useIsInstalled() {
  const [installed, setInstalled] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(display-mode: standalone)')
    const update = () => setInstalled(mq.matches || window.navigator.standalone === true)
    update()
    mq.addEventListener?.('change', update)
    return () => mq.removeEventListener?.('change', update)
  }, [])
  return installed
}

/**
 * Full control, shown in Settings. Handles every state: unsupported,
 * default, granted+subscribed, granted-not-subscribed, denied.
 */
export function NotificationsPanel() {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const installed = useIsInstalled()

  const refresh = useCallback(() => {
    getPushState().then(setState)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  if (!pushSupported) {
    return (
      <div className="notif">
        <p className="kicker">Check-in reminders</p>
        <p className="notif-body">
          This browser can’t deliver notifications. The check-in banner inside Choicely still works.
        </p>
      </div>
    )
  }

  if (!state) return null

  async function turnOn() {
    setBusy(true)
    setMsg('')
    const r = await enablePush()
    setBusy(false)
    if (r.ok) {
      setMsg('On. Choicely will notify you when a check-in comes due.')
    } else if (r.reason === 'denied') {
      setMsg('Blocked in your browser settings — you’ll need to re-allow notifications for this site.')
    } else if (r.reason === 'server-disabled') {
      setMsg('The server has push turned off right now.')
    } else if (r.reason === 'unsupported') {
      setMsg('Not supported in this browser.')
    } else {
      setMsg('Couldn’t turn it on. Try again.')
    }
    refresh()
  }

  async function turnOff() {
    setBusy(true)
    setMsg('')
    await disablePush()
    setBusy(false)
    setMsg('Off. You’ll still see check-ins when Choicely is open.')
    refresh()
  }

  async function test() {
    setBusy(true)
    const { delivered } = await sendTestPush()
    setBusy(false)
    setMsg(delivered ? 'Sent — check your notifications.' : 'Nothing delivered (no active subscription).')
  }

  const on = state.permission === 'granted' && state.subscribed
  const denied = state.permission === 'denied'

  return (
    <div className="notif">
      <p className="kicker">Check-in reminders</p>
      <p className="notif-body">
        When a decision’s check-in comes due, Choicely can notify you even with the app closed.
      </p>

      <div className="notif-row">
        <span className={`notif-status ${on ? 'on' : ''}`}>{on ? 'On' : denied ? 'Blocked' : 'Off'}</span>
        {on ? (
          <div className="notif-actions">
            <button className="notif-btn" onClick={test} disabled={busy}>
              Send test
            </button>
            <button className="notif-btn ghost" onClick={turnOff} disabled={busy}>
              Turn off
            </button>
          </div>
        ) : (
          <button className="notif-btn" onClick={turnOn} disabled={busy || denied}>
            {busy ? '…' : 'Turn on'}
          </button>
        )}
      </div>

      {msg && <p className="notif-msg">{msg}</p>}

      {!installed && (
        <p className="notif-hint">
          Tip: install Choicely (your browser’s “Add to Home Screen” / “Install”) so check-ins
          arrive like any other app’s.
        </p>
      )}
    </div>
  )
}

/**
 * A one-time, dismissible nudge on the timeline. Only appears when
 * notifications are supported, not yet decided, and there's something to
 * be reminded about.
 */
export function NotifyNudge({ decisionCount }) {
  const [state, setState] = useState(null)
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(NUDGE_DISMISSED) === '1'
    } catch {
      return false
    }
  })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getPushState().then(setState)
  }, [])

  if (
    dismissed ||
    !pushSupported ||
    !state ||
    state.permission !== 'default' ||
    state.subscribed ||
    decisionCount < 1
  ) {
    return null
  }

  function close() {
    setDismissed(true)
    try {
      localStorage.setItem(NUDGE_DISMISSED, '1')
    } catch {
      /* private mode — fine, it just re-shows next visit */
    }
  }

  async function turnOn() {
    setBusy(true)
    const r = await enablePush()
    setBusy(false)
    if (r.ok || r.reason === 'denied') close()
    else setState(await getPushState())
  }

  return (
    <div className="notif-nudge">
      <div className="notif-nudge-text">
        <strong>Let Choicely reach you.</strong> Get a notification when a check-in comes due —
        not only when the app is open.
      </div>
      <div className="notif-nudge-actions">
        <button className="notif-btn" onClick={turnOn} disabled={busy}>
          {busy ? '…' : 'Turn on'}
        </button>
        <button className="notif-nudge-x" onClick={close} aria-label="Dismiss">
          ✕
        </button>
      </div>
    </div>
  )
}
