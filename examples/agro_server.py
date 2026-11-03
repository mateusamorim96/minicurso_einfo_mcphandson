"""Wrapper de script para hosts que exigem um arquivo em vez de um módulo.

Use com ``mcp run``, ``MCPAdapter(Path("examples/agro_server.py"))`` ou em
configurações de host que não sabem chamar ``python -m``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from minicurso_einfo_mcphandson.server import mcp

if __name__ == "__main__":
    mcp.run()
