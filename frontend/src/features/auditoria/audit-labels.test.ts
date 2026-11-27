import assert from 'node:assert/strict'
import test from 'node:test'
import {
  auditActionLabel,
  auditActionLabels,
  auditActionOptions,
  auditGroupLabels,
  auditResourceLabel,
  auditResourceOptions,
} from './audit-labels.ts'
import { auditFilterError, noAuditFilters } from './auditoria-api.ts'

test('traduz as ações que a demonstração mostra', () => {
  assert.equal(auditActionLabel('condominio.aprovar'), 'Condomínio aprovado')
  assert.equal(auditActionLabel('seguranca.login'), 'Login')
  assert.equal(auditActionLabel('seguranca.login_falho'), 'Login recusado')
})

test('código sem tradução aparece como veio', () => {
  assert.equal(auditActionLabel('novo.evento'), 'novo.evento')
  assert.equal(auditResourceLabel('novo_recurso'), 'novo_recurso')
})

test('toda ação pertence a um grupo conhecido', () => {
  for (const code of Object.keys(auditActionLabels)) {
    assert.ok(auditGroupLabels[code.split('.')[0]], `grupo sem nome: ${code}`)
  }
})

test('as opções do filtro são valores que o servidor aceita', () => {
  const options = auditActionOptions()
  assert.equal(
    options.length,
    Object.keys(auditGroupLabels).length + Object.keys(auditActionLabels).length,
  )
  for (const { value } of options) {
    assert.equal(auditFilterError({ ...noAuditFilters, acao: value }), '', value)
  }
  assert.ok(options.some((option) => option.value === 'reserva.'))
})

test('tipos de recurso vêm em ordem alfabética do rótulo', () => {
  const labels = auditResourceOptions().map((option) => option.label)
  assert.deepEqual(
    labels,
    [...labels].sort((a, b) => a.localeCompare(b, 'pt-BR')),
  )
})
