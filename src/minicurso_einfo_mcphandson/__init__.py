"""AgroMCP — servidor e cliente usados no minicurso MCP Hands-on."""

from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    """CLI única do projeto.

    ``serve`` inicia o servidor MCP; ``client`` executa o cliente de demonstração.
    Sem subcomando, ``serve`` é o padrão para manter compatibilidade com hosts
    que chamam o módulo diretamente.
    """
    parser = argparse.ArgumentParser(
        prog="minicurso-einfo-mcphandson",
        description="AgroMCP: laboratório do minicurso MCP Hands-on.",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Inicia o servidor MCP.")
    serve.add_argument(
        "--http",
        action="store_true",
        help="Usa Streamable HTTP em vez de stdio.",
    )
    serve.add_argument(
        "--host", default="127.0.0.1", help="Host HTTP (padrão: 127.0.0.1)."
    )
    serve.add_argument(
        "--port", type=int, default=8000, help="Porta HTTP (padrão: 8000)."
    )
    serve.add_argument("--db", type=Path, help="Caminho do banco SQLite.")
    serve.add_argument(
        "--stateless",
        action="store_true",
        help="Habilita stateless_http no transporte HTTP.",
    )
    serve.add_argument(
        "--token",
        help="Exige este Bearer token no transporte Streamable HTTP.",
    )

    client = sub.add_parser("client", help="Executa o cliente de demonstração.")
    client.add_argument("--url", help="Conecta por Streamable HTTP.")
    client.add_argument(
        "--token",
        help="Envia Authorization: Bearer <token> ao conectar por HTTP.",
    )
    client.add_argument(
        "--stdio",
        action="store_true",
        help="Inicia o servidor como subprocesso (stdio).",
    )
    client.add_argument("--db", type=Path, help="Banco usado pelo servidor.")
    client.add_argument(
        "action",
        nargs="?",
        default="demo",
        choices=["demo", "tools", "resources", "call"],
    )
    client.add_argument("tool", nargs="?", help="Tool para o comando 'call'.")
    client.add_argument(
        "arguments",
        nargs="?",
        default="{}",
        help="Argumentos JSON para o comando 'call'.",
    )

    args = parser.parse_args(argv)

    if args.command == "client":
        from .client import main as client_main

        client_args = ["--db", str(args.db)] if args.db else []
        if args.url:
            client_args += ["--url", args.url]
        if args.token:
            client_args += ["--token", args.token]
        if args.stdio:
            client_args += ["--stdio"]
        client_args.append(args.action)
        if args.action == "call":
            if not args.tool:
                parser.error("o comando 'call' exige o nome da tool")
            client_args += [args.tool, args.arguments]
        client_main(client_args)
        return

    # ``serve`` é o padrão, inclusive quando nenhum subcomando é informado.
    from .server import create_server, mcp

    db_arg = getattr(args, "db", None)
    token_arg = getattr(args, "token", None)
    servidor = (
        create_server(db_arg, bearer_token=token_arg)
        if (db_arg is not None or token_arg is not None)
        else mcp
    )
    transport = "streamable-http" if getattr(args, "http", False) else "stdio"
    kwargs: dict[str, object] = {}
    if transport == "streamable-http":
        kwargs["host"] = args.host
        kwargs["port"] = args.port
        if args.stateless:
            kwargs["stateless_http"] = True
    servidor.run(transport=transport, **kwargs)


if __name__ == "__main__":
    main()
