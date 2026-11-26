import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createAdminOccurrencesClient } from './admin-occurrences-api.ts'

function fixture(reply: (url: string) => unknown = () => ({})) {
  const requests: unknown[][] = []
  const http = axios.create({
    adapter: async (config) => {
      requests.push([config.method, config.url, config.params, config.data])
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: reply(config.url ?? ''),
      }
    },
  })
  return { api: createAdminOccurrencesClient(http), requests }
}

test('lista com os filtros recebidos e limita page_size a 100', async () => {
  const { api, requests } = fixture(() => ({ items: [], page: 1, page_size: 20, total: 0 }))
  await api.occurrences({ page: 2, page_size: 20, status: 'em_aberto', de: '2026-11-01' })
  await api.occurrences({ page: 1, page_size: 500 })
  assert.deepEqual(requests, [
    [
      'get',
      '/ocorrencias',
      { page: 2, page_size: 20, status: 'em_aberto', de: '2026-11-01' },
      undefined,
    ],
    ['get', '/ocorrencias', { page: 1, page_size: 100 }, undefined],
  ])
})

test('detalha, responde e resolve com o id codificado na URL', async () => {
  const { api, requests } = fixture()
  await api.occurrence('oc/1')
  await api.reply('oc/1', { texto: 'Equipe acionada.', responsavel_id: 'r-1' })
  await api.resolve('oc/1', { responsavel_id: 'r-1' })
  await api.resolve('oc/1', { texto: 'Resolvido.', responsavel_id: 'r-1' })
  assert.deepEqual(requests, [
    ['get', '/ocorrencias/oc%2F1', undefined, undefined],
    [
      'post',
      '/ocorrencias/oc%2F1/respostas',
      undefined,
      JSON.stringify({ texto: 'Equipe acionada.', responsavel_id: 'r-1' }),
    ],
    ['post', '/ocorrencias/oc%2F1/resolucao', undefined, JSON.stringify({ responsavel_id: 'r-1' })],
    [
      'post',
      '/ocorrencias/oc%2F1/resolucao',
      undefined,
      JSON.stringify({ texto: 'Resolvido.', responsavel_id: 'r-1' }),
    ],
  ])
})

test('usa só os responsáveis ativos e baixa anexo pela API de arquivos', async () => {
  const { api, requests } = fixture((url) =>
    url === '/responsaveis-administracao'
      ? [
          { id: 'r-1', nome: 'Ana', ativo: true },
          { id: 'r-2', nome: 'Bia', ativo: false },
        ]
      : { url: 'http://files.test/anexo' },
  )
  const people = await api.activeResponsibles()
  assert.deepEqual(
    people.map((person) => person.id),
    ['r-1'],
  )
  assert.equal(await api.attachmentUrl('arq/1'), 'http://files.test/anexo')
  assert.deepEqual(
    requests.map((request) => request.slice(0, 2)),
    [
      ['get', '/responsaveis-administracao'],
      ['get', '/arquivos/arq%2F1/download'],
    ],
  )
})
