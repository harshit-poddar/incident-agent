import { motion, AnimatePresence } from 'framer-motion'
import { Check, X, Pause } from 'lucide-react'

const openPrAction = (incident) =>
  (incident?.plan?.actions || []).find((a) => a.action === 'open_pr') || null

export default function ApprovalGate({ incident, onDecide, busy }) {
  const show = incident?.status === 'awaiting_approval'
  const isPr = !!openPrAction(incident)
  const note = isPr
    ? 'Approving lets the agent open a pull request with the fix below. Nothing touches the repo until you do.'
    : 'Approving lets the agent execute the remediation in the sandbox cluster.'

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className="card warn"
          initial={{ opacity: 0, height: 0, marginTop: -20 }}
          animate={{ opacity: 1, height: 'auto', marginTop: 0 }}
          exit={{ opacity: 0, height: 0, marginTop: -20 }}
        >
          <h2><Pause size={14} /> Human approval gate</h2>
          <div>
            <b>{incident.plan?.summary}</b>
            <br />
            <span className="muted">{note}</span>
          </div>
          <div className="gate-actions">
            <button className="btn-approve" disabled={busy} onClick={() => onDecide(true)}>
              <Check size={16} /> Approve remediation
            </button>
            <button className="btn-reject" disabled={busy} onClick={() => onDecide(false)}>
              <X size={16} /> Reject
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
