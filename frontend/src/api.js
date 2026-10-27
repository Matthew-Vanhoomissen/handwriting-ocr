// Single switch between the mock and the real backend. See .env.development.
import * as mock from './mockApi.js'

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

// Returns { status, body } so the UI can show exactly what came back.
async function request(method, url, body) {
  const res = await fetch(url, { method, body })
  const text = await res.text()
  let parsed
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    parsed = text
  }
  if (!res.ok) {
    const detail = typeof parsed === 'object' && parsed?.error ? parsed.error : text
    const err = new Error(`${method} ${url} failed: HTTP ${res.status}${detail ? ` - ${detail}` : ''}`)
    err.body = parsed
    throw err
  }
  return { status: res.status, body: parsed }
}

const real = {
  createSubmission(file) {
    const form = new FormData()
    form.append('image', file)
    return request('POST', '/api/submissions', form)
  },
  getSubmission(id) {
    return request('GET', `/api/submissions/${id}`)
  },
}

export const api = USE_MOCK ? mock : real
