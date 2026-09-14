import { useEffect, useRef, useState } from 'react'

// One place to ask "should this move?" — honoured by every helper here and
// mirrored by a `* { transition: none }` rule in index.css.
export const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3)

/**
 * Animate a number toward `target` on mount and on every change. Returns the
 * current value, already rounded to `decimals`. Snaps instantly when the
 * viewer has asked for reduced motion.
 */
export function useCountUp(target, { duration = 750, decimals = 0 } = {}) {
  const value = Number.isFinite(Number(target)) ? Number(target) : 0
  const [display, setDisplay] = useState(() => (prefersReducedMotion() ? value : 0))
  const fromRef = useRef(prefersReducedMotion() ? value : 0)
  const rafRef = useRef(0)

  useEffect(() => {
    if (prefersReducedMotion()) {
      fromRef.current = value
      setDisplay(value)
      return
    }
    const from = fromRef.current
    if (from === value) return
    const start = performance.now()
    cancelAnimationFrame(rafRef.current)

    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      setDisplay(from + (value - from) * easeOutCubic(t))
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = value
      }
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [value, duration])

  const factor = 10 ** decimals
  return Math.round(display * factor) / factor
}

/** A number that ticks up to its value. Drop-in for a bare `{n}` in the tree. */
export function Count({ value, decimals = 0, suffix = '', duration }) {
  const n = useCountUp(value, { duration, decimals })
  return (
    <>
      {n.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </>
  )
}
