#!/usr/bin/env bash
# Gera a apostila dos alunos (apostila.pdf) a partir dos módulos 01 a 05.
# Se conteudo/00-guia-do-facilitador.md existir localmente, gera também o
# guia-do-facilitador.pdf separado (ignorado no .gitignore).
# Requer pandoc e um motor LaTeX com fontes DejaVu (xelatex).
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAIDA="${1:-$RAIZ/apostila.pdf}"
SAIDA_FACILITADOR="$RAIZ/guia-do-facilitador.pdf"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

{
  cat <<'EOF'
---
title: "MCP Hands-on: Expandindo o alcance de LLMs"
subtitle: "Apostila do participante — AgroMCP"
author: "Mateus Silva"
date: "2026"
lang: pt-BR
---

EOF
  cat "$RAIZ/conteudo/01-fundamentos.md"
  printf '\n\\newpage\n\n'
  cat "$RAIZ/conteudo/02-servidor.md"
  printf '\n\\newpage\n\n'
  cat "$RAIZ/conteudo/03-integracao.md"
  printf '\n\\newpage\n\n'
  cat "$RAIZ/conteudo/04-projeto-e-producao.md"
  printf '\n\\newpage\n\n'
  cat "$RAIZ/conteudo/05-referencia-rapida.md"
} > "$TMP/apostila.md"

pandoc "$TMP/apostila.md" \
  --from markdown+pipe_tables+fenced_code_blocks \
  --to pdf \
  --pdf-engine=xelatex \
  --toc \
  --toc-depth=2 \
  -V mainfont="DejaVu Sans" \
  -V monofont="DejaVu Sans Mono" \
  -V fontsize=10pt \
  -V geometry:margin=2.2cm \
  -V colorlinks=true \
  -V linkcolor=blue \
  -V urlcolor=blue \
  -o "$SAIDA"

echo "Apostila dos alunos gerada em $SAIDA"

if [[ -f "$RAIZ/conteudo/00-guia-do-facilitador.md" ]]; then
  {
    cat <<'EOF'
---
title: "MCP Hands-on: Expandindo o alcance de LLMs"
subtitle: "Guia do Facilitador (uso exclusivo do instrutor)"
author: "Mateus Silva"
date: "2026"
lang: pt-BR
---

EOF
    cat "$RAIZ/conteudo/00-guia-do-facilitador.md"
  } > "$TMP/facilitador.md"

  pandoc "$TMP/facilitador.md" \
    --from markdown+pipe_tables+fenced_code_blocks \
    --to pdf \
    --pdf-engine=xelatex \
    --toc \
    --toc-depth=2 \
    -V mainfont="DejaVu Sans" \
    -V monofont="DejaVu Sans Mono" \
    -V fontsize=10pt \
    -V geometry:margin=2.2cm \
    -V colorlinks=true \
    -V linkcolor=blue \
    -V urlcolor=blue \
    -o "$SAIDA_FACILITADOR"

  echo "Guia do facilitador gerado em $SAIDA_FACILITADOR (ignorado pelo git)"
fi
