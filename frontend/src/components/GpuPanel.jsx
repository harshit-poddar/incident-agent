import { Cpu } from 'lucide-react'

export default function GpuPanel({ gpus, live }) {
  return (
    <div className="card">
      <h2>
        <span className={`chip ${live ? 'live' : 'idle'}`}>
          {live && <span className="pulse" />} {live ? 'live' : 'offline'}
        </span>
        MI300X self-monitor <span className="note">— the agent watches its own hardware</span>
      </h2>
      {(!gpus || gpus.length === 0) ? (
        <div className="empty">starting…</div>
      ) : (
        gpus.map((g, i) => {
          const vramPct = (g.vram_used_gb / g.vram_total_gb) * 100
          return (
            <div key={i} style={{ marginBottom: i < gpus.length - 1 ? 16 : 0 }}>
              <div className="gpu-head">
                <span><Cpu size={15} style={{ verticalAlign: -2, marginRight: 6 }} />{g.device}</span>
                <span className="metric-big">{g.gpu_util_pct.toFixed(0)}<span style={{ fontSize: 14, color: 'var(--mut)' }}>%</span></span>
              </div>
              <div className="kv"><span>GPU utilisation</span><b>{g.gpu_util_pct.toFixed(0)}%</b></div>
              <div className="bar acc"><i style={{ width: `${g.gpu_util_pct}%` }} /></div>
              <div className="kv"><span>VRAM</span><b>{g.vram_used_gb.toFixed(0)} / {g.vram_total_gb.toFixed(0)} GB</b></div>
              <div className={`bar ${vramPct > 90 ? 'red' : 'acc'}`}><i style={{ width: `${vramPct}%` }} /></div>
              <div className="kv"><span>temperature</span><b>{g.temp_c.toFixed(0)} °C</b></div>
              <div className="bar warm"><i style={{ width: `${Math.min((g.temp_c / 110) * 100, 100)}%` }} /></div>
              <div className="kv"><span>board power</span><b>{g.power_w.toFixed(0)} W</b></div>
            </div>
          )
        })
      )}
    </div>
  )
}
