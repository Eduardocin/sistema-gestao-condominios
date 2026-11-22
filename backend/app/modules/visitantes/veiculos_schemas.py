import re
import uuid
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

from app.modules.visitantes.schemas import Entrada, Referencia

TextoVeiculo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class DadosVeiculo(Entrada):
    placa: Annotated[str, StringConstraints(max_length=20)]
    marca: TextoVeiculo
    modelo: TextoVeiculo
    cor: TextoVeiculo

    @field_validator("placa")
    @classmethod
    def normalizar_placa(cls, valor: str) -> str:
        placa = re.sub(r"[\s-]", "", valor).upper()
        if not re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", placa):
            raise ValueError("Informe uma placa brasileira válida.")
        return placa


class CadastroVeiculo(DadosVeiculo):
    unidade_id: uuid.UUID


class EdicaoVeiculo(DadosVeiculo):
    unidade_id: uuid.UUID | None = None


class VeiculoSaida(BaseModel):
    id: uuid.UUID
    unidade_id: uuid.UUID
    unidade: Referencia
    placa: str
    marca: str
    modelo: str
    cor: str
    ativo: bool
    placa_duplicada: bool | None = None
