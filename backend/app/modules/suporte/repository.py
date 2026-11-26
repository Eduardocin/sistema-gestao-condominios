"""Consultas dos chamados. Só aqui se fala com o banco.

Os mesmos chamados são lidos por duas partes: a Administração (só o próprio condomínio) e o ADM
da plataforma (todos). Em vez de duas classes, o repositório recebe `condominio_id`: **obrigatório
para a Administração** (todo filtro, junção e escrita o carrega) e `None` só para o ADM. O service
da Administração sempre passa `contexto.condominio_id`; nunca vem do cliente.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.modules.condominios.models import Condominio
from app.modules.storage.models import Arquivo
from app.modules.suporte.models import Chamado, ChamadoAnexo, ChamadoMensagem
from app.modules.usuarios.models import Usuario

ABERTOS = ("aberto", "em_atendimento")


@dataclass(frozen=True)
class Filtros:
    status: str | None = None
    condominio_id: uuid.UUID | None = None  # só o ADM filtra por condomínio
    de: date | None = None
    ate: date | None = None
    busca: str | None = None


@dataclass(frozen=True)
class ChamadoDetalhado:
    chamado: Chamado
    condominio_nome: str
    aberto_por_nome: str
    atendido_por_nome: str | None


@dataclass(frozen=True)
class MensagemDetalhada:
    mensagem: ChamadoMensagem
    autor_nome: str
    autor_e_plataforma: bool


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class RepositorioChamados:
    def __init__(self, session: Session, condominio_id: uuid.UUID | None) -> None:
        self.session = session
        self.condominio_id = condominio_id  # None = escopo de plataforma (ADM)

    # --- consultas --------------------------------------------------------------------------

    def _escopo(self) -> Select[tuple[Chamado]]:
        consulta = select(Chamado)
        if self.condominio_id is not None:
            consulta = consulta.where(Chamado.condominio_id == self.condominio_id)
        return consulta

    def _detalhado(self) -> Select[Any]:
        atendente = Usuario.__table__.alias("atendente")
        return (
            self._escopo()
            .add_columns(Condominio.nome, Usuario.nome, atendente.c.nome)
            .join(Condominio, Condominio.id == Chamado.condominio_id)
            .join(Usuario, Usuario.id == Chamado.aberto_por_usuario_id)
            .outerjoin(atendente, atendente.c.id == Chamado.atendido_por_usuario_id)
        )

    @staticmethod
    def _montar(linha: Any) -> ChamadoDetalhado:
        chamado, condominio, aberto_por, atendido_por = linha
        return ChamadoDetalhado(chamado, condominio, aberto_por, atendido_por)

    def obter_detalhado(self, chamado_id: uuid.UUID) -> ChamadoDetalhado | None:
        linha = self.session.execute(self._detalhado().where(Chamado.id == chamado_id)).first()
        return None if linha is None else self._montar(linha)

    def bloquear(self, chamado_id: uuid.UUID) -> Chamado | None:
        """Trava a linha até o commit: a primeira resposta do ADM e o encerramento não correm
        juntos, e `em_atendimento` é marcado uma única vez."""
        return self.session.scalar(self._escopo().where(Chamado.id == chamado_id).with_for_update())

    def _filtrados(self, filtros: Filtros) -> Select[Any]:
        consulta = self._detalhado()
        if filtros.status is not None:
            consulta = consulta.where(Chamado.status == filtros.status)
        if filtros.condominio_id is not None:
            consulta = consulta.where(Chamado.condominio_id == filtros.condominio_id)
        if filtros.de is not None:
            consulta = consulta.where(
                Chamado.criado_em >= datetime.combine(filtros.de, time.min, tzinfo=UTC)
            )
        if filtros.ate is not None:
            fim = datetime.combine(filtros.ate + timedelta(days=1), time.min, tzinfo=UTC)
            consulta = consulta.where(Chamado.criado_em < fim)
        if filtros.busca:
            padrao = f"%{_escapar_like(filtros.busca)}%"
            consulta = consulta.where(
                or_(
                    Chamado.titulo.ilike(padrao, escape="\\"),
                    Chamado.descricao.ilike(padrao, escape="\\"),
                )
            )
        return consulta

    def pagina(
        self, filtros: Filtros, *, fila: bool, limite: int, deslocamento: int
    ) -> tuple[list[ChamadoDetalhado], int]:
        """`fila=True` (ADM): sem `status`, só os não encerrados, do mais antigo ao mais novo
        (quem espera há mais tempo primeiro); `encerrado`, do mais recente ao mais antigo."""
        consulta = self._filtrados(filtros)
        if fila and filtros.status is None:
            consulta = consulta.where(Chamado.status.in_(ABERTOS))
        antigos_primeiro = fila and filtros.status != "encerrado"
        ordem = Chamado.criado_em.asc() if antigos_primeiro else Chamado.criado_em.desc()
        itens = [
            self._montar(linha)
            for linha in self.session.execute(
                consulta.order_by(ordem, Chamado.id).limit(limite).offset(deslocamento)
            )
        ]
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        return itens, total

    def mensagens(self, chamado: Chamado) -> list[MensagemDetalhada]:
        consulta = (
            select(ChamadoMensagem, Usuario.nome, Usuario.administrador_plataforma)
            .join(Usuario, Usuario.id == ChamadoMensagem.autor_usuario_id)
            .where(
                ChamadoMensagem.chamado_id == chamado.id,
                ChamadoMensagem.condominio_id == chamado.condominio_id,
            )
            .order_by(ChamadoMensagem.criado_em, ChamadoMensagem.id)
        )
        return [
            MensagemDetalhada(m, nome, bool(adm)) for m, nome, adm in self.session.execute(consulta)
        ]

    def anexos(self, chamado: Chamado) -> list[uuid.UUID]:
        return list(
            self.session.scalars(
                select(ChamadoAnexo.arquivo_id)
                .where(
                    ChamadoAnexo.chamado_id == chamado.id,
                    ChamadoAnexo.condominio_id == chamado.condominio_id,
                )
                .order_by(ChamadoAnexo.arquivo_id)
            )
        )

    def nome_do_usuario(self, usuario_id: uuid.UUID) -> str:
        return self.session.scalar(select(Usuario.nome).where(Usuario.id == usuario_id)) or ""

    def arquivo(self, arquivo_id: uuid.UUID) -> Arquivo | None:
        """O arquivo do condomínio da Administração, ou None (outro prédio não conta)."""
        if self.condominio_id is None:
            raise ValueError("Só a Administração anexa arquivos a um chamado.")
        return self.session.scalar(
            select(Arquivo).where(
                Arquivo.id == arquivo_id, Arquivo.condominio_id == self.condominio_id
            )
        )

    # --- escrita (sem commit: quem comita é o service) ---------------------------------------

    def criar(
        self, *, condominio_id: uuid.UUID, usuario_id: uuid.UUID, titulo: str, descricao: str
    ) -> Chamado:
        chamado = Chamado(
            condominio_id=condominio_id,
            titulo=titulo,
            descricao=descricao,
            aberto_por_usuario_id=usuario_id,
        )
        self.session.add(chamado)
        self.session.flush()
        self.session.refresh(chamado)
        return chamado

    def anexar(self, chamado: Chamado, arquivo_id: uuid.UUID) -> None:
        self.session.add(
            ChamadoAnexo(
                chamado_id=chamado.id,
                arquivo_id=arquivo_id,
                condominio_id=chamado.condominio_id,
            )
        )

    def adicionar_mensagem(
        self, chamado: Chamado, *, autor_usuario_id: uuid.UUID, texto: str
    ) -> ChamadoMensagem:
        mensagem = ChamadoMensagem(
            condominio_id=chamado.condominio_id,
            chamado_id=chamado.id,
            autor_usuario_id=autor_usuario_id,
            texto=texto,
        )
        self.session.add(mensagem)
        self.session.flush()
        self.session.refresh(mensagem)
        return mensagem

    def marcar_em_atendimento(self, chamado: Chamado, adm_usuario_id: uuid.UUID) -> None:
        chamado.status = "em_atendimento"
        chamado.atendido_por_usuario_id = adm_usuario_id
        self.session.flush()

    def encerrar(self, chamado: Chamado, adm_usuario_id: uuid.UUID) -> None:
        chamado.status = "encerrado"
        chamado.encerrado_em = func.now()
        if chamado.atendido_por_usuario_id is None:  # a constraint exige um ADM no atendimento
            chamado.atendido_por_usuario_id = adm_usuario_id
        self.session.flush()
        self.session.refresh(chamado)


__all__ = ["ABERTOS", "ChamadoDetalhado", "Filtros", "MensagemDetalhada", "RepositorioChamados"]
