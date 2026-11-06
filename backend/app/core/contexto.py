"""Contexto de uma requisição de condomínio: quem está agindo e em qual condomínio.

Quem monta é `get_current_context` (app/modules/auth/dependencies.py), sempre a partir do token
validado + vínculo lido do banco. Nenhuma rota constrói isto com IDs enviados pelo cliente.
Os nomes `usuario_id` e `condominio_id` casam com o `StorageContext` de propósito.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ContextoCondominio:
    usuario_id: uuid.UUID
    condominio_id: uuid.UUID
    # Perfil do vínculo no banco (R6). Ainda não permite nem nega nada: isso é a TASK-19.
    # Perfil do vínculo no banco (R6). Quem decide o que ele pode é `require_permission`
    # (app/modules/auth/autorizacao.py), com a matriz de app/core/permissoes.py.
    perfil: str
    vinculo_id: uuid.UUID


@dataclass(frozen=True)
class ContextoPlataforma:
    """Quem age nas rotas `/plataforma/...`: o ADM da plataforma, sem condomínio (R8, R9)."""

    usuario_id: uuid.UUID
