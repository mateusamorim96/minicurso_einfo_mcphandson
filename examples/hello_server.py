"""Servidor mínimo para o primeiro contato com o MCP Inspector.

Rode a partir da raiz do projeto::

    uv run mcp dev examples/hello_server.py

O arquivo não importa o pacote do curso de propósito: ele só depende de
``mcp`` e serve para mostrar o ciclo decorator → schema → Inspector.
"""

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
