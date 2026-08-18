import { useState, useRef } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { api, ApiError } from '@/lib/api'
import { useQueryClient } from '@tanstack/react-query'
import type { UploadBatchResponse } from '@/types/api'

export interface UploadBatchModalProps {
  open: boolean
  onClose: () => void
}

export function UploadBatchModal({ open, onClose }: UploadBatchModalProps) {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [result, setResult] = useState<UploadBatchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setError(null)
      setResult(null)
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setIsUploading(true)
    setError(null)
    try {
      const res = await api.uploadBatch(file)
      setResult(res)
      await queryClient.invalidateQueries({ queryKey: ['queue'] })
      await queryClient.invalidateQueries({ queryKey: ['summary'] })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : 'Upload failed')
      }
    } finally {
      setIsUploading(false)
    }
  }

  const handleReset = () => {
    setFile(null)
    setResult(null)
    setError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleClose = () => {
    handleReset()
    onClose()
  }

  return (
    <Modal open={open} onClose={handleClose} title="Upload Customer Batch">
      <div className="space-y-4 text-sm">
        {!result ? (
          <>
            <p className="text-xs text-ink-3">
              Upload an Excel (.xlsx) or CSV spreadsheet of customer accounts. Each row will be evaluated
              by the XGBoost churn model and the policy decision engine to compute Expected Value (EV) and
              re-rank the retention queue.
            </p>

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-line p-6 hover:border-accent hover:bg-surface-alt transition-colors cursor-pointer text-center"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                onChange={handleFileChange}
                className="hidden"
              />
              <span className="text-2xl mb-1">📂</span>
              <span className="font-medium text-ink">
                {file ? file.name : 'Click to select spreadsheet (.xlsx or .csv)'}
              </span>
              <span className="text-micro text-ink-3 mt-1">
                {file ? `${(file.size / 1024).toFixed(1)} KB` : 'Expected columns: CustomerID, Contract, Tenure Months, Monthly Charges, Total Charges, etc.'}
              </span>
            </button>

            {error && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t border-line">
              <Button variant="ghost" size="sm" onClick={handleClose} disabled={isUploading}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => void handleUpload()}
                disabled={!file || isUploading}
              >
                {isUploading ? 'Scoring & Re-Ranking...' : 'Score & Re-Rank Queue'}
              </Button>
            </div>
          </>
        ) : (
          <div className="space-y-4">
            <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-emerald-300">
              <h3 className="font-semibold text-emerald-400 flex items-center gap-2">
                <span>✓</span> Batch Scoring &amp; EV Re-Ranking Complete
              </h3>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div className="bg-surface/40 p-2 rounded">
                  <dt className="text-ink-3">Total Rows Processed</dt>
                  <dd className="font-mono font-bold text-ink text-sm">{result.total_uploaded}</dd>
                </div>
                <div className="bg-surface/40 p-2 rounded">
                  <dt className="text-ink-3">Qualified for Retention</dt>
                  <dd className="font-mono font-bold text-emerald-400 text-sm">{result.qualified_recommended}</dd>
                </div>
                <div className="bg-surface/40 p-2 rounded">
                  <dt className="text-ink-3">New Queue Total</dt>
                  <dd className="font-mono font-bold text-ink text-sm">{result.new_queue_total}</dd>
                </div>
                <div className="bg-surface/40 p-2 rounded">
                  <dt className="text-ink-3">Pending Accounts</dt>
                  <dd className="font-mono font-bold text-ink text-sm">{result.new_pending_total}</dd>
                </div>
              </dl>
              {result.promoted_to_active.length > 0 && (
                <p className="mt-2 text-micro text-emerald-200/90">
                  Promoted {result.promoted_to_active.length} high-EV customer(s) to today&apos;s active top 40.
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-line">
              <Button variant="secondary" size="sm" onClick={handleReset}>
                Upload Another
              </Button>
              <Button variant="primary" size="sm" onClick={handleClose}>
                View Updated Queue
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
