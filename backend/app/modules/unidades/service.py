import secrets
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.tempo import Relogio, agora
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef
from app.modules.funcionarios.repository import RepositorioFotos, RepositorioResponsaveis
from app.modules.unidades import repository
from app.modules.unidades.models import ChaveAcesso, Unidade
from app.modules.unidades.schemas import (
    ChaveSaida,
    FiltrosUnidades,
    PaginaUnidades,
    ProprietarioEntrada,
    ProprietarioSaida,
    RevogacaoSaida,
    UnidadeDetalhe,
    UnidadeResumo,
)

# O contrato exclui 0/O/1/I/L: são 31 símbolos alfanuméricos distintos.
ALFABETO_CHAVE = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def gerar_codigo() -> str:
    return "".join(secrets.choice(ALFABETO_CHAVE) for _ in range(10))


def gerar_chave(session: Session, unidade: Unidade, momento: datetime) -> ChaveAcesso:
    for _ in range(5):
        try:
            # Só a tentativa colidente é revertida; preserva a transação principal.
            with session.begin_nested():
                return repository.inserir_chave(session, unidade, gerar_codigo(), momento)
        except IntegrityError as erro:
            constraint = getattr(getattr(erro.orig, "diag", None), "constraint_name", None)
            if constraint != "uq_chaves_acesso_codigo":
                # Não deixar parâmetros SQL com códigos chegarem ao logger de exceções.
                raise ApiError(500, "internal_error", "Não foi possível gerar a chave.") from None
        except SQLAlchemyError:
            raise ApiError(500, "internal_error", "Não foi possível gerar a chave.") from None
    raise ApiError(
        503, "temporarily_unavailable", "Não foi possível gerar a chave. Tente novamente."
    )


def saida_chave(chave: ChaveAcesso) -> ChaveSaida:
    return ChaveSaida(
        codigo=f"{chave.codigo[:5]}-{chave.codigo[5:]}",
        criada_em=chave.criada_em.astimezone(UTC),
    )


class UnidadesService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.unidades = repository.RepositorioUnidades(session, contexto)
        self.chaves = repository.RepositorioChaves(session, contexto)
        self.proprietarios = repository.RepositorioProprietarios(session, contexto)
        self.responsaveis = RepositorioResponsaveis(session, contexto)

    def resumo(self, unidade: Unidade) -> UnidadeResumo:
        bloco, andar = self.unidades.localizacao(unidade)
        return UnidadeResumo(
            id=unidade.id,
            identificacao=unidade.identificacao,
            ativo=unidade.ativo,
            bloco=bloco,
            andar=andar,
            tem_proprietario=self.proprietarios.da_unidade(unidade.id) is not None,
        )

    def listar(self, filtros: FiltrosUnidades) -> PaginaUnidades:
        items, total = self.unidades.pagina(filtros)
        return PaginaUnidades(
            items=[self.resumo(u) for u in items],
            total=total,
            page=filtros.page,
            page_size=filtros.page_size,
        )

    def detalhe(self, id_: uuid.UUID) -> UnidadeDetalhe:
        unidade = self.unidades.obter(id_)
        proprietario = self.proprietarios.da_unidade(id_)
        chave = self.chaves.vigente(id_) if unidade.ativo else None
        return UnidadeDetalhe(
            **self.resumo(unidade).model_dump(),
            proprietario=ProprietarioSaida.model_validate(proprietario) if proprietario else None,
            chave=saida_chave(chave) if chave else None,
            moradores=self.unidades.moradores(id_),
        )

    def consultar_chave(self, id_: uuid.UUID) -> ChaveSaida:
        unidade = self.unidades.obter(id_)
        chave = self.chaves.vigente(id_) if unidade.ativo else None
        if chave is None:
            raise RecursoNaoEncontrado
        return saida_chave(chave)

    def alterar_chave(
        self,
        id_: uuid.UUID,
        responsavel_id: uuid.UUID,
        acao: Literal["gerar", "regenerar", "revogar"],
        *,
        ip: str | None,
        relogio: Relogio = agora,
    ) -> ChaveSaida | RevogacaoSaida:
        try:
            self.responsaveis.obter_ativo(responsavel_id)
            unidade = self.unidades.bloquear(id_)
            if not unidade.ativo:
                raise ApiError(409, "conflict", "Unidade inativa.", reason="unidade_inativa")
            anterior = self.chaves.vigente(id_)
            if acao == "gerar" and anterior is not None:
                raise ApiError(409, "conflict", "Já existe chave vigente.", reason="chave_vigente")
            if acao in {"regenerar", "revogar"} and anterior is None:
                raise ApiError(409, "conflict", "Não há chave vigente.", reason="sem_chave_vigente")
            momento = relogio()
            if anterior is not None:
                anterior.revogada_em = momento
                self.session.flush()
            nova = gerar_chave(self.session, unidade, momento) if acao != "revogar" else None
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao=f"chave.{acao}",
                recurso_tipo="unidade",
                recurso_id=id_,
                responsavel=ResponsavelRef("administracao", responsavel_id),
                antes={"chave_id": str(anterior.id)} if anterior else {},
                depois={"chave_id": str(nova.id)} if nova else {},
            )
            saida = saida_chave(nova) if nova else RevogacaoSaida(revogada_em=momento)
            self.session.commit()
            return saida
        except SQLAlchemyError:
            self.session.rollback()
            raise ApiError(500, "internal_error", "Não foi possível alterar a chave.") from None
        except Exception:
            self.session.rollback()
            raise

    def editar_proprietario(
        self,
        id_: uuid.UUID,
        dados: ProprietarioEntrada,
        *,
        ip: str | None,
    ) -> ProprietarioSaida:
        try:
            self.responsaveis.obter_ativo(dados.responsavel_id)
            self.unidades.bloquear(id_)
            if dados.foto_arquivo_id is not None:
                RepositorioFotos(self.session, self.contexto).conferir(dados.foto_arquivo_id)
            proprietario = self.proprietarios.da_unidade(id_)
            antes = {"cadastrado": proprietario is not None}
            campos = dados.model_dump(exclude={"responsavel_id"})
            if proprietario is None:
                proprietario = self.proprietarios.criar({**campos, "unidade_id": id_})
            else:
                for campo, valor in campos.items():
                    setattr(proprietario, campo, valor)
                self.session.flush()
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="proprietario.editar",
                recurso_tipo="unidade",
                recurso_id=id_,
                responsavel=ResponsavelRef("administracao", dados.responsavel_id),
                antes=antes,
                depois={"cadastrado": True, "documento": dados.documento},
            )
            saida = ProprietarioSaida.model_validate(proprietario)
            self.session.commit()
            return saida
        except Exception:
            self.session.rollback()
            raise
