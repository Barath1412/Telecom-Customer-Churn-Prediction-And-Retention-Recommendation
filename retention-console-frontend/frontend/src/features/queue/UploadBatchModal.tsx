import { useState, useRef, type ChangeEvent, type DragEvent } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'

export interface UploadBatchModalProps {
  open: boolean
  onClose: () => void
  onUploadSuccess?: (count: number) => void
}

export function UploadBatchModal({ open, onClose, onUploadSuccess }: UploadBatchModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const resetState = () => {
    setSelectedFile(null)
    setIsDragging(false)
    setIsProcessing(false)
    setErrorMessage(null)
    setSuccessMessage(null)
  }

  const handleClose = () => {
    resetState()
    onClose()
  }

  const validateAndSetFile = (file: File) => {
    setErrorMessage(null)
    setSuccessMessage(null)
    const validExtensions = ['.csv', '.xlsx', '.xls']
    const hasValidExtension = validExtensions.some((ext) =>
      file.name.toLowerCase().endsWith(ext),
    )

    if (!hasValidExtension) {
      setErrorMessage('Please upload a valid .csv, .xlsx, or .xls file.')
      setSelectedFile(null)
      return
    }

    if (file.size > 25 * 1024 * 1024) {
      setErrorMessage('File size exceeds the 25MB limit.')
      setSelectedFile(null)
      return
    }

    setSelectedFile(file)
  }

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      validateAndSetFile(files[0]!)
    }
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      validateAndSetFile(files[0]!)
    }
  }

  const handleUpload = async () => {
    if (!selectedFile) return
    setIsProcessing(true)
    setErrorMessage(null)

    try {
      // Simulate client-side cohort parse & validation
      await new Promise((resolve) => setTimeout(resolve, 800))
      setSuccessMessage(`Successfully processed "${selectedFile.name}". Batch queued for scoring.`)
      onUploadSuccess?.(40)
      setTimeout(() => {
        handleClose()
      }, 1200)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to process cohort file.')
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Upload Customer Cohort"
      description="Upload a batch file of customer records (.csv, .xlsx) to run batch churn risk scoring and recommendation generation."
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={handleClose} disabled={isProcessing}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleUpload}
            disabled={!selectedFile || isProcessing}
          >
            {isProcessing ? 'Processing Batch...' : 'Run Scoring & Ingest'}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
            isDragging
              ? 'border-accent bg-accent/5'
              : 'border-line hover:border-ink-3 bg-surface/50'
          }`}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              fileInputRef.current?.click()
            }
          }}
          aria-label="Click or drag file to upload batch"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv, .xlsx, .xls, text/csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
            onChange={handleFileChange}
            className="hidden"
          />

          <div className="mb-2 text-3xl">📊</div>
          <p className="text-sm font-medium text-ink">
            {selectedFile ? selectedFile.name : 'Click to select or drag & drop cohort file'}
          </p>
          <p className="text-xs text-ink-3 mt-1">
            {selectedFile
              ? `${(selectedFile.size / 1024).toFixed(1)} KB`
              : 'Supported formats: .csv, .xlsx, .xls (Max 25MB)'}
          </p>
        </div>

        {errorMessage && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {errorMessage}
          </div>
        )}

        {successMessage && (
          <div className="rounded-md border border-green-200 bg-green-50 p-3 text-xs text-green-700 dark:border-green-900/50 dark:bg-green-950/40 dark:text-green-300">
            {successMessage}
          </div>
        )}

        <div className="rounded-md bg-surface-2 p-3 text-xs text-ink-3 space-y-1">
          <p className="font-semibold text-ink-2">Required Columns:</p>
          <p>
            <code>customerID</code>, <code>tenure</code>, <code>Contract</code>,{' '}
            <code>MonthlyCharges</code>, <code>TotalCharges</code>, <code>InternetService</code>,{' '}
            <code>PaymentMethod</code>, <code>TechSupport</code>
          </p>
        </div>
      </div>
    </Modal>
  )
}
