# Inthezon MCP Distribution

Esta pasta agora contém duas camadas do MCP:

- `server.py` e os arquivos Python continuam como implementação legada local-first.
- `packages/` contém a nova distribuição em Node/TypeScript para empacotamento npm:
  - `@inthezon/shared-sdk`: cliente HTTP e persistência local de sessão
  - `@inthezon/mcp-cli`: CLI/TUI para login, setup e operação local
  - `@inthezon/mcp-server`: MCP local em `stdio` para Codex e Claude Code

## Arquitetura nova

1. O usuário instala o pacote npm.
2. Faz `login` ou `register` pela CLI.
3. Configura credenciais Amazon e conecta contas pela CLI.
4. O MCP local é iniciado com `inthezon mcp start`.
5. Codex e Claude Code falam com o MCP local.
6. O MCP local usa o backend HTTP autenticado; ele não acessa Postgres diretamente.

## Uso esperado

```bash
npm install
npm run build
npx inthezon
npx inthezon register
npx inthezon setup-amazon
npx inthezon connect-account
npx inthezon mcp config
```

## Observação

O backend existente já expõe os contratos principais usados por esta primeira versão:

- `/api/v1/auth/*`
- `/api/v1/accounts/*`
- `/api/v1/reports/*`
- `/api/v1/analytics/*`
- `/api/v1/catalog/*`
- `/api/v1/forecasts/*`

Esta migração não remove o servidor Python ainda; ela adiciona a nova trilha distribuível.
