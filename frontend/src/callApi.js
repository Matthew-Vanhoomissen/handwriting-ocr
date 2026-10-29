// Run one API call for a panel: report the response to the Raw JSON panel via
// `onResponse(label, body)`, and put any error message in the panel's own
// error state. Returns the response, or null if the call failed.
export async function callApi(label, fn, { onResponse, setError }) {
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
