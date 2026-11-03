"""Integração opcional com LangChain (extra ``agent``).

Não chama um LLM: valida a descoberta e a execução de tools pelo MCPAdapter,
que é a parte que o curso precisa garantir de ponta a ponta.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

pytest.importorskip("langchain.mcp")

from langchain_core._api import LangChainBetaWarning

from minicurso_einfo_mcphandson.server import create_server

warnings.filterwarnings("ignore", category=LangChainBetaWarning)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_langchain_descobre_e_executa_tool(tmp_path: Path) -> None:
    from langchain.mcp import MCPAdapter

    async with MCPAdapter(create_server(tmp_path / "langchain.db")) as adapter:
        tools = {tool.name: tool for tool in await adapter.list_tools()}
        assert "recomendar_irrigacao" in tools

        resultado = await tools["recomendar_irrigacao"].ainvoke(
            {"talhao_id": "T-002", "horizonte_dias": 3}
        )
        assert "prioridade" in str(resultado)
        assert "T-002" in str(resultado)
