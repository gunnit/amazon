import { EyeOff } from 'lucide-react'
import { Switch } from '@/components/ui/switch'
import { useTranslation } from '@/i18n'
import { useFilterStore } from '@/store/filterStore'

export function CampaignPrivacyToggle() {
  const { t } = useTranslation()
  const checked = useFilterStore(s => s.campaignPrivacy)
  const setChecked = useFilterStore(s => s.setCampaignPrivacy)
  return (
    <label className="inline-flex w-fit cursor-pointer items-center gap-2 text-sm text-muted-foreground">
      <EyeOff aria-hidden="true" className="h-4 w-4 shrink-0" />
      {t('campaign.privacy')}
      <Switch checked={checked} onCheckedChange={setChecked} aria-label={t('campaign.privacy')} />
    </label>
  )
}
