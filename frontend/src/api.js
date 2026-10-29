// Single switch between the mock and the real backend. See .env.development.
import * as mock from './mockApi.js'

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

// Returns { status, body } so the UI can show exactly what came back.
async function request(method, url, body) {
  const isJson = body !== undefined && !(body instanceof FormData)
  const res = await fetch(url, {
    method,
    headers: isJson ? { 'Content-Type': 'application/json' } : undefined,
    body: isJson ? JSON.stringify(body) : body,
  })
  const text = await res.text()
  let parsed
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    parsed = text
  }
  if (!res.ok) {
    // 400s carry { error }; 404s are Flask's HTML page, which is too long to show.
    let detail = ''
    if (parsed && typeof parsed === 'object' && parsed.error) detail = parsed.error
    else if (typeof parsed === 'string' && parsed.length < 200) detail = parsed
    const err = new Error(`${method} ${url} failed: HTTP ${res.status}${detail ? ` - ${detail}` : ''}`)
    err.body = parsed
    throw err
  }
  return { status: res.status, body: parsed }
}

const real = {
  listAssignments() {
    return request('GET', '/api/assignments')
  },
  getAssignment(id) {
    return request('GET', `/api/assignments/${id}`)
  },
  createAssignment(fields) {
    return request('POST', '/api/assignments', fields)
  },
  deleteAssignment(id) {
    return request('DELETE', `/api/assignments/${id}`)
  },
  addTestCase(assignmentId, fields) {
    return request('POST', `/api/assignments/${assignmentId}/tests`, fields)
  },
  deleteTestCase(id) {
    return request('DELETE', `/api/tests/${id}`)
  },
  // `label` is optional; the backend falls back to the file name when it's missing.
  createSubmission(assignmentId, file, label) {
    const form = new FormData()
    form.append('files', file)
    if (label) form.append('labels', label)
    return request('POST', `/api/assignments/${assignmentId}/submissions`, form)
  },
  listSubmissions(assignmentId) {
    return request('GET', `/api/assignments/${assignmentId}/submissions`)
  },
  getSubmission(id) {
    return request('GET', `/api/submissions/${id}`)
  },
  deleteSubmission(id) {
    return request('DELETE', `/api/submissions/${id}`)
  },
  imageUrl(id) {
    return `/api/submissions/${id}/image`
  },
}

export const api = USE_MOCK ? mock : real
