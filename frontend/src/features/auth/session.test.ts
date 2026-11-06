import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { test } from 'node:test'
import { createSessionClient, sessionKey } from './session.ts'

const condominium = { id: 'condo-a', nome: 'Residencial Aurora', perfil: 'morador', status: 'ativo' }
const identity = { usuario: { id: 'user-a', nome: 'Ana Exemplo', email: 'ana@example.com' }, condominio: condominium, unidades: [{ id: 'unit-a', identificacao: '101' }], administrador_plataforma: false }
const loginResponse = { ...identity, access_token: 'access-a', refresh_token: 'refresh-a', expires_in: 900, token_type: 'bearer', condominios: [condominium], requer_selecao: false }

function memoryStorage() {
  const values = new Map<string, string>()
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value) }, removeItem: (key: string) => { values.delete(key) } }
}

async function fixture(handler: (req: IncomingMessage, body: Record<string, unknown>, res: ServerResponse) => void | Promise<void>) {
  const server = createServer(async (req, res) => {
    const chunks: Buffer[] = []
    for await (const chunk of req) chunks.push(Buffer.from(chunk))
    const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) as Record<string, unknown> : {}
    res.setHeader('Content-Type', 'application/json')
    await handler(req, body, res)
  })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  assert.ok(address && typeof address !== 'string')
  return { url: `http://127.0.0.1:${address.port}`, close: () => new Promise<void>((resolve, reject) => { server.closeAllConnections(); server.close((error) => error ? reject(error) : resolve()) }) }
}

function json(res: ServerResponse, data: unknown, status = 200) {
  res.statusCode = status
  res.end(JSON.stringify(data))
}

test('login envia o contrato, valida /me com Bearer e persiste somente tokens e vínculos', async () => {
  const storage = memoryStorage()
  const api = await fixture((req, body, res) => {
    if (req.url === '/auth/login') {
      assert.deepEqual(body, { identificador: 'ana@example.com', senha: 'senha-ficticia' })
      assert.equal(req.headers.authorization, undefined)
      json(res, loginResponse)
    } else {
      assert.equal(req.url, '/auth/me')
      assert.equal(req.headers.authorization, 'Bearer access-a')
      json(res, identity)
    }
  })
  try {
    const client = createSessionClient(api.url, storage)
    await client.login('ana@example.com', 'senha-ficticia')
    assert.equal(client.getSnapshot().identity?.usuario.nome, 'Ana Exemplo')
    assert.equal(client.getSnapshot().status, 'authenticated')
    const persisted = JSON.parse(storage.getItem(sessionKey)!)
    assert.deepEqual(Object.keys(persisted).sort(), ['access_token', 'condominios', 'refresh_token'])
    assert.ok(!storage.getItem(sessionKey)!.includes('senha-ficticia'))
    const restored = createSessionClient(api.url, storage)
    assert.equal(restored.getSnapshot().identity, null)
    await restored.restore()
    assert.deepEqual(restored.getSnapshot().identity, identity)
    restored.logout()
    assert.equal(storage.getItem(sessionKey), null)
    assert.equal(restored.getSnapshot().status, 'anonymous')
  } finally { await api.close() }
})

test('seleção e recarga preservam vínculos, mas usam /me como contexto definitivo', async () => {
  const storage = memoryStorage()
  let selected = false
  const condominios = [condominium, { ...condominium, id: 'condo-b', nome: 'Residencial Ipê', perfil: 'funcionario' }]
  const api = await fixture((req, body, res) => {
    if (req.url === '/auth/login') json(res, { ...loginResponse, condominio: null, condominios, requer_selecao: true })
    else if (req.url === '/auth/selecionar-condominio') {
      assert.deepEqual(body, { condominio_id: 'condo-b' })
      selected = true
      json(res, { ...loginResponse, access_token: 'access-b', condominio: condominios[1], condominios })
    } else json(res, { ...identity, condominio: selected ? condominios[1] : null })
  })
  try {
    const client = createSessionClient(api.url, storage)
    await client.login('ana@example.com', 'senha')
    const restored = createSessionClient(api.url, storage)
    await restored.restore()
    assert.equal(restored.getSnapshot().condominiums.length, 2)
    assert.equal(restored.getSnapshot().identity?.condominio, null)
    await restored.selectCondominium('condo-b')
    assert.equal(restored.getSnapshot().identity?.condominio?.perfil, 'funcionario')
  } finally { await api.close() }
})

for (const status of ['pendente', 'rejeitado']) {
  test(`restauração aceita condomínio ${status} selecionado ou em outro vínculo`, async () => {
    const unavailable = { ...condominium, id: 'condo-pending', perfil: 'administracao', status }
    let selected = unavailable
    let meRequests = 0
    const api = await fixture((req, _body, res) => {
      assert.equal(req.url, '/auth/me')
      assert.equal(req.headers.authorization, 'Bearer access-a')
      meRequests++
      json(res, { ...identity, condominio: selected })
    })
    try {
      for (const activeSelected of [false, true]) {
        selected = activeSelected ? condominium : unavailable
        const storage = memoryStorage()
        const saved = JSON.stringify({ access_token: 'access-a', refresh_token: 'refresh-a', condominios: [condominium, unavailable] })
        storage.setItem(sessionKey, saved)
        const client = createSessionClient(api.url, storage)
        assert.equal(client.getSnapshot().identity, null)
        await client.restore()
        assert.equal(client.getSnapshot().status, 'authenticated')
        assert.deepEqual(client.getSnapshot().identity?.condominio, selected)
        assert.deepEqual(client.getSnapshot().condominiums, [condominium, unavailable])
        assert.equal(storage.getItem(sessionKey), saved)
      }
      assert.equal(meRequests, 2)
    } finally { await api.close() }
  })
}

test('estado desconhecido de condomínio continua recusado na sessão armazenada', async () => {
  let meRequests = 0
  const api = await fixture((_req, _body, res) => { meRequests++; json(res, identity) })
  try {
    const storage = memoryStorage()
    storage.setItem(sessionKey, JSON.stringify({ access_token: 'access-a', refresh_token: 'refresh-a', condominios: [{ ...condominium, status: 'estado-invalido' }] }))
    const client = createSessionClient(api.url, storage)
    await client.restore()
    assert.equal(client.getSnapshot().status, 'anonymous')
    assert.equal(storage.getItem(sessionKey), null)
    assert.equal(meRequests, 0)
  } finally { await api.close() }
})

test('401 concorrentes compartilham refresh, repetem uma vez e preservam refresh_token', async () => {
  const storage = memoryStorage()
  storage.setItem(sessionKey, JSON.stringify({ access_token: 'expired', refresh_token: 'refresh-a', condominios: [condominium] }))
  let refreshes = 0
  const api = await fixture(async (req, body, res) => {
    if (req.url === '/auth/refresh') {
      refreshes++
      assert.deepEqual(body, { refresh_token: 'refresh-a' })
      assert.equal(req.headers.authorization, undefined)
      await new Promise((resolve) => setTimeout(resolve, 30))
      json(res, { access_token: 'renewed', token_type: 'bearer', expires_in: 900 })
    } else if (req.headers.authorization === 'Bearer renewed') json(res, identity)
    else json(res, {}, 401)
  })
  try {
    const client = createSessionClient(api.url, storage)
    await Promise.all([client.restore(), client.http.get('/resource')])
    assert.equal(refreshes, 1)
    assert.equal(client.getSnapshot().status, 'authenticated')
    assert.equal(JSON.parse(storage.getItem(sessionKey)!).refresh_token, 'refresh-a')
  } finally { await api.close() }
})

test('refresh inválido encerra sessão e 403 de recurso não renova nem remove a sessão', async () => {
  const storage = memoryStorage()
  let forbidden = true
  let refreshes = 0
  const api = await fixture((req, _body, res) => {
    if (req.url === '/auth/login') json(res, loginResponse)
    else if (req.url === '/auth/me') json(res, identity)
    else if (req.url === '/auth/refresh') { refreshes++; json(res, {}, 401) }
    else json(res, {}, forbidden ? 403 : 401)
  })
  try {
    const client = createSessionClient(api.url, storage)
    await client.login('ana@example.com', 'senha')
    await assert.rejects(client.http.get('/resource'))
    assert.equal(refreshes, 0)
    assert.equal(client.getSnapshot().status, 'authenticated')
    forbidden = false
    await assert.rejects(client.http.get('/resource'))
    assert.equal(refreshes, 1)
    assert.equal(client.getSnapshot().status, 'anonymous')
    assert.match(client.getSnapshot().message!, /expirou/i)
    assert.equal(storage.getItem(sessionKey), null)
  } finally { await api.close() }
})

test('falha temporária ao restaurar preserva tokens e permite tentar novamente', async () => {
  const storage = memoryStorage()
  storage.setItem(sessionKey, JSON.stringify({ access_token: 'access-a', refresh_token: 'refresh-a', condominios: [] }))
  let unavailable = true
  const api = await fixture((_req, _body, res) => json(res, unavailable ? {} : identity, unavailable ? 503 : 200))
  try {
    const client = createSessionClient(api.url, storage)
    await client.restore()
    assert.equal(client.getSnapshot().status, 'error')
    assert.ok(storage.getItem(sessionKey))
    unavailable = false
    await client.restore()
    assert.equal(client.getSnapshot().status, 'authenticated')
  } finally { await api.close() }
})

test('logout durante refresh impede que a resposta restaure a sessão', async () => {
  const storage = memoryStorage()
  storage.setItem(sessionKey, JSON.stringify({ access_token: 'expired', refresh_token: 'refresh-a', condominios: [] }))
  let release!: () => void
  const pending = new Promise<void>((resolve) => { release = resolve })
  let started!: () => void
  const refreshing = new Promise<void>((resolve) => { started = resolve })
  const api = await fixture(async (req, _body, res) => {
    if (req.url === '/auth/refresh') { started(); await pending; json(res, { access_token: 'renewed' }) }
    else json(res, {}, 401)
  })
  try {
    const client = createSessionClient(api.url, storage)
    const restoring = client.restore()
    await refreshing
    client.logout()
    release()
    await restoring
    assert.equal(client.getSnapshot().status, 'anonymous')
    assert.equal(storage.getItem(sessionKey), null)
  } finally { release(); await api.close() }
})

test('senha incorreta e excesso de tentativas têm mensagens específicas sem persistir sessão', async () => {
  let status = 401
  const api = await fixture((_req, _body, res) => json(res, {}, status))
  try {
    const storage = memoryStorage()
    const client = createSessionClient(api.url, storage)
    await assert.rejects(client.login('ana@example.com', 'errada'), /E-mail ou senha incorretos/)
    status = 429
    await assert.rejects(client.login('ana@example.com', 'errada'), /Muitas tentativas/)
    assert.equal(storage.getItem(sessionKey), null)
  } finally { await api.close() }
})

test('armazenamento corrompido ou bloqueado não quebra a inicialização', async () => {
  const storage = memoryStorage()
  storage.setItem(sessionKey, '{broken')
  const client = createSessionClient('http://127.0.0.1:1', storage)
  await client.restore()
  assert.equal(client.getSnapshot().status, 'anonymous')
  const blocked = createSessionClient('http://127.0.0.1:1', { getItem() { throw new Error('bloqueado') }, setItem() { throw new Error('bloqueado') }, removeItem() { throw new Error('bloqueado') } })
  await blocked.restore()
  assert.equal(blocked.getSnapshot().status, 'anonymous')
})
