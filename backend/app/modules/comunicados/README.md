# Comunicados (US-804)

Contrato: [plataforma.md](../../../../docs/api-contracts/plataforma.md), seção 2. Os models (`Comunicado`, `ComunicadoDestinatario`) ficam em `app/modules/avisos/models.py`.

| Rota | Quem |
| --- | --- |
| `POST /plataforma/comunicados`, `GET /plataforma/comunicados`, `GET /plataforma/comunicados/{id}` | ADM da plataforma |
| `GET /comunicados` | Administração: só o que foi enviado ao seu condomínio |

- **Envio.** Numa transação: trava os condomínios `ativo` (`FOR SHARE`), grava o comunicado e uma linha de `comunicado_destinatarios` por condomínio, e audita `comunicado.enviar`.
- **Isolamento.** Condomínio criado ou aprovado depois do envio não vê comunicados antigos; a Administração não vê quais outros condomínios receberam.
- **Pendente.** `D` em comunicados (a matriz dá ao ADM, mas não há coluna de desativação) e a aprovação da tabela de destinatários pelo Davi e pela Tude.
- **Testes.** `tests/comunicados/`.
