import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  DEFAULT_FILTERS,
  buildOccurrenceParams,
  openingAttachments,
  validateReply,
  validateResolution,
} from './occurrence-form.ts'

const active = ['resp-1', 'resp-2']

test('resposta válida vira payload com texto aparado e responsável', () => {
  assert.deepEqual(
    validateReply({ texto: '  Equipe acionada.  ', responsavelId: 'resp-1' }, active),
    {
      ok: true,
      payload: { texto: 'Equipe acionada.', responsavel_id: 'resp-1' },
    },
  )
})

test('resposta exige texto de 1 a 2000 caracteres depois do trim', () => {
  const empty = validateReply({ texto: '   ', responsavelId: 'resp-1' }, active)
  assert.ok(!empty.ok && empty.errors.texto && !empty.errors.responsavel)
  assert.equal(
    validateReply({ texto: 'x'.repeat(2001), responsavelId: 'resp-1' }, active).ok,
    false,
  )
  assert.ok(validateReply({ texto: ` ${'x'.repeat(2000)} `, responsavelId: 'resp-1' }, active).ok)
  // Conta code points como o Python: 2000 emojis cabem, apesar de length = 4000.
  assert.ok(validateReply({ texto: '🔧'.repeat(2000), responsavelId: 'resp-1' }, active).ok)
})

test('resposta e resolução exigem responsável ativo', () => {
  for (const validate of [validateReply, validateResolution]) {
    const missing = validate({ texto: 'ok', responsavelId: '' }, active)
    assert.ok(!missing.ok && missing.errors.responsavel)
    const inactive = validate({ texto: 'ok', responsavelId: 'desligado' }, active)
    assert.ok(!inactive.ok && inactive.errors.responsavel)
    assert.equal(validate({ texto: 'ok', responsavelId: 'resp-1' }, []).ok, false)
  }
})

test('resolução aceita texto vazio e omite o campo no corpo', () => {
  assert.deepEqual(validateResolution({ texto: '   ', responsavelId: 'resp-2' }, active), {
    ok: true,
    payload: { responsavel_id: 'resp-2' },
  })
  assert.deepEqual(
    validateResolution({ texto: ' Trocado o cano. ', responsavelId: 'resp-2' }, active),
    {
      ok: true,
      payload: { texto: 'Trocado o cano.', responsavel_id: 'resp-2' },
    },
  )
})

test('resolução recusa texto acima de 2000 caracteres', () => {
  const result = validateResolution({ texto: 'x'.repeat(2001), responsavelId: 'resp-1' }, active)
  assert.ok(!result.ok && result.errors.texto)
  assert.ok(validateResolution({ texto: 'x'.repeat(2000), responsavelId: 'resp-1' }, active).ok)
})

test('filtros padrão listam as em aberto, sem parâmetro vazio', () => {
  assert.deepEqual(buildOccurrenceParams(DEFAULT_FILTERS), {
    ok: true,
    params: { page: 1, page_size: 20, status: 'em_aberto' },
  })
  assert.deepEqual(buildOccurrenceParams({ ...DEFAULT_FILTERS, status: '' }, 2), {
    ok: true,
    params: { page: 2, page_size: 20 },
  })
})

test('filtros incluem período e unidade com os nomes da API', () => {
  assert.deepEqual(
    buildOccurrenceParams(
      { status: 'resolvida', de: '2026-11-01', ate: '2026-11-30', unidadeId: 'u-1' },
      1,
    ),
    {
      ok: true,
      params: {
        page: 1,
        page_size: 20,
        status: 'resolvida',
        de: '2026-11-01',
        ate: '2026-11-30',
        unidade_id: 'u-1',
      },
    },
  )
})

test('período exige datas válidas e início igual ou anterior ao fim', () => {
  assert.ok(buildOccurrenceParams({ ...DEFAULT_FILTERS, de: '2026-11-10', ate: '2026-11-10' }).ok)
  assert.equal(
    buildOccurrenceParams({ ...DEFAULT_FILTERS, de: '2026-11-11', ate: '2026-11-10' }).ok,
    false,
  )
  for (const value of ['2026-02-30', '10/11/2026']) {
    assert.equal(buildOccurrenceParams({ ...DEFAULT_FILTERS, ate: value }).ok, false, value)
  }
})

test('página e tamanho ficam dentro dos limites da API', () => {
  const result = buildOccurrenceParams(DEFAULT_FILTERS, 0, 500)
  assert.ok(result.ok)
  assert.equal(result.params.page, 1)
  assert.equal(result.params.page_size, 100)
})

test('anexos da abertura excluem os que pertencem a interações', () => {
  const anexos = [
    { arquivo_id: 'a', interacao_id: null },
    { arquivo_id: 'b', interacao_id: 'i-1' },
  ]
  assert.deepEqual(
    openingAttachments(anexos).map((anexo) => anexo.arquivo_id),
    ['a'],
  )
})
