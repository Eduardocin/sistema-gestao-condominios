"""O texto de cada e-mail, montado a partir do banco no momento do envio (plataforma.md, 6.2).

O destinatário vem do envio gravado na fila, nunca de um campo livre. O corpo não leva segredo.
"""

from sqlalchemy.orm import Session

from app.modules.notificacoes import repository
from app.modules.notificacoes.models import EnvioEmail
from app.modules.notificacoes.smtp import Mensagem


class CorpoIndisponivel(Exception):
    """Não há como montar o texto: evento sem modelo ou recurso que deixou de existir."""


def montar(session: Session, envio: EnvioEmail) -> Mensagem:
    construtor = _MODELOS.get(envio.evento)
    if construtor is None:
        raise CorpoIndisponivel("evento_sem_modelo")
    return construtor(session, envio)


def _condominio_aprovado(session: Session, envio: EnvioEmail) -> Mensagem:
    nome = repository.condominio_do_envio(session, envio)
    if nome is None:
        raise CorpoIndisponivel("recurso_inexistente")
    return Mensagem(
        envio.destinatario,
        f"Cadastro aprovado: {nome}",
        f"O cadastro do condomínio {nome} foi aprovado.\n"
        "Você já pode entrar no sistema e começar a usar.",
    )


def _encomenda_registrada(session: Session, envio: EnvioEmail) -> Mensagem:
    dados = repository.dados_da_encomenda(session, envio)
    if dados is None:
        raise CorpoIndisponivel("recurso_inexistente")
    descricao, unidade = dados
    return Mensagem(
        envio.destinatario,
        "Chegou uma encomenda para você",
        f"Uma encomenda foi registrada na portaria para a unidade {unidade}.\n"
        f"Descrição: {descricao}\n"
        "Abra o sistema para confirmar a retirada.",
    )


def _reserva_cancelada(session: Session, envio: EnvioEmail) -> Mensagem:
    dados = repository.dados_da_reserva(session, envio)
    if dados is None:
        raise CorpoIndisponivel("recurso_inexistente")
    reserva, area = dados
    linhas = [
        f"Sua reserva de {area} em {reserva.data:%d/%m/%Y}, às {reserva.hora_inicio:%H:%M}, "
        "foi cancelada pela Administração."
    ]
    if reserva.motivo_cancelamento:
        linhas.append(f"Motivo: {reserva.motivo_cancelamento}")
    return Mensagem(envio.destinatario, "Reserva cancelada", "\n".join(linhas))


_MODELOS = {
    "condominio_aprovado": _condominio_aprovado,
    "encomenda_registrada": _encomenda_registrada,
    "reserva_cancelada": _reserva_cancelada,
}
