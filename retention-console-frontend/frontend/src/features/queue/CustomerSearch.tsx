import { TextField } from '@/components/ui/TextField'

export interface CustomerSearchProps {
  value: string
  onChange: (value: string) => void
}

export function CustomerSearch({ value, onChange }: CustomerSearchProps) {
  return (
    <TextField
      label="Find customer"
      type="search"
      placeholder="e.g. 0295-PPHDO"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}
