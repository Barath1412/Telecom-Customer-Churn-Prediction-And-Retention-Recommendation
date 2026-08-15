import { Button } from '@/components/ui/Button'

export interface ActionBarProps {
  hasOffer: boolean
  hasAlternatives: boolean
  onApprove: () => void
  onEdit: () => void
  onReject: () => void
}

export function ActionBar({
  hasOffer,
  hasAlternatives,
  onApprove,
  onEdit,
  onReject,
}: ActionBarProps) {
  const editDisabled = !hasAlternatives && !hasOffer

  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-3 px-4 py-3">
        <Button variant="primary" onClick={onApprove} disabled={!hasOffer}>
          Approve
        </Button>
        <Button variant="secondary" onClick={onEdit} disabled={editDisabled}>
          Edit offer
        </Button>
        <Button variant="danger" onClick={onReject}>
          Reject
        </Button>

        {!hasOffer && (
          <p className="text-xs text-ink-3">
            Approve is unavailable because no offer qualified.
          </p>
        )}
        {hasOffer && editDisabled && (
          <p className="text-xs text-ink-3">
            Edit is unavailable because no alternative offers are available.
          </p>
        )}
      </div>
    </div>
  )
}
