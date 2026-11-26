import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { createCondominiumAdminApi } from './condominium-admin-api.ts'

function fixture() {
  const requests: { method?: string; url?: string; data?: unknown }[] = []
  const http = axios.create({
    adapter: async (config) => {
      requests.push({ method: config.method, url: config.url, data: config.data })
      return { status: 200, statusText: 'OK', headers: {}, config, data: {} }
    },
  })
  return { api: createCondominiumAdminApi(http), requests }
}

test('consulta os dados e a estrutura do condomínio autenticado', async () => {
  const { api, requests } = fixture()
  await api.condominium()
  await api.structure()

  assert.deepEqual(
    requests.map(({ method, url }) => [method, url]),
    [
      ['get', '/condominio'],
      ['get', '/condominio/estrutura'],
    ],
  )
})

test('envia responsável nas edições sem permitir que o cliente escolha o condomínio', async () => {
  const { api, requests } = fixture()
  await api.updateCondominium({
    nome: 'Residencial Aurora',
    cnpj: '12345678000199',
    endereco: {
      cep: '50000000',
      logradouro: 'Rua Central',
      numero: '10',
      complemento: null,
      bairro: 'Centro',
      cidade: 'Recife',
      uf: 'PE',
    },
    responsavel_id: 'responsible-1',
  })
  await api.updateBlock('block/1', { nome: 'Torre A', responsavel_id: 'responsible-1' })
  await api.createFloor('block/1', {
    nome: 'Térreo',
    ordem: 0,
    responsavel_id: 'responsible-1',
  })

  assert.deepEqual(requests, [
    {
      method: 'put',
      url: '/condominio',
      data: JSON.stringify({
        nome: 'Residencial Aurora',
        cnpj: '12345678000199',
        endereco: {
          cep: '50000000',
          logradouro: 'Rua Central',
          numero: '10',
          complemento: null,
          bairro: 'Centro',
          cidade: 'Recife',
          uf: 'PE',
        },
        responsavel_id: 'responsible-1',
      }),
    },
    {
      method: 'put',
      url: '/estrutura/blocos/block%2F1',
      data: JSON.stringify({ nome: 'Torre A', responsavel_id: 'responsible-1' }),
    },
    {
      method: 'post',
      url: '/estrutura/blocos/block%2F1/andares',
      data: JSON.stringify({ nome: 'Térreo', ordem: 0, responsavel_id: 'responsible-1' }),
    },
  ])
  assert.ok(requests.every(({ data }) => !String(data).includes('condominio_id')))
})

test('gerencia conta compartilhada e responsáveis nos contratos existentes', async () => {
  const { api, requests } = fixture()
  await api.responsibles()
  await api.createResponsible('Ana Silva')
  await api.updateResponsible('responsible/1', 'Ana Souza')
  await api.deactivateResponsible('responsible/1')
  await api.sharedAccount()
  await api.saveSharedAccount({
    login: 'portaria@example.com',
    senha: 'senha-segura-123',
    responsavel_id: 'responsible-1',
  })

  assert.deepEqual(
    requests.map(({ method, url, data }) => [method, url, data]),
    [
      ['get', '/responsaveis-administracao', undefined],
      ['post', '/responsaveis-administracao', JSON.stringify({ nome: 'Ana Silva' })],
      ['put', '/responsaveis-administracao/responsible%2F1', JSON.stringify({ nome: 'Ana Souza' })],
      ['post', '/responsaveis-administracao/responsible%2F1/desativacao', '{}'],
      ['get', '/conta-funcionarios', undefined],
      [
        'put',
        '/conta-funcionarios',
        JSON.stringify({
          login: 'portaria@example.com',
          senha: 'senha-segura-123',
          responsavel_id: 'responsible-1',
        }),
      ],
    ],
  )
})

test('envia reenvio e inclusão de itens sem transmitir o condomínio pelo cliente', async () => {
  const { api, requests } = fixture()
  await api.resendRegistration('responsible-1')
  await api.createUnit('floor/1', {
    identificacao: '101',
    responsavel_id: 'responsible-1',
  })
  await api.setStructureStatus('unidades', 'unit/1', false, 'responsible-1')

  assert.deepEqual(
    requests.map(({ method, url, data }) => [method, url, data]),
    [
      ['post', '/condominio/reenvio', JSON.stringify({ responsavel_id: 'responsible-1' })],
      [
        'post',
        '/estrutura/andares/floor%2F1/unidades',
        JSON.stringify({ identificacao: '101', responsavel_id: 'responsible-1' }),
      ],
      [
        'post',
        '/estrutura/unidades/unit%2F1/desativacao',
        JSON.stringify({ responsavel_id: 'responsible-1' }),
      ],
    ],
  )
})

test('altera status apenas pelo recurso da plataforma e sem corpo de cliente', async () => {
  const { api, requests } = fixture()
  await api.setCondominiumStatus('condo/1', false)
  await api.setCondominiumStatus('condo/1', true)

  assert.deepEqual(
    requests.map(({ method, url, data }) => [method, url, data]),
    [
      ['post', '/plataforma/condominios/condo%2F1/desativacao', '{}'],
      ['post', '/plataforma/condominios/condo%2F1/reativacao', '{}'],
    ],
  )
})
