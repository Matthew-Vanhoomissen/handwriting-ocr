import { useEffect, useState } from 'react'
import { api, USE_MOCK } from './api.js'
import { SCENARIOS, setScenario } from './mockApi.js'
import CodeBlock from './components/CodeBlock.jsx'
import AssignmentPanel from './components/AssignmentPanel.jsx'
import AssignmentTabs from './components/AssignmentTabs.jsx'
import QuestionPanel from './components/QuestionPanel.jsx'
import SubmissionList from './components/SubmissionList.jsx'
import ConfirmDialog from './components/ConfirmDialog.jsx'
import TestResults from './components/TestResults.jsx'
import { questionLabel } from './format.js'

const POLL_MS = 1500
const DONE = ['ready', 'graded', 'error']

export default function App() {
  const [assignments, setAssignments] = useState(null) // null while loading
  const [assignmentsError, setAssignmentsError] = useState(null)
  const [creatingAssignment, setCreatingAssignment] = useState(false)
  const [assignmentId, setAssignmentId] = useState(null)
  const [detail, setDetail] = useState(null) // selected assignment with questions and their test cases
  const [detailError, setDetailError] = useState(null)
  const [detailVersion, setDetailVersion] = useState(0) // bump to re-fetch detail
  const [questionId, setQuestionId] = useState(null)
  const [creatingQuestion, setCreatingQuestion] = useState(false)
  const [file, setFile] = useState(null)
  const [label, setLabel] = useState('')
  const [uploading, setUploading] = useState(false)
  const [submissionId, setSubmissionId] = useState(null)
  const [submission, setSubmission] = useState(null)
  const [submissionVersion, setSubmissionVersion] = useState(0) // bump to re-fetch the open submission
  const [raw, setRaw] = useState(null) // { label, body } of the last backend response
  const [requestError, setRequestError] = useState(null)
  const [mockScenario, setMockScenario] = useState('ready_plain')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [listRefresh, setListRefresh] = useState(0)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  function clearSubmission() {
    setSubmission(null)
    setSubmissionId(null)
    setRequestError(null)
  }

  function selectAssignment(id) {
    // Submissions belong to a question in this assignment, so switching clears the current one.
    setCreatingAssignment(false)
    if (id === assignmentId) return
    clearSubmission()
    setCreatingQuestion(false)
    setQuestionId(null)
    setAssignmentId(id)
  }

  function selectQuestion(id) {
    setCreatingQuestion(false)
    if (id === questionId) return
    clearSubmission()
    setQuestionId(id)
  }

  const reloadDetail = () => setDetailVersion((v) => v + 1)

  // Load the tab list once; start on the newest assignment, or the create form if there are none.
  useEffect(() => {
    let cancelled = false
    api
      .listAssignments()
      .then((res) => {
        if (cancelled) return
        setRaw({ label: `GET /api/assignments -> ${res.status}`, body: res.body })
        setAssignments(res.body)
        if (res.body.length === 0) setCreatingAssignment(true)
        else setAssignmentId(res.body[res.body.length - 1].id)
      })
      .catch((err) => {
        if (cancelled) return
        setAssignmentsError(err.message)
        setRaw({ label: 'GET /api/assignments (failed)', body: err.body ?? null })
      })
    return () => {
      cancelled = true
    }
  }, [])

  function handleAssignmentCreated(row) {
    setAssignments((prev) => [...(prev ?? []), row])
    selectAssignment(row.id)
  }

  function handleAssignmentDeleted(id) {
    const remaining = assignments.filter((a) => a.id !== id)
    setAssignments(remaining)
    selectAssignment(remaining.length ? remaining[remaining.length - 1].id : null)
    if (remaining.length === 0) setCreatingAssignment(true)
  }

  // Load the selected assignment's questions and test cases. Clearing only on
  // an assignment switch (not on reloads) avoids flicker after edits.
  useEffect(() => {
    setDetail(null)
    setDetailError(null)
  }, [assignmentId])

  useEffect(() => {
    if (assignmentId == null) return
    let cancelled = false
    api
      .getAssignment(assignmentId)
      .then((res) => {
        if (cancelled) return
        setRaw({ label: `GET /api/assignments/${assignmentId} -> ${res.status}`, body: res.body })
        setDetail(res.body)
        setDetailError(null)
        // Keep the tab list's computed totals in step with question edits.
        const { id, question_count, total_points } = res.body
        setAssignments((prev) => prev?.map((a) => (a.id === id ? { ...a, question_count, total_points } : a)))
      })
      .catch((err) => {
        if (cancelled) return
        setDetailError(err.message)
        setRaw({ label: `GET /api/assignments/${assignmentId} (failed)`, body: err.body ?? null })
      })
    return () => {
      cancelled = true
    }
  }, [assignmentId, detailVersion])

  // Default to the first question whenever the current one isn't in this assignment.
  useEffect(() => {
    if (!detail) return
    if (!detail.questions.some((q) => q.id === questionId)) selectQuestion(detail.questions[0]?.id ?? null)
  }, [detail])

  function handleQuestionCreated(q) {
    selectQuestion(q.id)
    reloadDetail()
  }

  function handleQuestionDeleted(id) {
    // Move to the next question, or the previous one if it was last.
    const qs = detail.questions
    const i = qs.findIndex((q) => q.id === id)
    const neighbor = qs[i + 1] ?? qs[i - 1] ?? null
    selectQuestion(neighbor?.id ?? null)
    reloadDetail()
  }

  // Editing points or match mode re-scores the question's submissions, so
  // refresh the sidebar scores and the open review along with the detail.
  function handleQuestionEdited() {
    reloadDetail()
    setListRefresh((n) => n + 1)
    setSubmissionVersion((v) => v + 1)
  }

  const question = detail?.questions.find((q) => q.id === questionId) ?? null
  // Uploads go to the highlighted question; not while a create form is open.
  const uploadTarget = !creatingAssignment && !creatingQuestion ? question : null

  function selectSubmission(id) {
    if (id === submissionId) return
    clearSubmission()
    setSubmissionId(id)
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!file || uploadTarget == null) return
    setUploading(true)
    clearSubmission()
    const url = `/api/questions/${uploadTarget.id}/submissions`
    try {
      if (USE_MOCK) setScenario(mockScenario)
      const res = await api.createSubmission(uploadTarget.id, file, label.trim())
      setRaw({ label: `POST ${url} -> ${res.status}`, body: res.body })
      setLabel('')
      setSubmissionId(res.body.submission_ids[0])
      setListRefresh((n) => n + 1)
    } catch (err) {
      setRequestError(err.message)
      setRaw({ label: `POST ${url} (failed)`, body: err.body ?? null })
    } finally {
      setUploading(false)
    }
  }

  async function deleteSubmission() {
    const id = submission.id
    const url = `/api/submissions/${id}`
    setDeleting(true)
    try {
      const res = await api.deleteSubmission(id)
      setRaw({ label: `DELETE ${url} -> ${res.status}`, body: res.body })
      clearSubmission()
      setListRefresh((n) => n + 1)
    } catch (err) {
      setRequestError(err.message)
      setRaw({ label: `DELETE ${url} (failed)`, body: err.body ?? null })
    } finally {
      setDeleting(false)
      setConfirmingDelete(false)
    }
  }

  // Poll until the submission reaches a terminal status, then stop.
  useEffect(() => {
    if (submissionId == null) return
    let cancelled = false
    let timer

    async function poll() {
      try {
        const res = await api.getSubmission(submissionId)
        if (cancelled) return
        setRaw({ label: `GET /api/submissions/${submissionId} -> ${res.status}`, body: res.body })
        setSubmission(res.body)
        if (!DONE.includes(res.body.status)) timer = setTimeout(poll, POLL_MS)
      } catch (err) {
        if (cancelled) return
        setRequestError(err.message)
        setRaw({ label: `GET /api/submissions/${submissionId} (failed)`, body: err.body ?? null })
      }
    }

    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [submissionId, submissionVersion])

  return (
    <div className="page">
      <header>
        <h1>Grading Assistant</h1>
        {USE_MOCK && <span className="mock-badge">MOCK MODE - no backend calls</span>}
      </header>

      <AssignmentTabs
        assignments={assignments}
        selectedId={assignmentId}
        creating={creatingAssignment}
        error={assignmentsError}
        onSelect={selectAssignment}
        onNew={() => setCreatingAssignment(true)}
      />

      <div className={sidebarOpen ? 'layout' : 'layout sidebar-closed'}>
        <div className="main">
          <div className="setup">
            <AssignmentPanel
              detail={detail}
              assignmentId={assignmentId}
              creating={creatingAssignment}
              onCancelCreate={assignments?.length > 0 ? () => setCreatingAssignment(false) : null}
              onCreated={handleAssignmentCreated}
              onDeleted={handleAssignmentDeleted}
              questionId={questionId}
              creatingQuestion={creatingQuestion}
              onSelectQuestion={selectQuestion}
              onAddQuestion={() => setCreatingQuestion(true)}
              loadError={detailError}
              onResponse={(label, body) => setRaw({ label, body })}
            />
            <QuestionPanel
              detail={creatingAssignment ? null : detail}
              questionId={questionId}
              creating={creatingQuestion}
              creatingAssignment={creatingAssignment}
              onCancelCreate={() => setCreatingQuestion(false)}
              onCreated={handleQuestionCreated}
              onDeleted={handleQuestionDeleted}
              onChanged={reloadDetail}
              onEdited={handleQuestionEdited}
              onResponse={(label, body) => setRaw({ label, body })}
            />
          </div>

          <form className="upload" onSubmit={handleUpload}>
            <input
              type="file"
              accept=".jpg,.jpeg,.png,.webp"
              onChange={(e) => setFile(e.target.files[0] ?? null)}
            />
            {USE_MOCK && (
              <label>
                Mock scenario:{' '}
                <select value={mockScenario} onChange={(e) => setMockScenario(e.target.value)}>
                  {Object.entries(SCENARIOS).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <input
              className="label-input"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={file ? `Name (default: ${file.name.replace(/\.[^.]+$/, '')})` : 'Submission name (optional)'}
              aria-label="Submission name"
              title="Defaults to the file name. Use an anonymized label, not a student's real name."
            />
            <button type="submit" disabled={!file || uploading || uploadTarget == null}>
              {uploading ? 'Uploading...' : 'Upload'}
            </button>
            <span className="hint">
              {uploadTarget
                ? `Uploads to ${detail.title} > ${questionLabel(uploadTarget)}`
                : 'Select a question before uploading.'}
            </span>
          </form>

          {requestError && <div className="banner error">Request failed: {requestError}</div>}

          {!submission && !requestError && (
            <p className="empty">
              {submissionId != null
                ? `Loading submission #${submissionId}...`
                : 'Choose a photo of a handwritten program (jpg, png, or webp) and upload it, or pick a submission on the right.'}
            </p>
          )}

          {submission && <SubmissionView submission={submission} onDelete={() => setConfirmingDelete(true)} />}

          <ConfirmDialog
            open={confirmingDelete && submission != null}
            title="Delete submission?"
            busy={deleting}
            message={
              submission && (
                <>
                  <p>
                    This permanently deletes submission <strong>#{submission.id}</strong>
                    {submission.student_label && <> ({submission.student_label})</>}, including its uploaded
                    photo, transcription, test results, and scores.
                  </p>
                  {!DONE.includes(submission.status) && (
                    <p>It is still {submission.status}. Deleting it now discards any work in progress.</p>
                  )}
                  <p>This cannot be undone.</p>
                </>
              )
            }
            confirmLabel="Delete submission"
            onConfirm={deleteSubmission}
            onCancel={() => setConfirmingDelete(false)}
          />

          {raw && (
            <details className="raw">
              <summary>Raw JSON ({raw.label})</summary>
              <pre>{JSON.stringify(raw.body, null, 2)}</pre>
            </details>
          )}
        </div>

        <SubmissionList
          questionId={questionId}
          questionName={question ? questionLabel(question) : null}
          selectedId={submissionId}
          onSelect={selectSubmission}
          refreshKey={listRefresh}
          open={sidebarOpen}
          onToggle={() => setSidebarOpen((o) => !o)}
        />
      </div>
    </div>
  )
}

function SubmissionView({ submission, onDelete }) {
  const { id, student_label, status, transcription, flags, corrected_code, error_message, question } = submission
  const pending = !DONE.includes(status)
  const uncertainLines = (flags?.uncertain_lines ?? []).map((u) => u.line)
  const syntaxErrors = (flags?.static_flags ?? []).filter((f) => f.reason.startsWith('syntax error'))

  return (
    <section>
      <div className="status-row">
        Submission #{id}
        {student_label && ` (${student_label})`}: <span className={`status status-${status}`}>{status}</span>
        {question && <span className="hint">{questionLabel(question)}</span>}
        {pending && <span className="hint"> checking every {POLL_MS / 1000}s...</span>}
        <button type="button" className="danger" onClick={onDelete}>
          Delete submission
        </button>
      </div>
      {status === 'error' && (
        <div className="banner error">{error_message || 'Unknown error (no message from backend)'}</div>
      )}

      <div className="review">
        <div className="panel image-panel">
          <h2>Original photo</h2>
          <SubmissionImage src={api.imageUrl(id)} />
        </div>

        <div className="code-panels">
          <div className="panel">
            <h2>Transcription</h2>
            {syntaxErrors.map((f, i) => (
              <div key={i} className="banner warn">
                Line {f.line}: {f.reason}
              </div>
            ))}
            {transcription != null ? (
              <>
                <CodeBlock code={transcription} highlight={uncertainLines} />
                {uncertainLines.length > 0 && (
                  <p className="hint">Highlighted lines were marked uncertain by the model.</p>
                )}
              </>
            ) : (
              <p className="placeholder">
                {pending ? 'Waiting for transcription...' : 'No transcription returned.'}
              </p>
            )}
          </div>

          <div className="panel">
            <h2>Corrected code</h2>
            {corrected_code != null ? (
              <CodeBlock code={corrected_code} />
            ) : (
              <p className="placeholder">{pending ? 'Waiting...' : 'No corrected version generated.'}</p>
            )}
          </div>
        </div>
      </div>

      <TestResults submission={submission} />
    </section>
  )
}

function SubmissionImage({ src }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [src])
  if (failed) return <p className="placeholder">Image failed to load from {src}</p>
  return (
    <a href={src} target="_blank" rel="noreferrer">
      <img src={src} alt="Handwritten submission" onError={() => setFailed(true)} />
    </a>
  )
}
