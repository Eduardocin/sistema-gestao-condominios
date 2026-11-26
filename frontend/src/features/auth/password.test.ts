import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { test } from 'node:test'
import axios, { AxiosError } from 'axios'
import {
  changePasswordError,
  isInvalidResetToken,
  passwordRuleError,
  recoveryRequestError,
  resetPasswordError,
} from './password.ts'
import { createSessionClient, sessionKey } from './session.ts'

const failure = (status: number, reason?: string) =>
  new AxiosError('x', undefined, undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new axios.AxiosHeaders() },
    data: { error: { message: 'm', ...(reason ? { reason } : {}) } },
  })

test('a regra da senha nova repete a do cadastro', () => {
  assert.equal(passwordRuleError('senha1234', 'senha1234'), '')
  assert.match(passwordRuleError('curta1', 'curta1'), /8 a 128/)
  assert.match(passwordRuleError('somenteletras', 'somenteletras'), /letra e um número/)
  assert.match(passwordRuleError('12345678', '12345678'), /letra e um número/)
  assert.match(
    passwordRuleError('ana1@exemplo.com', 'ana1@exemplo.com', 'Ana1@Exemplo.com'),
    /diferente do e-mail/,
  )
  assert.match(passwordRuleError('senha1234', 'senha4321'), /iguais/)
  assert.match(passwordRuleError('a1'.repeat(65), 'a1'.repeat(65)), /8 a 128/)
})

test('traduz os erros da troca, da redefinição e do pedido de recuperação', () => {
  assert.match(changePasswordError(failure(422, 'senha_atual_incorreta')), /atual está incorreta/)
  assert.match(changePasswordError(failure(422, 'senha_nova_igual_atual')), /diferente da atual/)
  assert.match(changePasswordError(failure(422)), /8 a 128/)
  assert.match(changePasswordError(failure(403)), /não pode trocar/)
  assert.match(changePasswordError(failure(429)), /Muitas tentativas/)
  assert.match(changePasswordError(new Error('rede')), /Tente novamente/)
  assert.equal(isInvalidResetToken(failure(422, 'token_invalido')), true)
  assert.equal(isInvalidResetToken(failure(422, 'outro')), false)
  assert.match(
    resetPasswordError(failure(422, 'token_invalido')),
    /inválido, expirou ou já foi usado/,
  )
  assert.match(resetPasswordError(failure(422, 'outro')), /8 a 128/)
  assert.match(resetPasswordError(failure(422, 'outro')), /diferente do e-mail/)
  assert.match(resetPasswordError(failure(429)), /Muitas tentativas/)
  assert.match(recoveryRequestError(failure(422)), /e-mail válido/)
  assert.match(recoveryRequestError(failure(429)), /Muitas tentativas/)
  assert.match(recoveryRequestError(failure(500)), /Tente novamente/)
})

const condominium = { id: 'c', nome: 'Aurora', perfil: 'morador', status: 'ativo' }
const identity = {
  usuario: { id: 'u', nome: 'Ana', email: 'ana@example.com' },
  condominio: condominium,
  unidades: [],
  administrador_plataforma: false,
}
const session = (access: string) => ({
  ...identity,
  access_token: access,
  refresh_token: 'r2',
  expires_in: 900,
  token_type: 'bearer',
  condominios: [condominium],
  requer_selecao: false,
})

async function server(
  handler: (req: IncomingMessage, body: Record<string, unknown>, res: ServerResponse) => void,
) {
  const requests: {
    method?: string
    url?: string
    auth?: string
    body: Record<string, unknown>
  }[] = []
  const api = createServer(async (req, res) => {
    const chunks: Buffer[] = []
    for await (const chunk of req) chunks.push(Buffer.from(chunk))
    const body = chunks.length
      ? (JSON.parse(Buffer.concat(chunks).toString()) as Record<string, unknown>)
      : {}
    requests.push({ method: req.method, url: req.url, auth: req.headers.authorization, body })
    res.setHeader('Content-Type', 'application/json')
    handler(req, body, res)
  })
  await new Promise<void>((resolve) => api.listen(0, '127.0.0.1', resolve))
  const address = api.address()
  assert.ok(address && typeof address !== 'string')
  return {
    url: `http://127.0.0.1:${address.port}`,
    requests,
    close: () =>
      new Promise<void>((resolve, reject) => {
        api.closeAllConnections()
        api.close((error) => (error ? reject(error) : resolve()))
      }),
  }
}

test('pedido de recuperação e redefinição usam as rotas públicas, sem Authorization', async () => {
  const api = await server((_req, _body, res) => {
    res.statusCode = 202
    res.end('{}')
  })
  try {
    const client = createSessionClient(api.url, undefined)
    await client.requestPasswordReset('  ana@example.com ')
    await client.resetPassword('tok', 'senha1234')
    assert.deepEqual(
      api.requests.map(({ method, url, auth, body }) => [method, url, auth, body]),
      [
        ['POST', '/contas/recuperacao-senha', undefined, { email: 'ana@example.com' }],
        ['POST', '/contas/redefinicao-senha', undefined, { token: 'tok', senha_nova: 'senha1234' }],
      ],
    )
  } finally {
    await api.close()
  }
})

test('a troca de senha logada guarda os tokens novos e avisa antes de recarregar a identidade', async () => {
  const values = new Map<string, string>([
    [
      sessionKey,
      JSON.stringify({ access_token: 'old', refresh_token: 'r1', condominios: [condominium] }),
    ],
  ])
  const storage = {
    getItem: (k: string) => values.get(k) ?? null,
    setItem: (k: string, v: string) => {
      values.set(k, v)
    },
    removeItem: (k: string) => {
      values.delete(k)
    },
  }
  const api = await server((req, _body, res) => {
    if (req.url === '/contas/me/senha') {
      res.end(JSON.stringify(session('new')))
      return
    }
    if (req.url === '/auth/me') {
      res.end(JSON.stringify(identity))
      return
    }
    res.statusCode = 404
    res.end('{}')
  })
  try {
    const client = createSessionClient(api.url, storage)
    let notified = false
    await client.changePassword('senha1234', 'novasenha9', () => {
      notified = true
    })
    assert.ok(notified)
    assert.deepEqual(api.requests[0].body, { senha_atual: 'senha1234', senha_nova: 'novasenha9' })
    assert.equal(api.requests[0].auth, 'Bearer old')
    assert.equal(api.requests[1].auth, 'Bearer new')
    assert.equal(JSON.parse(values.get(sessionKey) ?? '{}').access_token, 'new')
    assert.equal(client.getSnapshot().status, 'authenticated')
  } finally {
    await api.close()
  }
})

test('senha atual incorreta não altera a sessão nem avisa', async () => {
  const values = new Map<string, string>([
    [
      sessionKey,
      JSON.stringify({ access_token: 'old', refresh_token: 'r1', condominios: [condominium] }),
    ],
  ])
  const storage = {
    getItem: (k: string) => values.get(k) ?? null,
    setItem: (k: string, v: string) => {
      values.set(k, v)
    },
    removeItem: (k: string) => {
      values.delete(k)
    },
  }
  const api = await server((_req, _body, res) => {
    res.statusCode = 422
    res.end(JSON.stringify({ error: { message: 'm', reason: 'senha_atual_incorreta' } }))
  })
  try {
    const client = createSessionClient(api.url, storage)
    let notified = false
    await assert.rejects(
      client.changePassword('errada123', 'novasenha9', () => {
        notified = true
      }),
      (error) => changePasswordError(error).includes('atual está incorreta'),
    )
    assert.equal(notified, false)
    assert.equal(JSON.parse(values.get(sessionKey) ?? '{}').access_token, 'old')
  } finally {
    await api.close()
  }
})
