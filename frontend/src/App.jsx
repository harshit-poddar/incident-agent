import { useCallback, useEffect, useRef, useState } from 'react'
import { getJSON, postJSON, del, DEMO_SIGNAL } from './api'
import Header from './components/Header'
import LifecyclePipeline from './components/LifecyclePipeline'
import LogConsole from './components/LogConsole'
import ApprovalGate from './components/ApprovalGate'
import ProposedFix from './components/ProposedFix'
import AgentReasoning from './components/AgentReasoning'
import TraceWaterfall from './components/TraceWaterfall'
import AuditTrail from './components/AuditTrail'
import ServicePanel from './components/ServicePanel'

export default function App() {
  const [incident, setIncident] = useState(null)
  const [logs, setLogs] = useState([])
  const [streaming, setStreaming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [gpus, setGpus] = useState([])
  const [gpuLive, setGpuLive] = useState(false)
  const [serviceMetrics, setServiceMetrics] = useState(null)
  const [spans, setSpans] = useState([])

  const esRef = useRef(null)
  const incidentRef = useRef(null)
  incidentRef.current = incident

  // ---- GPU self-monitor poll ----
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const g = await getJSON('/telemetry/gpu')
        if (alive) { setGpus(g); setGpuLive(true) }
      } catch {
        if (alive) setGpuLive(false)
      }
    }
    tick()
    const id = setInterval(tick, 3000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  // ---- adopt webhook-opened incidents when idle ----
  useEffect(() => {
    const id = setInterval(async () => {
      if (incidentRef.current) return
      try {
        const s = await getJSON('/incidents/latest')
        if (s && s.id) setIncident(s)
      } catch { /* none yet */ }
    }, 3000)
    return () => clearInterval(id)
  }, [])

  // ---- when the incident changes, refresh its service metrics + trace ----
  useEffect(() => {
    if (!incident) { setServiceMetrics(null); setSpans([]); return }
    let alive = true
    ;(async () => {
      try {
        const m = await getJSON(`/telemetry/service/${incident.signal.service}`)
        if (alive) setServiceMetrics(m)
      } catch { /* service unknown until triggered */ }
      try {
        const sp = await getJSON(`/traces/${incident.id}`)
        if (alive) setSpans(sp)
      } catch { /* no trace yet */ }
    })()
    return () => { alive = false }
  }, [incident?.id, incident?.status])

  const triggerIncident = useCallback(async () => {
    setBusy(true)
    try { setIncident(await postJSON('/incidents', DEMO_SIGNAL)) }
    catch (e) { alert(e.message) }
    finally { setBusy(false) }
  }, [])

  const simulateCI = useCallback(async () => {
    setBusy(true)
    try { setIncident(await postJSON('/github/simulate')) }
    catch (e) { alert(e.message) }
    finally { setBusy(false) }
  }, [])

  const simulateVuln = useCallback(async () => {
    setBusy(true)
    try { setIncident(await postJSON('/github/simulate-vuln')) }
    catch (e) { alert(e.message) }
    finally { setBusy(false) }
  }, [])

  const decide = useCallback(async (approved) => {
    const cur = incidentRef.current
    if (!cur) return
    setBusy(true)
    try {
      const s = await postJSON(`/incidents/${cur.id}/approve`, {
        approved, approver: 'manager',
        reason: approved ? 'approved in demo' : 'rejected in demo',
      })
      setIncident(s)
    } catch (e) { alert(e.message) }
    finally { setBusy(false) }
  }, [])

  const runPipeline = useCallback(() => {
    setStreaming(true)
    setLogs([])
    if (esRef.current) esRef.current.close()
    const es = new EventSource('/pipeline/stream')
    esRef.current = es
    es.onmessage = (e) => {
      const o = JSON.parse(e.data)
      if (o.type === 'log') setLogs((prev) => [...prev, o])
      else if (o.type === 'incident') setIncident(o.incident)
      else if (o.type === 'done') finish()
    }
    es.onerror = () => finish()
    function finish() {
      if (esRef.current) { esRef.current.close(); esRef.current = null }
      setStreaming(false)
    }
  }, [])

  const reset = useCallback(async () => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    setStreaming(false)
    try { await del('/incidents') } catch { /* ignore */ }
    setIncident(null); setLogs([]); setSpans([]); setServiceMetrics(null)
  }, [])

  return (
    <>
      <Header
        onPipeline={runPipeline}
        onSimulate={simulateCI}
        onSimulateVuln={simulateVuln}
        onTrigger={triggerIncident}
        onReset={reset}
        streaming={streaming}
        busy={busy}
      />
      <div className="shell">
        <div className="grid">
          <div className="col">
            <LifecyclePipeline incident={incident} />
            <ServicePanel metrics={serviceMetrics} />
            <LogConsole lines={logs} streaming={streaming} />
            <ApprovalGate incident={incident} onDecide={decide} busy={busy} />
            <ProposedFix incident={incident} />
            <AgentReasoning incident={incident} />
            <TraceWaterfall spans={spans} />
            <AuditTrail incident={incident} />
          </div>
        </div>
      </div>
    </>
  )
}
