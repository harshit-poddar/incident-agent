// Thin fetch wrapper. All paths are relative to the origin -- in production the
// FastAPI server serves both this app and the API; in dev Vite proxies them.
export async function api(method, path, body) {
  const opt = { method, headers: { 'Content-Type': 'application/json' } }
  if (body !== undefined) opt.body = JSON.stringify(body)
  const r = await fetch(path, opt)
  if (!r.ok) throw new Error(`${method} ${path} -> ${r.status}`)
  return r.json()
}

export const getJSON = (p) => api('GET', p)
export const postJSON = (p, b) => api('POST', p, b)
export const del = (p) => api('DELETE', p)

// The golden-path demo signal.
export const DEMO_SIGNAL = {
  service: 'payments-api',
  metric: 'error_rate',
  value: 0.38,
  threshold: 0.02,
  message: '5xx error rate breached threshold (OOMKilled)',
}
