// In-browser stand-in for the Flask API. Responses match the contract in
// CLAUDE.md section 12 exactly. Each upload walks queued -> processing -> final,
// where the final state comes from the scenario picked in the UI.

const QUEUED_MS = 2500
const PROCESSING_MS = 5000

export const SCENARIOS = {
  ready_plain: 'ready, no corrected code',
  ready_corrected: 'ready, syntax error + corrected code',
  error: 'error',
}

const FINAL = {
  ready_plain: {
    status: 'ready',
    image_url: '/mock/sample-1.svg',
    transcription: 'def add(a, b):\n    return a + b\n\nprint(add(2, 3))\n',
    uncertain_lines: [2],
    syntax_error: null,
    corrected_code: null,
    error: null,
  },
  ready_corrected: {
    status: 'ready',
    image_url: '/mock/sample-2.svg',
    transcription:
      'def average(nums)\n    total = 0\n    for n in nums:\n        total += n\n    return total / len(nums)\n\nprint(average([1, 2, 3]))\n',
    uncertain_lines: [1, 4],
    syntax_error: "line 1: expected ':'",
    corrected_code:
      'def average(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total / len(nums)\n\nprint(average([1, 2, 3]))\n',
    error: null,
  },
  error: {
    status: 'error',
    image_url: '/mock/sample-1.svg',
    transcription: null,
    uncertain_lines: [],
    syntax_error: null,
    corrected_code: null,
    error: 'Transcription failed: model API returned 429 (rate limited) after 3 attempts',
  },
}

const submissions = new Map()
let nextId = 7
let scenario = 'ready_plain'

export function setScenario(name) {
  scenario = name
}

const delay = (ms) => new Promise((r) => setTimeout(r, ms))

export async function createSubmission(_file) {
  await delay(300)
  const id = nextId++
  submissions.set(id, { createdAt: Date.now(), scenario })
  return { status: 201, body: { id, status: 'queued' } }
}

export async function getSubmission(id) {
  await delay(150)
  const sub = submissions.get(Number(id))
  if (!sub) {
    throw new Error(`GET /api/submissions/${id} failed: HTTP 404 (mock)`)
  }
  const elapsed = Date.now() - sub.createdAt
  const final = FINAL[sub.scenario]
  const pending = {
    image_url: final.image_url,
    transcription: null,
    uncertain_lines: [],
    syntax_error: null,
    corrected_code: null,
    error: null,
  }
  let body
  if (elapsed < QUEUED_MS) body = { id: Number(id), status: 'queued', ...pending }
  else if (elapsed < QUEUED_MS + PROCESSING_MS) body = { id: Number(id), status: 'processing', ...pending }
  else body = { id: Number(id), ...final }
  return { status: 200, body }
}
