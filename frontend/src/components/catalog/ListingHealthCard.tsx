import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { catalogApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import { cn } from '@/lib/utils'
import { AccountPicker } from './AccountPicker'
import type { ListingComponentName, ListingQualityItem, TabProps } from './types'

// Traffic lights over the listing-quality score the backend computes from
// synced catalog fields (listing_quality_service.py): green from 80 points,
// yellow from 50, red below. A component is green when it earns its full
// points, yellow when partial, red when it earns none.
type Light = 'green' | 'yellow' | 'red'

const SCORE_GREEN = 80
const SCORE_YELLOW = 50

const COMPONENTS: ListingComponentName[] = [
  'title',
  'brand',
  'category',
  'price',
  'availability',
  'rating',
  'reviews',
]

const LIGHT_DOT: Record<Light | 'na', string> = {
  green: 'bg-emerald-600',
  yellow: 'bg-amber-400',
  red: 'bg-red-600',
  na: 'bg-muted-foreground/30',
}

function scoreLight(score: number): Light {
  if (score >= SCORE_GREEN) return 'green'
  if (score >= SCORE_YELLOW) return 'yellow'
  return 'red'
}

function componentLight(item: ListingQualityItem, name: ListingComponentName): Light | 'na' {
  const component = item.components[name]
  if (!component) return 'na'
  if (component.earned >= component.max) return 'green'
  if (component.earned > 0) return 'yellow'
  return 'red'
}

function Dot({ light, label }: { light: Light | 'na'; label?: string }) {
  return (
    <span
      className={cn('inline-block h-3 w-3 shrink-0 rounded-full', LIGHT_DOT[light])}
      title={label}
      aria-label={label}
    />
  )
}

export function ListingHealthCard(props: TabProps) {
  const { t, accountId } = props
  const [filter, setFilter] = useState<Light | 'all'>('all')
  const [search, setSearch] = useState('')

  const query = useQuery({
    queryKey: ['catalog', 'listing-quality', accountId],
    queryFn: () => catalogApi.getListingQuality(accountId),
    enabled: !!accountId,
  })
  const data = query.data

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (data?.products ?? []).filter((item) => {
      if (filter !== 'all' && scoreLight(item.score) !== filter) return false
      if (!needle) return true
      return (
        item.asin.toLowerCase().includes(needle) ||
        (item.title ?? '').toLowerCase().includes(needle) ||
        (item.sku ?? '').toLowerCase().includes(needle)
      )
    })
  }, [data, filter, search])

  const counts: Record<Light, number> = {
    green: data?.good_count ?? 0,
    yellow: data?.fair_count ?? 0,
    red: data?.poor_count ?? 0,
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('catalog.health.title')}</CardTitle>
        <CardDescription>{t('catalog.health.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="max-w-sm">
          <AccountPicker {...props} />
        </div>

        {!accountId ? (
          <p className="text-sm text-muted-foreground">{t('catalog.products.selectAccount')}</p>
        ) : query.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('catalog.health.loading')}
          </div>
        ) : query.isError ? (
          <p className="text-sm text-destructive">{apiErrorDetail(query.error, t)}</p>
        ) : !data || data.product_count === 0 ? (
          <p className="text-sm text-muted-foreground">{t('catalog.health.empty')}</p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-4">
              {(['red', 'yellow', 'green'] as Light[]).map((light) => (
                <button
                  key={light}
                  type="button"
                  onClick={() => setFilter(filter === light ? 'all' : light)}
                  className={cn(
                    'flex items-center gap-3 rounded-md border p-4 text-left transition-colors hover:bg-muted/50',
                    filter === light && 'border-foreground bg-muted/50',
                  )}
                >
                  <Dot light={light} />
                  <div>
                    <p className="text-2xl font-semibold tabular-nums">{counts[light]}</p>
                    <p className="text-xs text-muted-foreground">{t(`catalog.health.count.${light}`)}</p>
                  </div>
                </button>
              ))}
              <div className="rounded-md border p-4">
                <p className="text-2xl font-semibold tabular-nums">
                  {data.average_score === null ? '—' : Math.round(data.average_score)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t('catalog.health.average', { count: data.product_count })}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t('catalog.health.search')}
                className="max-w-xs"
              />
              {filter !== 'all' ? (
                <Button variant="outline" size="sm" onClick={() => setFilter('all')}>
                  {t('catalog.health.showAll')}
                </Button>
              ) : null}
              <span className="text-xs text-muted-foreground">
                {t('catalog.health.shown', { shown: rows.length, total: data.product_count })}
              </span>
            </div>

            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[260px]">{t('catalog.health.col.product')}</TableHead>
                    {COMPONENTS.map((name) => (
                      <TableHead key={name} className="text-center">
                        {t(`catalog.health.component.${name}`)}
                      </TableHead>
                    ))}
                    <TableHead className="text-center">{t('catalog.health.col.score')}</TableHead>
                    <TableHead className="min-w-[220px]">{t('catalog.health.col.fix')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((item) => {
                    const toFix = COMPONENTS.filter((name) => {
                      const light = componentLight(item, name)
                      return light === 'red' || light === 'yellow'
                    })
                    return (
                      <TableRow key={item.asin}>
                        <TableCell>
                          <p className="line-clamp-2 text-sm">{item.title || item.asin}</p>
                          <p className="font-mono text-xs text-muted-foreground">{item.asin}</p>
                        </TableCell>
                        {COMPONENTS.map((name) => (
                          <TableCell key={name} className="text-center">
                            <span className="inline-flex justify-center">
                              <Dot
                                light={componentLight(item, name)}
                                label={item.components[name]?.detail}
                              />
                            </span>
                          </TableCell>
                        ))}
                        <TableCell>
                          <span className="flex items-center justify-center gap-2">
                            <Dot light={scoreLight(item.score)} />
                            <span className="font-semibold tabular-nums">{item.score}</span>
                          </span>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {toFix.length
                            ? toFix.map((name) => t(`catalog.health.fix.${name}`)).join(' · ')
                            : t('catalog.health.fix.none')}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
            {data.products.length < data.product_count ? (
              <p className="text-xs text-muted-foreground">
                {t('catalog.health.truncated', { shown: data.products.length, total: data.product_count })}
              </p>
            ) : null}
            <p className="text-xs text-muted-foreground">{t('catalog.health.criteria')}</p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
