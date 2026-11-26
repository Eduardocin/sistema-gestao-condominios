import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios, { AxiosError } from 'axios'
import {
  createSupportClient,
  reportPeriodError,
  supportError,
  ticketStatusLabels,
} from './suporte-api.ts'

function fixture() {
  const requests: unknown[][] = []
  const http = axios.create({
    adapter: async (config) => {
      requests.push([config.method, config.url, config.params, config.data])
      return { status: 200, statusText: 'OK', headers: {}, config, data: { id: 'x', url: 'u' } }
    },
  })
  return { api: createSupportClient(http), requests }
}

test('a Administração só filtra por status e usa as rotas do próprio condomínio', async () => {
  const { api, requests } = fixture()
  await api.tickets('administracao', 2, { status: 'aberto', busca: 'água', de: '2026-11-01' })
  await api.ticket('administracao', 'a/1')
  assert.deepEqual(requests, [
    ['get', '/chamados', { status: 'aberto', page: 2, page_size: 20 }, undefined],
    ['get', '/chamados/a%2F1', undefined, undefined],
  ])
})

test('o ADM filtra a fila por status, busca e período, sem enviar filtros vazios', async () => {
  const { api, requests } = fixture()
  await api.tickets('plataforma', 1, {
    status: undefined,
    busca: 'água',
    de: '',
    ate: '2026-11-30',
  })
  assert.deepEqual(requests[0], [
    'get',
    '/plataforma/chamados',
    { busca: 'água', ate: '2026-11-30', page: 1, page_size: 20 },
    undefined,
  ])
})

test('abre, responde e encerra chamados nas rotas de cada perfil', async () => {
  const { api, requests } = fixture()
  await api.openTicket('Erro', 'Detalhes', ['file-1'])
  await api.reply('administracao', 't1', 'Mais detalhes')
  await api.reply('plataforma', 't1', 'Resposta')
  await api.closeTicket('t1')
  assert.deepEqual(
    requests.map(([method, url, , data]) => [method, url, data]),
    [
      [
        'post',
        '/chamados',
        JSON.stringify({ titulo: 'Erro', descricao: 'Detalhes', anexos: ['file-1'] }),
      ],
      ['post', '/chamados/t1/mensagens', JSON.stringify({ texto: 'Mais detalhes' })],
      ['post', '/plataforma/chamados/t1/mensagens', JSON.stringify({ texto: 'Resposta' })],
      ['post', '/plataforma/chamados/t1/encerramento', JSON.stringify({})],
    ],
  )
})

test('envia anexos ao módulo suporte e baixa por URL assinada', async () => {
  const { api, requests } = fixture()
  const file = new File(['x'], 'print.png', { type: 'image/png' })
  assert.equal(await api.uploadAttachment(file), 'x')
  assert.equal(await api.download('f/1'), 'u')
  assert.deepEqual(requests[0].slice(0, 3), ['post', '/arquivos/suporte', { nome: 'print.png' }])
  assert.equal(requests[1][1], '/arquivos/f%2F1/download')
})

test('comunicados: o ADM envia e consulta; a Administração só lê os recebidos', async () => {
  const { api, requests } = fixture()
  await api.sendAnnouncement('Manutenção', 'Sábado às 8h')
  await api.platformAnnouncements(3)
  await api.platformAnnouncement('c1')
  await api.receivedAnnouncements(1)
  assert.deepEqual(
    requests.map(([method, url]) => [method, url]),
    [
      ['post', '/plataforma/comunicados'],
      ['get', '/plataforma/comunicados'],
      ['get', '/plataforma/comunicados/c1'],
      ['get', '/comunicados'],
    ],
  )
  assert.deepEqual(requests[1][2], { page: 3, page_size: 20 })
})

test('o relatório de encomendas envia só as datas preenchidas', async () => {
  const { api, requests } = fixture()
  await api.packageReport({ data_de: '2026-11-01', data_ate: '' })
  assert.deepEqual(requests[0], [
    'get',
    '/encomendas/relatorio',
    { data_de: '2026-11-01' },
    undefined,
  ])
})

test('rejeita período invertido e aceita datas iguais ou em branco', () => {
  assert.match(reportPeriodError({ data_de: '2026-11-30', data_ate: '2026-11-01' }), /posterior/)
  assert.equal(reportPeriodError({ data_de: '2026-11-01', data_ate: '2026-11-01' }), '')
  assert.equal(reportPeriodError({ data_de: '2026-11-01' }), '')
  assert.equal(reportPeriodError({}), '')
})

test('mostra a mensagem do servidor nos erros 4xx e uma genérica nos demais', () => {
  const failure = (status: number, message?: string) =>
    new AxiosError('x', undefined, undefined, undefined, {
      status,
      statusText: '',
      headers: {},
      config: { headers: new axios.AxiosHeaders() },
      data: message ? { error: { message } } : {},
    })
  assert.equal(supportError(failure(409, 'Chamado encerrado.')), 'Chamado encerrado.')
  assert.match(supportError(failure(403, 'x')), /não permite/)
  assert.match(supportError(failure(500, 'interno')), /Tente novamente/)
  assert.match(supportError(new Error('rede')), /Tente novamente/)
  assert.equal(ticketStatusLabels.em_atendimento, 'Em atendimento')
})
