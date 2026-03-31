import { useState, type RefObject } from 'react'
import { FileDown, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import { useTranslation } from '@/i18n'
import { exportsApi } from '@/services/api'
import { downloadBlob } from '@/lib/utils'
import { captureAllCharts } from '@/lib/chart-capture'
import type { MarketResearchReport } from '@/types'

interface PdfExportButtonProps {
  report: MarketResearchReport
  chartRefs: Record<string, RefObject<HTMLDivElement>>
}

export default function PdfExportButton({ report, chartRefs }: PdfExportButtonProps) {
  const [exporting, setExporting] = useState(false)
  const { toast } = useToast()
  const { t } = useTranslation()

  const handleExport = async () => {
    setExporting(true)
    try {
      // Capture chart SVGs as images
      const containers: Record<string, HTMLElement | null> = {}
      for (const [key, ref] of Object.entries(chartRefs)) {
        containers[key] = ref.current
      }
      const chartImages = await captureAllCharts(containers)

      // Request PDF from backend
      const blob = await exportsApi.exportMarketResearchPdf({
        report_id: report.id,
        language: report.language,
        chart_images: Object.keys(chartImages).length > 0 ? chartImages : undefined,
      })

      // Download
      const safeTitle = (report.title || 'report').replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 60)
      downloadBlob(blob, `inthezon_${safeTitle}.pdf`)

      toast({ title: t('export.pdfSuccess') })
    } catch (err) {
      console.error('PDF export failed:', err)
      toast({ variant: 'destructive', title: t('export.pdfFailed') })
    } finally {
      setExporting(false)
    }
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleExport}
      disabled={exporting || report.status !== 'completed'}
    >
      {exporting ? (
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      ) : (
        <FileDown className="mr-2 h-4 w-4" />
      )}
      {exporting ? t('export.pdfExporting') : t('export.pdfButton')}
    </Button>
  )
}
