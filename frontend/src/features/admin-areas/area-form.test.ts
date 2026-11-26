import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  FULL_HOURS,
  PHOTO_MAX_BYTES,
  buildAreaPayload,
  photoError,
  validateAreaForm,
} from './area-form.ts'
import type { AreaFormValues } from './area-form.ts'

const photo = { name: 'salao.JPG', type: 'image/jpeg', size: 1024 }
const base: AreaFormValues = {
  nome: '  Salão de festas  ',
  regras: '  Silêncio após as 22h.  ',
  abreAs: '08:00',
  fechaAs: '22:00',
  capacidade: '40',
  foto: photo,
}

function errorsOf(values: Partial<AreaFormValues>) {
  const result = validateAreaForm({ ...base, ...values })
  assert.equal(result.ok, false)
  return result.ok ? {} : result.errors
}

test('aceita o formulário válido e monta o payload com texto aparado e capacidade numérica', () => {
  const result = validateAreaForm(base)
  assert.ok(result.ok)
  assert.deepEqual(buildAreaPayload(result.fields, 'foto-1'), {
    nome: 'Salão de festas',
    regras: 'Silêncio após as 22h.',
    abre_as: '08:00',
    fecha_as: '22:00',
    capacidade: 40,
    foto_arquivo_id: 'foto-1',
  })
})

test('regras em branco viram null', () => {
  const result = validateAreaForm({ ...base, regras: '   ' })
  assert.ok(result.ok)
  assert.equal(result.fields.regras, null)
})

test('nome precisa ter de 1 a 100 caracteres depois do trim', () => {
  assert.ok(errorsOf({ nome: '   ' }).nome)
  assert.ok(errorsOf({ nome: 'a'.repeat(101) }).nome)
  assert.ok(validateAreaForm({ ...base, nome: ` ${'a'.repeat(100)} ` }).ok)
  // Conta code points como o Python: 100 emojis cabem, apesar de length = 200.
  assert.ok(validateAreaForm({ ...base, nome: '🏊'.repeat(100) }).ok)
})

test('regras aceitam até 2000 caracteres', () => {
  assert.ok(validateAreaForm({ ...base, regras: 'r'.repeat(2000) }).ok)
  assert.ok(errorsOf({ regras: 'r'.repeat(2001) }).regras)
})

test('horários só em hora cheia HH:00, entre 00:00 e 23:00', () => {
  for (const hour of ['08:30', '8:00', '24:00', '', 'lixo']) {
    assert.ok(errorsOf({ abreAs: hour }).abre_as, hour)
    assert.ok(errorsOf({ fechaAs: hour }).fecha_as, hour)
  }
  assert.equal(FULL_HOURS.length, 24)
  assert.equal(FULL_HOURS[0], '00:00')
  assert.equal(FULL_HOURS[23], '23:00')
})

test('fechamento precisa ser depois da abertura, com janela de pelo menos 1 hora', () => {
  assert.ok(errorsOf({ abreAs: '10:00', fechaAs: '10:00' }).fecha_as)
  assert.ok(errorsOf({ abreAs: '22:00', fechaAs: '08:00' }).fecha_as)
  assert.ok(validateAreaForm({ ...base, abreAs: '10:00', fechaAs: '11:00' }).ok)
  assert.ok(validateAreaForm({ ...base, abreAs: '00:00', fechaAs: '23:00' }).ok)
})

test('capacidade é inteiro de 1 a 32767', () => {
  for (const value of ['0', '-1', '32768', '4.5', '', 'abc', '1e3']) {
    assert.ok(errorsOf({ capacidade: value }).capacidade, value)
  }
  assert.ok(validateAreaForm({ ...base, capacidade: '1' }).ok)
  assert.ok(validateAreaForm({ ...base, capacidade: ' 32767 ' }).ok)
})

test('foto é obrigatória na criação e opcional na edição (mantém a atual)', () => {
  assert.ok(errorsOf({ foto: null }).foto)
  const editing = validateAreaForm({ ...base, foto: null, fotoAtualId: 'foto-atual' })
  assert.ok(editing.ok)
  assert.equal(buildAreaPayload(editing.fields, 'foto-atual').foto_arquivo_id, 'foto-atual')
})

test('foto aceita só JPG, PNG e WebP não vazios de até 5 MB, com extensão coerente', () => {
  assert.equal(photoError(photo), null)
  assert.equal(photoError({ name: 'a.webp', type: 'image/webp', size: PHOTO_MAX_BYTES }), null)
  assert.ok(photoError({ name: 'a.gif', type: 'image/gif', size: 10 }))
  assert.ok(photoError({ name: 'a.png', type: 'image/jpeg', size: 10 }))
  assert.ok(photoError({ name: 'a.png', type: 'image/png', size: 0 }))
  assert.ok(photoError({ name: 'a.png', type: 'image/png', size: PHOTO_MAX_BYTES + 1 }))
  assert.ok(errorsOf({ foto: { name: 'a.pdf', type: 'application/pdf', size: 10 } }).foto)
})

test('reúne todos os erros de uma vez', () => {
  const errors = errorsOf({ nome: '', abreAs: '08:15', capacidade: '0', foto: null })
  assert.deepEqual(Object.keys(errors).sort(), ['abre_as', 'capacidade', 'foto', 'nome'])
})
