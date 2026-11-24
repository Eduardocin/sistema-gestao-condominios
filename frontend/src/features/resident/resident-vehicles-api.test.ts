import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AxiosError, AxiosHeaders } from 'axios'
import { createSessionClient, sessionKey } from '../auth/session.ts'
import {
  createResidentVehiclesClient,
  prepareVehicle,
  vehicleFailureMessage,
} from './resident-vehicles-api.ts'

const vehicle = {
  id: 'vehicle-1',
  unidade_id: 'unit-1',
  unidade: { id: 'unit-1', nome: '101' },
  placa: 'ABC1D23',
  marca: 'Fiat',
  modelo: 'Uno',
  cor: 'Prata',
  ativo: true,
}

const fields = { placa: 'ABC1D23', marca: 'Fiat', modelo: 'Uno', cor: 'Prata' }

function startVehiclesApi() {
  const requests: {
    method?: string
    url?: string
    params: unknown
    body: unknown
    auth: unknown
  }[] = []
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
      auth: config.headers.get('Authorization'),
    })
    let data: unknown = vehicle
    if (config.method === 'get' && config.url === '/veiculos') {
      data = { items: [vehicle], total: 5, page: 2, page_size: 4 }
    }
    if (config.url === '/veiculos/vehicle-1/remocao') data = { ...vehicle, ativo: false }
    return { config, data, headers: {}, status: 200, statusText: 'OK' }
  }

  return { api: createResidentVehiclesClient(session.http), requests }
}

test('consulta veículos da unidade vinculada com filtro e paginação na sessão autenticada', async () => {
  const { api, requests } = startVehiclesApi()
  const result = await api.list('unit-1', '  Uno  ', 2, 4)

  assert.deepEqual(requests, [
    {
      method: 'get',
      url: '/veiculos',
      params: { unidade_id: 'unit-1', busca: 'Uno', page: 2, page_size: 4 },
      body: undefined,
      auth: 'Bearer access-a',
    },
  ])
  assert.deepEqual(result, { items: [vehicle], total: 5, page: 2, page_size: 4 })
})

test('omite busca em branco ao consultar veículos', async () => {
  const { api, requests } = startVehiclesApi()
  await api.list('unit-1', '   ', 1, 4)

  assert.equal(
    new URLSearchParams(requests[0].params as Record<string, string>).has('busca'),
    false,
  )
})

test('envia a unidade no cadastro do veículo', async () => {
  const { api, requests } = startVehiclesApi()
  assert.deepEqual(await api.create('unit-1', fields), vehicle)
  assert.deepEqual(requests[0], {
    method: 'post',
    url: '/veiculos',
    params: undefined,
    body: { ...fields, unidade_id: 'unit-1' },
    auth: 'Bearer access-a',
  })
})

test('carrega o cadastro completo para editar e salva sem trocar a unidade', async () => {
  const { api, requests } = startVehiclesApi()
  assert.deepEqual(await api.detail('vehicle-1'), vehicle)
  await api.update('vehicle-1', fields)

  assert.deepEqual(
    requests.map(({ method, url, body }) => ({ method, url, body })),
    [
      { method: 'get', url: '/veiculos/vehicle-1', body: undefined },
      { method: 'put', url: '/veiculos/vehicle-1', body: fields },
    ],
  )
})

test('remove o veículo por POST no recurso de remoção', async () => {
  const { api, requests } = startVehiclesApi()
  assert.equal((await api.remove('vehicle-1')).ativo, false)
  assert.deepEqual(requests[0], {
    method: 'post',
    url: '/veiculos/vehicle-1/remocao',
    params: undefined,
    body: {},
    auth: 'Bearer access-a',
  })
})

test('aceita placas tradicional e Mercosul e normaliza os campos do cadastro', () => {
  assert.deepEqual(prepareVehicle({ ...fields, placa: ' abc-1234 ', marca: '  Fiat  ' }), {
    data: { placa: 'ABC1234', marca: 'Fiat', modelo: 'Uno', cor: 'Prata' },
  })
  assert.deepEqual(prepareVehicle({ ...fields, placa: 'abc 1d23' }), { data: fields })
})

test('recusa placas fora dos dois formatos e textos vazios ou acima do limite', () => {
  const result = prepareVehicle({ placa: 'ABC-D123', marca: ' ', modelo: 'A'.repeat(41), cor: '' })
  assert.ok(result.errors?.placa)
  assert.ok(result.errors?.marca)
  assert.ok(result.errors?.modelo)
  assert.ok(result.errors?.cor)
  assert.equal(result.data, undefined)
})

function apiFailure(status: number, reason?: string) {
  return new AxiosError('Request failed', undefined, undefined, undefined, {
    status,
    data: { error: { code: 'error', reason } },
    statusText: 'Error',
    headers: {},
    config: { headers: new AxiosHeaders() },
  })
}

test('distingue acesso bloqueado, placa duplicada e limite da unidade', () => {
  assert.match(vehicleFailureMessage(apiFailure(403)), /acesso.*unidade/i)
  assert.match(vehicleFailureMessage(apiFailure(409, 'placa_ja_cadastrada_na_unidade')), /placa/i)
  assert.match(vehicleFailureMessage(apiFailure(409, 'limite_veiculos')), /5 veículos ativos/i)
  assert.match(vehicleFailureMessage(apiFailure(409, 'veiculo_removido')), /já foi removido/i)
})
