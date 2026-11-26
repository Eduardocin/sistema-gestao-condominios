import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  desvinculacaoErrorMessage,
  desvinculacaoPath,
  desvinculacaoSuccessMessage,
} from './desvinculacao.ts'

test('monta a rota de desvinculação com os IDs codificados', () => {
  assert.equal(desvinculacaoPath('u 1', 'm/2'), '/unidades/u%201/moradores/m%2F2/desvinculacao')
})

test('409 ultimo_usuarios explica como resolver', () => {
  const msg = desvinculacaoErrorMessage({ status: 409, reason: 'ultimo_usuarios' })
  assert.match(msg, /ao menos um morador com acesso a Usuários/)
})

test('403 e 404 têm mensagens próprias e o resto cai na genérica', () => {
  assert.match(desvinculacaoErrorMessage({ status: 403 }), /si mesmo/)
  assert.match(desvinculacaoErrorMessage({ status: 404 }), /já foi desvinculado/)
  assert.match(desvinculacaoErrorMessage({ status: 500 }), /Tente novamente/)
  assert.match(desvinculacaoErrorMessage({}), /Tente novamente/)
})

test('409 sem o motivo esperado não promete o que não sabe', () => {
  assert.match(desvinculacaoErrorMessage({ status: 409, reason: 'outro' }), /Tente novamente/)
})

test('avisa da chave revogada só quando houve revogação', () => {
  assert.match(desvinculacaoSuccessMessage('Ana', true), /chave de acesso.*revogada/)
  assert.doesNotMatch(desvinculacaoSuccessMessage('Ana', false), /chave/)
})
