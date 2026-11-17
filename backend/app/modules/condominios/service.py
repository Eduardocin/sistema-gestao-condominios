import uuid
from typing import Literal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoPlataforma
from app.core.errors import ApiError
from app.core.tempo import Relogio, agora
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria
from app.modules.condominios import repository, schemas
from app.modules.condominios.models import Condominio
from app.modules.condominios.schemas import (
    CadastroCondominio,
    CadastroCondominioSaida,
    CondominioResumo,
)
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
        blocos=[
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
        ],
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
