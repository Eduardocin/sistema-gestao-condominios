import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.modules.auditoria import service as audit
from app.modules.auditoria.models import TipoEventoAuditoria
from app.modules.auth.security import hash_senha
from app.modules.condominios import wizard_repository
from app.modules.condominios.models import (
    AreaComum,
    BlocoCondominio,
    Condominio,
    RascunhoCondominio,
    VinculoCondominio,
)
from app.modules.condominios.wizard_schemas import (
    AreasComunsRequest,
    BlocosRequest,
    DadosGeraisRequest,
    ResponsavelRequest,
    UnidadesRequest,
)
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario

ETAPAS = ("dados_gerais", "blocos", "unidades", "areas_comuns", "responsavel")
DURACAO_RASCUNHO = timedelta(days=30)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _obter_rascunho(session: Session, *, rascunho_id: uuid.UUID, token: str) -> RascunhoCondominio:
    rascunho = wizard_repository.obter_rascunho(
        session, rascunho_id=rascunho_id, token_hash=_hash_token(token)
    )
    if rascunho is None:
        raise ApiError(404, "not_found", "Rascunho não encontrado.")
    if rascunho.expira_em <= datetime.now(UTC):
        raise ApiError(410, "draft_expired", "O prazo deste rascunho expirou.")
    return rascunho


def iniciar(session: Session) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    agora = datetime.now(UTC)
    rascunho = RascunhoCondominio(
        id=uuid.uuid4(),
        token_hash=_hash_token(token),
        etapa_atual=ETAPAS[0],
        expira_em=agora + DURACAO_RASCUNHO,
    )
    session.add(rascunho)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {
        "id": rascunho.id,
        "token": token,
        "etapa_atual": rascunho.etapa_atual,
        "expira_em": rascunho.expira_em,
    }


def _proxima_etapa(rascunho: RascunhoCondominio) -> str:
    for etapa in ETAPAS:
        if getattr(rascunho, etapa) is None:
            return etapa
    return ETAPAS[-1]


def obter_status(session: Session, *, rascunho_id: uuid.UUID, token: str) -> dict[str, Any]:
    rascunho = _obter_rascunho(session, rascunho_id=rascunho_id, token=token)
    responsavel_configurado = rascunho.responsavel is not None
    return {
        "id": rascunho.id,
        "etapa_atual": rascunho.etapa_atual,
        "expira_em": rascunho.expira_em,
        "dados_gerais": rascunho.dados_gerais,
        "blocos": rascunho.blocos,
        "unidades": rascunho.unidades,
        "areas_comuns": rascunho.areas_comuns,
        "responsavel_configurado": responsavel_configurado,
    }


def _validar_etapa_anterior(rascunho: RascunhoCondominio, etapa: str) -> None:
    indice = ETAPAS.index(etapa)
    if indice and getattr(rascunho, ETAPAS[indice - 1]) is None:
        raise ApiError(
            409,
            "wizard_step_incomplete",
            f"Conclua a etapa '{ETAPAS[indice - 1]}' antes desta etapa.",
        )


def _salvar_etapa(
    session: Session,
    *,
    rascunho_id: uuid.UUID,
    token: str,
    etapa: str,
    dados: Any,
) -> dict[str, Any]:
    rascunho = _obter_rascunho(session, rascunho_id=rascunho_id, token=token)
    _validar_etapa_anterior(rascunho, etapa)
    indice = ETAPAS.index(etapa)
    setattr(rascunho, etapa, dados)
    for etapa_posterior in ETAPAS[indice + 1 :]:
        setattr(rascunho, etapa_posterior, None)
    rascunho.etapa_atual = _proxima_etapa(rascunho)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return obter_status(session, rascunho_id=rascunho_id, token=token)


def salvar_dados_gerais(
    session: Session,
    *,
    rascunho_id: uuid.UUID,
    token: str,
    dados: DadosGeraisRequest,
) -> dict[str, Any]:
    return _salvar_etapa(
        session,
        rascunho_id=rascunho_id,
        token=token,
        etapa="dados_gerais",
        dados=dados.model_dump(mode="json"),
    )


def salvar_blocos(
    session: Session,
    *,
    rascunho_id: uuid.UUID,
    token: str,
    dados: BlocosRequest,
) -> dict[str, Any]:
    return _salvar_etapa(
        session,
        rascunho_id=rascunho_id,
        token=token,
        etapa="blocos",
        dados=[bloco.model_dump(mode="json") for bloco in dados.blocos],
    )


def salvar_unidades(
    session: Session,
    *,
    rascunho_id: uuid.UUID,
    token: str,
    dados: UnidadesRequest,
) -> dict[str, Any]:
    rascunho = _obter_rascunho(session, rascunho_id=rascunho_id, token=token)
    nomes_blocos = {bloco["nome"].casefold() for bloco in rascunho.blocos or []}
    nomes_geracoes = {geracao.bloco.casefold() for geracao in dados.geracoes}
    if nomes_blocos != nomes_geracoes:
        raise ApiError(
            422,
            "validation_error",
            "Configure a geração de unidades para cada bloco, sem blocos extras.",
        )
    return _salvar_etapa(
        session,
        rascunho_id=rascunho_id,
        token=token,
        etapa="unidades",
        dados=[geracao.model_dump(mode="json") for geracao in dados.geracoes],
    )


def salvar_areas_comuns(
    session: Session,
    *,
    rascunho_id: uuid.UUID,
    token: str,
    dados: AreasComunsRequest,
) -> dict[str, Any]:
    return _salvar_etapa(
        session,
        rascunho_id=rascunho_id,
        token=token,
        etapa="areas_comuns",
        dados=[area.model_dump(mode="json") for area in dados.areas_comuns],
    )


def salvar_responsavel(
    session: Session,
    *,
    rascunho_id: uuid.UUID,
    token: str,
    dados: ResponsavelRequest,
) -> dict[str, Any]:
    rascunho = _obter_rascunho(session, rascunho_id=rascunho_id, token=token)
    _validar_etapa_anterior(rascunho, "responsavel")
    if wizard_repository.obter_email_ou_cpf(session, email=dados.email, cpf=dados.cpf):
        raise ApiError(409, "conflict", "E-mail ou CPF já cadastrado.")
    responsavel = dados.model_dump(exclude={"senha"})
    responsavel["senha_hash"] = hash_senha(dados.senha)
    return _salvar_etapa(
        session,
        rascunho_id=rascunho_id,
        token=token,
        etapa="responsavel",
        dados=responsavel,
    )


def _validar_rascunho_completo(rascunho: RascunhoCondominio) -> None:
    etapas_faltantes = [etapa for etapa in ETAPAS if getattr(rascunho, etapa) is None]
    if etapas_faltantes:
        raise ApiError(
            409,
            "wizard_incomplete",
            f"Conclua as etapas antes de finalizar: {', '.join(etapas_faltantes)}.",
        )
    blocos = rascunho.blocos or []
    geracoes = rascunho.unidades or []
    if {bloco["nome"].casefold() for bloco in blocos} != {
        geracao["bloco"].casefold() for geracao in geracoes
    }:
        raise ApiError(422, "validation_error", "A configuração de unidades está inconsistente.")


def _criar_unidades(
    condominio_id: uuid.UUID,
    blocos: list[BlocoCondominio],
    geracoes: list[dict[str, Any]],
) -> list[Unidade]:
    ids_blocos = {bloco.nome.casefold(): bloco for bloco in blocos}
    unidades: list[Unidade] = []
    for geracao in geracoes:
        bloco = ids_blocos[geracao["bloco"].casefold()]
        andar_inicial = geracao["andar_inicial"]
        for andar in range(andar_inicial, andar_inicial + geracao["quantidade_andares"]):
            for numero in range(1, geracao["unidades_por_andar"] + 1):
                unidades.append(
                    Unidade(
                        id=uuid.uuid4(),
                        condominio_id=condominio_id,
                        bloco_id=bloco.id,
                        identificacao=f"{bloco.nome}-{andar:02d}-{numero:02d}",
                    )
                )
    return unidades


def finalizar(
    session: Session, *, rascunho_id: uuid.UUID, token: str, ip: str | None
) -> dict[str, Any]:
    rascunho = _obter_rascunho(session, rascunho_id=rascunho_id, token=token)
    _validar_rascunho_completo(rascunho)
    dados_gerais = rascunho.dados_gerais
    responsavel = rascunho.responsavel
    if dados_gerais is None or responsavel is None:
        raise ApiError(409, "wizard_incomplete", "Complete todas as etapas do wizard.")

    token_status_solicitacao = secrets.token_urlsafe(32)
    condominio = Condominio(
        id=uuid.uuid4(),
        ativo=False,
        status="pendente",
        token_status_solicitacao_hash=_hash_token(token_status_solicitacao),
        **dados_gerais,
    )
    usuario = Usuario(
        id=uuid.uuid4(),
        nome=responsavel["nome"],
        email=responsavel["email"],
        cpf=responsavel["cpf"],
        senha_hash=responsavel["senha_hash"],
        ativo=False,
        status_conta="pendente",
    )
    try:
        session.add(usuario)
        session.flush()
        condominio.solicitante_id = usuario.id
        session.add(condominio)
        session.flush()
        blocos = [
            BlocoCondominio(id=uuid.uuid4(), condominio_id=condominio.id, nome=bloco["nome"])
            for bloco in rascunho.blocos or []
        ]
        session.add_all(blocos)
        session.flush()
        unidades = _criar_unidades(condominio.id, blocos, rascunho.unidades or [])
        areas = [
            AreaComum(
                id=uuid.uuid4(),
                condominio_id=condominio.id,
                nome=area["nome"],
                descricao=area["descricao"],
            )
            for area in rascunho.areas_comuns or []
        ]
        vinculo = VinculoCondominio(
            id=uuid.uuid4(),
            usuario_id=usuario.id,
            condominio_id=condominio.id,
            perfil="administracao",
            ativo=False,
        )
        session.add_all([*unidades, *areas, vinculo])
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.CRIACAO_CONTA,
            recurso="usuario",
            recurso_id=str(usuario.id),
            usuario_id=usuario.id,
            ator=usuario.nome,
            perfil="administracao",
            condominio_id=condominio.id,
            ip=ip,
            conta_compartilhada=True,
            nome_responsavel=usuario.nome,
            dados_depois={"email": usuario.email, "status_conta": usuario.status_conta},
        )
        session.delete(rascunho)
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        raise ApiError(
            409, "conflict", "Não foi possível concluir: e-mail, CPF ou cadastro duplicado."
        ) from erro
    except Exception:
        session.rollback()
        raise

    return {
        "condominio_id": condominio.id,
        "condominio_ativo": condominio.ativo,
        "usuario_administracao_id": usuario.id,
        "unidades_criadas": len(unidades),
        "status_conta": usuario.status_conta,
        "token_status_solicitacao": token_status_solicitacao,
    }
