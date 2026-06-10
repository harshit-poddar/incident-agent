import { GitPullRequest, ExternalLink } from 'lucide-react'

const openPrAction = (incident) =>
  (incident?.plan?.actions || []).find((a) => a.action === 'open_pr') || null

function prUrl(incident) {
  const out = (incident?.remediation_results || []).map((r) => r.output || '').join(' ')
  const m = out.match(/https:\/\/github\.com\/\S+/)
  return m ? m[0] : null
}

export default function ProposedFix({ incident }) {
  const action = openPrAction(incident)
  if (!action || !action.fix) return null
  const f = action.fix
  const url = prUrl(incident)

  return (
    <div className="card glow">
      <h2><GitPullRequest size={14} /> Proposed code fix <span className="note">— LLM-generated, gated behind approval</span></h2>
      <div className="fixmeta"><b>{f.pr_title}</b><br />{f.rationale}</div>
      <div className="fixmeta">file <b>{f.file_path}</b></div>
      <pre className="code">{f.new_content}</pre>
      {url ? (
        <a className="prlink" href={url} target="_blank" rel="noreferrer">
          <ExternalLink size={15} /> Pull request opened → {url}
        </a>
      ) : (
        <div className="fixmeta" style={{ marginTop: 10 }}>The PR opens only after you approve at the gate.</div>
      )}
    </div>
  )
}
