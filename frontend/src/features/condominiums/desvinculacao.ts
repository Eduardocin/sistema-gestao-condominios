// Desvinculação de morador (US-305): caminho da rota e mensagens de erro.
// Funções puras, sem axios, para serem testadas direto no Node.

export function desvinculacaoPath(unidadeId: string, moradorUnidadeId: string): string {
  return `/unidades/${encodeURIComponent(unidadeId)}/moradores/${encodeURIComponent(moradorUnidadeId)}/desvinculacao`
}

export interface ApiFailure {
  status?: number
  reason?: string
}

const GENERIC = 'Não foi possível desvincular agora. Tente novamente.'

/** Traduz a resposta da API em texto para a tela. Nunca devolve o texto cru do servidor. */
export function desvinculacaoErrorMessage({ status, reason }: ApiFailure): string {
  if (status === 409 && reason === 'ultimo_usuarios') {
    return 'Esta unidade precisa manter ao menos um morador com acesso a Usuários. Transfira essa permissão antes de desvincular.'
  }
  if (status === 403) return 'Você não pode desvincular a si mesmo nem moradores sem ter acesso a Usuários.'
  if (status === 404) return 'Este morador já foi desvinculado ou não pertence mais a esta unidade.'
  return GENERIC
}

export function desvinculacaoSuccessMessage(nome: string, chaveRevogada: boolean): string {
  const base = `${nome} foi desvinculado(a) da unidade.`
  return chaveRevogada
    ? `${base} A chave de acesso da unidade foi revogada; peça à Administração para gerar outra.`
    : base
}
