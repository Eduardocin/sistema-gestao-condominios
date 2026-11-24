"""Regras das ocorrências (convivencia.md, §5).

Quem chama já passou por `require_permission` (perfil): ver o router. Aqui ficam o passo 4
(unidade e aba do Morador), a validação dos anexos, as transições, a auditoria e o commit.
"""

import uuid
from dataclasses import replace

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.permissoes import Perfil
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef
from app.modules.auth.autorizacao import garantir_aba_da_unidade
from app.modules.funcionarios.repository import RepositorioResponsaveis
from app.modules.ocorrencias.repository import (
    FiltrosOcorrencias,
    OcorrenciaDetalhada,
    RepositorioAnexos,
    RepositorioArquivos,
    RepositorioInteracoes,
    RepositorioOcorrencias,
    UltimaInteracao,
)
from app.modules.ocorrencias.schemas import (
    AnexoSaida,
    AutorSaida,
    InteracaoSaida,
    OcorrenciaEntrada,
    OcorrenciaResumo,
    OcorrenciaSaida,
    PaginaDeOcorrencias,
    PessoaResumo,
    ResolucaoEntrada,
    RespostaEntrada,
    UnidadeResumo,
)

ABA_OCORRENCIAS = "ocorrencias"
MENSAGEM_UNIDADE_OBRIGATORIA = "Informe a unidade."
MENSAGEM_ANEXO_INVALIDO = "Um ou mais anexos informados não existem neste condomínio."
MENSAGEM_JA_RESOLVIDA = "A ocorrência já está resolvida."


class OcorrenciasService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.ocorrencias = RepositorioOcorrencias(session, contexto)
        self.interacoes = RepositorioInteracoes(session, contexto)
        self.anexos = RepositorioAnexos(session, contexto)
        self.arquivos = RepositorioArquivos(session, contexto)
        self.responsaveis = RepositorioResponsaveis(session, contexto)

    @property
    def _e_morador(self) -> bool:
        return self.contexto.perfil == Perfil.MORADOR

    def _unidade(self, unidade_id: uuid.UUID) -> None:
        # Passo 4: 404 se a unidade não é do Morador, depois 403 se a aba estiver Sem Acesso.
        garantir_aba_da_unidade(self.session, self.contexto, unidade_id, ABA_OCORRENCIAS)

    def _conferir_anexos(self, anexos: list[uuid.UUID]) -> None:
        """O storage já validou tipo e tamanho; aqui conferimos o vínculo com este condomínio."""
        prefixo = f"condominio/{self.contexto.condominio_id}/ocorrencias/"
        for arquivo_id in anexos:
            arquivo = self.arquivos.buscar(arquivo_id)
            if (
                arquivo is None
                or arquivo.enviado_por_usuario_id != self.contexto.usuario_id
                or not arquivo.chave_storage.startswith(prefixo)
                or not (arquivo.tipo_mime.startswith("image/") or arquivo.tipo_mime == "video/mp4")
            ):
                raise ApiError(422, "validation_error", MENSAGEM_ANEXO_INVALIDO)

    # --- abertura -------------------------------------------------------------------------

    def criar(self, dados: OcorrenciaEntrada) -> OcorrenciaSaida:
        self._unidade(dados.unidade_id)
        self._conferir_anexos(dados.anexos)
        ocorrencia = self.ocorrencias.criar(
            {
                "unidade_id": dados.unidade_id,
                "aberta_por_usuario_id": self.contexto.usuario_id,
                "titulo": dados.titulo,
                "detalhe": dados.detalhe,
            }
        )
        for arquivo_id in dados.anexos:
            self.anexos.criar({"ocorrencia_id": ocorrencia.id, "arquivo_id": arquivo_id})
        ocorrencia_id = ocorrencia.id
        self.session.commit()
        return self.obter(ocorrencia_id)

    # --- consulta -------------------------------------------------------------------------

    def listar(
        self,
        *,
        unidade_id: uuid.UUID | None,
        filtros: FiltrosOcorrencias,
        page: int,
        page_size: int,
    ) -> PaginaDeOcorrencias:
        if self._e_morador:
            # Para o Morador só vale `unidade_id`; os filtros da Administração são ignorados.
            if unidade_id is None:
                raise ApiError(422, "validation_error", MENSAGEM_UNIDADE_OBRIGATORIA)
            self._unidade(unidade_id)
            filtros = FiltrosOcorrencias(unidade_id=unidade_id, status=filtros.status)
        else:
            # Filtro dentro do condomínio do token: unidade de outro prédio devolve lista vazia.
            filtros = replace(filtros, unidade_id=unidade_id)

        itens, total = self.ocorrencias.pagina(
            filtros, limite=page_size, deslocamento=(page - 1) * page_size
        )
        ultimas = self.ocorrencias.ultimas_interacoes([item.ocorrencia.id for item in itens])
        return PaginaDeOcorrencias(
            items=[self._resumo(item, ultimas.get(item.ocorrencia.id)) for item in itens],
            page=page,
            page_size=page_size,
            total=total,
        )

    def obter(self, ocorrencia_id: uuid.UUID) -> OcorrenciaSaida:
        detalhada = self.ocorrencias.obter_detalhada(ocorrencia_id)
        if detalhada is None:
            raise RecursoNaoEncontrado
        if self._e_morador:
            # Ocorrência de outra unidade: 404. Da própria unidade sem a aba: 403.
            self._unidade(detalhada.ocorrencia.unidade_id)
        return self._apresentar(detalhada)

    # --- tratamento pela Administração ----------------------------------------------------

    def responder(self, ocorrencia_id: uuid.UUID, dados: RespostaEntrada) -> InteracaoSaida:
        self.ocorrencias.obter(ocorrencia_id)  # 404 se não existir ou for de outro condomínio
        responsavel = self.responsaveis.obter_ativo(dados.responsavel_id)
        interacao = self.interacoes.criar(
            {
                "ocorrencia_id": ocorrencia_id,
                "tipo": "resposta",
                "texto": dados.texto,
                "usuario_id": self.contexto.usuario_id,
                "responsavel_id": responsavel.id,
            }
        )
        saida = InteracaoSaida(
            id=interacao.id,
            tipo="resposta",
            texto=interacao.texto,
            autor=AutorSaida(tipo="administracao", nome=responsavel.nome),
            em=interacao.criado_em,
            anexos=[],
        )
        self.session.commit()
        return saida

    def resolver(
        self, ocorrencia_id: uuid.UUID, dados: ResolucaoEntrada, *, ip: str | None
    ) -> OcorrenciaSaida:
        ocorrencia = self.ocorrencias.bloquear(ocorrencia_id)
        if ocorrencia is None:
            raise RecursoNaoEncontrado
        responsavel = self.responsaveis.obter_ativo(dados.responsavel_id)
        if ocorrencia.status != "em_aberto":
            raise ApiError(409, "conflict", MENSAGEM_JA_RESOLVIDA, reason="ocorrencia_ja_resolvida")

        self.ocorrencias.atualizar(
            ocorrencia.id, {"status": "resolvida", "resolvida_em": func.now()}
        )
        self.interacoes.criar(
            {
                "ocorrencia_id": ocorrencia.id,
                "tipo": "resolucao",
                "texto": dados.texto,
                "usuario_id": self.contexto.usuario_id,
                "responsavel_id": responsavel.id,
            }
        )
        auditoria.registrar_acao(
            self.session,
            ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
            acao="ocorrencia.resolver",
            recurso_tipo="ocorrencia",
            recurso_id=ocorrencia.id,
            responsavel=ResponsavelRef("administracao", responsavel.id),
            antes={"status": "em_aberto"},
            depois={"status": "resolvida"},
        )
        ocorrencia_id = ocorrencia.id
        self.session.commit()
        return self.obter(ocorrencia_id)

    # --- apresentação ---------------------------------------------------------------------

    def _resumo(
        self, detalhada: OcorrenciaDetalhada, ultima: UltimaInteracao | None
    ) -> OcorrenciaResumo:
        ocorrencia = detalhada.ocorrencia
        return OcorrenciaResumo(
            id=ocorrencia.id,
            titulo=ocorrencia.titulo,
            status=ocorrencia.status,
            unidade=UnidadeResumo(
                id=ocorrencia.unidade_id, identificacao=detalhada.unidade_identificacao
            ),
            criada_em=ocorrencia.criado_em,
            ultima_interacao_em=None if ultima is None else ultima.em,
            aguardando_administracao=ultima is None or ultima.responsavel_id is None,
        )

    def _apresentar(self, detalhada: OcorrenciaDetalhada) -> OcorrenciaSaida:
        ocorrencia = detalhada.ocorrencia
        anexos = self.ocorrencias.anexos(ocorrencia.id)
        interacoes = [
            InteracaoSaida(
                id=interacao.interacao.id,
                tipo=interacao.interacao.tipo,
                texto=interacao.interacao.texto,
                autor=AutorSaida(tipo=interacao.autor_tipo, nome=interacao.autor_nome),
                em=interacao.interacao.criado_em,
                anexos=[
                    AnexoSaida(arquivo_id=anexo.arquivo_id, interacao_id=anexo.interacao_id)
                    for anexo in anexos
                    if anexo.interacao_id == interacao.interacao.id
                ],
            )
            for interacao in self.ocorrencias.interacoes(ocorrencia.id)
        ]
        return OcorrenciaSaida(
            id=ocorrencia.id,
            unidade=UnidadeResumo(
                id=ocorrencia.unidade_id, identificacao=detalhada.unidade_identificacao
            ),
            titulo=ocorrencia.titulo,
            detalhe=ocorrencia.detalhe,
            status=ocorrencia.status,
            aberta_por=PessoaResumo(
                id=ocorrencia.aberta_por_usuario_id, nome=detalhada.aberta_por_nome
            ),
            criada_em=ocorrencia.criado_em,
            resolvida_em=ocorrencia.resolvida_em,
            anexos=[
                AnexoSaida(arquivo_id=anexo.arquivo_id, interacao_id=anexo.interacao_id)
                for anexo in anexos
            ],
            interacoes=interacoes,
        )
