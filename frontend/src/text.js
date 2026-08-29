// Backend copy is written with ASCII "--" for portability. Render it with a
// real em dash. Also tidies a couple of other typographic rough edges.
export function prose(s) {
  if (typeof s !== 'string') return s
  return s
    .replace(/ -- /g, ' — ')
    .replace(/--/g, '—')
    .replace(/\.\.\./g, '…')
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// Backend timestamps are "YYYY-MM-DD HH:MM:SS". Render them the way a person
// reads a log: relative for the last week, then an absolute short date.
export function when(ts) {
  if (typeof ts !== 'string') return ''
  // Backend timestamps are local wall-clock ("YYYY-MM-DD HH:MM:SS", no zone);
  // parse them as local so "just logged" reads as "just now", not hours off.
  const d = new Date(ts.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return ts
  const hours = (Date.now() - d.getTime()) / 3.6e6
  if (hours < 1) return 'just now'
  if (hours < 24) return `${Math.round(hours)}h ago`
  const days = Math.round(hours / 24)
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days}d ago`
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`
}
