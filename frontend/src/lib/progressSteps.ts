// Job progress steps are written by the backend as stable English literals and
// stored on the row. Translating them at render time keeps the DB values usable
// as codes (pdf_service and MarketResearch branch on some of them) while the
// client still reads Italian. Unknown steps fall through unchanged.
const STEP_KEYS: Record<string, string> = {
  'queued': 'progress.queued',
  'initializing analysis...': 'progress.initializing',
  'fetching product data...': 'progress.fetchingProduct',
  'fetching reference product...': 'progress.fetchingReference',
  'searching amazon catalog...': 'progress.searchingCatalog',
  'searching market...': 'progress.searchingMarket',
  'discovering competitors...': 'progress.discoveringCompetitors',
  'discovering related products...': 'progress.discoveringRelated',
  'generating ai insights...': 'progress.generatingInsights',
  'creating pdf report...': 'progress.creatingPdf',
  'finalizing report...': 'progress.finalizing',
  'preparing export...': 'progress.preparingExport',
  'exporting data': 'progress.exportingData',
  'generating forecast workbook...': 'progress.generatingWorkbook',
  'packaging files...': 'progress.packaging',
  'generating report': 'progress.generatingReport',
  'report generated': 'progress.reportGenerated',
  'sending email': 'progress.sendingEmail',
  'delivered': 'progress.delivered',
  'delivery failed': 'progress.deliveryFailed',
  'delivery not configured': 'progress.deliveryNotConfigured',
  'waiting for source data': 'progress.waitingSourceData',
  'waiting for processing': 'progress.waitingProcessing',
  'waiting for external yearly export upload': 'progress.waitingYearlyUpload',
  'internal sales sync requested': 'progress.internalSyncRequested',
  'internal sync completed': 'progress.internalSyncCompleted',
  'internal sync failed; continuing with available data': 'progress.internalSyncFailed',
  'sync completed': 'progress.syncCompleted',
  'sync failed': 'progress.syncFailed',
  'cancellation requested': 'progress.cancellationRequested',
  'cancelled by user': 'progress.cancelledByUser',
  'reconnect google account': 'progress.reconnectGoogle',
  'complete': 'progress.complete',
  'complete with limitations': 'progress.completeWithLimitations',
  'stalled': 'progress.stalled',
  'failed': 'progress.failed',
  'generation failed': 'progress.generationFailed',
}

export function translateProgressStep(
  step: string | null | undefined,
  t: (key: string) => string,
  fallback = '—',
): string {
  if (!step) return fallback
  const key = STEP_KEYS[step.trim().toLowerCase()]
  return key ? t(key) : step
}
