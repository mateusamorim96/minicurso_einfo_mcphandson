"""Servidor MCP do AgroMCP.

Execute com stdio (padrão, usado por hosts locais)::

    python -m minicurso_einfo_mcphandson serve

Ou exponha via Streamable HTTP::

    python -m minicurso_einfo_mcphandson serve --http --port 8000

O objeto ``mcp`` é criado no nível do módulo para que ``mcp run`` e os hosts
consigam encontrá-lo sem executar o servidor durante o import.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, cast

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.server.mcpserver.prompts.base import AssistantMessage, Message, UserMessage
from mcp.types import ToolAnnotations
from pydantic import Field

from minicurso_einfo_mcphandson.db import CULTURAS, AgroDB
from minicurso_einfo_mcphandson.models import (
    ConfirmacaoObservacao,
    Cultura,
    DiagnosticoTalhao,
    ObservacaoRegistrada,
    RecomendacaoIrrigacao,
    Severidade,
    StatusTalhao,
    TalhaoDetalhe,
    TalhaoResumo,
)

logger = logging.getLogger("agro_mcp")

GUIA_MANEJO = """# Guia rápido de manejo — AgroMCP

## Princípios
- A umidade crítica é o piso: abaixo dela, a planta já está em estresse.
- O NDVI ajuda a separar estresse hídrico de outras causas (praga, nutrição).
- Toda recomendação é uma sugestão técnica; a decisão final é do responsável de campo.

## Prioridades
1. Talhões com umidade abaixo do crítico e NDVI em queda.
2. Talhões com observações de severidade alta nas últimas 48 h.
3. Culturas com maior coeficiente cultural (Kc) e menor profundidade de raiz.

## Segurança
- Nunca ligue irrigação automaticamente a partir de uma resposta de LLM.
- Registre a decisão humana antes de executar qualquer ação de campo.
"""


@dataclass
class AppContext:
    """Objetos compartilhados durante o ciclo de vida do servidor."""

    db: AgroDB


def _default_db_path() -> Path:
    return Path(os.getenv("AGRO_DB_PATH", "data/agro.db")).expanduser()


def _db(ctx: Context) -> AgroDB:
    app = cast(AppContext, ctx.request_context.lifespan_context)
    return app.db


def _talhao_ou_erro(ctx: Context, talhao_id: str) -> TalhaoDetalhe:
    talhao = _db(ctx).obter_talhao(talhao_id)
    if talhao is None:
        # ToolError é legível pelo modelo: ele pode corrigir o ID e tentar de novo.
        raise ToolError(
            f"Talhão {talhao_id!r} não encontrado. "
            "Use listar_talhoes para descobrir os IDs disponíveis."
        )
    return talhao


class StaticTokenVerifier(TokenVerifier):
    """Verificador didático de Bearer token para o transporte Streamable HTTP.

    Em produção, troque pela validação de um JWT OAuth 2.1 (assinatura, ``iss``,
    ``aud``, expiração e escopos) emitido pelo seu provedor de identidade.
    """

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


def _confirmar_alta_severidade(
    talhao_id: str,
    severidade: Severidade,
) -> ConfirmacaoObservacao | Elicit[ConfirmacaoObservacao]:
    """Resolver de confirmação humana (human-in-the-loop) para escrita crítica.

    Observações de severidade baixa ou média passam direto. Quando a severidade
    é ``"alta"``, o resolver devolve ``Elicit(...)`` e o SDK solicita a
    confirmação do usuário antes de executar o corpo da tool — tanto no
    protocolo 2026-07-28 (multi-round-trip) quanto em conexões legadas.
    """
    if severidade == "alta":
        return Elicit(
            f"Confirmar registro de observação de ALTA severidade no talhão {talhao_id}?",
            ConfirmacaoObservacao,
        )
    return ConfirmacaoObservacao(confirmado=True, responsavel="automático")


def create_server(
    db_path: Path | None = None,
    bearer_token: str | None = None,
) -> MCPServer:
    """Cria uma instância isolada do servidor.

    ``db_path`` permite usar um banco temporário nos testes. ``bearer_token``
    (ou a variável ``AGRO_BEARER_TOKEN``) ativa o ``TokenVerifier`` no
    transporte Streamable HTTP.
    """

    caminho_banco = Path(db_path) if db_path is not None else _default_db_path()
    token_configurado = (
        bearer_token if bearer_token is not None else os.getenv("AGRO_BEARER_TOKEN")
    )
    verifier = StaticTokenVerifier(token_configurado) if token_configurado else None
    auth_settings = (
        AuthSettings(
            issuer_url="https://auth.agromcp.local",
            resource_server_url="http://127.0.0.1:8000/mcp",
            validate_token_resource=False,
        )
        if verifier is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
        db = AgroDB(caminho_banco)
        db.initialize()
        yield AppContext(db=db)

    server = MCPServer(
        name="agro-mcp",
        title="AgroMCP — Monitoramento de Talhões",
        version="1.0.0",
        instructions=(
            "Servidor de demonstração do minicurso MCP Hands-on. "
            "Expõe talhões, leituras de sensores e um catálogo agronômico. "
            "Tools de escrita exigem confirmação humana no host."
        ),
        lifespan=lifespan,
        token_verifier=verifier,
        auth=auth_settings,
        log_level="INFO",
    )

    # ------------------------------------------------------------------ tools
    @server.tool(
        title="Listar talhões",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    def listar_talhoes(
        ctx: Context,
        cultura: Cultura | None = None,
        status: StatusTalhao | None = None,
    ) -> list[TalhaoResumo]:
        """Lista os talhões monitorados, com filtros opcionais por cultura e status."""
        return _db(ctx).listar_talhoes(cultura=cultura, status=status)

    @server.tool(
        title="Consultar talhão",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
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
        return _talhao_ou_erro(ctx, talhao_id)

    @server.tool(
        title="Recomendar irrigação",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
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
            Field(
                ge=1,
                le=14,
                description="Horizonte do planejamento, em dias (1 a 14).",
            ),
        ] = 7,
    ) -> RecomendacaoIrrigacao:
        """Calcula a necessidade hídrica do talhão para os próximos dias.

        O cálculo combina o Kc da cultura, a evapotranspiração de referência,
        a umidade atual e a água disponível na zona radicular. É uma estimativa
        para apoiar a decisão humana, não um comando de irrigação.
        """
        talhao = _talhao_ou_erro(ctx, talhao_id)
        cultura = CULTURAS[talhao.cultura]
        et0 = 5.8 + max(0.0, talhao.temperatura_c - 30.0) * 0.15
        etc = round(cultura.kc * et0, 2)
        agua_disponivel = max(
            0.0,
            (talhao.umidade_solo_pct - cultura.umidade_critica_pct)
            / 100.0
            * cultura.profundidade_raiz_mm,
        )
        necessidade = max(0.0, etc * horizonte_dias - agua_disponivel)
        volume = necessidade * talhao.area_ha * 10.0
        lamina_limite = cultura.lamina_maxima_mm_dia * horizonte_dias

        deficit = cultura.umidade_critica_pct - talhao.umidade_solo_pct
        if deficit > 0 or necessidade > lamina_limite:
            prioridade = "alta"
        elif deficit > -3 or talhao.ndvi < 0.65:
            prioridade = "media"
        else:
            prioridade = "baixa"

        recomendacoes: list[str] = []
        alertas: list[str] = []
        if necessidade > 0:
            recomendacoes.append(
                f"Aplicar até {necessidade:.1f} mm em {horizonte_dias} dia(s), "
                f"preferindo turnos noturnos."
            )
            recomendacoes.append(
                f"Volume estimado: {volume:.0f} m³ para {talhao.area_ha:.1f} ha."
            )
        else:
            recomendacoes.append(
                "Não há déficit estimado no horizonte; manter o monitoramento."
            )

        if necessidade > lamina_limite:
            alertas.append(
                f"A necessidade ({necessidade:.1f} mm) supera a lâmina máxima "
                f"recomendada ({lamina_limite:.1f} mm). Divida a aplicação e "
                "reavalie o solo."
            )
        if talhao.umidade_solo_pct < cultura.umidade_critica_pct:
            alertas.append(
                f"Umidade ({talhao.umidade_solo_pct:.1f}%) abaixo do crítico "
                f"para {cultura.nome} ({cultura.umidade_critica_pct:.1f}%)."
            )
        if talhao.ndvi < 0.6:
            alertas.append(
                f"NDVI baixo ({talhao.ndvi:.2f}); investigue pragas, nutrição "
                "e falhas de aplicação antes de atribuir tudo à água."
            )

        return RecomendacaoIrrigacao(
            talhao_id=talhao.id,
            cultura=talhao.cultura,
            horizonte_dias=horizonte_dias,
            etc_mm_dia=etc,
            necessidade_total_mm=round(necessidade, 1),
            volume_m3=round(volume, 1),
            prioridade=prioridade,
            recomendacoes=recomendacoes,
            alertas=alertas,
        )

    @server.tool(
        title="Diagnosticar talhão",
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
    )
    async def diagnosticar_talhao(
        talhao_id: Annotated[
            str,
            Field(
                description="Identificador do talhão, no formato T-000.",
                pattern=r"^T-\d{3}$",
            ),
        ],
        ctx: Context,
    ) -> DiagnosticoTalhao:
        """Gera um diagnóstico sintético combinando sensores, catálogo e observações.

        Demonstra três recursos do Context: leitura de um resource do próprio
        servidor, progresso para o cliente e logs estruturados.
        """
        await ctx.report_progress(0.1, 1.0, "Carregando catálogo de culturas")
        catalogo = await _ler_catalogo(ctx)

        await ctx.report_progress(0.4, 1.0, "Lendo histórico do talhão")
        talhao = _talhao_ou_erro(ctx, talhao_id)
        if talhao.cultura not in catalogo:
            raise ToolError(
                f"Cultura {talhao.cultura!r} ausente do catálogo agronômico."
            )
        cultura = CULTURAS[talhao.cultura]

        await ctx.report_progress(0.8, 1.0, "Calculando indicadores")
        score = 100
        fatores: list[str] = []

        deficit = cultura.umidade_critica_pct - talhao.umidade_solo_pct
        if deficit > 0:
            perda = min(40, int(deficit * 4))
            score -= perda
            fatores.append(
                f"Umidade {deficit:.1f} p.p. abaixo do crítico (−{perda} pontos)."
            )
        else:
            fatores.append("Umidade do solo acima do limite crítico.")

        if talhao.ndvi < 0.6:
            perda = min(30, int((0.6 - talhao.ndvi) * 100))
            score -= perda
            fatores.append(f"NDVI baixo: {talhao.ndvi:.2f} (−{perda} pontos).")
        elif talhao.ndvi >= 0.75:
            fatores.append(f"NDVI saudável: {talhao.ndvi:.2f}.")
        else:
            fatores.append(f"NDVI intermediário: {talhao.ndvi:.2f}.")

        if talhao.temperatura_c >= 35:
            score -= 5
            fatores.append(f"Temperatura elevada: {talhao.temperatura_c:.1f} °C.")

        for obs in talhao.observacoes[:3]:
            if obs.severidade == "alta":
                score -= 10
            elif obs.severidade == "media":
                score -= 5

        score = max(0, min(100, score))
        if score >= 85:
            classificacao = "saudavel"
        elif score >= 60:
            classificacao = "atencao"
        else:
            classificacao = "critico"

        proximos_passos = [
            "Validar a leitura do sensor em campo antes de qualquer aplicação."
        ]
        if deficit > 0:
            proximos_passos.append(
                "Priorizar uma avaliação de irrigação nas próximas 24 h."
            )
        if talhao.ndvi < 0.6:
            proximos_passos.append(
                "Inspecionar pragas e nutrição no trecho de menor NDVI."
            )
        if any(o.severidade == "alta" for o in talhao.observacoes):
            proximos_passos.append(
                "Revisar as observações de severidade alta com o agrônomo."
            )

        # A capacidade de logging do protocolo foi descontinuada na revisão
        # 2026-07-28 (SEP-2577). O caminho atual é o logging local em stderr.
        logger.info(
            "Diagnóstico de %s concluído: %s (score %s).",
            talhao_id,
            classificacao,
            score,
        )
        await ctx.report_progress(1.0, 1.0, "Diagnóstico concluído")
        return DiagnosticoTalhao(
            talhao_id=talhao.id,
            score=score,
            classificacao=classificacao,
            fatores=fatores,
            proximos_passos=proximos_passos,
        )

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
            Field(
                description="Identificador do talhão, no formato T-000.",
                pattern=r"^T-\d{3}$",
            ),
        ],
        texto: Annotated[
            str,
            Field(
                min_length=10,
                max_length=500,
                description="Descrição objetiva do que foi observado em campo.",
            ),
        ],
        severidade: Severidade,
        confirmacao: Annotated[
            ConfirmacaoObservacao,
            Resolve(_confirmar_alta_severidade),
        ],
        ctx: Context,
    ) -> ObservacaoRegistrada:
        """Grava uma observação de campo no banco do laboratório.

        Observações com ``severidade="alta"`` acionam ``Resolve`` + ``Elicit``
        para solicitar confirmação humana antes de gravar no banco. O parâmetro
        ``confirmacao`` não aparece no schema enviado ao modelo.
        """
        _talhao_ou_erro(ctx, talhao_id)
        if not confirmacao.confirmado:
            raise ToolError(
                "Gravação cancelada: o responsável não confirmou a operação."
            )
        obs_id, criado_em = _db(ctx).registrar_observacao(
            talhao_id=talhao_id,
            texto=texto,
            severidade=severidade,
        )
        logger.info(
            "Observação %s registrada em %s (aprovada por %s).",
            obs_id,
            talhao_id,
            confirmacao.responsavel,
        )
        return ObservacaoRegistrada(
            id=obs_id,
            talhao_id=talhao_id,
            severidade=severidade,
            responsavel=confirmacao.responsavel,
            criado_em=criado_em,
            mensagem="Observação registrada. Nenhuma ação de campo foi executada.",
        )

    # -------------------------------------------------------------- resources
    @server.resource(
        "agro://talhoes",
        name="talhoes",
        title="Talhões monitorados",
        description="Lista resumida de todos os talhões, em JSON.",
        mime_type="application/json",
    )
    def recurso_talhoes() -> str:
        """Lista resumida dos talhões."""
        dados = [
            t.model_dump(mode="json") for t in AgroDB(caminho_banco).listar_talhoes()
        ]
        return json.dumps(dados, ensure_ascii=False, indent=2)

    @server.resource(
        "agro://talhoes/{talhao_id}",
        name="talhao",
        title="Ficha do talhão",
        description="Ficha completa de um talhão, em JSON.",
        mime_type="application/json",
    )
    def recurso_talhao(talhao_id: str, ctx: Context) -> str:
        """Ficha completa de um talhão."""
        talhao = _db(ctx).obter_talhao(talhao_id)
        if talhao is None:
            # Em resources não existe resultado "is_error": o protocolo falha.
            raise ResourceNotFoundError(f"Talhão {talhao_id!r} não encontrado.")
        return talhao.model_dump_json(indent=2)

    @server.resource(
        "agro://catalogo/culturas",
        name="catalogo_culturas",
        title="Catálogo de culturas",
        description="Parâmetros agronômicos por cultura, em JSON.",
        mime_type="application/json",
    )
    def recurso_catalogo() -> str:
        """Parâmetros agronômicos usados pelo servidor."""
        return json.dumps(
            {chave: info.model_dump() for chave, info in CULTURAS.items()},
            ensure_ascii=False,
            indent=2,
        )

    @server.resource(
        "agro://guia/manejo",
        name="guia_manejo",
        title="Guia de manejo",
        description="Boas práticas resumidas para interpretar os indicadores.",
        mime_type="text/markdown",
    )
    def recurso_guia() -> str:
        """Guia de manejo embarcado no servidor."""
        return GUIA_MANEJO

    @server.resource(
        "agro://resumo",
        name="resumo",
        title="Resumo operacional",
        description="Contagens e área total do cenário, em JSON.",
        mime_type="application/json",
    )
    def recurso_resumo() -> str:
        """Resumo do cenário para dashboards e prompts."""
        return json.dumps(AgroDB(caminho_banco).resumo(), ensure_ascii=False, indent=2)

    # ---------------------------------------------------------------- prompts
    @server.prompt(
        title="Analisar talhão",
        description="Monta um pedido de análise agronômica para um talhão.",
    )
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

    @server.prompt(
        title="Planejar irrigação",
        description="Monta um roteiro de decisão para o horizonte de irrigação.",
    )
    def planejar_irrigacao(talhao_id: str, horizonte_dias: str = "7") -> str:
        """Prompt simples, retornado como uma mensagem de usuário."""
        return (
            f"Monte um plano de irrigação para o talhão {talhao_id} nos próximos "
            f"{horizonte_dias} dias. Consulte a recomendação, liste riscos e "
            "termine com uma pergunta de confirmação para o responsável de campo. "
            "Não execute nenhuma ação sem aprovação humana."
        )

    @server.prompt(
        title="Revisar observações críticas",
        description="Prepara uma revisão das observações de campo por severidade.",
    )
    def revisar_observacoes(severidade: Severidade = "alta") -> list[Message]:
        """Prompt com duas mensagens para orientar a revisão."""
        return [
            UserMessage(
                f"Liste as observações de severidade {severidade} e proponha "
                "uma triagem. Para cada uma, diga o que confirmar em campo."
            ),
            AssistantMessage(
                "Vou separar o que é evidência do que é hipótese e priorizar "
                "os casos com maior risco operacional."
            ),
        ]

    return server


async def _ler_catalogo(ctx: Context) -> dict[str, Any]:
    """Lê o resource do catálogo pelo mesmo caminho que um cliente usaria."""
    partes = list(await ctx.read_resource("agro://catalogo/culturas"))
    if not partes:
        return {}
    conteudo = partes[0].content
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("utf-8")
    return json.loads(conteudo)


# O nome ``mcp`` é o que ferramentas como ``mcp run`` procuram por convenção.
mcp = create_server()


if __name__ == "__main__":
    mcp.run()
