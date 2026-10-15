import { http } from '../../services/http'

export async function checkHealth(signal: AbortSignal): Promise<void> {
  const { data } = await http.get<unknown>('/health', { signal })
  if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
    throw new Error('Resposta inesperada da API')
  }
}
