"""Importe aqui cada novo modelo para que o Alembic enxergue seu metadata."""

from app.modules.auditoria.models import RegistroAuditoria
from app.modules.avisos.models import Aviso, Comunicado, ComunicadoDestinatario
from app.modules.condominios.models import (
    Condominio,
    CondominioAnalise,
    CondominioDocumento,
    VinculoCondominio,
)
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.notificacoes.models import EnvioEmail
from app.modules.ocorrencias.models import Ocorrencia, OcorrenciaAnexo, OcorrenciaInteracao
from app.modules.reservas.models import AreaComum, BloqueioArea, Reserva
from app.modules.storage.models import Arquivo
from app.modules.suporte.models import Chamado, ChamadoAnexo, ChamadoMensagem
from app.modules.unidades.models import (
    Andar,
    Bloco,
    ChaveAcesso,
    ConviteMorador,
    MoradorUnidade,
    PermissaoAba,
    ProprietarioUnidade,
    Unidade,
)
from app.modules.usuarios.models import TentativaChaveAcesso, TokenRecuperacaoSenha, Usuario
from app.modules.visitantes.models import RegistroVisita, Veiculo, Visitante

__all__ = [
    "Andar",
    "AreaComum",
    "Arquivo",
    "Aviso",
    "Bloco",
    "BloqueioArea",
    "Chamado",
    "ChamadoAnexo",
    "ChamadoMensagem",
    "ChaveAcesso",
    "Comunicado",
    "ComunicadoDestinatario",
    "Condominio",
    "CondominioAnalise",
    "CondominioDocumento",
    "ConviteMorador",
    "Encomenda",
    "EnvioEmail",
    "Funcionario",
    "MoradorUnidade",
    "Ocorrencia",
    "OcorrenciaAnexo",
    "OcorrenciaInteracao",
    "PermissaoAba",
    "ProprietarioUnidade",
    "RegistroAuditoria",
    "RegistroVisita",
    "Reserva",
    "ResponsavelAdministracao",
    "TentativaChaveAcesso",
    "TokenRecuperacaoSenha",
    "Unidade",
    "Usuario",
    "Veiculo",
    "VinculoCondominio",
    "Visitante",
]
