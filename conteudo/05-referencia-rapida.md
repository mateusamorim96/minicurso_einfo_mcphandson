# Referência rápida

## Comandos

```bash
# ambiente
uv sync
uv sync --extra agent

# servidor
uv run python -m minicurso_einfo_mcphandson serve
uv run python -m minicurso_einfo_mcphandson serve --http --port 8000
uv run python -m minicurso_einfo_mcphandson serve --http --port 8000 --token segredo-lab
uv run mcp dev examples/hello_server.py
uv run mcp dev examples/esqueleto_server.py
uv run mcp run examples/agro_server.py
uv run mcp install examples/agro_server.py --name "AgroMCP"

# cliente
uv run python -m minicurso_einfo_mcphandson client demo
uv run python -m minicurso_einfo_mcphandson client tools
uv run python -m minicurso_einfo_mcphandson client --stdio demo
uv run python -m minicurso_einfo_mcphandson client --url http://127.0.0.1:8000/mcp demo
uv run python -m minicurso_einfo_mcphandson client --url http://127.0.0.1:8000/mcp --token segredo-lab demo
uv run python -m minicurso_einfo_mcphandson client call listar_talhoes '{"status":"atencao"}'

# testes
uv run pytest -q
uv run pytest --cov=minicurso_einfo_mcphandson --cov-report=term-missing
./scripts/smoke_inspector.sh

# hosts
opencode mcp list
opencode mcp add agro -- uv run --frozen python -m minicurso_einfo_mcphandson serve
```

## Imports que importam (SDK 2.x)

```python
from mcp import Client, StdioServerParameters, MCPError
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import (
    ToolError,
    ResourceError,
    ResourceNotFoundError,
)
from mcp.server.mcpserver.prompts.base import UserMessage, AssistantMessage, Message
from mcp.types import ElicitResult, ToolAnnotations
from mcp.client.streamable_http import streamable_http_client
```

> `from mcp.server.fastmcp import FastMCP` é SDK 1.x; não existe no 2.x.

## Esqueleto de servidor

```python
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import BaseModel, Field
from typing import Annotated, Literal

mcp = MCPServer("meu-servidor", version="1.0.0")


class Resposta(BaseModel):
    valor: int


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
def minha_tool(
    ctx: Context,
    nome: Annotated[str, Field(min_length=1, description="Nome do recurso")],
    modo: Literal["rapido", "completo"] = "rapido",
) -> Resposta:
    """Descrição que o modelo lê para decidir quando chamar."""
    return Resposta(valor=42)


@mcp.resource("meu://recurso/{id}", mime_type="application/json")
def meu_resource(id: str) -> str:
    """Resource template: {id} casa com o parâmetro id."""
    return '{"ok": true}'


@mcp.prompt()
def meu_prompt(tema: str) -> str:
    """Prompt escolhido pelo usuário."""
    return f"Explique {tema} em cinco linhas."


if __name__ == "__main__":
    mcp.run()  # stdio; para HTTP: mcp.run(transport="streamable-http", port=8000)
```

## Erros

| Situação | Exceção | Resultado |
|---|---|---|
| ID não encontrado, o modelo pode corrigir | `ToolError` | `is_error=True`, mensagem no content |
| Requisição inválida, o modelo não resolve | `MCPError(code, msg)` | erro JSON-RPC |
| Bug inesperado | qualquer outra | `is_error=True` genérico + traceback no log |
| Resource template inexistente | `ResourceNotFoundError` | `-32602` com URI em `data` |
| Argumento fora do schema | nenhuma (SDK valida) | `is_error=True` com detalhe |

## Context

```python
ctx.request_id
ctx.headers
ctx.session
await ctx.report_progress(0.5, 1.0, "metade")
partes = await ctx.read_resource("meu://recurso/1")   # async no SDK 2.3
app = ctx.request_context.lifespan_context
```

## Teste em memória

```python
from mcp import Client
from meu_servidor import create_server

async with Client(create_server(tmp_path / "t.db"), raise_exceptions=True) as c:
    result = await c.call_tool("minha_tool", {"nome": "x"})
    assert not result.is_error
    assert result.structured_content["valor"] == 42
```

## Hosts: chaves de configuração

| Host | Chave raiz | Tipo | Observação |
|---|---|---|---|
| Claude Desktop | `mcpServers` | — | Reinicie o app por completo |
| Cursor | `mcpServers` | — | `.cursor/mcp.json` |
| VS Code | `servers` | `"stdio"` | `.vscode/mcp.json`, Copilot Chat em Agent |
| OpenCode | `mcp.servers` | `"local"` | `opencode.json`, `opencode mcp list` |

## Diagnóstico de problemas

```bash
python --version                 # 3.11+
uv run mcp version               # SDK 2.x
node --version                   # 22.19+ para Inspector 2.13
uv run python -c "import mcp; print(mcp.__file__)"
```

- stdout é o protocolo em stdio: use `logging`, nunca `print`.
- O host não herda seu shell: passe `env` explicitamente.
- Caminho relativo é a causa mais comum de “servidor não aparece”.
- Depois de editar a config do host, reinicie-o.
- `MCP_INSPECTOR_SECRET_STORE=memory` evita keychain no Linux/container.

## Links

- SDK Python v2: <https://py.sdk.modelcontextprotocol.io/>
- Guia de migração v1 → v2: <https://py.sdk.modelcontextprotocol.io/migration/>
- Especificação 2026-07-28: <https://modelcontextprotocol.io/specification/2026-07-28>
- Segurança: <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices>
- Servidor local seguro: <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/local-server-security>
- Inspector: <https://github.com/modelcontextprotocol/inspector>
- FastMCP: <https://gofastmcp.com/>
- LangChain MCP: <https://docs.langchain.com/oss/python/langchain/mcp>
- OpenCode MCP: <https://opencode.ai/docs/mcp-servers/>
