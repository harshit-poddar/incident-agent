import { motion } from 'framer-motion'

function pct(x) {
  return Math.round((x || 0) * 100)
}

function AgentCard({ role, filled, children }) {
  return (
    <motion.div
      className={`agent ${filled ? 'filled' : ''}`}
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
    >
      <div className="role">{role}</div>
      <div className="body">{filled ? children : <span className="muted">pending…</span>}</div>
    </motion.div>
  )
}

export default function AgentReasoning({ incident }) {
  const d = incident?.detection
  const dg = incident?.diagnosis
  const p = incident?.plan
  const v = incident?.verification

  if (!incident) {
    return (
      <div className="card">
        <h2>Agent reasoning</h2>
        <div className="empty">No incident yet — trigger one, simulate a CI failure, or run the pipeline.</div>
      </div>
    )
  }

  return (
    <div className="card">
      <h2>Agent reasoning <span className="note">— four specialists, one closed loop</span></h2>

      <AgentCard role="🛰  Detector" filled={!!d}>
        {d && (
          <>
            {d.summary} <span className={`pill ${d.severity}`}>{d.severity}</span>
            <div className="conf-meter"><i style={{ width: `${pct(d.confidence)}%` }} /></div>
            <span className="muted">confidence {pct(d.confidence)}%</span>
          </>
        )}
      </AgentCard>

      <AgentCard role="🩺  Diagnoser" filled={!!dg}>
        {dg && (
          <>
            <b>{dg.root_cause}</b>
            <ul className="evidence">
              {(dg.evidence || []).map((e, i) => <li key={i}>{e}</li>)}
            </ul>
            <div className="conf-meter"><i style={{ width: `${pct(dg.confidence)}%` }} /></div>
            <span className="muted">confidence {pct(dg.confidence)}% · recommends {dg.recommended_action_type}</span>
          </>
        )}
      </AgentCard>

      <AgentCard role="📋  Planner" filled={!!p}>
        {p && (
          <>
            {p.summary}
            {(p.actions || []).map((a, i) => (
              <div className="action-row" key={i}>
                {a.action} → <b>{a.target}</b> <span className={`pill ${a.risk}`}>{a.risk}</span>
                <br />
                <span className="de">{a.rationale}</span>
              </div>
            ))}
          </>
        )}
      </AgentCard>

      <AgentCard role="✅  Verifier" filled={!!v}>
        {v && (
          <>
            {v.summary}
            <br />
            <span className={`pill ${v.resolved ? 'low' : 'high'}`} style={{ marginTop: 6, display: 'inline-block' }}>
              {v.resolved ? 'resolved' : 'not resolved'}
            </span>
            {v.notes && <><br /><span className="muted">{v.notes}</span></>}
          </>
        )}
      </AgentCard>
    </div>
  )
}
