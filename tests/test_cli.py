"""Testa o ponto de entrada ``python -m minicurso_einfo_mcphandson``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJETO = Path(__file__).resolve().parents[1]


def _run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "minicurso_einfo_mcphandson", *args],
        cwd=PROJETO,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_cli_demo(tmp_path: Path) -> None:
    resultado = _run("client", "--db", str(tmp_path / "cli.db"), "demo")
    assert resultado.returncode == 0, resultado.stderr
    assert "== Tools ==" in resultado.stdout
    assert "diagnosticar_talhao" in resultado.stdout
    assert "is_error=True" in resultado.stdout


def test_cli_call(tmp_path: Path) -> None:
    resultado = _run(
        "client",
        "--db",
        str(tmp_path / "cli.db"),
        "call",
        "recomendar_irrigacao",
        '{"talhao_id": "T-002", "horizonte_dias": 3}',
    )
    assert resultado.returncode == 0, resultado.stderr
    assert '"prioridade": "alta"' in resultado.stdout
    assert '"horizonte_dias": 3' in resultado.stdout
