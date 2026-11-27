/**
 * Nomes legíveis da auditoria. O banco e a API continuam usando os códigos `grupo.verbo`
 * (contrato da auditoria); a tela só traduz o que mostra ao ADM da plataforma.
 */

/** Grupos de ação, na ordem em que aparecem no filtro. */
export const auditGroupLabels: Record<string, string> = {
  condominio: 'Condomínios',
  estrutura: 'Estrutura',
  chave: 'Chaves de acesso',
  vinculo: 'Vínculos de moradores',
  permissao_aba: 'Permissões',
  proprietario: 'Proprietários',
  conta: 'Contas',
  conta_compartilhada: 'Conta de funcionários',
  responsaveis: 'Responsáveis',
  funcionario: 'Funcionários',
  aviso: 'Avisos',
  comunicado: 'Comunicados',
  chamado: 'Suporte',
  area: 'Áreas comuns',
  reserva: 'Reservas',
  ocorrencia: 'Ocorrências',
  encomenda: 'Encomendas',
  visitante: 'Visitantes',
  visita: 'Visitas',
  veiculo: 'Veículos',
  seguranca: 'Segurança',
}

export const auditActionLabels: Record<string, string> = {
  'condominio.enviar': 'Cadastro de condomínio enviado',
  'condominio.reenviar': 'Cadastro de condomínio reenviado',
  'condominio.aprovar': 'Condomínio aprovado',
  'condominio.rejeitar': 'Condomínio rejeitado',
  'condominio.editar': 'Dados do condomínio editados',
  'condominio.desativar': 'Condomínio desativado',
  'condominio.reativar': 'Condomínio reativado',
  'estrutura.editar': 'Estrutura editada',
  'chave.gerar': 'Chave de acesso gerada',
  'chave.regenerar': 'Chave de acesso regenerada',
  'chave.revogar': 'Chave de acesso revogada',
  'vinculo.aprovar': 'Vínculo de morador aprovado',
  'vinculo.desfazer': 'Morador desvinculado',
  'permissao_aba.alterar': 'Permissões de abas alteradas',
  'proprietario.editar': 'Proprietário editado',
  'conta.criar': 'Conta criada',
  'conta.editar': 'Perfil editado',
  'conta.senha_alterar': 'Senha alterada',
  'conta.senha_recuperacao_solicitar': 'Recuperação de senha solicitada',
  'conta.senha_redefinir': 'Senha redefinida',
  'conta_compartilhada.trocar_acesso': 'Acesso da conta de funcionários alterado',
  'responsaveis.alterar': 'Responsáveis alterados',
  'funcionario.cadastrar': 'Funcionário cadastrado',
  'funcionario.editar': 'Funcionário editado',
  'funcionario.desativar': 'Funcionário desligado',
  'aviso.publicar': 'Aviso publicado',
  'aviso.editar': 'Aviso editado',
  'aviso.encerrar': 'Aviso encerrado',
  'comunicado.enviar': 'Comunicado enviado',
  'chamado.atender': 'Chamado em atendimento',
  'chamado.encerrar': 'Chamado encerrado',
  'area.bloquear': 'Área comum bloqueada',
  'area.desbloquear': 'Área comum desbloqueada',
  'reserva.criar': 'Reserva criada',
  'reserva.cancelar': 'Reserva cancelada',
  'ocorrencia.resolver': 'Ocorrência resolvida',
  'ocorrencia.reabrir': 'Ocorrência reaberta',
  'encomenda.receber': 'Encomenda recebida',
  'encomenda.entregar': 'Encomenda entregue',
  'encomenda.confirmar': 'Retirada de encomenda confirmada',
  'visitante.criar': 'Visitante cadastrado',
  'visitante.editar': 'Visitante editado',
  'visitante.cancelar': 'Visitante cancelado',
  'visitante.cadastrar_avulso': 'Visitante avulso cadastrado',
  'visita.entrar': 'Entrada de visitante',
  'visita.sair': 'Saída de visitante',
  'visita.registrar_contato': 'Contato com morador registrado',
  'veiculo.criar': 'Veículo cadastrado',
  'veiculo.editar': 'Veículo editado',
  'veiculo.remover': 'Veículo removido',
  'seguranca.login': 'Login',
  'seguranca.login_falho': 'Login recusado',
  'seguranca.login_bloqueado': 'Login bloqueado por excesso de tentativas',
  'seguranca.chave_invalida': 'Chave de acesso inválida informada',
  'seguranca.acesso_cross_tenant': 'Tentativa de acesso a outro condomínio',
  'seguranca.acesso_negado': 'Acesso negado',
}

export const auditResourceLabels: Record<string, string> = {
  condominio: 'Condomínio',
  bloco: 'Bloco',
  andar: 'Andar',
  unidade: 'Unidade',
  morador_unidade: 'Morador da unidade',
  usuario: 'Conta de usuário',
  responsavel_administracao: 'Responsável da administração',
  funcionario: 'Funcionário',
  aviso: 'Aviso',
  comunicado: 'Comunicado',
  chamado: 'Chamado de suporte',
  area_comum: 'Área comum',
  reserva: 'Reserva',
  ocorrencia: 'Ocorrência',
  encomenda: 'Encomenda',
  visitante: 'Visitante',
  visita: 'Visita',
  contato_portaria: 'Contato da portaria',
  veiculo: 'Veículo',
}

/** Nome legível da ação; um código novo, sem tradução, aparece como veio. */
export function auditActionLabel(code: string) {
  return auditActionLabels[code] ?? code
}

export function auditResourceLabel(code: string) {
  return auditResourceLabels[code] ?? code
}

/** Opções do filtro "Ação": cada grupo traz "todas" (prefixo `grupo.`) e depois cada ação. */
export function auditActionOptions() {
  return Object.entries(auditGroupLabels).flatMap(([group, groupLabel]) => [
    { value: `${group}.`, label: `${groupLabel} — todas` },
    ...Object.entries(auditActionLabels)
      .filter(([code]) => code.startsWith(`${group}.`))
      .map(([code, label]) => ({ value: code, label: `· ${label}` })),
  ])
}

export function auditResourceOptions() {
  return Object.entries(auditResourceLabels)
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'))
}
