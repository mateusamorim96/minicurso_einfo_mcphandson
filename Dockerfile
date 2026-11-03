# syntax=docker/dockerfile:1.7
#
# Imagem de laboratório do minicurso "MCP Hands-on: Expandindo o alcance de LLMs".
# Versões de referência (verificadas em 2026-10-30):
#   Python 3.13 | mcp 2.3.x | FastMCP 4.1.x | LangChain 1.4.x
#   Node.js 22.19+ (MCP Inspector 2.13.x)
#
# Build:
#   docker build -t mcp-lab:1.0 .
#
# Uso recomendado em Linux (o Inspector escuta só em loopback; host network
# evita publicar portas e mantém o token de acesso fora da rede):
#   docker run --rm -it --init --network host \
#     -v "$PWD":/workspace mcp-lab:1.0
#
#   # dentro do container, para abrir a UI em http://localhost:6274:
#   npx @modelcontextprotocol/inspector --web python -m minicurso_einfo_mcphandson serve
#
# Alternativa com portas publicadas (Docker Desktop, macOS/Windows ou bridge):
#   docker run --rm -it --init \
#     -p 6274:6274 -p 6275:6275 -p 6277:6277 -p 8000:8000 \
#     -e HOST=0.0.0.0 -e DANGEROUSLY_BIND_ALL_INTERFACES=true \
#     -v "$PWD":/workspace mcp-lab:1.0
#
# O VS Code pode se conectar a esse contêiner via extensão "Dev Containers".

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim-bookworm

# --- uv (binário oficial, sem instalar via pip) ------------------------------
# Versão fixada para builds reprodutíveis (0.13.6 casa com o uv_build do pyproject).
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

# MCP_INSPECTOR_SECRET_STORE=memory evita tentar o keychain do host.
# UV_PROJECT_ENVIRONMENT=/opt/venv faz `uv run` usar o venv da imagem mesmo
# quando /workspace é montado a partir do host (que pode ter seu próprio .venv).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    MCP_INSPECTOR_SECRET_STORE=memory \
    PYTHONPATH=/workspace/src

# --- Dependências de sistema + Node.js (para o MCP Inspector) ----------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      jq \
      less \
      procps \
      unzip \
      build-essential \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @modelcontextprotocol/inspector@2.13.0 \
 && npm cache clean --force \
 && rm -rf /var/lib/apt/lists/*

# --- Ambiente Python do curso, já populado (funciona offline no lab) ---------
# mcp 2.x: o import de alto nível é `from mcp.server import MCPServer`.
# fastmcp 4.x é a base do MCPAdapter do LangChain e uma alternativa standalone.
# langchain[mcp] habilita o Módulo 3 sem depender de download durante a aula.
WORKDIR /workspace
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --extra agent

# --- Usuário sem privilégios (UID/GID 1000 casa com o host em bind mounts) ---
ARG UID=1000
ARG GID=1000
# /etc/profile.d garante o venv no PATH também em shells de login (bash -l),
# que redefinem o PATH e ignorariam o ENV acima.
RUN groupadd --gid "${GID}" dev \
 && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /bin/bash dev \
 && printf 'export PATH="/opt/venv/bin:$PATH"\nexport UV_PROJECT_ENVIRONMENT="/opt/venv"\n' > /etc/profile.d/venv.sh \
 && chown -R "${UID}:${GID}" /workspace "${VIRTUAL_ENV}"

USER dev

# 6274 = UI do Inspector | 6275 = sandbox | 6277 = proxy | 8000 = servidor MCP
EXPOSE 6274 6275 6277 8000

# Sem ENTRYPOINT fixo: o participante roda `python -m ...`, `pytest`,
# `npx @modelcontextprotocol/inspector` etc. dentro do shell.
CMD ["bash"]
