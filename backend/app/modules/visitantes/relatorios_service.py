from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.tempo import inicio_do_slot
from app.modules.auth.autorizacao import garantir_acesso_a_unidade
from app.modules.visitantes import relatorios_schemas as s
from app.modules.visitantes.relatorios_repository import (
    LinhaVisitaRelatorio,
    RepositorioRelatorioVeiculos,
    RepositorioRelatorioVisitas,
)
from app.modules.visitantes.schemas import Movimentacao, Pagina, Referencia


class RelatoriosService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.ctx = contexto
        self.visitas = RepositorioRelatorioVisitas(session, contexto)
        self.veiculos = RepositorioRelatorioVeiculos(session, contexto)

    def _limites(self, filtros: s.FiltrosRelatorio) -> tuple[datetime | None, datetime | None]:
        if filtros.unidade_id is not None:
            # Histórico admite unidades inativas; a validação central confere o condomínio.
            garantir_acesso_a_unidade(self.session, self.ctx, filtros.unidade_id)
        inicio = inicio_do_slot(filtros.de, time.min) if filtros.de is not None else None
        fim = (
            inicio_do_slot(filtros.ate + timedelta(days=1), time.min)
            if filtros.ate is not None
            else None
        )
        return inicio, fim

    @staticmethod
    def _visita(linha: LinhaVisitaRelatorio) -> s.VisitaRelatorio:
        item, nome, unidade, identificacao, bloco, andar, entrada, saida, avulso = linha
        return s.VisitaRelatorio(
            id=item.id,
            visitante=Referencia(id=item.visitante_id, nome=nome),
            unidade=s.UnidadeRelatorio(
                id=unidade, identificacao=identificacao, bloco=bloco, andar=andar
            ),
            avulso=avulso,
            status="em_andamento" if item.saida_em is None else "encerrada",
            entrada=Movimentacao(
                em=item.entrada_em,
                funcionario=Referencia(id=item.entrada_por_funcionario_id, nome=entrada),
            ),
            saida=(
                Movimentacao(
                    em=item.saida_em,
                    funcionario=Referencia(id=item.saida_por_funcionario_id, nome=saida),
                )
                if item.saida_em is not None
                and item.saida_por_funcionario_id is not None
                and saida is not None
                else None
            ),
        )

    def visitantes(self, filtros: s.FiltrosRelatorio) -> Pagina[s.VisitaRelatorio]:
        inicio, fim = self._limites(filtros)
        linhas, total = self.visitas.pagina_relatorio(
            filtros.unidade_id, inicio, fim, filtros.page, filtros.page_size
        )
        return Pagina(
            items=[self._visita(linha) for linha in linhas],
            total=total,
            page=filtros.page,
            page_size=filtros.page_size,
        )

    def veiculos_cadastrados(self, filtros: s.FiltrosRelatorio) -> Pagina[s.VeiculoRelatorio]:
        inicio, fim = self._limites(filtros)
        linhas, total = self.veiculos.pagina_relatorio(
            filtros.unidade_id, inicio, fim, filtros.page, filtros.page_size
        )
        return Pagina(
            items=[
                s.VeiculoRelatorio(
                    id=item.id,
                    unidade=s.UnidadeRelatorio(
                        id=item.unidade_id, identificacao=identificacao, bloco=bloco, andar=andar
                    ),
                    placa=item.placa,
                    marca=item.marca,
                    modelo=item.modelo,
                    cor=item.cor,
                    ativo=item.ativo,
                    criado_em=item.criado_em,
                    removido_em=item.removido_em,
                    placa_duplicada=duplicada,
                )
                for item, identificacao, bloco, andar, duplicada in linhas
            ],
            total=total,
            page=filtros.page,
            page_size=filtros.page_size,
        )
