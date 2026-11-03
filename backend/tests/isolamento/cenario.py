"""Montagem dos dados dos testes de isolamento: dois condomínios, cada um com seu usuário."""

import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.main import create_app
from app.modules.auth.security import TipoToken, emitir_token
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.usuarios.models import Usuario
from tests.isolamento import app_exemplo
from tests.isolamento.app_exemplo import Item


def montar_app() -> FastAPI:
    """A API real + as rotas de exemplo (que existem só aqui, nunca na API de verdade)."""
    app = create_app()
    app.include_router(app_exemplo.router, prefix="/api/v1")
    app.include_router(app_exemplo.diagnostico, prefix="/api/v1")
    return app


@dataclass
class Lado:
    """Um condomínio completo: o prédio, o usuário vinculado a ele e um item de exemplo."""

    condominio: Condominio
    usuario: Usuario
    vinculo: VinculoCondominio
    item: Item

    @property
    def cabecalho(self) -> dict[str, str]:
        return cabecalho(token_de(self.usuario, self.condominio.id, perfil=self.vinculo.perfil))


def criar_usuario(
    session: Session, *, ativo: bool = True, adm: bool = False, sessao_versao: int = 1
) -> Usuario:
    usuario = Usuario(
        nome="Pessoa de Teste",
        email=f"{uuid.uuid4().hex[:12]}@exemplo.test",
        ativo=ativo,
        administrador_plataforma=adm,
        sessao_versao=sessao_versao,
    )
    session.add(usuario)
    session.flush()
    return usuario


def criar_condominio(session: Session, nome: str = "Residencial Teste", ativo: bool = True):
    condominio = Condominio(nome=nome, status="ativo" if ativo else "desativado")
    session.add(condominio)
    session.flush()
    return condominio


def vincular(
    session: Session,
    usuario: Usuario,
    condominio: Condominio,
    perfil: str = "morador",
    ativo: bool = True,
) -> VinculoCondominio:
    vinculo = VinculoCondominio(
        usuario_id=usuario.id, condominio_id=condominio.id, perfil=perfil, ativo=ativo
    )
    session.add(vinculo)
    session.flush()
    return vinculo


def criar_item(session: Session, condominio: Condominio, nome: str) -> Item:
    item = Item(condominio_id=condominio.id, nome=nome)
    session.add(item)
    session.flush()
    return item


def criar_lado(session: Session, nome: str) -> Lado:
    condominio = criar_condominio(session, nome)
    usuario = criar_usuario(session)
    vinculo = vincular(session, usuario, condominio)
    item = criar_item(session, condominio, f"Item do {nome}")
    return Lado(condominio=condominio, usuario=usuario, vinculo=vinculo, item=item)


def token_de(
    usuario: Usuario,
    condominio_id: uuid.UUID | None,
    *,
    perfil: str | None = None,
    sessao_versao: int | None = None,
    tipo: TipoToken = TipoToken.ACCESS,
) -> str:
    """Assina um token direto, sem passar pelo login (que não é o assunto aqui)."""
    return emitir_token(
        tipo=tipo,
        usuario_id=usuario.id,
        condominio_id=condominio_id,
        sessao_versao=usuario.sessao_versao if sessao_versao is None else sessao_versao,
        perfil=perfil,
    )


def cabecalho(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
