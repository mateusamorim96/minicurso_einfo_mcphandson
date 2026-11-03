"""Camada de acesso a dados do AgroMCP.

O curso usa SQLite para manter o laboratório autocontido: nenhum serviço externo,
nenhuma credencial e um arquivo que pode ser apagado e recriado a qualquer momento.
As consultas são sempre parametrizadas; nenhuma tool aceita SQL vindo do modelo.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import CulturaInfo, Observacao, TalhaoDetalhe, TalhaoResumo

SCHEMA = """
CREATE TABLE IF NOT EXISTS talhoes (
    id                 TEXT PRIMARY KEY,
    nome               TEXT NOT NULL,
    fazenda            TEXT NOT NULL,
    municipio          TEXT NOT NULL,
    cultura            TEXT NOT NULL,
    area_ha            REAL NOT NULL,
    solo               TEXT NOT NULL,
    status             TEXT NOT NULL,
    umidade_solo_pct   REAL NOT NULL,
    ndvi               REAL NOT NULL,
    temperatura_c      REAL NOT NULL,
    atualizado_em      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leituras (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    talhao_id          TEXT NOT NULL REFERENCES talhoes(id) ON DELETE CASCADE,
    data               TEXT NOT NULL,
    umidade_solo_pct   REAL NOT NULL,
    ndvi               REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leituras_talhao
    ON leituras (talhao_id, data DESC);

CREATE TABLE IF NOT EXISTS observacoes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    talhao_id          TEXT NOT NULL REFERENCES talhoes(id) ON DELETE CASCADE,
    texto              TEXT NOT NULL,
    severidade         TEXT NOT NULL,
    criado_em          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observacoes_talhao
    ON observacoes (talhao_id, criado_em DESC);
"""

# Catálogo agronômico fictício, porém plausível para uma demonstração.
# Em produção, estes valores viriam de uma fonte agronômica versionada.
CULTURAS: dict[str, CulturaInfo] = {
    "uva": CulturaInfo(
        nome="Uva",
        kc=0.80,
        umidade_critica_pct=22.0,
        profundidade_raiz_mm=600.0,
        lamina_maxima_mm_dia=6.5,
    ),
    "manga": CulturaInfo(
        nome="Manga",
        kc=0.75,
        umidade_critica_pct=20.0,
        profundidade_raiz_mm=800.0,
        lamina_maxima_mm_dia=7.0,
    ),
    "melo": CulturaInfo(
        nome="Melão",
        kc=0.95,
        umidade_critica_pct=18.0,
        profundidade_raiz_mm=350.0,
        lamina_maxima_mm_dia=5.5,
    ),
    "cana": CulturaInfo(
        nome="Cana-de-açúcar",
        kc=1.05,
        umidade_critica_pct=24.0,
        profundidade_raiz_mm=900.0,
        lamina_maxima_mm_dia=8.0,
    ),
}

# Sementes fixas: o laboratório começa sempre com o mesmo cenário.
_SEED = [
    (
        "T-001",
        "Parcela Norte",
        "Fazenda Boa Vista",
        "Petrolina/PE",
        "uva",
        4.2,
        "Latossolo",
        "ativo",
        27.5,
        0.81,
        33.4,
    ),
    (
        "T-002",
        "Parcela Sul",
        "Fazenda Boa Vista",
        "Petrolina/PE",
        "uva",
        3.8,
        "Argissolo",
        "atencao",
        19.8,
        0.63,
        34.1,
    ),
    (
        "T-003",
        "Manga A",
        "Fazenda Santa Clara",
        "Juazeiro/BA",
        "manga",
        6.8,
        "Latossolo",
        "ativo",
        24.1,
        0.76,
        32.8,
    ),
    (
        "T-004",
        "Manga B",
        "Fazenda Santa Clara",
        "Juazeiro/BA",
        "manga",
        5.4,
        "Neossolo",
        "ativo",
        22.7,
        0.71,
        33.0,
    ),
    (
        "T-005",
        "Melão Experimental",
        "Fazenda Boa Vista",
        "Petrolina/PE",
        "melo",
        1.6,
        "Argissolo",
        "atencao",
        16.2,
        0.55,
        35.2,
    ),
    (
        "T-006",
        "Cana do Vale",
        "Usina Vale Verde",
        "Petrolina/PE",
        "cana",
        12.0,
        "Latossolo",
        "inativo",
        25.9,
        0.68,
        31.9,
    ),
]


class AgroDB:
    """Repositório SQLite com operações pequenas e explícitas."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        """Cria o schema e popula o cenário apenas quando o banco está vazio."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            total = conn.execute("SELECT COUNT(*) FROM talhoes").fetchone()[0]
            if total == 0:
                self._seed(conn)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _seed(self, conn: sqlite3.Connection) -> None:
        now = datetime.now(UTC).replace(microsecond=0)
        hoje = datetime.now(UTC).date()

        for row in _SEED:
            conn.execute(
                """
                INSERT INTO talhoes (
                    id, nome, fazenda, municipio, cultura, area_ha, solo,
                    status, umidade_solo_pct, ndvi, temperatura_c, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*row, now.isoformat()),
            )

            # Série de sete dias com uma tendência suave e determinística.
            base_umidade, base_ndvi = row[8], row[9]
            for offset in range(7, 0, -1):
                dia = hoje - timedelta(days=offset)
                variacao = ((offset * 7) % 5 - 2) * 0.35
                conn.execute(
                    """
                    INSERT INTO leituras (talhao_id, data, umidade_solo_pct, ndvi)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        row[0],
                        dia.isoformat(),
                        round(base_umidade + variacao, 2),
                        round(min(1.0, max(0.0, base_ndvi + variacao / 100)), 3),
                    ),
                )

        conn.executemany(
            """
            INSERT INTO observacoes (talhao_id, texto, severidade, criado_em)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    "T-002",
                    "Sinal de déficit hídrico nas bordas da parcela.",
                    "alta",
                    (now - timedelta(days=1)).isoformat(),
                ),
                (
                    "T-005",
                    "Plantas com folhas amareladas em um trecho de 20 m.",
                    "media",
                    (now - timedelta(days=2)).isoformat(),
                ),
                (
                    "T-003",
                    "Troca de filtro do sistema de gotejamento concluída.",
                    "baixa",
                    (now - timedelta(days=4)).isoformat(),
                ),
            ],
        )

    def listar_talhoes(
        self,
        cultura: str | None = None,
        status: str | None = None,
    ) -> list[TalhaoResumo]:
        sql = "SELECT * FROM talhoes WHERE 1 = 1"
        params: list[Any] = []
        if cultura:
            sql += " AND cultura = ?"
            params.append(cultura)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id"

        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            TalhaoResumo(
                id=r["id"],
                nome=r["nome"],
                fazenda=r["fazenda"],
                cultura=r["cultura"],
                area_ha=r["area_ha"],
                status=r["status"],
                umidade_solo_pct=r["umidade_solo_pct"],
                ndvi=r["ndvi"],
            )
            for r in rows
        ]

    def obter_talhao(self, talhao_id: str) -> TalhaoDetalhe | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM talhoes WHERE id = ?", (talhao_id,)
            ).fetchone()
            if row is None:
                return None

            leituras = conn.execute(
                """
                SELECT data, umidade_solo_pct, ndvi
                FROM leituras WHERE talhao_id = ?
                ORDER BY data DESC LIMIT 7
                """,
                (talhao_id,),
            ).fetchall()
            observacoes = conn.execute(
                """
                SELECT id, texto, severidade, criado_em
                FROM observacoes WHERE talhao_id = ?
                ORDER BY criado_em DESC, id DESC
                """,
                (talhao_id,),
            ).fetchall()

        return TalhaoDetalhe(
            id=row["id"],
            nome=row["nome"],
            fazenda=row["fazenda"],
            municipio=row["municipio"],
            cultura=row["cultura"],
            area_ha=row["area_ha"],
            solo=row["solo"],
            status=row["status"],
            umidade_solo_pct=row["umidade_solo_pct"],
            ndvi=row["ndvi"],
            temperatura_c=row["temperatura_c"],
            atualizado_em=row["atualizado_em"],
            leituras=[dict(r) for r in leituras],
            observacoes=[
                Observacao(
                    id=o["id"],
                    texto=o["texto"],
                    severidade=o["severidade"],
                    criado_em=o["criado_em"],
                )
                for o in observacoes
            ],
        )

    def registrar_observacao(
        self,
        talhao_id: str,
        texto: str,
        severidade: str,
    ) -> tuple[int, datetime]:
        criado_em = datetime.now(UTC).replace(microsecond=0)
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO observacoes (talhao_id, texto, severidade, criado_em)
                VALUES (?, ?, ?, ?)
                """,
                (talhao_id, texto, severidade, criado_em.isoformat()),
            )
            conn.commit()
            return int(cursor.lastrowid or 0), criado_em

    def resumo(self) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            por_cultura = {
                r["cultura"]: r["total"]
                for r in conn.execute(
                    "SELECT cultura, COUNT(*) AS total FROM talhoes GROUP BY cultura"
                )
            }
            area = conn.execute(
                "SELECT COALESCE(SUM(area_ha), 0) FROM talhoes"
            ).fetchone()[0]
            alertas = conn.execute(
                "SELECT COUNT(*) FROM talhoes WHERE status = 'atencao'"
            ).fetchone()[0]
        return {
            "talhoes": sum(por_cultura.values()),
            "por_cultura": por_cultura,
            "area_total_ha": round(area, 2),
            "talhoes_em_atencao": alertas,
        }
