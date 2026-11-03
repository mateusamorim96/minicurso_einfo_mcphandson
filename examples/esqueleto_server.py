"""Esqueleto de live coding do AgroMCP (Módulo 2).

Este arquivo traz a estrutura do servidor com ``listar_talhoes`` e
``recurso_talhoes`` prontos como exemplo, e marca com ``TODO`` os cinco blocos
que os participantes implementam durante a oficina:

1. ``consultar_talhao`` — validação com ``Field(pattern=...)`` e ``ToolError``;
2. ``recomendar_irrigacao`` — cálculo agronômico e saída estruturada;
3. ``registrar_observacao`` — escrita protegida por ``Resolve`` + ``Elicit``;
4. ``recurso_talhao`` — resource template ``agro://talhoes/{talhao_id}``;
5. ``analise_talhao`` — prompt multi-mensagem com ``UserMessage``/``AssistantMessage``.

Compare a qualquer momento com o gabarito 100% pronto em:
``src/minicurso_einfo_mcphandson/server.py``.

Para abrir no MCP Inspector durante o exercício::

    uv run mcp dev examples/esqueleto_server.py
"""

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.server.mcpserver.prompts.base import AssistantMessage, Message, UserMessage
from mcp.types import ToolAnnotations
from pydantic import Field

from minicurso_einfo_mcphandson.db import CULTURAS, AgroDB
from minicurso_einfo_mcphandson.models import (
    ConfirmacaoObservacao,
    Cultura,
    ObservacaoRegistrada,
    RecomendacaoIrrigacao,
    Severidade,
    StatusTalhao,
    TalhaoDetalhe,
    TalhaoResumo,
)


@dataclass
class AppContext:
    db: AgroDB


def _db(ctx: Context) -> AgroDB:
    return cast(AppContext, ctx.request_context.lifespan_context).db


def _confirmar_alta_severidade(
    talhao_id: str,
    severidade: Severidade,
) -> ConfirmacaoObservacao | Elicit[ConfirmacaoObservacao]:
    """Exemplo de resolver para o TODO 3."""
    if severidade == "alta":
        return Elicit(
            f"Confirmar registro de observação de ALTA severidade no talhão {talhao_id}?",
            ConfirmacaoObservacao,
        )
    return ConfirmacaoObservacao(confirmado=True, responsavel="automático")


def create_esqueleto_server(db_path: Path | None = None) -> MCPServer:
    caminho_banco = (
        Path(db_path)
        if db_path is not None
        else Path(os.getenv("AGRO_DB_PATH", "data/agro.db")).expanduser()
    )

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
        db = AgroDB(caminho_banco)
        db.initialize()
        yield AppContext(db=db)

    server = MCPServer(
        name="agro-mcp-esqueleto",
        title="AgroMCP (Esqueleto de Aula)",
        version="0.1.0",
        instructions="Esqueleto do Módulo 2. Compare com src/minicurso_einfo_mcphandson/server.py.",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ PRONTO
    @server.tool(
        title="Listar talhões",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def listar_talhoes(
        ctx: Context,
        cultura: Cultura | None = None,
        status: StatusTalhao | None = None,
    ) -> list[TalhaoResumo]:
        """Lista os talhões monitorados (já implementada como referência)."""
        return _db(ctx).listar_talhoes(cultura=cultura, status=status)

    # ------------------------------------------------------------------ TODO 1
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
        """Retorna a ficha completa de um talhão, incluindo as últimas leituras."""
        # TODO (Módulo 2 - Passo 1):
        # 1. Busque o talhão com `_db(ctx).obter_talhao(talhao_id)`.
        # 2. Se for `None`, levante `ToolError` orientando o modelo a usar `listar_talhoes`.
        # 3. Retorne o objeto `TalhaoDetalhe`.
        # Gabarito: função `consultar_talhao` em `src/minicurso_einfo_mcphandson/server.py`.
        _ = (talhao_id, ctx, ToolError)
        raise ToolError("TODO 1 pendente: implemente consultar_talhao.")

    # ------------------------------------------------------------------ TODO 2
    @server.tool(
        title="Recomendar irrigação",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def recomendar_irrigacao(
        ctx: Context,
        talhao_id: Annotated[
            str,
            Field(
                description="Identificador do talhão, no formato T-000.",
                pattern=r"^T-\d{3}$",
            ),
        ],
        horizonte_dias: Annotated[
            int,
            Field(ge=1, le=14, description="Horizonte em dias (1 a 14)."),
        ] = 7,
    ) -> RecomendacaoIrrigacao:
        """Calcula a necessidade hídrica do talhão para os próximos dias."""
        # TODO (Módulo 2 - Passo 2):
        # 1. Obtenha o talhão no banco e os parâmetros da cultura em `CULTURAS[talhao.cultura]`.
        # 2. Calcule `etc`, `agua_disponivel`, `necessidade` e `volume`.
        # 3. Defina `prioridade` ("baixa" | "media" | "alta") e preencha `recomendacoes` e `alertas`.
        # 4. Retorne uma instância de `RecomendacaoIrrigacao`.
        # Gabarito: função `recomendar_irrigacao` em `src/minicurso_einfo_mcphandson/server.py`.
        _ = (ctx, talhao_id, horizonte_dias, CULTURAS)
        raise ToolError("TODO 2 pendente: implemente recomendar_irrigacao.")

    # ------------------------------------------------------------------ TODO 3
    @server.tool(
        title="Registrar observação de campo",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
    async def registrar_observacao(
        talhao_id: Annotated[
            str,
            Field(pattern=r"^T-\d{3}$", description="ID no formato T-000."),
        ],
        texto: Annotated[
            str,
            Field(min_length=10, max_length=500, description="O que foi visto."),
        ],
        severidade: Severidade,
        confirmacao: Annotated[
            ConfirmacaoObservacao,
            Resolve(_confirmar_alta_severidade),
        ],
        ctx: Context,
    ) -> ObservacaoRegistrada:
        """Grava uma observação de campo após validar a confirmação humana."""
        # TODO (Módulo 2 - Passo 3):
        # 1. Verifique se o talhão existe.
        # 2. Se `not confirmacao.confirmado`, levante `ToolError` cancelando a operação.
        # 3. Grave no banco com `_db(ctx).registrar_observacao(...)` e retorne `ObservacaoRegistrada`.
        # Gabarito: função `registrar_observacao` em `src/minicurso_einfo_mcphandson/server.py`.
        _ = (talhao_id, texto, severidade, confirmacao, ctx)
        raise ToolError("TODO 3 pendente: implemente registrar_observacao.")

    # ----------------------------------------------------- RESOURCE DE EXEMPLO
    @server.resource(
        "agro://talhoes",
        name="talhoes",
        description="Lista resumida de todos os talhões, em JSON.",
        mime_type="application/json",
    )
    def recurso_talhoes() -> str:
        """Resource fixo (já implementado como referência)."""
        dados = [
            t.model_dump(mode="json") for t in AgroDB(caminho_banco).listar_talhoes()
        ]
        return json.dumps(dados, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ TODO 4
    @server.resource(
        "agro://talhoes/{talhao_id}",
        name="talhao",
        description="Ficha completa de um talhão, em JSON.",
        mime_type="application/json",
    )
    def recurso_talhao(talhao_id: str, ctx: Context) -> str:
        """Resource template parametrizado por {talhao_id}."""
        # TODO (Módulo 2 - Passo 4):
        # 1. Consulte `_db(ctx).obter_talhao(talhao_id)`.
        # 2. Se não existir, levante `ResourceNotFoundError(...)` (gera código -32602).
        # 3. Retorne `talhao.model_dump_json(indent=2)`.
        # Gabarito: função `recurso_talhao` em `src/minicurso_einfo_mcphandson/server.py`.
        _ = (talhao_id, ctx)
        raise ResourceNotFoundError(
            f"TODO 4 pendente: implemente recurso_talhao para {talhao_id!r}."
        )

    # ------------------------------------------------------------------ TODO 5
    @server.prompt(
        title="Analisar talhão",
        description="Monta um pedido de análise agronômica para um talhão.",
    )
    def analise_talhao(talhao_id: str, foco: str = "irrigação") -> list[Message]:
        """Prompt escolhido pelo usuário."""
        # TODO (Módulo 2 - Passo 5):
        # Retorne uma lista com `UserMessage(...)` e `AssistantMessage(...)`
        # orientando o modelo a consultar os dados e separar fatos de hipóteses.
        # Gabarito: função `analise_talhao` em `src/minicurso_einfo_mcphandson/server.py`.
        return [
            UserMessage(f"TODO 5: analise o talhão {talhao_id} com foco em {foco}."),
            AssistantMessage("Complete o prompt no esqueleto_server.py."),
        ]

    return server


mcp = create_esqueleto_server()

if __name__ == "__main__":
    mcp.run()
