#!/usr/bin/env bash
# Smoke test do servidor usando o MCP Inspector em modo CLI.
# Requer Node.js >= 22.19 e jq. Fixa a versão do Inspector para ser reprodutível.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

INSPECTOR_VERSION="${INSPECTOR_VERSION:-2.13.0}"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$RAIZ/.venv/bin/python" ]] && "$RAIZ/.venv/bin/python" -c "import minicurso_einfo_mcphandson" >/dev/null 2>&1; then
    PYTHON_BIN="$RAIZ/.venv/bin/python"
  elif command -v python >/dev/null 2>&1 && python -c "import minicurso_einfo_mcphandson" >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    PYTHON_BIN="python3"
  fi
fi

inspector() {
  if command -v mcp-inspector >/dev/null 2>&1; then
    mcp-inspector --cli "$PYTHON_BIN" -m minicurso_einfo_mcphandson serve "$@"
  else
    npx --yes "@modelcontextprotocol/inspector@${INSPECTOR_VERSION}" --cli \
      "$PYTHON_BIN" -m minicurso_einfo_mcphandson serve "$@"
  fi
}

echo "1/5 — initialize (era legada)"
inspector --method initialize --format json \
  | jq -e '.result.serverInfo.name == "agro-mcp"' >/dev/null

echo "2/5 — initialize (2026-07-28)"
inspector --protocol-era modern --method initialize --format json \
  | jq -e '.result.protocolVersion == "2026-07-28"' >/dev/null

echo "3/5 — tools/list"
inspector --protocol-era modern --method tools/list --format json \
  | jq -e '.result.tools | map(.name) | index("diagnosticar_talhao")' >/dev/null

echo "4/5 — tools/call"
inspector --protocol-era modern --method tools/call --tool-name diagnosticar_talhao \
  --tool-args-json '{"talhao_id":"T-002"}' --format json \
  | jq -e '.result.structuredContent.classificacao == "atencao"' >/dev/null

echo "5/5 — resources/read"
inspector --protocol-era modern --method resources/read --uri 'agro://talhoes/T-001' \
  --format json \
  | jq -e '.result.contents[0].text | contains("T-001")' >/dev/null

echo "OK: initialize (legado e moderno), tools/list, tools/call e resources/read."
