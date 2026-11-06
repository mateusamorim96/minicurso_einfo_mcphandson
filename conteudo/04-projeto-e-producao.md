# Módulo 4 — Projeto orientado e produção

**Tempo:** 45 minutos · **Objetivo:** aplicar o aprendizado em uma extensão do
AgroMCP e revisar o que muda ao levar um servidor MCP para produção.

## 4.1 O caso AgroMCP

O servidor do laboratório é deliberadamente pequeno, mas cobre o ciclo completo:

```text
Host (OpenCode / VS Code / LangChain)
        |  stdio ou Streamable HTTP
        v
+----------------------------- AgroMCP ------------------------------+
|  MCPServer + lifespan                                              |
|  +-- Tools: listar, consultar, recomendar, diagnosticar, registrar |
|  +-- Resources: talhões, template por ID, catálogo, guia, resumo   |
|  +-- Prompts: análise, plano de irrigação, triagem                 |
|  +-- SQLite (schema + seed determinístico)                         |
+--------------------------------------------------------------------+
```

Decisões de projeto que valem discussão:

| Decisão | Por quê |
|---|---|
| SQLite local | Zero infraestrutura; o foco é o protocolo |
| Consultas parametrizadas | Nenhuma tool aceita SQL livre |
| `ToolError` para ID inexistente | O modelo pode corrigir e tentar de novo |
| Resource template por ID | Uma função serve qualquer talhão |
| Tool de escrita separada | Fácil de negar/confirmar no host |
| `read_only_hint` nas leituras | O host pode exibir risco corretamente |
| Seed determinístico | Laboratório reproduzível e testes estáveis |
| `AGRO_DB_PATH` | Isola testes e permite apontar para outro banco |

## 4.2 Projeto orientado (25 min)

Escolha **uma** extensão e entregue código + teste + evidência no host.

### Opção A — Alertas prioritários (recomendada)

Crie a tool:

```python
@server.tool(title="Alertas prioritários")
def alertas_prioritarios(
    ctx: Context,
    limite: Annotated[int, Field(ge=1, le=20)] = 5,
) -> list[Alerta]:
    """Retorna os talhões mais críticos, ordenados por risco."""
```

Regras:

- combine umidade abaixo do crítico, NDVI baixo, temperatura e observações de
  severidade alta;
- retorne um modelo Pydantic `Alerta` com `talhao_id`, `score`, `motivos` e
  `acao_sugerida`;
- inclua um teste que verifique a ordenação e o limite;
- conecte ao host e chame a tool.

### Opção B — Histórico de sensores

Crie `historico_ndvi(talhao_id, dias=7)` e um resource
`agro://talhoes/{talhao_id}/serie` com a série em CSV. Teste o template com um ID
válido e um inválido.

### Opção C — Relatório de safra

Crie um prompt `relatorio_safra(fazenda, periodo)` e uma tool
`resumo_por_fazenda(fazenda)` que agrega área, culturas e alertas. O prompt deve
instruir o modelo a citar números e separar fatos de hipóteses.

### Critérios de aceite

- [ ] a tool tem schema com descrições e limites;
- [ ] entradas inválidas retornam erro legível, não traceback;
- [ ] há pelo menos um teste automatizado;
- [ ] `uv run pytest -q` passa;
- [ ] a tool aparece no Inspector ou no host;
- [ ] nenhuma credencial ou caminho absoluto foi hardcoded no código.

## 4.3 O que muda em produção

### Transporte e escala

Para um servidor remoto, use **Streamable HTTP**:

```python
mcp.run(
    transport="streamable-http",
    host="0.0.0.0",
    port=8000,
    stateless_http=True,
)
```

- `stateless_http=True` cria um transporte novo por requisição, sem sessão
  persistente; facilita escala horizontal.
- Atrás de um proxy TLS, configure `transport_security` e os hosts permitidos
  para evitar DNS rebinding.
- Para muitas réplicas, eventos e notificações precisam de um event store
  compartilhado (Redis, por exemplo).
- Coloque um gateway/ingress com autenticação, rate limit e timeout.

### Autenticação e autorização (`TokenVerifier`)

- **Remoto:** OAuth 2.1 como resource server; valide assinatura, `iss`, `aud`,
  expiração e escopos. Não aceite token “qualquer um”.
- **Local:** não há OAuth; o controle é o sistema operacional, o contêiner e a
  política do host.
- **Multi-tenant:** o token identifica o tenant; nunca confie em um
  `tenant_id` vindo nos argumentos da tool.
- **Escopos por tool:** leitura, escrita e administração devem ser escopos
  distintos.
- **Auditoria:** registre `request_id`, usuário, tool, argumentos (com PII
  mascarada), resultado e latência.

No AgroMCP, `server.py` inclui um `StaticTokenVerifier` didático para proteger o
transporte Streamable HTTP quando `--token` (ou `AGRO_BEARER_TOKEN`) é informado:

```python
import hmac
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings


class StaticTokenVerifier(TokenVerifier):
    def __init__(self, expected_token: str) -> None:
        self.expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self.expected_token):
            return None
        return AccessToken(
            token=token,
            client_id="agro-http-client",
            scopes=["agro:read", "agro:write"],
            subject="operador-autenticado",
        )


server = MCPServer(
    "agro-mcp",
    token_verifier=StaticTokenVerifier(token),
    auth=AuthSettings(
        issuer_url="https://auth.agromcp.local",
        resource_server_url="http://127.0.0.1:8000/mcp",
        validate_token_resource=False,
    ),
)
```

Para testar no terminal:

```bash
uv run python -m minicurso_einfo_mcphandson serve --http --port 8000 \
  --token segredo-lab
# em outro terminal:
uv run python -m minicurso_einfo_mcphandson client \
  --url http://127.0.0.1:8000/mcp --token segredo-lab demo
```

Requisições sem cabeçalho `Authorization: Bearer segredo-lab` recebem
`HTTP 401 Unauthorized` (validado em `tests/test_transports.py`). Em produção,
substitua o comparador estático pela validação de JWT (JWKS, `iss`, `aud` e
`validate_token_resource=True`).

### Observabilidade

O SDK 2.x já traz propagação de OpenTelemetry por padrão (dependência
`opentelemetry-api`). Para ver traces, instale um SDK/exportador e configure o
coletor:

```python
# exemplo conceitual; o exporter depende da sua infraestrutura
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

trace.set_tracer_provider(TracerProvider())
```

Logs:

- stdio: sempre stderr;
- HTTP: JSON estruturado com `request_id`, `tool`, `duration_ms`, `status`;
- nunca logue segredos, tokens ou conteúdo sensível sem política de retenção.

### Resiliência

- timeouts em toda chamada externa;
- retry com backoff apenas em erros transitórios e operações idempotentes;
- circuit breaker para dependências instáveis;
- limite de tamanho de resposta e de entrada;
- degradação graciosa: se o catálogo cair, a tool de leitura deve explicar, não
  travar;
- health check separado do endpoint MCP.

### Versionamento

- versione o **schema** das tools; mudanças incompatíveis exigem nova tool ou
  nova versão do servidor;
- mantenha `serverInfo.version` coerente com o deploy;
- clients antigos podem não entender campos novos; adicione, não remova;
- documente o contrato (schemas gerados) no pipeline.

### Deploy

```dockerfile
# trecho ilustrativo
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra agent
CMD ["uv", "run", "--frozen", "python", "-m", \
     "minicurso_einfo_mcphandson", "serve", "--http"]
```

Checklist de release:

- [ ] imagem imutável com versões pinadas;
- [ ] usuário não-root;
- [ ] health check e readiness;
- [ ] variáveis/segredos fora da imagem;
- [ ] migrations de banco versionadas;
- [ ] logs e métricas coletados;
- [ ] política de timeout/rate limit no ingress;
- [ ] rollback testado;
- [ ] smoke test do Inspector/CLI no pipeline.

## 4.4 Segurança em uma página

| Pergunta | Resposta esperada |
|---|---|
| A tool aceita SQL/shell/caminho livre? | Não; operações específicas e parametrizadas |
| A tool de escrita é idempotente? | Sim, ou tem chave de idempotência |
| O host pede confirmação? | Sim, para `read_only_hint=False` |
| O banco usa usuário de menor privilégio? | Sim; leitura separada de escrita |
| Segredos estão no código/config versionado? | Não; env/secret store |
| Token remoto é validado com `aud`/`iss`? | Sim |
| Logs têm PII/segredos? | Não, ou mascarados com retenção definida |
| Servidor de terceiros roda isolado? | Sim, contêiner/VM com rede mínima |
| Catálogo de tools foi revisado? | Sim; descrições são instruções para o modelo |
| Há teste para entrada inválida e erro de dependência? | Sim |

## 4.5 Avaliação final e próximos passos

Rode a bateria completa:

```bash
uv run pytest -q
./scripts/smoke_inspector.sh
uv run python -m minicurso_einfo_mcphandson client demo
opencode mcp list
```

Se o OpenCode estiver conectado, peça em uma sessão:

> “Liste os talhões em atenção, diagnostique o mais crítico e proponha um plano
> de irrigação. Não execute nenhuma ação de escrita.”

Observe no transcript:

- o modelo escolheu as tools certas?
- citou os números retornados?
- separou fatos de hipóteses?
- pediu confirmação antes de escrever?
- inventou algum dado?

### Para continuar

- **FastMCP 4:** composição de servidores, auth embutida, apps interativos,
  middleware, providers e tool search.
- **MCP Apps:** devolver UI interativa em vez de texto.
- **Avaliação:** crie um dataset de perguntas e rubricas; meça acurácia de
  seleção de tool, qualidade da resposta e taxa de confirmação.
- **Observabilidade:** traces ponta a ponta host → tool → banco.
- **Registro de servidores:** catálogo interno com dono, versão, escopos e
  política de revisão.

## 4.6 Encerramento

MCP padroniza o que antes era um conector artesanal por aplicação. O ganho não
vem de “ter uma tool”, mas de **contratos claros, validação, erros legíveis,
testes e limites de segurança**. Um servidor pequeno, observável e fácil de
remover vale mais do que um monorepo de tools sem dono.

Obrigado! Leve o [`05-referencia-rapida.md`](05-referencia-rapida.md) para a
semana seguinte.
