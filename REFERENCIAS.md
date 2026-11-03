# Referências e notas de verificação

**Data da verificação:** 2026-10-30.

## Versões usadas

| Componente | Versão | Como foi verificado |
|---|---|---|
| Python | 3.15.2 local; imagem Docker 3.13 | `python --version` |
| `mcp` | 2.3.0 | `uv run mcp version` / PyPI |
| `mcp-types` | 2.3.0 | `importlib.metadata.version` |
| `fastmcp` | 4.1.4 | `importlib.metadata.version` |
| `langchain` | 1.4.7 | `importlib.metadata.version` |
| `langchain-core` | 1.7.3 | idem |
| MCP Inspector | 2.13.0 | `npm view @modelcontextprotocol/inspector version`; smoke test |
| Node.js | 24.15.0 local; 22.x na imagem | `node --version` |
| Protocolo MCP | 2026-07-28 | `Client.protocol_version` nos testes |

## Fontes primárias

### MCP Python SDK v2

- Documentação: <https://py.sdk.modelcontextprotocol.io/>
- Getting started: <https://py.sdk.modelcontextprotocol.io/get-started/>
- What's new in v2: <https://py.sdk.modelcontextprotocol.io/whats-new/>
- Migration guide: <https://py.sdk.modelcontextprotocol.io/migration/>
- Repositório: <https://github.com/modelcontextprotocol/python-sdk>

Pontos confirmados na fonte e no código:

- `FastMCP` foi renomeado para `MCPServer`;
- o import é `from mcp.server import MCPServer`;
- campos dos tipos são snake_case (`is_error`, `input_schema`);
- `streamablehttp_client` foi substituído por `streamable_http_client`;
- `httpx`/`httpx-sse` foram substituídos por `httpx2`;
- opções de transporte ficam em `run()`, não no construtor;
- `ctx.read_resource` é assíncrono no 2.3;
- logging de protocolo está descontinuado (SEP-2577);
- o SDK atende clientes 2026-07-28 e legados.

### Especificação MCP

- Arquitetura: <https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture>
- Especificação: <https://modelcontextprotocol.io/specification/2026-07-28>
- Transportes: <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports>
- Segurança: <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices>
- Servidor local seguro: <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/local-server-security>
- Inspector: <https://github.com/modelcontextprotocol/inspector>
- Smoke test via CLI: <https://github.com/modelcontextprotocol/inspector/blob/main/docs/cli-smoke-testing.md>

### FastMCP 4

- Documentação: <https://gofastmcp.com/>
- Servidores: <https://gofastmcp.com/servers/server>
- Clientes: <https://gofastmcp.com/clients/client>
- O FastMCP 4 é a base do `MCPAdapter` do LangChain e uma alternativa standalone
  ao `MCPServer` do SDK oficial.

### LangChain

- MCP no LangChain: <https://docs.langchain.com/oss/python/langchain/mcp>
- Migração de `langchain-mcp-adapters`: <https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters>
- O repositório `langchain-mcp-adapters` está arquivado/descontinuado; o caminho
  atual é `langchain[mcp]` (namespace `langchain.mcp`), em beta na versão 1.4.

### Hosts

- Claude Desktop / VS Code / Cursor / Claude Code:
  <https://py.sdk.modelcontextprotocol.io/get-started/real-host/>
- OpenCode: <https://opencode.ai/docs/mcp-servers/>
- VS Code MCP: <https://code.visualstudio.com/docs/agent-customization/mcp-servers>

## O que foi executado neste repositório

```bash
uv sync --extra agent
uv run pytest -q
# 19 passed

uv run python -m minicurso_einfo_mcphandson client demo
# tools, resources, prompts, recomendações, diagnóstico e erro de tool

./scripts/smoke_inspector.sh
# initialize, tools/list, tools/call e resources/read: OK

opencode mcp list
# ✓ agro  connected

uv run python -m minicurso_einfo_mcphandson.agent
# descoberta e execução de tool via langchain.mcp.MCPAdapter: OK
```

Observações de campo:

- O `Client` do SDK negociou `2026-07-28`. O Inspector 2.13, por padrão,
  negociou `2025-11-25`; com `--protocol-era modern`, negociou `2026-07-28`.
  Os três caminhos funcionaram com o mesmo servidor.
- Resources fixos não aceitam parâmetro `Context` no SDK 2.3; apenas templates.
  O código foi ajustado e o erro está documentado no Módulo 2.
- O `langchain.mcp` emite `LangChainBetaWarning`; o material avisa e silencia a
  advertência apenas nos exemplos.

## Como reproduzir a checagem de versões

```bash
uv run python - <<'PY'
import importlib.metadata as m
for pkg in ("mcp", "mcp-types", "fastmcp", "langchain", "langchain-core"):
    print(pkg, m.version(pkg))
PY

curl -s https://pypi.org/pypi/mcp/json | python -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
npm view @modelcontextprotocol/inspector version
```
