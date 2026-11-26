import assert from 'node:assert/strict'
import { test } from 'node:test'
import { visibleResidentNavigation } from './resident-navigation.ts'

test('o menu inclui apenas abas permitidas em pelo menos uma unidade', () => {
  const menu = visibleResidentNavigation([{ abas: ['encomendas'] }, { abas: ['visitantes'] }])
  assert.deepEqual(menu.map((item) => item.key), ['overview', 'packages', 'visitors'])
  assert.deepEqual(visibleResidentNavigation([{ abas: [] }]).map((item) => item.key), ['overview'])
})
