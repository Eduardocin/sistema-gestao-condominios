/**
 * Mensagem de sucesso que precisa sobreviver a uma remontagem da tela. Depois de salvar,
 * `client.restore()` renova a sessão e a página é montada de novo: o estado local se perde,
 * mas a mensagem não. `sessionStorage` pode estar indisponível, e a mensagem então só não aparece.
 */
export function saveFlash(key: string, message: string): void {
  try {
    sessionStorage.setItem(key, message)
  } catch {
    /* O que o usuário salvou já foi gravado; só a mensagem se perde. */
  }
}

/** Lê e apaga a mensagem guardada. Devolve '' quando não há nenhuma. */
export function takeFlash(key: string): string {
  try {
    const message = sessionStorage.getItem(key) ?? ''
    sessionStorage.removeItem(key)
    return message
  } catch {
    return ''
  }
}
