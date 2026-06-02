# Inthezon — Checklist de provisionamento para entrega

Itens que **a empresa precisa fornecer** antes do deploy de produção. Cada um vira uma variável de ambiente no serviço de backend (e worker) no Render.

> Sem estes itens o app sobe, mas funcionalidades específicas falham (e-mail, Ads, jobs em background). Os itens de código já foram resolvidos do nosso lado.

---

## 1. SendGrid (e-mail) — OBRIGATÓRIO
Sem isto, **todo e-mail do app não é enviado**: reset de senha, entrega de relatórios agendados, e-mails de alerta e digest diário.

- [ ] Criar conta no SendGrid
- [ ] Gerar uma **API Key** (permissão Mail Send)
- [ ] Verificar um remetente: **Single Sender** ou **Domain Authentication** (recomendado autenticar o domínio)

Variáveis:
```
SENDGRID_API_KEY=<a key gerada>
SENDGRID_FROM_EMAIL=<e-mail remetente verificado>   # ex: noreply@seudominio.com
```

## 2. Amazon Advertising API — OBRIGATÓRIO se for usar dados de Ads
O código do cliente está pronto; falta credencial. (SP-API e Vendor já estão com credenciais válidas.)

- [ ] Ter/ criar um **app na Amazon Advertising API** (client id + secret)
- [ ] Obter o **Profile ID** da conta de publicidade
- [ ] Autorizar OAuth por conta (gera o refresh token de advertising por conta)

Variáveis:
```
AMAZON_ADS_CLIENT_ID=<client id do app de Advertising>
AMAZON_ADS_CLIENT_SECRET=<client secret>
AMAZON_ADS_PROFILE_ID=<profile id>            # pode também ser por conta no app
AMAZON_ADS_API_BASE_URL=                       # opcional; o cliente já tem defaults por região (NA/EU/FE)
```

## 3. Redis (fila de tarefas e cache) — OBRIGATÓRIO
Necessário para Celery (worker + beat), relatórios agendados, alertas, digests e cache. Sem Redis, os jobs em background não rodam e `/health/ready` falha.

- [ ] Provisionar um Redis gerenciado (Render Redis, AWS ElastiCache, Redis Cloud, etc.)

Variáveis (podem apontar para a mesma instância em DBs diferentes):
```
REDIS_URL=redis://:<senha>@<host>:6379/0
CELERY_BROKER_URL=redis://:<senha>@<host>:6379/1
CELERY_RESULT_BACKEND=redis://:<senha>@<host>:6379/2
```

## 4. Google OAuth — OPCIONAL (só para o sync de Google Sheets)
Se a feature de Google Sheets for usada. Caso contrário, pode deixar em branco (a tarefa apenas falha em runtime; não derruba o app).

- [ ] Criar credenciais OAuth no Google Cloud Console
- [ ] Configurar a Redirect URI apontando para o backend

Variáveis:
```
GOOGLE_CLIENT_ID=<...>
GOOGLE_CLIENT_SECRET=<...>
GOOGLE_REDIRECT_URI=https://<backend-prod>/api/v1/google/oauth/callback
```

---

## 5. Variáveis de produção que o nosso hardening agora exige
Não dependem de terceiros, mas **precisam estar setadas no ambiente de produção**:

```
APP_ENV=production
APP_DEBUG=false
JWT_SECRET_KEY=<string aleatória forte, >= 32 chars>   # o app RECUSA iniciar em produção sem isto
APP_FRONTEND_URL=https://<frontend-prod>               # usado nos links de reset de senha
ENCRYPTION_KEY=<já existente; manter o mesmo entre deploys>
DATABASE_URL=<postgres de produção>
```
Gerar um JWT_SECRET_KEY forte:
```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Não é necessário (decisão tomada)
- **AWS S3** — imagens e artefatos ficam no armazenamento do Render após o deploy. Nenhuma credencial AWS/S3 é necessária.
