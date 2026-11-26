import { isAxiosError } from 'axios'

/** Ação que falhou: muda só o sentido do 404 (área sumida x responsável inativo). */
export type AdminAction = 'area' | 'cancelamento' | 'carregar'

interface ApiErrorBody {
  error?: { code?: string; message?: string; reason?: string }
}

// Textos por `reason` (convivencia.md e reservas/router.py). Ficam aqui para a tela
// não depender do texto da API, que pode mudar.
export const REASON_MESSAGES: Record<string, string> = {
  nome_duplicado: 'Já existe uma área comum com esse nome neste condomínio. Escolha outro nome.',
  foto_invalida: 'A foto enviada não foi encontrada neste condomínio. Selecione a imagem de novo.',
  reservas_fora_do_horario:
    'Há reservas ativas fora do novo horário. Cancele essas reservas em Reservas ou mantenha o horário atual.',
  area_ja_desativada: 'Esta área já estava desativada. A lista foi atualizada.',
  area_ja_ativa: 'Esta área já estava ativa. A lista foi atualizada.',
  reserva_ja_cancelada: 'Esta reserva já estava cancelada. A lista foi atualizada.',
  reserva_encerrada: 'O horário desta reserva já começou; ela não pode mais ser cancelada.',
}

export const GENERIC_ERROR = 'Não foi possível concluir a operação. Tente novamente.'
export const RESPONSIBLE_NOT_FOUND =
  'O responsável escolhido não está mais ativo ou a reserva não existe mais. Atualize a página e tente novamente.'

export function adminErrorMessage(error: unknown, action: AdminAction): string {
  if (!isAxiosError<ApiErrorBody>(error) || !error.response) return GENERIC_ERROR
  const { status, data } = error.response
  const body = data?.error
  if (body?.reason && REASON_MESSAGES[body.reason]) return REASON_MESSAGES[body.reason]
  if (status === 403) return 'Seu perfil não permite esta operação neste condomínio.'
  if (status === 404) {
    // No cancelamento, a reserva veio da lista; o 404 mais provável é o responsável
    // (inativo ou de outro condomínio). A API não diferencia os dois casos.
    if (action === 'cancelamento') return RESPONSIBLE_NOT_FOUND
    if (action === 'area') return 'Esta área não foi encontrada. Atualize a lista.'
    return 'Registro não encontrado. Atualize a página.'
  }
  if (status === 503) return 'O envio de fotos está indisponível no momento. Tente novamente.'
  // 409 e 422 sem reason conhecido: a mensagem da API já vem em pt-BR para exibir.
  if ((status === 409 || status === 422) && body?.message) return body.message
  return GENERIC_ERROR
}

export function errorStatus(error: unknown) {
  return isAxiosError(error) ? error.response?.status : undefined
}

/** 409 de transição (já desativada, já cancelada...): a lista está velha e vale recarregar. */
export function isConflict(error: unknown) {
  return errorStatus(error) === 409
}
