# Suporte (chamados, US-901 e US-902)

Contrato: [plataforma.md](../../../../docs/api-contracts/plataforma.md), seção 3.

| Rota | Quem |
| --- | --- |
| `POST /chamados`, `GET /chamados`, `GET /chamados/{id}`, `POST /chamados/{id}/mensagens` | Administração, só o próprio condomínio |
| `GET /plataforma/chamados`, `GET /plataforma/chamados/{id}`, `POST .../mensagens`, `POST .../encerramento` | ADM da plataforma |

- **Repositório.** `RepositorioChamados(session, condominio_id)`: o `condominio_id` é obrigatório para a Administração (vem do token) e `None` só para o ADM. É a única classe do módulo que fala com o banco.
- **Transições.** `aberto` -> `em_atendimento` na primeira mensagem do ADM; `aberto` ou `em_atendimento` -> `encerrado` pelo ADM. A linha é travada (`FOR UPDATE`) nas duas. Mensagem em chamado encerrado: 409 `chamado_encerrado`.
- **Auditoria.** `chamado.atender` e `chamado.encerrar`, perfil `plataforma`.
- **Anexos.** Módulo `suporte` do storage, mesmo condomínio, enviados por quem abre.
- **Testes.** `tests/suporte/`.
