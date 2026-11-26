import axios from 'axios'

export const passwordHint = 'De 8 a 128 caracteres, com pelo menos uma letra e um número.'

/** Regra da senha nova, a mesma do cadastro (nucleo.md, 3.1). Devolve a mensagem ou ''. */
export function passwordRuleError(next: string, confirmation: string, email?: string) {
  if (next.length < 8 || next.length > 128) return 'A senha deve ter de 8 a 128 caracteres.'
  if (!/\p{L}/u.test(next) || !/\p{N}/u.test(next))
    return 'A senha deve ter pelo menos uma letra e um número.'
  if (email && next.trim().toLowerCase() === email.trim().toLowerCase())
    return 'Escolha uma senha diferente do e-mail.'
  if (next !== confirmation) return 'As senhas devem ser iguais.'
  return ''
}

function responseOf(error: unknown) {
  if (!axios.isAxiosError<{ error?: { message?: string; reason?: string } }>(error))
    return undefined
  return error.response
}

const generic = 'Não foi possível concluir a operação. Tente novamente.'
const tooMany = 'Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.'

export function changePasswordError(error: unknown) {
  const response = responseOf(error)
  const reason = response?.data?.error?.reason
  if (response?.status === 429) return tooMany
  if (response?.status === 403)
    return 'Esta conta não pode trocar a senha por aqui. Fale com a Administração.'
  if (reason === 'senha_atual_incorreta') return 'A senha atual está incorreta.'
  if (reason === 'senha_nova_igual_atual') return 'A senha nova deve ser diferente da atual.'
  if (response?.status === 422)
    return 'Confira as senhas informadas. A nova senha deve ter de 8 a 128 caracteres, com letra e número.'
  return generic
}

export function resetPasswordError(error: unknown) {
  const response = responseOf(error)
  if (response?.status === 429) return tooMany
  if (response?.data?.error?.reason === 'token_invalido')
    return 'Este link é inválido, expirou ou já foi usado. Solicite um novo e-mail de recuperação.'
  if (response?.status === 422)
    return 'Confira a senha informada. Ela deve ter de 8 a 128 caracteres, com letra e número.'
  return generic
}

export function recoveryRequestError(error: unknown) {
  return responseOf(error)?.status === 429
    ? tooMany
    : 'Não foi possível enviar o pedido agora. Tente novamente.'
}
