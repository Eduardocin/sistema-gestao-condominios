import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.tempo import Relogio, inicio_do_slot, no_fuso
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef
from app.modules.auditoria.service import registrar_acao
from app.modules.auth import repository as auth_repository
from app.modules.auth.autorizacao import garantir_aba_da_unidade
from app.modules.funcionarios.repository import RepositorioFuncionarios
from app.modules.visitantes import schemas as s
from app.modules.visitantes.models import Visitante
from app.modules.visitantes.repository import (
    LinhaContato,
    LinhaVisita,
    RepositorioContatos,
    RepositorioVisitantes,
    RepositorioVisitas,
)


def conflito(reason: str, mensagem: str) -> ApiError:
    return ApiError(409, "conflict", mensagem, reason=reason)


def nome_unidade(identificacao: str, bloco: str | None, andar: str | None) -> str:
    return " / ".join(parte for parte in (bloco, andar, identificacao) if parte)


def dados_basicos(item: Visitante) -> dict[str, Any]:
    return {
        "id": item.id,
        "nome": item.nome,
        "unidade_id": item.unidade_id,
        "entrada_prevista": item.entrada_prevista,
        "saida_prevista": item.saida_prevista,
    }


class VisitantesService:
    def __init__(self, session: Session, contexto: ContextoCondominio, relogio: Relogio) -> None:
        self.session = session
        self.ctx = contexto
        self.relogio = relogio
        self.visitantes = RepositorioVisitantes(session, contexto)
        self.visitas = RepositorioVisitas(session, contexto)
        self.contatos = RepositorioContatos(session, contexto)
        self.funcionarios = RepositorioFuncionarios(session, contexto)

    def _auditar(
        self,
        acao: str,
        tipo: str,
        id_: uuid.UUID,
        ip: str | None,
        *,
        funcionario_id: uuid.UUID | None = None,
        antes: dict[str, Any] | None = None,
        depois: dict[str, Any] | None = None,
    ) -> None:
        registrar_acao(
            self.session,
            ctx=ContextoAuditoria.do_condominio(self.ctx, ip=ip),
            acao=acao,
            recurso_tipo=tipo,
            recurso_id=id_,
            antes=antes,
            depois=depois,
            responsavel=ResponsavelRef("funcionario", funcionario_id) if funcionario_id else None,
        )

    def _unidade_ativa(self, id_: uuid.UUID) -> None:
        unidade = auth_repository.obter_unidade(self.session, id_, self.ctx.condominio_id)
        if unidade is None or not unidade.ativo:
            raise RecursoNaoEncontrado

    def _aba(self, unidade_id: uuid.UUID) -> None:
        garantir_aba_da_unidade(self.session, self.ctx, unidade_id, "visitantes")
        self._unidade_ativa(unidade_id)

    def _morador_saida(self, item: Visitante) -> s.VisitanteMorador:
        autor = item.cadastrado_por_usuario_id == self.ctx.usuario_id
        return s.VisitanteMorador(
            **dados_basicos(item),
            idade=item.idade,
            cpf=item.cpf if autor else None,
            observacoes=item.observacoes if autor else None,
            cancelado_em=item.cancelado_em,
        )

    def pagina_morador(
        self,
        unidade: uuid.UUID,
        busca: str | None,
        situacao: s.Situacao | None,
        page: int,
        size: int,
    ) -> s.Pagina[s.VisitanteMorador]:
        self._aba(unidade)
        items, total = self.visitantes.pagina_morador(
            unidade, busca, situacao, no_fuso(self.relogio()).date(), page, size
        )
        return s.Pagina(
            items=[self._morador_saida(item) for item in items],
            total=total,
            page=page,
            page_size=size,
        )

    def _do_morador(self, id_: uuid.UUID, *, alterando: bool = False) -> Visitante:
        item = self.visitantes.bloquear(id_) if alterando else self.visitantes.obter(id_)
        if item.avulso:
            raise RecursoNaoEncontrado
        self._aba(item.unidade_id)
        if alterando and item.cadastrado_por_usuario_id != self.ctx.usuario_id:
            raise ApiError(403, "forbidden", "Somente o autor pode alterar este cadastro.")
        return item

    def detalhe_morador(self, id_: uuid.UUID) -> s.VisitanteMorador:
        return self._morador_saida(self._do_morador(id_))

    def cadastrar(self, dados: s.CadastroVisitante, ip: str | None) -> s.VisitanteMorador:
        self._aba(dados.unidade_id)
        item = self.visitantes.criar(
            {**dados.model_dump(), "cadastrado_por_usuario_id": self.ctx.usuario_id}
        )
        self._auditar(
            "visitante.criar",
            "visitante",
            item.id,
            ip,
            depois={
                "unidade_id": item.unidade_id,
                "entrada_prevista": item.entrada_prevista,
                "saida_prevista": item.saida_prevista,
            },
        )
        saida = self._morador_saida(item)
        self.session.commit()
        return saida

    def editar(
        self, id_: uuid.UUID, dados: s.EdicaoVisitante, ip: str | None
    ) -> s.VisitanteMorador:
        item = self._do_morador(id_, alterando=True)
        if item.cancelado_em is not None:
            raise conflito("visitante_cancelado", "Este cadastro foi cancelado.")
        if self.visitas.tem_visita(id_):
            raise conflito("visitante_ja_utilizado", "Já houve uma entrada com este cadastro.")
        if dados.unidade_id not in (None, item.unidade_id):
            raise ApiError(422, "validation_error", "Não é possível trocar a unidade do cadastro.")
        alteracoes = {
            campo: valor
            for campo, valor in dados.model_dump(exclude={"unidade_id"}).items()
            if getattr(item, campo) != valor
        }
        if alteracoes:
            periodo = {"entrada_prevista", "saida_prevista"}
            antes = {campo: getattr(item, campo) for campo in periodo & alteracoes.keys()}
            for campo, valor in alteracoes.items():
                setattr(item, campo, valor)
            # Auditar os campos alterados, sem registrar CPF, nome ou texto livre.
            self._auditar(
                "visitante.editar",
                "visitante",
                item.id,
                ip,
                antes=antes,
                depois={
                    "campos_alterados": sorted(alteracoes),
                    **{campo: alteracoes[campo] for campo in antes},
                },
            )
        saida = self._morador_saida(item)
        self.session.commit()
        return saida

    def cancelar(self, id_: uuid.UUID, ip: str | None) -> s.VisitanteMorador:
        item = self._do_morador(id_, alterando=True)
        if item.cancelado_em is not None:
            raise conflito("visitante_cancelado", "Este cadastro já foi cancelado.")
        if self.visitas.tem_visita(id_, aberta=True):
            raise conflito("visita_em_andamento", "Registre a saída antes de cancelar o cadastro.")
        item.cancelado_em = self.relogio()
        self._auditar(
            "visitante.cancelar",
            "visitante",
            item.id,
            ip,
            antes={"cancelado_em": None},
            depois={"cancelado_em": item.cancelado_em},
        )
        saida = self._morador_saida(item)
        self.session.commit()
        return saida

    def pagina_portaria(
        self, unidade: uuid.UUID | None, busca: str | None, cpf: str | None, page: int, size: int
    ) -> s.Pagina[s.VisitantePortaria]:
        if unidade is not None:
            self._unidade_ativa(unidade)
        linhas, total = self.visitantes.pagina_portaria(unidade, busca, cpf, page, size)
        return s.Pagina(
            items=[
                s.VisitantePortaria(
                    **dados_basicos(item),
                    unidade=s.Referencia(
                        id=item.unidade_id, nome=nome_unidade(identificacao, bloco, andar)
                    ),
                    ambigua=ambigua,
                )
                for item, identificacao, bloco, andar, ambigua in linhas
            ],
            total=total,
            page=page,
            page_size=size,
        )

    def _destino(
        self, visitante_id: uuid.UUID, unidade_id: uuid.UUID, *, trancar: bool = False
    ) -> Visitante:
        item = (
            self.visitantes.bloquear(visitante_id)
            if trancar
            else self.visitantes.obter(visitante_id)
        )
        if item.unidade_id != unidade_id or item.avulso:
            raise RecursoNaoEncontrado
        self._unidade_ativa(unidade_id)
        return item

    def _autorizacao(self, item: Visitante, momento: datetime) -> s.Autorizacao | None:
        hoje = no_fuso(momento).date()
        if (
            item.cancelado_em is not None
            or not item.entrada_prevista <= hoje <= item.saida_prevista
        ):
            return None
        autor = self.visitantes.morador_ativo(
            item.unidade_id, usuario_id=item.cadastrado_por_usuario_id
        )
        if autor is None or not auth_repository.morador_tem_acesso_a_aba(
            self.session,
            usuario_id=item.cadastrado_por_usuario_id,
            condominio_id=self.ctx.condominio_id,
            unidade_id=item.unidade_id,
            aba="visitantes",
        ):
            return None
        # Cadastros legados podem ter date.max. Não representar um fim inválido.
        fim = (
            inicio_do_slot(item.saida_prevista + timedelta(days=1), time.min)
            if item.saida_prevista < date.max
            else inicio_do_slot(date.max, time.max)
        )
        return s.Autorizacao(
            id=item.id,
            visitante_id=item.id,
            unidade_id=item.unidade_id,
            autorizado_por=s.Referencia(id=autor[0].id, nome=autor[1]),
            inicio=inicio_do_slot(item.entrada_prevista, time.min),
            fim=fim,
        )

    def autorizacoes(self, visitante: uuid.UUID, unidade: uuid.UUID) -> list[s.Autorizacao]:
        item = self._destino(visitante, unidade)
        autorizacao = self._autorizacao(item, self.relogio())
        return [autorizacao] if autorizacao else []

    def _funcionario(self, id_: uuid.UUID) -> None:
        if not self.funcionarios.bloquear(id_).ativo:
            raise RecursoNaoEncontrado

    def _contato(self, unidade: uuid.UUID, morador: uuid.UUID) -> None:
        if self.visitantes.morador_ativo(unidade, vinculo_id=morador) is None:
            raise RecursoNaoEncontrado

    def entrar(self, dados: s.EntradaVisita, ip: str | None) -> s.VisitaSaida:
        item = self._destino(dados.visitante_id, dados.unidade_id, trancar=True)
        self._funcionario(dados.funcionario_id)
        if item.cancelado_em is not None:
            raise conflito("visitante_cancelado", "Este cadastro foi cancelado.")
        if self.visitas.tem_visita(item.id, aberta=True):
            raise conflito(
                "visita_em_andamento", "Já existe uma visita em andamento para este cadastro."
            )
        momento = self.relogio()
        autorizacao = self._autorizacao(item, momento)
        evidencia: dict[str, Any]
        if dados.contato is not None:
            if autorizacao is not None:
                raise conflito("autorizacao_vigente", "O cadastro tem autorização prévia vigente.")
            self._contato(item.unidade_id, dados.contato.morador_id)
            evidencia = {"contato": dados.contato.model_dump(mode="json")}
        else:
            if dados.autorizacao_id != item.id or autorizacao is None:
                raise conflito(
                    "autorizacao_invalida", "Autorização prévia indisponível. Consulte o morador."
                )
            evidencia = {"autorizacao": autorizacao.model_dump(mode="json")}
        try:
            with self.session.begin_nested():
                visita = self.visitas.criar(
                    {
                        "visitante_id": item.id,
                        "entrada_em": momento,
                        "entrada_por_funcionario_id": dados.funcionario_id,
                        "evidencia": evidencia,
                    }
                )
        except IntegrityError as erro:
            if (
                getattr(getattr(erro.orig, "diag", None), "constraint_name", None)
                != "uq_registros_visita_em_aberto"
            ):
                raise
            raise conflito(
                "visita_em_andamento", "Já existe uma visita em andamento para este cadastro."
            ) from erro
        self._auditar(
            "visita.entrar",
            "visita",
            visita.id,
            ip,
            funcionario_id=dados.funcionario_id,
            depois={"visitante_id": item.id, "unidade_id": item.unidade_id, "entrada_em": momento},
        )
        saida = self.detalhe_visita(visita.id)
        self.session.commit()
        return saida

    def sair(self, id_: uuid.UUID, funcionario: uuid.UUID, ip: str | None) -> s.VisitaSaida:
        visita = self.visitas.bloquear(id_)
        self._funcionario(funcionario)
        if visita.saida_em is not None:
            raise conflito("visita_encerrada", "A saída desta visita já foi registrada.")
        momento = self.relogio()
        if momento < visita.entrada_em:
            raise conflito("horario_invalido", "O horário da saída é anterior ao da entrada.")
        visita.saida_em = momento
        visita.saida_por_funcionario_id = funcionario
        self.session.flush()
        self._auditar(
            "visita.sair",
            "visita",
            visita.id,
            ip,
            funcionario_id=funcionario,
            antes={"saida_em": None},
            depois={"saida_em": momento},
        )
        saida = self.detalhe_visita(visita.id)
        self.session.commit()
        return saida

    def registrar_contato(self, dados: s.ContatoSemEntrada, ip: str | None) -> s.ContatoSaida:
        item = self._destino(dados.visitante_id, dados.unidade_id, trancar=True)
        self._funcionario(dados.funcionario_id)
        self._contato(item.unidade_id, dados.morador_id)
        if item.cancelado_em is not None:
            raise conflito("visitante_cancelado", "Este cadastro foi cancelado.")
        contato = self.contatos.criar({**dados.model_dump(), "registrado_em": self.relogio()})
        self._auditar(
            "visita.registrar_contato",
            "contato_portaria",
            contato.id,
            ip,
            funcionario_id=dados.funcionario_id,
            depois=dados.model_dump(),
        )
        saida = self._contato_saida(self.contatos.detalhe(contato.id))
        self.session.commit()
        return saida

    @staticmethod
    def _contato_saida(linha: LinhaContato) -> s.ContatoSaida:
        contato, visitante, unidade, funcionario = linha
        return s.ContatoSaida.model_validate(
            {
                **{campo: getattr(contato, campo) for campo in s.ContatoSemEntrada.model_fields},
                "id": contato.id,
                "registrado_em": contato.registrado_em,
                "visitante": s.Referencia(id=contato.visitante_id, nome=visitante),
                "unidade": s.Referencia(id=contato.unidade_id, nome=unidade),
                "funcionario": s.Referencia(id=contato.funcionario_id, nome=funcionario),
            }
        )

    def pagina_contatos(self, page: int, size: int) -> s.Pagina[s.ContatoSaida]:
        items, total = self.contatos.pagina(page, size)
        return s.Pagina(
            items=[self._contato_saida(linha) for linha in items],
            total=total,
            page=page,
            page_size=size,
        )

    @staticmethod
    def _visita_saida(linha: LinhaVisita) -> s.VisitaSaida:
        item, nome, unidade, identificacao, bloco, andar, entrada, saida = linha
        evidencia = item.evidencia or {}
        autorizacao = (
            s.Autorizacao.model_validate(evidencia["autorizacao"])
            if "autorizacao" in evidencia
            else None
        )
        contato = (
            s.ContatoAutorizado.model_validate(evidencia["contato"])
            if "contato" in evidencia
            else None
        )
        return s.VisitaSaida(
            id=item.id,
            visitante=s.Referencia(id=item.visitante_id, nome=nome),
            unidade=s.Referencia(id=unidade, nome=nome_unidade(identificacao, bloco, andar)),
            status="encerrada" if item.saida_em is not None else "em_andamento",
            entrada=s.Movimentacao(
                em=item.entrada_em,
                funcionario=s.Referencia(id=item.entrada_por_funcionario_id, nome=entrada),
            ),
            saida=s.Movimentacao(
                em=item.saida_em,
                funcionario=s.Referencia(id=item.saida_por_funcionario_id, nome=saida or ""),
            )
            if item.saida_em is not None and item.saida_por_funcionario_id is not None
            else None,
            autorizacao_id=autorizacao.id if autorizacao else None,
            autorizacao=autorizacao,
            contato=contato,
        )

    def detalhe_visita(self, id_: uuid.UUID) -> s.VisitaSaida:
        return self._visita_saida(self.visitas.detalhe(id_))

    def pagina_visitas(
        self, busca: str | None, status: s.StatusVisita | None, page: int, size: int
    ) -> s.Pagina[s.VisitaSaida]:
        items, total = self.visitas.pagina(busca, status, page, size)
        return s.Pagina(
            items=[self._visita_saida(linha) for linha in items],
            total=total,
            page=page,
            page_size=size,
        )
