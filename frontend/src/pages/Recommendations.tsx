import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Lightbulb,
  Loader2,
  Megaphone,
  Package,
  Pencil,
  Sparkles,
  Tag,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { accountsApi, catalogApi, recommendationsApi, type StrategicRecommendation } from '@/services/api'
import { useTranslation } from '@/i18n'
import type { AmazonAccount, Product } from '@/types'

const CATEGORIES: StrategicRecommendation['category'][] = [
  'pricing',
  'advertising',
  'inventory',
  'content',
]
const ALL_GENERATE_ACCOUNTS_VALUE = '__all_generate_accounts__'
const ALL_GENERATE_PRODUCTS_VALUE = '__all_generate_products__'

function getContextRecord(
  context: StrategicRecommendation['context']
): Record<string, unknown> | null {
  if (!context || typeof context !== 'object' || Array.isArray(context)) {
    return null
  }
  return context
}

function getGenerationFilters(context: StrategicRecommendation['context']) {
  const contextRecord = getContextRecord(context)
  const rawFilters = contextRecord?.generation_filters
  if (!rawFilters || typeof rawFilters !== 'object' || Array.isArray(rawFilters)) {
    return null
  }
  return rawFilters as Record<string, unknown>
}

function getScopedAsins(context: StrategicRecommendation['context']): string[] {
  const contextRecord = getContextRecord(context)
  const rawAsins = contextRecord?.asins
  if (Array.isArray(rawAsins)) {
    return rawAsins.filter((value): value is string => typeof value === 'string' && value.length > 0)
  }

  const filters = getGenerationFilters(context)
  return typeof filters?.asin === 'string' && filters.asin.length > 0 ? [filters.asin] : []
}

function getScopedAccountId(rec: StrategicRecommendation): string | null {
  if (rec.account_id) return rec.account_id

  const contextRecord = getContextRecord(rec.context)
  if (typeof contextRecord?.account_id === 'string' && contextRecord.account_id.length > 0) {
    return contextRecord.account_id
  }

  const filters = getGenerationFilters(rec.context)
  return typeof filters?.account_id === 'string' && filters.account_id.length > 0
    ? filters.account_id
    : null
}

function categoryIcon(category: StrategicRecommendation['category']) {
  switch (category) {
    case 'pricing':
      return <Tag className="h-4 w-4" />
    case 'advertising':
      return <Megaphone className="h-4 w-4" />
    case 'inventory':
      return <Package className="h-4 w-4" />
    case 'content':
      return <Pencil className="h-4 w-4" />
  }
}

function priorityBadge(priority: StrategicRecommendation['priority']) {
  if (priority === 'high') return <Badge variant="destructive">{priority}</Badge>
  if (priority === 'medium') return <Badge variant="outline">{priority}</Badge>
  return <Badge variant="secondary">{priority}</Badge>
}

export default function Recommendations() {
  const { t, language } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [status, setStatus] = useState<StrategicRecommendation['status']>('pending')
  const [category, setCategory] = useState<string>('')
  const [selectedGenerateAccountId, setSelectedGenerateAccountId] = useState(
    ALL_GENERATE_ACCOUNTS_VALUE
  )
  const [selectedGenerateAsin, setSelectedGenerateAsin] = useState(ALL_GENERATE_PRODUCTS_VALUE)

  const accountsQuery = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const generateProductsQuery = useQuery<Product[]>({
    queryKey: ['recommendation-products', selectedGenerateAccountId],
    queryFn: () =>
      catalogApi.getProducts({
        active_only: true,
        limit: 1000,
        account_ids:
          selectedGenerateAccountId === ALL_GENERATE_ACCOUNTS_VALUE
            ? undefined
            : [selectedGenerateAccountId],
      }),
  })

  const generateProducts = useMemo(() => {
    const deduped = new Map<string, Product>()
    for (const product of generateProductsQuery.data ?? []) {
      if (!deduped.has(product.asin)) {
        deduped.set(product.asin, product)
      }
    }
    return Array.from(deduped.values()).sort((a, b) =>
      (a.title || a.asin).localeCompare(b.title || b.asin)
    )
  }, [generateProductsQuery.data])

  const accountsById = useMemo(
    () => new Map((accountsQuery.data ?? []).map((account) => [account.id, account.account_name])),
    [accountsQuery.data]
  )

  useEffect(() => {
    if (
      selectedGenerateAsin !== ALL_GENERATE_PRODUCTS_VALUE &&
      !generateProducts.some((product) => product.asin === selectedGenerateAsin)
    ) {
      setSelectedGenerateAsin(ALL_GENERATE_PRODUCTS_VALUE)
    }
  }, [generateProducts, selectedGenerateAsin])

  const listQuery = useQuery({
    queryKey: ['recommendations', status, category],
    queryFn: () =>
      recommendationsApi.list({
        status,
        category: (category as StrategicRecommendation['category']) || undefined,
      }),
  })

  const generateMutation = useMutation({
    mutationFn: () =>
      recommendationsApi.generate({
        language,
        lookback_days: 28,
        account_id:
          selectedGenerateAccountId === ALL_GENERATE_ACCOUNTS_VALUE
            ? undefined
            : selectedGenerateAccountId,
        asin:
          selectedGenerateAsin === ALL_GENERATE_PRODUCTS_VALUE
            ? undefined
            : selectedGenerateAsin,
      }),
    onSuccess: (data) => {
      toast({
        title: t('recommendations.generated'),
        description: t('recommendations.generatedDesc', { n: data.created_count }),
      })
      queryClient.invalidateQueries({ queryKey: ['recommendations'] })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, nextStatus }: { id: string; nextStatus: StrategicRecommendation['status'] }) =>
      recommendationsApi.updateStatus(id, { status: nextStatus }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['recommendations'] }),
  })

  const items = listQuery.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="flex items-center gap-3">
          <Lightbulb className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">{t('recommendations.title')}</h1>
            <p className="text-muted-foreground text-sm">{t('recommendations.subtitle')}</p>
          </div>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t('recommendations.generateAccount')}
            </p>
            <Select
              value={selectedGenerateAccountId}
              onValueChange={setSelectedGenerateAccountId}
              disabled={generateMutation.isPending || accountsQuery.isLoading}
            >
              <SelectTrigger className="w-full sm:w-[220px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_GENERATE_ACCOUNTS_VALUE}>
                  {t('filter.allAccounts')}
                </SelectItem>
                {(accountsQuery.data ?? []).map((account) => (
                  <SelectItem key={account.id} value={account.id}>
                    {account.account_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t('recommendations.generateProduct')}
            </p>
            <Select
              value={selectedGenerateAsin}
              onValueChange={setSelectedGenerateAsin}
              disabled={generateMutation.isPending || generateProductsQuery.isLoading}
            >
              <SelectTrigger className="w-full sm:w-[320px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_GENERATE_PRODUCTS_VALUE}>
                  {selectedGenerateAccountId === ALL_GENERATE_ACCOUNTS_VALUE
                    ? t('recommendations.generateAllAccountsAndProducts')
                    : t('recommendations.generateAllProducts')}
                </SelectItem>
                {generateProducts.map((product) => (
                  <SelectItem key={product.asin} value={product.asin}>
                    {product.title ? `${product.title} (${product.asin})` : product.asin}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button onClick={() => generateMutation.mutate()} disabled={generateMutation.isPending}>
            {generateMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            {t('recommendations.generate')}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Tabs
          value={status}
          onValueChange={(v) => setStatus(v as StrategicRecommendation['status'])}
        >
          <TabsList>
            <TabsTrigger value="pending">{t('recommendations.status.pending')}</TabsTrigger>
            <TabsTrigger value="implemented">
              {t('recommendations.status.implemented')}
            </TabsTrigger>
            <TabsTrigger value="dismissed">{t('recommendations.status.dismissed')}</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="min-w-[220px]">
          <Select
            value={category || '__all__'}
            onValueChange={(v) => setCategory(v === '__all__' ? '' : v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">{t('recommendations.allCategories')}</SelectItem>
              {CATEGORIES.map((c) => (
                <SelectItem key={c} value={c}>
                  {t(`recommendations.category.${c}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {listQuery.isLoading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {items.length === 0 && !listQuery.isLoading && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            {t('recommendations.empty')}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {items.map((rec) => (
          (() => {
            const scopedAccountId = getScopedAccountId(rec)
            const scopedAsins = getScopedAsins(rec.context)
            const accountLabel = scopedAccountId
              ? accountsById.get(scopedAccountId) ?? scopedAccountId
              : t('filter.allAccounts')
            const isGlobalScope = !scopedAccountId && scopedAsins.length === 0

            return (
              <Card key={rec.id}>
                <CardHeader className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="gap-1">
                      {categoryIcon(rec.category)}
                      {t(`recommendations.category.${rec.category}`)}
                    </Badge>
                    {priorityBadge(rec.priority)}
                  </div>
                  <CardTitle className="text-base leading-snug">{rec.title}</CardTitle>
                  <CardDescription className="space-y-2 text-xs">
                    <div>{new Date(rec.generated_at).toLocaleDateString()}</div>
                    <div className="flex flex-wrap gap-2">
                      {isGlobalScope ? (
                        <Badge variant="secondary">
                          {t('recommendations.generateAllAccountsAndProducts')}
                        </Badge>
                      ) : (
                        <>
                          <Badge variant="secondary">
                            {t('recommendations.scopeAccount')}: {accountLabel}
                          </Badge>
                          <Badge variant="secondary">
                            {t('recommendations.scopeProduct')}:{' '}
                            {scopedAsins.length > 0
                              ? scopedAsins.join(', ')
                              : t('recommendations.generateAllProducts')}
                          </Badge>
                        </>
                      )}
                    </div>
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground uppercase mb-1">
                      {t('recommendations.rationale')}
                    </p>
                    <p className="text-sm whitespace-pre-wrap">{rec.rationale}</p>
                  </div>
                  {rec.expected_impact && (
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase mb-1">
                        {t('recommendations.expectedImpact')}
                      </p>
                      <p className="text-sm whitespace-pre-wrap">{rec.expected_impact}</p>
                    </div>
                  )}
                  {rec.status === 'pending' && (
                    <div className="flex gap-2 pt-2">
                      <Button
                        size="sm"
                        onClick={() =>
                          statusMutation.mutate({ id: rec.id, nextStatus: 'implemented' })
                        }
                        disabled={statusMutation.isPending}
                      >
                        <CheckCircle2 className="mr-2 h-4 w-4" />
                        {t('recommendations.markImplemented')}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          statusMutation.mutate({ id: rec.id, nextStatus: 'dismissed' })
                        }
                        disabled={statusMutation.isPending}
                      >
                        <X className="mr-2 h-4 w-4" />
                        {t('recommendations.dismiss')}
                      </Button>
                    </div>
                  )}
                  {rec.status !== 'pending' && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => statusMutation.mutate({ id: rec.id, nextStatus: 'pending' })}
                    >
                      {t('recommendations.reopen')}
                    </Button>
                  )}
                </CardContent>
              </Card>
            )
          })()
        ))}
      </div>
    </div>
  )
}
