export default function AuditTrail({ incident }) {
  const audit = incident?.audit || []
  return (
    <div className="card">
      <h2>Audit trail <span className="note">— every actor, every decision</span></h2>
      <div className="audit">
        {audit.length === 0 ? (
          <div className="empty">—</div>
        ) : (
          audit.map((e, i) => (
            <div className="ev" key={i}>
              <span className="ac">[{e.actor}]</span>
              <span>{e.event}</span>
              <span className="de">{e.detail || ''}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
