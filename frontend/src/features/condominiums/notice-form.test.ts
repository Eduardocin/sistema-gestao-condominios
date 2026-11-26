import assert from 'node:assert/strict'
import { test } from 'node:test'
import { NOTICE_PERIOD_ERROR, buildNoticePayload, localDate } from './notice-form.ts'

const base = {
  titulo: '  Manutenção  ',
  texto: ' Sem água na quinta. ',
  inicio: '2026-12-01T08:00',
  fim: '2026-12-02T08:00',
  importante: true,
  responsavelId: 'resp-1',
}

test('monta o payload com texto aparado, datas em ISO e responsável', () => {
  const result = buildNoticePayload(base)
  assert.ok(result.ok)
  assert.equal(result.payload.titulo, 'Manutenção')
  assert.equal(result.payload.texto, 'Sem água na quinta.')
  assert.equal(result.payload.inicio_em, new Date('2026-12-01T08:00').toISOString())
  assert.equal(result.payload.fim_em, new Date('2026-12-02T08:00').toISOString())
  assert.equal(result.payload.importante, true)
  assert.equal(result.payload.responsavel_id, 'resp-1')
})

test('recusa término igual ou anterior ao início e datas vazias ou inválidas', () => {
  for (const override of [
    { fim: base.inicio },
    { fim: '2026-11-30T08:00' },
    { inicio: '' },
    { fim: '' },
    { inicio: 'lixo' },
  ]) {
    const result = buildNoticePayload({ ...base, ...override })
    assert.deepEqual(result, { ok: false, message: NOTICE_PERIOD_ERROR })
  }
})

test('localDate devolve o valor do campo sem perder o instante', () => {
  const iso = '2026-12-01T11:30:00.000Z'
  const field = localDate(iso)
  assert.match(field, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  assert.equal(new Date(field).toISOString(), iso)
})
