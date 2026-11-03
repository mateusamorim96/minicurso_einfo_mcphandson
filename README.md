# MCP Hands-on: Expandindo o alcance de LLMs

Material completo do minicurso de 4 horas **MCP Hands-on**, com teoria, código
executável, testes ponta a ponta e configurações de hosts reais.

O laboratório constrói o **AgroMCP**, um servidor MCP de monitoramento agrícola
que expõe talhões, leituras de sensores, recomendações de irrigação e um catálogo
agronômico. O domínio é fictício, mas o desenho é o mesmo de um servidor de
produção: validação de entrada, banco local, recursos somente leitura, uma tool de
escrita, erros legíveis pelo modelo e testes em três transportes.

> **Versões verificadas em 2026-10-30:** Python 3.13 (mínimo 3.11), `mcp` 2.3.0,
> `fastmcp` 4.1.4, `langchain[mcp]` 1.4.7, MCP Inspector 2.13.0 e protocolo MCP
> `2026-07-28`. Os comandos e snippets foram executados neste repositório.

## Comece em 60 segundos

```bash
uv sync --extra agent
uv run python -m minicurso_einfo_mcphandson client demo
```

O comando conecta um `Client` ao servidor **em memória**, lista tools, resources
e prompts, chama as tools e mostra um erro que o modelo poderia corrigir.

O banco SQLite é criado em `data/agro.db` na primeira execução. Para resetar o
cenário, apague o arquivo ou aponte `AGRO_DB_PATH` para outro caminho.

Para abrir o servidor no Inspector:

```bash
uv run mcp dev examples/hello_server.py
```

Para subir o AgroMCP via Streamable HTTP:

```bash
uv run python -m minicurso_einfo_mcphandson serve --http --port 8000
# em outro terminal:
uv run python -m minicurso_einfo_mcphandson client --url http://127.0.0.1:8000/mcp demo
```

## Roteiro do curso

| Módulo | Tempo | Conteúdo | Material |
|---|---:|---|---|
| 1 | 45 min | Protocolo, arquitetura, primitivas e revisão 2026-07-28 | [`conteudo/01-fundamentos.md`](conteudo/01-fundamentos.md) |
| 2 | 1h15 | Servidor do zero: tools, resources, prompts, contexto, erros e Inspector | [`conteudo/02-servidor.md`](conteudo/02-servidor.md) |
| 3 | 1h15 | Cliente, transportes, hosts reais, LangChain e segurança | [`conteudo/03-integracao.md`](conteudo/03-integracao.md) |
| 4 | 45 min | Projeto orientado, produção e encerramento | [`conteudo/04-projeto-e-producao.md`](conteudo/04-projeto-e-producao.md) |

Extras:

- [`conteudo/05-referencia-rapida.md`](conteudo/05-referencia-rapida.md): cola de comandos, imports, erros e links.
- [`apostila.pdf`](apostila.pdf): apostila completa dos alunos gerada a partir de `conteudo/`.
- [`REFERENCIAS.md`](REFERENCIAS.md): fontes consultadas e o que foi verificado.

Para regenerar a apostila:

```bash
./scripts/build_apostila.sh
```

## O que está no repositório

```text
.
├── src/minicurso_einfo_mcphandson/
│   ├── server.py        # gabarito 100% pronto (MCPServer, Resolve/Elicit, TokenVerifier)
│   ├── db.py            # SQLite, schema e seed determinístico
│   ├── models.py        # modelos Pydantic de entrada/saída
│   ├── client.py        # cliente de demonstração (memória, stdio, HTTP, Elicitation)
│   ├── agent.py         # integração opcional com LangChain MCPAdapter
│   └── __init__.py      # CLI: serve / client
├── examples/
│   ├── hello_server.py      # servidor mínimo para o Inspector
│   ├── esqueleto_server.py  # esqueleto com TODOs 1–5 para o live coding do Módulo 2
│   └── agro_server.py       # wrapper de script para hosts
├── tests/
│   ├── test_server.py           # contrato em memória
│   ├── test_transports.py       # stdio + Streamable HTTP reais
│   ├── test_cli.py              # ponto de entrada
│   └── test_agent_integration.py# LangChain (extra agent)
├── hosts/               # exemplos de configuração de hosts
├── .vscode/mcp.json     # VS Code já configurado para o projeto
├── opencode.json        # OpenCode já configurado para o projeto
├── scripts/smoke_inspector.sh   # smoke test via Inspector CLI
├── Dockerfile           # laboratório offline
└── pyproject.toml
```

## Comandos úteis

```bash
# Sincronizar o ambiente principal
uv sync

# Sincronizar também a integração com agentes
uv sync --extra agent

# Testes (memória + stdio + HTTP + CLI + LangChain)
uv run pytest -q

# Cobertura
uv run pytest --cov=minicurso_einfo_mcphandson --cov-report=term-missing

# Inspector (interface web)
uv run mcp dev examples/hello_server.py

# Inspector (smoke test de terminal, fixa a versão)
./scripts/smoke_inspector.sh

# Servidor em HTTP (com ou sem Bearer token)
uv run python -m minicurso_einfo_mcphandson serve --http --port 8000
uv run python -m minicurso_einfo_mcphandson serve --http --port 8000 --token segredo-lab

# Cliente contra o HTTP
uv run python -m minicurso_einfo_mcphandson client --url http://127.0.0.1:8000/mcp demo
uv run python -m minicurso_einfo_mcphandson client --url http://127.0.0.1:8000/mcp --token segredo-lab demo

# Integração LangChain sem LLM (valida descoberta e chamada de tools)
uv run python -m minicurso_einfo_mcphandson.agent

# Integração LangChain com um modelo (configure a chave e o catálogo do provedor)
export AGRO_MODEL="provedor:modelo"
uv run python -m minicurso_einfo_mcphandson.agent \
  --model "$AGRO_MODEL" "Qual talhão exige atenção hoje?"
```

## Hosts reais

O projeto já inclui configurações prontas para dois hosts:

- **OpenCode:** `opencode.json` na raiz. Confirme com `opencode mcp list`; as tools
  do AgroMCP aparecem no agente.
- **VS Code:** `.vscode/mcp.json`. Abra a Command Palette e use **MCP: List
  Servers**; aceite o prompt de confiança e mantenha o Copilot Chat em modo Agent.

Exemplos para Claude Desktop, Cursor e OpenCode estão em [`hosts/`](hosts/).
Troque `/CAMINHO/ABSOLUTO/PROJETO` pelo caminho real antes de usar.

## Docker

```bash
docker build -t mcp-lab:1.0 .
docker run --rm -it --init --network host -v "$PWD":/workspace mcp-lab:1.0
```

Dentro do contêiner:

```bash
python -m minicurso_einfo_mcphandson client demo
pytest -q
npx @modelcontextprotocol/inspector --web python -m minicurso_einfo_mcphandson serve
```

A imagem já traz Python 3.13, `mcp` 2.3, FastMCP 4.1, LangChain 1.4, Node.js 22
e o Inspector 2.13. O laboratório funciona sem rede depois do build.

## Referências principais

- MCP Python SDK v2: <https://py.sdk.modelcontextprotocol.io/>
- Especificação MCP 2026-07-28: <https://modelcontextprotocol.io/specification/2026-07-28>
- MCP Inspector: <https://github.com/modelcontextprotocol/inspector>
- FastMCP 4: <https://gofastmcp.com/>
- LangChain MCP: <https://docs.langchain.com/oss/python/langchain/mcp>
- Segurança local de servidores MCP: <https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/local-server-security>

Lista completa e notas de verificação em [`REFERENCIAS.md`](REFERENCIAS.md).
