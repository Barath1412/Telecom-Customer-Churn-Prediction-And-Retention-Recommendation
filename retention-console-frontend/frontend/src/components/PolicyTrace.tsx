import { Badge, type BadgeTone } from './ui/Badge'
import type { PolicyRule, RuleState } from '@/types/api'

const TONE: Record<RuleState, BadgeTone> = {
  pass: 'low',
  veto: 'critical',
  not_evaluable: 'warn',
}
const WORD: Record<RuleState, string> = {
  pass: 'pass',
  veto: 'veto',
  not_evaluable: 'not checked',
}

/**
 * Three states, not two. `not_evaluable` means the rule could not be checked
 * because a data feed is missing — rendering it as a pass would be a lie the
 * agent acts on.
 */
export function PolicyTrace({ rules }: { rules: PolicyRule[] }) {
  return (
    <ul className="divide-y divide-line">
      {rules.map((r) => (
        <li key={r.rule_id} className="flex items-start gap-3 py-2">
          <Badge tone={TONE[r.state]}>{WORD[r.state]}</Badge>
          <div className="min-w-0">
            <div className="font-mono text-xs">{r.rule_id}</div>
            <p className="text-xs text-ink-2">{r.detail}</p>
            {r.unmet_requirement && (
              <p className="text-micro text-ink-3">Needs: {r.unmet_requirement}</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
