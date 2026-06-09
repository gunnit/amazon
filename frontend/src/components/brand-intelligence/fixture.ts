import type { BrandIntelligenceReport } from '@/types'

// A fully-populated, typed sample report. The reader is built and verified
// against this so the UI is complete before the backend pipeline produces a
// real report. Toggle the import in BrandIntelligence.tsx during local work.
export const SAMPLE_REPORT: BrandIntelligenceReport = {
  id: 'sample-001',
  account_id: 'sample-account',
  brand_label: 'Zwilling',
  status: 'completed',
  generated_at: '2026-06-09T07:00:00Z',
  model: 'claude-opus-4-8',
  coverage_note:
    'Built from connected Seller Central sales plus public marketplace signals for the 7 days ending 8 Jun. Competitor pricing reflects the latest crawl, not intraday changes.',
  period: {
    start: '2026-06-02',
    end: '2026-06-08',
    previous_start: '2026-05-26',
    previous_end: '2026-06-01',
    week_label: 'Week 23 · 2–8 Jun 2026',
    window_days: 7,
  },
  exec_summary: {
    headline:
      'Revenue grew 12% on the back of the Pro knife block, but a competitor undercut on the flagship santoku and two hero ASINs slipped out of stock mid-week.',
    kpis: [
      { label: 'Revenue', value: '€48.2k', delta_percent: 12.4, trend: 'up' },
      { label: 'Units', value: '1,840', delta_percent: 8.1, trend: 'up' },
      { label: 'Avg. price', value: '€26.20', delta_percent: 4.0, trend: 'up' },
      { label: 'Buy Box win rate', value: '91%', delta_percent: -3.2, trend: 'down' },
    ],
  },
  sections: [
    {
      key: 'market_category',
      title: 'Market & category',
      narrative:
        'The premium kitchen-knives category expanded ~6% week-over-week, driven by an early Prime-season lift across cookware. Search demand for "damascus knife" rose sharply while generic "kitchen knife set" demand was flat.',
      delta: 6,
      items: [
        {
          title: 'Category demand up ~6% WoW',
          detail:
            'Aggregate glance views across the top 50 category ASINs rose from 412k to 437k week-over-week.',
          source: 'Marketplace search trends',
          confidence: 'medium',
          evidence: 'Glance-view index 437k vs 412k prior week',
        },
        {
          title: '"Damascus knife" breakout term',
          detail:
            'Long-tail demand for damascus-pattern blades is accelerating; you rank page 2 for it with one eligible ASIN.',
          source: 'Search trends',
          confidence: 'medium',
          evidence: 'Search popularity +34% WoW',
        },
      ],
    },
    {
      key: 'brand_evolution',
      title: 'Brand evolution',
      narrative:
        'Your share of category revenue ticked up to 14.2% from 13.1%. The Pro knife block carried most of the gain; the santoku line lost ground on price competitiveness.',
      delta: 8.4,
      items: [
        {
          title: 'Revenue share 14.2% (+1.1pt)',
          detail: 'Highest weekly share in the trailing quarter, led by the Pro 7-piece block.',
          source: 'Internal sales + category estimate',
          confidence: 'high',
          evidence: '€48.2k of an estimated €339k category total',
        },
      ],
    },
    {
      key: 'competitor_activity',
      title: 'Competitor activity',
      narrative:
        'Wüsthof dropped the price on its flagship santoku by 9% and won the Buy Box on a comparable ASIN for three days. A new private-label entrant launched an aggressively priced 15-piece set.',
      delta: null,
      items: [
        {
          title: 'Wüsthof cut santoku price 9%',
          detail:
            'Their comparable santoku moved from €89 to €81, undercutting your €84 listing and pulling Buy Box share.',
          source: 'Competitor price crawl',
          confidence: 'high',
          evidence: '€81 vs your €84 on the matched ASIN',
        },
        {
          title: 'New private-label 15-piece set',
          detail:
            'A new entrant listed a €59 block set with 40+ reviews already; watch for review velocity.',
          source: 'New-listing monitor',
          confidence: 'medium',
          evidence: 'Listed 4 Jun, 43 reviews by 8 Jun',
        },
      ],
    },
    {
      key: 'opportunities',
      title: 'Opportunities',
      narrative:
        'Two concrete openings this week: capture the "damascus knife" breakout term, and convert the Pro block momentum into a bundle.',
      delta: null,
      items: [
        {
          title: 'Bid up on "damascus knife"',
          detail:
            'You have an eligible ASIN ranking page 2; a modest sponsored-product push could capture rising demand cheaply before competitors notice.',
          source: 'Search trends + ads gap',
          confidence: 'medium',
          evidence: 'CPC est. €0.62, term +34% WoW',
        },
        {
          title: 'Bundle the Pro block + sharpener',
          detail:
            'Block buyers attach a sharpener 22% of the time at full price — a bundle could lift AOV without discounting.',
          source: 'Attach-rate analysis',
          confidence: 'medium',
          evidence: '22% sharpener attach on block orders',
        },
      ],
    },
    {
      key: 'risks',
      title: 'Risks',
      narrative:
        'Stock-outs on two hero ASINs and an eroding Buy Box win rate are the two things to act on before next week.',
      delta: null,
      items: [
        {
          title: 'Two hero ASINs went out of stock',
          detail:
            'The 7-piece block and the chef knife both hit zero on-hand mid-week, costing an estimated €3.1k in lost sales.',
          source: 'Inventory snapshot',
          confidence: 'high',
          evidence: '0 units 5–7 Jun on B07ABC / B07DEF',
        },
        {
          title: 'Buy Box win rate down 3.2pt',
          detail: 'Driven mainly by the santoku price gap above; recoverable with a price match.',
          source: 'Buy Box tracking',
          confidence: 'high',
          evidence: '91% vs 94.2% prior week',
        },
      ],
    },
    {
      key: 'product_trends',
      title: 'Product & trend movements',
      narrative:
        'The Pro block is the clear riser; the santoku and the paring-knife 2-pack are softening.',
      delta: null,
      items: [
        {
          title: 'Pro 7-piece block rising fast',
          detail: 'Revenue +41% WoW, now your single largest contributor.',
          source: 'Internal sales',
          confidence: 'high',
          evidence: '€11.3k vs €8.0k prior week',
        },
        {
          title: 'Santoku declining',
          detail: 'Units -18% WoW under competitor pricing pressure.',
          source: 'Internal sales',
          confidence: 'high',
          evidence: '212 vs 258 units',
        },
      ],
    },
    {
      key: 'strategic_recommendations',
      title: 'Strategic recommendations',
      narrative:
        'Prioritised for the coming week, highest-leverage first.',
      delta: null,
      items: [
        {
          title: 'Match the santoku price to €81 for 7 days',
          detail:
            'Recover Buy Box on the matched ASIN; the 3pt margin hit is smaller than the lost-sales run-rate.',
          source: 'Competitor price crawl',
          confidence: 'high',
          evidence: 'Wüsthof at €81; you at €84',
        },
        {
          title: 'Expedite replenishment on the two stocked-out ASINs',
          detail: 'Lost ~€3.1k in three days; a faster inbound avoids a repeat next week.',
          source: 'Inventory snapshot',
          confidence: 'high',
          evidence: '0 on-hand 5–7 Jun',
        },
        {
          title: 'Launch a "damascus knife" sponsored campaign',
          detail: 'Cheap entry now on a breakout term before competition intensifies.',
          source: 'Search trends',
          confidence: 'medium',
          evidence: 'Term +34% WoW, CPC est. €0.62',
        },
      ],
    },
  ],
}
