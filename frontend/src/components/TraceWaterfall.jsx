import { motion } from 'framer-motion'
import { Activity } from 'lucide-react'

const KINDS = [
  { k: 'graph', label: 'graph' },
  { k: 'agent', label: 'agent' },
  { k: 'llm', label: 'llm call' },
  { k: 'tool', label: 'tool / rag' },
]

function depthOf(span, byId) {
  let d = 0
  let cur = span
  const seen = new Set()
  while (cur.parent_id && byId[cur.parent_id] && !seen.has(cur.span_id)) {
    seen.add(cur.span_id)
    d += 1
    cur = byId[cur.parent_id]
  }
  return d
}

export default function TraceWaterfall({ spans }) {
  if (!spans || spans.length === 0) {
    return (
      <div className="card">
        <h2><Activity size={14} /> Execution trace <span className="note">— OpenTelemetry-style span waterfall</span></h2>
        <div className="empty">Spans appear here once an incident runs. Each agent call and model invocation is timed and nested.</div>
      </div>
    )
  }

  const byId = Object.fromEntries(spans.map((s) => [s.span_id, s]))
  const t0 = Math.min(...spans.map((s) => s.start_ms))
  const t1 = Math.max(...spans.map((s) => (s.end_ms ?? s.start_ms)))
  const span = Math.max(t1 - t0, 1)
  const total = (t1 - t0).toFixed(0)

  return (
    <div className="card">
      <h2><Activity size={14} /> Execution trace <span className="note">— {spans.length} spans · {total} ms wall-clock</span></h2>
      <div className="wf-legend">
        {KINDS.map((x) => (
          <span key={x.k}><span className={`k-dot k-${x.k}`} />{x.label}</span>
        ))}
      </div>
      <div className="wf">
        {spans.map((s, i) => {
          const d = depthOf(s, byId)
          const left = ((s.start_ms - t0) / span) * 100
          const width = Math.max(((s.duration_ms ?? 0) / span) * 100, 1.2)
          return (
            <div className="wf-row" key={s.span_id}>
              <div className="wf-name" style={{ paddingLeft: d * 14 }} title={s.name}>
                <span className={`k-dot k-${s.kind}`} />{s.name}
              </div>
              <div className="wf-track">
                <motion.div
                  className={`wf-bar k-${s.kind} ${s.status === 'error' ? 'wf-err' : ''}`}
                  initial={{ width: 0, left: `${left}%` }}
                  animate={{ width: `${width}%`, left: `${left}%` }}
                  transition={{ delay: i * 0.03, duration: 0.4 }}
                />
              </div>
              <div className="wf-dur">{(s.duration_ms ?? 0).toFixed(1)}ms</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
