"""Regras dos chamados de suporte (US-901, US-902): quem vê, quem responde e as transições.

A Administração abre, lista e responde os chamados do próprio condomínio. O ADM da plataforma
atende a fila de todos: a primeira mensagem dele move o chamado para `em_atendimento` (uma única
vez) e só ele encerra. O histórico nunca é alterado; mensagem em chamado encerrado é 409.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria
from app.modules.suporte.models import Chamado
from app.modules.suporte.repository import (
    ChamadoDetalhado,
    Filtros,
    MensagemDetalhada,
    RepositorioChamados,
)
from app.modules.suporte.schemas import (
    AutorDaMensagem,
    ChamadoEntrada,
    ChamadoResumo,
    ChamadoSaida,
    ConsultaDaAdministracao,
    ConsultaDaPlataforma,
    MensagemEntrada,
    MensagemSaida,
    PaginaDeChamados,
    Referencia,
)

MENSAGEM_ANEXO_INVALIDO = "Um ou mais anexos informados não existem neste condomínio."
MENSAGEM_ENCERRADO = "Esse chamado está encerrado. Abra um novo chamado."
MENSAGEM_JA_ENCERRADO = "Esse chamado já foi encerrado."


def _mensagem(item: MensagemDetalhada) -> MensagemSaida:
    return MensagemSaida(
        id=item.mensagem.id,
        autor=AutorDaMensagem(
            tipo="plataforma" if item.autor_e_plataforma else "administracao",
            nome=item.autor_nome,
        ),
        texto=item.mensagem.texto,
        em=item.mensagem.criado_em,
    )


def _resumo(item: ChamadoDetalhado, *, com_condominio: bool) -> ChamadoResumo:
    chamado = item.chamado
    return ChamadoResumo(
        id=chamado.id,
        titulo=chamado.titulo,
        status=chamado.status,
        condominio=Referencia(id=chamado.condominio_id, nome=item.condominio_nome)
        if com_condominio
        else None,
        aberto_por=Referencia(id=chamado.aberto_por_usuario_id, nome=item.aberto_por_nome),
        atendido_por=Referencia(
            id=chamado.atendido_por_usuario_id, nome=item.atendido_por_nome or ""
        )
        if chamado.atendido_por_usuario_id is not None
        else None,
        criado_em=chamado.criado_em,
        encerrado_em=chamado.encerrado_em,
    )


class _Base:
    com_condominio: bool

    def __init__(self, session: Session, repositorio: RepositorioChamados) -> None:
        self.session = session
        self.chamados = repositorio

    def _completo(self, chamado_id: uuid.UUID) -> ChamadoSaida:
        item = self.chamados.obter_detalhado(chamado_id)
        if item is None:
            raise RecursoNaoEncontrado  # inexistente ou de outro condomínio: a mesma resposta
        resumo = _resumo(item, com_condominio=self.com_condominio)
        return ChamadoSaida(
            **resumo.model_dump(),
            descricao=item.chamado.descricao,
            anexos=self.chamados.anexos(item.chamado),
            mensagens=[_mensagem(m) for m in self.chamados.mensagens(item.chamado)],
        )

    def _pagina(
        self, filtros: Filtros, consulta: ConsultaDaAdministracao, *, fila: bool
    ) -> PaginaDeChamados:
        itens, total = self.chamados.pagina(
            filtros,
            fila=fila,
            limite=consulta.page_size,
            deslocamento=(consulta.page - 1) * consulta.page_size,
        )
        return PaginaDeChamados(
            items=[_resumo(i, com_condominio=self.com_condominio) for i in itens],
            page=consulta.page,
            page_size=consulta.page_size,
            total=total,
        )

    def _travar_aberto(self, chamado_id: uuid.UUID) -> Chamado:
        chamado = self.chamados.bloquear(chamado_id)
        if chamado is None:
            raise RecursoNaoEncontrado
        if chamado.status == "encerrado":
            raise ApiError(409, "conflict", MENSAGEM_ENCERRADO, reason="chamado_encerrado")
        return chamado


class ChamadosDaAdministracao(_Base):
    com_condominio = False

    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        super().__init__(session, RepositorioChamados(session, contexto.condominio_id))
        self.contexto = contexto

    def abrir(self, dados: ChamadoEntrada) -> ChamadoSaida:
        self._conferir_anexos(dados.anexos)
        chamado = self.chamados.criar(
            condominio_id=self.contexto.condominio_id,
            usuario_id=self.contexto.usuario_id,
            titulo=dados.titulo,
            descricao=dados.descricao,
        )
        for arquivo_id in dados.anexos:
            self.chamados.anexar(chamado, arquivo_id)
        self.session.commit()
        return self._completo(chamado.id)

    def listar(self, consulta: ConsultaDaAdministracao) -> PaginaDeChamados:
        return self._pagina(Filtros(status=consulta.status), consulta, fila=False)

    def obter(self, chamado_id: uuid.UUID) -> ChamadoSaida:
        return self._completo(chamado_id)

    def responder(self, chamado_id: uuid.UUID, dados: MensagemEntrada) -> MensagemSaida:
        chamado = self._travar_aberto(chamado_id)
        mensagem = self.chamados.adicionar_mensagem(
            chamado, autor_usuario_id=self.contexto.usuario_id, texto=dados.texto
        )
        self.session.commit()
        return _mensagem(
            MensagemDetalhada(mensagem, self._nome_do_autor(), autor_e_plataforma=False)
        )

    def _nome_do_autor(self) -> str:
        return self.chamados.nome_do_usuario(self.contexto.usuario_id)

    def _conferir_anexos(self, anexos: list[uuid.UUID]) -> None:
        """O storage já validou tipo e tamanho; aqui conferimos o vínculo com este condomínio."""
        prefixo = f"condominio/{self.contexto.condominio_id}/suporte/"
        for arquivo_id in anexos:
            arquivo = self.chamados.arquivo(arquivo_id)
            if (
                arquivo is None
                or arquivo.enviado_por_usuario_id != self.contexto.usuario_id
                or not arquivo.chave_storage.startswith(prefixo)
            ):
                raise ApiError(422, "validation_error", MENSAGEM_ANEXO_INVALIDO)


class ChamadosDaPlataforma(_Base):
    com_condominio = True

    def __init__(
        self, session: Session, contexto: ContextoPlataforma, *, ip: str | None = None
    ) -> None:
        super().__init__(session, RepositorioChamados(session, None))
        self.contexto = contexto
        self.ip = ip

    def listar(self, consulta: ConsultaDaPlataforma) -> PaginaDeChamados:
        filtros = Filtros(
            status=consulta.status,
            condominio_id=consulta.condominio_id,
            de=consulta.de,
            ate=consulta.ate,
            busca=consulta.busca or None,
        )
        return self._pagina(filtros, consulta, fila=True)

    def obter(self, chamado_id: uuid.UUID) -> ChamadoSaida:
        return self._completo(chamado_id)

    def responder(self, chamado_id: uuid.UUID, dados: MensagemEntrada) -> MensagemSaida:
        chamado = self._travar_aberto(chamado_id)
        primeira_resposta = chamado.status == "aberto"
        mensagem = self.chamados.adicionar_mensagem(
            chamado, autor_usuario_id=self.contexto.usuario_id, texto=dados.texto
        )
        if primeira_resposta:  # a linha está travada: só uma resposta vê `aberto`
            self.chamados.marcar_em_atendimento(chamado, self.contexto.usuario_id)
            self._auditar(chamado, "chamado.atender", {"status": "aberto"}, "em_atendimento")
        self.session.commit()
        return _mensagem(
            MensagemDetalhada(
                mensagem, self.chamados.nome_do_usuario(self.contexto.usuario_id), True
            )
        )

    def encerrar(self, chamado_id: uuid.UUID) -> ChamadoSaida:
        chamado = self.chamados.bloquear(chamado_id)
        if chamado is None:
            raise RecursoNaoEncontrado
        if chamado.status == "encerrado":
            raise ApiError(409, "conflict", MENSAGEM_JA_ENCERRADO, reason="chamado_ja_encerrado")
        anterior = chamado.status
        self.chamados.encerrar(chamado, self.contexto.usuario_id)
        self._auditar(chamado, "chamado.encerrar", {"status": anterior}, "encerrado")
        self.session.commit()
        return self._completo(chamado_id)

    def _auditar(self, chamado: Chamado, acao: str, antes: dict[str, str], depois: str) -> None:
        auditoria.registrar_acao(
            self.session,
            ctx=ContextoAuditoria(
                self.contexto.usuario_id, chamado.condominio_id, "plataforma", self.ip
            ),
            acao=acao,
            recurso_tipo="chamado",
            recurso_id=chamado.id,
            antes=antes,
            depois={"status": depois},
        )
