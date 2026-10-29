// Per-test results for a submission: input, expected vs actual output, the
// points each test is worth, and pass/fail, with the total at the bottom.
//
// The backend doesn't send a per-test score. It scores a submission as
// max_points * passed / total (backend/scoring.py), so each test is worth
// max_points / total. The total row uses the backend's suggested_score so the
// table always agrees with it, even where rounding the per-test shares wouldn't.

const VERSION_TITLES = { original: 'Transcribed code', corrected: 'Corrected code' }

const fmt = (n) => String(Math.round(n * 100) / 100)

export default function TestResults({ submission }) {
  const { status, test_results: results = [], assignment, suggested_score, score_reasoning } = submission
  const pending = status === 'queued' || status === 'processing'

  let body
  if (pending) body = <p className="placeholder">Tests run after transcription finishes.</p>
  else if (status === 'error') body = <p className="placeholder">No test results: processing failed.</p>
  else if (results.length === 0) body = <p className="placeholder">No test results: the assignment had no test cases when this submission was processed.</p>
  else {
    // One table per code version, original first ("corrected" appears once the syntax-fix step exists).
    const versions = ['original', 'corrected'].filter((v) => results.some((r) => r.version === v))
    body = versions.map((v) => (
      <ResultsTable
        key={v}
        title={versions.length > 1 ? VERSION_TITLES[v] : null}
        rows={results.filter((r) => r.version === v)}
        maxPoints={assignment?.max_points}
        total={v === 'original' ? suggested_score : null}
      />
    ))
  }

  return (
    <div className="panel results-panel">
      <h2>Test results</h2>
      {body}
      {!pending && score_reasoning && <p className="hint">{score_reasoning}</p>}
    </div>
  )
}

function ResultsTable({ title, rows, maxPoints, total }) {
  const share = maxPoints != null ? maxPoints / rows.length : null
  const passed = rows.filter((r) => r.passed).length
  const sum = total ?? (share != null ? share * passed : null)

  return (
    <>
      {title && <h3>{title}</h3>}
      <table className="tests results">
        <thead>
          <tr>
            <th>#</th>
            <th>Input</th>
            <th>Expected output</th>
            <th>Actual output</th>
            <th className="num">Score</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id} className={r.passed ? undefined : 'failed'}>
              <td>{i + 1}</td>
              <td><Output text={r.input} /></td>
              <td><Output text={r.expected_output} /></td>
              <td>
                <Output text={r.actual_output} />
                {r.error && <pre className="run-error">{r.error}</pre>}
              </td>
              <td className="num">{share != null ? `${r.passed ? fmt(share) : 0} / ${fmt(share)}` : '-'}</td>
              <td>
                <span className={r.passed ? 'result result-pass' : 'result result-fail'}>{r.passed ? 'Pass' : 'Fail'}</span>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={4} className="total-label">Total</td>
            <td className="num">
              <strong>{sum != null ? fmt(sum) : '-'}</strong>
              {maxPoints != null && ` / ${fmt(maxPoints)}`}
            </td>
            <td>
              {passed}/{rows.length} passed
            </td>
          </tr>
        </tfoot>
      </table>
    </>
  )
}

function Output({ text }) {
  if (text == null || text === '') return <span className="hint">(empty)</span>
  return <pre>{text}</pre>
}
