# Catalog Management audit — May 2026

## Why this audit

The Excel `Avanzamento tool Niuexa new.xlsx` marked the 4 catalog management
features (bulk listing updates, prices, availability, images) as 🔴 with the
note _"Da preview non è ancora integrata funzionalità"_. Inspecting the code
showed the skeleton was already in place but had real production gaps. This
branch (`claude/catalog-management-validation-and-polish`) closes those gaps.

## State before this branch

| Area | What existed | What was missing |
|------|--------------|------------------|
| `catalog_service.py` | `bulk_update_from_excel`, `update_prices_bulk`, `toggle_availability` with per-row try/except, returning dicts | Untyped responses; no audit trail; `update_prices_bulk` accepted bare `float`; no user attribution |
| `image_service.py` | MIME and size validation, S3 upload, SP-API patch | No audit log row when SP-API failed; `sp_api_error` returned but not persisted; no user attribution |
| `api/v1/catalog.py` | 10 endpoints with auth + account-in-org check | Inline Pydantic models with no validation (`price: float`, no ASIN regex); no history endpoint |
| `sp_api_client.py` | All listing-mutation methods implemented and decorated with `@with_throttle_retry` | (nothing missing) |
| Models | `Product`, `BSRHistory`, plus 17 unrelated models | No audit log table |
| Schemas | No `catalog.py` module | All catalog request/response shapes lived inline |
| Tests | 20 test files for other surfaces | Zero coverage of catalog services or endpoints |
| Frontend `Catalog.tsx` | 5 tabs, ~780 lines with 4 inline card functions | No `components/catalog/` directory; bulk results rendered as `<pre>{JSON.stringify(...)}</pre>`; no confirmations before destructive ops; weak validation; bulk response typed as `Record<string, unknown>` |
| i18n | Happy-path keys in en.ts + it.ts | No keys for errors, confirmations, per-row results, history |

## What this branch delivers

Mapped to the 4 features the Excel tracks:

### Aggiornamenti in massa liste prodotti (row 20)
- `BulkResult[BulkListingUpdateResult]` typed response with row numbers and `BulkErrorCode` (`invalid_input`, `sp_api_error`, `unexpected_error`).
- Audit log row per attempted change (success and failure).
- `BulkResultTable` UI with status badges + row numbers replaces the JSON dump.
- Confirmation dialog before the upload.
- Test: `test_bulk_update_from_excel_mixed_results` parses a real .xlsx with mixed outcomes; asserts audit writes and row numbers.

### Gestione prezzi (row 21)
- `PriceUpdate` Pydantic schema: `Decimal` with `ge=0` and `decimal_places=2`, ASIN regex `^[A-Z0-9]{10}$`, requires asin-or-sku. Frontend mirrors with Zod.
- `BulkPriceUpdateRequest` rejects empty `updates` array.
- `BulkResult[PriceUpdateResult]` with explicit `MISSING_SKU`, `PRODUCT_NOT_FOUND`, `SP_API_ERROR` codes.
- Confirmation dialog with row count before push.
- Audit log + new `GET /catalog/products/{asin}/history` endpoint.

### Aggiornamenti disponibilità (row 22)
- `AvailabilityUpdateRequest.quantity` constrained to non-negative integer.
- SP-API failure now raises `CatalogOperationError` but still records the failed attempt in `catalog_change_log` first.
- Explicit confirmation dialog on **disable** (destructive); enable is one-click.
- Zod ASIN validation client-side.

### Gestione immagini (row 23)
- Backend MIME and size validation (already existed) + Zod client-side rejection with per-file error messages instead of silent drop.
- Per-image audit log row with `field=image`, `new_value={main_image_url, other_image_urls, uploaded_keys}`.
- Confirmation dialog before "Push to Amazon listing".
- Banner separates "uploaded to S3 but SP-API failed" from full success.

### Cross-cutting
- New `catalog_change_log` table (migration `022_catalog_change_log`) keyed on `(account_id, asin, created_at desc)`. Indexed for organization-scoped queries.
- `frontend/src/components/catalog/` directory with extracted cards + `BulkResultTable` + `ConfirmDialog` + `types.ts`.
- 18 backend unit tests covering schemas, services, and ImageService (`backend/tests/test_catalog_service.py`).
- 38 new i18n keys in both `en.ts` and `it.ts`.

## Verification done locally

- `cd backend && ./venv/bin/python -m pytest tests/test_catalog_service.py` → 18/18 pass
- `cd frontend && ./node_modules/.bin/tsc --noEmit` → clean
- `cd frontend && ./node_modules/.bin/vite build` → builds (1.55 MB bundle, no errors)
- Excel verified: rows 20–23 emoji `🟢`, Note column updated

## Intentionally out of scope (gaps remaining)

These are honest carve-outs the user should know about:

1. **No transactional rollback across SP-API + local DB.** Local mirror is updated only after SP-API returns 2xx, but if the DB flush fails after that point, Amazon and the local DB drift. Acceptable because SP-API is the source of truth, but worth a follow-up.
2. **No granular per-action permissions.** Any user in the org with access to the page can push price/availability/image changes. A `can_edit_listings` flag on `OrganizationMember` would let admins restrict who can write.
3. **Image metadata not persisted in DB.** Image keys live only in S3; the catalog tables don't reference them. If S3 listing diverges from SP-API's view of images, only S3 has the data.
4. **History endpoint is account-scoped but not paginated.** `limit` parameter is capped at 500. For ASINs with many changes, a cursor-based pager would be needed.
5. **No live SP-API smoke test.** All tests mock the SP-API client. A human should run an end-to-end smoke against a real sandbox/seller account before this is trusted in production — see manual checklist below.

## Manual smoke test for staging

Before merging, exercise these against a real seller account in a staging environment:

- [ ] Download the bulk template, fill 2 rows (1 valid SKU, 1 invalid SKU), upload. Confirm BulkResultTable shows 1 OK and 1 error with `sp_api_error` code.
- [ ] Push a price change for a real ASIN. Confirm Amazon backend reflects the new price within the SP-API processing window.
- [ ] Disable an ASIN via the Availability tab. Confirm Amazon listing shows out-of-stock.
- [ ] Re-enable. Confirm listing is buyable again.
- [ ] Upload 2 images for an ASIN with `push_to_amazon=true`. Confirm S3 has the objects and Amazon listing shows the new main image.
- [ ] Hit `GET /catalog/products/{asin}/history?account_id=…` and confirm all 5 operations above appear as audit rows with correct `user_id`, `old_value`, `new_value`, `sp_api_status`.

## Multi-agent collision note

During this work, another agent on branch `claude/docs-alignment-and-internal-hardening` ran a broad `git add` that accidentally bundled this branch's 5 catalog files into their docs commit `9f12643`. They subsequently amended their commit to remove those files, so the contamination is cleaned up on their side. Files were re-applied on this branch in commit `4916ea5`. No further intervention needed.
