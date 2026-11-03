"""Cliente de demonstração do AgroMCP.

Conecta-se ao servidor de três formas, todas com a mesma API ``Client``:

* em memória, passando o próprio objeto do servidor (ótimo para testes);
* por stdio, iniciando o servidor como subprocesso;
* por Streamable HTTP, apontando para uma URL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ElicitResult, TextContent

from .server import create_server


async def _confirmar_elicitation(_context: Any, params: Any) -> ElicitResult:
    """Callback de Elicitation usado pelo cliente de demonstração."""
    mensagem = getattr(params, "message", "Confirmação solicitada pelo servidor")
    print(f"[elicitation] Servidor perguntou: {mensagem}")
    return ElicitResult(
        action="accept",
        content={"confirmado": True, "responsavel": "operador-demo"},
    )


def _stdio_params(db_path: Path | None) -> StdioServerParameters:
    env: dict[str, str] = {}
    if db_path is not None:
        env["AGRO_DB_PATH"] = str(db_path)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "minicurso_einfo_mcphandson", "serve"],
        env=env or None,
    )


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _text(result: Any) -> str:
    """Extrai texto de um CallToolResult, GetPromptResult ou content block."""
    conteudo = getattr(result, "content", result)
    if isinstance(conteudo, TextContent):
        return conteudo.text
    if isinstance(conteudo, str):
        return conteudo
    return "\n".join(bloco.text for bloco in conteudo if isinstance(bloco, TextContent))


async def _demo(client: Client) -> None:
    print("== Tools ==")
    for tool in (await client.list_tools()).tools:
        print(f"- {tool.name}: {tool.description}")

    print("\n== Resources ==")
    for resource in (await client.list_resources()).resources:
        print(f"- {resource.uri} ({resource.mime_type})")

    print("\n== Resource templates ==")
    for template in (await client.list_resource_templates()).resource_templates:
        print(f"- {template.uri_template}")

    print("\n== Listar talhões ==")
    result = await client.call_tool("listar_talhoes", {"status": "atencao"})
    _print_json(result.structured_content)

    print("\n== Recomendação de irrigação (T-002) ==")
    result = await client.call_tool(
        "recomendar_irrigacao", {"talhao_id": "T-002", "horizonte_dias": 7}
    )
    _print_json(result.structured_content)

    print("\n== Diagnóstico (T-005) ==")
    result = await client.call_tool("diagnosticar_talhao", {"talhao_id": "T-005"})
    _print_json(result.structured_content)

    print("\n== Escrita com confirmação humana (Resolve + Elicit) ==")
    result = await client.call_tool(
        "registrar_observacao",
        {
            "talhao_id": "T-002",
            "texto": "Inspeção visual confirmou gotejadores entupidos na linha 4.",
            "severidade": "alta",
        },
    )
    _print_json(result.structured_content)

    print("\n== Prompt renderizado ==")
    prompt = await client.get_prompt(
        "analise_talhao", {"talhao_id": "T-002", "foco": "irrigação"}
    )
    for message in prompt.messages:
        print(f"[{message.role}] {_text(message)}")

    print("\n== Erro de tool (modelo pode corrigir) ==")
    result = await client.call_tool("consultar_talhao", {"talhao_id": "T-999"})
    print(f"is_error={result.is_error}")
    print(_text(result))


async def _run(args: argparse.Namespace) -> None:
    async with AsyncExitStack() as stack:
        if args.url and args.token:
            http_client = await stack.enter_async_context(
                httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {args.token}"},
                    timeout=httpx2.Timeout(30, read=300),
                )
            )
            alvo: Any = streamable_http_client(args.url, http_client=http_client)
        elif args.url:
            alvo = args.url
        elif args.stdio:
            alvo = _stdio_params(args.db)
        else:
            # Em memória: sem subprocesso, sem porta, mas passando pelo protocolo.
            alvo = create_server(args.db)

        client = await stack.enter_async_context(
            Client(alvo, elicitation_callback=_confirmar_elicitation)
        )
        if args.action == "demo":
            await _demo(client)
            return

        if args.action == "tools":
            for tool in (await client.list_tools()).tools:
                _print_json(
                    {
                        "name": tool.name,
                        "title": tool.title,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "annotations": tool.annotations.model_dump()
                        if tool.annotations
                        else None,
                    }
                )
        elif args.action == "resources":
            for resource in (await client.list_resources()).resources:
                _print_json(resource.model_dump(mode="json"))
            for template in (await client.list_resource_templates()).resource_templates:
                _print_json(template.model_dump(mode="json"))
        elif args.action == "call":
            argumentos = json.loads(args.arguments)
            result = await client.call_tool(args.tool, argumentos)
            print(f"is_error={result.is_error}")
            _print_json(result.structured_content)
            if result.is_error:
                print(_text(result))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cliente de demonstração do AgroMCP")
    parser.add_argument(
        "--url",
        help="Conecta por Streamable HTTP (ex.: http://127.0.0.1:8000/mcp).",
    )
    parser.add_argument(
        "--token",
        help="Envia Authorization: Bearer <token> ao conectar por HTTP.",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Inicia o servidor como subprocesso e conecta por stdio.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="Caminho do banco SQLite usado pelo servidor.",
    )
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("demo", help="Executa um roteiro completo de demonstração.")
    sub.add_parser("tools", help="Lista as tools e seus schemas.")
    sub.add_parser("resources", help="Lista resources e templates.")

    call = sub.add_parser("call", help="Chama uma tool com argumentos JSON.")
    call.add_argument("tool", help="Nome da tool.")
    call.add_argument(
        "arguments",
        nargs="?",
        default="{}",
        help='Objeto JSON com os argumentos (padrão: "{}").',
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    # O cliente é uma demonstração: logs INFO do servidor poluiriam a saída.
    logging.getLogger().setLevel(logging.WARNING)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
