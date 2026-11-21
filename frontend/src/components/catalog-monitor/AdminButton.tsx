import { Button, type ButtonProps } from '@/components/ui/button'
import { useIsAdmin } from './useIsAdmin'

interface Props extends ButtonProps {
  /** Tooltip a non-admin sees on the disabled button. */
  adminOnlyTitle: string
}

/** A button only admins can use; members see it disabled, with a tooltip saying why. */
export function AdminButton({ adminOnlyTitle, disabled, ...props }: Props) {
  const isAdmin = useIsAdmin()
  if (isAdmin) return <Button disabled={disabled} {...props} />
  return (
    // a disabled button gets no pointer events: the wrapper carries the tooltip
    <span className="inline-flex cursor-not-allowed" title={adminOnlyTitle} tabIndex={0}>
      <Button {...props} disabled aria-disabled="true" />
    </span>
  )
}
