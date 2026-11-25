"""Envio e consulta de comunicados (US-804).

O ADM cria um comunicado e ele vai, de uma vez, para todos os condomínios `ativo` naquele instante.
A lista de destinatários é gravada no envio: o condomínio criado depois não vê comunicados
antigos, e a Administração só enxerga o que foi enviado ao seu condomínio.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.core.errors import RecursoNaoEncontrado
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria
from app.modules.comunicados import repository
from app.modules.comunicados.repository import ComunicadoDetalhado
from app.modules.comunicados.schemas import (
    ComunicadoComDestinatarios,
    ComunicadoDaAdministracao,
    ComunicadoEntrada,
    ComunicadoSaida,
    ConsultaDeComunicados,
    PaginaDeComunicados,
    PaginaDeComunicadosDaAdministracao,
    Referencia,
)


def _saida(item: ComunicadoDetalhado) -> ComunicadoSaida:
    comunicado = item.comunicado
    return ComunicadoSaida(
        id=comunicado.id,
        titulo=comunicado.titulo,
        texto=comunicado.texto,
        criado_em=comunicado.criado_em,
        enviado_por=Referencia(id=comunicado.enviado_por_usuario_id, nome=item.enviado_por_nome),
        total_destinatarios=item.total_destinatarios,
    )


class ComunicadosDaPlataforma:
    def __init__(
        self, session: Session, contexto: ContextoPlataforma, *, ip: str | None = None
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.ip = ip

    def enviar(self, dados: ComunicadoEntrada) -> ComunicadoSaida:
        destinatarios = repository.ids_dos_condominios_ativos(self.session)
        comunicado = repository.criar(
            self.session,
            titulo=dados.titulo,
            texto=dados.texto,
            enviado_por=self.contexto.usuario_id,
            destinatarios=destinatarios,
        )
        auditoria.registrar_acao(
            self.session,
            ctx=ContextoAuditoria(self.contexto.usuario_id, None, "plataforma", self.ip),
            acao="comunicado.enviar",
            recurso_tipo="comunicado",
            recurso_id=comunicado.id,
            antes={},
            depois={"titulo": dados.titulo, "total_destinatarios": len(destinatarios)},
        )
        self.session.commit()
        return self._detalhado(comunicado.id)

    def _detalhado(self, comunicado_id: uuid.UUID) -> ComunicadoSaida:
        item = repository.detalhado(self.session, comunicado_id)
        if item is None:
            raise RecursoNaoEncontrado
        return _saida(item)

    def listar(self, consulta: ConsultaDeComunicados) -> PaginaDeComunicados:
        itens, total = repository.pagina(
            self.session,
            limite=consulta.page_size,
            deslocamento=(consulta.page - 1) * consulta.page_size,
        )
        return PaginaDeComunicados(
            items=[_saida(i) for i in itens],
            page=consulta.page,
            page_size=consulta.page_size,
            total=total,
        )

    def obter(self, comunicado_id: uuid.UUID) -> ComunicadoComDestinatarios:
        base = self._detalhado(comunicado_id)
        return ComunicadoComDestinatarios(
            **base.model_dump(),
            destinatarios=[
                Referencia(id=i, nome=nome)
                for i, nome in repository.destinatarios(self.session, comunicado_id)
            ],
        )


class ComunicadosDaAdministracao:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto

    def listar(self, consulta: ConsultaDeComunicados) -> PaginaDeComunicadosDaAdministracao:
        itens, total = repository.pagina_do_condominio(
            self.session,
            self.contexto.condominio_id,
            limite=consulta.page_size,
            deslocamento=(consulta.page - 1) * consulta.page_size,
        )
        return PaginaDeComunicadosDaAdministracao(
            items=[
                ComunicadoDaAdministracao(
                    id=c.id, titulo=c.titulo, texto=c.texto, criado_em=c.criado_em
                )
                for c in itens
            ],
            page=consulta.page,
            page_size=consulta.page_size,
            total=total,
        )
