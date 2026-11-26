import { isAxiosError } from 'axios'

export type OccurrenceAction = 'carregar' | 'resposta' | 'resolucao'

interface ApiErrorBody {
  error?: { code?: string; message?: string; reason?: string }
}

export const GENERIC_ERROR = 'Não foi possível concluir a operação. Tente novamente.'
export const ALREADY_RESOLVED =
  'Esta ocorrência já tinha sido resolvida. O detalhe foi atualizado com a situação atual.'
export const RESPONSIBLE_NOT_FOUND =
  'O responsável escolhido não está mais ativo ou a ocorrência não foi encontrada. A lista de responsáveis foi atualizada; tente novamente.'

export function errorStatus(error: unknown) {
  return isAxiosError(error) ? error.response?.status : undefined
}

export function isAlreadyResolved(error: unknown) {
  return (
    isAxiosError<ApiErrorBody>(error) &&
    error.response?.status === 409 &&
    error.response.data?.error?.reason === 'ocorrencia_ja_resolvida'
  )
}

/** Mensagem para a tela, sem código HTTP nem detalhe técnico. */
export function occurrenceErrorMessage(error: unknown, action: OccurrenceAction): string {
  if (isAlreadyResolved(error)) return ALREADY_RESOLVED
  if (!isAxiosError<ApiErrorBody>(error) || !error.response) return GENERIC_ERROR
  const { status, data } = error.response
  if (status === 403) return 'Seu perfil não permite esta operação neste condomínio.'
  if (status === 404) {
    // Ao responder ou resolver, a ocorrência veio da lista: o 404 provável é o responsável.
    // A API não diferencia os dois casos.
    if (action !== 'carregar') return RESPONSIBLE_NOT_FOUND
    return 'Ocorrência não encontrada. Atualize a lista.'
  }
  if (status === 422)
    return action === 'carregar'
      ? 'Confira os filtros e tente novamente.'
      : 'Confira o texto e o responsável e tente novamente.'
  // Outro 409 com mensagem da API (já em pt-BR para exibir).
  if (status === 409 && data?.error?.message) return data.error.message
  return GENERIC_ERROR
}
