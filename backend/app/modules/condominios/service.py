import uuid
from typing import Literal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.core.errors import ApiError
from app.core.tempo import Relogio, agora
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef
from app.modules.condominios import repository, schemas
from app.modules.condominios.models import Condominio
from app.modules.condominios.schemas import (
    CadastroCondominio,
    CadastroCondominioSaida,
    CondominioResumo,
)
from app.modules.funcionarios.repository import RepositorioFotos, RepositorioResponsaveis
from app.modules.permissoes_aba.repository import RepositorioMoradores
from app.modules.unidades.models import Andar, Bloco, Unidade
from app.modules.unidades.repository import RepositorioChaves, RepositorioUnidades
from app.modules.unidades.service import gerar_chave
from app.modules.usuarios.models import Usuario


def exigir_administracao(usuario: Usuario) -> None:
    # Tipo da conta no banco; não depende do perfil/cid declarado no token.
    if usuario.tipo_cadastro != "administracao" or usuario.administrador_plataforma:
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")


def cadastrar(
    session: Session,
    usuario: Usuario,
    dados: CadastroCondominio,
    *,
    ip: str | None,
    relogio: Relogio = agora,
) -> CadastroCondominioSaida:
    exigir_administracao(usuario)
    if dados.logo_arquivo_id is not None or dados.documentos:
        # Upload atual exige condomínio existente. Não reaproveitar arquivos de outro
        # condomínio nem alterar seu escopo para contornar o bootstrap.
        raise ApiError(
            422,
            "validation_error",
            "Logo e documentos dependem de upload para o cadastro inicial.",
            reason="arquivos_indisponiveis_no_cadastro",
        )
    momento = relogio()
    try:
        condominio = repository.criar_condominio(
            session, dados, usuario_id=usuario.id, momento=momento
        )
        estrutura = repository.criar_estrutura(
            session, condominio_id=condominio.id, dados=dados.blocos
        )
        repository.vincular_criador(session, condominio_id=condominio.id, usuario_id=usuario.id)
        repository.registrar_envio(
            session, condominio_id=condominio.id, usuario_id=usuario.id, momento=momento
        )
        auditoria.registrar_acao(
            session,
            # Cadastro global autenticado, sem um papel local previamente selecionado.
            # A lista de responsáveis desse condomínio ainda não existe.
            ctx=ContextoAuditoria(usuario_id=usuario.id, condominio_id=condominio.id, ip=ip),
            acao="condominio.enviar",
            recurso_tipo="condominio",
            recurso_id=condominio.id,
            antes={},
            depois={"status": "pendente", "estrutura": estrutura.model_dump()},
        )
        saida = CadastroCondominioSaida(
            id=condominio.id,
            nome=condominio.nome,
            cnpj=dados.cnpj,
            status="pendente",
            enviado_em=momento,
            estrutura=estrutura,
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        if (
            getattr(getattr(erro.orig, "diag", None), "constraint_name", None)
            == "uq_condominios_cnpj"
        ):
            raise ApiError(
                409,
                "conflict",
                "Já existe um condomínio com este CNPJ.",
                reason="cnpj_ja_cadastrado",
            ) from erro
        raise
    except Exception:
        session.rollback()
        raise
    return saida


def listar_meus(session: Session, usuario: Usuario) -> list[CondominioResumo]:
    exigir_administracao(usuario)
    return [
        CondominioResumo(id=item.id, nome=item.nome, status=item.status)
        for item in repository.listar_da_administracao(session, usuario.id)
    ]


def dados_condominio(session: Session, condominio: Condominio) -> schemas.CondominioSaida:
    return schemas.CondominioSaida(
        id=condominio.id,
        nome=condominio.nome,
        cnpj=condominio.cnpj,
        status=condominio.status,
        endereco=schemas.EnderecoSaida.model_validate(condominio),
        logo_arquivo_id=condominio.logo_arquivo_id,
        aprovado_em=condominio.aprovado_em,
        motivo_rejeicao=condominio.motivo_rejeicao if condominio.status == "rejeitado" else None,
        analises=[
            schemas.AnaliseSaida(evento=a.evento, motivo=a.motivo, em=a.criado_em)
            for a in repository.historico(session, condominio.id)
        ],
    )


def item_fila(session: Session, condominio: Condominio) -> schemas.ItemFila:
    administracao = repository.administracao_do_cadastro(session, condominio)
    blocos, andares, unidades = repository.estrutura_da_analise(session, condominio.id)
    return schemas.ItemFila(
        id=condominio.id,
        nome=condominio.nome,
        cnpj=condominio.cnpj,
        status=condominio.status,
        enviado_em=condominio.enviado_em,
        administracao=schemas.AdministracaoSaida.model_validate(administracao)
        if administracao
        else None,
        documentos=[
            schemas.DocumentoSaida(arquivo_id=a.id, nome_original=a.nome_original)
            for a in repository.documentos_da_analise(session, condominio.id)
        ],
        estrutura=schemas.ContagemEstrutura(
            blocos=len(blocos), andares=len(andares), unidades=len(unidades)
        ),
        possivel_duplicidade=[
            schemas.DuplicidadeSaida.model_validate(c)
            for c in repository.possiveis_duplicidades(session, condominio)
        ],
    )


def listar_fila(session: Session, filtros: schemas.FiltrosFila) -> schemas.PaginaFila:
    items, total = repository.listar_fila(session, filtros)
    return schemas.PaginaFila(
        items=[item_fila(session, c) for c in items],
        page=filtros.page,
        page_size=filtros.page_size,
        total=total,
    )


def detalhe_plataforma(session: Session, id_: uuid.UUID) -> schemas.DetalhePlataforma:
    condominio = repository.obter_plataforma(session, id_)
    blocos, andares, unidades = repository.estrutura_da_analise(session, id_)
    dados = item_fila(session, condominio).model_dump(exclude={"id", "nome", "cnpj", "status"})
    return schemas.DetalhePlataforma(
        **dados_condominio(session, condominio).model_dump(),
        **dados,
        blocos=_arvore_estrutura(blocos, andares, unidades),
    )


def decidir(
    session: Session,
    contexto: ContextoPlataforma,
    id_: uuid.UUID,
    decisao: Literal["aprovado", "rejeitado"],
    *,
    motivo: str | None = None,
    ip: str | None,
    relogio: Relogio = agora,
) -> schemas.CondominioSaida:
    try:
        condominio = repository.obter_plataforma(session, id_, bloquear=True)
        if condominio.status != "pendente":
            raise ApiError(409, "conflict", "Transição inválida.", reason="transicao_invalida")
        momento = relogio()
        quantidade = 0
        if decisao == "aprovado":
            condominio.status = "ativo"
            condominio.aprovado_em = momento
            for unidade in repository.estrutura_da_analise(session, id_)[2]:
                if unidade.ativo:
                    gerar_chave(session, unidade, momento)
                    quantidade += 1
        else:
            condominio.status = "rejeitado"
            condominio.motivo_rejeicao = motivo
        repository.registrar_decisao(
            session,
            condominio_id=id_,
            usuario_id=contexto.usuario_id,
            evento=decisao,
            motivo=motivo,
            momento=momento,
        )
        if decisao == "aprovado":
            repository.enfileirar_aprovacao(session, condominio, momento)
        auditoria.registrar_acao(
            session,
            ctx=ContextoAuditoria(contexto.usuario_id, id_, "plataforma", ip),
            acao="condominio.aprovar" if decisao == "aprovado" else "condominio.rejeitar",
            recurso_tipo="condominio",
            recurso_id=id_,
            antes={"status": "pendente"},
            depois={"status": "ativo", "chaves_geradas": quantidade}
            if decisao == "aprovado"
            else {"status": "rejeitado", "motivo": motivo},
        )
        saida = dados_condominio(session, condominio)
        session.commit()
        return saida
    except SQLAlchemyError:
        session.rollback()
        raise ApiError(500, "internal_error", "Não foi possível registrar a decisão.") from None
    except Exception:
        session.rollback()
        raise


def _arvore_estrutura(
    blocos: list[Bloco], andares: list[Andar], unidades: list[Unidade]
) -> list[schemas.BlocoAnalise]:
    return [
        schemas.BlocoAnalise(
            id=b.id,
            nome=b.nome,
            ativo=b.ativo,
            andares=[
                schemas.AndarAnalise(
                    id=a.id,
                    nome=a.nome,
                    ordem=a.ordem,
                    ativo=a.ativo,
                    unidades=[
                        schemas.UnidadeAnalise(
                            id=u.id, identificacao=u.identificacao, ativo=u.ativo
                        )
                        for u in unidades
                        if u.andar_id == a.id
                    ],
                )
                for a in andares
                if a.bloco_id == b.id
            ],
        )
        for b in blocos
    ]


def estrutura_do_cadastro(session: Session, contexto: ContextoCondominio) -> schemas.EstruturaSaida:
    repository.obter_do_cadastro(session, contexto)
    return schemas.EstruturaSaida(
        blocos=_arvore_estrutura(*repository.estrutura_da_analise(session, contexto.condominio_id))
    )


def erro_de_correcao(erro: IntegrityError) -> ApiError:
    constraint = getattr(getattr(erro.orig, "diag", None), "constraint_name", None)
    if constraint == "uq_condominios_cnpj":
        return ApiError(
            409, "conflict", "Já existe um condomínio com este CNPJ.", reason="cnpj_ja_cadastrado"
        )
    if constraint in {
        "uq_blocos_condominio_nome",
        "uq_andares_bloco_nome",
        "uq_unidades_andar_identificacao",
        "uq_unidades_condominio_identificacao_sem_andar",
    }:
        return ApiError(
            409, "conflict", "Já existe um item com este nome.", reason="nome_duplicado"
        )
    return ApiError(500, "internal_error", "Não foi possível corrigir o cadastro.")


class CorrecaoCadastroService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.blocos = repository.RepositorioBlocos(session, contexto)
        self.andares = repository.RepositorioAndares(session, contexto)
        self.unidades = RepositorioUnidades(session, contexto)
        self.chaves = RepositorioChaves(session, contexto)
        self.moradores = RepositorioMoradores(session, contexto)
        self.fotos = RepositorioFotos(session, contexto)

    def _bloquear_cadastro(
        self, responsavel_id: uuid.UUID, *, somente_rejeitado: bool = False
    ) -> Condominio:
        if self.contexto.perfil != "administracao":
            raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")
        # Conflita com a decisão do ADM e revalida o estado depois de esperar pela trava.
        condominio = repository.obter_do_cadastro(self.session, self.contexto, bloquear=True)
        if somente_rejeitado and condominio.status != "rejeitado":
            raise ApiError(409, "conflict", "Transição inválida.", reason="transicao_invalida")
        if not somente_rejeitado and condominio.status not in {"pendente", "rejeitado", "ativo"}:
            raise ApiError(403, "forbidden", "Este condomínio não está disponível no momento.")
        RepositorioResponsaveis(self.session, self.contexto).obter_ativo(responsavel_id)
        return condominio

    def editar_dados(
        self, dados: schemas.EdicaoCondominio, *, ip: str | None
    ) -> schemas.CondominioSaida:
        try:
            condominio = self._bloquear_cadastro(dados.responsavel_id)
            campos = {"nome": dados.nome, "cnpj": dados.cnpj, **dados.endereco.model_dump()}
            if "logo_arquivo_id" in dados.model_fields_set:
                if dados.logo_arquivo_id is not None:
                    self.fotos.conferir(dados.logo_arquivo_id)
                campos["logo_arquivo_id"] = dados.logo_arquivo_id
            antes = {
                campo: getattr(condominio, campo)
                for campo, valor in campos.items()
                if getattr(condominio, campo) != valor
            }
            for campo, valor in campos.items():
                setattr(condominio, campo, valor)
            self.session.flush()
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="condominio.editar",
                recurso_tipo="condominio",
                recurso_id=condominio.id,
                responsavel=ResponsavelRef("administracao", dados.responsavel_id),
                antes=antes,
                depois={campo: campos[campo] for campo in antes},
            )
            saida = dados_condominio(self.session, condominio)
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise

    def editar_bloco(
        self, id_: uuid.UUID, dados: schemas.EdicaoBloco, *, ip: str | None
    ) -> schemas.BlocoCorrecaoSaida:
        try:
            self._bloquear_cadastro(dados.responsavel_id)
            bloco = self.blocos.obter(id_)
            antes = {"nome": bloco.nome} if bloco.nome != dados.nome else {}
            bloco.nome = dados.nome
            self.session.flush()
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="estrutura.editar",
                recurso_tipo="bloco",
                recurso_id=bloco.id,
                responsavel=ResponsavelRef("administracao", dados.responsavel_id),
                antes=antes,
                depois={"nome": bloco.nome} if antes else {},
            )
            saida = schemas.BlocoCorrecaoSaida.model_validate(bloco)
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise

    def editar_andar(
        self, id_: uuid.UUID, dados: schemas.EdicaoAndar, *, ip: str | None
    ) -> schemas.AndarCorrecaoSaida:
        try:
            self._bloquear_cadastro(dados.responsavel_id)
            andar = self.andares.obter(id_)
            campos = {"nome": dados.nome, "ordem": dados.ordem}
            antes = {
                campo: getattr(andar, campo)
                for campo, valor in campos.items()
                if getattr(andar, campo) != valor
            }
            andar.nome, andar.ordem = dados.nome, dados.ordem
            self.session.flush()
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="estrutura.editar",
                recurso_tipo="andar",
                recurso_id=andar.id,
                responsavel=ResponsavelRef("administracao", dados.responsavel_id),
                antes=antes,
                depois={campo: campos[campo] for campo in antes},
            )
            saida = schemas.AndarCorrecaoSaida.model_validate(andar)
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise

    def editar_unidade(
        self, id_: uuid.UUID, dados: schemas.EdicaoUnidade, *, ip: str | None
    ) -> schemas.UnidadeAnalise:
        try:
            self._bloquear_cadastro(dados.responsavel_id)
            unidade = self.unidades.bloquear(id_)
            antes = (
                {"identificacao": unidade.identificacao}
                if unidade.identificacao != dados.identificacao
                else {}
            )
            unidade.identificacao = dados.identificacao
            self.session.flush()
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="estrutura.editar",
                recurso_tipo="unidade",
                recurso_id=unidade.id,
                responsavel=ResponsavelRef("administracao", dados.responsavel_id),
                antes=antes,
                depois={"identificacao": unidade.identificacao} if antes else {},
            )
            saida = schemas.UnidadeAnalise(
                id=unidade.id, identificacao=unidade.identificacao, ativo=unidade.ativo
            )
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise

    def reenviar(
        self, dados: schemas.AcaoCorrecao, *, ip: str | None, relogio: Relogio = agora
    ) -> schemas.ReenvioSaida:
        try:
            condominio = self._bloquear_cadastro(dados.responsavel_id, somente_rejeitado=True)
            momento = relogio()
            condominio.status = "pendente"
            condominio.enviado_em = momento
            condominio.motivo_rejeicao = None
            repository.registrar_decisao(
                self.session,
                condominio_id=condominio.id,
                usuario_id=self.contexto.usuario_id,
                evento="reenviado",
                motivo=None,
                momento=momento,
            )
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="condominio.reenviar",
                recurso_tipo="condominio",
                recurso_id=condominio.id,
                responsavel=ResponsavelRef("administracao", dados.responsavel_id),
                antes={"status": "rejeitado"},
                depois={"status": "pendente", "enviado_em": momento},
            )
            saida = schemas.ReenvioSaida(
                **dados_condominio(self.session, condominio).model_dump(), enviado_em=momento
            )
            self.session.commit()
            return saida
        except Exception:
            self.session.rollback()
            raise

    def _bloco_ativo(self, id_: uuid.UUID) -> Bloco:
        bloco = self.blocos.obter(id_)
        if not bloco.ativo:
            raise ApiError(409, "conflict", "Estrutura inativa.", reason="estrutura_inativa")
        return bloco

    def _andar_ativo(self, id_: uuid.UUID) -> Andar:
        andar = self.andares.obter(id_)
        self._bloco_ativo(andar.bloco_id)
        if not andar.ativo:
            raise ApiError(409, "conflict", "Estrutura inativa.", reason="estrutura_inativa")
        return andar

    def _auditar_estrutura(
        self,
        tipo: str,
        id_: uuid.UUID,
        responsavel_id: uuid.UUID,
        *,
        antes: dict[str, object],
        depois: dict[str, object],
        ip: str | None,
    ) -> None:
        auditoria.registrar_acao(
            self.session,
            ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
            acao="estrutura.editar",
            recurso_tipo=tipo,
            recurso_id=id_,
            responsavel=ResponsavelRef("administracao", responsavel_id),
            antes=antes,
            depois=depois,
        )

    def cadastrar_bloco(
        self, dados: schemas.EdicaoBloco, *, ip: str | None
    ) -> schemas.BlocoCorrecaoSaida:
        try:
            self._bloquear_cadastro(dados.responsavel_id)
            bloco = self.blocos.criar({"nome": dados.nome})
            self._auditar_estrutura(
                "bloco",
                bloco.id,
                dados.responsavel_id,
                antes={},
                depois={"nome": bloco.nome, "ativo": True},
                ip=ip,
            )
            saida = schemas.BlocoCorrecaoSaida.model_validate(bloco)
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise

    def cadastrar_andar(
        self, bloco_id: uuid.UUID, dados: schemas.EdicaoAndar, *, ip: str | None
    ) -> schemas.AndarCorrecaoSaida:
        try:
            self._bloquear_cadastro(dados.responsavel_id)
            bloco = self._bloco_ativo(bloco_id)
            andar = self.andares.criar(
                {"bloco_id": bloco.id, "nome": dados.nome, "ordem": dados.ordem}
            )
            self._auditar_estrutura(
                "andar",
                andar.id,
                dados.responsavel_id,
                antes={},
                depois={
                    "bloco_id": bloco.id,
                    "nome": andar.nome,
                    "ordem": andar.ordem,
                    "ativo": True,
                },
                ip=ip,
            )
            saida = schemas.AndarCorrecaoSaida.model_validate(andar)
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise

    def cadastrar_unidade(
        self,
        andar_id: uuid.UUID,
        dados: schemas.EdicaoUnidade,
        *,
        ip: str | None,
        relogio: Relogio = agora,
    ) -> schemas.UnidadeAnalise:
        try:
            condominio = self._bloquear_cadastro(dados.responsavel_id)
            andar = self._andar_ativo(andar_id)
            unidade = self.unidades.criar(
                {"andar_id": andar.id, "identificacao": dados.identificacao}
            )
            depois: dict[str, object] = {
                "andar_id": andar.id,
                "identificacao": unidade.identificacao,
                "ativo": True,
            }
            if condominio.status == "ativo":
                chave = gerar_chave(self.session, unidade, relogio())
                depois["chave_id"] = chave.id
            self._auditar_estrutura(
                "unidade",
                unidade.id,
                dados.responsavel_id,
                antes={},
                depois=depois,
                ip=ip,
            )
            saida = schemas.UnidadeAnalise(
                id=unidade.id, identificacao=unidade.identificacao, ativo=unidade.ativo
            )
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise

    def alterar_status_estrutura(
        self,
        tipo: schemas.TipoEstrutura,
        id_: uuid.UUID,
        ativo: bool,
        dados: schemas.AcaoCorrecao,
        *,
        ip: str | None,
        relogio: Relogio = agora,
    ) -> schemas.ElementoEstruturaSaida:
        try:
            condominio = self._bloquear_cadastro(dados.responsavel_id)
            item: Bloco | Andar | Unidade
            if tipo == "blocos":
                item = self.blocos.obter(id_)
                recurso = "bloco"
            elif tipo == "andares":
                item = self.andares.obter(id_)
                recurso = "andar"
            else:
                item = self.unidades.bloquear(id_)
                recurso = "unidade"
            if item.ativo == ativo:
                raise ApiError(409, "conflict", "Transição inválida.", reason="transicao_invalida")
            antes: dict[str, object] = {"ativo": item.ativo}
            depois: dict[str, object] = {"ativo": ativo}
            if isinstance(item, Bloco):
                if not ativo and self.blocos.tem_unidades_ativas(item.id):
                    raise ApiError(
                        409,
                        "conflict",
                        "Há unidades ativas nesta estrutura.",
                        reason="estrutura_com_unidades_ativas",
                    )
            elif isinstance(item, Andar):
                if ativo:
                    self._bloco_ativo(item.bloco_id)
                elif self.andares.tem_unidades_ativas(item.id):
                    raise ApiError(
                        409,
                        "conflict",
                        "Há unidades ativas nesta estrutura.",
                        reason="estrutura_com_unidades_ativas",
                    )
            else:
                if not ativo and self.moradores.contar_da_unidade(item.id):
                    raise ApiError(
                        409,
                        "conflict",
                        "A unidade possui moradores ativos.",
                        reason="unidade_com_vinculo_ativo",
                    )
                if ativo and item.andar_id is not None:
                    self._andar_ativo(item.andar_id)
                chave = self.chaves.vigente(item.id)
                if not ativo and chave is not None:
                    antes["chave_id"] = chave.id
                    chave.revogada_em = relogio()
                    depois["chave_id"] = None
                elif ativo and condominio.status == "ativo" and chave is None:
                    chave = gerar_chave(self.session, item, relogio())
                    antes["chave_id"] = None
                    depois["chave_id"] = chave.id
            item.ativo = ativo
            self.session.flush()
            self._auditar_estrutura(
                recurso, item.id, dados.responsavel_id, antes=antes, depois=depois, ip=ip
            )
            if isinstance(item, Andar):
                saida: schemas.ElementoEstruturaSaida = schemas.AndarCorrecaoSaida.model_validate(
                    item
                )
            elif isinstance(item, Bloco):
                saida = schemas.BlocoCorrecaoSaida.model_validate(item)
            else:
                saida = schemas.UnidadeAnalise(
                    id=item.id, identificacao=item.identificacao, ativo=item.ativo
                )
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            raise erro_de_correcao(erro) from None
        except Exception:
            self.session.rollback()
            raise
