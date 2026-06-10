import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock } from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { brandIntelligenceApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import { useToast } from '@/components/ui/use-toast'
import type { BrandIntelligenceSchedule } from '@/types'

const DAY_KEYS = [
  'brandIntelligence.day.sun',
  'brandIntelligence.day.mon',
  'brandIntelligence.day.tue',
  'brandIntelligence.day.wed',
  'brandIntelligence.day.thu',
  'brandIntelligence.day.fri',
  'brandIntelligence.day.sat',
]

export function WeeklySubscribeToggle({ accountId }: { accountId: string }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const { data: schedule } = useQuery({
    queryKey: ['brand-intelligence-schedule', accountId],
    queryFn: () => brandIntelligenceApi.getSchedule(accountId),
    enabled: !!accountId,
  })

  const mutation = useMutation({
    mutationFn: (next: BrandIntelligenceSchedule) =>
      brandIntelligenceApi.updateSchedule(next),
    onSuccess: (saved) => {
      queryClient.setQueryData(['brand-intelligence-schedule', accountId], saved)
      toast({
        description: saved.is_enabled
          ? t('brandIntelligence.subscribe.on')
          : t('brandIntelligence.subscribe.off'),
      })
    },
    onError: () => {
      toast({ variant: 'destructive', description: t('brandIntelligence.subscribe.error') })
    },
  })

  const enabled = schedule?.is_enabled ?? false
  const dayLabel = t(DAY_KEYS[schedule?.day_of_week ?? 1] ?? DAY_KEYS[1])

  const onToggle = (checked: boolean) => {
    mutation.mutate({
      account_id: accountId,
      is_enabled: checked,
      day_of_week: schedule?.day_of_week ?? 1,
      timezone: schedule?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
    })
  }

  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-sm border border-foreground/25 px-3 py-2 text-sm">
      <CalendarClock className="h-4 w-4 text-muted-foreground" />
      <span className="flex flex-col leading-tight">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-foreground">
          {t('brandIntelligence.subscribe.label')}
        </span>
        <span className="mt-0.5 text-xs text-muted-foreground">
          {enabled
            ? t('brandIntelligence.subscribe.next', { day: dayLabel })
            : t('brandIntelligence.subscribe.hint')}
        </span>
      </span>
      <Switch
        checked={enabled}
        onCheckedChange={onToggle}
        disabled={!accountId || mutation.isPending}
        aria-label={t('brandIntelligence.subscribe.label')}
      />
    </label>
  )
}
