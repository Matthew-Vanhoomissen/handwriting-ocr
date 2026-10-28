import { useEffect, useState } from 'react'
import { api } from './api.js'

// Pick or create an assignment, and manage its test cases.
// `onResponse(label, body)` feeds the Raw JSON panel in App.
export default function AssignmentSetup({ assignmentId, onSelect, onResponse }) {
  const [assignments, setAssignments] = useState(null) // null while loading
  const [detail, setDetail] = useState(null) // assignment with test_cases
  const [showCreate, setShowCreate] = useState(false)
  const [error, setError] = useState(null)

  async function call(label, fn) {
    setError(null)
    try {
      const res = await fn()
      onResponse(`${label} -> ${res.status}`, res.body)
      return res
    } catch (err) {
      setError(err.message)
      onResponse(`${label} (failed)`, err.body ?? null)
      return null
    }
  }

  async function loadAssignments() {
    const res = await call('GET /api/assignments', () => api.listAssignments())
    if (!res) return
    setAssignments(res.body)
    if (res.body.length === 0) setShowCreate(true)
    else if (assignmentId == null) onSelect(res.body[res.body.length - 1].id)
  }

  async function loadDetail(id) {
    const res = await call(`GET /api/assignments/${id}`, () => api.getAssignment(id))
    if (res) setDetail(res.body)
  }

  useEffect(() => {
    loadAssignments()
  }, [])

  useEffect(() => {
    setDetail(null)
    if (assignmentId != null) loadDetail(assignmentId)
  }, [assignmentId])

  async function handleCreate(fields) {
    const res = await call('POST /api/assignments', () => api.createAssignment(fields))
    if (!res) return false
    setAssignments((prev) => [...(prev ?? []), res.body])
    setShowCreate(false)
    onSelect(res.body.id)
    return true
  }

  async function handleAddTest(fields) {
    const res = await call(`POST /api/assignments/${assignmentId}/tests`, () =>
      api.addTestCase(assignmentId, fields)
    )
    if (!res) return false
    await loadDetail(assignmentId) // the POST returns only the new id
    return true
  }

  async function handleDeleteTest(id) {
    const res = await call(`DELETE /api/tests/${id}`, () => api.deleteTestCase(id))
    if (res) await loadDetail(assignmentId)
  }

  return (
    <div className="setup">
      <div className="panel">
        <h2>Assignment</h2>
        {assignments == null ? (
          <p className="placeholder">Loading assignments...</p>
        ) : (
          <div className="row">
            {assignments.length > 0 ? (
              <select
                value={assignmentId ?? ''}
                onChange={(e) => onSelect(Number(e.target.value))}
              >
                {assignments.map((a) => (
                  <option key={a.id} value={a.id}>
                    #{a.id} {a.title}
                  </option>
                ))}
              </select>
            ) : (
              <span className="placeholder">No assignments yet.</span>
            )}
            {!showCreate && (
              <button type="button" onClick={() => setShowCreate(true)}>
                New assignment
              </button>
            )}
          </div>
        )}

        {detail && !showCreate && (
          <div className="assignment-info">
            <div>
              Max points: <strong>{detail.max_points}</strong> | Output match:{' '}
              <strong>{detail.exact_match ? 'exact' : 'ignore trailing whitespace'}</strong>
            </div>
            {detail.prompt ? <p className="prompt">{detail.prompt}</p> : <p className="hint">No prompt.</p>}
          </div>
        )}

        {showCreate && (
          <CreateAssignmentForm
            onSubmit={handleCreate}
            onCancel={assignments?.length > 0 ? () => setShowCreate(false) : null}
          />
        )}

        {error && <div className="banner error">{error}</div>}
      </div>

      <div className="panel">
        <h2>Test cases</h2>
        {assignmentId == null ? (
          <p className="placeholder">Create or select an assignment first.</p>
        ) : detail == null ? (
          <p className="placeholder">Loading test cases...</p>
        ) : (
          <>
            {detail.test_cases.length === 0 ? (
              <p className="placeholder">No test cases yet. Uploads will get no suggested score until you add some.</p>
            ) : (
              <table className="tests">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Input (stdin)</th>
                    <th>Expected output</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {detail.test_cases.map((t, i) => (
                    <tr key={t.id}>
                      <td>{i + 1}</td>
                      <td>{t.input ? <pre>{t.input}</pre> : <span className="hint">(none)</span>}</td>
                      <td>
                        <pre>{t.expected_output}</pre>
                      </td>
                      <td>
                        <button type="button" onClick={() => handleDeleteTest(t.id)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <AddTestForm onSubmit={handleAddTest} />
          </>
        )}
      </div>
    </div>
  )
}

function CreateAssignmentForm({ onSubmit, onCancel }) {
  const [title, setTitle] = useState('')
  const [maxPoints, setMaxPoints] = useState('10')
  const [prompt, setPrompt] = useState('')
  const [exactMatch, setExactMatch] = useState(false)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    await onSubmit({ title: title.trim(), max_points: Number(maxPoints), prompt, exact_match: exactMatch })
    setSaving(false)
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Max points
        <input type="number" min="0" step="any" value={maxPoints} onChange={(e) => setMaxPoints(e.target.value)} required />
      </label>
      <label>
        Prompt
        <textarea rows="3" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </label>
      <label className="inline">
        <input type="checkbox" checked={exactMatch} onChange={(e) => setExactMatch(e.target.checked)} />
        Exact output match (off: trailing whitespace and blank lines are ignored)
      </label>
      <div className="row">
        <button type="submit" disabled={saving || !title.trim()}>
          {saving ? 'Creating...' : 'Create assignment'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}

function AddTestForm({ onSubmit }) {
  const [input, setInput] = useState('')
  const [expected, setExpected] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    const ok = await onSubmit({ input, expected_output: expected })
    setSaving(false)
    if (ok) {
      setInput('')
      setExpected('')
    }
  }

  return (
    <form className="add-test" onSubmit={handleSubmit}>
      <label>
        Input (stdin, optional)
        <textarea rows="3" value={input} onChange={(e) => setInput(e.target.value)} />
      </label>
      <label>
        Expected output
        <textarea rows="3" value={expected} onChange={(e) => setExpected(e.target.value)} />
      </label>
      <div>
        <button type="submit" disabled={saving}>
          {saving ? 'Adding...' : 'Add test case'}
        </button>
      </div>
    </form>
  )
}
