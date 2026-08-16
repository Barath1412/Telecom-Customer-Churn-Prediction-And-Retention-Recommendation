import React from 'react'

interface RegenerateNoteProps {
  onRegenerate?: () => void
}

export const RegenerateNote: React.FC<RegenerateNoteProps> = ({ onRegenerate }) => {
  return (
    <div className="flex items-center gap-2 p-3 text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg">
      <span>AI Note generated based on customer profile.</span>
      {onRegenerate && (
        <button
          onClick={onRegenerate}
          className="ml-auto text-xs font-semibold text-brand-600 hover:text-brand-700 underline"
        >
          Regenerate
        </button>
      )}
    </div>
  )
}
