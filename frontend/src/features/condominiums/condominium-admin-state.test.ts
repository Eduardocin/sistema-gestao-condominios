import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canResendRegistration } from './condominium-admin-state.ts'

test('só libera reenvio quando os dados e a estrutura foram salvos', () => {
  assert.equal(canResendRegistration(false, false), true)
  assert.equal(canResendRegistration(true, false), false)
  assert.equal(canResendRegistration(false, true), false)
  assert.equal(canResendRegistration(true, true), false)
})
