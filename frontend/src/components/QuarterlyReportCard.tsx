import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, Loader2 } from 'lucide-react'

import { accountsApi, catalogApi, reportsApi } from '@/services/api'
import type { AmazonAccount } from '@/types'
import { downloadBlob } from '@/lib/utils'
import { apiErrorDetail } from '@/lib/apiError'
import { useTranslation } from '@/i18n'
import { useToast } from '@/components/ui/use-toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const MAX_ASINS = 500

/** The last completed calendar quarter as of ``today``. */
function lastFullQuarter(today: Date = new Date()): { year: number; quarter: number } {
  const current = Math.floor(today.getMonth() / 3) + 1
  return current === 1
    ? { year: today.getFullYear() - 1, quarter: 4 }
    : { year: today.getFullYear(), quarter: current - 1 }
}

/** ASINs separated by commas, spaces or new lines: upper-cased, unique. */
function parseAsins(text: string): string[] {
  return Array.from(
    new Set(
      text
        .split(/[\s,;]+/)
        .map((asin) => asin.trim().toUpperCase())
        .filter(Boolean)
    )
  )
}

export function QuarterlyReportCard() {
  const { t, language } = useTranslation()
  const { toast } = useToast()
  const initial = useMemo(() => lastFullQuarter(), [])

  const [year, setYear] = useState(initial.year)
  const [quarter, setQuarter] = useState(initial.quarter)
  const [accountIds, setAccountIds] = useState<string[]>([])
  const [brand, setBrand] = useState('')
  const [category, setCategory] = useState('')
  const [asinsText, setAsinsText] = useState('')
  const [reportLanguage, setReportLanguage] = useState<'it' | 'en'>(language === 'en' ? 'en' : 'it')

  const { data: accounts = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })
  const { data: brands = [] } = useQuery<string[]>({
    queryKey: ['catalog-brands', accountIds],
    queryFn: () => catalogApi.getBrands({ account_ids: accountIds.length > 0 ? accountIds : undefined }),
  })

  const asins = parseAsins(asinsText)
  const tooManyAsins = asins.length > MAX_ASINS
  const thisYear = new Date().getFullYear()
  const years = Array.from({ length: thisYear - 2020 + 1 }, (_, index) => thisYear - index)

  const generateMutation = useMutation({
    mutationFn: async () => {
      const blob = await reportsApi.generateQuarterlyReport({
        account_ids: accountIds,
        year,
        quarter,
        brand: brand || undefined,
        category: category.trim() || undefined,
        asins: asins.length > 0 ? asins : undefined,
        language: reportLanguage,
      })
      return { blob, filename: `report-trimestrale-${year}-Q${quarter}.pptx` }
    },
    onSuccess: ({ blob, filename }) => {
      downloadBlob(blob, filename)
      toast({ title: t('quarterlyReport.ready') })
    },
    onError: (error) => {
      toast({
        variant: 'destructive',
        title: t('quarterlyReport.failed'),
        description: apiErrorDetail(error, t) ?? t('quarterlyReport.failedDesc'),
      })
    },
  })

  const toggleAccount = (id: string) =>
    setAccountIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
    )

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('quarterlyReport.title')}</CardTitle>
        <CardDescription>{t('quarterlyReport.desc')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label>{t('quarterlyReport.year')}</Label>
            <Select value={String(year)} onValueChange={(value) => setYear(Number(value))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {years.map((value) => (
                  <SelectItem key={value} value={String(value)}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>{t('quarterlyReport.quarter')}</Label>
            <Select value={String(quarter)} onValueChange={(value) => setQuarter(Number(value))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[1, 2, 3, 4].map((value) => (
                  <SelectItem key={value} value={String(value)}>
                    {`Q${value}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>{t('quarterlyReport.language')}</Label>
            <Select value={reportLanguage} onValueChange={(value: 'it' | 'en') => setReportLanguage(value)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="it">Italiano</SelectItem>
                <SelectItem value="en">English</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid gap-2">
          <Label>{t('quarterlyReport.accounts')}</Label>
          <div className="grid max-h-44 gap-2 overflow-y-auto rounded-lg border p-3 sm:grid-cols-2">
            {accounts.map((account) => (
              <label key={account.id} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={accountIds.includes(account.id)}
                  onCheckedChange={() => toggleAccount(account.id)}
                />
                <span>
                  {account.account_name} ({account.marketplace_country})
                </span>
              </label>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{t('quarterlyReport.accountsHint')}</p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label>{t('quarterlyReport.brand')}</Label>
            <Select value={brand || '_all'} onValueChange={(value) => setBrand(value === '_all' ? '' : value)}>
              <SelectTrigger>
                <SelectValue placeholder={t('filter.allBrands')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">{t('filter.allBrands')}</SelectItem>
                {brands.map((value) => (
                  <SelectItem key={value} value={value}>
                    {value}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="quarterly-report-category">{t('quarterlyReport.category')}</Label>
            <Input
              id="quarterly-report-category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
              placeholder={t('filter.allCategories')}
            />
          </div>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="quarterly-report-asins">{t('quarterlyReport.asins')}</Label>
          <textarea
            id="quarterly-report-asins"
            value={asinsText}
            onChange={(event) => setAsinsText(event.target.value)}
            rows={3}
            placeholder={t('quarterlyReport.asinsPlaceholder')}
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          />
          <p className={`text-xs ${tooManyAsins ? 'text-destructive' : 'text-muted-foreground'}`}>
            {t('quarterlyReport.asinsHint', { n: asins.length, max: MAX_ASINS })}
          </p>
        </div>

        <div>
          <Button
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending || accountIds.length === 0 || tooManyAsins}
          >
            {generateMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            {generateMutation.isPending ? t('quarterlyReport.generating') : t('quarterlyReport.generate')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
