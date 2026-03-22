import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { useTranslation } from '@/i18n'
import type { ProductSnapshot, CompetitorSnapshot } from '@/types'

interface RadarComparisonProps {
  product: ProductSnapshot
  competitors: CompetitorSnapshot[]
}

function normalize(value: number | null, max: number, invert = false): number {
  if (value == null || max === 0) return 0
  const normalized = Math.min(value / max, 1) * 100
  return invert ? 100 - normalized : normalized
}

export default function RadarComparison({ product, competitors }: RadarComparisonProps) {
  const { t } = useTranslation()

  // Compute competitor averages
  const avg = (field: keyof CompetitorSnapshot) => {
    const vals = competitors
      .map((c) => c[field] as number | null)
      .filter((v): v is number => v != null)
    return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
  }

  // Find max values for normalization
  const allProducts = [product, ...competitors]
  const maxPrice = Math.max(...allProducts.map((p) => p.price ?? 0), 1)
  const maxBsr = Math.max(...allProducts.map((p) => p.bsr ?? 0), 1)
  const maxReviews = Math.max(...allProducts.map((p) => p.review_count ?? 0), 1)

  const data = [
    {
      dimension: t('marketResearch.price'),
      product: normalize(product.price, maxPrice, true), // lower price = better
      competitors: normalize(avg('price') as number, maxPrice, true),
    },
    {
      dimension: t('marketResearch.bsr'),
      product: normalize(product.bsr, maxBsr, true), // lower BSR = better
      competitors: normalize(avg('bsr') as number, maxBsr, true),
    },
    {
      dimension: t('marketResearch.reviews'),
      product: normalize(product.review_count, maxReviews),
      competitors: normalize(avg('review_count') as number, maxReviews),
    },
    {
      dimension: t('marketResearch.rating'),
      product: (product.rating ?? 0) * 20, // 5.0 -> 100
      competitors: (avg('rating') as number) * 20,
    },
  ]

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data}>
        <PolarGrid />
        <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 12 }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
        <Radar
          name={t('marketResearch.yourProduct')}
          dataKey="product"
          stroke="hsl(var(--primary))"
          fill="hsl(var(--primary))"
          fillOpacity={0.3}
        />
        <Radar
          name={`${t('marketResearch.competitors')} avg`}
          dataKey="competitors"
          stroke="hsl(var(--destructive))"
          fill="hsl(var(--destructive))"
          fillOpacity={0.1}
        />
        <Legend />
      </RadarChart>
    </ResponsiveContainer>
  )
}
