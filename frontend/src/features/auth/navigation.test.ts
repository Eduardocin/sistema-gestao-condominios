import assert from 'node:assert/strict'
import { test } from 'node:test'
import { homePath, condominiumNotice } from './navigation.ts'
import type { Identity } from './types.ts'

const base: Identity = { usuario: { id: 'u', nome: 'Ana Exemplo', email: 'ana@example.com' }, condominio: null, unidades: [], administrador_plataforma: false }
const condominium = { id: 'c', nome: 'Aurora', perfil: 'morador' as const, status: 'ativo' as const }

test('destinos usam o contexto validado, separam seleção e não abrem operações indisponíveis', () => {
  assert.equal(homePath(base, []), '/app/sem-condominio')
  assert.equal(homePath(base, [condominium, { ...condominium, id: 'b' }]), '/selecionar-condominio')
  assert.equal(homePath({ ...base, administrador_plataforma: true }, []), '/app/plataforma')
  assert.equal(homePath({ ...base, condominio: condominium }, []), '/app/morador')
  assert.equal(homePath({ ...base, condominio: { ...condominium, perfil: 'funcionario' } }, []), '/app/portaria')
  assert.equal(homePath({ ...base, condominio: { ...condominium, perfil: 'administracao' } }, []), '/app/administracao')
  assert.equal(homePath({ ...base, condominio: { ...condominium, status: 'desativado' } }, []), '/app/sem-condominio')
})

test('restaurar sessão não abre operações para condomínio pendente, rejeitado ou desativado', () => {
  for (const status of ['pendente', 'rejeitado', 'desativado'] as const) {
    for (const perfil of ['morador', 'funcionario', 'administracao'] as const) {
      assert.equal(homePath({ ...base, condominio: { ...condominium, status, perfil } }, [condominium]), '/app/sem-condominio')
    }
  }
})

test('mensagens de acesso distinguem análise, rejeição, desativação e falta de vínculo', () => {
  assert.match(condominiumNotice('pendente').title, /análise/)
  assert.match(condominiumNotice('rejeitado').title, /rejeitado/)
  assert.match(condominiumNotice('desativado').title, /desativado/)
  assert.match(condominiumNotice(undefined).message, /vínculo/)
})
