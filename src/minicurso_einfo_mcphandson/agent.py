"""Integração do AgroMCP com um agente LangChain.

Dois modos:

* sem ``--model``: descobre as tools pelo ``MCPAdapter`` e chama uma delas
  diretamente. É o teste de integração que não precisa de chave de API;
* com ``--model``: monta um agente com ``create_agent`` e executa uma pergunta.
  O modelo é resolvido pelo LangChain no formato ``provedor:modelo``; não
  fixamos nomes de modelos no código porque o catálogo muda com frequência.

Requer o extra ``agent``::

    uv sync --extra agent
    export AGRO_MODEL="provedor:modelo"   # consulte o catálogo do provedor
    uv run python -m minicurso_einfo_mcphandson.agent \
        --model "$AGRO_MODEL" "Qual talhão exige atenção hoje?"
"""

from __future__ import annotations

import argparse
import asyncio
import warnings
from pathlib import Path

from langchain_core._api import LangChainBetaWarning

from .server import create_server

warnings.filterwarnings("ignore", category=LangChainBetaWarning)


async def _sem_modelo(servidor) -> None:
    """Valida a descoberta e a chamada de tools sem acionar um LLM."""
    from langchain.mcp import MCPAdapter

    async with MCPAdapter(servidor) as adapter:
        tools = await adapter.list_tools()
        print("Tools descobertas pelo LangChain:")
        for tool in tools:
            print(f"- {tool.name}")

        listar = next(t for t in tools if t.name == "listar_talhoes")
        resultado = await listar.ainvoke({"status": "atencao"})
        print("\nResultado de listar_talhoes(status='atencao'):")
        print(resultado)


async def _com_agente(servidor, model: str, pergunta: str) -> None:
    from langchain.agents import create_agent
    from langchain.mcp import MCPAdapter

    async with MCPAdapter(servidor) as adapter:
        tools = await adapter.list_tools()
        agente = create_agent(
            model,
            tools,
            system_prompt=(
                "Você é um assistente agronômico. Use as tools do AgroMCP para "
                "basear cada afirmação em dados. Separe fatos de hipóteses, cite "
                "os números consultados e nunca recomende executar uma ação de "
                "campo sem confirmação humana."
            ),
        )
        resposta = await agente.ainvoke({"messages": pergunta})
        print(resposta["messages"][-1].content)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Agente LangChain + AgroMCP")
    parser.add_argument(
        "--model",
        help="Modelo LangChain no formato provedor:modelo. Sem ele, só valida as tools.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="Banco SQLite usado pelo servidor em memória.",
    )
    parser.add_argument(
        "pergunta",
        nargs="?",
        default="Qual talhão exige atenção hoje e por quê?",
        help="Pergunta enviada ao agente.",
    )
    args = parser.parse_args(argv)

    servidor = create_server(args.db)
    if args.model:
        asyncio.run(_com_agente(servidor, args.model, args.pergunta))
    else:
        asyncio.run(_sem_modelo(servidor))
        print(
            "\nIntegração validada. Para conversar com um LLM, informe "
            "--model e configure a chave do provedor."
        )


if __name__ == "__main__":
    main()
