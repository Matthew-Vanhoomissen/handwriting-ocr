// Display helpers shared by several components.

// Question titles are optional (the backend allows ''), so fall back to the position.
export function questionLabel(q) {
  if (!q) return ''
  return q.title ? `Q${q.position}. ${q.title}` : `Question ${q.position}`
}

// Points like 10.0 or 2.3333 -> "10", "2.33".
export function fmtPoints(n) {
  return String(Math.round(Number(n) * 100) / 100)
}
