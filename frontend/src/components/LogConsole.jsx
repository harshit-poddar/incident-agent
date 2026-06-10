import { useEffect, useRef } from 'react'

export default function LogConsole({ lines, streaming }) {
  const boxRef = useRef(null)
  useEffect(() => {
    const el = boxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines])

  return (
    <div className="card">
      <h2>
        <span className={`chip ${streaming ? 'live' : 'idle'}`}>
          {streaming && <span className="pulse" />} {streaming ? 'streaming' : 'idle'}
        </span>
        CI / runtime log monitor <span className="note">— watches the stream, auto-opens incidents</span>
      </h2>
      <div className="console" ref={boxRef}>
        {lines.length === 0 ? (
          <div className="empty">Click “Run pipeline” to stream live CI logs.</div>
        ) : (
          lines.map((o, i) => (
            <div className={`logln lvl-${o.level || 'INFO'}`} key={i}>
              <span className="lts">{o.ts || ''}</span>
              <span className="lstage">{o.stage || ''}</span>
              {o.service && <span className="lsvc">{o.service}</span>}
              <span className="lmsg">{o.msg || ''}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
