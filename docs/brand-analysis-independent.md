# Brand Analysis — Independent Product Decision

Date: 2026-06-21

Brand Analysis is an independent Inthezon feature. We are not integrating Helium10/H10 as a required data source.

The canonical production flow is:

1. Use Inthezon internal Amazon/SP-API data from a connected account.
2. Enrich ASINs through the existing Market Research/SP-API path where Amazon exposes catalog, pricing, offer, review, rating, BSR or image fields.
3. Generate the Brand Analysis metrics, narrative and PPTX from Inthezon-controlled data and provenance.

Manual yearly exports remain a fallback only when internal account data is incomplete or unavailable. They are generic uploads, not a Helium10 integration commitment.

Legacy mode names such as `helium10`, `helium10_api` and `helium10_browser` may still appear in old database rows or compatibility types. They should be treated as backward-compatible aliases that route to manual upload. They must not be exposed as new product choices or planned as future integrations.

Product implication: any open item phrased as "automatic H10/Helium10 import" is closed by scope decision, not a pending engineering task.

## Scope of this decision (clarified 2026-07-27)

This document governs **Brand Analysis inputs only**, and is unchanged for them: no H10 as a Brand Analysis data source, no H10 upload mode.

It does **not** govern Market Research. A separate, customer-confirmed, complementary **fill-only** H10 integration exists there: competitor (non-owned) ASINs only, filling only fields SP-API cannot return for them, Amazon data always winning, every filled field tagged in `helium10_fields`, off unless credentials are configured. It is not a dependency and replaces nothing. See `00-ROADMAP.md` **C-11** and `../helium10-substitution-map.md`.
