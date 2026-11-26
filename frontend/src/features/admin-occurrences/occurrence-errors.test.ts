import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AxiosError, AxiosHeaders } from 'axios'
import {
  ALREADY_RESOLVED,
  GENERIC_ERROR,
  RESPONSIBLE_NOT_FOUND,
  isAlreadyResolved,
  occurrenceErrorMessage,
} from './occurrence-errors.ts'

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

const resolved = apiError(409, {
  code: 'conflict',
  message: 'A ocorrência já está resolvida.',
  reason: 'ocorrencia_ja_resolvida',
})

test('409 ocorrencia_ja_resolvida tem mensagem própria e é reconhecido', () => {
  assert.equal(isAlreadyResolved(resolved), true)
  assert.equal(occurrenceErrorMessage(resolved, 'resolucao'), ALREADY_RESOLVED)
  assert.equal(isAlreadyResolved(apiError(409, { reason: 'outro' })), false)
  assert.equal(isAlreadyResolved(new Error('x')), false)
})

test('404 ao responder ou resolver aponta o responsável; ao carregar, a ocorrência', () => {
  const notFound = apiError(404, { code: 'not_found', message: 'Recurso não encontrado.' })
  assert.equal(occurrenceErrorMessage(notFound, 'resposta'), RESPONSIBLE_NOT_FOUND)
  assert.equal(occurrenceErrorMessage(notFound, 'resolucao'), RESPONSIBLE_NOT_FOUND)
  assert.match(occurrenceErrorMessage(notFound, 'carregar'), /não encontrada/)
})

test('nunca expõe detalhe técnico: 403, 422, 500 e rede viram texto amigável', () => {
  assert.match(occurrenceErrorMessage(apiError(403, { code: 'forbidden' }), 'carregar'), /perfil/)
  assert.match(
    occurrenceErrorMessage(apiError(422, { message: 'Dados inválidos.' }), 'resposta'),
    /Confira o texto/,
  )
  assert.equal(
    occurrenceErrorMessage(apiError(500, { message: 'stack trace' }), 'resposta'),
    GENERIC_ERROR,
  )
  assert.equal(occurrenceErrorMessage(new Error('ECONNREFUSED'), 'carregar'), GENERIC_ERROR)
})
