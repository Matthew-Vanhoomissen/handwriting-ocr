// In-browser stand-in for the Flask API. Responses match the contract in
// CLAUDE.md section 12 (which mirrors backend/app.py). Each upload walks
// queued -> processing -> final, where the final state comes from the
// scenario picked in the UI. Data lives in memory and resets on reload.

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
  },
  error: {
    status: 'error',
    transcription: null,
    corrected_code: null,
    flags: null,
    error_message: 'RateLimitError: model API returned 429 (rate limited)',
  },
}

const assignments = new Map()
const testCases = new Map()
const submissions = new Map()
let nextAssignmentId = 1
let nextTestId = 1
let nextSubmissionId = 7
let scenario = 'ready_plain'

function insertAssignment({ title, prompt = '', max_points, exact_match = false }) {
  const row = { id: nextAssignmentId++, title, prompt, max_points: Number(max_points), language: 'python', exact_match: exact_match ? 1 : 0 }
  assignments.set(row.id, row)
  return row
}

function insertTestCase(assignmentId, { input = '', expected_output }) {
  const row = { id: nextTestId++, assignment_id: assignmentId, input, expected_output }
  testCases.set(row.id, row)
  return row
}

// Seed one assignment so the page is usable right away.
const seeded = insertAssignment({ title: 'Add two numbers (mock)', prompt: 'Read two ints, print their sum.', max_points: 10 })
insertTestCase(seeded.id, { input: '2 3\n', expected_output: '5\n' })
insertTestCase(seeded.id, { input: '-1 1\n', expected_output: '0\n' })

export function setScenario(name) {
  scenario = name
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms))

function fail(method, url, status, error) {
  const err = new Error(`${method} ${url} failed: HTTP ${status} - ${error} (mock)`)
  err.body = { error }
  return err
}

function assignmentOr404(method, url, id) {
  const row = assignments.get(Number(id))
  if (!row) throw fail(method, url, 404, 'Not Found')
  return row
}

export async function listAssignments() {
  await delay(100)
  return { status: 200, body: [...assignments.values()] }
}

export async function getAssignment(id) {
  await delay(100)
  const row = assignmentOr404('GET', `/api/assignments/${id}`, id)
  const tests = [...testCases.values()].filter((t) => t.assignment_id === row.id)
  return { status: 200, body: { ...row, test_cases: tests } }
}

export async function createAssignment(fields) {
  await delay(150)
  const url = '/api/assignments'
  if (!fields.title || fields.max_points == null || fields.max_points === '') {
    throw fail('POST', url, 400, 'title and max_points are required')
  }
  if (Number.isNaN(Number(fields.max_points))) throw fail('POST', url, 400, 'max_points must be a number')
  return { status: 201, body: insertAssignment(fields) }
}

export async function addTestCase(assignmentId, fields) {
  await delay(150)
  const url = `/api/assignments/${assignmentId}/tests`
  assignmentOr404('POST', url, assignmentId)
  if (!('expected_output' in fields)) throw fail('POST', url, 400, 'expected_output is required')
  return { status: 201, body: { id: insertTestCase(Number(assignmentId), fields).id } }
}

export async function deleteTestCase(id) {
  await delay(100)
  testCases.delete(Number(id))
  return { status: 204, body: null }
}

export async function createSubmission(assignmentId, file) {
  await delay(300)
  const url = `/api/assignments/${assignmentId}/submissions`
  assignmentOr404('POST', url, assignmentId)
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!ALLOWED_EXTENSIONS.includes(ext)) throw fail('POST', url, 400, `${file.name}: use jpg, png, or webp`)
  const id = nextSubmissionId++
  const label = file.name.slice(0, file.name.lastIndexOf('.'))
  submissions.set(id, { createdAt: Date.now(), scenario, assignmentId: Number(assignmentId), label })
  return { status: 201, body: { submission_ids: [id] } }
}

export async function getSubmission(id) {
  await delay(150)
  const sub = submissions.get(Number(id))
  if (!sub) throw fail('GET', `/api/submissions/${id}`, 404, 'Not Found')
  const elapsed = Date.now() - sub.createdAt
  const pending = { transcription: null, corrected_code: null, flags: null, error_message: null }
  let state
  if (elapsed < QUEUED_MS) state = { status: 'queued', ...pending }
  else if (elapsed < QUEUED_MS + PROCESSING_MS) state = { status: 'processing', ...pending }
  else state = FINAL[sub.scenario]

  // Mock does not run tests, so there are no results and no suggested score.
  const body = {
    id: Number(id),
    assignment_id: sub.assignmentId,
    student_label: sub.label,
    status: state.status,
    transcription: state.transcription,
    corrected_code: state.corrected_code,
    flags: state.flags,
    error_message: state.error_message,
    verdict: null,
    suggested_score: null,
    final_score: null,
    notes: null,
    assignment: assignments.get(sub.assignmentId) ?? null,
    test_results: [],
    score_reasoning: null,
  }
  return { status: 200, body }
}

export function imageUrl(id) {
  const sub = submissions.get(Number(id))
  return IMAGES[sub?.scenario ?? 'ready_plain']
}
