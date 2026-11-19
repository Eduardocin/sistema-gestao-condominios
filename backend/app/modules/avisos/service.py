import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.core.permissoes import Perfil
from app.core.tempo import Relogio, agora
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO, garantir_acesso_a_unidade
from app.modules.avisos.models import Aviso
from app.modules.avisos.repository import AvisoDetalhado, RepositorioAvisos
from app.modules.avisos.schemas import (
    AvisoEntrada,
    AvisoSaida,
    PaginaDeAvisos,
    ResponsavelSaida,
    SituacaoAviso,
    SituacaoFiltro,
    UnidadeSaida,
)
from app.modules.funcionarios.repository import RepositorioResponsaveis


def situacao_do_aviso(aviso: Aviso, momento: datetime) -> SituacaoAviso:
    if aviso.encerrado_em is not None:
        return "encerrado"
    if aviso.fim_em <= momento:
        return "expirado"
    if aviso.inicio_em > momento:
        return "agendado"
    return "vigente"


class AvisosService:
    def __init__(
        self, session: Session, contexto: ContextoCondominio, relogio: Relogio = agora
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.relogio = relogio
        self.avisos = RepositorioAvisos(session, contexto)
        self.responsaveis = RepositorioResponsaveis(session, contexto)

    def listar(
        self, *, situacao: SituacaoFiltro = "vigentes", page: int = 1, page_size: int = 20
    ) -> PaginaDeAvisos:
        momento = self.relogio()
        itens, total = self.avisos.pagina(
            momento=momento, situacao=situacao, page=page, page_size=page_size
        )
        return PaginaDeAvisos(
            items=[self._apresentar(item, momento) for item in itens],
            page=page,
            page_size=page_size,
            total=total,
        )

    def obter(self, aviso_id: uuid.UUID) -> AvisoSaida:
        momento = self.relogio()
        return self._apresentar(self.avisos.obter_detalhado(aviso_id, momento), momento)

    def _administracao(self) -> None:
        # Também protege a interface interna; contexto sempre vem da autenticação central.
        if self.contexto.perfil != Perfil.ADMINISTRACAO:
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)

    def _publicar(
        self, dados: AvisoEntrada, *, unidade_id: uuid.UUID | None = None, ip: str | None
    ) -> Aviso:
        self._administracao()
        self.responsaveis.obter_ativo(dados.responsavel_id)
        if unidade_id is not None:
            garantir_acesso_a_unidade(self.session, self.contexto, unidade_id)
        aviso = self.avisos.criar({**dados.model_dump(), "unidade_id": unidade_id})
        self._auditar(
            "aviso.publicar",
            aviso,
            dados.responsavel_id,
            ip=ip,
            antes={},
            depois={**dados.model_dump(), "unidade_id": unidade_id},
        )
        return aviso

    def publicar(self, dados: AvisoEntrada, *, ip: str | None) -> AvisoSaida:
        aviso = self._publicar(dados, ip=ip)
        self.session.commit()
        return self.obter(aviso.id)

    def _editavel(self, aviso_id: uuid.UUID) -> Aviso:
        self._administracao()
        aviso = self.avisos.bloquear(aviso_id)
        if aviso.encerrado_em is not None or aviso.fim_em <= self.relogio():
            raise ApiError(409, "conflict", "O aviso já foi encerrado.", reason="aviso_encerrado")
        return aviso

    def editar(self, aviso_id: uuid.UUID, dados: AvisoEntrada, *, ip: str | None) -> AvisoSaida:
        aviso = self._editavel(aviso_id)
        if aviso.unidade_id is not None:
            raise ApiError(
                409,
                "conflict",
                "O aviso automático não pode ser editado.",
                reason="aviso_automatico",
            )
        self.responsaveis.obter_ativo(dados.responsavel_id)
        # O responsável recebido identifica a edição; o autor da publicação é preservado.
        valores = dados.model_dump(exclude={"responsavel_id"})
        antes = {
            campo: getattr(aviso, campo)
            for campo in valores
            if getattr(aviso, campo) != valores[campo]
        }
        depois = {campo: valores[campo] for campo in antes}
        aviso = self.avisos.atualizar(aviso.id, valores)
        self._auditar(
            "aviso.editar", aviso, dados.responsavel_id, ip=ip, antes=antes, depois=depois
        )
        self.session.commit()
        return self.obter(aviso.id)

    def encerrar(
        self, aviso_id: uuid.UUID, responsavel_id: uuid.UUID, *, ip: str | None
    ) -> AvisoSaida:
        aviso = self._editavel(aviso_id)
        self.responsaveis.obter_ativo(responsavel_id)
        aviso = self.avisos.atualizar(aviso.id, {"encerrado_em": self.relogio()})
        self._auditar(
            "aviso.encerrar",
            aviso,
            responsavel_id,
            ip=ip,
            antes={"encerrado_em": None},
            depois={"encerrado_em": aviso.encerrado_em},
        )
        self.session.commit()
        return self.obter(aviso.id)

    def _auditar(
        self,
        acao: str,
        aviso: Aviso,
        responsavel_id: uuid.UUID,
        *,
        ip: str | None,
        antes: dict[str, Any],
        depois: dict[str, Any],
    ) -> None:
        auditoria.registrar_acao(
            self.session,
            ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
            acao=acao,
            recurso_tipo="aviso",
            recurso_id=aviso.id,
            responsavel=ResponsavelRef("administracao", responsavel_id),
            antes=antes,
            depois=depois,
        )

    def _apresentar(self, item: AvisoDetalhado, momento: datetime) -> AvisoSaida:
        aviso = item.aviso
        campos: dict[str, Any] = {}
        if self.contexto.perfil == Perfil.ADMINISTRACAO:
            campos["publicado_por"] = (
                ResponsavelSaida(id=aviso.responsavel_id, nome=item.responsavel_nome or "")
                if aviso.responsavel_id is not None
                else None
            )
        return AvisoSaida(
            id=aviso.id,
            titulo=aviso.titulo,
            texto=aviso.texto,
            importante=aviso.importante,
            inicio_em=aviso.inicio_em,
            fim_em=aviso.fim_em,
            encerrado_em=aviso.encerrado_em,
            situacao=situacao_do_aviso(aviso, momento),
            unidade=(
                UnidadeSaida(id=aviso.unidade_id, identificacao=item.unidade_identificacao or "")
                if aviso.unidade_id is not None
                else None
            ),
            **campos,
        )


def publicar_para_unidade(
    session: Session,
    *,
    ctx: ContextoCondominio,
    unidade_id: uuid.UUID,
    titulo: str,
    texto: str,
    responsavel_id: uuid.UUID,
    importante: bool = True,
    dias_de_exibicao: int = 7,
    ip: str | None = None,
    relogio: Relogio = agora,
) -> uuid.UUID:
    """Publica e audita sem commit: a transação pertence ao fluxo chamador."""
    if (
        isinstance(dias_de_exibicao, bool)
        or not isinstance(dias_de_exibicao, int)
        or dias_de_exibicao < 1
    ):
        raise ValueError("dias_de_exibicao precisa ser um inteiro positivo.")
    momento = relogio()
    dados = AvisoEntrada(
        titulo=titulo,
        texto=texto,
        importante=importante,
        inicio_em=momento,
        fim_em=momento + timedelta(days=dias_de_exibicao),
        responsavel_id=responsavel_id,
    )
    return AvisosService(session, ctx, relogio)._publicar(dados, unidade_id=unidade_id, ip=ip).id
