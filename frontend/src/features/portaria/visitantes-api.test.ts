import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSessionClient, sessionKey } from '../auth/session.ts'
import { createVisitantesClient } from './visitantes-api.ts'

interface CapturedRequest {
  method: string
  url: string
  params?: Record<string, unknown>
  body: unknown
}

function startVisitantesApi() {
  const requests: CapturedRequest[] = []
  const session = createSessionClient('http://api.test', {
    getItem: (key) =>
      key === sessionKey
        ? JSON.stringify({ access_token: 'access-a', refresh_token: 'refresh-a', condominios: [] })
        : null,
    setItem() {},
    removeItem() {},
  })
  session.http.defaults.adapter = async (config) => {
    requests.push({
      method: config.method?.toUpperCase() ?? 'GET',
      url: config.url ?? '/',
      params: config.params as Record<string, unknown> | undefined,
      body: config.data ? JSON.parse(String(config.data)) : undefined,
    })
    const path = config.url ?? '/'
    const data =
      path === '/portaria/autorizacoes'
        ? []
        : { items: [], total: 0, page: 1, page_size: 20 }
    return {
      config,
      data,
      headers: {},
      status: 200,
      statusText: 'OK',
    }
  }
  return { api: createVisitantesClient(session.http), requests }
}

test('busca por CPF envia documento somente no corpo de POST e nunca na URL ou query', async () => {
  const { api, requests } = startVisitantesApi()

  await api.buscar({ unidade: 'unit-1', termo: '529.982.247-25', por: 'cpf' }, 2)

  assert.equal(requests.length, 1)
  assert.equal(requests[0].method, 'POST')
  assert.equal(requests[0].url, '/portaria/visitantes/busca-documento')
  assert.deepEqual(requests[0].params, { page: 2, page_size: 20 })
  assert.equal(JSON.stringify(requests[0].params).includes('52998224725'), false)
  assert.deepEqual(requests[0].body, { unidade_id: 'unit-1', cpf: '52998224725' })
})

test('visitas repassa termo de busca normalizado quando informado', async () => {
  const { api, requests } = startVisitantesApi()

  await api.visitas('em_andamento', 1, '  101  ')
  await api.visitas('encerrada', 2, '   ')

  assert.equal(requests.length, 2)
  assert.deepEqual(requests[0].params, {
    status: 'em_andamento',
    page: 1,
    page_size: 20,
    busca: '101',
  })
  assert.deepEqual(requests[1].params, {
    status: 'encerrada',
    page: 2,
    page_size: 20,
    busca: undefined,
  })
})
