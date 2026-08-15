import { useEffect, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { SelectField } from '@/components/ui/SelectField'
import { TextField } from '@/components/ui/TextField'
import { ApiError } from '@/lib/api'
import { usd } from '@/lib/format'
import type { ActionKind, ActionRequest, Alternative } from '@/types/api'

export interface ConfirmDialogProps {
  open: boolean
  onClose: () => void
  customerId: string
  action: ActionKind | null
  alternatives: Alternative[]
  loading: boolean
  serverError?: unknown
  onSubmit: (payload: ActionRequest) => void
}

const ACTION_TITLE: Record<ActionKind, string> = {
  approve: 'Approve recommendation',
  edit: 'Change the offer',
  reject: 'Reject recommendation',
}

const REJECT_REASONS = [
  { value: 'already_contacted', label: 'Already contacted' },
  { value: 'offer_not_suitable', label: 'Offer not suitable' },
  { value: 'customer_unreachable', label: 'Customer unreachable' },
  { value: 'account_closing', label: 'Account closing' },
  { value: 'data_looks_wrong', label: 'Data looks wrong' },
  { value: 'other', label: 'Other' },
]

export function ConfirmDialog({
  open,
  onClose,
  customerId,
  action,
  alternatives,
  loading,
  serverError,
  onSubmit,
}: ConfirmDialogProps) {
  const [reason, setReason] = useState(REJECT_REASONS[0]!.value)
  const [selectedOffer, setSelectedOffer] = useState<string>('')
  const [note, setNote] = useState('')
  const [touched, setTouched] = useState(false)

  // Reset form when dialog opens or changes action
  useEffect(() => {
    if (open) {
      setReason(REJECT_REASONS[0]!.value)
      setSelectedOffer(alternatives[0]?.offer_id ?? '')
      setNote('')
      setTouched(false)
    }
  }, [open, action, alternatives])

  if (!action) return null

  // Extract server-side field-level errors if present
  const apiError = serverError instanceof ApiError ? serverError : null
  const serverFields = apiError?.fields ?? []
  const serverNoteError = serverFields.find((f) => f.field === 'note')?.message
  const serverReasonError = serverFields.find((f) => f.field === 'reason_code')?.message
  const serverOfferError = serverFields.find((f) => f.field === 'modified_offer_id')?.message

  // Note becomes required only when rejecting with reason 'other'
  const noteRequired = action === 'reject' && reason === 'other'
  const clientNoteError =
    touched && noteRequired && note.trim().length < 5 ? 'Add a short note.' : undefined
  const noteError = clientNoteError || serverNoteError

  const handleSubmit = () => {
    setTouched(true)
    if (noteRequired && note.trim().length < 5) {
      return
    }

    const payload: ActionRequest = {
      action,
      actor: 'agent_42',
      reason_code: action === 'reject' ? reason : null,
      modified_offer_id: action === 'edit' ? selectedOffer || null : null,
      note: note.trim() || null,
    }

    onSubmit(payload)
  }

  const offerOptions = alternatives.map((alt) => ({
    value: alt.offer_id,
    label: `${alt.offer_name} (EV: ${usd(alt.expected_value)})`,
  }))

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={ACTION_TITLE[action]}
      description={`This writes an audit record against ${customerId}. It cannot be undone.`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button variant="primary" loading={loading} onClick={handleSubmit}>
            Confirm
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {action === 'reject' && (
          <SelectField
            label="Reason"
            options={REJECT_REASONS}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value)
              if (touched) {
                // Re-evaluate validation
              }
            }}
            error={serverReasonError}
            required
          />
        )}

        {action === 'edit' && (
          <SelectField
            label="Replacement offer"
            options={offerOptions}
            value={selectedOffer}
            onChange={(e) => setSelectedOffer(e.target.value)}
            error={serverOfferError}
            required
          />
        )}

        <TextField
          label="Note"
          hint="Stored in the audit log."
          required={noteRequired}
          error={noteError}
          value={note}
          onBlur={() => setTouched(true)}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
    </Modal>
  )
}
