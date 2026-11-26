import uuid

import pytest

from app.modules.auth.service import Acesso


@pytest.mark.parametrize(
    ("perfil", "status", "liberado"),
    [
        ("administracao", "ativo", True),
        ("administracao", "pendente", True),
        ("administracao", "rejeitado", True),
        ("administracao", "desativado", False),
        ("morador", "pendente", False),
        ("funcionario", "desativado", False),
    ],
)
def test_acesso_local_respeita_estado_do_condominio(perfil, status, liberado):
    acesso = Acesso(
        condominio_id=uuid.uuid4(),
        nome="Residencial Aurora",
        perfil=perfil,
        status=status,
    )

    assert acesso.liberado is liberado
