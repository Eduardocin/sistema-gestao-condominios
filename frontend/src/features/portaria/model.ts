/** Regras locais do protótipo. A API deverá repetir as validações com contexto autenticado. */
export type Result<T> = { ok: true; value: T } | { ok: false; error: string }
export const units = [{ id: 'a101', name: 'Bloco A · 101' }, { id: 'a102', name: 'Bloco A · 102' }, { id: 'b202', name: 'Bloco B · 202' }]
export const residents = [
  { id: 'ana', name: 'Ana Martins', unitId: 'a101' },
  { id: 'bruno', name: 'Bruno Martins', unitId: 'a101' },
  { id: 'pedro', name: 'Pedro Almeida', unitId: 'a102' },
  { id: 'julia', name: 'Júlia Costa', unitId: 'b202' },
]
export const employees = [{ id: 'joana', name: 'Joana Ribeiro' }, { id: 'marcos', name: 'Marcos Oliveira' }]
export const visitors = [{ id: 'carlos', name: 'Carlos Souza', unitId: 'a101' }, { id: 'marina', name: 'Marina Lima', unitId: 'b202' }, { id: 'rafael', name: 'Rafael Santos', unitId: 'a102' }]
export const parcelStatus = { awaiting: 'Aguardando retirada', pending_confirmation: 'Entregue, aguardando confirmação', confirmed: 'Retirada confirmada' }
export interface Parcel {
  id: string; unitId: string; residentId: string; description: string; photo: string
  status: keyof typeof parcelStatus; receivedAt: string; receivedBy: string
  receiverId?: string; deliveredAt?: string; deliveredBy?: string; confirmedAt?: string; confirmedBy?: string
}
export interface Authorization {
  id: string; visitorId: string; unitId: string; residentId: string; startsAt: string; endsAt: string
}
export type ContactResponse = 'authorized' | 'denied' | 'no_answer'
export interface Contact { residentId: string; channel: 'intercom' | 'phone'; response: ContactResponse }
export interface Visit {
  id: string; visitorId: string; unitId: string; status: 'active' | 'closed'; enteredAt: string; enteredBy: string
  authorizationId?: string; contact?: Contact; exitedAt?: string; exitedBy?: string
}
export interface Attempt { id: string; visitorId: string; unitId: string; employeeId: string; at: string; contact: Contact }
export interface DemoState { packages: Parcel[]; authorizations: Authorization[]; visits: Visit[]; attempts: Attempt[] }
export interface ReceiptInput { unitId: string; residentId: string; employeeId: string; description: string; photo: string }
export interface EntryInput {
  visitorId: string; unitId: string; employeeId: string; identityChecked: boolean; authorizationId?: string
  residentId?: string; channel?: Contact['channel']; response?: ContactResponse
}
const fail = (error: string): { ok: false; error: string } => ({ ok: false, error })
const employeeExists = (id: string) => employees.some((employee) => employee.id === id)
const belongsToUnit = (residentId: string, unitId: string) => residents.some((resident) => resident.id === residentId && resident.unitId === unitId)
export const personName = (id?: string) => [...residents, ...employees, ...visitors].find((person) => person.id === id)?.name ?? '—'
export const unitName = (id: string) => units.find((unit) => unit.id === id)?.name ?? '—'
export const formatTime = (date?: string) => date ? new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(date)) : '—'

export function seedDemo(now: string): DemoState {
  const before = (hours: number) => new Date(Date.parse(now) - hours * 3_600_000).toISOString()
  return {
    packages: [
      { id: 'ENC-001', unitId: 'a101', residentId: 'ana', description: 'Caixa pequena · Livraria', photo: '', status: 'awaiting', receivedAt: before(2), receivedBy: 'joana' },
      { id: 'ENC-002', unitId: 'a101', residentId: 'ana', description: 'Pacote · Loja online', photo: '', status: 'pending_confirmation', receivedAt: before(26), receivedBy: 'marcos', receiverId: 'ana', deliveredAt: before(20), deliveredBy: 'joana' },
      { id: 'ENC-003', unitId: 'b202', residentId: 'julia', description: 'Envelope · Correspondência', photo: '', status: 'confirmed', receivedAt: before(48), receivedBy: 'marcos', receiverId: 'julia', deliveredAt: before(30), deliveredBy: 'joana', confirmedAt: before(29), confirmedBy: 'julia' },
    ],
    authorizations: [{ id: 'AUT-001', visitorId: 'carlos', unitId: 'a101', residentId: 'ana', startsAt: before(1), endsAt: new Date(Date.parse(now) + 3_600_000).toISOString() }],
    visits: [{ id: 'VIS-001', visitorId: 'rafael', unitId: 'a102', status: 'active', enteredAt: before(1), enteredBy: 'marcos', contact: { residentId: 'pedro', channel: 'phone', response: 'authorized' } }],
    attempts: [],
  }
}

export function receivePackage(input: ReceiptInput, now: string): Result<Parcel> {
  if (!employeeExists(input.employeeId)) return fail('Selecione o funcionário responsável.')
  if (!belongsToUnit(input.residentId, input.unitId)) return fail('Selecione um destinatário com vínculo ativo na unidade.')
  if (!input.description.trim()) return fail('Informe uma descrição da encomenda.')
  if (!input.photo) return fail('Anexe uma foto antes de confirmar o recebimento.')
  return { ok: true, value: { id: `ENC-${crypto.randomUUID().slice(0, 8)}`, unitId: input.unitId, residentId: input.residentId, description: input.description.trim(), photo: input.photo, status: 'awaiting', receivedAt: now, receivedBy: input.employeeId } }
}

export function deliverPackage(parcel: Parcel, receiverId: string, employeeId: string, now: string): Result<Parcel> {
  if (parcel.status !== 'awaiting') return fail('Esta encomenda já foi entregue.')
  if (!employeeExists(employeeId)) return fail('Selecione o funcionário responsável.')
  if (!belongsToUnit(receiverId, parcel.unitId)) return fail('Quem retira precisa ter vínculo ativo com a unidade.')
  return { ok: true, value: { ...parcel, status: 'pending_confirmation', receiverId, deliveredAt: now, deliveredBy: employeeId } }
}

export function confirmPackage(parcel: Parcel, residentId: string, now: string): Result<Parcel> {
  if (parcel.status !== 'pending_confirmation') return fail('Esta encomenda não aguarda confirmação.')
  if (parcel.receiverId !== residentId || !belongsToUnit(residentId, parcel.unitId)) return fail('A confirmação deve ser feita pelo morador que recebeu a encomenda.')
  return { ok: true, value: { ...parcel, status: 'confirmed', confirmedAt: now, confirmedBy: residentId } }
}

export function resolveAuthorization(authorizations: Authorization[], visitorId: string, unitId: string, now: string) {
  return authorizations.find((authorization) => authorization.visitorId === visitorId && authorization.unitId === unitId && visitors.some((visitor) => visitor.id === visitorId && visitor.unitId === unitId) && belongsToUnit(authorization.residentId, unitId) && Date.parse(authorization.startsAt) <= Date.parse(now) && Date.parse(now) < Date.parse(authorization.endsAt))
}

export function enterVisitor(state: DemoState, input: EntryInput, now: string): Result<DemoState> {
  if (!employeeExists(input.employeeId)) return fail('Selecione o funcionário responsável.')
  if (!visitors.some((visitor) => visitor.id === input.visitorId && visitor.unitId === input.unitId)) return fail('Selecione um visitante cadastrado para esta unidade de destino.')
  if (!input.identityChecked) return fail('Confira a identidade do visitante antes de liberar a entrada.')
  if (state.visits.some((visit) => visit.visitorId === input.visitorId && visit.status === 'active')) return fail('Este visitante já tem uma visita em andamento. Registre a saída antes de uma nova entrada.')
  const authorization = resolveAuthorization(state.authorizations, input.visitorId, input.unitId, now)
  if (input.authorizationId && input.authorizationId !== authorization?.id) return fail('A autorização não está mais válida. Consulte o morador.')
  if (!input.authorizationId && (input.response !== 'authorized' || !input.residentId || !belongsToUnit(input.residentId, input.unitId) || !['intercom', 'phone'].includes(input.channel ?? ''))) return fail('A entrada depende de autorização do morador. Sem resposta ou com negativa, não libere o acesso.')
  const visit: Visit = { id: `VIS-${crypto.randomUUID().slice(0, 8)}`, visitorId: input.visitorId, unitId: input.unitId, status: 'active', enteredAt: now, enteredBy: input.employeeId, ...(input.authorizationId ? { authorizationId: input.authorizationId } : { contact: { residentId: input.residentId!, channel: input.channel!, response: 'authorized' } }) }
  return { ok: true, value: { ...state, visits: [visit, ...state.visits] } }
}

export function closeVisit(visit: Visit, employeeId: string, now: string): Result<Visit> {
  if (visit.status !== 'active') return fail('Esta visita já foi encerrada.')
  if (!employeeExists(employeeId)) return fail('Selecione o funcionário responsável.')
  return { ok: true, value: { ...visit, status: 'closed', exitedAt: now, exitedBy: employeeId } }
}
