import { Badge } from './ui/Badge'
import type { Narration } from '@/types/api'

export interface NarrationPanelProps {
  narration: Narration | null
}

/**
 * The only AI-generated text in the product, and it is labelled as such every
 * single time. `source` also distinguishes a real model note from the
 * deterministic fallback template, because an agent should know which one they
 * are reading.
 */
export function NarrationPanel({ narration }: NarrationPanelProps) {
  if (!narration) {
    return (
      <p className="text-sm text-ink-3">
        No note was generated for this customer. Use the levers and the policy trace directly.
      </p>
    )
  }

  const generated = narration.source === 'llm'

  return (
    <article className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={generated ? 'info' : 'neutral'}>
          {generated ? `AI-drafted · ${narration.model}` : `Template · no model`}
        </Badge>
        {narration.validator_attempts > 1 && (
          <Badge tone="neutral">rewritten {narration.validator_attempts - 1}×</Badge>
        )}
      </div>

      <p className="text-sm font-medium">{narration.summary}</p>
      <p className="text-sm text-ink-2">{narration.why}</p>
      <blockquote className="border-l-2 border-line-strong pl-3 text-sm text-ink">
        {narration.talk_track}
      </blockquote>
      <p className="text-micro text-ink-3">{narration.uncertainty_note}</p>
      <p className="text-micro text-ink-3">
        Evidence:{' '}
        <span className="font-mono">
          {narration.evidence_ids.length > 0 ? narration.evidence_ids.join(', ') : 'none cited'}
        </span>
      </p>
    </article>
  )
}
