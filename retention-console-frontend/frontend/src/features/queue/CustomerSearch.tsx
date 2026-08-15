import { TextField } from '@/components/ui/TextField'

export interface CustomerSearchProps {
  value: string
  onChange: (value: string) => void
}

export function CustomerSearch({ value, onChange }: CustomerSearchProps) {
  return (
    <div className="max-w-xs">
      <TextField
        label="Find customer"
        type="search"
        placeholder="e.g. 7590-VHVEG"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}
