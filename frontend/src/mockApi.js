// In-browser stand-in for the Flask API. Responses match the contract in
// CLAUDE.md section 12 (which mirrors backend/app.py): assignments hold
// questions, and each question has its own points, test cases, and
// submissions. Each upload walks queued -> processing -> final, where the
// final state comes from the scenario picked in the UI. Data lives in memory
// and resets on reload.

const QUEUED_MS = 2500
const PROCESSING_MS = 5000
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']

export const SCENARIOS = {
  ready_plain: 'ready, no corrected code',
  ready_corrected: 'ready, syntax error + corrected code',
  error: 'error',
}

const IMAGES = {
  ready_plain: '/mock/sample-1.svg',
  ready_corrected: '/mock/sample-2.svg',
  error: '/mock/sample-1.svg',
}

const FINAL = {
  ready_plain: {
    status: 'ready',
    transcription: 'def add(a, b):\n    return a + b\n\nprint(add(2, 3))\n',
    corrected_code: null,
    flags: {
      uncertain_lines: [
        { line: 2, chosen: '    return a + b', alternative: '    return a + 6', reason: 'b and 6 look alike' },
      ],
      static_flags: [],
    },
    error_message: null,
    // Ignores stdin and always prints 5, so it passes some tests and fails others.
    run: () => ({ actual_output: '5\n', error: null }),
  },
  ready_corrected: {
    status: 'ready',
    transcription:
      'def average(nums)\n    total = 0\n    for n in nums:\n        total += n\n    return total / len(nums)\n\nprint(average([1, 2, 3]))\n',
    corrected_code:
      'def average(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total / len(nums)\n\nprint(average([1, 2, 3]))\n',
    flags: {
      uncertain_lines: [
        { line: 1, chosen: 'def average(nums)', alternative: 'def average(nums):', reason: 'faint mark after )' },
        { line: 4, chosen: '        total += n', alternative: '        total + n', reason: 'unclear = sign' },
      ],
      static_flags: [{ line: 1, reason: "syntax error: expected ':'" }],
    },
    error_message: null,
    // The original transcription doesn't parse, so every test fails the way the sandbox reports it.
    run: () => ({
      actual_output: '',
      error: '  File "/code/main.py", line 1\n    def average(nums)\n                     ^\nSyntaxError: expected \':\'',
    }),
  },
  error: {
    status: 'error',
    transcription: null,
    corrected_code: null,
    flags: null,
    error_message: 'RateLimitError: model API returned 429 (rate limited)',
    run: null,
  },
}

const PENDING = {
  transcription: null,
  corrected_code: null,
  flags: null,
  error_message: null,
  run: null,
}

// Same comparison as backend/sandbox.py outputs_match: unless exact, ignore
// trailing whitespace on each line and trailing blank lines.
function outputsMatch(actual, expected, exact) {
  if (exact) return actual === expected
  const norm = (s) => s.replace(/\r\n/g, '\n').split('\n').map((l) => l.trimEnd()).join('\n').replace(/\n+$/, '')
  return norm(actual) === norm(expected)
}

// In-memory tables, mirroring backend/db.py. Booleans are stored as 0/1 like SQLite.
const assignments = new Map()
const questions = new Map()
const testCases = new Map()
const submissions = new Map() // id -> { createdAt, scenario, questionId, label }
let nextAssignmentId = 1
let nextQuestionId = 1
let nextTestId = 1
let nextSubmissionId = 7
let scenario = 'ready_plain'

const questionsOf = (assignmentId) =>
  [...questions.values()].filter((q) => q.assignment_id === assignmentId).sort((a, b) => a.position - b.position || a.id - b.id)
const testsOf = (questionId) => [...testCases.values()].filter((t) => t.question_id === questionId)

// Assignment row plus the computed totals the backend adds (ASSIGNMENT_SELECT).
function assignmentRow(a) {
  const qs = questionsOf(a.id)
  return { ...a, question_count: qs.length, total_points: qs.reduce((sum, q) => sum + q.max_points, 0) }
}

const questionWithTests = (q) => ({ ...q, test_cases: testsOf(q.id) })

function insertAssignment({ title, language = 'python' }) {
  const row = { id: nextAssignmentId++, title, language }
  assignments.set(row.id, row)
  return row
}

function insertQuestion(assignmentId, { max_points, title = '', prompt = '', exact_match = false, position = null }) {
  const pos = position ?? questionsOf(assignmentId).reduce((m, q) => Math.max(m, q.position), 0) + 1
  const row = {
    id: nextQuestionId++,
    assignment_id: assignmentId,
    position: pos,
    title,
    prompt,
    max_points: Number(max_points),
    exact_match: exact_match ? 1 : 0,
  }
  questions.set(row.id, row)
  return row
}

function insertTestCase(questionId, { input = '', expected_output }) {
  const row = { id: nextTestId++, question_id: questionId, input, expected_output }
  testCases.set(row.id, row)
  return row
}

// Seed one assignment with three questions (one untitled, to exercise the
// "Question N" fallback) and some finished submissions.
const seeded = insertAssignment({ title: 'Homework 1 (mock)' })
const q1 = insertQuestion(seeded.id, { title: 'Add two numbers', prompt: 'Read two ints on one line, print their sum.', max_points: 10 })
insertTestCase(q1.id, { input: '2 3\n', expected_output: '5\n' })
insertTestCase(q1.id, { input: '-1 1\n', expected_output: '0\n' })
const q2 = insertQuestion(seeded.id, { title: 'Average of a list', prompt: 'Print the average of [1, 2, 3].', max_points: 5 })
insertTestCase(q2.id, { input: '', expected_output: '2.0\n' })
insertQuestion(seeded.id, { title: '', prompt: '', max_points: 2 })
for (const [label, name, questionId] of [
  ['sample_01', 'ready_plain', q1.id],
  ['sample_03', 'error', q1.id],
  ['sample_02', 'ready_corrected', q2.id],
]) {
  submissions.set(nextSubmissionId++, { createdAt: 0, scenario: name, questionId, label })
}

export function setScenario(name) {
  scenario = name
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms))

function fail(method, url, status, error) {
  const err = new Error(`${method} ${url} failed: HTTP ${status} - ${error} (mock)`)
  err.body = { error }
  return err
}

function or404(table, method, url, id) {
  const row = table.get(Number(id))
  if (!row) throw fail(method, url, 404, 'Not Found')
  return row
}

// Delete the submissions matching `pred`, like db._delete_submissions_where.
function deleteSubmissionsWhere(pred) {
  for (const [id, s] of submissions) if (pred(s)) submissions.delete(id)
}

// Assignments

export async function listAssignments() {
  await delay(100)
  return { status: 200, body: [...assignments.values()].map(assignmentRow) }
}

export async function getAssignment(id) {
  await delay(100)
  const a = or404(assignments, 'GET', `/api/assignments/${id}`, id)
  return { status: 200, body: { ...assignmentRow(a), questions: questionsOf(a.id).map(questionWithTests) } }
}

export async function createAssignment(fields) {
  await delay(150)
  if (!fields.title) throw fail('POST', '/api/assignments', 400, 'title is required')
  const a = insertAssignment(fields)
  return { status: 201, body: { ...assignmentRow(a), questions: [] } }
}

// Like the backend: removes everything under the assignment, and returns 204
// even if the id doesn't exist.
export async function deleteAssignment(id) {
  await delay(150)
  const assignmentId = Number(id)
  const qids = new Set(questionsOf(assignmentId).map((q) => q.id))
  deleteSubmissionsWhere((s) => qids.has(s.questionId))
  for (const [tid, t] of testCases) if (qids.has(t.question_id)) testCases.delete(tid)
  for (const qid of qids) questions.delete(qid)
  assignments.delete(assignmentId)
  return { status: 204, body: null }
}

// Questions

export async function createQuestion(assignmentId, fields) {
  await delay(150)
  const url = `/api/assignments/${assignmentId}/questions`
  or404(assignments, 'POST', url, assignmentId)
  if (fields.max_points == null || fields.max_points === '' || Number.isNaN(Number(fields.max_points))) {
    throw fail('POST', url, 400, 'max_points must be a number')
  }
  if (fields.position != null && !Number.isInteger(fields.position)) throw fail('POST', url, 400, 'position must be an integer')
  return { status: 201, body: questionWithTests(insertQuestion(Number(assignmentId), fields)) }
}

// Like the backend's PATCH: only title, prompt, max_points, exact_match are
// read; other keys are ignored. Mock test results are computed on read, so
// submissions re-score on their own, which matches the backend's rescore.
export async function updateQuestion(id, fields) {
  await delay(150)
  const url = `/api/questions/${id}`
  const q = or404(questions, 'PATCH', url, id)
  const changes = {}
  for (const name of ['title', 'prompt']) {
    if (name in fields) {
      if (typeof fields[name] !== 'string') throw fail('PATCH', url, 400, `${name} must be a string`)
      changes[name] = fields[name]
    }
  }
  if ('max_points' in fields) {
    const n = Number(fields.max_points)
    if (fields.max_points == null || fields.max_points === '' || Number.isNaN(n)) {
      throw fail('PATCH', url, 400, 'max_points must be a number')
    }
    changes.max_points = n
  }
  if ('exact_match' in fields) changes.exact_match = fields.exact_match ? 1 : 0
  if (Object.keys(changes).length === 0) {
    throw fail('PATCH', url, 400, 'nothing to update (title, prompt, max_points, exact_match)')
  }
  Object.assign(q, changes)
  return { status: 200, body: questionWithTests(q) }
}

// Removes the question's tests and submissions, and moves later questions up
// one position so numbering stays 1..n.
export async function deleteQuestion(id) {
  await delay(150)
  const q = questions.get(Number(id))
  if (q) {
    deleteSubmissionsWhere((s) => s.questionId === q.id)
    for (const [tid, t] of testCases) if (t.question_id === q.id) testCases.delete(tid)
    questions.delete(q.id)
    for (const other of questionsOf(q.assignment_id)) if (other.position > q.position) other.position -= 1
  }
  return { status: 204, body: null }
}

// Test cases

export async function addTestCase(questionId, fields) {
  await delay(150)
  const url = `/api/questions/${questionId}/tests`
  or404(questions, 'POST', url, questionId)
  if (!('expected_output' in fields)) throw fail('POST', url, 400, 'expected_output is required')
  return { status: 201, body: { id: insertTestCase(Number(questionId), fields).id } }
}

export async function deleteTestCase(id) {
  await delay(100)
  testCases.delete(Number(id))
  return { status: 204, body: null }
}

// Submissions

export async function createSubmission(questionId, file, label) {
  await delay(300)
  const url = `/api/questions/${questionId}/submissions`
  or404(questions, 'POST', url, questionId)
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) throw fail('POST', url, 400, `${file.name}: use jpg, png, or webp`)
  const id = nextSubmissionId++
  const fileStem = file.name.slice(0, file.name.lastIndexOf('.'))
  submissions.set(id, { createdAt: Date.now(), scenario, questionId: Number(questionId), label: label || fileStem })
  return { status: 201, body: { submission_ids: [id] } }
}

// Fake a test run against the question's current test cases, scored like
// backend/scoring.py. Results are computed on read, so they follow later test edits.
function runMockTests(submissionId, question, run) {
  const none = { test_results: [], verdict: null, suggested_score: null, score_reasoning: null }
  if (!run || !question) return none
  const test_results = testsOf(question.id).map((t, i) => {
    const { actual_output, error } = run(t)
    const passed = error == null && outputsMatch(actual_output, t.expected_output, Boolean(question.exact_match))
    return {
      id: submissionId * 100 + i,
      submission_id: submissionId,
      test_case_id: t.id,
      version: 'original',
      passed: passed ? 1 : 0,
      actual_output,
      error,
      input: t.input,
      expected_output: t.expected_output,
    }
  })
  const total = test_results.length
  const passed = test_results.filter((r) => r.passed).length
  if (total === 0) return none
  const score = Math.round((question.max_points * passed / total) * 100) / 100
  return {
    test_results,
    verdict: passed === total ? 'pass' : null,
    suggested_score: score,
    score_reasoning: `Passed ${passed} of ${total} tests: ${question.max_points} x ${passed}/${total} = ${score}.`,
  }
}

// Full submission object as GET /api/submissions/:id returns it.
function buildSubmission(id, sub) {
  const elapsed = Date.now() - sub.createdAt
  let state
  if (elapsed < QUEUED_MS) state = { status: 'queued', ...PENDING }
  else if (elapsed < QUEUED_MS + PROCESSING_MS) state = { status: 'processing', ...PENDING }
  else state = FINAL[sub.scenario]

  const question = questions.get(sub.questionId) ?? null
  const assignment = question ? assignmentRow(assignments.get(question.assignment_id)) : null
  const graded = runMockTests(id, question, state.run)
  return {
    id,
    question_id: sub.questionId,
    student_label: sub.label,
    status: state.status,
    transcription: state.transcription,
    corrected_code: state.corrected_code,
    flags: state.flags,
    error_message: state.error_message,
    verdict: graded.verdict,
    suggested_score: graded.suggested_score,
    final_score: null,
    notes: null,
    question,
    assignment,
    test_results: graded.test_results,
    score_reasoning: graded.score_reasoning,
  }
}

export async function listSubmissions(questionId) {
  await delay(150)
  or404(questions, 'GET', `/api/questions/${questionId}/submissions`, questionId)
  const rows = [...submissions.entries()]
    .filter(([, sub]) => sub.questionId === Number(questionId))
    .map(([id, sub]) => {
      const s = buildSubmission(id, sub)
      return {
        id: s.id,
        question_id: s.question_id,
        student_label: s.student_label,
        status: s.status,
        verdict: s.verdict,
        suggested_score: s.suggested_score,
        final_score: s.final_score,
        error_message: s.error_message,
      }
    })
  return { status: 200, body: rows }
}

export async function getSubmission(id) {
  await delay(150)
  const sub = or404(submissions, 'GET', `/api/submissions/${id}`, id)
  return { status: 200, body: buildSubmission(Number(id), sub) }
}

export async function deleteSubmission(id) {
  await delay(150)
  submissions.delete(Number(id))
  return { status: 204, body: null }
}

export function imageUrl(id) {
  const sub = submissions.get(Number(id))
  return IMAGES[sub?.scenario ?? 'ready_plain']
}

