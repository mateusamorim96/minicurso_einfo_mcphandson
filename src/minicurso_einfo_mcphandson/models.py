"""Modelos de domínio do AgroMCP.

Toda a validação de entrada e de saída do servidor MCP passa por estes modelos
Pydantic. As anotações de tipo das funções registradas como tools geram o JSON
Schema que o modelo (LLM) vê em ``tools/list``; os modelos de retorno geram o
``outputSchema`` e o ``structuredContent`` das respostas.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Severidade = Literal["baixa", "media", "alta"]
StatusTalhao = Literal["ativo", "atencao", "inativo"]
Cultura = Literal["uva", "manga", "melo", "cana"]


class CulturaInfo(BaseModel):
    """Parâmetros agronômicos usados nos cálculos de irrigação."""

    nome: str
    kc: float = Field(description="Coeficiente cultural (Kc) na fase atual.")
    umidade_critica_pct: float = Field(
        description="Umidade do solo abaixo da qual a planta entra em estresse."
    )
    profundidade_raiz_mm: float = Field(
        description="Profundidade efetiva do sistema radicular, em milímetros."
    )
    lamina_maxima_mm_dia: float = Field(
        description="Lâmina máxima recomendada por dia, em milímetros."
    )


class Leitura(BaseModel):
    """Uma leitura diária de sensores no talhão."""

    data: date
    umidade_solo_pct: float = Field(ge=0, le=100)
    ndvi: float = Field(ge=-1, le=1)


class Observacao(BaseModel):
    """Observação de campo registrada por uma pessoa."""

    id: int
    texto: str
    severidade: Severidade
    criado_em: datetime


class TalhaoResumo(BaseModel):
    """Visão resumida de um talhão, usada em listagens."""

    id: str
    nome: str
    fazenda: str
    cultura: Cultura
    area_ha: float = Field(gt=0)
    status: StatusTalhao
    umidade_solo_pct: float = Field(ge=0, le=100)
    ndvi: float = Field(ge=-1, le=1)


class TalhaoDetalhe(TalhaoResumo):
    """Ficha completa de um talhão, incluindo histórico e observações."""

    municipio: str
    solo: str
    temperatura_c: float
    atualizado_em: datetime
    leituras: list[Leitura]
    observacoes: list[Observacao]


class RecomendacaoIrrigacao(BaseModel):
    """Resultado do cálculo de necessidade hídrica para um horizonte de dias."""

    talhao_id: str
    cultura: Cultura
    horizonte_dias: int = Field(ge=1, le=14)
    etc_mm_dia: float = Field(description="Evapotranspiração da cultura, em mm/dia.")
    necessidade_total_mm: float = Field(ge=0)
    volume_m3: float = Field(ge=0)
    prioridade: Literal["baixa", "media", "alta"]
    recomendacoes: list[str]
    alertas: list[str]


class DiagnosticoTalhao(BaseModel):
    """Diagnóstico sintético produzido a partir das leituras e do catálogo."""

    talhao_id: str
    score: int = Field(ge=0, le=100)
    classificacao: Literal["saudavel", "atencao", "critico"]
    fatores: list[str]
    proximos_passos: list[str]


class ConfirmacaoObservacao(BaseModel):
    """Formulário de confirmação humana solicitado via Elicitation."""

    confirmado: bool = Field(
        description="Confirma a gravação desta observação de alta severidade?"
    )
    responsavel: str = Field(
        default="agrônomo-de-plantão",
        description="Nome ou identificação de quem aprovou o registro.",
    )


class ObservacaoRegistrada(BaseModel):
    """Confirmação de uma observação gravada no banco."""

    id: int
    talhao_id: str
    severidade: Severidade
    responsavel: str = "automático"
    criado_em: datetime
    mensagem: str
