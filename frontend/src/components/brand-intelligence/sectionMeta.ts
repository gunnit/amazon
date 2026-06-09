import {
  AlertTriangle,
  Globe,
  Lightbulb,
  Swords,
  Target,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import type { BrandIntelligenceSectionKey } from '@/types'

// One ordered map: section key → icon. Titles come from the report payload
// (the model writes them), so they are not duplicated here.
export const SECTION_META: Record<BrandIntelligenceSectionKey, { icon: LucideIcon }> = {
  market_category: { icon: Globe },
  brand_evolution: { icon: TrendingUp },
  competitor_activity: { icon: Swords },
  opportunities: { icon: Lightbulb },
  risks: { icon: AlertTriangle },
  product_trends: { icon: TrendingUp },
  strategic_recommendations: { icon: Target },
}

// Render order — the API may return sections in any order; we present them in
// the canonical intelligence-report sequence and append any unknown keys last.
export const SECTION_ORDER: BrandIntelligenceSectionKey[] = [
  'market_category',
  'brand_evolution',
  'competitor_activity',
  'opportunities',
  'risks',
  'product_trends',
  'strategic_recommendations',
]
