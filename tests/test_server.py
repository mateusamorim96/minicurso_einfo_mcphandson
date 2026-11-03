"""Testes de contrato do AgroMCP usando o cliente em memória.

O mesmo ``Client`` que um host usa é passado ao objeto do servidor, então o
teste exercita o protocolo real (listas, schemas, validação, erros) sem abrir
porta nem subprocesso.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, MCPError
from mcp.server import MCPServer
from mcp.types import ElicitResult
from pydantic import ValidationError

from minicurso_einfo_mcphandson.server import create_server


async def _aprovar_elicitation(_context: Any, _params: Any) -> ElicitResult:
    return ElicitResult(
        action="accept",
        content={"confirmado": True, "responsavel": "Maria Agrônoma"},
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def server(tmp_path: Path) -> MCPServer:
    return create_server(tmp_path / "agro-teste.db")


@pytest.fixture
async def client(server: MCPServer) -> AsyncIterator[Client]:
    async with Client(
        server,
        elicitation_callback=_aprovar_elicitation,
        raise_exceptions=True,
    ) as cliente:
        yield cliente


@pytest.mark.anyio
async def test_capacidades_e_instrucoes(client: Client) -> None:
    assert client.protocol_version == "2026-07-28"
    assert client.server_info is not None
    assert client.server_info.name == "agro-mcp"
    assert client.server_capabilities.tools is not None
    assert client.server_capabilities.resources is not None
    assert client.server_capabilities.prompts is not None
    assert "confirmação humana" in (client.instructions or "")


@pytest.mark.anyio
async def test_tools_tem_schema_e_annotations(client: Client) -> None:
    tools = {t.name: t for t in (await client.list_tools()).tools}

    assert set(tools) == {
        "listar_talhoes",
        "consultar_talhao",
        "recomendar_irrigacao",
        "diagnosticar_talhao",
        "registrar_observacao",
    }
    assert (
        "T-000"
        in tools["consultar_talhao"].input_schema["properties"]["talhao_id"][
            "description"
        ]
    )
    assert (
        tools["recomendar_irrigacao"].input_schema["properties"]["horizonte_dias"][
            "maximum"
        ]
        == 14
    )
    assert tools["recomendar_irrigacao"].output_schema is not None
    assert tools["registrar_observacao"].annotations.read_only_hint is False
    # O parâmetro `confirmacao` usa Resolve(...) e fica invisível para o modelo.
    assert "confirmacao" not in tools["registrar_observacao"].input_schema["properties"]


@pytest.mark.anyio
async def test_listar_e_filtrar_talhoes(client: Client) -> None:
    todos = await client.call_tool("listar_talhoes", {})
    assert not todos.is_error
    assert len(todos.structured_content["result"]) == 6

    atencao = await client.call_tool("listar_talhoes", {"status": "atencao"})
    ids = {t["id"] for t in atencao.structured_content["result"]}
    assert ids == {"T-002", "T-005"}

    uva = await client.call_tool("listar_talhoes", {"cultura": "uva"})
    assert {t["id"] for t in uva.structured_content["result"]} == {"T-001", "T-002"}


@pytest.mark.anyio
async def test_consultar_talhao_retorna_historico(client: Client) -> None:
    result = await client.call_tool("consultar_talhao", {"talhao_id": "T-002"})
    assert not result.is_error
    dados = result.structured_content
    assert dados["id"] == "T-002"
    assert dados["municipio"] == "Petrolina/PE"
    assert len(dados["leituras"]) == 7
    assert dados["observacoes"][0]["severidade"] == "alta"


@pytest.mark.anyio
async def test_recomendacao_irrigacao(client: Client) -> None:
    result = await client.call_tool(
        "recomendar_irrigacao", {"talhao_id": "T-002", "horizonte_dias": 7}
    )
    assert not result.is_error
    dados = result.structured_content
    assert dados["prioridade"] == "alta"
    assert dados["necessidade_total_mm"] > 0
    assert dados["volume_m3"] > 0
    assert any("abaixo do crítico" in a for a in dados["alertas"])
    assert any("turnos noturnos" in r for r in dados["recomendacoes"])


@pytest.mark.anyio
async def test_argumentos_invalidos_viram_erro_legivel(client: Client) -> None:
    result = await client.call_tool(
        "recomendar_irrigacao", {"talhao_id": "T-001", "horizonte_dias": 99}
    )
    assert result.is_error
    texto = result.content[0].text
    assert "less than or equal to 14" in texto


@pytest.mark.anyio
async def test_id_fora_do_padrao_e_rejeitado(client: Client) -> None:
    result = await client.call_tool(
        "consultar_talhao", {"talhao_id": "../../etc/passwd"}
    )
    assert result.is_error
    assert "String should match pattern" in result.content[0].text


@pytest.mark.anyio
async def test_tool_error_nao_derruba_o_servidor(client: Client) -> None:
    result = await client.call_tool("consultar_talhao", {"talhao_id": "T-999"})
    assert result.is_error
    assert "não encontrado" in result.content[0].text
    assert result.structured_content is None

    # A conexão continua utilizável depois do erro.
    ok = await client.call_tool("listar_talhoes", {})
    assert not ok.is_error


@pytest.mark.anyio
async def test_resources_e_templates(client: Client) -> None:
    resources = {str(r.uri) for r in (await client.list_resources()).resources}
    templates = {
        t.uri_template
        for t in (await client.list_resource_templates()).resource_templates
    }
    assert "agro://talhoes" in resources
    assert "agro://catalogo/culturas" in resources
    assert "agro://talhoes/{talhao_id}" in templates

    lido = await client.read_resource("agro://talhoes/T-001")
    assert lido.contents[0].mime_type == "application/json"
    dados = json.loads(lido.contents[0].text)
    assert dados["id"] == "T-001"

    catalogo = await client.read_resource("agro://catalogo/culturas")
    assert "uva" in json.loads(catalogo.contents[0].text)


@pytest.mark.anyio
async def test_resource_inexistente_e_erro_de_protocolo(client: Client) -> None:
    with pytest.raises(MCPError) as exc:
        await client.read_resource("agro://talhoes/T-999")
    assert "não encontrado" in str(exc.value)
    assert exc.value.code == -32602
    assert exc.value.data == {"uri": "agro://talhoes/T-999"}


@pytest.mark.anyio
async def test_prompts(client: Client) -> None:
    prompts = {p.name: p for p in (await client.list_prompts()).prompts}
    assert set(prompts) == {
        "analise_talhao",
        "planejar_irrigacao",
        "revisar_observacoes",
    }
    resultado = await client.get_prompt(
        "analise_talhao", {"talhao_id": "T-001", "foco": "nutrição"}
    )
    assert len(resultado.messages) == 2
    assert resultado.messages[0].role == "user"
    assert "T-001" in resultado.messages[0].content.text
    assert "nutrição" in resultado.messages[0].content.text


@pytest.mark.anyio
async def test_diagnostico_usa_resource_e_progresso(client: Client) -> None:
    eventos: list[tuple[float, float | None, str | None]] = []

    async def progresso(p: float, total: float | None, msg: str | None) -> None:
        eventos.append((p, total, msg))

    result = await client.call_tool(
        "diagnosticar_talhao",
        {"talhao_id": "T-005"},
        progress_callback=progresso,
    )
    assert not result.is_error
    assert result.structured_content["classificacao"] == "atencao"
    assert eventos
    assert eventos[-1][0] == 1.0


@pytest.mark.anyio
async def test_escrita_persiste_entre_chamadas(client: Client) -> None:
    criada = await client.call_tool(
        "registrar_observacao",
        {
            "talhao_id": "T-001",
            "texto": "Falha no gotejamento do setor 3 confirmada em campo.",
            "severidade": "alta",
        },
    )
    assert not criada.is_error
    obs_id = criada.structured_content["id"]
    assert criada.structured_content["responsavel"] == "Maria Agrônoma"

    detalhe = await client.call_tool("consultar_talhao", {"talhao_id": "T-001"})
    observacoes = detalhe.structured_content["observacoes"]
    assert observacoes[0]["id"] == obs_id
    assert observacoes[0]["severidade"] == "alta"


@pytest.mark.anyio
async def test_escrita_recusada_no_elicitation_nao_persiste(
    server: MCPServer,
) -> None:
    async def recusar(_context: Any, _params: Any) -> ElicitResult:
        return ElicitResult(
            action="accept",
            content={"confirmado": False, "responsavel": "Maria Agrônoma"},
        )

    async with Client(
        server,
        elicitation_callback=recusar,
        raise_exceptions=True,
    ) as c:
        # Severidade baixa não pede confirmação humana.
        baixa = await c.call_tool(
            "registrar_observacao",
            {
                "talhao_id": "T-001",
                "texto": "Leitura preventiva de rotina sem anomalias.",
                "severidade": "baixa",
            },
        )
        assert not baixa.is_error
        assert baixa.structured_content["responsavel"] == "automático"

        # Severidade alta aciona o resolver e respeita a recusa humana.
        recusada = await c.call_tool(
            "registrar_observacao",
            {
                "talhao_id": "T-001",
                "texto": "Suspeita não confirmada de vazamento na adutora.",
                "severidade": "alta",
            },
        )
        assert recusada.is_error
        assert "não confirmou" in recusada.content[0].text

        detalhe = await c.call_tool("consultar_talhao", {"talhao_id": "T-001"})
        assert all(
            "adutora" not in o["texto"]
            for o in detalhe.structured_content["observacoes"]
        )


@pytest.mark.anyio
async def test_esqueleto_live_coding_funciona_e_sinaliza_todos(
    tmp_path: Path,
) -> None:
    import importlib.util
    import sys

    caminho = Path(__file__).resolve().parents[1] / "examples" / "esqueleto_server.py"
    spec = importlib.util.spec_from_file_location("esqueleto_server", caminho)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["esqueleto_server"] = modulo
    spec.loader.exec_module(modulo)

    srv = modulo.create_esqueleto_server(tmp_path / "esqueleto.db")
    async with Client(srv, raise_exceptions=True) as c:
        lista = await c.call_tool("listar_talhoes", {"status": "atencao"})
        assert not lista.is_error
        assert len(lista.structured_content["result"]) == 2

        todo = await c.call_tool("consultar_talhao", {"talhao_id": "T-001"})
        assert todo.is_error
        assert "TODO 1 pendente" in todo.content[0].text


def test_modelos_rejeitam_dados_invalidos() -> None:
    from minicurso_einfo_mcphandson.models import TalhaoResumo

    with pytest.raises(ValidationError):
        TalhaoResumo(
            id="T-001",
            nome="X",
            fazenda="Y",
            cultura="uva",
            area_ha=0,
            status="ativo",
            umidade_solo_pct=20,
            ndvi=0.8,
        )
