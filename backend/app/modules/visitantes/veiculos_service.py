import uuid
from typing import Any, NoReturn

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.permissoes import Perfil
from app.core.tempo import Relogio
from app.modules.auditoria.schemas import ContextoAuditoria
from app.modules.auditoria.service import registrar_acao
from app.modules.auth.autorizacao import garantir_aba_da_unidade
from app.modules.auth.repository import obter_unidade
from app.modules.visitantes.schemas import Pagina, Referencia
from app.modules.visitantes.service import conflito, nome_unidade
from app.modules.visitantes.veiculos_repository import Linha, RepositorioVeiculos
from app.modules.visitantes.veiculos_schemas import CadastroVeiculo, EdicaoVeiculo, VeiculoSaida

LIMITE_VEICULOS = 5


def placa_repetida() -> ApiError:
    return conflito(
        "placa_ja_cadastrada_na_unidade", "Já existe um veículo ativo com essa placa na unidade."
    )


class VeiculosService:
    def __init__(self, session: Session, ctx: ContextoCondominio, relogio: Relogio) -> None:
        self.session = session
        self.ctx = ctx
        self.relogio = relogio
        self.repo = RepositorioVeiculos(session, ctx)

    def _unidade(self, id_: uuid.UUID, *, escrita: bool = False) -> None:
        if escrita and self.ctx.perfil != Perfil.MORADOR:
            raise ApiError(403, "forbidden", "Somente moradores podem alterar veículos.")
        if self.ctx.perfil == Perfil.MORADOR:
            garantir_aba_da_unidade(self.session, self.ctx, id_, "veiculos")
        unidade = obter_unidade(self.session, id_, self.ctx.condominio_id, bloquear=escrita)
        if unidade is None or not unidade.ativo:
            raise RecursoNaoEncontrado

    def _saida(self, linha: Linha) -> VeiculoSaida:
        veiculo, identificacao, bloco, andar, duplicada = linha
        return VeiculoSaida(
            id=veiculo.id,
            unidade_id=veiculo.unidade_id,
            unidade=Referencia(
                id=veiculo.unidade_id, nome=nome_unidade(identificacao, bloco, andar)
            ),
            placa=veiculo.placa,
            marca=veiculo.marca,
            modelo=veiculo.modelo,
            cor=veiculo.cor,
            ativo=veiculo.ativo,
            placa_duplicada=duplicada if self.ctx.perfil == Perfil.ADMINISTRACAO else None,
        )

    def _auditar(
        self,
        acao: str,
        id_: uuid.UUID,
        ip: str | None,
        depois: dict[str, Any],
        antes: dict[str, Any] | None = None,
    ) -> None:
        registrar_acao(
            self.session,
            ctx=ContextoAuditoria.do_condominio(self.ctx, ip=ip),
            acao=acao,
            recurso_tipo="veiculo",
            recurso_id=id_,
            antes=antes,
            depois=depois,
        )

    @staticmethod
    def _duplicidade(erro: IntegrityError) -> NoReturn:
        if (
            getattr(getattr(erro.orig, "diag", None), "constraint_name", None)
            == "uq_veiculos_unidade_placa_ativo"
        ):
            raise placa_repetida() from erro
        raise erro

    def pagina(
        self, unidade: uuid.UUID | None, busca: str | None, page: int, size: int
    ) -> Pagina[VeiculoSaida]:
        if unidade is None and self.ctx.perfil == Perfil.MORADOR:
            raise ApiError(422, "validation_error", "Informe a unidade.")
        if unidade is not None:
            self._unidade(unidade)
        items, total = self.repo.pagina(unidade, busca, page, size)
        return Pagina(
            items=[self._saida(linha) for linha in items], total=total, page=page, page_size=size
        )

    def detalhe(self, id_: uuid.UUID) -> VeiculoSaida:
        linha = self.repo.detalhe(id_)
        self._unidade(linha[0].unidade_id)
        return self._saida(linha)

    def cadastrar(self, dados: CadastroVeiculo, ip: str | None) -> VeiculoSaida:
        self._unidade(dados.unidade_id, escrita=True)
        if self.repo.quantidade_ativa(dados.unidade_id) >= LIMITE_VEICULOS:
            if self.repo.placa_ativa(dados.unidade_id, dados.placa):
                raise placa_repetida()
            raise conflito(
                "limite_veiculos", f"A unidade já tem {LIMITE_VEICULOS} veículos ativos."
            )
        try:
            with self.session.begin_nested():
                item = self.repo.criar(dados.model_dump())
        except IntegrityError as erro:
            self._duplicidade(erro)
        self._auditar("veiculo.criar", item.id, ip, {"unidade_id": item.unidade_id})
        saida = self._saida(self.repo.detalhe(item.id))
        self.session.commit()
        return saida

    def _para_alterar(self, id_: uuid.UUID) -> Linha:
        item = self.repo.obter(id_)
        self._unidade(item.unidade_id, escrita=True)
        return self.repo.detalhe(id_)

    def editar(self, id_: uuid.UUID, dados: EdicaoVeiculo, ip: str | None) -> VeiculoSaida:
        linha = self._para_alterar(id_)
        item = linha[0]
        if dados.unidade_id not in (None, item.unidade_id):
            raise ApiError(422, "validation_error", "Não é possível trocar a unidade do veículo.")
        alteracoes = {
            campo: valor
            for campo, valor in dados.model_dump(exclude={"unidade_id"}).items()
            if getattr(item, campo) != valor
        }
        if alteracoes:
            try:
                with self.session.begin_nested():
                    self.repo.atualizar(id_, alteracoes)
            except IntegrityError as erro:
                self._duplicidade(erro)
            self._auditar("veiculo.editar", id_, ip, {"campos_alterados": sorted(alteracoes)})
        saida = self._saida(self.repo.detalhe(id_))
        self.session.commit()
        return saida

    def remover(self, id_: uuid.UUID, ip: str | None) -> VeiculoSaida:
        item = self.repo.obter(id_)
        self._unidade(item.unidade_id, escrita=True)
        if not self.repo.detalhe(id_, somente_ativos=False)[0].ativo:
            raise conflito("veiculo_removido", "O veículo já foi removido.")
        self.repo.atualizar(id_, {"ativo": False, "removido_em": self.relogio()})
        self._auditar("veiculo.remover", id_, ip, {"ativo": False}, {"ativo": True})
        saida = self._saida(self.repo.detalhe(id_, somente_ativos=False))
        self.session.commit()
        return saida
