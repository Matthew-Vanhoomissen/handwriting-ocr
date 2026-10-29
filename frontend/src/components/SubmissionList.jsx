import { useEffect, useState } from 'react'
import { api } from '../api.js'

const REFRESH_MS = 3000
const PENDING = ['queued', 'processing']

// Right-hand panel listing the selected assignment's submissions. Refreshes
// while anything is still queued or processing; `refreshKey` forces a reload
// (e.g. after an upload). List responses are kept out of the Raw JSON panel so
// background refreshes don't replace the submission being debugged.
export default function SubmissionList({ assignmentId, selectedId, onSelect, refreshKey, open, onToggle }) {
  const [rows, setRows] = useState(null) // null while loading
  const [error, setError] = useState(null)

  useEffect(() => {
    setRows(null)
    setError(null)
    if (assignmentId == null) return
    let cancelled = false
    let timer

    async function load() {
      try {
        const res = await api.listSubmissions(assignmentId)
        if (cancelled) return
        setRows(res.body)
        setError(null)
        if (res.body.some((s) => PENDING.includes(s.status))) timer = setTimeout(load, REFRESH_MS)
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }

    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [assignmentId, refreshKey])

  if (!open) {
    return (
      <aside className="sidebar collapsed">
        <button type="button" className="sidebar-tab" onClick={onToggle} title="Show submissions">
          Submissions{rows ? ` (${rows.length})` : ''}
        </button>
      </aside>
    )
  }

  return (
    <aside className="sidebar panel">
      <div className="sidebar-header">
        <h2>Submissions{rows ? ` (${rows.length})` : ''}</h2>
        <button type="button" onClick={onToggle} title="Hide submissions">
          Hide
        </button>
      </div>

      {assignmentId == null ? (
        <p className="placeholder">Select an assignment.</p>
      ) : error ? (
        <div className="banner error">{error}</div>
      ) : rows == null ? (
        <p className="placeholder">Loading...</p>
      ) : rows.length === 0 ? (
        <p className="placeholder">No submissions yet.</p>
      ) : (
        <ul className="submission-list">
          {rows.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className={s.id === selectedId ? 'submission-item selected' : 'submission-item'}
                onClick={() => onSelect(s.id)}
                title={s.error_message ?? undefined}
              >
                <span className="item-top">
                  <span className="item-label">{s.student_label}</span>
                  <span className={`status status-${s.status}`}>{s.status}</span>
                </span>
                <span className="item-meta">
                  #{s.id}
                  {s.final_score != null
                    ? ` | final ${s.final_score}`
                    : s.suggested_score != null
                      ? ` | suggested ${s.suggested_score}`
                      : ''}
                  {s.verdict && ` | ${s.verdict}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
