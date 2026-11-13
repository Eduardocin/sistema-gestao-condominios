import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSessionClient, sessionKey } from '../auth/session.ts'
import { createEncomendasClient } from './encomendas-api.ts'

interface CapturedRequest {
  method: string
  url: string
  params?: Record<string, unknown>
  contentType: string | undefined
  authorization: string | undefined
  body: unknown
}

const pacote = {
  id: 'package-a',
  unidade: { id: 'unit-a', identificacao: 'Bloco A / 101' },
  destinatario: { id: 'resident-a', nome: 'Ana Exemplo' },
  descricao: 'Caixa de livros',
  foto_arquivo_id: 'file-a',
  status: 'aguardando_retirada',
  recebimento: {
    em: '2026-11-13T12:00:00Z',
    funcionario_id: 'employee-a',
    funcionario_nome: 'Carlos Exemplo',
  },
  entrega: null,
  confirmacao: null,
  pode_confirmar: false,
}

async function startApi() {
  const requests: CapturedRequest[] = []
  const baseURL = 'http://api.test'
  const session = createSessionClient(baseURL, {
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
      contentType: config.headers.get('Content-Type')?.toString(),
      authorization: config.headers.get('Authorization')?.toString(),
      body: config.data,
    })

    const path = config.url ?? '/'
    const query = config.params as Record<string, unknown> | undefined
    const page = Number(query?.page ?? 1)
    let result: unknown = pacote
    if (path === '/encomendas' && config.method === 'get') {
      result = { items: [pacote], page: 2, page_size: 10, total: 11 }
    } else if (path === '/portaria/unidades') {
      result = {
        items: [
          page === 1
            ? { id: 'unit-a', identificacao: 'Bloco A / 101' }
            : { id: 'unit-b', identificacao: 'Bloco B / 202' },
        ],
        page,
        page_size: 100,
        total: 2,
      }
    } else if (path.endsWith('/moradores')) {
      result = {
        items: [
          page === 1
            ? { id: 'resident-a', nome: 'Ana Exemplo' }
            : { id: 'resident-b', nome: 'Bruno Exemplo' },
        ],
        page,
        page_size: 100,
        total: 2,
      }
    } else if (path === '/funcionarios') {
      result = {
        items: [
          page === 1
            ? { id: 'employee-a', nome: 'Carlos Exemplo' }
            : { id: 'employee-b', nome: 'Diana Exemplo' },
        ],
        page,
        page_size: 100,
        total: 2,
      }
    } else if (path === '/arquivos/file-a/download') {
      result = { url: 'https://storage.exemplo.test/foto.png?assinatura=ficticia', expires_in: 60 }
    }
    return {
      data: result,
      status: 200,
      statusText: 'OK',
      headers: { 'content-type': 'application/json' },
      config,
    }
  }

  return {
    api: createEncomendasClient(session.http),
    requests,
    close: async () => {},
  }
}

test('consulta encomendas com filtros e paginação no contexto autenticado', async () => {
  const testApi = await startApi()
  try {
    const page = await testApi.api.list({
      search: ' Caixa ',
      status: 'aguardando_retirada',
      page: 2,
    })
    assert.equal(page.total, 11)
    const request = testApi.requests[0]
    assert.equal(request.method, 'GET')
    assert.equal(request.authorization, 'Bearer access-a')
    assert.equal(request.url, '/encomendas')
    assert.deepEqual(request.params, {
      busca: 'Caixa',
      status: 'aguardando_retirada',
      page: 2,
      page_size: 20,
    })
  } finally {
    await testApi.close()
  }
})

test('consulta os detalhes de uma encomenda com a sessão autenticada', async () => {
  const testApi = await startApi()
  const result = await testApi.api.get('package-a')
  assert.equal(result.id, 'package-a')
  assert.equal(testApi.requests[0].url, '/encomendas/package-a')
  assert.equal(testApi.requests[0].authorization, 'Bearer access-a')
})

test('registra campos e foto em uma única requisição multipart', async () => {
  const testApi = await startApi()
  try {
    const photo = new File([new Uint8Array([1, 2, 3])], 'nota.png', { type: 'image/png' })
    await testApi.api.register({
      unidade_id: 'unit-a',
      destinatario_morador_unidade_id: 'resident-a',
      descricao: '  Caixa de livros  ',
      recebido_por_funcionario_id: 'employee-a',
      foto: photo,
    })

    const request = testApi.requests[0]
    const body = request.body as FormData
    assert.equal(request.method, 'POST')
    assert.equal(request.authorization, 'Bearer access-a')
    assert.ok(body instanceof FormData)
    for (const field of [
      'unidade_id',
      'destinatario_morador_unidade_id',
      'descricao',
      'recebido_por_funcionario_id',
      'foto',
    ]) {
      assert.ok(body.has(field), `campo multipart ${field}`)
    }
    assert.equal((body.get('foto') as File).name, 'nota.png')
    assert.equal(body.get('descricao'), 'Caixa de livros')
    assert.ok(!body.has('condominio_id'))
  } finally {
    await testApi.close()
  }
})

test('carrega opções de formulário e usa as ações de entrega e confirmação', async () => {
  const testApi = await startApi()
  try {
    const units = await testApi.api.units()
    const residents = await testApi.api.residents('unit-a', true)
    const employees = await testApi.api.employees()
    assert.deepEqual(
      units.map((unit) => unit.id),
      ['unit-a', 'unit-b'],
    )
    assert.deepEqual(
      residents.map((resident) => resident.id),
      ['resident-a', 'resident-b'],
    )
    assert.deepEqual(
      employees.map((employee) => employee.id),
      ['employee-a', 'employee-b'],
    )
    await testApi.api.deliver('package-a', {
      recebedor_morador_unidade_id: 'resident-a',
      entregue_por_funcionario_id: 'employee-a',
    })
    await testApi.api.confirm('package-a')
    const requests = testApi.requests
    assert.equal(requests[0].url, '/portaria/unidades')
    assert.deepEqual(requests[0].params, { page: 1, page_size: 100 })
    assert.deepEqual(requests[1].params, { page: 2, page_size: 100 })
    assert.equal(requests[2].url, '/portaria/unidades/unit-a/moradores')
    assert.deepEqual(requests[2].params, {
      somente_confirmaveis: true,
      page: 1,
      page_size: 100,
    })
    assert.equal(requests[3].url, '/portaria/unidades/unit-a/moradores')
    assert.deepEqual(requests[3].params, {
      somente_confirmaveis: true,
      page: 2,
      page_size: 100,
    })
    assert.equal(requests[4].url, '/funcionarios')
    assert.deepEqual(requests[4].params, { ativo: true, page: 1, page_size: 100 })
    assert.deepEqual(requests[5].params, { ativo: true, page: 2, page_size: 100 })
    assert.equal(requests[6].url, '/encomendas/package-a/entrega')
    assert.deepEqual(JSON.parse(String(requests[6].body)), {
      recebedor_morador_unidade_id: 'resident-a',
      entregue_por_funcionario_id: 'employee-a',
    })
    assert.equal(requests[7].url, '/encomendas/package-a/confirmacao')
    assert.deepEqual(JSON.parse(String(requests[7].body)), {})
  } finally {
    await testApi.close()
  }
})

test('consulta a URL protegida da foto apenas pela API de arquivos', async () => {
  const testApi = await startApi()
  try {
    const url = await testApi.api.photoUrl('file-a')
    assert.equal(url, 'https://storage.exemplo.test/foto.png?assinatura=ficticia')
    assert.equal(testApi.requests[0].url, '/arquivos/file-a/download')
    assert.equal(testApi.requests[0].authorization, 'Bearer access-a')
  } finally {
    await testApi.close()
  }
})
