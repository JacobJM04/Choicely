// Client-side Web Push wiring. Everything here is defensive: unsupported
// browsers, denied permission, and a server with push disabled all resolve
// to a quiet "unavailable" rather than throwing.
import { API_BASE } from './api'

export const pushSupported =
  typeof window !== 'undefined' &&
  'serviceWorker' in navigator &&
  'PushManager' in window &&
  'Notification' in window

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

export async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return null
  try {
    return await navigator.serviceWorker.register('/sw.js')
  } catch {
    return null
  }
}

export async function getPushState() {
  if (!pushSupported) return { supported: false, permission: 'unsupported', subscribed: false }
  const reg = await navigator.serviceWorker.ready.catch(() => null)
  const sub = reg ? await reg.pushManager.getSubscription() : null
  return {
    supported: true,
    permission: Notification.permission, // 'default' | 'granted' | 'denied'
    subscribed: !!sub,
  }
}

export async function enablePush() {
  if (!pushSupported) return { ok: false, reason: 'unsupported' }

  const cfg = await fetch(`${API_BASE}/push/config`)
    .then((r) => r.json())
    .catch(() => null)
  if (!cfg || !cfg.enabled || !cfg.public_key) return { ok: false, reason: 'server-disabled' }

  let permission
  try {
    permission = await Notification.requestPermission()
  } catch {
    return { ok: false, reason: 'denied' }
  }
  if (permission !== 'granted') return { ok: false, reason: permission }

  try {
    const reg = await navigator.serviceWorker.ready
    const sub =
      (await reg.pushManager.getSubscription()) ||
      (await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(cfg.public_key),
      }))

    const res = await fetch(`${API_BASE}/push/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscription: sub.toJSON() }),
    })
    if (!res.ok) return { ok: false, reason: 'save-failed' }
    return { ok: true }
  } catch {
    return { ok: false, reason: 'subscribe-failed' }
  }
}

export async function disablePush() {
  if (!pushSupported) return
  const reg = await navigator.serviceWorker.ready.catch(() => null)
  const sub = reg ? await reg.pushManager.getSubscription() : null
  if (!sub) return
  const { endpoint } = sub
  await sub.unsubscribe().catch(() => {})
  await fetch(`${API_BASE}/push/unsubscribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ endpoint }),
  }).catch(() => {})
}

export async function sendTestPush() {
  return fetch(`${API_BASE}/push/test`, { method: 'POST' })
    .then((r) => r.json())
    .catch(() => ({ delivered: 0 }))
}
