import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ConfirmDialog from './ConfirmDialog.jsx'

// Details, create form, and delete for the assignment chosen in the tab bar,
// plus its test cases. App owns the assignment list; this reports changes to
// it through onCreated/onDeleted. `onResponse(label, body)` feeds Raw JSON.
export default function AssignmentSetup({
  assignmentId,
  creating,
  onCancelCreate,
  onCreated,
  onDeleted,
  onResponse,
}) {
  const [detail, setDetail] = useState(null) // assignment with test_cases
  const [error, setError] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null) // { id, title, tests, submissions }
  const [deleting, setDeleting] = useState(false)

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

  async function loadDetail(id) {
    const res = await call(`GET /api/assignments/${id}`, () => api.getAssignment(id))
    if (res) setDetail(res.body)
  }

  useEffect(() => {
    setDetail(null)
    if (assignmentId != null) loadDetail(assignmentId)
  }, [assignmentId])

  async function handleCreate(fields) {
    const res = await call('POST /api/assignments', () => api.createAssignment(fields))
    if (!res) return false
    onCreated(res.body)
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

  // Count the submissions first so the confirmation says exactly what will go.
  async function askDeleteAssignment() {
    let submissions = null
    try {
      submissions = (await api.listSubmissions(detail.id)).body.length
    } catch {
      // Count is informational; still allow the delete.
    }
    setPendingDelete({ id: detail.id, title: detail.title, tests: detail.test_cases.length, submissions })
  }

  async function confirmDeleteAssignment() {
    const { id } = pendingDelete
    setDeleting(true)
    const res = await call(`DELETE /api/assignments/${id}`, () => api.deleteAssignment(id))
    setDeleting(false)
    setPendingDelete(null)
    if (res) onDeleted(id)
  }

  return (
    <div className="setup">
      <div className="panel">
        <h2>{creating ? 'New assignment' : 'Assignment'}</h2>
        {!creating &&
          (assignmentId == null ? (
            <p className="placeholder">No assignment selected. Pick a tab above or create one.</p>
          ) : detail == null ? (
            <p className="placeholder">Loading assignment...</p>
          ) : (
            <div className="row">
              <strong className="assignment-title">{detail.title}</strong>
              <span className="hint">#{detail.id}</span>
              <button type="button" className="danger push-right" onClick={askDeleteAssignment}>
                Delete assignment
              </button>
            </div>
          ))}

        <ConfirmDialog
          open={pendingDelete != null}
          title="Delete assignment?"
          busy={deleting}
          message={
            pendingDelete && (
              <>
                <p>
                  This permanently deletes <strong>{pendingDelete.title}</strong> along with:
                </p>
                <ul>
                  <li>
                    {pendingDelete.tests} test case{pendingDelete.tests === 1 ? '' : 's'}
                  </li>
                  <li>
                    {pendingDelete.submissions ?? 'all'} submission{pendingDelete.submissions === 1 ? '' : 's'}, with
                    their uploaded photos, test results, and scores
                  </li>
                </ul>
                <p>This cannot be undone.</p>
              </>
            )
          }
          confirmLabel="Delete assignment"
          onConfirm={confirmDeleteAssignment}
          onCancel={() => setPendingDelete(null)}
        />

        {detail && !creating && (
          <div className="assignment-info">
            <div>
              Max points: <strong>{detail.max_points}</strong> | Output match:{' '}
              <strong>{detail.exact_match ? 'exact' : 'ignore trailing whitespace'}</strong>
            </div>
            {detail.prompt ? <p className="prompt">{detail.prompt}</p> : <p className="hint">No prompt.</p>}
          </div>
        )}

        {creating && <CreateAssignmentForm onSubmit={handleCreate} onCancel={onCancelCreate} />}

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
