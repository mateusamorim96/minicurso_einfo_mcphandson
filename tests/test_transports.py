"""Testes ponta a ponta dos transportes stdio e Streamable HTTP.

Diferente dos testes em memória, aqui o servidor roda em outro processo e a
comunicação passa pelo transporte real que um host usaria.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from minicurso_einfo_mcphandson.server import create_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"servidor HTTP não abriu a porta {port}")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "agro-transporte.db"


@pytest.fixture
def http_server(db_path: Path) -> Iterator[str]:
    port = _free_port()
    processo = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "minicurso_einfo_mcphandson",
            "serve",
            "--http",
            "--port",
            str(port),
            "--db",
            str(db_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_port(port)
        yield f"http://127.0.0.1:{port}/mcp"
    except Exception:
        if processo.poll() is not None:
            print(processo.stderr.read() if processo.stderr else "")
        raise
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()
            processo.wait(timeout=5)


@pytest.mark.anyio
async def test_stdio_chama_tool_e_le_resource(db_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "minicurso_einfo_mcphandson", "serve"],
        env={"AGRO_DB_PATH": str(db_path)},
    )
    async with Client(params, raise_exceptions=True) as client:
        assert client.protocol_version == "2026-07-28"
        tools = {t.name for t in (await client.list_tools()).tools}
        assert "diagnosticar_talhao" in tools

        result = await client.call_tool(
            "recomendar_irrigacao", {"talhao_id": "T-002", "horizonte_dias": 3}
        )
        assert not result.is_error
        assert result.structured_content["horizonte_dias"] == 3

        resource = await client.read_resource("agro://talhoes/T-001")
        assert '"T-001"' in resource.contents[0].text


@pytest.mark.anyio
async def test_streamable_http_ponta_a_ponta(http_server: str) -> None:
    async with Client(http_server, raise_exceptions=True) as client:
        assert client.protocol_version == "2026-07-28"
        assert client.server_capabilities.tools is not None

        listing = await client.call_tool("listar_talhoes", {"cultura": "manga"})
        assert not listing.is_error
        assert {t["id"] for t in listing.structured_content["result"]} == {
            "T-003",
            "T-004",
        }

        prompt = await client.get_prompt(
            "planejar_irrigacao", {"talhao_id": "T-003", "horizonte_dias": "5"}
        )
        assert "T-003" in prompt.messages[0].content.text

        erro = await client.call_tool("consultar_talhao", {"talhao_id": "T-404"})
        assert erro.is_error


@pytest.mark.anyio
async def test_streamable_http_com_bearer_token(db_path: Path) -> None:
    srv = create_server(db_path, bearer_token="segredo-lab")
    app = srv.streamable_http_app()

    async with app.router.lifespan_context(app):
        # 1. Sem token -> 401 Unauthorized
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as http_sem_token:
            resposta = await http_sem_token.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert resposta.status_code == 401

        # 2. Com token errado -> 401 Unauthorized
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            headers={"Authorization": "Bearer token-invalido"},
        ) as http_token_errado:
            resposta = await http_token_errado.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert resposta.status_code == 401

        # 3. Com Bearer token válido -> 200 OK e execução normal pelo Client
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
            headers={"Authorization": "Bearer segredo-lab"},
            timeout=httpx2.Timeout(30, read=300),
        ) as http_autenticado:
            transporte = streamable_http_client(
                "http://127.0.0.1:8000/mcp",
                http_client=http_autenticado,
            )
            async with Client(transporte, raise_exceptions=True) as client:
                resultado = await client.call_tool(
                    "listar_talhoes", {"status": "atencao"}
                )
                assert not resultado.is_error
                assert len(resultado.structured_content["result"]) == 2
