import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.modules.auditoria import service as audit
from app.modules.auditoria.models import PERFIS_CONTAS_COMPARTILHADAS, TipoEventoAuditoria
from app.modules.auth.security import hash_senha
from app.modules.condominios import aprovacao_service
from app.modules.condominios.models import VinculoCondominio
from app.modules.usuarios import repository
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.schemas import (
    CadastroAdministracaoRequest,
    CadastroFuncionarioRequest,
    CadastroMoradorRequest,
    EditarUsuarioRequest,
)


def _verificar_unicidade(
    session: Session,
    *,
    email: str,
    cpf: str | None,
    exceto_usuario_id: uuid.UUID | None = None,
) -> None:
    if repository.obter_por_email(session, email, exceto_usuario_id=exceto_usuario_id):
        raise ApiError(409, "conflict", "E-mail já cadastrado.")
    if cpf is not None and repository.obter_por_cpf(
        session, cpf, exceto_usuario_id=exceto_usuario_id
    ):
        raise ApiError(409, "conflict", "CPF já cadastrado.")


def _nova_conta(
    dados: CadastroMoradorRequest | CadastroFuncionarioRequest | CadastroAdministracaoRequest,
) -> Usuario:
    return Usuario(
        id=uuid.uuid4(),
        nome=dados.nome,
        email=dados.email,
        cpf=dados.cpf,
        senha_hash=hash_senha(dados.senha),
        ativo=False,
        status_conta="pendente",
    )


def _gravar_criacao(
    session: Session,
    usuario: Usuario,
    *,
    perfil: str,
    condominio_id: uuid.UUID | None,
    ip: str | None,
    nome_responsavel: str | None = None,
) -> None:
    audit.log(
        session,
        tipo_evento=TipoEventoAuditoria.CRIACAO_CONTA,
        recurso="usuario",
        recurso_id=str(usuario.id),
        usuario_id=usuario.id,
        ator=usuario.nome,
        perfil=perfil,
        condominio_id=condominio_id,
        ip=ip,
        conta_compartilhada=perfil in PERFIS_CONTAS_COMPARTILHADAS,
        nome_responsavel=nome_responsavel,
        dados_depois={"email": usuario.email, "status_conta": usuario.status_conta},
    )


def _commit_or_conflict(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        raise ApiError(409, "conflict", "E-mail ou CPF já cadastrado.") from erro


def cadastrar_morador(
    session: Session, *, dados: CadastroMoradorRequest, ip: str | None
) -> Usuario:
    _verificar_unicidade(session, email=dados.email, cpf=dados.cpf)
    usuario = _nova_conta(dados)
    try:
        condominio = aprovacao_service.consumir_chave(session, codigo=dados.chave_acesso)
        session.add(usuario)
        session.flush()
        session.add(
            VinculoCondominio(
                id=uuid.uuid4(),
                usuario_id=usuario.id,
                condominio_id=condominio.id,
                perfil="morador",
                ativo=False,
            )
        )
        session.flush()
        _gravar_criacao(
            session,
            usuario,
            perfil="morador",
            condominio_id=condominio.id,
            ip=ip,
        )
        _commit_or_conflict(session)
    except Exception:
        session.rollback()
        raise
    return usuario


def cadastrar_funcionario(
    session: Session, *, dados: CadastroFuncionarioRequest, ip: str | None
) -> Usuario:
    _verificar_unicidade(session, email=dados.email, cpf=dados.cpf)
    usuario = _nova_conta(dados)
    try:
        condominio = aprovacao_service.consumir_chave(session, codigo=dados.chave_acesso)
        session.add(usuario)
        session.flush()
        session.add(
            VinculoCondominio(
                id=uuid.uuid4(),
                usuario_id=usuario.id,
                condominio_id=condominio.id,
                perfil="funcionario",
                ativo=False,
            )
        )
        session.flush()
        _gravar_criacao(
            session,
            usuario,
            perfil="funcionario",
            condominio_id=condominio.id,
            ip=ip,
            nome_responsavel=dados.nome_responsavel,
        )
        _commit_or_conflict(session)
    except Exception:
        session.rollback()
        raise
    return usuario


def cadastrar_administracao(
    session: Session,
    *,
    dados: CadastroAdministracaoRequest,
    ip: str | None,
) -> Usuario:
    _verificar_unicidade(session, email=dados.email, cpf=dados.cpf)
    condominio = repository.obter_condominio(session, dados.condominio_id)
    if condominio is None:
        raise ApiError(404, "not_found", "Condomínio não encontrado.")

    usuario = _nova_conta(dados)
    vinculo = VinculoCondominio(
        usuario_id=usuario.id,
        condominio_id=condominio.id,
        perfil="administracao",
        ativo=False,
    )
    try:
        session.add(usuario)
        session.flush()
        session.add(vinculo)
        session.flush()
        _gravar_criacao(
            session,
            usuario,
            perfil="administracao",
            condominio_id=condominio.id,
            ip=ip,
            nome_responsavel=dados.nome,
        )
        _commit_or_conflict(session)
    except Exception:
        session.rollback()
        raise
    return usuario


def obter_proprio_perfil(usuario: Usuario) -> Usuario:
    return usuario


def editar_proprio_perfil(
    session: Session,
    *,
    usuario: Usuario,
    condominio_id: uuid.UUID | None,
    dados: EditarUsuarioRequest,
    ip: str | None,
) -> Usuario:
    alteracoes = dados.model_dump(exclude_unset=True, exclude={"nome_responsavel"})
    responsavel = dados.nome_responsavel
    _verificar_unicidade(
        session,
        email=alteracoes.get("email", usuario.email),
        cpf=alteracoes.get("cpf", usuario.cpf),
        exceto_usuario_id=usuario.id,
    )

    vinculos = repository.listar_vinculos(session, usuario.id)
    perfis = {vinculo.perfil for vinculo, _ in vinculos}
    conta_compartilhada = bool(perfis & PERFIS_CONTAS_COMPARTILHADAS)
    if conta_compartilhada and not (responsavel and responsavel.strip()):
        raise ApiError(
            422,
            "validation_error",
            "Informe o nome da pessoa responsável para editar uma conta compartilhada.",
        )

    perfil = (
        repository.perfil_no_condominio(session, usuario.id, condominio_id)
        if condominio_id
        else None
    )
    if perfil is None and len(perfis) == 1:
        perfil = next(iter(perfis))
    contexto_condominio = condominio_id
    if contexto_condominio is None and len(vinculos) == 1:
        contexto_condominio = vinculos[0][1].id
    if usuario.administrador_plataforma:
        perfil = "plataforma"

    antes = {campo: getattr(usuario, campo) for campo in alteracoes}
    dados_antes = {campo: valor for campo, valor in antes.items() if campo != "cpf"}
    if "cpf" in antes:
        dados_antes["cpf_alterado"] = True
    for campo, valor in alteracoes.items():
        setattr(usuario, campo, valor)
    dados_depois = {campo: valor for campo, valor in alteracoes.items() if campo != "cpf"}
    if "cpf" in alteracoes:
        dados_depois["cpf_alterado"] = True

    try:
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.EDICAO_CONTA,
            recurso="usuario",
            recurso_id=str(usuario.id),
            usuario_id=usuario.id,
            ator=str(antes.get("nome", usuario.nome)),
            perfil=perfil,
            condominio_id=contexto_condominio,
            ip=ip,
            conta_compartilhada=conta_compartilhada,
            nome_responsavel=responsavel,
            dados_antes=dados_antes,
            dados_depois=dados_depois,
        )
        _commit_or_conflict(session)
    except Exception:
        session.rollback()
        raise
    return usuario
