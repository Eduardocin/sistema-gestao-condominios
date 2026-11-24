import uuid
from datetime import date

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import aliased

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.condominios.models import VinculoCondominio
from app.modules.funcionarios.models import Funcionario
from app.modules.unidades.models import Andar, Bloco, MoradorUnidade, Unidade
from app.modules.usuarios.models import Usuario
from app.modules.visitantes.models import ContatoPortaria, RegistroVisita, Visitante
from app.modules.visitantes.schemas import Situacao, StatusVisita

LinhaVisitante = tuple[Visitante, str, str | None, str | None, bool]
LinhaVisita = tuple[RegistroVisita, str, uuid.UUID, str, str | None, str | None, str, str | None]
LinhaContato = tuple[ContatoPortaria, str, str, str]


class RepositorioVisitantes(RepositorioDoCondominio[Visitante]):
    modelo = Visitante

    def bloquear(self, id_: uuid.UUID) -> Visitante:
        item = self.session.scalar(
            self.consulta()
            .where(Visitante.id == id_)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def pagina_morador(
        self,
        unidade_id: uuid.UUID,
        busca: str | None,
        situacao: Situacao | None,
        hoje: date,
        page: int,
        size: int,
    ) -> tuple[list[Visitante], int]:
        consulta = self.consulta().where(
            Visitante.unidade_id == unidade_id, Visitante.avulso.is_(False)
        )
        if busca:
            digitos = "".join(ch for ch in busca if ch.isdigit())
            criterio = Visitante.nome.icontains(busca, autoescape=True)
            if digitos:
                criterio = or_(criterio, Visitante.cpf.icontains(digitos, autoescape=True))
            consulta = consulta.where(criterio)
        if situacao == "cancelados":
            consulta = consulta.where(Visitante.cancelado_em.is_not(None))
        elif situacao is not None:
            consulta = consulta.where(Visitante.cancelado_em.is_(None))
            if situacao == "vigentes":
                consulta = consulta.where(
                    Visitante.entrada_prevista <= hoje, Visitante.saida_prevista >= hoje
                )
            elif situacao == "futuros":
                consulta = consulta.where(Visitante.entrada_prevista > hoje)
            else:
                consulta = consulta.where(Visitante.saida_prevista < hoje)
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        linhas = self.session.scalars(
            consulta.order_by(Visitante.criado_em.desc(), Visitante.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(linhas), total

    def pagina_portaria(
        self,
        unidade_id: uuid.UUID | None,
        busca: str | None,
        cpf: str | None,
        page: int,
        size: int,
    ) -> tuple[list[LinhaVisitante], int]:
        consulta = (
            self.consulta()
            .add_columns(
                Unidade.identificacao,
                Bloco.nome,
                Andar.nome,
                func.count().over(
                    partition_by=(
                        Visitante.unidade_id,
                        func.lower(Visitante.nome),
                        Visitante.entrada_prevista,
                        Visitante.saida_prevista,
                    )
                )
                > 1,
            )
            .join(
                Unidade,
                and_(
                    Unidade.id == Visitante.unidade_id,
                    Unidade.condominio_id == Visitante.condominio_id,
                ),
            )
            .outerjoin(
                Andar,
                and_(Andar.id == Unidade.andar_id, Andar.condominio_id == Unidade.condominio_id),
            )
            .outerjoin(
                Bloco, and_(Bloco.id == Andar.bloco_id, Bloco.condominio_id == Andar.condominio_id)
            )
            .where(
                Unidade.ativo.is_(True),
                Visitante.avulso.is_(False),
                Visitante.cancelado_em.is_(None),
            )
        )
        if unidade_id is not None:
            consulta = consulta.where(Visitante.unidade_id == unidade_id)
        if busca:
            consulta = consulta.where(Visitante.nome.icontains(busca, autoescape=True))
        if cpf:
            consulta = consulta.where(Visitante.cpf == cpf)
        return self._pagina_linhas(consulta, page, size)

    def _pagina_linhas(
        self, consulta: Select[LinhaVisitante], page: int, size: int
    ) -> tuple[list[LinhaVisitante], int]:
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        linhas = self.session.execute(
            consulta.order_by(Visitante.nome, Visitante.entrada_prevista, Visitante.id)
            .offset((page - 1) * size)
            .limit(size)
        ).tuples()
        return list(linhas), total

    def morador_ativo(
        self,
        unidade_id: uuid.UUID,
        *,
        vinculo_id: uuid.UUID | None = None,
        usuario_id: uuid.UUID | None = None,
    ) -> tuple[MoradorUnidade, str] | None:
        consulta = (
            select(MoradorUnidade, Usuario.nome)
            .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
            .join(
                VinculoCondominio,
                and_(
                    VinculoCondominio.usuario_id == MoradorUnidade.usuario_id,
                    VinculoCondominio.condominio_id == MoradorUnidade.condominio_id,
                ),
            )
            .where(
                MoradorUnidade.condominio_id == self.contexto.condominio_id,
                MoradorUnidade.unidade_id == unidade_id,
                MoradorUnidade.status == "ativo",
                VinculoCondominio.perfil == "morador",
                VinculoCondominio.ativo.is_(True),
                Usuario.ativo.is_(True),
            )
        )
        if vinculo_id is not None:
            consulta = consulta.where(MoradorUnidade.id == vinculo_id)
        if usuario_id is not None:
            consulta = consulta.where(MoradorUnidade.usuario_id == usuario_id)
        return self.session.execute(consulta).tuples().one_or_none()


class RepositorioVisitas(RepositorioDoCondominio[RegistroVisita]):
    modelo = RegistroVisita

    def tem_visita(self, visitante_id: uuid.UUID, *, aberta: bool = False) -> bool:
        consulta = self.consulta().where(RegistroVisita.visitante_id == visitante_id)
        if aberta:
            consulta = consulta.where(RegistroVisita.saida_em.is_(None))
        return bool(self.session.scalar(select(consulta.exists())))

    def bloquear(self, id_: uuid.UUID) -> RegistroVisita:
        item = self.session.scalar(
            self.consulta()
            .where(RegistroVisita.id == id_)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def detalhada(self) -> Select[LinhaVisita]:
        entrada, saida = aliased(Funcionario), aliased(Funcionario)
        return (
            self.consulta()
            .add_columns(
                Visitante.nome,
                Unidade.id,
                Unidade.identificacao,
                Bloco.nome,
                Andar.nome,
                entrada.nome,
                saida.nome,
            )
            .join(
                Visitante,
                and_(
                    Visitante.id == RegistroVisita.visitante_id,
                    Visitante.condominio_id == RegistroVisita.condominio_id,
                ),
            )
            .join(
                Unidade,
                and_(
                    Unidade.id == Visitante.unidade_id,
                    Unidade.condominio_id == Visitante.condominio_id,
                ),
            )
            .outerjoin(
                Andar,
                and_(Andar.id == Unidade.andar_id, Andar.condominio_id == Unidade.condominio_id),
            )
            .outerjoin(
                Bloco, and_(Bloco.id == Andar.bloco_id, Bloco.condominio_id == Andar.condominio_id)
            )
            .join(
                entrada,
                and_(
                    entrada.id == RegistroVisita.entrada_por_funcionario_id,
                    entrada.condominio_id == RegistroVisita.condominio_id,
                ),
            )
            .outerjoin(
                saida,
                and_(
                    saida.id == RegistroVisita.saida_por_funcionario_id,
                    saida.condominio_id == RegistroVisita.condominio_id,
                ),
            )
        )

    def detalhe(self, id_: uuid.UUID) -> LinhaVisita:
        linha = (
            self.session.execute(self.detalhada().where(RegistroVisita.id == id_))
            .tuples()
            .one_or_none()
        )
        if linha is None:
            raise RecursoNaoEncontrado
        return linha

    def pagina(
        self, busca: str | None, status: StatusVisita | None, page: int, size: int
    ) -> tuple[list[LinhaVisita], int]:
        consulta = self.detalhada()
        if busca:
            consulta = consulta.where(
                or_(
                    Visitante.nome.icontains(busca, autoescape=True),
                    Unidade.identificacao.icontains(busca, autoescape=True),
                    Bloco.nome.icontains(busca, autoescape=True),
                )
            )
        if status == "em_andamento":
            consulta = consulta.where(RegistroVisita.saida_em.is_(None))
        elif status == "encerrada":
            consulta = consulta.where(RegistroVisita.saida_em.is_not(None))
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        linhas = self.session.execute(
            consulta.order_by(RegistroVisita.entrada_em.desc(), RegistroVisita.id)
            .offset((page - 1) * size)
            .limit(size)
        ).tuples()
        return list(linhas), total


class RepositorioContatos(RepositorioDoCondominio[ContatoPortaria]):
    modelo = ContatoPortaria

    def detalhada(self) -> Select[LinhaContato]:
        return (
            self.consulta()
            .add_columns(Visitante.nome, Unidade.identificacao, Funcionario.nome)
            .join(
                Visitante,
                and_(
                    Visitante.id == ContatoPortaria.visitante_id,
                    Visitante.condominio_id == ContatoPortaria.condominio_id,
                ),
            )
            .join(
                Unidade,
                and_(
                    Unidade.id == ContatoPortaria.unidade_id,
                    Unidade.condominio_id == ContatoPortaria.condominio_id,
                ),
            )
            .join(
                Funcionario,
                and_(
                    Funcionario.id == ContatoPortaria.funcionario_id,
                    Funcionario.condominio_id == ContatoPortaria.condominio_id,
                ),
            )
        )

    def detalhe(self, id_: uuid.UUID) -> LinhaContato:
        return (
            self.session.execute(self.detalhada().where(ContatoPortaria.id == id_)).tuples().one()
        )

    def pagina(self, page: int, size: int) -> tuple[list[LinhaContato], int]:
        total = (
            self.session.scalar(select(func.count()).select_from(self.consulta().subquery())) or 0
        )
        linhas = self.session.execute(
            self.detalhada()
            .order_by(ContatoPortaria.registrado_em.desc(), ContatoPortaria.id)
            .offset((page - 1) * size)
            .limit(size)
        ).tuples()
        return list(linhas), total
