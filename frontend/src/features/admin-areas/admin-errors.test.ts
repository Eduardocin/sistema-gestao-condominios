import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AxiosError, AxiosHeaders } from 'axios'
import {
  GENERIC_ERROR,
  REASON_MESSAGES,
  RESPONSIBLE_NOT_FOUND,
  adminErrorMessage,
  isConflict,
} from './admin-errors.ts'

function apiError(status: number, error?: { code?: string; message?: string; reason?: string }) {
  const config = { headers: new AxiosHeaders() }
  return new AxiosError('falhou', 'ERR_BAD_REQUEST', config, null, {
    status,
    statusText: '',
    headers: {},
    config,
    data: error ? { error } : undefined,
  })
}

test('cada reason da API tem mensagem própria, sem depender do texto do backend', () => {
  const reasons = [
    ['nome_duplicado', 409],
    ['foto_invalida', 422],
    ['reservas_fora_do_horario', 409],
    ['area_ja_desativada', 409],
    ['area_ja_ativa', 409],
    ['reserva_ja_cancelada', 409],
    ['reserva_encerrada', 409],
  ] as const
  for (const [reason, status] of reasons) {
    const message = adminErrorMessage(
      apiError(status, { code: 'conflict', message: 'texto da API', reason }),
      'area',
    )
    assert.equal(message, REASON_MESSAGES[reason], reason)
    assert.notEqual(message, GENERIC_ERROR)
  }
  assert.equal(new Set(reasons.map(([reason]) => REASON_MESSAGES[reason])).size, reasons.length)
})

test('404 no cancelamento aponta o responsável; nas áreas, a área', () => {
  const notFound = apiError(404, { code: 'not_found', message: 'Recurso não encontrado.' })
  assert.equal(adminErrorMessage(notFound, 'cancelamento'), RESPONSIBLE_NOT_FOUND)
  assert.match(adminErrorMessage(notFound, 'area'), /área/)
})

test('409 e 422 sem reason conhecido mostram a mensagem da API', () => {
  const missing = apiError(422, {
    code: 'validation_error',
    message: 'Informe o motivo e o responsável pelo cancelamento.',
  })
  assert.equal(
    adminErrorMessage(missing, 'cancelamento'),
    'Informe o motivo e o responsável pelo cancelamento.',
  )
  const unknown = apiError(409, { code: 'conflict', message: 'Outro conflito.', reason: 'novo' })
  assert.equal(adminErrorMessage(unknown, 'area'), 'Outro conflito.')
})

test('403, 503, erro de rede e erro sem corpo têm mensagens próprias ou genérica', () => {
  assert.match(adminErrorMessage(apiError(403, { code: 'forbidden' }), 'area'), /perfil/)
  assert.match(adminErrorMessage(apiError(503, { code: 'storage_unavailable' }), 'area'), /fotos/)
  assert.equal(adminErrorMessage(apiError(500), 'area'), GENERIC_ERROR)
  assert.equal(adminErrorMessage(new Error('rede'), 'carregar'), GENERIC_ERROR)
  assert.equal(adminErrorMessage(apiError(422), 'area'), GENERIC_ERROR)
})

test('isConflict reconhece só o 409', () => {
  assert.equal(isConflict(apiError(409, { reason: 'reserva_ja_cancelada' })), true)
  assert.equal(isConflict(apiError(422)), false)
  assert.equal(isConflict(new Error('x')), false)
})
