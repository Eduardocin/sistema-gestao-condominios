"""Carrega dados fictícios no banco local de demonstração.

A massa cobre todas as telas do roteiro em docs/demo/README.md: dois condomínios ativos com
estrutura, moradores, portaria, convivência e suporte, e um terceiro aguardando análise para
que o ADM da plataforma aprove ao vivo. Datas são relativas ao dia do reset.
"""

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from pydantic_settings import SettingsError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.tempo import agora, inicio_do_slot
from app.db.base import Base
from app.db.models import (
    Andar,
    AreaComum,
    Arquivo,
    Aviso,
    Bloco,
    Chamado,
    ChamadoMensagem,
    ChaveAcesso,
    Comunicado,
    ComunicadoDestinatario,
    Condominio,
    CondominioAnalise,
    Encomenda,
    Funcionario,
    MoradorUnidade,
    Ocorrencia,
    OcorrenciaInteracao,
    PermissaoAba,
    RegistroAuditoria,
    RegistroVisita,
    Reserva,
    ResponsavelAdministracao,
    Unidade,
    Usuario,
    Veiculo,
    VinculoCondominio,
    Visitante,
)
from app.db.session import get_session_factory
from app.modules.auth.security import hash_senha
from app.modules.storage.s3 import S3Adapter
from app.modules.unidades.models import ABAS_MORADOR
from app.modules.unidades.service import ALFABETO_CHAVE
from app.modules.visitantes.schemas import Autorizacao, Referencia

SENHA_DEMO = "Teste123"
IMAGENS = {
    "fotos": "sala-ilustrativa.png",
    "encomendas": "caixa-ilustrativa.png",
}
MIME_IMAGEM = "image/png"
# Chave fixa de uma unidade vaga, para demonstrar o vínculo de um novo morador.
CHAVE_DEMO = "AURRAB2Z22"


@dataclass(frozen=True)
class MoradorDemo:
    login: str
    nome: str
    unidade: str  # "Bloco/identificação"


@dataclass(frozen=True)
class CenarioDemo:
    nome: str
    cnpj: str
    endereco: tuple[str, str, str, str, str, str]  # cep, logradouro, número, bairro, cidade, UF
    blocos: tuple[str, ...]
    andares: int
    unidades_por_andar: int
    moradores: tuple[MoradorDemo, ...]
    placa: str
    areas: tuple[tuple[str, int, int, int, str], ...]  # nome, abre, fecha, capacidade, regras
    funcionarios: tuple[tuple[str, str], ...] = ()
    responsaveis: tuple[str, ...] = ("Responsável Demo",)


CENARIOS: dict[str, CenarioDemo] = {
    "aurora": CenarioDemo(
        nome="Jardins da Aurora",
        cnpj="48261593000176",
        endereco=("01310100", "Avenida das Acácias", "1200", "Jardim Aurora", "São Paulo", "SP"),
        blocos=("Bloco A", "Bloco B"),
        andares=3,
        unidades_por_andar=2,
        moradores=(
            MoradorDemo("morador.aurora", "Ana Souza", "Bloco A/101"),
            MoradorDemo("morador.aurora.a102", "Bruno Lima", "Bloco A/102"),
            MoradorDemo("morador.aurora.a201", "Carla Mendes", "Bloco A/201"),
            MoradorDemo("morador.aurora.b101", "Diego Rocha", "Bloco B/101"),
            MoradorDemo("morador.aurora.b302", "Elisa Fernandes", "Bloco B/302"),
        ),
        placa="DEM0A01",
        areas=(
            ("Salão da Aurora", 8, 22, 60, "Música até as 22h. Deixe o espaço organizado."),
            ("Churrasqueira", 10, 22, 25, "Traga seu carvão. Limpe a grelha após o uso."),
            ("Academia", 6, 22, 8, "Use toalha nos aparelhos. Uma hora por unidade."),
        ),
        funcionarios=(
            ("Porteiro Demo", "porteiro"),
            ("Joana Ribeiro", "porteiro"),
            ("Paulo Santos", "seguranca"),
        ),
        responsaveis=("Responsável Demo", "Síndica Marta Alves"),
    ),
    "horizonte": CenarioDemo(
        nome="Pátio do Horizonte",
        cnpj="57390418000170",
        endereco=("30140071", "Rua do Horizonte", "455", "Centro", "Belo Horizonte", "MG"),
        blocos=("Torre Única",),
        andares=2,
        unidades_por_andar=2,
        moradores=(
            MoradorDemo("morador.horizonte", "Fábio Martins", "Torre Única/202"),
            MoradorDemo("morador.horizonte.t101", "Gabriela Nunes", "Torre Única/101"),
        ),
        placa="DEM0B02",
        areas=(
            ("Salão do Horizonte", 9, 22, 40, "Reservas de uma hora. Respeite o silêncio."),
            ("Piscina", 8, 20, 15, "Proibido vidro na área da piscina."),
        ),
        funcionarios=(("Porteiro Demo", "porteiro"), ("Rita Moraes", "porteiro")),
        responsaveis=("Responsável Demo", "Síndico Otávio Reis"),
    ),
}
PENDENTE = CenarioDemo(
    nome="Residencial Vista Verde",
    cnpj="61928374000166",
    endereco=("80020000", "Rua das Palmeiras", "88", "Batel", "Curitiba", "PR"),
    blocos=("Bloco Único",),
    andares=2,
    unidades_por_andar=2,
    moradores=(),
    placa="",
    areas=(),
)


def _imagem(modulo: str) -> bytes:
    return (Path(__file__).with_name("demo_assets") / IMAGENS[modulo]).read_bytes()


def _id_demo(cenario: str, recurso: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://example.test/condominios-demo/{cenario}/{recurso}")


def _chave_imagem(cenario: str, modulo: str) -> str:
    # IDs reservados para a demo mantêm as quatro chaves estáveis entre resets e no backup.
    condominio_id = _id_demo(cenario, "condominio")
    return f"condominio/{condominio_id}/{modulo}/{_id_demo(cenario, modulo)}"


def _carregar_imagens(storage: S3Adapter) -> None:
    for modulo in IMAGENS:
        imagem = _imagem(modulo)
        for cenario in CENARIOS:
            storage.put(_chave_imagem(cenario, modulo), imagem, MIME_IMAGEM)


@dataclass(frozen=True)
class DemoSeedSummary:
    condominios: int
    contas: int


@dataclass
class _Carga:
    """Estado compartilhado durante a carga de um reset."""

    session: Session
    hoje: date
    senha_hash: str
    contas: int = 0

    def momento(self, dias: int, hora: int, minuto: int = 0) -> datetime:
        return inicio_do_slot(self.hoje + timedelta(days=dias), time(hora, minuto))

    def conta(
        self, login: str, nome: str, *, tipo: str | None = None, plataforma: bool = False
    ) -> Usuario:
        usuario = Usuario(
            nome=nome,
            email=f"{login}@example.test",
            senha_hash=self.senha_hash,
            tipo_cadastro=tipo,
            administrador_plataforma=plataforma,
        )
        self.session.add(usuario)
        self.contas += 1
        return usuario


@dataclass
class _Condominio:
    chave: str
    registro: Condominio
    portaria: Usuario | None
    unidades: dict[str, Unidade] = field(default_factory=dict)
    moradias: dict[str, MoradorUnidade] = field(default_factory=dict)
    moradores: dict[str, Usuario] = field(default_factory=dict)
    funcionarios: list[Funcionario] = field(default_factory=list)
    responsaveis: list[ResponsavelAdministracao] = field(default_factory=list)
    areas: list[AreaComum] = field(default_factory=list)

    @property
    def cid(self) -> UUID:
        return self.registro.id

    def de(self, login: str) -> tuple[Usuario, MoradorUnidade, Unidade]:
        moradia = self.moradias[login]
        return self.moradores[login], moradia, self.unidades_por_id[moradia.unidade_id]

    @property
    def unidades_por_id(self) -> dict[UUID, Unidade]:
        return {unidade.id: unidade for unidade in self.unidades.values()}


def _condominio(
    carga: _Carga,
    chave: str,
    cenario: CenarioDemo,
    *,
    dono: Usuario,
    plataforma: Usuario,
    status: str,
) -> _Condominio:
    session = carga.session
    cep, logradouro, numero, bairro, cidade, uf = cenario.endereco
    enviado = carga.momento(-30 if status == "ativo" else -1, 10)
    registro = Condominio(
        id=_id_demo(chave, "condominio"),
        nome=cenario.nome,
        status=status,
        cnpj=cenario.cnpj,
        cep=cep,
        logradouro=logradouro,
        numero=numero,
        bairro=bairro,
        cidade=cidade,
        uf=uf,
        criado_por_usuario_id=dono.id,
        enviado_em=enviado,
        aprovado_em=enviado + timedelta(days=1) if status == "ativo" else None,
    )
    ativo = status == "ativo"
    portaria = carga.conta(f"portaria.{chave}", f"Portaria {cenario.nome}") if ativo else None
    session.add(registro)
    session.flush()
    estado = _Condominio(chave=chave, registro=registro, portaria=portaria)

    for nome_bloco in cenario.blocos:
        bloco = Bloco(condominio_id=registro.id, nome=nome_bloco)
        session.add(bloco)
        session.flush()
        for ordem in range(1, cenario.andares + 1):
            andar = Andar(
                condominio_id=registro.id, bloco_id=bloco.id, nome=f"Andar {ordem}", ordem=ordem
            )
            session.add(andar)
            session.flush()
            for sufixo in range(1, cenario.unidades_por_andar + 1):
                identificacao = f"{ordem}{sufixo:02d}"
                unidade = Unidade(
                    condominio_id=registro.id, andar_id=andar.id, identificacao=identificacao
                )
                session.add(unidade)
                estado.unidades[f"{nome_bloco}/{identificacao}"] = unidade
    session.flush()

    vinculos = [(dono, "administracao")]
    if portaria is not None:
        vinculos.append((portaria, "funcionario"))
        estado.funcionarios = [
            Funcionario(condominio_id=registro.id, nome=nome, funcao=funcao)
            for nome, funcao in cenario.funcionarios
        ]
        estado.responsaveis = [
            ResponsavelAdministracao(condominio_id=registro.id, nome=nome)
            for nome in cenario.responsaveis
        ]
        session.add_all([*estado.funcionarios, *estado.responsaveis])
        for morador in cenario.moradores:
            usuario = carga.conta(morador.login, morador.nome, tipo="morador")
            session.flush()
            moradia = MoradorUnidade(
                condominio_id=registro.id,
                unidade_id=estado.unidades[morador.unidade].id,
                usuario_id=usuario.id,
                origem="cadastro",
            )
            session.add(moradia)
            estado.moradores[morador.login] = usuario
            estado.moradias[morador.login] = moradia
            vinculos.append((usuario, "morador"))
    session.flush()
    session.add_all(
        VinculoCondominio(usuario_id=usuario.id, condominio_id=registro.id, perfil=perfil)
        for usuario, perfil in vinculos
    )
    session.add_all(
        PermissaoAba(
            morador_unidade_id=moradia.id, condominio_id=registro.id, aba=aba, com_acesso=True
        )
        for moradia in estado.moradias.values()
        for aba in ABAS_MORADOR
    )

    if ativo:
        _historico_aprovacao(carga, estado, plataforma)
        ocupadas = {moradia.unidade_id for moradia in estado.moradias.values()}
        for nome_unidade, unidade in estado.unidades.items():
            if unidade.id in ocupadas:
                continue
            demo = (chave, nome_unidade) == ("aurora", "Bloco B/202")
            session.add(
                ChaveAcesso(
                    condominio_id=registro.id,
                    unidade_id=unidade.id,
                    codigo=CHAVE_DEMO if demo else _codigo_chave(chave, nome_unidade),
                    criada_em=registro.aprovado_em,
                )
            )
    session.flush()
    return estado


def _codigo_chave(chave: str, unidade: str) -> str:
    """Código estável entre resets, no mesmo alfabeto das chaves reais."""
    numero = _id_demo(chave, f"chave/{unidade}").int
    return "".join(ALFABETO_CHAVE[(numero >> (5 * i)) % len(ALFABETO_CHAVE)] for i in range(10))


def _historico_aprovacao(carga: _Carga, estado: _Condominio, plataforma: Usuario) -> None:
    registro = estado.registro
    carga.session.add_all(
        [
            CondominioAnalise(
                condominio_id=registro.id,
                evento="aprovado",
                usuario_id=plataforma.id,
                criado_em=registro.aprovado_em,
            ),
            RegistroAuditoria(
                condominio_id=registro.id,
                usuario_id=plataforma.id,
                perfil="plataforma",
                acao="condominio.aprovar",
                recurso_tipo="condominio",
                recurso_id=registro.id,
                antes={"status": "pendente"},
                depois={"status": "ativo"},
                criado_em=registro.aprovado_em,
            ),
        ]
    )


def _arquivo_demo(carga: _Carga, estado: _Condominio, modulo: str, autor: Usuario) -> Arquivo:
    registro = Arquivo(
        id=_id_demo(estado.chave, modulo),
        condominio_id=estado.cid,
        chave_storage=_chave_imagem(estado.chave, modulo),
        nome_original=IMAGENS[modulo],
        tipo_mime=MIME_IMAGEM,
        tamanho_bytes=len(_imagem(modulo)),
        enviado_por_usuario_id=autor.id,
    )
    carga.session.add(registro)
    carga.session.flush()
    return registro


# Encomendas: (morador, descrição, transportadora, dias atrás, etapa 0-2)
ENCOMENDAS = {
    "aurora": (
        ("morador.aurora", "Caixa de livros", "Correios", 1, 0),
        ("morador.aurora", "Pacote de papelaria", "Transportes Demo", 2, 1),
        ("morador.aurora", "Envelope de documentos", "Correios", 6, 2),
        ("morador.aurora.a102", "Kit de panelas", "Entrega Rápida", 2, 0),
        ("morador.aurora.a102", "Caixa de sapatos", "Transportes Demo", 8, 2),
        ("morador.aurora.a201", "Medicamentos da farmácia", "Moto Entregas", 1, 0),
        ("morador.aurora.a201", "Livro de receitas", "Correios", 4, 2),
        ("morador.aurora.b101", "Peças de bicicleta", "Entrega Rápida", 3, 1),
        ("morador.aurora.b302", "Fones de ouvido", "Transportes Demo", 5, 2),
    ),
    "horizonte": (
        ("morador.horizonte", "Caixa de ferramentas", "Correios", 1, 0),
        ("morador.horizonte", "Pacote de roupas", "Transportes Demo", 2, 1),
        ("morador.horizonte.t101", "Cafeteira", "Entrega Rápida", 5, 2),
    ),
}
ESTADOS_ENCOMENDA = (
    "aguardando_retirada",
    "entregue_aguardando_confirmacao",
    "retirada_confirmada",
)


def _encomendas(carga: _Carga, estado: _Condominio, foto: Arquivo) -> None:
    porteiro = estado.funcionarios[0]
    for posicao, (login, descricao, transportadora, dias, etapa) in enumerate(
        ENCOMENDAS[estado.chave]
    ):
        morador, moradia, unidade = estado.de(login)
        registrada = carga.momento(-dias, 9 + posicao % 8, 15)
        carga.session.add(
            Encomenda(
                condominio_id=estado.cid,
                unidade_id=unidade.id,
                destinatario_morador_unidade_id=moradia.id,
                descricao=descricao,
                transportadora=transportadora,
                foto_nota_arquivo_id=foto.id,
                recebido_por_funcionario_id=porteiro.id,
                status=ESTADOS_ENCOMENDA[etapa],
                registrada_em=registrada,
                entregue_em=registrada + timedelta(hours=3) if etapa else None,
                recebedor_morador_unidade_id=moradia.id if etapa else None,
                entregue_por_funcionario_id=porteiro.id if etapa else None,
                confirmada_em=registrada + timedelta(hours=4) if etapa == 2 else None,
                confirmado_por_usuario_id=morador.id if etapa == 2 else None,
            )
        )


# Visitantes: (morador, nome, início, fim, situação) com dias relativos a hoje.
# Situação: "no_predio" (entrada sem saída), "saiu" (entrada e saída) ou "agendado".
VISITANTES = {
    "aurora": (
        ("morador.aurora", "Visitante Demo", -1, 3, "no_predio"),
        ("morador.aurora", "Juliana Costa", 2, 2, "agendado"),
        ("morador.aurora.a102", "Rafael Alves", -2, -2, "saiu"),
        ("morador.aurora.b101", "Luísa Prado", 0, 1, "agendado"),
    ),
    "horizonte": (("morador.horizonte", "Visitante Demo", -1, 3, "no_predio"),),
}


def _visitantes(carga: _Carga, estado: _Condominio) -> None:
    session = carga.session
    porteiro = estado.funcionarios[0]
    for login, nome, inicio, fim, situacao in VISITANTES[estado.chave]:
        morador, moradia, unidade = estado.de(login)
        visitante = Visitante(
            condominio_id=estado.cid,
            unidade_id=unidade.id,
            nome=nome,
            entrada_prevista=carga.hoje + timedelta(days=inicio),
            saida_prevista=carga.hoje + timedelta(days=fim),
            cadastrado_por_usuario_id=morador.id,
            criado_em=carga.momento(min(inicio, 0) - 1, 18),
        )
        session.add(visitante)
        session.flush()
        if situacao == "agendado":
            continue
        autorizacao = Autorizacao(
            id=visitante.id,
            visitante_id=visitante.id,
            unidade_id=unidade.id,
            autorizado_por=Referencia(id=moradia.id, nome=morador.nome),
            inicio=inicio_do_slot(visitante.entrada_prevista, time.min),
            fim=inicio_do_slot(visitante.saida_prevista + timedelta(days=1), time.min),
        )
        entrada = carga.momento(inicio, 14)
        session.add(
            RegistroVisita(
                condominio_id=estado.cid,
                visitante_id=visitante.id,
                entrada_em=entrada,
                entrada_por_funcionario_id=porteiro.id,
                saida_em=entrada + timedelta(hours=2) if situacao == "saiu" else None,
                saida_por_funcionario_id=porteiro.id if situacao == "saiu" else None,
                evidencia={"autorizacao": autorizacao.model_dump(mode="json")},
            )
        )


VEICULOS = {
    "aurora": (
        ("morador.aurora", None, "Marca Demo", "Compacto Demo", "Azul"),
        ("morador.aurora.a102", "BRA2E19", "Marca Demo", "Sedã Demo", "Prata"),
        ("morador.aurora.a201", "QWE4R56", "Marca Demo", "Hatch Demo", "Vermelho"),
        # Mesma placa em outra unidade: aparece no relatório de placas duplicadas (US-506).
        ("morador.aurora.b101", "BRA2E19", "Marca Demo", "Sedã Demo", "Prata"),
    ),
    "horizonte": (
        ("morador.horizonte", None, "Marca Demo", "Compacto Demo", "Branco"),
        ("morador.horizonte.t101", "HZN3C45", "Marca Demo", "Utilitário Demo", "Preto"),
    ),
}


def _veiculos(carga: _Carga, estado: _Condominio, placa_principal: str) -> None:
    for login, placa, marca, modelo, cor in VEICULOS[estado.chave]:
        _, _, unidade = estado.de(login)
        carga.session.add(
            Veiculo(
                condominio_id=estado.cid,
                unidade_id=unidade.id,
                placa=placa or placa_principal,
                marca=marca,
                modelo=modelo,
                cor=cor,
            )
        )


def _areas(carga: _Carga, estado: _Condominio, cenario: CenarioDemo, foto: Arquivo) -> None:
    estado.areas = [
        AreaComum(
            condominio_id=estado.cid,
            nome=nome,
            foto_arquivo_id=foto.id,
            regras=regras,
            abre_as=time(abre),
            fecha_as=time(fecha),
            capacidade=capacidade,
        )
        for nome, abre, fecha, capacidade, regras in cenario.areas
    ]
    carga.session.add_all(estado.areas)
    carga.session.flush()


# Reservas: (morador, índice da área, dias, hora, situação)
# Situação: "ativa", "cancelada_morador" ou "cancelada_adm".
RESERVAS = {
    "aurora": (
        ("morador.aurora", 0, 2, 15, "ativa"),
        ("morador.aurora", 0, 1, 10, "cancelada_morador"),
        ("morador.aurora", 1, -3, 13, "ativa"),
        ("morador.aurora.a102", 1, 3, 12, "ativa"),
        ("morador.aurora.a102", 0, 4, 18, "cancelada_adm"),
        ("morador.aurora.a201", 0, 5, 19, "ativa"),
        ("morador.aurora.b101", 2, 1, 7, "ativa"),
        ("morador.aurora.b302", 2, 1, 8, "ativa"),
    ),
    "horizonte": (
        ("morador.horizonte", 0, 2, 15, "ativa"),
        ("morador.horizonte", 0, 1, 10, "cancelada_morador"),
        ("morador.horizonte.t101", 1, 3, 9, "ativa"),
    ),
}


def _reservas(carga: _Carga, estado: _Condominio, administracao: Usuario) -> None:
    criado = carga.momento(-5, 20)
    for login, area, dias, hora, situacao in RESERVAS[estado.chave]:
        morador, _, unidade = estado.de(login)
        cancelada = situacao != "ativa"
        pela_adm = situacao == "cancelada_adm"
        carga.session.add(
            Reserva(
                condominio_id=estado.cid,
                area_id=estado.areas[area].id,
                unidade_id=unidade.id,
                usuario_id=morador.id,
                data=carga.hoje + timedelta(days=dias),
                hora_inicio=time(hora),
                status="cancelada" if cancelada else "ativa",
                criado_em=min(criado, carga.momento(dias - 1, 20)),
                cancelada_em=criado + timedelta(days=1) if cancelada else None,
                cancelada_por_usuario_id=(administracao if pela_adm else morador).id
                if cancelada
                else None,
                cancelada_responsavel_id=estado.responsaveis[0].id if pela_adm else None,
                motivo_cancelamento="Manutenção elétrica no salão." if pela_adm else None,
            )
        )


# Ocorrências: (morador, título, detalhe, dias atrás, situação)
# Situação: "aberta", "respondida", "resolvida" ou "reaberta".
OCORRENCIAS = {
    "aurora": (
        (
            "morador.aurora",
            "Portão fecha lentamente",
            "Favor verificar o tempo de fechamento do portão de pedestres.",
            1,
            "respondida",
        ),
        (
            "morador.aurora",
            "Lâmpada do corredor",
            "A iluminação do corredor do 1º andar falha ao anoitecer.",
            6,
            "resolvida",
        ),
        (
            "morador.aurora.a102",
            "Barulho após as 22h",
            "Música alta vinda do Bloco B depois do horário de silêncio.",
            2,
            "aberta",
        ),
        (
            "morador.aurora.a201",
            "Vazamento na garagem",
            "Há uma poça constante perto da vaga 12.",
            5,
            "reaberta",
        ),
    ),
    "horizonte": (
        (
            "morador.horizonte",
            "Interfone sem som",
            "O interfone da unidade 202 não recebe chamadas.",
            2,
            "aberta",
        ),
        (
            "morador.horizonte.t101",
            "Lixeira quebrada",
            "A tampa da lixeira do térreo está solta.",
            4,
            "resolvida",
        ),
    ),
}


def _ocorrencias(carga: _Carga, estado: _Condominio, administracao: Usuario) -> None:
    session = carga.session
    responsavel = estado.responsaveis[0]
    for login, titulo, detalhe, dias, situacao in OCORRENCIAS[estado.chave]:
        morador, _, unidade = estado.de(login)
        criada = carga.momento(-dias, 8)
        resolvida = situacao == "resolvida"
        ocorrencia = Ocorrencia(
            condominio_id=estado.cid,
            unidade_id=unidade.id,
            aberta_por_usuario_id=morador.id,
            titulo=titulo,
            detalhe=detalhe,
            status="resolvida" if resolvida else "em_aberto",
            criado_em=criada,
            resolvida_em=criada + timedelta(hours=6) if resolvida else None,
        )
        session.add(ocorrencia)
        session.flush()

        interacoes: list[tuple[str, str, int, Usuario]] = []
        if situacao in {"respondida", "reaberta"}:
            interacoes.append(
                ("resposta", "Recebemos o chamado e acionamos a manutenção.", 2, administracao)
            )
        if situacao in {"resolvida", "reaberta"}:
            interacoes.append(
                ("resolucao", "Serviço concluído pela equipe de manutenção.", 6, administracao)
            )
        if situacao == "reaberta":
            interacoes.append(
                ("reabertura", "O problema voltou a acontecer hoje cedo.", 30, morador)
            )
        session.add_all(
            OcorrenciaInteracao(
                condominio_id=estado.cid,
                ocorrencia_id=ocorrencia.id,
                tipo=tipo,
                texto=texto,
                usuario_id=autor.id,
                responsavel_id=responsavel.id if autor is administracao else None,
                criado_em=criada + timedelta(hours=horas),
            )
            for tipo, texto, horas, autor in interacoes
        )


AVISOS = (
    # (título, texto, importante, início em dias, fim em dias)
    (
        "Manutenção dos elevadores",
        "Os elevadores passarão por manutenção preventiva das 9h às 12h.",
        True,
        -1,
        3,
    ),
    (
        "Coleta seletiva",
        "Separe recicláveis nas lixeiras azuis do térreo. A coleta passa às quintas.",
        False,
        -7,
        30,
    ),
    (
        "Assembleia geral ordinária",
        "A assembleia acontece no salão de festas. A pauta será enviada por e-mail.",
        True,
        5,
        12,
    ),
    ("Dedetização concluída", "A dedetização das áreas comuns foi concluída.", False, -20, -10),
)


def _avisos(carga: _Carga, estado: _Condominio) -> None:
    for titulo, texto, importante, inicio, fim in AVISOS:
        carga.session.add(
            Aviso(
                condominio_id=estado.cid,
                titulo=titulo,
                texto=texto,
                importante=importante,
                inicio_em=carga.momento(inicio, 0),
                fim_em=carga.momento(fim, 23, 59),
                responsavel_id=estado.responsaveis[0].id,
                criado_em=carga.momento(min(inicio, 0) - 1, 17),
            )
        )


def _suporte(
    carga: _Carga, estado: _Condominio, administracao: Usuario, plataforma: Usuario
) -> None:
    session = carga.session
    chamados = (
        ("Dúvida sobre relatório de encomendas", "Como exportar o relatório do mês?", "aberto"),
        (
            "Morador sem acesso às reservas",
            "Um morador do Bloco B informa que não vê a aba de reservas.",
            "em_atendimento",
        ),
        ("Troca do logotipo", "Gostaríamos de atualizar o logotipo do condomínio.", "encerrado"),
    )
    for posicao, (titulo, descricao, status) in enumerate(chamados):
        if estado.chave != "aurora" and posicao:
            break
        aberto = carga.momento(-(posicao * 3 + 1), 11)
        chamado = Chamado(
            condominio_id=estado.cid,
            titulo=titulo,
            descricao=descricao,
            status=status,
            aberto_por_usuario_id=administracao.id,
            atendido_por_usuario_id=plataforma.id if status != "aberto" else None,
            criado_em=aberto,
            encerrado_em=aberto + timedelta(days=1) if status == "encerrado" else None,
        )
        session.add(chamado)
        session.flush()
        if status != "aberto":
            session.add_all(
                [
                    ChamadoMensagem(
                        condominio_id=estado.cid,
                        chamado_id=chamado.id,
                        autor_usuario_id=plataforma.id,
                        texto="Olá! Estamos verificando e retornamos em breve.",
                        criado_em=aberto + timedelta(hours=2),
                    ),
                    ChamadoMensagem(
                        condominio_id=estado.cid,
                        chamado_id=chamado.id,
                        autor_usuario_id=administracao.id,
                        texto="Obrigado, fico no aguardo.",
                        criado_em=aberto + timedelta(hours=3),
                    ),
                ]
            )


def _comunicados(carga: _Carga, plataforma: Usuario, ativos: list[_Condominio]) -> None:
    session = carga.session
    for dias, titulo, texto in (
        (
            -10,
            "Bem-vindos à plataforma",
            "Este canal reúne novidades e orientações para as Administrações.",
        ),
        (
            -2,
            "Nova tela de auditoria",
            "As ações registradas agora podem ser consultadas pela equipe da plataforma.",
        ),
    ):
        comunicado = Comunicado(
            titulo=titulo,
            texto=texto,
            enviado_por_usuario_id=plataforma.id,
            criado_em=carga.momento(dias, 10),
        )
        session.add(comunicado)
        session.flush()
        session.add_all(
            ComunicadoDestinatario(comunicado_id=comunicado.id, condominio_id=estado.cid)
            for estado in ativos
        )


def _auditoria_operacional(carga: _Carga, estado: _Condominio, administracao: Usuario) -> None:
    """Alguns eventos recentes, para a tela de auditoria não mostrar só aprovações."""
    responsavel = estado.responsaveis[0]
    eventos = (
        (-3, administracao, "administracao", "funcionario.cadastrar", "funcionario"),
        (-2, estado.portaria or administracao, "funcionario", "encomenda.receber", "encomenda"),
        (-1, administracao, "administracao", "reserva.cancelar", "reserva"),
        (-1, administracao, "administracao", "ocorrencia.resolver", "ocorrencia"),
    )
    carga.session.add_all(
        RegistroAuditoria(
            condominio_id=estado.cid,
            usuario_id=usuario.id,
            responsavel_nome=responsavel.nome if perfil == "administracao" else "Porteiro Demo",
            perfil=perfil,
            acao=acao,
            recurso_tipo=recurso,
            criado_em=carga.momento(dias, 16),
        )
        for dias, usuario, perfil, acao, recurso in eventos
    )


def seed_demo(session: Session, *, hoje: date) -> DemoSeedSummary:
    """Limpa e carrega a massa em uma única transação PostgreSQL."""
    with session.begin():
        preparador = session.get_bind().dialect.identifier_preparer
        tabelas = ", ".join(
            preparador.format_table(tabela) for tabela in Base.metadata.tables.values()
        )
        # Esta trava é suspensa exclusivamente no reset. O ALTER e o TRUNCATE são
        # transacionais e o lock exclusivo impede que outra sessão veja a suspensão.
        auditoria = "ALTER TABLE registros_auditoria"
        trigger = "TRIGGER registros_auditoria_somente_insercao"
        session.execute(text(f"{auditoria} DISABLE {trigger}"))
        # Sem CASCADE: uma dependência inesperada interrompe o reset.
        session.execute(text(f"TRUNCATE TABLE {tabelas} RESTART IDENTITY"))
        session.execute(text(f"{auditoria} ENABLE {trigger}"))

        # Um único hash para todas as contas: a senha é a mesma e o hash é lento de propósito.
        carga = _Carga(session=session, hoje=hoje, senha_hash=hash_senha(SENHA_DEMO))
        plataforma = carga.conta("plataforma", "ADM Demo", plataforma=True)
        administracao = carga.conta("administracao", "Administração Demo", tipo="administracao")
        session.flush()

        ativos: list[_Condominio] = []
        for chave, cenario in CENARIOS.items():
            estado = _condominio(
                carga, chave, cenario, dono=administracao, plataforma=plataforma, status="ativo"
            )
            ativos.append(estado)
            _encomendas(carga, estado, _arquivo_demo(carga, estado, "encomendas", administracao))
            _visitantes(carga, estado)
            _veiculos(carga, estado, cenario.placa)
            _areas(carga, estado, cenario, _arquivo_demo(carga, estado, "fotos", administracao))
            _reservas(carga, estado, administracao)
            _ocorrencias(carga, estado, administracao)
            _avisos(carga, estado)
            _suporte(carga, estado, administracao, plataforma)
            _auditoria_operacional(carga, estado, administracao)
        _comunicados(carga, plataforma, ativos)

        # Condomínio aguardando análise: o ADM aprova ao vivo e as chaves são geradas.
        dono_pendente = carga.conta(
            "administracao.vistaverde", "Administração Vista Verde", tipo="administracao"
        )
        session.flush()
        _condominio(
            carga,
            "vistaverde",
            PENDENTE,
            dono=dono_pendente,
            plataforma=plataforma,
            status="pendente",
        )
    return DemoSeedSummary(condominios=len(CENARIOS) + 1, contas=carga.contas)


def _validar_configuracao(settings: Settings) -> None:
    if (
        settings.app_env != "development"
        or settings.compose_demo_app_env != "development"
        or not settings.demo_seed_allowed
        or settings.postgres_host != "db"
        or settings.postgres_port != 5432
        or settings.postgres_db != "condominios"
        or (settings.database_url and settings.database_url.get_secret_value())
        or settings.compose_demo_database_url.get_secret_value()
        or settings.storage_endpoint != "http://storage:9000"
    ):
        raise ValueError(
            "Reset recusado: use o serviço demo-seed com banco db:5432/condominios e MinIO locais."
        )


def run() -> int:
    try:
        settings = get_settings()
        _validar_configuracao(settings)
    except (ValidationError, SettingsError):
        print("Reset recusado: configuração inválida.", file=sys.stderr)
        return 1
    except ValueError as erro:
        print(erro, file=sys.stderr)
        return 1

    factory = get_session_factory()
    with factory() as sessao, sessao.begin():
        conexao = sessao.connection()
        if conexao.execute(
            text("SELECT current_database(), current_schema(), inet_server_port()")
        ).one() != ("condominios", "public", 5432):
            print("Reset recusado: identidade do banco conectado inesperada.", file=sys.stderr)
            return 1
        # Serializa inclusive dois seeds concorrentes em um volume ainda vazio.
        conexao.execute(text("SELECT pg_advisory_xact_lock(66, 20261126)"))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = conexao
        command.upgrade(config, "head")
        _carregar_imagens(S3Adapter(settings))
        with factory(bind=conexao) as carga:
            resumo = seed_demo(carga, hoje=agora().date())

    print(f"Demo pronta: {resumo.condominios} condomínios e {resumo.contas} contas locais.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
