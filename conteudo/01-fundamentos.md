# Módulo 1 — O que é o Model Context Protocol

**Tempo:** 45 minutos · **Objetivo:** entender o problema que o MCP resolve,
a arquitetura e as três primitivas que um servidor expõe.

## 1.1 O problema: contexto estático não é suficiente

Um LLM só conhece duas coisas: o que está no seu contexto e o que aprendeu no
treinamento. Para trabalhar com dados da empresa, ele precisa que alguém coloque
esses dados no contexto. As abordagens usuais têm limites:

| Abordagem | O que resolve | O que não resolve |
|---|---|---|
| Colar dados no prompt | Casos pequenos e pontuais | Escala, atualização, custo, auditabilidade |
| RAG | Busca semântica sobre documentos | Ações, dados transacionais, parâmetros validados |
| Function calling nativo | Uma ação específica | Padronização entre fornecedores, descoberta, reuso |
| Integração sob medida | Um caso de uso | Explosão de conectores M×N |

O MCP ataca a última linha. Em vez de cada aplicação de IA criar um conector
para cada fonte de dados, define um **protocolo comum** entre a aplicação e um
processo que expõe dados e ações. O mesmo servidor serve Claude Desktop, VS Code,
OpenCode, LangChain ou um script Python.

> MCP é para **contexto e ferramentas**, não para treinar nem para substituir a
> API do modelo. Ele não decide quando uma tool será chamada; isso é papel do
> host e do modelo.

## 1.2 Arquitetura: host, cliente e servidor

```text
+-------------------------- Host (aplicação de IA) --------------------------+
| Interface - orquestração do LLM - política de permissões - auditoria       |
|                                                                            |
|  MCP Client A <---- conexão dedicada ----> MCP Server A (stdio, local)     |
|  MCP Client B <---- conexão dedicada ----> MCP Server B (HTTP, remoto)     |
+----------------------------------------------------------------------------+
```

- **Host**: a aplicação que o usuário usa (Claude Desktop, VS Code, OpenCode,
  um agente LangChain). Ele cria um **cliente** por servidor.
- **Cliente**: a metade que fala MCP. Mantém a conexão, negocia versão e
  encaminha chamadas.
- **Servidor**: o processo que expõe tools, resources e prompts. Ele **não fala
  com o modelo**; apenas responde ao cliente.

Um host pode conectar vários servidores ao mesmo tempo. O contexto de todos
conversa entre si, o que é poderoso e perigoso: um servidor malicioso pode
influenciar como o modelo usa as tools dos outros. Voltaremos a isso em 3.5.

## 1.3 Duas camadas

### Camada de dados

JSON-RPC 2.0. Toda mensagem é requisição, resposta ou notificação. A camada
define:

- **descoberta** de versão, capacidades e identidade do servidor;
- as primitivas de servidor: tools, resources e prompts;
- primitivas de cliente, como **elicitation** (pedir informação ao usuário);
- utilidades: progresso, cancelamento, notificações de mudança.

### Camada de transporte

Define como os bytes viajam:

| Transporte | Uso típico | Observações |
|---|---|---|
| **stdio** | Servidor local iniciado pelo host | stdin/stdout são o protocolo; logs vão para stderr |
| **Streamable HTTP** | Servidor remoto ou compartilhado | POST + SSE opcional; é o transporte de produção |
| **SSE** | Compatibilidade com clientes antigos | Superado pelo Streamable HTTP; não construa nada novo nele |

O mesmo servidor pode falar stdio e HTTP; o que muda é apenas `mcp.run(...)`.
O protocolo e as tools são idênticos.

## 1.4 As três primitivas

| Primitiva | Quem decide usar | O que é | Exemplo no AgroMCP |
|---|---|---|---|
| **Tool** | O modelo | Ação com efeito ou consulta | `recomendar_irrigacao` |
| **Resource** | A aplicação | Dado somente leitura, endereçado por URI | `agro://talhoes/T-001` |
| **Prompt** | O usuário | Template de mensagens | `analise_talhao` |

A pergunta de modelagem é sempre **quem controla**:

- Se o modelo precisa **decidir e agir**, é tool.
- Se o host precisa **carregar dados** no contexto, é resource.
- Se a pessoa escolhe um fluxo pronto (menu, slash command), é prompt.

### Tools

Uma tool tem nome, descrição, `inputSchema` e, opcionalmente, `outputSchema`.
O schema é gerado a partir dos type hints. O modelo lê a descrição e os campos
para decidir se e como chamar. Tools podem ser somente leitura ou ter efeitos;
as **annotations** (`read_only_hint`, `destructive_hint`, `idempotent_hint`,
`open_world_hint`) ajudam o host a decidir se pede confirmação — mas são apenas
dicas, não enforcement.

### Resources

Resources são endereçados por URI e lidos pela aplicação, não pelo modelo. Um
resource com `{param}` vira um **template** e aparece em outra lista
(`resources/templates/list`). O servidor só executa a função quando alguém lê o
URI concreto, o que permite expor milhares de registros sem custo de listagem.

### Prompts

Prompts recebem argumentos **string** e retornam uma ou mais mensagens. Não há
JSON Schema de prompt: é um formulário para uma pessoa preencher. O host decide
como apresentar (menu, slash command).

## 1.5 Descoberta, capacidades e versões

Ao conectar, o cliente precisa saber o que o servidor oferece. O SDK declara as
capacidades automaticamente quando você registra uma primitiva:

```python
server_capabilities = {
    "tools": {"list_changed": True},
    "resources": {"subscribe": True, "list_changed": True},
    "prompts": {"list_changed": True},
}
```

O cliente só pede o que foi declarado. Se o servidor não implementa completions,
não anuncia `completions`; um cliente bem-comportado não pergunta.

### A revisão 2026-07-28

A versão atual do protocolo mudou pontos importantes em relação às revisões
2025:

- **sem handshake e sem sessão**: cada requisição carrega versão, identidade e
  capacidades relevantes em `_meta`; o servidor é stateless por requisição;
- **descoberta explícita** via `server/discover`;
- **sem requisições iniciadas pelo servidor**: sampling e logging foram
  descontinuados; elicitation acontece por *multi-round-trip*;
- **subscriptions/listen** substitui o antigo par subscribe/unsubscribe para
  notificações;
- clientes antigos continuam funcionando: o SDK 2.x negocia a versão e atende
  as duas eras.

No curso usamos o SDK 2.x. O `Client` em memória negocia `2026-07-28`; o
Inspector 2.13, quando testado, negociou `2025-11-25`. O mesmo servidor atendeu
aos dois — e isso é uma lição prática, não um detalhe de implementação.

## 1.6 O que o MCP não é

- Não é um banco de dados nem um ORM.
- Não é um sandbox: um servidor stdio roda com os privilégios do usuário.
- Não é um sistema de permissões: o host decide o que aprovar.
- Não é um padrão de prompt: é um padrão de **contexto e ações**.
- Não substitui autenticação, autorização, auditoria ou observabilidade da sua
  aplicação; ele dá um lugar padronizado para plugá-las.

## 1.7 Exercício em duplas (5 min)

Classifique cada capacidade de um sistema de RH como **tool**, **resource** ou
**prompt** e justifique em uma frase:

1. consultar o saldo de férias de um funcionário;
2. carregar a política de viagens em Markdown;
3. aprovar uma solicitação de despesa;
4. preencher o formulário de avaliação de desempenho;
5. listar os centros de custo disponíveis.

## 1.8 Ponte para o Módulo 2

Agora que sabemos **o que** expor, vamos construir **como**: um servidor
`MCPServer` com tools validadas por Pydantic, resources endereçados por URI,
prompts e testes no Inspector.

Próximo: [`02-servidor.md`](02-servidor.md).
