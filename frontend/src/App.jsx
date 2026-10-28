import { useEffect, useState } from 'react'
import { api, USE_MOCK } from './api.js'
import { SCENARIOS, setScenario } from './mockApi.js'
import CodeBlock from './CodeBlock.jsx'
import AssignmentSetup from './AssignmentSetup.jsx'

const POLL_MS = 1500
const DONE = ['ready', 'graded', 'error']

export default function App() {
  const [assignmentId, setAssignmentId] = useState(null)
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [submissionId, setSubmissionId] = useState(null)
  const [submission, setSubmission] = useState(null)
  const [raw, setRaw] = useState(null) // { label, body } of the last backend response
  const [requestError, setRequestError] = useState(null)
  const [mockScenario, setMockScenario] = useState('ready_plain')

  function clearSubmission() {
    setSubmission(null)
    setSubmissionId(null)
    setRequestError(null)
  }

  function selectAssignment(id) {
    // Submissions belong to an assignment, so switching clears the current one.
    clearSubmission()
    setAssignmentId(id)
  }

  async function handleUpload(e) {
    e.preventDefault()
    if (!file || assignmentId == null) return
    setUploading(true)
    clearSubmission()
    const url = `/api/assignments/${assignmentId}/submissions`
    try {
      if (USE_MOCK) setScenario(mockScenario)
      const res = await api.createSubmission(assignmentId, file)
      setRaw({ label: `POST ${url} -> ${res.status}`, body: res.body })
      setSubmissionId(res.body.submission_ids[0])
    } catch (err) {
      setRequestError(err.message)
      setRaw({ label: `POST ${url} (failed)`, body: err.body ?? null })
    } finally {
      setUploading(false)
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
  }, [submissionId])

  return (
    <div className="page">
      <header>
        <h1>Grading Assistant</h1>
        {USE_MOCK && <span className="mock-badge">MOCK MODE - no backend calls</span>}
      </header>

      <AssignmentSetup
        assignmentId={assignmentId}
        onSelect={selectAssignment}
        onResponse={(label, body) => setRaw({ label, body })}
      />

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
        <button type="submit" disabled={!file || uploading || assignmentId == null}>
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
        {assignmentId == null && <span className="hint">Select an assignment before uploading.</span>}
      </form>

      {requestError && <div className="banner error">Request failed: {requestError}</div>}

      {!submission && !requestError && (
        <p className="empty">
          {submissionId != null
            ? `Uploaded. Loading submission #${submissionId}...`
            : 'Choose a photo of a handwritten program (jpg, png, or webp) and upload it.'}
        </p>
      )}

      {submission && <SubmissionView submission={submission} />}

      {raw && (
        <details className="raw">
          <summary>Raw JSON ({raw.label})</summary>
          <pre>{JSON.stringify(raw.body, null, 2)}</pre>
        </details>
      )}
    </div>
  )
}

function SubmissionView({ submission }) {
  const { id, student_label, status, transcription, flags, corrected_code, error_message } = submission
  const pending = !DONE.includes(status)
  const uncertainLines = (flags?.uncertain_lines ?? []).map((u) => u.line)
  const syntaxErrors = (flags?.static_flags ?? []).filter((f) => f.reason.startsWith('syntax error'))

  return (
    <section>
      <div className="status-row">
        Submission #{id}
        {student_label && ` (${student_label})`}: <span className={`status status-${status}`}>{status}</span>
        {pending && <span className="hint"> checking every {POLL_MS / 1000}s...</span>}
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
