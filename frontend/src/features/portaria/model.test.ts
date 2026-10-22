import assert from 'node:assert/strict'
import { test } from 'node:test'
import { closeVisit, confirmPackage, deliverPackage, enterVisitor, receivePackage, resolveAuthorization, seedDemo } from './model.ts'

const now = '2026-10-20T15:00:00.000Z'

test('recebimento exige foto, funcionário e destinatário da unidade selecionada', () => {
  const input = { unitId: 'a101', residentId: 'ana', employeeId: 'joana', description: 'Caixa', photo: 'data:image/png;base64,AA==' }
  assert.equal(receivePackage(input, now).ok, true)
  assert.equal(receivePackage({ ...input, photo: '' }, now).ok, false)
  assert.equal(receivePackage({ ...input, employeeId: '' }, now).ok, false)
  assert.equal(receivePackage({ ...input, residentId: 'julia' }, now).ok, false)
})

test('entrega aceita outro morador ativo da mesma unidade, preserva recebimento e impede repetição', () => {
  const parcel = seedDemo(now).packages[0]
  assert.equal(deliverPackage(parcel, 'julia', 'joana', now).ok, false)
  const result = deliverPackage(parcel, 'bruno', 'joana', now)
  assert.equal(result.ok, true)
  if (!result.ok) return
  assert.equal(result.value.status, 'pending_confirmation')
  assert.equal(result.value.receivedAt, parcel.receivedAt)
  assert.equal(result.value.receiverId, 'bruno')
  assert.equal(deliverPackage(result.value, 'bruno', 'joana', now).ok, false)
})

test('somente quem recebeu confirma a encomenda; pendência não expira sozinha', () => {
  const parcel = seedDemo(now).packages[1]
  assert.equal(confirmPackage(parcel, 'bruno', now).ok, false)
  const result = confirmPackage(parcel, 'ana', '2027-01-01T15:00:00.000Z')
  assert.equal(result.ok, true)
  if (!result.ok) return
  assert.equal(result.value.status, 'confirmed')
  assert.equal(result.value.deliveredAt, parcel.deliveredAt)
  assert.equal(confirmPackage(result.value, 'ana', now).ok, false)
})

test('autorização só vale para visitante, unidade e intervalo corretos', () => {
  const authorization = seedDemo(now).authorizations[0]
  assert.ok(resolveAuthorization([authorization], 'carlos', 'a101', now))
  assert.equal(resolveAuthorization([authorization], 'carlos', 'b202', now), undefined)
  assert.equal(resolveAuthorization([authorization], 'marina', 'a101', now), undefined)
  assert.equal(resolveAuthorization([authorization], 'carlos', 'a101', authorization.startsAt)?.id, authorization.id)
  assert.equal(resolveAuthorization([authorization], 'carlos', 'a101', authorization.endsAt), undefined)
  assert.equal(resolveAuthorization([authorization], 'carlos', 'a101', '2027-01-01T15:00:00.000Z'), undefined)
})

test('entrada não libera sem conferência e preserva a autorização válida para o período', () => {
  const state = seedDemo(now)
  const input = { visitorId: 'carlos', unitId: 'a101', employeeId: 'joana', identityChecked: true, authorizationId: state.authorizations[0].id }
  assert.equal(enterVisitor(state, { ...input, identityChecked: false }, now).ok, false)
  const result = enterVisitor(state, input, now)
  assert.equal(result.ok, true)
  if (!result.ok) return
  assert.deepEqual(result.value.authorizations, state.authorizations)
  assert.equal(result.value.visits[0].status, 'active')
  assert.equal(enterVisitor(result.value, input, now).ok, false)
})

test('após a saída, permite nova entrada no período; após expiração exige novo contato', () => {
  const state = seedDemo(now)
  const input = { visitorId: 'carlos', unitId: 'a101', employeeId: 'joana', identityChecked: true, authorizationId: state.authorizations[0].id }
  const first = enterVisitor(state, input, now)
  assert.equal(first.ok, true)
  if (!first.ok) return
  const exitedAt = '2026-10-20T15:10:00.000Z'
  const closed = closeVisit(first.value.visits[0], 'marcos', exitedAt)
  assert.equal(closed.ok, true)
  if (!closed.ok) return
  const afterExit = { ...first.value, visits: first.value.visits.map((visit) => visit.id === closed.value.id ? closed.value : visit) }
  const second = enterVisitor(afterExit, input, '2026-10-20T15:20:00.000Z')
  assert.equal(second.ok, true)
  if (!second.ok) return
  assert.equal(second.value.visits.filter((visit) => visit.visitorId === 'carlos').length, 2)
  assert.deepEqual(second.value.authorizations, state.authorizations)
  assert.equal(enterVisitor(afterExit, input, state.authorizations[0].endsAt).ok, false)
})

test('cadastro de visitante de outra unidade não permite entrada nem por contato externo', () => {
  const state = seedDemo(now)
  assert.equal(enterVisitor(state, { visitorId: 'carlos', unitId: 'b202', employeeId: 'joana', identityChecked: true, residentId: 'julia', channel: 'phone', response: 'authorized' }, now).ok, false)
})

test('contato externo exige resposta autorizada e morador da unidade; negativa não libera entrada', () => {
  const state = seedDemo(now)
  const input = { visitorId: 'marina', unitId: 'b202', employeeId: 'joana', identityChecked: true, response: 'authorized' as const, residentId: 'julia', channel: 'intercom' as const }
  assert.equal(enterVisitor(state, { ...input, response: 'denied' }, now).ok, false)
  assert.equal(enterVisitor(state, { ...input, response: 'no_answer' }, now).ok, false)
  assert.equal(enterVisitor(state, { ...input, residentId: 'ana' }, now).ok, false)
  assert.equal(enterVisitor(state, input, now).ok, true)
})
