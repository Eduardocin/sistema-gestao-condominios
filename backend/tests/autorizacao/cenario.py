"""Um prédio com um usuário de cada perfil, mais o ADM da plataforma, para os testes."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.permissoes import Perfil
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.unidades.models import MoradorUnidade, Unidade
from app.modules.usuarios.models import Usuario
from tests.isolamento.cenario import (
    cabecalho,
    criar_condominio,
    criar_usuario,
    token_de,
    vincular,
)


@dataclass
class Predio:
    condominio: Condominio
    unidade_101: Unidade
    unidade_102: Unidade
    morador: Usuario  # mora na 101
    vinculo_morador: VinculoCondominio
    funcionario: Usuario
    administracao: Usuario
    adm: Usuario  # ADM da plataforma: sem condomínio e sem vínculo
    morador_unidade: MoradorUnidade

    def cabecalho_de(self, perfil: str) -> dict[str, str]:
        """Cabeçalho Authorization de cada perfil, com o token que o login emitiria."""
        if perfil == Perfil.PLATAFORMA:
            return cabecalho(token_de(self.adm, None, perfil=Perfil.PLATAFORMA))
        usuario = {
            Perfil.MORADOR: self.morador,
            Perfil.FUNCIONARIO: self.funcionario,
            Perfil.ADMINISTRACAO: self.administracao,
        }[Perfil(perfil)]
        return cabecalho(token_de(usuario, self.condominio.id, perfil=perfil))


def criar_unidade(session: Session, condominio: Condominio, identificacao: str) -> Unidade:
    unidade = Unidade(condominio_id=condominio.id, identificacao=identificacao)
    session.add(unidade)
    session.flush()
    return unidade


def montar_predio(session: Session, nome: str = "Residencial Aurora") -> Predio:
    condominio = criar_condominio(session, nome)
    u101 = criar_unidade(session, condominio, "Bloco A / 101")
    u102 = criar_unidade(session, condominio, "Bloco A / 102")

    morador = criar_usuario(session)
    vinculo = vincular(session, morador, condominio, perfil="morador")
    vinculo.unidade_id = u101.id  # mantido para os consumidores ainda legados, como /auth/me
    morador_unidade = MoradorUnidade(
        condominio_id=condominio.id,
        unidade_id=u101.id,
        usuario_id=morador.id,
        origem="cadastro",
    )
    session.add(morador_unidade)
    session.flush()

    funcionario = criar_usuario(session)
    vincular(session, funcionario, condominio, perfil="funcionario")
    administracao = criar_usuario(session)
    vincular(session, administracao, condominio, perfil="administracao")
    adm = criar_usuario(session, adm=True)

    return Predio(
        condominio=condominio,
        unidade_101=u101,
        unidade_102=u102,
        morador=morador,
        vinculo_morador=vinculo,
        funcionario=funcionario,
        administracao=administracao,
        adm=adm,
        morador_unidade=morador_unidade,
    )
