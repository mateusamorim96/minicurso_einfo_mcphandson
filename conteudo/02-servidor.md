# Módulo 2 — Construindo seu primeiro MCP Server

**Tempo:** 1h15 · **Objetivo:** construir o AgroMCP com tools, resources,
prompts, contexto, erros e testes no Inspector.

## 2.1 Setup

Requisitos: Python 3.11+ e `uv` (recomendado) ou `pip`.

```bash
# a partir da raiz do repositório
uv sync
uv run python --version      # 3.11+ (o laboratório foi validado em 3.13/3.15)
uv run mcp version
```

O pacote `mcp[cli]` instala o SDK e o comando `mcp` (`dev`, `run`, `install`,
`version`). O extra `agent` adiciona LangChain e FastMCP:

```bash
uv sync --extra agent
```

> **SDK 2.x:** o import de alto nível mudou. O antigo
> `from mcp.server.fastmcp import FastMCP` não existe mais. Use
> `from mcp.server import MCPServer`. O decorator `@mcp.tool()` continua igual.
> O FastMCP 4 standalone (`pip install fastmcp`) é outro projeto, mantido pela
> Prefect, e serve de base para o adaptador do LangChain.

## 2.2 O servidor mínimo

Arquivo [`examples/hello_server.py`](../examples/hello_server.py):

```python
from mcp.server import MCPServer

mcp = MCPServer("Hello MCP")


@mcp.tool()
def somar(a: int, b: int) -> int:
    """Soma dois números inteiros."""
    return a + b


@mcp.resource("curso://boas-vindas/{nome}")
def boas_vindas(nome: str) -> str:
    """Mensagem de boas-vindas personalizada."""
    return f"Olá, {nome}! Este resource veio do seu primeiro servidor MCP."


@mcp.prompt()
def explicar_tool(nome_tool: str) -> str:
    """Pede ao modelo uma explicação didática de uma tool."""
    return (
        f"Explique em português, em no máximo cinco linhas, o que a tool "
        f"{nome_tool} faz e quando um agente deveria chamá-la."
    )


if __name__ == "__main__":
    mcp.run()
```

Rode no Inspector:

```bash
uv run mcp dev examples/hello_server.py
```

O Inspector inicia o arquivo como subprocesso (**stdio**), abre a UI em
`http://localhost:6274` e mostra uma aba por primitiva. Em **Tools**, chame
`somar` com `a=1, b=2`; o formulário foi gerado a partir dos type hints. Em
**Resources**, expanda o template `curso://boas-vindas/{nome}` e leia
`curso://boas-vindas/Ana`. Em **Prompts**, renderize `explicar_tool`.

O que você **não** escreveu: JSON Schema, parser de requisição, roteamento,
declaração de capacidades, framing JSON-RPC. O SDK fez isso.

## 2.3 Tools: o contrato são os tipos

No AgroMCP, uma tool de leitura:

```python
@server.tool(
    title="Consultar talhão",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
)
def consultar_talhao(
    talhao_id: Annotated[
        str,
        Field(
            description="Identificador do talhão, no formato T-000.",
            pattern=r"^T-\d{3}$",
        ),
    ],
    ctx: Context,
) -> TalhaoDetalhe:
    """Retorna a ficha completa de um talhão e suas últimas leituras."""
    return _talhao_ou_erro(ctx, talhao_id)
```

O SDK deriva:

- **nome** da função;
- **descrição** da docstring;
- **inputSchema** dos type hints e `Field(...)`;
- **outputSchema** do tipo de retorno;
- **annotations** do decorator.

### Parâmetros opcionais e validação

```python
def listar_talhoes(
    ctx: Context,
    cultura: Literal["uva", "manga", "melo", "cana"] | None = None,
    status: Literal["ativo", "atencao", "inativo"] | None = None,
) -> list[TalhaoResumo]:
    ...
```

- um valor padrão remove o campo de `required`;
- `Literal` vira `enum` no schema;
- `Field(ge=1, le=14)` vira `minimum`/`maximum`;
- `Field(pattern=...)` vira `pattern`;
- `Annotated[str, Field(description=...)]` documenta o campo para o modelo.

Se o cliente mandar `horizonte_dias=99`, o SDK rejeita **antes** da função
rodar e devolve um erro legível:

```text
Input should be less than or equal to 14
```

Esse erro volta como resultado `is_error=True`, e o modelo pode corrigir e
tentar de novo. Você não escreve `if` para validar tipo.

### Síncrono ou assíncrono?

- `def` para CPU leve e SQLite local; o SDK executa em worker thread.
- `async def` para I/O de rede, banco assíncrono ou quando precisar de
  `ctx.report_progress`, `ctx.elicit`, etc.

### Modelos como parâmetro

Em vez de dez parâmetros soltos, agrupe em um `BaseModel`:

```python
class FiltroTalhao(BaseModel):
    cultura: Literal["uva", "manga", "melo", "cana"] | None = None
    status: Literal["ativo", "atencao", "inativo"] | None = None
    area_min_ha: float = Field(default=0, ge=0)
```

O schema do modelo é aninhado em `$defs`, e a função recebe uma instância já
validada. O mesmo vale para listas de modelos.

## 2.4 Saída estruturada

O tipo de retorno não é decoração: ele gera o `outputSchema` e o
`structuredContent`.

```python
class RecomendacaoIrrigacao(BaseModel):
    talhao_id: str
    necessidade_total_mm: float = Field(ge=0)
    prioridade: Literal["baixa", "media", "alta"]
    recomendacoes: list[str]
    alertas: list[str]
```

Ao chamar a tool, o cliente recebe duas visões:

```python
result.content             # texto que o MODELO lê
result.structured_content  # dicionário que a APLICAÇÃO lê
result.is_error            # falha?
```

Regras práticas do SDK 2.x:

- `BaseModel`, `TypedDict`, dataclass e `dict[str, ...]` viram objeto JSON;
- `str`, `int`, `float`, `bool`, `None` e listas são embrulhados em
  `{"result": ...}`;
- o retorno é validado contra o schema antes de sair do servidor;
- uma lista vira vários blocos de texto para o modelo, mas um único
  `structuredContent`.

No AgroMCP, `listar_talhoes -> list[TalhaoResumo]` produz
`{"result": [...]}`; `consultar_talhao -> TalhaoDetalhe` produz o objeto direto.
Isso é intencional e aparece nos testes.

## 2.5 Resources: dados endereçados

Um resource fixo:

```python
@server.resource(
    "agro://talhoes",
    mime_type="application/json",
    description="Lista resumida de todos os talhões, em JSON.",
)
def recurso_talhoes() -> str:
    dados = [
        t.model_dump(mode="json")
        for t in AgroDB(caminho_banco).listar_talhoes()
    ]
    return json.dumps(dados, ensure_ascii=False, indent=2)
```

Um template:

```python
@server.resource(
    "agro://talhoes/{talhao_id}",
    mime_type="application/json",
)
def recurso_talhao(talhao_id: str, ctx: Context) -> str:
    talhao = _db(ctx).obter_talhao(talhao_id)
    if talhao is None:
        raise ResourceNotFoundError(f"Talhão {talhao_id!r} não encontrado.")
    return talhao.model_dump_json(indent=2)
```

O `{talhao_id}` do URI **precisa** casar com o parâmetro `talhao_id`. Se você
renomear um dos dois, o servidor falha no import:

```text
ValueError: Mismatch between URI parameters {'talhao_id'}
           and function parameters {'talhao'}
```

### Uma pegadinha real do SDK 2.3

Resources **fixos** não aceitam injeção de `Context`; apenas templates aceitam.
Tentar registrar `def recurso_talhoes(ctx: Context)` em `agro://talhoes` falha
no import com:

```text
ValueError: Resource 'agro://talhoes' has no URI template variables, but the
handler declares a Context parameter.
```

Por isso o código abre o banco pelo caminho configurado nos resources fixos e
usa `ctx` apenas no template. É um detalhe que só aparece quando testamos — e
por isso o curso enfatiza rodar o servidor, não só ler a documentação.

### O que retornar

- `str`: texto puro;
- `dict`/`list`/modelo: o SDK serializa para JSON **texto**; declare
  `mime_type="application/json"`;
- `bytes`: vira `BlobResourceContents` em base64;
- `read_resource` só executa ao ler o URI concreto; listar é barato.

## 2.6 Prompts: fluxos escolhidos pelo usuário

```python
@server.prompt(title="Analisar talhão")
def analise_talhao(talhao_id: str, foco: str = "irrigação") -> list[Message]:
    """Prepara uma análise com dados e critérios explícitos."""
    return [
        UserMessage(
            f"Analise o talhão {talhao_id} com foco em {foco}. "
            "Use as tools do AgroMCP para consultar a ficha e o histórico. "
            "Separe fatos observados de hipóteses e cite os números usados."
        ),
        AssistantMessage(
            "Vou consultar os dados do talhão e cruzar umidade, NDVI, "
            "observações de campo e necessidade hídrica antes de recomendar "
            "qualquer ação."
        ),
    ]
```

- argumentos são **sempre strings** (use `"7"`, não `7`);
- retornar `str` gera uma mensagem de usuário;
- retornar `list[Message]` permite semear uma conversa com turnos de assistente;
- `UserMessage`/`AssistantMessage` vêm de
  `mcp.server.mcpserver.prompts.base`;
- prompt não é tool: não há chamada do modelo, é o usuário que escolhe.

## 2.7 Context e ciclo de vida

Um parâmetro anotado como `Context` é injetado e **não aparece no schema**:

```python
async def diagnosticar_talhao(
    talhao_id: str, ctx: Context
) -> DiagnosticoTalhao:
    await ctx.report_progress(0.1, 1.0, "Carregando catálogo")
    catalogo = await _ler_catalogo(ctx)
    ...
```

O que o `Context` oferece:

| Membro | Uso |
|---|---|
| `request_id` | Identificador da requisição |
| `report_progress(p, total, msg)` | Progresso para o cliente |
| `read_resource(uri)` | Ler um resource do próprio servidor (**async**) |
| `request_context.lifespan_context` | Objeto criado no startup |
| `notify_tools_changed()` | Notifica clientes 2026-07-28 sobre mudança na lista |
| `session` | Canal direto para clientes legados (`send_*_list_changed`) |
| `headers` | Cabeçalhos HTTP (None em stdio) |

### Lifespan

O banco é aberto uma vez no startup e compartilhado:

```python
@dataclass
class AppContext:
    db: AgroDB


@asynccontextmanager
async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
    db = AgroDB(caminho_banco)
    db.initialize()
    yield AppContext(db=db)


server = MCPServer("agro-mcp", lifespan=lifespan)
```

Dentro de uma tool:

```python
def _db(ctx: Context) -> AgroDB:
    app = cast(AppContext, ctx.request_context.lifespan_context)
    return app.db
```

Isso evita abrir conexão a cada chamada e dá um lugar natural para pools,
clientes HTTP e telemetria. Em produção, cuidado com o ciclo de vida em
múltiplos workers: cada processo tem o seu.

### Logging

A capacidade de **logging do protocolo foi descontinuada** na revisão
2026-07-28 (SEP-2577). `ctx.info()` ainda existe para clientes antigos, mas
emite `MCPDeprecationWarning`. O caminho atual é `logging` local (stderr) ou
OpenTelemetry:

```python
logger = logging.getLogger("agro_mcp")
logger.info("Diagnóstico de %s concluído: %s", talhao_id, classificacao)
```

Em stdio, **nunca** escreva logs em stdout: stdout é o protocolo. `print()` pode
corromper a conexão.

### Confirmação humana no protocolo: `Resolve` + `Elicit`

Nem todo parâmetro de uma tool deve vir do modelo. No SDK 2.x, um parâmetro
anotado com `Annotated[T, Resolve(fn)]` fica **invisível no `inputSchema`** e é
preenchido pela função `fn` antes de o corpo da tool executar. Se `fn` retornar
`Elicit(mensagem, SchemaPydantic)`, o SDK solicita confirmação humana ao cliente
(tanto por *multi-round-trip* no protocolo `2026-07-28` quanto pelo canal legado):

```python
class ConfirmacaoObservacao(BaseModel):
    confirmado: bool = Field(description="Confirma a gravação?")
    responsavel: str = Field(default="agrônomo-de-plantão")


def _confirmar_alta_severidade(
    talhao_id: str,
    severidade: Severidade,
) -> ConfirmacaoObservacao | Elicit[ConfirmacaoObservacao]:
    if severidade == "alta":
        return Elicit(
            "Confirmar registro de observação de ALTA severidade "
            f"no talhão {talhao_id}?",
            ConfirmacaoObservacao,
        )
    return ConfirmacaoObservacao(confirmado=True, responsavel="automático")


@server.tool(title="Registrar observação de campo")
async def registrar_observacao(
    talhao_id: Annotated[str, Field(pattern=r"^T-\d{3}$")],
    texto: Annotated[str, Field(min_length=10, max_length=500)],
    severidade: Severidade,
    confirmacao: Annotated[
        ConfirmacaoObservacao,
        Resolve(_confirmar_alta_severidade),
    ],
    ctx: Context,
) -> ObservacaoRegistrada:
    if not confirmacao.confirmado:
        raise ToolError(
            "Gravação cancelada: o responsável não confirmou a operação."
        )
    ...
```

- para severidade `baixa` ou `media`, o resolver devolve `ConfirmacaoObservacao`
  direto, sem interromper ninguém;
- para severidade `alta`, o cliente/host recebe o formulário; se o usuário
  recusar, a tool não grava no banco.

## 2.8 Erros: três caminhos

| O que você faz | O que o cliente vê | Quando usar |
|---|---|---|
| `raise ToolError("...")` | `is_error=True`, mensagem no `content` | O modelo pode corrigir (ID errado, título inexistente) |
| `raise MCPError(code, "...")` | Erro JSON-RPC, sem resultado | A requisição em si é inválida; o modelo não resolve |
| Qualquer outra exceção | `is_error=True` com mensagem genérica | Bug; o traceback fica no log do servidor |
| `ResourceNotFoundError` | `-32602` com o URI em `data` | Resource template que não existe |

```python
if talhao is None:
    raise ToolError(
        f"Talhão {talhao_id!r} não encontrado. "
        "Use listar_talhoes para descobrir os IDs disponíveis."
    )
```

A pergunta de decisão: **um modelo mais esperto evitaria esse erro?** Sim →
`ToolError`; não → `MCPError`.

Nunca retorne uma string de erro como sucesso. Um retorno normal tem
`is_error=False`, e o modelo vai tratar o texto como resposta válida.

## 2.9 Inspector: interface e CLI

Interface:

```bash
uv run mcp dev examples/hello_server.py
```

CLI (útil para smoke tests e CI; fixe a versão):

```bash
npx --yes @modelcontextprotocol/inspector@2.13.0 --cli \
  .venv/bin/python -m minicurso_einfo_mcphandson serve \
  --method tools/list --format json
```

Chamada de tool:

```bash
npx --yes @modelcontextprotocol/inspector@2.13.0 --cli \
  .venv/bin/python -m minicurso_einfo_mcphandson serve \
  --method tools/call \
  --tool-name recomendar_irrigacao \
  --tool-args-json '{"talhao_id":"T-002","horizonte_dias":7}' \
  --format json
```

O script [`scripts/smoke_inspector.sh`](../scripts/smoke_inspector.sh) encadeia
`initialize`, `tools/list`, `tools/call` e `resources/read` com `jq -e`.

> **Detalhe observado:** por padrão, o Inspector 2.13 negociou `2025-11-25`
> com o nosso servidor; com `--protocol-era modern`, negociou `2026-07-28`.
> O `Client` do SDK negociou `2026-07-28` por padrão. O mesmo código atendeu
> aos três casos — é a compatibilidade entre eras funcionando na prática. O
> smoke test do repositório exercita as duas eras.

## 2.10 Testes: o mesmo cliente, sem rede

O jeito mais rápido de testar é passar o objeto do servidor ao `Client`:

```python
from mcp import Client
from minicurso_einfo_mcphandson.server import create_server

async def test_listar():
    server = create_server(tmp_path / "teste.db")
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool(
            "listar_talhoes", {"status": "atencao"}
        )
        assert not result.is_error
        assert {t["id"] for t in result.structured_content["result"]} == {
            "T-002", "T-005"
        }
```

Isso não é um mock: o protocolo real é exercitado, sem subprocesso nem porta.
`raise_exceptions=True` só afeta falhas **fora** da tool; um `ToolError` continua
sendo um resultado normal.

Testes de transporte real ficam em `tests/test_transports.py`:

- **stdio**: `StdioServerParameters(command=sys.executable, args=["-m", ...])`;
- **HTTP**: sobe `serve --http`, espera a porta e conecta em
  `http://127.0.0.1:8000/mcp`.

O ambiente do subprocesso stdio é uma allowlist (`PATH`, `HOME`, etc.), não o
seu ambiente inteiro. Passe o que precisar em `env=` — no nosso caso,
`AGRO_DB_PATH` para isolar o banco do teste.

## 2.11 Prática guiada com esqueleto e gabarito (20 min)

Para praticar sem começar de uma tela em branco (e sem apenas executar código
pronto), use o arquivo [`examples/esqueleto_server.py`](../examples/esqueleto_server.py)
e compare cada passo com o gabarito 100% completo em
[`src/minicurso_einfo_mcphandson/server.py`](../src/minicurso_einfo_mcphandson/server.py):

1. **TODO 1 (`consultar_talhao`)**: busque no banco e levante `ToolError` quando
   o ID não existir.
2. **TODO 2 (`recomendar_irrigacao`)**: calcule a necessidade hídrica e retorne
   `RecomendacaoIrrigacao`.
3. **TODO 3 (`registrar_observacao`)**: verifique `confirmacao.confirmado`
   (preenchido via `Resolve` + `Elicit`) antes de gravar no SQLite.
4. **TODO 4 (`recurso_talhao`)**: implemente o template `agro://talhoes/{talhao_id}`
   levantando `ResourceNotFoundError` para IDs ausentes.
5. **TODO 5 (`analise_talhao`)**: retorne `[UserMessage(...), AssistantMessage(...)]`.

Se terminar antes, adicione em `server.py` uma tool extra
`historico_ndvi(talhao_id, dias=7)` e um teste em `tests/test_server.py`.

Critérios de aceite:

- o schema da tool aparece em `tools/list` com os limites corretos;
- um `talhao_id` inválido retorna erro legível, não traceback;
- o teste passa sem rede;
- o resource novo aparece em `resources/templates/list`.

## 2.12 Checkpoint do módulo

```bash
uv run pytest -q
./scripts/smoke_inspector.sh
uv run python -m minicurso_einfo_mcphandson client demo
```

Se os três passam, você tem um servidor MCP funcional e testado. O próximo
módulo o coloca dentro de hosts e agentes reais.

Próximo: [`03-integracao.md`](03-integracao.md).
