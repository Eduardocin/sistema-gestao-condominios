import logging
from typing import BinaryIO
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO
from app.modules.encomendas import repository
from app.modules.encomendas.models import Encomenda
from app.modules.encomendas.repository import LinhaEncomenda
from app.modules.encomendas.schemas import (
    ConfirmacaoSaida,
    EncomendaEntrada,
    EncomendaSaida,
    EntregaSaida,
    MoradorOpcao,
    MoradorResumo,
    PaginaEncomendas,
    PaginaMoradores,
    PaginaUnidades,
    RecebimentoSaida,
    StatusEncomenda,
    UnidadeOpcao,
    UnidadeResumo,
)
from app.modules.notificacoes.models import EnvioEmail
from app.modules.storage.models import Arquivo
from app.modules.storage.policy import autorizar_upload, conferir_unidade
from app.modules.storage.service import StorageService
from app.modules.storage.types import (
    Action,
    AuthorizationPolicy,
    FileMetadata,
    Module,
    StorageAdapter,
    StorageContext,
    StorageNotFound,
)

logger = logging.getLogger(__name__)


class EncomendasService:
    def __init__(
        self,
        session: Session,
        contexto: ContextoCondominio,
        storage_adapter: StorageAdapter | None = None,
    ):
        self.session = session
        self.contexto = contexto
        self.storage_adapter = storage_adapter

    def registrar(
        self,
        dados: EncomendaEntrada,
        foto: BinaryIO,
        nome_foto: str,
        tipo_mime: str,
        *,
        ip: str | None,
    ) -> Encomenda:
        if self.contexto.perfil != "funcionario":
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        if self.storage_adapter is None:
            raise RuntimeError("O recebimento de encomendas precisa de um adaptador de storage.")

        uploaded_file: FileMetadata | None = None
        storage: StorageService | None = None
        storage_context = StorageContext(self.contexto.condominio_id, self.contexto.usuario_id)

        class PoliticaStorageRecebimento(AuthorizationPolicy):
            arquivo_criado_id: UUID | None = None

            def __call__(
                politica,
                ctx: StorageContext,
                modulo: Module,
                acao: Action,
                arquivo: FileMetadata | None,
            ) -> None:
                if acao == "remove":
                    # A compensação só pode apagar o objeto recém-criado nesta chamada.
                    if arquivo is None or arquivo.id != politica.arquivo_criado_id:
                        raise StorageNotFound("Arquivo indisponível.")
                    return
                autorizar_upload(self.session, self.contexto, modulo, None)

        politica_storage = PoliticaStorageRecebimento()

        try:
            referencias = repository.obter_referencias_recebimento(
                self.session,
                self.contexto.condominio_id,
                unidade_id=dados.unidade_id,
                destinatario_morador_unidade_id=dados.destinatario_morador_unidade_id,
                recebido_por_funcionario_id=dados.recebido_por_funcionario_id,
            )
            if referencias is None:
                raise RecursoNaoEncontrado

            storage = StorageService(
                self.storage_adapter,
                authorize=politica_storage,
                url_seconds=get_settings().storage_url_seconds,
            )
            uploaded_file = storage.upload(
                storage_context, "encomendas", nome_foto, tipo_mime, foto
            )
            politica_storage.arquivo_criado_id = uploaded_file.id
            arquivo = Arquivo(
                id=uploaded_file.id,
                condominio_id=self.contexto.condominio_id,
                chave_storage=uploaded_file.chave_storage,
                nome_original=uploaded_file.nome_original,
                tipo_mime=uploaded_file.tipo_mime,
                tamanho_bytes=uploaded_file.tamanho_bytes,
                enviado_por_usuario_id=self.contexto.usuario_id,
                criado_em=uploaded_file.criado_em,
            )
            encomenda = Encomenda(
                condominio_id=self.contexto.condominio_id,
                unidade_id=dados.unidade_id,
                destinatario_morador_unidade_id=dados.destinatario_morador_unidade_id,
                descricao=dados.descricao,
                foto_nota_arquivo_id=uploaded_file.id,
                recebido_por_funcionario_id=dados.recebido_por_funcionario_id,
            )
            self.session.add(arquivo)
            self.session.flush()
            self.session.add(encomenda)
            self.session.flush()
            self.session.add_all(
                (
                    RegistroAuditoria(
                        condominio_id=self.contexto.condominio_id,
                        usuario_id=self.contexto.usuario_id,
                        responsavel_nome=referencias.funcionario.nome,
                        perfil=self.contexto.perfil,
                        acao="encomenda.receber",
                        recurso_tipo="encomenda",
                        recurso_id=encomenda.id,
                        antes=None,
                        depois={
                            "unidade_id": str(encomenda.unidade_id),
                            "destinatario_morador_unidade_id": str(
                                encomenda.destinatario_morador_unidade_id
                            ),
                            "descricao": encomenda.descricao,
                            "foto_arquivo_id": str(encomenda.foto_nota_arquivo_id),
                            "status": encomenda.status,
                        },
                        ip=ip,
                    ),
                    EnvioEmail(
                        condominio_id=self.contexto.condominio_id,
                        destinatario=referencias.destinatario_email,
                        evento="encomenda_registrada",
                        recurso_tipo="encomenda",
                        recurso_id=encomenda.id,
                    ),
                )
            )
            self.session.commit()
            return encomenda
        except Exception:
            try:
                self.session.rollback()
            except Exception:
                logger.error(
                    "Falha no rollback de recebimento: arquivo_id=%s",
                    uploaded_file.id if uploaded_file is not None else "indisponivel",
                )
            if uploaded_file is not None and storage is not None:
                try:
                    storage.remove(storage_context, uploaded_file)
                except Exception:
                    logger.error(
                        "Falha na compensação do recebimento: arquivo_id=%s", uploaded_file.id
                    )
            raise

    def listar(
        self,
        *,
        busca: str | None,
        status: StatusEncomenda | None,
        page: int,
        page_size: int,
    ) -> PaginaEncomendas:
        linhas, total = repository.listar(
            self.session,
            self.contexto,
            busca=busca,
            status=status.value if status is not None else None,
            page=page,
            page_size=page_size,
        )
        return PaginaEncomendas(
            items=[self._saida(linha) for linha in linhas],
            page=page,
            page_size=page_size,
            total=total,
        )

    def obter(self, id_: UUID) -> EncomendaSaida:
        encomenda = repository.obter(self.session, self.contexto.condominio_id, id_)
        if encomenda is None:
            raise RecursoNaoEncontrado
        if self.contexto.perfil == "morador":
            conferir_unidade(self.session, self.contexto, encomenda.unidade_id, "encomendas")
        linha = repository.obter_linha(self.session, self.contexto, id_)
        if linha is None:
            raise RecursoNaoEncontrado
        return self._saida(linha)

    def listar_unidades(self, *, busca: str | None, page: int, page_size: int) -> PaginaUnidades:
        self._exigir_funcionario()
        unidades, total = repository.listar_unidades(
            self.session,
            self.contexto.condominio_id,
            busca=busca,
            page=page,
            page_size=page_size,
        )
        return PaginaUnidades(
            items=[
                UnidadeOpcao(id=unidade.id, identificacao=unidade.identificacao)
                for unidade in unidades
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    def listar_moradores(self, unidade_id: UUID, *, page: int, page_size: int) -> PaginaMoradores:
        self._exigir_funcionario()
        unidade = repository.obter_unidade_ativa(
            self.session, self.contexto.condominio_id, unidade_id
        )
        if unidade is None:
            raise RecursoNaoEncontrado
        linhas, total = repository.listar_moradores(
            self.session,
            self.contexto.condominio_id,
            unidade.id,
            page=page,
            page_size=page_size,
        )
        return PaginaMoradores(
            items=[MoradorOpcao(id=morador.id, nome=nome) for morador, nome in linhas],
            page=page,
            page_size=page_size,
            total=total,
        )

    def _exigir_funcionario(self) -> None:
        if self.contexto.perfil != "funcionario":
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)

    @staticmethod
    def _saida(linha: LinhaEncomenda) -> EncomendaSaida:
        encomenda = linha.encomenda
        entrega = None
        if (
            encomenda.entregue_em is not None
            and linha.entrega_funcionario_id is not None
            and linha.entrega_funcionario_nome is not None
            and linha.recebedor_id is not None
            and linha.recebedor_nome is not None
        ):
            entrega = EntregaSaida(
                em=encomenda.entregue_em,
                funcionario_id=linha.entrega_funcionario_id,
                funcionario_nome=linha.entrega_funcionario_nome,
                recebedor_id=linha.recebedor_id,
                recebedor_nome=linha.recebedor_nome,
            )

        confirmacao = None
        if (
            encomenda.confirmada_em is not None
            and linha.confirmacao_morador_id is not None
            and linha.confirmacao_morador_nome is not None
        ):
            confirmacao = ConfirmacaoSaida(
                em=encomenda.confirmada_em,
                morador_id=linha.confirmacao_morador_id,
                morador_nome=linha.confirmacao_morador_nome,
            )

        return EncomendaSaida(
            id=encomenda.id,
            unidade=UnidadeResumo(id=linha.unidade_id, identificacao=linha.unidade_identificacao),
            destinatario=MoradorResumo(id=linha.destinatario_id, nome=linha.destinatario_nome),
            descricao=encomenda.descricao,
            foto_arquivo_id=encomenda.foto_nota_arquivo_id,
            status=StatusEncomenda(encomenda.status),
            recebimento=RecebimentoSaida(
                em=encomenda.registrada_em,
                funcionario_id=linha.recebimento_funcionario_id,
                funcionario_nome=linha.recebimento_funcionario_nome,
            ),
            entrega=entrega,
            confirmacao=confirmacao,
            pode_confirmar=False,
        )
