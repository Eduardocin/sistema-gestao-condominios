import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { saveFlash, takeFlash } from './flash.ts'

const original = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')

function stubStorage(storage: Partial<Storage>) {
  Object.defineProperty(globalThis, 'sessionStorage', { value: storage, configurable: true })
}

afterEach(() => {
  if (original) Object.defineProperty(globalThis, 'sessionStorage', original)
  else Reflect.deleteProperty(globalThis, 'sessionStorage')
})

test('a mensagem guardada é lida uma única vez', () => {
  const data = new Map<string, string>()
  stubStorage({
    setItem: (key, value) => void data.set(key, value),
    getItem: (key) => data.get(key) ?? null,
    removeItem: (key) => void data.delete(key),
  })
  saveFlash('k', 'Salvo.')
  assert.equal(takeFlash('k'), 'Salvo.')
  assert.equal(takeFlash('k'), '')
})

test('sem sessionStorage a leitura devolve vazio e a gravação não lança', () => {
  stubStorage({
    setItem: () => {
      throw new Error('bloqueado')
    },
    getItem: () => {
      throw new Error('bloqueado')
    },
  })
  assert.doesNotThrow(() => saveFlash('k', 'x'))
  assert.equal(takeFlash('k'), '')
})
