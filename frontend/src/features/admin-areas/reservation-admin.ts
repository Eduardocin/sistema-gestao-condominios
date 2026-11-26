// Regras puras da lista de reservas da Administração (convivencia.md, seção 4.3).
import { charCount } from './area-form.ts'

export type ReservationStatusFilter = '' | 'ativa' | 'cancelada'

export interface ReservationFilters {
  areaId: string
  unidadeId: string
  dataDe: string
  dataAte: string
  status: ReservationStatusFilter
}

export interface ReservationParams {
  page: number
  page_size: number
  area_id?: string
  unidade_id?: string
  data_de?: string
  data_ate?: string
  status?: 'ativa' | 'cancelada'
}

export type ReservationParamsResult =
  | { ok: true; params: ReservationParams }
  | { ok: false; message: string }

export const EMPTY_FILTERS: ReservationFilters = {
  areaId: '',
  unidadeId: '',
  dataDe: '',
  dataAte: '',
  status: '',
}

export const REASON_MAX = 300
export const PAGE_SIZE = 20

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

function validDate(value: string) {
  if (!ISO_DATE.test(value)) return false
  // Date normaliza 2026-02-31 para março: comparar de volta pega a data inexistente.
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

/** Monta a query de GET /reservas sem parâmetros vazios e com o período coerente. */
export function buildReservationParams(
  filters: ReservationFilters,
  page = 1,
  pageSize = PAGE_SIZE,
): ReservationParamsResult {
  const dataDe = filters.dataDe.trim()
  const dataAte = filters.dataAte.trim()
  if ((dataDe && !validDate(dataDe)) || (dataAte && !validDate(dataAte)))
    return { ok: false, message: 'Informe datas válidas no período.' }
  // AAAA-MM-DD ordena como texto, então a comparação direta basta.
  if (dataDe && dataAte && dataDe > dataAte)
    return { ok: false, message: 'A data inicial deve ser igual ou anterior à data final.' }

  const params: ReservationParams = { page: Math.max(1, Math.trunc(page)), page_size: pageSize }
  if (filters.areaId) params.area_id = filters.areaId
  if (filters.unidadeId) params.unidade_id = filters.unidadeId
  if (dataDe) params.data_de = dataDe
  if (dataAte) params.data_ate = dataAte
  if (filters.status) params.status = filters.status
  return { ok: true, params }
}

export interface CancellationValues {
  motivo: string
  responsavelId: string
}

export type CancellationResult =
  | { ok: true; motivo: string; responsavelId: string }
  | { ok: false; errors: { motivo?: string; responsavel?: string } }

export function validateCancellation(values: CancellationValues): CancellationResult {
  const motivo = values.motivo.trim()
  const errors: { motivo?: string; responsavel?: string } = {}
  if (!motivo) errors.motivo = 'Informe o motivo do cancelamento.'
  else if (charCount(motivo) > REASON_MAX) errors.motivo = `Use no máximo ${REASON_MAX} caracteres.`
  if (!values.responsavelId) errors.responsavel = 'Escolha o responsável pelo cancelamento.'
  if (errors.motivo || errors.responsavel) return { ok: false, errors }
  return { ok: true, motivo, responsavelId: values.responsavelId }
}

// O horário das reservas vale no fuso do condomínio (convencoes.md, seção 1).
const condoClock = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'America/Sao_Paulo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** "AAAA-MM-DD HH:MM" no fuso do condomínio, comparável como texto. */
export function condoNow(date = new Date()) {
  return condoClock.format(date)
}

/** Botão Cancelar só em reserva ativa cujo horário ainda não começou (senão a API dá 409). */
export function isCancellable(
  reservation: { status: string; data: string; hora_inicio: string },
  now: string,
) {
  return reservation.status === 'ativa' && `${reservation.data} ${reservation.hora_inicio}` > now
}

/** 2026-11-14 → 14/11/2026, sem passar por Date (evita deslocar o dia pelo fuso). */
export function formatDate(value: string) {
  const [year, month, day] = value.split('-')
  return year && month && day ? `${day}/${month}/${year}` : value
}

const condoDateTime = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'America/Sao_Paulo',
})

export function formatDateTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : condoDateTime.format(date)
}
