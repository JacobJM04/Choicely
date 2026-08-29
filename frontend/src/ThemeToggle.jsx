import { useEffect, useState } from 'react'

const KEY = 'choicely-theme'
const THEMES = ['system', 'light', 'dark']

function read() {
  try {
    const stored = localStorage.getItem(KEY)
    return THEMES.includes(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

function apply(theme) {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

// Apply the saved theme before first paint so there's no flash of the default.
apply(read())

const NEXT = { system: 'light', light: 'dark', dark: 'system' }
const ICON = { system: '◐', light: '☀', dark: '☾' }
const TITLE = { system: 'Theme: system', light: 'Theme: light', dark: 'Theme: dark' }

export default function ThemeToggle() {
  const [theme, setTheme] = useState(read)

  useEffect(() => {
    apply(theme)
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* private mode / storage disabled — theme still applies for this session */
    }
  }, [theme])

  return (
    <button
      className="icon-btn"
      onClick={() => setTheme((t) => NEXT[t])}
      title={TITLE[theme]}
      aria-label={TITLE[theme]}
    >
      {ICON[theme]}
    </button>
  )
}
