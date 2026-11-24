"""Dados dos testes de ocorrências, criados direto pelos models."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.ocorrencias.models import Ocorrencia, OcorrenciaAnexo, OcorrenciaInteracao
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario
from tests.autorizacao.cenario import Predio


def criar_arquivo(
    session: Session,
    predio: Predio,
    *,
    usuario: Usuario | None = None,
    modulo: str = "ocorrencias",
    tipo_mime: str = "image/jpeg",
    de_condominio: bool = True,
) -> Arquivo:
    arquivo = Arquivo(
        condominio_id=predio.condominio.id if de_condominio else None,
        chave_storage=f"condominio/{predio.condominio.id}/{modulo}/{uuid.uuid4()}",
        nome_original="anexo.jpg",
        tipo_mime=tipo_mime,
        tamanho_bytes=1024,
        enviado_por_usuario_id=(usuario or predio.morador).id,
    )
    session.add(arquivo)
    session.flush()
    return arquivo


def criar_ocorrencia(
    session: Session,
    predio: Predio,
    *,
    unidade: Unidade | None = None,
    usuario: Usuario | None = None,
    titulo: str = "Vazamento na garagem",
    detalhe: str = "Há água escorrendo do teto da vaga 12 desde ontem.",
    status: str = "em_aberto",
    criado_em: datetime | None = None,
    resolvida_em: datetime | None = None,
    anexos: tuple[Arquivo, ...] = (),
) -> Ocorrencia:
    valores: dict[str, Any] = {
        "condominio_id": predio.condominio.id,
        "unidade_id": (unidade or predio.unidade_101).id,
        "aberta_por_usuario_id": (usuario or predio.morador).id,
        "titulo": titulo,
        "detalhe": detalhe,
        "status": status,
    }
    if criado_em is not None:
        valores["criado_em"] = criado_em
    if status == "resolvida":
        valores["resolvida_em"] = resolvida_em or datetime.now(UTC)
    ocorrencia = Ocorrencia(**valores)
    session.add(ocorrencia)
    session.flush()
    for arquivo in anexos:
        session.add(
            OcorrenciaAnexo(
                condominio_id=predio.condominio.id,
                ocorrencia_id=ocorrencia.id,
                arquivo_id=arquivo.id,
            )
        )
    session.flush()
    return ocorrencia


def criar_interacao(
    session: Session,
    predio: Predio,
    ocorrencia: Ocorrencia,
    *,
    tipo: str = "resposta",
    texto: str = "Equipe de manutenção acionada.",
    responsavel: ResponsavelAdministracao | None = None,
    usuario: Usuario | None = None,
    criado_em: datetime | None = None,
) -> OcorrenciaInteracao:
    valores: dict[str, Any] = {
        "condominio_id": predio.condominio.id,
        "ocorrencia_id": ocorrencia.id,
        "tipo": tipo,
        "texto": texto,
        "usuario_id": (usuario or predio.administracao).id,
        "responsavel_id": responsavel.id if responsavel else None,
    }
    if criado_em is not None:
        valores["criado_em"] = criado_em
    interacao = OcorrenciaInteracao(**valores)
    session.add(interacao)
    session.flush()
    return interacao


def corpo(predio: Predio, unidade: Unidade | None = None, **campos: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "unidade_id": str((unidade or predio.unidade_101).id),
        "titulo": "Vazamento na garagem",
        "detalhe": "Há água escorrendo do teto da vaga 12 desde ontem.",
        "anexos": [],
    }
    base.update(campos)
    return base


def resposta(responsavel_id: uuid.UUID, texto: str = "Equipe de manutenção acionada.") -> dict:
    return {"texto": texto, "responsavel_id": str(responsavel_id)}


def resolucao(responsavel_id: uuid.UUID, texto: str | None = "Vazamento corrigido.") -> dict:
    return {"texto": texto, "responsavel_id": str(responsavel_id)}
