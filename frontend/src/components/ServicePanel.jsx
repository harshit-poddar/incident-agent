export default function ServicePanel({ metrics }) {
  if (!metrics) {
    return (
      <div className="card">
        <h2>Affected service</h2>
        <div className="empty">—</div>
      </div>
    )
  }
  const err = metrics.error_rate * 100
  const mem = metrics.mem_usage * 100
  return (
    <div className="card">
      <h2>Affected service</h2>
      <div className="kv">
        <span>service</span><b>{metrics.service}</b>
      </div>
      <div className="kv">
        <span>health</span>
        <b className={`health-badge ${metrics.healthy ? 'health-ok' : 'health-bad'}`}>
          {metrics.healthy ? '● healthy' : '● degraded'}
        </b>
      </div>
      <div className="kv"><span>error rate</span><b>{err.toFixed(1)}%</b></div>
      <div className={`bar ${err > 5 ? 'red' : 'grn'}`}><i style={{ width: `${Math.min(err, 100)}%` }} /></div>
      <div className="kv"><span>memory usage</span><b>{mem.toFixed(0)}%</b></div>
      <div className={`bar ${mem > 85 ? 'red' : 'acc'}`}><i style={{ width: `${Math.min(mem, 100)}%` }} /></div>
      <div className="kv"><span>p95 latency</span><b>{Math.round(metrics.p95_latency_ms)} ms</b></div>
    </div>
  )
}
