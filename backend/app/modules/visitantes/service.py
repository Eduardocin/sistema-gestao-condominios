"""Regras dos visitantes cadastrados pelo Morador (convivencia.md, §6.2).

Quem chama já passou por `require_permission` e pela checagem de perfil: ver o router. Aqui ficam
o passo 4 (unidade e aba do Morador), as regras de edição e cancelamento e o commit.
"""

import uuid
from datetime import date

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.permissoes import Perfil
from app.core.tempo import Relogio, no_fuso
from app.modules.auth.autorizacao import garantir_aba_da_unidade
from app.modules.visitantes.models import Veiculo, Visitante
from app.modules.visitantes.repository import (
    FiltrosVeiculos,
    FiltrosVisitantes,
    RepositorioVeiculos,
    RepositorioVisitantes,
    VeiculoDetalhado,
    VisitanteDetalhado,
)
from app.modules.visitantes.schemas import (
    PaginaDeVeiculos,
    PaginaDeVisitantes,
    UnidadeResumo,
    VeiculoAtualizacao,
    VeiculoEntrada,
    VeiculoSaida,
    VisitanteAtualizacao,
    VisitanteEntrada,
    VisitanteSaida,
)

ABA_VISITANTES = "visitantes"
ABA_VEICULOS = "veiculos"
INDICE_PLACA_NA_UNIDADE = "uq_veiculos_unidade_placa_ativo"
MENSAGEM_PLACA_REPETIDA = "Já existe um veículo ativo com esta placa nesta unidade."
MENSAGEM_VEICULO_REMOVIDO = "O veículo foi removido."
MENSAGEM_UNIDADE_OBRIGATORIA = "Informe a unidade."
MENSAGEM_JA_UTILIZADO = "O visitante já teve uma visita registrada e não pode mais ser editado."
MENSAGEM_CANCELADO = "O cadastro do visitante está cancelado."
MENSAGEM_VISITA_EM_ANDAMENTO = "O visitante está no condomínio. Cancele depois da saída."
MENSAGEM_TROCA_DE_UNIDADE = "A unidade não pode ser trocada."


class VisitantesService:
    def __init__(self, session: Session, contexto: ContextoCondominio, relogio: Relogio) -> None:
        self.session = session
        self.contexto = contexto
        self.relogio = relogio
        self.visitantes = RepositorioVisitantes(session, contexto)

    def _unidade(self, unidade_id: uuid.UUID) -> None:
        # Passo 4: 404 se a unidade não é do Morador, depois 403 se a aba estiver Sem Acesso.
        garantir_aba_da_unidade(self.session, self.contexto, unidade_id, ABA_VISITANTES)

    def _hoje(self) -> date:
        return no_fuso(self.relogio()).date()

    def _detalhado_autorizado(self, visitante_id: uuid.UUID) -> VisitanteDetalhado:
        detalhado = self.visitantes.obter_detalhado(visitante_id)
        if detalhado is None:
            raise RecursoNaoEncontrado
        # Cadastro de outra unidade: 404. Da própria unidade sem a aba: 403.
        self._unidade(detalhado.visitante.unidade_id)
        return detalhado

    # --- cadastro -------------------------------------------------------------------------

    def criar(self, dados: VisitanteEntrada) -> VisitanteSaida:
        self._unidade(dados.unidade_id)
        visitante = self.visitantes.criar(
            {
                **dados.model_dump(),
                "cadastrado_por_usuario_id": self.contexto.usuario_id,
                "avulso": False,
            }
        )
        visitante_id = visitante.id
        self.session.commit()
        return self.obter(visitante_id)

    def atualizar(self, visitante_id: uuid.UUID, dados: VisitanteAtualizacao) -> VisitanteSaida:
        atual = self._detalhado_autorizado(visitante_id).visitante
        if dados.unidade_id is not None and dados.unidade_id != atual.unidade_id:
            raise ApiError(422, "validation_error", MENSAGEM_TROCA_DE_UNIDADE)

        visitante = self._travar(visitante_id)
        if visitante.cancelado_em is not None:
            raise ApiError(409, "conflict", MENSAGEM_CANCELADO, reason="visitante_cancelado")
        if self.visitantes.tem_visita(visitante_id):
            raise ApiError(409, "conflict", MENSAGEM_JA_UTILIZADO, reason="visitante_ja_utilizado")

        self.visitantes.atualizar(visitante_id, dados.model_dump(exclude={"unidade_id"}))
        self.session.commit()
        return self.obter(visitante_id)

    def cancelar(self, visitante_id: uuid.UUID) -> VisitanteSaida:
        self._detalhado_autorizado(visitante_id)
        visitante = self._travar(visitante_id)
        if visitante.cancelado_em is not None:
            raise ApiError(409, "conflict", MENSAGEM_CANCELADO, reason="visitante_ja_cancelado")
        if self.visitantes.tem_visita_em_andamento(visitante_id):
            raise ApiError(
                409, "conflict", MENSAGEM_VISITA_EM_ANDAMENTO, reason="visita_em_andamento"
            )

        self.visitantes.atualizar(visitante_id, {"cancelado_em": func.now()})
        self.session.commit()
        return self.obter(visitante_id)

    def _travar(self, visitante_id: uuid.UUID) -> Visitante:
        visitante = self.visitantes.bloquear(visitante_id)
        if visitante is None:
            raise RecursoNaoEncontrado
        return visitante

    # --- consulta -------------------------------------------------------------------------

    def listar(
        self,
        *,
        unidade_id: uuid.UUID,
        busca: str | None,
        situacao: str | None,
        page: int,
        page_size: int,
    ) -> PaginaDeVisitantes:
        self._unidade(unidade_id)
        filtros = FiltrosVisitantes(
            unidade_id=unidade_id,
            busca=(busca or "").strip() or None,
            situacao=situacao,
            hoje=self._hoje(),
        )
        itens, total = self.visitantes.pagina(
            filtros, limite=page_size, deslocamento=(page - 1) * page_size
        )
        return PaginaDeVisitantes(
            items=[self._apresentar(item) for item in itens],
            page=page,
            page_size=page_size,
            total=total,
        )

    def obter(self, visitante_id: uuid.UUID) -> VisitanteSaida:
        return self._apresentar(self._detalhado_autorizado(visitante_id))

    # --- apresentação ---------------------------------------------------------------------

    def _apresentar(self, detalhado: VisitanteDetalhado) -> VisitanteSaida:
        visitante = detalhado.visitante
        hoje = self._hoje()
        if visitante.cancelado_em is not None:
            situacao = "cancelado"
        elif visitante.saida_prevista < hoje:
            situacao = "encerrado"
        elif visitante.entrada_prevista > hoje:
            situacao = "futuro"
        else:
            situacao = "vigente"
        return VisitanteSaida(
            id=visitante.id,
            unidade=UnidadeResumo(
                id=visitante.unidade_id, identificacao=detalhado.unidade_identificacao
            ),
            nome=visitante.nome,
            cpf=visitante.cpf,
            idade=visitante.idade,
            observacoes=visitante.observacoes,
            entrada_prevista=visitante.entrada_prevista,
            saida_prevista=visitante.saida_prevista,
            avulso=visitante.avulso,
            situacao=situacao,
            ja_utilizado=detalhado.ja_utilizado,
            criado_em=visitante.criado_em,
            cancelado_em=visitante.cancelado_em,
        )


class VeiculosService:
    """Veículos da unidade (US-502). O Morador cadastra; Funcionário e Administração consultam."""

    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.veiculos = RepositorioVeiculos(session, contexto)

    def _unidade(self, unidade_id: uuid.UUID) -> None:
        # Passo 4: 404 se a unidade não é de quem pede, depois 403 se o Morador estiver Sem Acesso.
        garantir_aba_da_unidade(self.session, self.contexto, unidade_id, ABA_VEICULOS)

    def _detalhado_autorizado(self, veiculo_id: uuid.UUID) -> VeiculoDetalhado:
        detalhado = self.veiculos.obter_detalhado(veiculo_id)
        if detalhado is None:
            raise RecursoNaoEncontrado
        # Veículo de outra unidade: 404. Da própria unidade sem a aba: 403. Funcionário e
        # Administração enxergam o condomínio inteiro (o repository já filtra por ele).
        self._unidade(detalhado.veiculo.unidade_id)
        return detalhado

    def _travar(self, veiculo_id: uuid.UUID) -> Veiculo:
        veiculo = self.veiculos.bloquear(veiculo_id)
        if veiculo is None:
            raise RecursoNaoEncontrado
        return veiculo

    @staticmethod
    def _placa_repetida(erro: IntegrityError) -> bool:
        diag = getattr(erro.orig, "diag", None)
        return getattr(diag, "constraint_name", None) == INDICE_PLACA_NA_UNIDADE

    def _conflito_de_placa(self, erro: IntegrityError) -> ApiError:
        if not self._placa_repetida(erro):
            raise erro
        return ApiError(
            409, "conflict", MENSAGEM_PLACA_REPETIDA, reason="placa_ja_cadastrada_na_unidade"
        )

    # --- cadastro -------------------------------------------------------------------------

    def criar(self, dados: VeiculoEntrada) -> VeiculoSaida:
        self._unidade(dados.unidade_id)
        # Placa igual em outra unidade é aceita e não é revelada ao Morador (regra 14). Na mesma
        # unidade vale o índice único parcial: a corrida entre dois cadastros também cai aqui.
        try:
            with self.session.begin_nested():
                veiculo = self.veiculos.criar(dados.model_dump())
        except IntegrityError as erro:
            raise self._conflito_de_placa(erro) from erro
        veiculo_id = veiculo.id
        self.session.commit()
        return self.obter(veiculo_id)

    def atualizar(self, veiculo_id: uuid.UUID, dados: VeiculoAtualizacao) -> VeiculoSaida:
        atual = self._detalhado_autorizado(veiculo_id).veiculo
        if dados.unidade_id is not None and dados.unidade_id != atual.unidade_id:
            raise ApiError(422, "validation_error", MENSAGEM_TROCA_DE_UNIDADE)

        veiculo = self._travar(veiculo_id)
        if not veiculo.ativo:
            raise ApiError(409, "conflict", MENSAGEM_VEICULO_REMOVIDO, reason="veiculo_removido")
        try:
            with self.session.begin_nested():
                self.veiculos.atualizar(veiculo_id, dados.model_dump(exclude={"unidade_id"}))
        except IntegrityError as erro:
            raise self._conflito_de_placa(erro) from erro
        self.session.commit()
        return self.obter(veiculo_id)

    def remover(self, veiculo_id: uuid.UUID) -> VeiculoSaida:
        """Desativa o veículo (`ativo = false`); a linha nunca é apagada. A placa pode voltar."""
        self._detalhado_autorizado(veiculo_id)
        veiculo = self._travar(veiculo_id)
        if not veiculo.ativo:
            raise ApiError(409, "conflict", MENSAGEM_VEICULO_REMOVIDO, reason="veiculo_ja_removido")
        self.veiculos.atualizar(veiculo_id, {"ativo": False, "removido_em": func.now()})
        self.session.commit()
        return self.obter(veiculo_id)

    # --- consulta -------------------------------------------------------------------------

    def listar(
        self, *, unidade_id: uuid.UUID | None, busca: str | None, page: int, page_size: int
    ) -> PaginaDeVeiculos:
        if self.contexto.perfil == Perfil.MORADOR and unidade_id is None:
            raise ApiError(422, "validation_error", MENSAGEM_UNIDADE_OBRIGATORIA)
        if unidade_id is not None:
            self._unidade(unidade_id)
        filtros = FiltrosVeiculos(unidade_id=unidade_id, busca=(busca or "").strip() or None)
        itens, total = self.veiculos.pagina(
            filtros, limite=page_size, deslocamento=(page - 1) * page_size
        )
        return PaginaDeVeiculos(
            items=[self._apresentar(item) for item in itens],
            page=page,
            page_size=page_size,
            total=total,
        )

    def obter(self, veiculo_id: uuid.UUID) -> VeiculoSaida:
        return self._apresentar(self._detalhado_autorizado(veiculo_id))

    @staticmethod
    def _apresentar(detalhado: VeiculoDetalhado) -> VeiculoSaida:
        veiculo = detalhado.veiculo
        return VeiculoSaida(
            id=veiculo.id,
            unidade=UnidadeResumo(
                id=veiculo.unidade_id, identificacao=detalhado.unidade_identificacao
            ),
            placa=veiculo.placa,
            marca=veiculo.marca,
            modelo=veiculo.modelo,
            cor=veiculo.cor,
            ativo=veiculo.ativo,
            criado_em=veiculo.criado_em,
            removido_em=veiculo.removido_em,
        )
