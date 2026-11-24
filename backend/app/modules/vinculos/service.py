import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.tempo import Relogio, agora
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO, garantir_aba_da_unidade
from app.modules.funcionarios.repository import RepositorioResponsaveis
from app.modules.permissoes_aba.repository import RepositorioMoradores as MoradoresDaUnidade
from app.modules.permissoes_aba.repository import RepositorioPermissoes
from app.modules.unidades.models import ABAS_MORADOR, Unidade
from app.modules.unidades.repository import (
    RepositorioChaves,
    RepositorioProprietarios,
    RepositorioUnidades,
)
from app.modules.usuarios.models import TentativaChaveAcesso, Usuario
from app.modules.vinculos import repository, schemas

JANELA = timedelta(minutes=15)
MENSAGEM_CHAVE_INVALIDA = (
    "Chave de acesso inválida ou já substituída. Peça uma nova à Administração."
)


def exigir_conta_morador(usuario: Usuario) -> None:
    if usuario.administrador_plataforma or usuario.tipo_cadastro != "morador":
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")


def bloqueio_restante(tentativas: list[TentativaChaveAcesso], momento: datetime) -> int:
    falhas: list[datetime] = []
    bloqueado_ate: datetime | None = None
    for tentativa in tentativas:
        if tentativa.sucesso:
            falhas, bloqueado_ate = [], None
        elif bloqueado_ate is not None and tentativa.criado_em < bloqueado_ate:
            # Registrar um 429 não renova o prazo nem conta como outra avaliação de chave.
            continue
        else:
            if bloqueado_ate is not None:
                falhas, bloqueado_ate = [], None
            falhas = [t for t in falhas if t > tentativa.criado_em - JANELA]
            falhas.append(tentativa.criado_em)
            if len(falhas) >= 5:
                bloqueado_ate = tentativa.criado_em + JANELA
                falhas = []
    return max(0, math.ceil((bloqueado_ate - momento).total_seconds())) if bloqueado_ate else 0


def recusar_tentativa(
    session: Session, usuario_id: uuid.UUID, momento: datetime, *, ip: str | None, segundos: int = 0
) -> NoReturn:
    repository.registrar_tentativa(session, usuario_id, sucesso=False, momento=momento)
    # Transação concluída ANTES do erro HTTP; o rollback da dependência não apaga a tentativa.
    session.commit()
    auditoria.registrar_evento_seguranca(
        acao="seguranca.chave_invalida",
        usuario_id=usuario_id,
        condominio_id=None,
        ip=ip,
        detalhe={"status_http": 429 if segundos else 404},
    )
    if segundos:
        raise ApiError(
            429,
            "too_many_attempts",
            "Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(segundos)},
        )
    raise ApiError(404, "not_found", MENSAGEM_CHAVE_INVALIDA)


def vincular(
    session: Session,
    usuario: Usuario,
    dados: schemas.VinculoEntrada,
    *,
    ip: str | None,
    relogio: Relogio = agora,
) -> schemas.VinculoSaida:
    exigir_conta_morador(usuario)
    usuario_id = usuario.id
    try:
        usuario = repository.bloquear_conta(session, usuario_id)
        exigir_conta_morador(usuario)
        tentativas = repository.tentativas_desde_sucesso(session, usuario_id)
        momento = relogio().astimezone(UTC)
        if tentativas and momento <= tentativas[-1].criado_em:
            # Ordem inequívoca mesmo com um relógio de teste congelado ou resolução igual.
            momento = tentativas[-1].criado_em + timedelta(microseconds=1)
        segundos = bloqueio_restante(tentativas, momento)
        if segundos:
            recusar_tentativa(session, usuario_id, momento, ip=ip, segundos=segundos)
        chave = repository.localizar_chave(session, dados.chave)
        destino = repository.bloquear_destino(session, chave) if chave is not None else None
        if destino is None:
            recusar_tentativa(session, usuario_id, momento, ip=ip)
        condominio, unidade = destino
        vinculo = repository.obter_vinculo(session, usuario_id, condominio.id)
        if vinculo is not None and vinculo.perfil != "morador":
            raise ApiError(
                409,
                "conflict",
                "A conta possui outro perfil neste condomínio.",
                reason="perfil_incompativel",
            )
        if vinculo is None:
            vinculo = repository.criar_vinculo(session, usuario_id, condominio.id)
        contexto = ContextoCondominio(
            usuario_id=usuario_id,
            condominio_id=condominio.id,
            perfil="morador",
            vinculo_id=vinculo.id,
        )
        moradores = repository.RepositorioMoradores(session, contexto)
        if moradores.ja_vinculado(unidade.id):
            raise ApiError(409, "conflict", "Já vinculado à unidade.", reason="ja_vinculado")
        primeiro = MoradoresDaUnidade(session, contexto).contar_da_unidade(unidade.id) == 0
        vinculo.ativo = True
        morador = moradores.criar(
            {
                "usuario_id": usuario_id,
                "unidade_id": unidade.id,
                "status": "ativo",
                "origem": "chave",
                "vinculado_em": momento,
            }
        )
        RepositorioPermissoes(session, contexto).definir(
            morador.id,
            {aba: primeiro or aba != "usuarios" for aba in ABAS_MORADOR},
            alterado_por=usuario_id,
        )
        repository.registrar_tentativa(session, usuario_id, sucesso=True, momento=momento)
        auditoria.registrar_acao(
            session,
            ctx=ContextoAuditoria.do_condominio(contexto, ip=ip),
            acao="vinculo.aprovar",
            recurso_tipo="morador_unidade",
            recurso_id=morador.id,
            antes={},
            depois={"status": "ativo", "origem": "chave", "unidade_id": unidade.id},
        )
        saida = schemas.VinculoSaida(
            unidade=schemas.ReferenciaUnidade(id=unidade.id, identificacao=unidade.identificacao),
            condominio=schemas.ReferenciaCondominio(id=condominio.id, nome=condominio.nome),
        )
        session.commit()
        return saida
    except SQLAlchemyError:
        session.rollback()
        # Erros de driver podem carregar o código da chave nos parâmetros SQL.
        raise ApiError(500, "internal_error", "Não foi possível registrar o vínculo.") from None
    except Exception:
        session.rollback()
        raise


class MinhasUnidadesService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.unidades = repository.RepositorioMinhasUnidades(session, contexto)
        self.proprietarios = RepositorioProprietarios(session, contexto)

    def saida(
        self, unidade: Unidade, condominio: schemas.ReferenciaCondominio
    ) -> schemas.MinhaUnidade:
        proprietario = self.proprietarios.da_unidade(unidade.id)
        return schemas.MinhaUnidade(
            id=unidade.id,
            identificacao=unidade.identificacao,
            condominio=condominio,
            proprietario=schemas.ProprietarioPublico.model_validate(proprietario)
            if proprietario
            else None,
        )

    def listar(self, filtros: schemas.FiltrosMinhasUnidades) -> schemas.PaginaMinhasUnidades:
        unidades, total = self.unidades.pagina(filtros.page, filtros.page_size)
        condominio = self.unidades.condominio()
        referencia = schemas.ReferenciaCondominio(id=condominio.id, nome=condominio.nome)
        return schemas.PaginaMinhasUnidades(
            items=[self.saida(u, referencia) for u in unidades],
            page=filtros.page,
            page_size=filtros.page_size,
            total=total,
        )

    def detalhe(self, id_: uuid.UUID) -> schemas.MinhaUnidade:
        unidade = self.unidades.obter_vinculada(id_)
        garantir_aba_da_unidade(self.session, self.contexto, id_, "unidades")
        condominio = self.unidades.condominio()
        return self.saida(
            unidade, schemas.ReferenciaCondominio(id=condominio.id, nome=condominio.nome)
        )


def desvincular(
    session: Session,
    contexto: ContextoCondominio,
    unidade_id: uuid.UUID,
    morador_unidade_id: uuid.UUID,
    dados: schemas.DesvinculacaoEntrada,
    *,
    ip: str | None,
    relogio: Relogio = agora,
) -> schemas.DesvinculacaoSaida:
    try:
        if contexto.perfil not in {"morador", "administracao"}:
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        if contexto.perfil == "morador" and dados.model_fields_set:
            raise ApiError(422, "validation_error", "Morador deve enviar um corpo vazio.")
        if contexto.perfil == "administracao" and dados.responsavel_id is None:
            raise ApiError(422, "validation_error", "Informe o responsável pela ação.")

        moradores = repository.RepositorioMoradores(session, contexto)
        usuario_id = moradores.usuario_do_alvo(unidade_id, morador_unidade_id)
        # Não travar a conta do executor: em remoções mútuas isso inverteria a ordem.
        # SHARE é compatível com SHARE da portaria e KEY SHARE das FKs de autor/auditoria.
        # Conflita com a vinculação; desvínculos paralelos serializam a decisão no vínculo global.
        repository.bloquear_conta(session, usuario_id, compartilhada=True)
        condominio = repository.bloquear_condominio(session, contexto)
        if condominio.status != "ativo":
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        responsavel = None
        if contexto.perfil == "administracao":
            assert dados.responsavel_id is not None
            RepositorioResponsaveis(session, contexto).obter_ativo(dados.responsavel_id)
            responsavel = ResponsavelRef("administracao", dados.responsavel_id)
        # A validação do responsável precede a unidade, como na gestão de chaves.
        unidade = RepositorioUnidades(session, contexto).bloquear(unidade_id)
        if not unidade.ativo:
            raise ApiError(409, "conflict", "Unidade inativa.", reason="unidade_inativa")
        if not repository.executor_habilitado(session, contexto):
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        garantir_aba_da_unidade(session, contexto, unidade_id, "usuarios")
        alvo = moradores.associacao(unidade_id, morador_unidade_id)
        if alvo.usuario_id != usuario_id:
            raise RecursoNaoEncontrado
        if alvo.status == "desvinculado":
            raise ApiError(409, "conflict", "Morador já desvinculado.", reason="ja_desvinculado")
        if contexto.perfil == "morador" and alvo.usuario_id == contexto.usuario_id:
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        restantes = MoradoresDaUnidade(session, contexto).contar_da_unidade(
            unidade_id, excluindo=alvo.id
        )
        if (
            restantes
            and RepositorioPermissoes(session, contexto).contar_com_usuarios(
                unidade_id, excluindo=alvo.id
            )
            == 0
        ):
            raise ApiError(
                409,
                "conflict",
                "Transfira o acesso à aba Usuários antes da desvinculação.",
                reason="ultimo_usuarios",
            )
        vinculo = repository.obter_vinculo(session, usuario_id, contexto.condominio_id)
        if vinculo is None or vinculo.perfil != "morador":
            raise ApiError(409, "conflict", "Vínculo incompatível.", reason="perfil_incompativel")
        ativo_antes = vinculo.ativo
        if not moradores.tem_outra_unidade_ativa(usuario_id, excluindo=alvo.id):
            vinculo.ativo = False
        momento = relogio().astimezone(UTC)
        alvo.status = "desvinculado"
        alvo.desvinculado_em = momento
        alvo.desvinculado_por_usuario_id = contexto.usuario_id
        chave = RepositorioChaves(session, contexto).vigente(unidade_id)
        if chave is not None:
            chave.revogada_em = momento
        auditoria.registrar_acao(
            session,
            ctx=ContextoAuditoria.do_condominio(contexto, ip=ip),
            acao="vinculo.desfazer",
            recurso_tipo="morador_unidade",
            recurso_id=alvo.id,
            responsavel=responsavel,
            antes={"status": "ativo", "vinculo_condominio_ativo": ativo_antes},
            depois={
                "status": alvo.status,
                "unidade_id": unidade_id,
                "desvinculado_em": momento,
                "vinculo_condominio_ativo": vinculo.ativo,
                "vinculo_condominio_desativado": ativo_antes and not vinculo.ativo,
                "chave_revogada": chave is not None,
                "chave_id": chave.id if chave is not None else None,
            },
        )
        saida = schemas.DesvinculacaoSaida(
            id=alvo.id, desvinculado_em=momento, chave_revogada=chave is not None
        )
        session.commit()
        return saida
    except SQLAlchemyError:
        session.rollback()
        raise ApiError(500, "internal_error", "Não foi possível desvincular o morador.") from None
    except Exception:
        session.rollback()
        raise
