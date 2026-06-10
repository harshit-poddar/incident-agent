import { motion } from 'framer-motion'
import { Radar, Stethoscope, ClipboardList, ShieldQuestion, Wrench, BadgeCheck, CheckCircle2 } from 'lucide-react'

const STAGES = [
  { key: 'detected', label: 'detect', Icon: Radar },
  { key: 'diagnosing', label: 'diagnose', Icon: Stethoscope },
  { key: 'planned', label: 'plan', Icon: ClipboardList },
  { key: 'awaiting_approval', label: 'approval', Icon: ShieldQuestion },
  { key: 'remediating', label: 'remediate', Icon: Wrench },
  { key: 'verifying', label: 'verify', Icon: BadgeCheck },
  { key: 'resolved', label: 'resolved', Icon: CheckCircle2 },
]

const rank = (status) => {
  const i = STAGES.findIndex((s) => s.key === status)
  return i === -1 ? STAGES.length : i
}

export default function LifecyclePipeline({ incident }) {
  const status = incident?.status || ''
  const cur = rank(status)
  const terminalBad = status === 'rejected' || status === 'failed'

  return (
    <div className="card">
      <h2>
        Incident lifecycle
        {incident && (
          <span className="note">
            {' '}· {incident.id} · {status.replace(/_/g, ' ')}
          </span>
        )}
      </h2>
      <div className="pipe">
        {STAGES.map((s, i) => {
          let cls = 'stage'
          if (status === s.key) cls += s.key === 'resolved' ? ' resolved' : ' active'
          else if (i < cur) cls += ' done'
          const { Icon } = s
          return (
            <motion.div
              key={s.key}
              className={cls}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <Icon className="ico" size={18} />
              {s.label}
            </motion.div>
          )
        })}
        {terminalBad && (
          <motion.div
            className={`stage ${status}`}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
          >
            {status}
          </motion.div>
        )}
      </div>
    </div>
  )
}
