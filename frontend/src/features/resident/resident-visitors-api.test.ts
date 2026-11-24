import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AxiosError } from 'axios'
import { createSessionClient, sessionKey } from '../auth/session.ts'
import { createResidentVisitorsClient, residentVisitorError } from './resident-visitors-api.ts'

const visitorData = {
  nome: 'Lúcia Silva',
  cpf: '52998224725',
  idade: null,
  observacoes: 'Aguardar no hall',
  entrada_prevista: '2026-11-24',
  saida_prevista: '2026-11-25',
}
const visitor = {
  ...visitorData,
  id: 'visitante/1',
  unidade_id: 'unit-1',
  avulso: false,
  cancelado_em: null,
}
const page = { items: [visitor], total: 21, page: 2, page_size: 20 }

interface CapturedRequest {
  method: string | undefined
  url: string | undefined
  params: unknown
  body: unknown
  authorization: unknown
}

function startVisitorsApi(conflictReason?: string) {
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
      method: config.method,
      url: config.url,
      params: config.params,
      body: config.data ? JSON.parse(String(config.data)) : undefined,
      authorization: config.headers.get('Authorization'),
    })
    if (conflictReason) {
      throw new AxiosError('Conflict', AxiosError.ERR_BAD_REQUEST, config, null, {
        config,
        data: { error: { code: 'conflict', reason: conflictReason } },
        headers: {},
        status: 409,
        statusText: 'Conflict',
      })
    }
    return {
      config,
      data: config.method === 'get' && config.url === '/visitantes' ? page : visitor,
      headers: {},
      status: 200,
      statusText: 'OK',
    }
  }
  return { api: createResidentVisitorsClient(session.http), requests }
}

test('lista visitantes por unidade, nome, situação e página com a sessão do morador', async () => {
  const { api, requests } = startVisitorsApi()

  const result = await api.list({
    unidade_id: 'unit-1',
    busca: '  Lúcia  ',
    situacao: 'futuros',
    page: 2,
  })

  assert.deepEqual(result, page)
  assert.deepEqual(requests, [
    {
      method: 'get',
      url: '/visitantes',
      params: { unidade_id: 'unit-1', busca: 'Lúcia', situacao: 'futuros', page: 2, page_size: 20 },
      body: undefined,
      authorization: 'Bearer access-a',
    },
  ])
})

test('não envia termos numéricos que a busca da API poderia interpretar como CPF', async () => {
  const { api, requests } = startVisitorsApi()

  for (const busca of ['529.982.247-25', 'Silva 529', 'Silva ５２９']) {
    await assert.rejects(api.list({ unidade_id: 'unit-1', busca, page: 1 }), /Busque pelo nome/)
  }
  assert.equal(requests.length, 0)
})

test('restringe a query aos filtros de visitantes e omite buscas em branco', async () => {
  const { api, requests } = startVisitorsApi()
  const query = { unidade_id: 'unit-1', page: 1, busca: '  ', cpf: visitorData.cpf }

  await api.list(query)

  const params = requests[0].params as Record<string, unknown>
  assert.equal(params.busca, undefined)
  assert.equal('cpf' in params, false)
})

test('consulta, cadastra, atualiza e cancela com os contratos do morador', async () => {
  const { api, requests } = startVisitorsApi()

  assert.deepEqual(await api.get(visitor.id), visitor)
  assert.deepEqual(await api.create({ ...visitorData, unidade_id: 'unit-1' }), visitor)
  assert.deepEqual(await api.update(visitor.id, visitorData), visitor)
  assert.deepEqual(await api.cancel(visitor.id), visitor)

  assert.deepEqual(
    requests.map(({ method, url, params, body }) => [method, url, params, body]),
    [
      ['get', '/visitantes/visitante%2F1', undefined, undefined],
      ['post', '/visitantes', undefined, { ...visitorData, unidade_id: 'unit-1' }],
      ['put', '/visitantes/visitante%2F1', undefined, visitorData],
      ['post', '/visitantes/visitante%2F1/cancelamento', undefined, {}],
    ],
  )
})

test('distingue cadastro já utilizado e visita em andamento em conflitos da API', async () => {
  const editing = startVisitorsApi('visitante_ja_utilizado')
  await assert.rejects(editing.api.update(visitor.id, visitorData), (error: unknown) => {
    assert.match(residentVisitorError(error, 'Falha ao editar.'), /já registrou uma entrada/)
    return true
  })

  const cancelling = startVisitorsApi('visita_em_andamento')
  await assert.rejects(cancelling.api.cancel(visitor.id), (error: unknown) => {
    assert.match(residentVisitorError(error, 'Falha ao cancelar.'), /registro de saída/)
    return true
  })
})
