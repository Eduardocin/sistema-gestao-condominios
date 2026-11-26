import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createAdminAreasClient } from './admin-areas-api.ts'

type Reply = (url: string, params: Record<string, unknown> | undefined) => unknown

function fixture(reply: Reply = () => ({ id: 'novo' })) {
  const requests: unknown[][] = []
  const http = axios.create({
    adapter: async (config) => {
      requests.push([
        config.method,
        config.url,
        config.params,
        config.data,
        config.headers.get('Content-Type'),
      ])
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: reply(config.url ?? '', config.params),
      }
    },
  })
  return { api: createAdminAreasClient(http), requests }
}

const payload = {
  nome: 'Salão',
  foto_arquivo_id: 'foto-1',
  regras: null,
  abre_as: '08:00',
  fecha_as: '22:00',
  capacidade: 40,
}

test('lista áreas com o filtro ativa só quando não é "todas"', async () => {
  const page = { items: [], page: 1, page_size: 20, total: 0 }
  const { api, requests } = fixture(() => page)
  await api.areas('ativas', 1)
  await api.areas('desativadas', 2)
  await api.areas('todas', 1)
  assert.deepEqual(
    requests.map((request) => request.slice(0, 3)),
    [
      ['get', '/areas-comuns', { page: 1, page_size: 20, ativa: true }],
      ['get', '/areas-comuns', { page: 2, page_size: 20, ativa: false }],
      ['get', '/areas-comuns', { page: 1, page_size: 20 }],
    ],
  )
})

test('cria, edita (PUT), desativa e reativa com o id codificado na URL', async () => {
  const { api, requests } = fixture()
  await api.createArea(payload)
  await api.updateArea('area/1', payload)
  await api.deactivateArea('area/1')
  await api.reactivateArea('area/1')
  assert.deepEqual(
    requests.map((request) => request.slice(0, 4)),
    [
      ['post', '/areas-comuns', undefined, JSON.stringify(payload)],
      ['put', '/areas-comuns/area%2F1', undefined, JSON.stringify(payload)],
      ['post', '/areas-comuns/area%2F1/desativacao', undefined, '{}'],
      ['post', '/areas-comuns/area%2F1/reativacao', undefined, '{}'],
    ],
  )
})

test('envia a foto como corpo binário em /arquivos/fotos e devolve o id', async () => {
  const { api, requests } = fixture(() => ({ id: 'foto-9' }))
  const photo = new File(['png'], 'salao.png', { type: 'image/png' })
  assert.equal(await api.uploadPhoto(photo), 'foto-9')
  assert.deepEqual(requests, [
    ['post', '/arquivos/fotos', { nome: 'salao.png' }, photo, 'image/png'],
  ])
})

test('lista reservas com os filtros recebidos e cancela com motivo e responsável', async () => {
  const { api, requests } = fixture(() => ({ items: [], page: 1, page_size: 20, total: 0 }))
  await api.reservations({ page: 2, page_size: 20, area_id: 'a-1', status: 'ativa' })
  await api.cancelReservation('res/1', 'Manutenção', 'resp-1')
  assert.deepEqual(
    requests.map((request) => request.slice(0, 4)),
    [
      ['get', '/reservas', { page: 2, page_size: 20, area_id: 'a-1', status: 'ativa' }, undefined],
      [
        'post',
        '/reservas/res%2F1/cancelamento',
        undefined,
        JSON.stringify({ motivo: 'Manutenção', responsavel_id: 'resp-1' }),
      ],
    ],
  )
})

test('selects: percorre todas as páginas de unidades e filtra responsáveis ativos', async () => {
  const { api, requests } = fixture((url, params) => {
    if (url === '/responsaveis-administracao')
      return [
        { id: 'r-1', nome: 'Ana', ativo: true },
        { id: 'r-2', nome: 'Bia', ativo: false },
      ]
    const page = Number(params?.page)
    return { items: [{ id: `u-${page}` }], page, page_size: 100, total: 2 }
  })
  const units = await api.units()
  const people = await api.activeResponsibles()
  assert.deepEqual(
    units.map((unit) => unit.id),
    ['u-1', 'u-2'],
  )
  assert.deepEqual(
    people.map((person) => person.id),
    ['r-1'],
  )
  assert.deepEqual(
    requests.map((request) => request.slice(0, 3)),
    [
      ['get', '/unidades', { page: 1, page_size: 100 }],
      ['get', '/unidades', { page: 2, page_size: 100 }],
      ['get', '/responsaveis-administracao', undefined],
    ],
  )
})
