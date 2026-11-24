import assert from 'node:assert/strict'
import { test } from 'node:test'
import axios from 'axios'
import { communityError, createResidentCommunityClient } from './resident-community-api.ts'

function fixture() {
  const requests: unknown[][] = []
  const http = axios.create({
    adapter: async (config) => {
      requests.push([
        config.method,
        config.url,
        config.params,
        config.data,
        config.headers.get('Content-Type'),
      ])
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
        data: { id: 'photo-1', url: 'http://files.test/photo' },
      }
    },
  })
  return { api: createResidentCommunityClient(http), requests }
}

test('consulta a agenda por unidade e reserva somente o horário inicial', async () => {
  const { api, requests } = fixture()
  await api.agenda('area/1', 'unit-1', '2026-11-30')
  await api.reserve('area/1', 'unit-1', '2026-11-30', '08:00')
  await api.cancelReservation('reserve-1')
  assert.deepEqual(
    requests.map((request) => request.slice(0, 4)),
    [
      [
        'get',
        '/areas-comuns/area%2F1/agenda',
        { unidade_id: 'unit-1', data: '2026-11-30' },
        undefined,
      ],
      [
        'post',
        '/reservas',
        undefined,
        JSON.stringify({
          area_id: 'area/1',
          unidade_id: 'unit-1',
          data: '2026-11-30',
          hora_inicio: '08:00',
        }),
      ],
      ['post', '/reservas/reserve-1/cancelamento', undefined, '{}'],
    ],
  )
})

test('envia foto binária e associa o ID retornado à ocorrência', async () => {
  const { api, requests } = fixture()
  const photo = new File(['test'], 'foto.png', { type: 'image/png' })
  const id = await api.uploadOccurrencePhoto('unit-1', photo)
  await api.openOccurrence('unit-1', 'Vazamento', 'No corredor', [id])
  assert.deepEqual(requests, [
    [
      'post',
      '/arquivos/ocorrencias',
      { nome: 'foto.png', unidade_id: 'unit-1' },
      photo,
      'image/png',
    ],
    [
      'post',
      '/ocorrencias',
      undefined,
      JSON.stringify({
        unidade_id: 'unit-1',
        titulo: 'Vazamento',
        detalhe: 'No corredor',
        anexos: ['photo-1'],
      }),
      'application/json',
    ],
  ])
})

test('mantém a orientação do servidor quando um horário deixa de estar disponível', () => {
  const error = new axios.AxiosError('Conflict', undefined, undefined, undefined, {
    status: 409,
    data: { error: { message: 'Este horário já está reservado.' } },
  } as never)
  assert.equal(communityError(error), 'Este horário já está reservado.')
})
