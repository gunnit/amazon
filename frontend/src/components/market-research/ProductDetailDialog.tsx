import { ExternalLink, Target } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useTranslation } from '@/i18n'
import type { MarketSearchResult } from '@/types'

interface ProductDetailDialogProps {
  product: MarketSearchResult | null
  open: boolean
  onClose: () => void
  onSelectAsReference: (product: MarketSearchResult) => void
  averagePrice: number | null
  averageBsr: number | null
}

function formatDiff(value: number, avg: number, lowerIsBetter = false): { text: string; color: string } {
  const pct = Math.round(((value - avg) / avg) * 100)
  const isGood = lowerIsBetter ? pct < 0 : pct > 0

  if (Math.abs(pct) < 3) {
    return { text: 'At market average', color: 'text-muted-foreground' }
  }

  return {
    text: `${Math.abs(pct)}% ${pct > 0 ? 'above' : 'below'} market avg`,
    color: isGood
      ? 'text-emerald-600 dark:text-emerald-400'
      : 'text-red-600 dark:text-red-400',
  }
}

export default function ProductDetailDialog({
  product,
  open,
  onClose,
  onSelectAsReference,
  averagePrice,
  averageBsr,
}: ProductDetailDialogProps) {
  const { t } = useTranslation()

  if (!product) return null

  const priceDiff = product.price != null && averagePrice != null
    ? formatDiff(product.price, averagePrice, true)
    : null

  const bsrDiff = product.bsr != null && averageBsr != null
    ? formatDiff(product.bsr, averageBsr, true)
    : null

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            {t('marketTracker.productDetail')}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* ASIN */}
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">{t('marketResearch.asin')}</p>
            <p className="font-mono text-sm font-medium">{product.asin}</p>
          </div>

          {/* Title */}
          {product.title && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">{t('marketResearch.title2')}</p>
              <p className="text-sm">{product.title}</p>
            </div>
          )}

          {/* Brand & Category */}
          <div className="flex gap-2 flex-wrap">
            {product.brand && (
              <Badge variant="outline">{product.brand}</Badge>
            )}
            {product.category && (
              <Badge variant="secondary">{product.category}</Badge>
            )}
          </div>

          {/* Metrics grid */}
          <div className="grid grid-cols-2 gap-3">
            {/* Price */}
            <div className="rounded-lg border p-3 space-y-1">
              <p className="text-xs text-muted-foreground">{t('marketResearch.price')}</p>
              <p className="text-lg font-bold">
                {product.price != null ? `$${product.price.toFixed(2)}` : '--'}
              </p>
              {priceDiff && (
                <p className={`text-xs ${priceDiff.color}`}>{priceDiff.text}</p>
              )}
            </div>

            {/* BSR */}
            <div className="rounded-lg border p-3 space-y-1">
              <p className="text-xs text-muted-foreground">{t('marketResearch.bsr')}</p>
              <p className="text-lg font-bold">
                {product.bsr != null ? product.bsr.toLocaleString() : '--'}
              </p>
              {bsrDiff && (
                <p className={`text-xs ${bsrDiff.color}`}>{bsrDiff.text}</p>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <Button
              className="flex-1"
              onClick={() => {
                onSelectAsReference(product)
                onClose()
              }}
            >
              <Target className="mr-2 h-4 w-4" />
              {t('marketTracker.selectAsReference')}
            </Button>
            <Button
              variant="outline"
              asChild
            >
              <a
                href={`https://www.amazon.com/dp/${product.asin}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="mr-2 h-4 w-4" />
                {t('marketTracker.openOnAmazon')}
              </a>
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
