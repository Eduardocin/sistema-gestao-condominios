import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios, { AxiosError } from 'axios'
import {
  auditError,
  auditFilterError,
  auditValue,
  createAuditClient,
  noAuditFilters,
} from './auditoria-api.ts'

function fixture() {
  const requests: unknown[][] = []
  const http = axios.create({
    adapter: async (config) => {
      requests.push([config.method, config.url, config.params])
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: { items: [{ id: 'c1', nome: 'Aurora', status: 'ativo', extra: 1 }] },
      }
    },
  })
  return { api: createAuditClient(http), requests }
}

test('consulta a auditoria sem enviar filtros vazios e com o cursor da página anterior', async () => {
  const { api, requests } = fixture()
  await api.records(noAuditFilters, null)
  await api.records(
    { ...noAuditFilters, acao: ' reserva. ', de: '2026-11-01', condominio_id: 'c/1' },
    'abc',
  )
  assert.deepEqual(requests, [
    ['get', '/plataforma/auditoria', { page_size: 20 }],
    [
      'get',
      '/plataforma/auditoria',
      { page_size: 20, condominio_id: 'c/1', de: '2026-11-01', acao: 'reserva.', cursor: 'abc' },
    ],
  ])
})

test('lista só os condomínios ativos, com id e nome', async () => {
  const { api, requests } = fixture()
  assert.deepEqual(await api.condominiums(), [{ id: 'c1', nome: 'Aurora' }])
  assert.deepEqual(requests[0], [
    'get',
    '/plataforma/condominios',
    { status: 'ativo', page: 1, page_size: 100 },
  ])
})

test('avisa ação fora do formato e período invertido antes de consultar', () => {
  const base = noAuditFilters
  assert.equal(auditFilterError(base), '')
  assert.equal(auditFilterError({ ...base, acao: 'reserva.' }), '')
  assert.equal(auditFilterError({ ...base, acao: 'reserva.cancelar' }), '')
  assert.match(auditFilterError({ ...base, acao: 'reserva' }), /grupo\.verbo/)
  assert.match(auditFilterError({ ...base, acao: 'Reserva.x' }), /grupo\.verbo/)
  assert.match(auditFilterError({ ...base, de: '2026-11-30', ate: '2026-11-01' }), /posterior/)
  assert.equal(auditFilterError({ ...base, de: '2026-11-01', ate: '2026-11-01' }), '')
})

test('mostra a mensagem do servidor em 4xx e uma genérica nos demais erros', () => {
  const failure = (status: number, message?: string) =>
    new AxiosError('x', undefined, undefined, undefined, {
      status,
      statusText: '',
      headers: {},
      config: { headers: new axios.AxiosHeaders() },
      data: message ? { error: { message } } : {},
    })
  assert.equal(auditError(failure(422, 'Cursor inválido.')), 'Cursor inválido.')
  assert.match(auditError(failure(403, 'x')), /não permite/)
  assert.match(auditError(failure(500, 'interno')), /Tente novamente/)
  assert.match(auditError(new Error('rede')), /Tente novamente/)
})

test('formata valores de antes e depois', () => {
  assert.equal(auditValue(null), '—')
  assert.equal(auditValue('ativo'), 'ativo')
  assert.equal(auditValue(38), '38')
  assert.equal(auditValue({ a: 1 }), '{"a":1}')
})
