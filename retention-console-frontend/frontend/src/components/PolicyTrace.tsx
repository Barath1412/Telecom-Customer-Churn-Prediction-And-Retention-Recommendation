import { Badge } from './ui/Badge'
import type { PolicyRule } from '@/types/api'

export interface PolicyTraceProps {
  rules: PolicyRule[]
}

/**
 * Three states, not two. `not_evaluable` means the rule could not be checked
 * because a data feed is missing — rendering it as a pass would be a lie the
 * agent acts on.
 *
 * Tone convention:
 * - pass: tone="neutral" (quiet non-risk state)
 * - veto: tone="neutral" with className="border-danger text-danger" (application danger token,
 *         strictly avoiding reuse of the critical risk band; logged for Module A3 to add tone="danger")
 * - not_evaluable: tone="warn" (the single legitimate reservation in the console)
 */
export function PolicyTrace({ rules }: PolicyTraceProps) {
  return (
    <ul className="divide-y divide-line">
      {rules.map((r) => (
        <li key={r.rule_id} className="flex items-start gap-3 py-2">
          {r.state === 'pass' && <Badge tone="neutral">pass</Badge>}
          {r.state === 'veto' && (
            <Badge tone="neutral" className="border-danger text-danger">
              veto
            </Badge>
          )}
          {r.state === 'not_evaluable' && <Badge tone="warn">not checked</Badge>}

          <div className="min-w-0">
            <div className="font-mono text-xs">{r.rule_id}</div>
            <p className="text-xs text-ink-2">{r.detail}</p>
            {r.state === 'not_evaluable' && (
              <p className="text-micro text-ink-3">Needs: {r.unmet_requirement}</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
