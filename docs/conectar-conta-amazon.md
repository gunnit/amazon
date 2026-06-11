# Como conectar uma conta Amazon nova no Inthezon

> Guia simples, escrito para o caso concreto da **Vignola**, mas vale para qualquer conta nova.
> Última verificação contra o código: 2026-06-09.

---

## TL;DR — o que falta para a Vignola

A conta **Vignola já existe** no Inthezon (foi criada com nome, tipo, marketplace e o login do portal), **mas está sem o `SP-API Refresh Token`**. Por isso o status dela é `PENDING` e ela **não puxa nenhum dado da Amazon**.

Falta **uma única coisa**: gerar o *refresh token* da Vignola na Amazon e colá-lo no Inthezon. Não precisa mexer em mais nada.

---

## Entenda os 2 "personagens" (é isso que costuma confundir)

| Personagem | O que é | Quem mexe |
|---|---|---|
| **O App (aplicação SP-API)** | A aplicação registrada na Amazon que tem `Client ID` + `Client Secret`. Vive na **conta de desenvolvedor** (`assistente42@inthezon.com`). **Já está configurada** no servidor do Inthezon. | Ninguém — já está pronto. |
| **A conta do vendedor (Vignola)** | O Seller Central da Vignola (login `assistente46@inthezon.com`). Ele precisa **autorizar o App**. Essa autorização gera o **Refresh Token** (começa com `Atzr\|...`). | **É aqui que você atua.** |

**Analogia:** o *App* é o aplicativo já instalado. O *Refresh Token* é a **chave** que aquele vendedor específico entrega ao app para ele entrar e ler os dados dele. Cada vendedor = uma chave própria. Dialcos e Bitron já têm a chave deles; a Vignola ainda não.

> ⚠️ Não confunda os dois e-mails:
> - `assistente42@inthezon.com` → conta **dona do App** (onde se gera/autoriza).
> - `assistente46@inthezon.com` → login do **Seller Central da Vignola** (o vendedor). Esse login já está guardado no Inthezon, mas serve só para o robô de portal — **não** é o que puxa dados via SP-API.

---

## Passo a passo

### Parte A — Gerar o Refresh Token na Amazon

Existem dois caminhos. O **Caminho 1** é o "simples" que você lembra (o token aparece na tela). Use o **Caminho 2** só se a Vignola for um Seller Central totalmente separado da conta do app.

#### Caminho 1 — Self-authorize (recomendado, mais simples)

**Link (não há deep-link estável; entra-se pelo menu):**
- Seller Central Itália: **https://sellercentral.amazon.it**
- (ou EU unificado: https://sellercentral-europe.amazon.com)

1. Entre no **Seller Central** com a conta dona do app: `assistente42@inthezon.com`.
2. Menu → **Apps and Services → Develop Apps** (em algumas contas aparece sob **Partner Network → Develop Apps**). Abre a página **"Developer Central"**. Esse menu só aparece para contas registradas como desenvolvedor.
3. No seu app, clique na **setinha ao lado de "Edit App"** → **Authorize / Autorizar**.
4. Clique em **"Authorize app"**. *(Cada clique gera um novo refresh token; os anteriores continuam válidos.)*
5. A Amazon mostra o **Refresh Token** na tela (string longa começando com `Atzr|...`). **Copie.**

> **Pré-requisitos (documentação oficial da Amazon):**
> - Você precisa ser o **"Primary User"** da conta Seller Central que está autorizando.
> - Um **app privado só aparece no "Develop Apps" da conta de desenvolvedor que o criou** (`assistente42`).
>
> Portanto, o Caminho 1 só entrega o token da **Vignola** se a `assistente42` também controlar/enxergar o Seller Central da Vignola. **Se a Vignola for uma conta separada** (com `assistente46` como primary user), o app não aparecerá no Develop Apps dela → **use o Caminho 2**.
>
> Ref.: https://developer-docs.amazon.com/sp-api/docs/self-authorization

#### Caminho 2 — Autorização OAuth (vendedor separado)

1. **(Você, dono do app)** Em **Develop Apps → seu app → Authorize**, copie a **URL de autorização** (o "website authorization workflow").
2. Entre no **Seller Central da Vignola** (`assistente46@inthezon.com`).
3. Abra aquela URL → aparece a tela de consentimento → clique **Authorize**.
4. A Amazon redireciona para a *redirect URI* do app com `spapi_oauth_code=...` na barra de endereço. **Copie esse código.**
5. Troque o código pelo refresh token (o Inthezon ainda **não** faz essa troca sozinho — é só este passo manual). No terminal:

   ```bash
   curl -X POST https://api.amazon.com/auth/o2/token \
     -d grant_type=authorization_code \
     -d code='<SPAPI_OAUTH_CODE>' \
     -d redirect_uri='<REDIRECT_URI_DO_APP>' \
     -d client_id='<AMAZON_SP_API_CLIENT_ID>' \
     -d client_secret='<AMAZON_SP_API_CLIENT_SECRET>'
   ```

   A resposta vem em JSON com o campo **`refresh_token`** (começa com `Atzr|...`). É esse valor que você usa no próximo passo.
   *(O `client_id` e `client_secret` são os mesmos do App; um dev tem acesso a eles no `backend/.env`.)*

---

### Parte B — Colar o token no Inthezon

> ⚠️ **Faça em PRODUÇÃO** — é o ambiente que a Gioia usa, e o token é criptografado com a chave daquele ambiente. Colar no local não conecta a prod.

1. Abra o Inthezon de produção: **https://inthezon-frontend.onrender.com** → faça login.
2. **Configurações (Settings) → aba Contas (Accounts)**.
3. Encontre a linha **"Vignola"** → clique no ícone de **chave 🔑** (botão *Reconnect SP-API*).
4. Cole o **Refresh Token** no campo **"SP-API Refresh Token"** → **Salvar**.
5. Confira: a coluna **SP-API** da Vignola deve mudar de **"Mancante / Missing"** para **"Connesso / Connected"**.

---

### Parte C — Puxar os dados

- Na conta Vignola, clique em **"Sincronizza / Sync"** para puxar os dados **agora**.
- Se não sincronizar na hora, a sincronização automática roda **todo dia às 02:00 UTC** (≈03:00–04:00 no horário da Itália).

---

## Como saber se deu certo

- ✅ Badge **SP-API = "Connesso/Connected"** na linha da Vignola.
- ✅ Depois do sync, aparecem **vendas / inventário / catálogo** da Vignola no dashboard.
- ❌ Se aparecer erro de credencial após salvar, normalmente é token errado/expirado, ou foi colado no ambiente errado (local em vez de prod).

---

## Detalhes técnicos (para o dev / fallback)

- O token é guardado **criptografado** (Fernet) em `amazon_accounts.sp_api_refresh_token_encrypted`.
- Caminho na UI = `PUT /accounts/{id}` com `{ "refresh_token": "Atzr|..." }` → o backend chama `encrypt_value()` (`backend/app/api/v1/accounts.py:303-304`).
- Identificadores da Vignola:
  - **Prod**: `4a391a63-43b0-4d2e-838d-6318b89fae22`
  - **Local**: `f668f40a-7e6f-4f5f-bda2-2a2fca0f54a2`
  - Tipo **SELLER**, país **IT**, marketplace **`APJ6JRA9NG5V4`**.
- **NÃO existe** botão "Login com Amazon" / OAuth dentro do Inthezon ainda — por isso o token é obtido na Amazon e colado manualmente (a própria UI avisa: *"OAuth pode ser adicionado depois; por ora use o refresh token autorizado"*).
- **Fallback sem UI** (foi assim que a Vignola foi criada): rodar um job em produção que faz `account.sp_api_refresh_token_encrypted = encrypt_value("<token>")` e dá commit. Mas o caminho da UI (Parte B) é mais simples e seguro.
- ⚠️ O *refresh token é específico do par vendedor+app*. O `AMAZON_SP_API_REFRESH_TOKEN` global do `.env` pertence a outro vendedor e **não** serve para a Vignola — por isso ela precisa do token dela.
