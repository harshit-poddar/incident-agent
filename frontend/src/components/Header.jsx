import { Play, Github, Zap, RotateCcw, ShieldAlert } from 'lucide-react'

export default function Header({ onPipeline, onSimulate, onSimulateVuln, onTrigger, onReset, streaming, busy }) {
  return (
    <div className="topbar">
      <div className="brand">
        <div className="logo">🛰️</div>
        <div>
          <h1>AGENTS_026 · Autonomous Incident Agent</h1>
          <div className="flow">
            detect → diagnose → plan → <b>human approval</b> → remediate → verify
          </div>
        </div>
      </div>
      <div className="actions">
        <button className="btn-pipe" onClick={onPipeline} disabled={streaming}>
          <Play size={15} /> {streaming ? 'streaming…' : 'Run pipeline'}
        </button>
        <button className="btn-gh" onClick={onSimulate} disabled={busy}>
          <Github size={15} /> Simulate CI failure
        </button>
        <button className="btn-sec" onClick={onSimulateVuln} disabled={busy}>
          <ShieldAlert size={15} /> Security scan fail
        </button>
        <button className="btn-primary" onClick={onTrigger} disabled={busy}>
          <Zap size={15} /> Trigger incident
        </button>
        <button className="btn-ghost" onClick={onReset}>
          <RotateCcw size={15} /> Reset
        </button>
      </div>
    </div>
  )
}
