# Regras de negócio

Status: proposta para a reunião do grupo (TASK-7). Consolida numa página as regras que hoje estão espalhadas pelas user stories, pela [matriz de permissões](../permissoes-e-multitenant.md), pelo [modelo de dados](../modelo-de-dados.md) e pelos contratos de API.

Documentos irmãos: [escopo do MVP](escopo-mvp.md) e [glossário](glossario.md).

## Como ler

Cada regra tem um código `RN-xx` para ser citada em tasks, PRs e testes.

- **Garantida por:** onde a regra é obrigada a valer. **Banco** é uma constraint, que vale mesmo se o código errar. **Serviço** é a regra de negócio no backend. **Autorização** é a dependência central de acesso. **Tela** é só apoio visual, nunca a garantia.
- **Situação:** **Documentada** quando já está na matriz, no modelo de dados ou no fluxo da portaria, que estão no repositório. **Proposta** quando vem de um contrato de API ainda em revisão ou de uma decisão que o grupo precisa confirmar (ver o [escopo](escopo-mvp.md), seção 5).

## 1. Isolamento e acesso

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-01 | O condomínio de uma requisição vem do token. O cliente nunca informa `condominio_id` em rotas do dia a dia; se enviar, o campo é rejeitado ou ignorado, nunca usado. | Autorização | Documentada |
| RN-02 | Recurso de outro condomínio, ou de outra unidade do morador, responde 404, igual a um recurso que não existe. Nunca 403, para não revelar que existe. | Autorização e serviço | Documentada |
| RN-03 | Toda tabela de negócio tem `condominio_id`, e as referências entre tabelas conferem o mesmo condomínio. | Banco | Documentada |
| RN-04 | Perfil, unidades e permissões por aba são lidos do banco a cada requisição, para desvincular um morador ou mudar uma aba valer na hora. | Autorização | Documentada |
| RN-05 | Condomínio que não está `ativo` (pendente, rejeitado ou desativado) só aceita o fluxo de cadastro: a Administração vê e corrige o cadastro. As demais rotas respondem 403. | Autorização | Documentada |
| RN-06 | O ADM não acessa o dia a dia de nenhum condomínio: encomendas, visitantes, ocorrências, reservas e avisos. | Autorização | Documentada |
| RN-07 | Só as rotas de plataforma recebem um ID de condomínio na URL, e só para o ADM. | Autorização | Documentada |
| RN-08 | A unidade usada por um morador vem do vínculo dele, nunca só do cliente: unidade que não é dele responde 404. | Autorização | Documentada |
| RN-09 | Aba do morador em Sem Acesso responde 403 no servidor, mesmo que a tela seja burlada. | Autorização | Documentada |
| RN-10 | Nenhum perfil apaga registro de forma definitiva. Desativa, cancela, resolve ou desvincula. | Serviço | Documentada |
| RN-11 | Perfil local (morador, funcionário, administração) e perfil de plataforma (ADM) são separados: o ADM nunca tem vínculo com condomínio. | Banco | Documentada |

## 2. Contas e login

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-12 | Morador e Administração se autocadastram em telas separadas. Funcionário e ADM não se autocadastram. | Serviço | Documentada |
| RN-13 | O login é por e-mail ou telefone. O e-mail é guardado em minúsculas; telefone, CPF e CNPJ, só com dígitos. | Serviço e banco | Documentada |
| RN-14 | E-mail, telefone e documento (CPF ou CNPJ) de uma conta são únicos. | Banco | Documentada |
| RN-15 | A senha é guardada só como hash, nunca em texto, e nunca aparece em resposta nem em log. | Serviço | Documentada |
| RN-16 | A mensagem de erro de login é a mesma para e-mail inexistente e senha errada. | Serviço | Proposta |
| RN-17 | Funcionários e Administração usam **uma conta compartilhada por condomínio**. Trocar o acesso dela incrementa a versão da sessão e derruba as sessões abertas. | Serviço | Documentada |
| RN-18 | Os nomes de funcionários e de responsáveis da Administração são cadastrados pela Administração e não fazem login. | Serviço | Documentada |
| RN-19 | Recuperar senha é só por e-mail, sempre responde "enviado", exista ou não a conta, e o link vale uma vez. | Serviço | Proposta |

## 3. Condomínio e estrutura

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-20 | O condomínio nasce `pendente` quando a Administração envia o cadastro. Não existe rascunho. | Serviço | Proposta |
| RN-21 | Só o ADM aprova ou rejeita, e só um condomínio `pendente`. Rejeitar exige motivo, e a Administração consegue ler o motivo. | Serviço e banco | Documentada |
| RN-22 | Condomínio `rejeitado` pode ser corrigido e reenviado. O motivo anterior continua no histórico de análises. | Serviço | Documentada |
| RN-23 | Aprovar gera uma chave de acesso para cada unidade ativa, numa só transação. Se qualquer passo falhar, nada é gravado. | Serviço | Documentada |
| RN-24 | O CNPJ do condomínio é único. | Banco | Documentada |
| RN-25 | O assistente de cadastro envia o prédio inteiro e grava tudo ou nada. Estrutura inválida em qualquer ponto não grava nem o condomínio. | Serviço | Proposta |
| RN-26 | Nomes não se repetem: bloco único no condomínio, andar único no bloco, unidade única no andar. | Banco | Documentada |
| RN-27 | Unidade com morador vinculado não pode ser removida. | Serviço | Documentada |
| RN-28 | Desativar um condomínio vale na hora: as rotas do dia a dia passam a responder 403. | Autorização | Documentada |

## 4. Chaves de acesso e vínculo

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-29 | Cada unidade tem no máximo uma chave vigente, e o código é único em todo o sistema. | Banco | Documentada |
| RN-30 | Regenerar uma chave invalida a anterior na hora, na mesma transação. Revogar deixa a unidade sem chave. | Serviço e banco | Documentada |
| RN-31 | A chave só é mostrada à Administração. O morador a digita uma vez e nunca a recebe de volta. | Serviço | Documentada |
| RN-32 | Chave inexistente, revogada ou de condomínio não `ativo` responde com uma mensagem única, sem revelar o motivo. | Serviço | Proposta |
| RN-33 | Depois de 5 tentativas erradas seguidas em 15 minutos, a conta fica 15 minutos sem poder tentar. | Serviço | Proposta |
| RN-34 | Um morador pode se vincular a várias unidades, do mesmo condomínio ou de outros, mas não duas vezes à mesma unidade. | Banco | Documentada |
| RN-35 | A chave válida vincula o morador imediatamente; a Administração corrige depois, desvinculando. | Serviço | Proposta |
| RN-36 | Cada vínculo de morador tem as 7 abas de permissão, criadas junto com o vínculo. | Serviço e banco | Documentada |
| RN-37 | Nunca se pode retirar a aba Usuários de quem é o último a tê-la na unidade. | Serviço | Documentada |
| RN-38 | Permissões iniciais: o primeiro morador da unidade recebe todas as abas; os seguintes, todas menos Usuários. | Serviço | Proposta |
| RN-39 | A Administração não altera permissões por aba. | Autorização | Documentada |
| RN-40 | O morador vê o proprietário da unidade, **sem o documento** (CPF ou CNPJ). Nunca vê dados do proprietário de outra unidade. | Serviço | Proposta |
| RN-41 | O morador não desvincula a si mesmo. Quem desvincula é a Administração, ou outro morador com a aba Usuários. | Autorização | Proposta |
| RN-42 | Ao desvincular, o histórico da unidade (encomendas, reservas, ocorrências) permanece. | Serviço | Proposta |

## 5. Encomendas

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-43 | Só o Funcionário registra uma encomenda, com foto da nota fiscal, unidade de destino e o nome de quem a recebeu, escolhido na lista de funcionários. | Serviço e banco | Documentada |
| RN-44 | A encomenda tem três estados em sequência: `aguardando_retirada`, `entregue_aguardando_confirmacao` e `retirada_confirmada`. Nenhum estado se pula. | Banco | Documentada |
| RN-45 | Cada estado exige todos os seus dados ou nenhum deles; datas e horários são sempre do servidor. | Banco | Documentada |
| RN-46 | Destinatário e recebedor precisam ter vínculo ativo com a unidade da encomenda. O recebedor pode ser outro morador da mesma unidade. | Serviço | Documentada |
| RN-47 | Só o recebedor registrado confirma o recebimento, pela própria conta, com vínculo ativo e a aba Encomendas habilitada. A conta de Funcionários não confirma pelo morador. | Autorização e serviço | Documentada |
| RN-48 | A pendência de confirmação não se encerra sozinha. | Serviço | Documentada |
| RN-49 | Os dados da encomenda não se editam depois do registro; correções ficam na auditoria. | Serviço | Documentada |

## 6. Visitantes e veículos

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-50 | O morador cadastra visitantes e veículos da própria unidade, e só se tiver acesso às abas Visitantes e Veículos. | Autorização | Documentada |
| RN-51 | O cadastro do visitante é uma autorização reutilizável durante o período informado, inclusive o último dia, no fuso do condomínio. Não é de uso único. | Serviço | Documentada |
| RN-52 | A cada entrada, a portaria confere se o cadastro não foi cancelado, se o período está vigente e se o morador autorizador ainda tem vínculo e permissão. Fora do período, consulta-se o morador antes de liberar. | Serviço | Documentada |
| RN-53 | Cada visitante tem no máximo uma visita em aberto; a saída não pode ser anterior à entrada. | Banco | Documentada |
| RN-54 | O período do visitante só vale se a saída prevista não for anterior à entrada prevista. | Banco | Documentada |
| RN-55 | O Funcionário consulta visitantes e veículos, cadastra visitante avulso e registra entrada e saída. | Autorização | Documentada |
| RN-56 | A placa segue o formato brasileiro, antigo ou Mercosul. | Banco | Documentada |
| RN-57 | A placa não se repete na mesma unidade. Entre unidades pode repetir; a US-502 pede só um aviso à Administração, e a forma do aviso está em aberto. | Banco | Documentada |

## 7. Reservas de áreas comuns

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-58 | A reserva é de um horário de **1 hora cheia**, numa data, dentro do funcionamento da área. | Banco e serviço | Documentada |
| RN-59 | Cada unidade tem no máximo **uma reserva ativa por área por dia**. A segunda tentativa é recusada com mensagem que explica a regra. | Banco | Documentada |
| RN-60 | Dois pedidos para o mesmo horário da mesma área gravam só uma reserva. Quem garante é o banco, não uma consulta feita antes do `INSERT`. | Banco e transação | Documentada |
| RN-61 | Não se reserva no passado nem em data bloqueada pela Administração. | Serviço | Proposta |
| RN-62 | Cancelar uma reserva libera o horário na hora e preserva o registro cancelado. O morador cancela as reservas da própria unidade; a matriz diz "só a própria", e a proposta é que valha para qualquer morador da unidade com a aba habilitada. | Banco e autorização | Documentada (quem cancela: proposta) |
| RN-63 | A agenda do morador mostra só livre, ocupado ou da própria unidade. A API nunca revela qual outra unidade reservou. | Serviço | Documentada |
| RN-64 | A Administração cancela qualquer reserva, com motivo e responsável. A unidade afetada recebe um aviso e um e-mail. | Serviço | Documentada |
| RN-65 | Bloquear uma data com reservas existentes exige confirmar o cancelamento delas, e tudo é gravado numa transação só. | Serviço | Proposta |
| RN-66 | O Funcionário não acessa áreas, bloqueios nem reservas. | Autorização | Documentada |

## 8. Ocorrências

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-67 | A ocorrência exige unidade, título e detalhe. Fotos e vídeos são opcionais, com tipo e tamanho validados. | Serviço | Documentada |
| RN-68 | Data e hora são automáticas, do servidor. | Serviço | Documentada |
| RN-69 | A ocorrência tem dois estados: `em_aberto` (vermelho) e `resolvida` (verde). Reabrir é um evento do histórico, e a ocorrência volta a `em_aberto`. | Banco e serviço | Documentada |
| RN-70 | A Administração responde e muda o status. O morador consulta as da sua unidade, responde e reabre. | Autorização | Documentada |
| RN-71 | O Funcionário não acessa ocorrências. | Autorização | Documentada |
| RN-72 | O histórico de respostas não se apaga nem se edita. | Serviço | Proposta |

## 9. Avisos, e-mail e suporte

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-73 | O aviso tem título, texto, início e fim. O período é válido se o fim for depois do início. | Banco | Documentada |
| RN-74 | Moradores e funcionários veem só os avisos vigentes; o importante aparece em laranja. Quem publicou fica registrado. | Serviço | Documentada |
| RN-75 | O aviso de uma unidade não aparece para outra unidade nem para o Funcionário. | Serviço | Proposta |
| RN-76 | O e-mail é enviado em segundo plano nos quatro eventos: recuperação de senha, aprovação do condomínio, encomenda registrada e reserva cancelada. Falha no e-mail nunca desfaz nem bloqueia a operação principal. | Serviço | Documentada |
| RN-77 | Todo envio de e-mail fica registrado e pode ser reenviado pelo ADM, exceto o de recuperação de senha, que exige um novo pedido. | Serviço | Proposta |
| RN-78 | Só o ADM envia comunicados da plataforma; a Administração lê os que foram enviados ao seu condomínio. | Autorização | Documentada |
| RN-79 | A Administração abre chamados de suporte do próprio condomínio; só o ADM os atende. | Autorização | Documentada |

## 10. Auditoria

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-80 | Toda ação crítica gera um registro de auditoria, pelo mecanismo único que todos os módulos chamam. | Serviço | Documentada |
| RN-81 | O registro guarda a conta, o responsável informado, o perfil, o condomínio, a ação, o recurso, os valores antes e depois, o IP e a hora do servidor. | Serviço | Documentada |
| RN-82 | A auditoria é de apenas inserção: nem a aplicação nem o banco aceitam editar ou apagar. | Banco | Documentada |
| RN-83 | Nas ações da Administração, o responsável é obrigatório e precisa pertencer ao condomínio do token. | Serviço | Documentada |
| RN-84 | Senhas, tokens e códigos de chave nunca são gravados na auditoria; documentos aparecem mascarados. | Serviço | Proposta |
| RN-85 | Login falho, acesso negado e tentativa de acessar outro condomínio geram evento de segurança, mesmo quando a requisição é desfeita. | Serviço | Documentada |
| RN-86 | Só o ADM consulta a auditoria. | Autorização | Documentada |

## 11. Regras gerais

| Código | Regra | Garantida por | Situação |
| --- | --- | --- | --- |
| RN-87 | Datas e horas de registro são sempre geradas pelo servidor. | Serviço | Documentada |
| RN-88 | Datas e horários de negócio (reserva, período de visitante, vigência de aviso) valem no fuso do condomínio, fixado em America/Sao_Paulo no MVP. | Serviço | Proposta |
| RN-89 | Fotos, vídeos e documentos ficam fora do banco; o sistema guarda só a referência. | Serviço | Documentada |
| RN-90 | Erros usam o formato `{"error": {"code": "...", "message": "..."}}`, com mensagens que não revelam recurso, condomínio ou unidade de terceiros. | Serviço | Documentada |

## 12. Pontos que dependem de decisão do grupo

Estas regras são marcadas como **Proposta** porque a documentação ainda não resolveu uma divergência entre as fontes:

| Regras | Dúvida | Quem decide |
| --- | --- | --- |
| RN-35 | A matriz e o modelo de dados preveem solicitar, aprovar e rejeitar vínculo; a US-301 diz que a chave válida já vincula. A proposta segue a story. | Paulo e Gabriel |
| RN-38 e RN-40 | Permissões iniciais e quais dados do proprietário o morador vê. | Paulo e Gabriel |
| RN-62 | A US-604 fala em cancelar "reservas da unidade"; a matriz fala em cancelar "só a própria". A proposta é que qualquer morador da unidade com a aba habilitada cancele as da unidade. | Gabriel e Vitor |
| RN-33 e RN-16 | Limite de tentativas de login e de chave não está nas stories. | Gabriel |
| RN-88 | O banco não guarda o fuso do condomínio. | Davi e Gabriel |

## 13. Como manter esta página

- Regra nova ou alterada entra aqui no mesmo PR que muda o comportamento, com o próximo código `RN-xx` livre. Códigos não são reaproveitados.
- Regra que muda de **Proposta** para **Documentada** só muda a coluna "Situação" depois que o PR que a documenta for aprovado.
- Toda regra com "Garantida por: Banco" deve ter uma constraint correspondente no modelo de dados e um teste.
