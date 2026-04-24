import { useMutation, useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { Loader2, Sheet } from 'lucide-react'

import { googleSheetsApi } from '@/services/api'
import type { GoogleSheetsDataType } from '@/types'
import { useTranslation } from '@/i18n'
import { useToast } from '@/components/ui/use-toast'
import { Button } from '@/components/ui/button'

interface GoogleSheetsExportButtonProps {
  dataTypes: GoogleSheetsDataType[]
  startDate: string
  endDate: string
  accountIds?: string[]
  language: 'en' | 'it'
  groupBy?: 'day' | 'week' | 'month'
  disabled?: boolean
  onSuccess?: () => void
}

export function GoogleSheetsExportButton({
  dataTypes,
  startDate,
  endDate,
  accountIds,
  language,
  groupBy = 'day',
  disabled = false,
  onSuccess,
}: GoogleSheetsExportButtonProps) {
  const { t } = useTranslation()
  const { toast } = useToast()

  const { data: connection } = useQuery({
    queryKey: ['google-connection'],
    queryFn: () => googleSheetsApi.getConnection(),
  })

  const exportMutation = useMutation({
    mutationFn: () =>
      googleSheetsApi.exportToSheets({
        data_types: dataTypes,
        start_date: startDate,
        end_date: endDate,
        account_ids: accountIds,
        language,
        group_by: groupBy,
        name: `Inthezon Export ${startDate} to ${endDate}`,
        parameters: {
          language,
          group_by: groupBy,
        },
      }),
    onSuccess: (result) => {
      toast({
        title: t('googleSheets.exportSuccess'),
        description: (
          <a
            href={result.spreadsheet_url}
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            {t('googleSheets.openSpreadsheet')}
          </a>
        ),
      })
      onSuccess?.()
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null
      const isReauth = detail === 'google_reauth_required'
      toast({
        variant: 'destructive',
        title: isReauth ? t('googleSheets.reconnectRequired') : t('googleSheets.exportFailed'),
      })
    },
  })

  const buttonDisabled = disabled || dataTypes.length === 0 || !connection || exportMutation.isPending

  return (
    <Button
      variant="outline"
      onClick={() => exportMutation.mutate()}
      disabled={buttonDisabled}
      title={!connection ? t('googleSheets.exportConnectHint') : undefined}
    >
      {exportMutation.isPending ? (
        <>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          {t('googleSheets.exporting')}
        </>
      ) : (
        <>
          <Sheet className="mr-2 h-4 w-4" />
          {connection ? t('googleSheets.exportButton') : t('googleSheets.connectInSettings')}
        </>
      )}
    </Button>
  )
}
