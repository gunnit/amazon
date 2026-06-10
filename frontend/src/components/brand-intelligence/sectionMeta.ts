import type { BrandIntelligenceSectionKey } from '@/types'

// Render order — the API may return sections in any order; we present them in
// the canonical intelligence-report sequence and append any unknown keys last.
// Titles come from the report payload (the model writes them).
export const SECTION_ORDER: BrandIntelligenceSectionKey[] = [
  'market_category',
  'brand_evolution',
  'competitor_activity',
  'opportunities',
  'risks',
  'product_trends',
  'strategic_recommendations',
]
