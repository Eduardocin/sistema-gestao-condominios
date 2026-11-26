import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  EMPTY_FILTERS,
  buildReservationParams,
  condoNow,
  formatDate,
  isCancellable,
  validateCancellation,
} from './reservation-admin.ts'

test('sem filtros envia só a paginação', () => {
  assert.deepEqual(buildReservationParams(EMPTY_FILTERS), {
    ok: true,
    params: { page: 1, page_size: 20 },
  })
})

test('inclui apenas os filtros preenchidos, com os nomes da API', () => {
  const result = buildReservationParams(
    { areaId: 'area-1', unidadeId: '', dataDe: '2026-11-01', dataAte: '', status: 'ativa' },
    3,
  )
  assert.deepEqual(result, {
    ok: true,
    params: { page: 3, page_size: 20, area_id: 'area-1', data_de: '2026-11-01', status: 'ativa' },
  })
  const all = buildReservationParams({
    areaId: 'a',
    unidadeId: 'u',
    dataDe: '2026-11-01',
    dataAte: '2026-11-30',
    status: 'cancelada',
  })
  assert.ok(all.ok)
  assert.deepEqual(Object.keys(all.params).sort(), [
    'area_id',
    'data_ate',
    'data_de',
    'page',
    'page_size',
    'status',
    'unidade_id',
  ])
})

test('aceita período de um dia e recusa data inicial depois da final', () => {
  assert.ok(
    buildReservationParams({ ...EMPTY_FILTERS, dataDe: '2026-11-10', dataAte: '2026-11-10' }).ok,
  )
  const result = buildReservationParams({
    ...EMPTY_FILTERS,
    dataDe: '2026-11-11',
    dataAte: '2026-11-10',
  })
  assert.equal(result.ok, false)
})

test('recusa datas inexistentes ou fora do formato', () => {
  for (const value of ['2026-02-30', '10/11/2026', '2026-13-01']) {
    assert.equal(buildReservationParams({ ...EMPTY_FILTERS, dataDe: value }).ok, false, value)
  }
})

test('página inválida volta para 1', () => {
  const result = buildReservationParams(EMPTY_FILTERS, 0)
  assert.ok(result.ok)
  assert.equal(result.params.page, 1)
})

test('cancelamento exige motivo de 1 a 300 caracteres e responsável', () => {
  assert.deepEqual(validateCancellation({ motivo: '  Manutenção  ', responsavelId: 'r-1' }), {
    ok: true,
    motivo: 'Manutenção',
    responsavelId: 'r-1',
  })
  const empty = validateCancellation({ motivo: '   ', responsavelId: '' })
  assert.equal(empty.ok, false)
  assert.ok(!empty.ok && empty.errors.motivo && empty.errors.responsavel)
  assert.equal(validateCancellation({ motivo: 'x'.repeat(301), responsavelId: 'r' }).ok, false)
  assert.ok(validateCancellation({ motivo: 'x'.repeat(300), responsavelId: 'r' }).ok)
})

test('só reserva ativa e ainda não iniciada pode ser cancelada', () => {
  const now = '2026-11-26 14:00'
  const base = { status: 'ativa', data: '2026-11-26', hora_inicio: '15:00' }
  assert.equal(isCancellable(base, now), true)
  assert.equal(isCancellable({ ...base, hora_inicio: '14:00' }, now), false)
  assert.equal(isCancellable({ ...base, data: '2026-11-25', hora_inicio: '23:00' }, now), false)
  assert.equal(isCancellable({ ...base, status: 'cancelada' }, now), false)
  assert.equal(isCancellable({ ...base, data: '2026-12-01', hora_inicio: '08:00' }, now), true)
})

test('relógio do condomínio usa o fuso de São Paulo no formato comparável', () => {
  assert.equal(condoNow(new Date('2026-11-26T03:30:00Z')), '2026-11-26 00:30')
  assert.equal(condoNow(new Date('2026-11-26T02:59:00Z')), '2026-11-25 23:59')
})

test('formata data pura sem deslocar o dia', () => {
  assert.equal(formatDate('2026-11-01'), '01/11/2026')
})
