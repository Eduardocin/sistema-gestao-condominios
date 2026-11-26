// Regras puras da tela de ocorrências da Administração, espelhando
// backend/app/modules/ocorrencias/schemas.py (RespostaEntrada e ResolucaoEntrada).

export const TEXT_MAX = 2000
export const PAGE_SIZE = 20

export interface ReplyPayload {
  texto: string
  responsavel_id: string
}

/** Sem texto, o campo nem vai no corpo: a API trata ausência e branco do mesmo jeito. */
export interface ResolutionPayload {
  texto?: string
  responsavel_id: string
}

export interface InteractionErrors {
  texto?: string
  responsavel?: string
}

export type ReplyResult =
  | { ok: true; payload: ReplyPayload }
  | { ok: false; errors: InteractionErrors }
export type ResolutionResult =
  | { ok: true; payload: ResolutionPayload }
  | { ok: false; errors: InteractionErrors }

/** Conta caracteres como o Python (code points), para não divergir da API com emoji. */
export function charCount(value: string) {
  return [...value].length
}

// O responsável precisa estar entre os ativos carregados; senão a API devolveria 404.
function responsibleError(responsavelId: string, activeIds: readonly string[]) {
  if (!responsavelId) return 'Escolha o responsável da Administração.'
  if (!activeIds.includes(responsavelId))
    return 'Este responsável não está mais ativo. Escolha outro.'
  return undefined
}

export function validateReply(
  values: { texto: string; responsavelId: string },
  activeIds: readonly string[],
): ReplyResult {
  const texto = values.texto.trim()
  const errors: InteractionErrors = {}
  if (!texto) errors.texto = 'Escreva a resposta.'
  else if (charCount(texto) > TEXT_MAX) errors.texto = `Use no máximo ${TEXT_MAX} caracteres.`
  const responsavel = responsibleError(values.responsavelId, activeIds)
  if (responsavel) errors.responsavel = responsavel
  if (errors.texto || errors.responsavel) return { ok: false, errors }
  return { ok: true, payload: { texto, responsavel_id: values.responsavelId } }
}

export function validateResolution(
  values: { texto: string; responsavelId: string },
  activeIds: readonly string[],
): ResolutionResult {
  const texto = values.texto.trim()
  const errors: InteractionErrors = {}
  if (charCount(texto) > TEXT_MAX) errors.texto = `Use no máximo ${TEXT_MAX} caracteres.`
  const responsavel = responsibleError(values.responsavelId, activeIds)
  if (responsavel) errors.responsavel = responsavel
  if (errors.texto || errors.responsavel) return { ok: false, errors }
  return {
    ok: true,
    payload: texto
      ? { texto, responsavel_id: values.responsavelId }
      : { responsavel_id: values.responsavelId },
  }
}

export type StatusFilter = '' | 'em_aberto' | 'resolvida'

export interface OccurrenceFilters {
  status: StatusFilter
  de: string
  ate: string
  unidadeId: string
}

export interface OccurrenceListParams {
  page: number
  page_size: number
  status?: 'em_aberto' | 'resolvida'
  de?: string
  ate?: string
  unidade_id?: string
}

export type ListParamsResult =
  | { ok: true; params: OccurrenceListParams }
  | { ok: false; message: string }

export const DEFAULT_FILTERS: OccurrenceFilters = {
  status: 'em_aberto',
  de: '',
  ate: '',
  unidadeId: '',
}

function validDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  // Date normaliza 2026-02-31 para março: comparar de volta pega a data inexistente.
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

/** Query de GET /ocorrencias sem parâmetro vazio e com o período coerente. */
export function buildOccurrenceParams(
  filters: OccurrenceFilters,
  page = 1,
  pageSize = PAGE_SIZE,
): ListParamsResult {
  const de = filters.de.trim()
  const ate = filters.ate.trim()
  if ((de && !validDate(de)) || (ate && !validDate(ate)))
    return { ok: false, message: 'Informe datas válidas no período.' }
  // AAAA-MM-DD ordena como texto.
  if (de && ate && de > ate)
    return { ok: false, message: 'A data inicial deve ser igual ou anterior à data final.' }
  const params: OccurrenceListParams = {
    page: Math.max(1, Math.trunc(page)),
    page_size: Math.min(Math.max(1, Math.trunc(pageSize)), 100),
  }
  if (filters.status) params.status = filters.status
  if (de) params.de = de
  if (ate) params.ate = ate
  if (filters.unidadeId) params.unidade_id = filters.unidadeId
  return { ok: true, params }
}

/** Anexos da abertura: os de interação já aparecem na própria interação. */
export function openingAttachments<T extends { interacao_id: string | null }>(anexos: T[]) {
  return anexos.filter((anexo) => anexo.interacao_id === null)
}

const condoDateTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'America/Sao_Paulo',
})

/** Instante da API mostrado no fuso do condomínio. */
export function formatDateTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : condoDateTime.format(date)
}
