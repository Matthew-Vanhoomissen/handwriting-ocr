import { useEffect, useRef } from 'react'
import { fmtPoints } from '../format.js'

// Horizontal tab bar for switching assignments. The tabs scroll sideways when
// there are more than fit (the active one is scrolled into view); "+ New" sits
// outside the scrolling part so it is always visible.
export default function AssignmentTabs({ assignments, selectedId, creating, error, onSelect, onNew }) {
  const activeRef = useRef(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [selectedId, creating, assignments])

  return (
    <div className="tabs-bar">
      <nav className="tabs" aria-label="Assignments">
        {error ? (
          <div className="banner error">{error}</div>
        ) : assignments == null ? (
          <span className="placeholder tabs-loading">Loading assignments...</span>
        ) : (
          assignments.map((a) => {
            const active = a.id === selectedId && !creating
            return (
              <button
                key={a.id}
                type="button"
                ref={active ? activeRef : null}
                className={active ? 'tab active' : 'tab'}
                aria-current={active ? 'page' : undefined}
                title={`#${a.id} ${a.title} (${a.question_count} question${a.question_count === 1 ? '' : 's'}, ${fmtPoints(a.total_points)} pts)`}
                onClick={() => onSelect(a.id)}
              >
                {a.title}
              </button>
            )
          })
        )}
      </nav>
      <button type="button" className={creating ? 'tab tab-new active' : 'tab tab-new'} onClick={onNew}>
        + New assignment
      </button>
    </div>
  )
}
