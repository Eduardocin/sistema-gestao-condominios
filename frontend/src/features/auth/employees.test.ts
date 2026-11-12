import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { test } from 'node:test'
import { createSessionClient, sessionKey } from './session.ts'
import { createEmployeesClient } from '../employees/api.ts'

test('gestão envia filtros paginados, cria responsável, cadastra e desliga funcionário no contexto autenticado', async () => {
  const requests: { method?: string; url?: string; body: unknown }[] = []
  const employee = {
    id: 'employee-a',
    nome: 'João Exemplo',
    funcao: 'porteiro',
    telefone: '11987654321',
    email: 'joao@example.com',
    foto_arquivo_id: null,
    ativo: true,
    desligado_em: null,
  }
  const server = createServer(async (req, res) => {
    assert.equal(req.headers.authorization, 'Bearer access-a')
    const chunks: Buffer[] = []
    for await (const chunk of req) chunks.push(Buffer.from(chunk))
    const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : null
    requests.push({ method: req.method, url: req.url, body })
    res.setHeader('Content-Type', 'application/json')
    if (req.url === '/responsaveis-administracao')
      res.end(
        JSON.stringify(
          req.method === 'POST' ? { id: 'responsible-a', nome: body.nome, ativo: true } : [],
        ),
      )
    else if (req.method === 'GET')
      res.end(JSON.stringify({ items: [employee], page: 2, page_size: 20, total: 21 }))
    else res.end(JSON.stringify({ ...employee, ativo: !req.url?.endsWith('/desligamento') }))
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  assert.ok(address && typeof address !== 'string')
  const client = createSessionClient(`http://127.0.0.1:${address.port}`, {
    getItem: (key) =>
      key === sessionKey
        ? JSON.stringify({ access_token: 'access-a', refresh_token: 'refresh-a', condominios: [] })
        : null,
    setItem() {},
    removeItem() {},
  })
  try {
    const api = createEmployeesClient(client.http)
    assert.deepEqual(await api.responsibles(), [])
    assert.equal((await api.addResponsible(' Maria Exemplo ')).nome, 'Maria Exemplo')
    const list = await api.list({ active: false, search: ' João ', page: 2 })
    assert.equal(list.total, 21)
    await api.create({
      nome: ' João Exemplo ',
      funcao: 'porteiro',
      telefone: '11987654321',
      email: 'JOAO@EXAMPLE.COM',
      responsavel_id: 'responsible-a',
    })
    assert.equal((await api.dismiss('employee-a', 'responsible-a')).ativo, false)
    assert.deepEqual(requests, [
      { method: 'GET', url: '/responsaveis-administracao', body: null },
      { method: 'POST', url: '/responsaveis-administracao', body: { nome: 'Maria Exemplo' } },
      {
        method: 'GET',
        url: '/funcionarios?ativo=false&busca=Jo%C3%A3o&page=2&page_size=20',
        body: null,
      },
      {
        method: 'POST',
        url: '/funcionarios',
        body: {
          nome: 'João Exemplo',
          funcao: 'porteiro',
          telefone: '11987654321',
          email: 'joao@example.com',
          responsavel_id: 'responsible-a',
        },
      },
      {
        method: 'POST',
        url: '/funcionarios/employee-a/desligamento',
        body: { responsavel_id: 'responsible-a' },
      },
    ])
  } finally {
    server.closeAllConnections()
    await new Promise<void>((resolve) => server.close(() => resolve()))
  }
})
