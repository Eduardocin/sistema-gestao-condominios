import axios from 'axios'
import type { InternalAxiosRequestConfig } from 'axios'
import type { Condominium, Identity, LoginResponse, SessionSnapshot, SessionStorage } from './types.ts'

export const sessionKey = 'gestao-condominios.session.v1'
interface Credentials { access_token: string; refresh_token: string; condominios: Condominium[] }
type SessionRequest = InternalAxiosRequestConfig & { sessionEpoch?: number; sessionRetried?: boolean }

export function accessMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    switch (error.response?.status) {
      case 401: return 'E-mail ou senha incorretos.'
      case 403: return 'Você não tem permissão para este acesso.'
      case 404: return 'O vínculo com este condomínio não está mais disponível.'
      case 422: return 'Confira os dados informados e tente novamente.'
      case 429: return 'Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.'
      default: return 'Não foi possível conectar ao serviço. Tente novamente.'
    }
  }
  return error instanceof Error ? error.message : 'Não foi possível concluir o acesso. Tente novamente.'
}

function isCondominium(value: unknown): value is Condominium {
  if (typeof value !== 'object' || value === null) return false
  const c = value as Partial<Condominium>
  return typeof c.id === 'string' && typeof c.nome === 'string' && ['morador', 'funcionario', 'administracao'].includes(c.perfil ?? '') && ['ativo', 'desativado'].includes(c.status ?? '')
}

function readCredentials(storage: SessionStorage | undefined): Credentials | null {
  try {
    const saved = storage?.getItem(sessionKey)
    if (!saved) return null
    const data = JSON.parse(saved) as Partial<Credentials> | null
    if (!data || typeof data.access_token !== 'string' || !data.access_token || typeof data.refresh_token !== 'string' || !data.refresh_token || !Array.isArray(data.condominios) || !data.condominios.every(isCondominium)) return null
    return data as Credentials
  } catch { return null }
}

/** O serviço não depende de React: uma única fonte de sessão para telas e HTTP. */
export function createSessionClient(baseURL: string, storage?: SessionStorage) {
  const publicHttp = axios.create({ baseURL, timeout: 10000 })
  const http = axios.create({ baseURL, timeout: 10000 })
  let credentials = readCredentials(storage)
  let epoch = 0
  let snapshot: SessionSnapshot = { status: 'loading', identity: null, condominiums: [], message: null }
  const listeners = new Set<() => void>()
  let refreshing: { epoch: number; promise: Promise<void> } | null = null
  let restoring: { epoch: number; promise: Promise<void> } | null = null

  function publish(value: SessionSnapshot) {
    snapshot = value
    listeners.forEach((listener) => listener())
  }

  function persist() {
    try {
      if (credentials) storage?.setItem(sessionKey, JSON.stringify(credentials))
      else storage?.removeItem(sessionKey)
    } catch { /* Em navegadores que bloqueiam storage, a sessão continua em memória. */ }
  }

  function logout(message: string | null = null) {
    epoch++
    credentials = null
    persist()
    publish({ status: 'anonymous', identity: null, condominiums: [], message })
  }

  function assertCurrent(expected: number) {
    if (epoch !== expected) throw new Error('A sessão mudou. Tente novamente.')
  }

  function refresh(expected: number): Promise<void> {
    if (refreshing?.epoch === expected) return refreshing.promise
    const refreshToken = credentials?.refresh_token
    const promise = (async () => {
      try {
        if (!refreshToken) throw new Error('Sessão indisponível.')
        const { data } = await publicHttp.post<{ access_token: string }>('/auth/refresh', { refresh_token: refreshToken })
        assertCurrent(expected)
        if (!credentials || typeof data.access_token !== 'string' || !data.access_token) throw new Error('Resposta de sessão inválida.')
        credentials = { ...credentials, access_token: data.access_token }
        persist()
      } catch (error) {
        if (epoch === expected && axios.isAxiosError(error) && [401, 403].includes(error.response?.status ?? 0)) logout('Sua sessão expirou. Entre novamente.')
        throw error
      } finally {
        if (refreshing?.epoch === expected) refreshing = null
      }
    })()
    refreshing = { epoch: expected, promise }
    return promise
  }

  http.interceptors.request.use((original) => {
    const config = original as SessionRequest
    if (config.sessionEpoch !== undefined) assertCurrent(config.sessionEpoch)
    config.sessionEpoch = epoch
    if (credentials) config.headers.set('Authorization', `Bearer ${credentials.access_token}`)
    return config
  })

  http.interceptors.response.use((response) => {
    assertCurrent((response.config as SessionRequest).sessionEpoch!)
    return response
  }, async (error: unknown) => {
    if (!axios.isAxiosError(error)) throw error
    const config = error.config as SessionRequest | undefined
    if (!config || config.sessionEpoch !== epoch || error.response?.status !== 401 || !credentials) throw error
    if (config.sessionRetried) {
      logout('Sua sessão expirou. Entre novamente.')
      throw error
    }
    config.sessionRetried = true
    // Uma resposta 401 antiga pode chegar depois de outra chamada já renovar.
    if (config.headers.get('Authorization') === `Bearer ${credentials.access_token}`) await refresh(epoch)
    assertCurrent(config.sessionEpoch)
    return http.request(config)
  })

  async function loadIdentity(expected: number) {
    const { data } = await http.get<Identity>('/auth/me')
    assertCurrent(expected)
    publish({ status: 'authenticated', identity: data, condominiums: credentials?.condominios ?? [], message: null })
  }

  async function acceptLogin(data: LoginResponse, expected: number) {
    assertCurrent(expected)
    credentials = { access_token: data.access_token, refresh_token: data.refresh_token, condominios: data.condominios }
    persist()
    try { await loadIdentity(expected) }
    catch (error) {
      if (epoch === expected) publish({ status: 'error', identity: null, condominiums: data.condominios, message: accessMessage(error) })
      throw error
    }
  }

  async function login(email: string, password: string) {
    logout()
    const expected = epoch
    try {
      const { data } = await publicHttp.post<LoginResponse>('/auth/login', { identificador: email.trim(), senha: password })
      await acceptLogin(data, expected)
    } catch (error) { throw new Error(accessMessage(error), { cause: error }) }
  }

  async function selectCondominium(id: string) {
    const expected = epoch
    const { data } = await http.post<LoginResponse>('/auth/selecionar-condominio', { condominio_id: id })
    assertCurrent(expected)
    // Não deixar requisições do condomínio anterior preencherem o novo contexto.
    epoch++
    publish({ status: 'loading', identity: null, condominiums: data.condominios, message: null })
    await acceptLogin(data, epoch)
  }

  function restore(): Promise<void> {
    if (restoring?.epoch === epoch) return restoring.promise
    if (!credentials) { logout(snapshot.message); return Promise.resolve() }
    const expected = epoch
    publish({ ...snapshot, status: 'loading', identity: null, message: null })
    const promise = loadIdentity(expected).catch((error: unknown) => {
      if (epoch === expected) publish({ status: 'error', identity: null, condominiums: credentials?.condominios ?? [], message: accessMessage(error) })
    }).finally(() => { if (restoring?.epoch === expected) restoring = null })
    restoring = { epoch: expected, promise }
    return promise
  }

  return {
    http, login, selectCondominium, restore, logout,
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } },
  }
}

export type SessionClient = ReturnType<typeof createSessionClient>
