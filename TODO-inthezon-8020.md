# TODO — Inthezon 80/20 (pós-merge feat/inthezon-8020 → master @ 849b9ff)

Merge local feito, **não pushed** (alguns commits já em prod: `98f358a`). App rodando local. Este arquivo está **untracked**.

> **2026-06-04 — Investigação multi-agente (14 tasks) concluída.** Diagnóstico read-only feito por 14 agentes Opus 4.8. Resultados + plano de execução abaixo. Implementação em ondas, no working tree, **sem commit** (revisão primeiro).

### ✅ Progresso da implementação
- **Batch 1 — DONE & verificado** (todos com testes verdes):
  - **T1** ✅ `Layout.tsx` nav reativado (+ ícone Sparkles) · `tsc` ok · spec Playwright escrita (não rodada: dev server off).
  - **T11** ✅ handler `RequestValidationError`→422 em `main.py` · 3 testes pass (`test_validation_exception_handler.py`).
  - **T12** ✅ `_mask_arn()` em `auth.py:484` · 4 testes pass (`test_org_api_keys_masking.py`). Tb add `from __future__ import annotations` em `auth.py` (corrige import sob venv 3.9; no-op em prod 3.11).
  - **T13** ✅ fixtures corrigidas · 9 testes pass (returns 2 + ads-vs-organic 7) + comparison 3 pass.
  - **T14** ✅ migração `026_widen_alembic_version` → `varchar(255)` aplicada no DB local (width=255 confirmado, round-trip ok).
- **Batch 2 — DONE** (alembic head agora `027`):
  - **T6** ✅ import manual Vendor: migração `027_product_source` (col `products.source`) + `POST /catalog/import` + `GET /catalog/import/template` + `ImportCard` + aba "Importa". 28 testes pass, tsc ok.
  - **T4** ✅ catalog period-aware: `date_from/date_to`→`has_sales_in_period` (não filtra linhas, só flag) + resumo "X con vendite su Y sincronizzati" + badge "Senza vendite" + tooltip + empty-period. 4 testes pass, tsc ok.
  - **T7** 🟡 Partial: `fetch_merchant_listings()` (o relatório já era baixado mas descartado) + enumeração em `sync_products` p/ seller. 7 testes pass (mock SP-API). **Blocked external:** validar 52→62 precisa do token Bitron real no Render.
- **Achado novo:** `tests/test_accounts_summary.py` tem 2 falhas **pré-existentes** (assinatura `_load_account_metrics` 2 vs 4 args) — não introduzidas por nós. → corrigindo em T13b (Batch 3).
- **Nota:** rodar muitos testes importlib juntos pode colidir no registry do SQLAlchemy (pré-existente) — rodar arquivos isolados p/ sinal limpo. Validação final fará suíte por grupos.
- **Batch 3 — DONE:**
  - **T2** ✅ Forecast: bug `giorni`→`mesi` corrigido nos DOIS lados (Excel `forecast_export_service.py` agora bate com o PDF; frontend usa `mesi` p/ forecast mensal) + Popover explicando affidabilità (def + data_quality_notes) + empty state IA no export (mapeia 'credit balance too low'/'ANTHROPIC_API_KEY') + hint do paste de ASIN. 9 testes pass, tsc ok.
  - **T9** ✅ PowerPoint: bug "1 barra" resolvido (grain por range day/week/month + zero-fill + fallback p/ linhas não-sentinela) + deck 6→11 slides (top-20 em 2 slides, inventory, advertising c/ empty-state Ads, forecast, recommendations c/ degrade gracioso se Anthropic cair). Frontend parou de forçar `group_by:'month'`. 9 testes pass + smoke pptx 11 slides, tsc ok.
  - **T13b** ✅ `test_accounts_summary.py` corrigido (fixture 2→4 args; sem bug de prod). 7 pass.
- **Nota env local:** venv 3.9 não tinha `reportlab` (declarado em requirements, presente em prod 3.11) — instalado localmente só p/ rodar o teste; nenhum arquivo de source/requirements alterado.
- **Batch 4 — DONE:**
  - **T5** ✅ `EmptyState.tsx` reutilizável + Recommendations Anthropic→**502** limpo (`ai_provider_unavailable`, sem stack) + Advertising "In attesa dell'approvazione Amazon Ads API" + Market Research nota price-only + Catalog nota Vendor + ErrorBoundary esconde stack em prod. 4 testes pass, build ok.
  - **T10** ✅ `SENDGRID_FROM_EMAIL` agora efetivo em TODOS os paths (era hardcoded) + digest curto-circuita sem key + `GET /reports/email-status` + banner amber na UI. 5+4 testes pass, build ok.

### 🔬 Verificação consolidada (2026-06-04)
- **Frontend:** `tsc && vite build` ✅ (3373 módulos, build limpo).
- **Backend (rodado POR ARQUIVO p/ evitar colisão importlib pré-existente):** **25/29 arquivos 100% verdes** — inclui TODOS os nossos testes novos/alterados.
- **4 arquivos vermelhos = PRÉ-EXISTENTES (confirmado: falham idênticos no base limpo via `git stash`), NÃO regressão nossa:**
  - `test_notifications_worker.py` — importa `_format_age` que nunca existiu no HEAD.
  - `test_data_reconciliation.py` (2) — mocks `FakeDb`/`SimpleNamespace` sem `.execute`/`get_vendor_purchase_orders` (vendor sales fallback).
  - `test_returns_sync.py` (1) — `SimpleNamespace` sem `seller_id`.
  - `test_product_trends_service.py` (3) — drift de asserção na classificação de trends.
  - → fora do escopo das 14; ofereço corrigir como T13c se quiser.
- **Playwright:** specs escritas (T1 nav) mas e2e com dados não roda local — DB local é fixture vazia (1 conta, 1 linha 2026-02-03) e app não está de pé. Roda quando subir front+back+DB seeded.
- **Migrations:** alembic head local = `027_product_source` (chain 025→026→027 aplica limpo).

**STATUS FINAL:** 11/14 done · T7 partial (token Bitron) · T3 verify-only (prod) · T8 deferred (decisão Gioia).

### ✅ Pós-entrega (2026-06-04)
- **Code review** (agente Opus 4.8): `minor_fixes`, **security PASS** (0 secrets, ARN mascarado, SendGrid env-only, sem stack p/ user). 2 nits médios aplicados: catalog `has_sales_in_period` agora por `(account_id, asin)`; teste catalog usa imports reais (trio roda junto, 40 pass).
- **T13c** ✅: 4 testes pré-existentes corrigidos (7/7/5/9). `data_extraction.py`/`product_trends_service.py` NÃO alterados (só fixtures); 1 helper `_format_age` add.
- **Playwright** (live Docker stack 3.11): **ALL 6 FLOWS PASS** — login, Brand Analysis nav, Catalog "51 con vendite su 60 sincronizzati"+Importa, Forecast "Previsione a 1 mesi" (mesi!), Reports sem banner, Recommendations 502→empty-state gracioso. Screenshots em `test-results/qa-*.png`.
- **Migrações** aplicadas no DB Docker real: `025→026→027`, `products.source` ok, `alembic_version` width=255.
- **COMMIT:** `acf0221` em `master` (55 arquivos, +3658/-147). **NÃO pushed** (push = deploy prod no Render). `.env` confirmado gitignored; nenhum secret commitado.
- Stack Docker local **de pé**: frontend http://localhost:5173, login `peppepretto@gmail.com`/`QaTest123!`. Parar com `docker compose down`.

### ✅ T8 — hub "Performance" (2026-06-04, Variante A aprovada pelo usuário)
- `Reports.tsx`+`Analytics.tsx` → **fundidos** em `Performance.tsx` (6 abas, FilterBar compartilhado, composição — sem reescrever cálculo). Sidebar: 1 item "Performance". Rotas `/reports`+`/analytics`→`/performance`; `/analytics/product/:asin` preservada. Dashboard deep-links + back-link repontados.
- **Playwright ALL 7 PASS** (live): sidebar, 6 abas com dados reais (Panoramica €70.058,70/20.740 un), drill-down per-ASIN, Export modal (Excel/PPT/CSV), redirects. 0 erros de console. tsc+vite build limpos.
- **TODAS as 14 tasks agora resolvidas** (T8 era a última deferida). Commit T8 separado.

---

## 📋 Status das 14 tasks (pós-investigação)

| # | Task | Diagnóstico-chave | Esforço | Status |
|---|------|-------------------|---------|--------|
| T1 | Brand Analysis (reativar no menu) | 1 linha comentada em `Layout.tsx:37`; rota/i18n/backend já prontos | S | ✅ Ready |
| T2 | Forecast UX/clareza | paste de ASIN **já existe**; bug real = label `giorni`→`mesi` (Excel `forecast_export_service.py:322` + frontend) + explicar reliability + empty state IA | M | ✅ Ready |
| T3 | Dashboard date range / maio | **já corrigido** no master (`27a43b7`). Resíduo = bundle prod antigo **ou** falta de dados maio/2026 (prod sem sync auto) | S | 🔎 Verify-only |
| T4 | Catalog clarity | sem filtro de período hoje; add `date_from/date_to`→`has_sales_in_period` + labels "X con vendite su Y sincronizzati" | M | ⚠️ Decisão de label (default adotado) |
| T5 | Empty/error states | gap real = Recommendations IA-indisponível (mapear Anthropic→502) + padrão EmptyState | M | ✅ Ready (depois de T2/T4) |
| T6 | Vendor catalog import (CSV/Excel) | não existe import manual; add col `products.source` + migração **027** + endpoint `/catalog/import` + ImportCard | M | ✅ Ready |
| T7 | Bitron seller_id / SP-API listings | `seller_id` já auto-resolve; relatório `GET_MERCHANT_LISTINGS_ALL_DATA` já é baixado mas as linhas são **descartadas** → add `fetch_merchant_listings()` em `sync_products` | M | 🟡 Partial (precisa token Bitron real p/ validar 52→62) |
| T8 | Report + Analisi unificados | hub único **"Performance"** (Variante A, aprovada): Panoramica/Per ASIN/Resi/Ads vs Organic/Inventario/Export + redirects | L | ✅ Done |
| T9 | PowerPoint / chart bug | "1 barra" = `_sales_trend_rows` agrupa por mês + só lê `__DAILY_TOTAL__` + sem zero-fill. Fix: grain auto por range, zero-fill, fallback p/ linhas não-sentinela + enriquecer deck | M | ✅ Ready |
| T10 | Scheduled reports / email | já é resiliente; gaps = `from_email` hardcoded ignora `SENDGRID_FROM_EMAIL`; digest não curto-circuita sem key; add `/reports/email-status` + banner UI | M | ✅ Ready |
| T11 | 422 vira 500 | sem handler de `RequestValidationError`; default crasha ao serializar `PydanticUndefined`→ cai no handler 500. Add handler 422 robusto em `main.py` | S | ✅ Ready |
| T12 | IAM ARN masking backend | `auth.py:467` retorna `role_arn` cru em `_build_api_keys_response`; mascarado só no front. Add `_mask_arn()` | S | ✅ Ready |
| T13 | pytest quebrados | fixtures desatualizadas (não bug): `FakeResult` sem `.scalars()` + falta `AccountType`/`granularity` stub + execute counts | S | ✅ Ready |
| T14 | migrations / alembic_version | prod `varchar(32)`, local `64`. Add migração **026_widen_alembic_version**→`varchar(255)` + comentário-guia no template | S | ✅ Ready |

---

## 🌊 Plano de execução (ordenado por conflito de arquivos, não só por visibilidade)

**Batch 1 — independentes, paralelo (em curso):** T1 (`Layout.tsx`), T11 (`main.py`), T12 (`auth.py`), T13 (test files), T14 (migração 026). Zero overlap de arquivos. T14 cria a 026 (widen) **antes** de T6.

**Batch 2 — cadeia Catalog/DB (sequencial — Product model, `schemas/report.py`, `Catalog.tsx`, migração):** T6 (migração **027** `products.source` + import) → T7 (`fetch_merchant_listings` em `data_extraction.py`/`sp_api_client.py`) → T4 (contadores por período). Compartilham Product/catalog → serializar.

**Batch 3 — Forecast/Export (sequencial — i18n + forecast/export):** T2 → T9 (T9 embute forecast).

**Batch 4 — Infra email + empty states:** T10 (scheduled/email) ‖ T5 (empty states, **por último**, revisa páginas após T2/T4).

**Verify:** T3 (Playwright regression do range + checar dados prod). **Deferred:** T8 (aguardando Gioia).

### ⚠️ Conflitos a coordenar
- **Migração:** T14 = `026_widen_alembic_version` (down_revision `025_recommendation_confidence`) → T6 = `027_product_source` (down_revision `026_widen_alembic_version`). IDs ≤32 chars.
- **`Product` model / `schemas/report.py`:** T6 adiciona `source`; T4/T7 só leem. T6 primeiro.
- **`Catalog.tsx`:** T4 (filtro+resumo) e T6 (aba Importa) → sequencial.
- **`i18n/it.ts`+`en.ts`:** T2,T4,T5,T6,T10 adicionam keys → nunca em paralelo.
- **Sidebar `Layout.tsx`:** T1 (add Brand Analysis) e T8 (colapsar Report+Analisi) → T8 adiado, T1 livre.

---

## 🔌 Externo / ops (não-código — destrava entrega real) — INALTERADO
- [ ] **SendGrid:** verificar sender `noreply@niuexa.ai` (Domain Authentication DKIM/SPF no DNS de `niuexa.ai`). Sem isso → 403. T10 garante que o código fica resiliente e usa `SENDGRID_FROM_EMAIL` corretamente, mas o envio real depende disto.
- [ ] **SendGrid (prod):** `SENDGRID_API_KEY` + `SENDGRID_FROM_EMAIL` nas env vars do **Render** (hoje só `.env` local).
- [ ] **Anthropic API:** recarregar crédito — Recommendations + narrativa de Market Research + insights de export/forecast usam Claude (500 "credit balance too low"). T2/T5/T9 adicionam fallback/empty state claro.
- [ ] **Amazon Ads:** OAuth por conta + Partner Network (Gioia) — destrava PPC. UI fica pronta com empty state (T5/T9), sem dados falsos.
- [ ] **Catálogo completo (59→~80 / 52→~62):** T6 (import manual Vendor) + T7 (enumeração SP-API seller) atacam isto, mas T7 precisa de **token Bitron real** no Render p/ validar.
- [ ] **Google OAuth (Sheets):** bypass por ora.
- [ ] **Prod sem Redis/Celery:** scheduled reports/syncs não rodam sozinhos; só `Run now` (fallback in-process) e `/accounts/sync-all` manual.
- [ ] **`APP_FRONTEND_URL`** ainda localhost em prod → quebra links de reset; setar URL pública no Render.

## 🚀 Deploy de prod (Render)
- [x] `git push origin master` → deployado (commit `98f358a`, 2026-06-03). Migração 025 aplicada.
  - ⚠️ Lição: ids de migração ≤32 chars (prod `alembic_version varchar(32)`). T14 remove o limite de vez (→255).
- [ ] Após Batch 1: confirmar que o bundle prod do frontend inclui `27a43b7` (fix do date range) — senão Gioia testou build antigo (T3).
- [ ] Rodar `SELECT to_char(date,'YYYY-MM'), count(*) FROM sales_data GROUP BY 1` no **prod** p/ confirmar se maio/2026 existe (T3).
