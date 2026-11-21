import { useRef } from 'react'
import { Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  file: File | null
  onChange: (file: File | null) => void
  /** Button text while no file is chosen. */
  label: string
  accept?: string
  disabled?: boolean
}

export function FilePicker({ file, onChange, label, accept = '.xlsx,.xlsm,.csv', disabled }: Props) {
  const input = useRef<HTMLInputElement>(null)
  return (
    <>
      <input
        ref={input}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          onChange(e.target.files?.[0] ?? null)
          // choosing the same file again must fire onChange again
          e.target.value = ''
        }}
      />
      <Button variant="outline" onClick={() => input.current?.click()} disabled={disabled}>
        <Upload className="mr-2 h-4 w-4" />
        <span className="max-w-[240px] truncate">{file ? file.name : label}</span>
      </Button>
    </>
  )
}
