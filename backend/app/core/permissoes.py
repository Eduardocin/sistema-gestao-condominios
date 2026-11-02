"""A matriz de permissões (docs/permissoes-e-multitenant.md, seção 7) virada em código.

Este arquivo é só dados e uma pergunta: "esse perfil pode fazer essa ação nesse recurso?".
Ele não conhece banco nem HTTP. Quem aplica a regra numa rota é `require_permission`
(app/modules/auth/autorizacao.py).

A regra é negar por padrão: o que não está na matriz não é permitido.
"""

from enum import StrEnum


class Perfil(StrEnum):
    MORADOR = "morador"
    FUNCIONARIO = "funcionario"
    ADMINISTRACAO = "administracao"
    # O ADM da plataforma não é vínculo de condomínio (é `usuarios.administrador_plataforma`),
    # mas ganha uma coluna própria aqui para a matriz ficar igual à do documento.
    PLATAFORMA = "plataforma"


# As quatro ações da matriz. A letra é a mesma da tabela do documento.
# Nenhum perfil apaga de verdade: "D" é desativar, cancelar ou desvincular.
ACOES = {"V": "ver", "C": "criar", "E": "editar", "D": "desativar"}

# Cada linha segue a ordem das colunas do documento: Morador, Funcionário, Administração, ADM.
# Texto vazio = traço da tabela (negado). As letras dizem o que o perfil pode fazer.
#
# Detalhes que a letra não carrega (só a própria unidade, só o próprio recebedor, só o nome do
# condomínio...) NÃO ficam aqui: são a "regra de negócio", passo 6 da ordem de checagem, e cada
# módulo cuida delas no seu service. A matriz responde só "pode ou não pode esse tipo de ação".
_LINHAS: dict[str, tuple[str, str, str, str]] = {
    #                         Morador  Func.  Admin.  ADM
    "conta_propria": ("VE", "V", "VE", "VE"),
    "dados_condominio": ("V", "V", "VE", "VED"),
    # Administração: "C, e E para corrigir". O V vem da R7 (ela precisa ver o que corrige).
    # ADM: aprovar e rejeitar contam como E.
    "cadastro_condominio": ("", "", "VCE", "VED"),
    "estrutura": ("V", "V", "VCED", "V"),
    "proprietarios": ("V", "", "VCE", ""),
    # gerar = C, regenerar = E, revogar = D
    "chaves_acesso": ("", "", "VCED", ""),
    # Morador: solicitar com a chave (C) e convidar. Administração: aprovar/rejeitar (E) e
    # desvincular (D).
    "vinculos": ("VC", "", "VED", ""),
    "permissoes_aba": ("VE", "", "", ""),
    "funcionarios": ("", "V", "VCED", ""),
    "contas_compartilhadas": ("", "", "VCE", ""),
    # E do Morador = só confirmar o recebimento (o service confere se ele é o recebedor).
    # E do Funcionário = registrar a entrega física.
    "encomendas": ("VE", "VCE", "V", ""),
    "visitantes": ("VCED", "VCE", "V", ""),
    "veiculos": ("VCED", "V", "V", ""),
    "areas_comuns": ("V", "", "VCED", ""),
    "reservas": ("VCD", "", "VD", ""),
    "ocorrencias": ("VCE", "", "VE", ""),
    "avisos": ("V", "V", "VCED", ""),
    "comunicados": ("", "", "V", "VCD"),
    "suporte": ("", "", "VC", "VE"),
    "auditoria": ("", "", "", "V"),
}

_COLUNAS = (Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA)

RECURSOS = frozenset(_LINHAS)
NOMES_DAS_ACOES = frozenset(ACOES.values())


def _montar_matriz() -> dict[tuple[str, str], frozenset[str]]:
    """Transforma as letras da tabela em {(perfil, recurso): {"ver", "criar", ...}}."""
    matriz: dict[tuple[str, str], frozenset[str]] = {}
    for recurso, celulas in _LINHAS.items():
        for perfil, letras in zip(_COLUNAS, celulas, strict=True):
            desconhecidas = set(letras) - set(ACOES)
            if desconhecidas:
                # Erro de digitação na tabela estoura na hora do import, não em produção.
                raise ValueError(f"{recurso}/{perfil}: letras inválidas {sorted(desconhecidas)}")
            matriz[(perfil.value, recurso)] = frozenset(ACOES[letra] for letra in letras)
    return matriz


_MATRIZ = _montar_matriz()


def pode(perfil: str | None, recurso: str, acao: str) -> bool:
    """O perfil pode executar a ação no recurso? Perfil ou recurso desconhecido: não."""
    if perfil is None:
        return False
    return acao in _MATRIZ.get((perfil, recurso), frozenset())


def interpretar(permissao: str) -> tuple[str, str]:
    """Quebra "encomendas:ver" em ("encomendas", "ver"), conferindo se os dois existem.

    Quem declara uma rota com um nome errado (ex.: "encomenda:ver") recebe o erro ao subir a
    aplicação, e não um 403 misterioso depois.
    """
    recurso, separador, acao = permissao.partition(":")
    if not separador or recurso not in RECURSOS or acao not in NOMES_DAS_ACOES:
        raise ValueError(
            f"Permissão inválida: {permissao!r}. Use 'recurso:acao', com recurso em "
            f"{sorted(RECURSOS)} e ação em {sorted(NOMES_DAS_ACOES)}."
        )
    return recurso, acao
