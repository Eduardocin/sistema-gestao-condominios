import { useCallback, useRef, useState } from 'react'
import {
  Badge,
  Button,
  ButtonLink,
  Calendar,
  Heading,
  Modal,
  Notice,
  Select,
  Text,
  TimeGrid,
} from '../../components'
import { CommunityLoadError, CommunityPageControls, ResidentCommunity } from './ResidentCommunity'
import type { CommunityUnit } from './ResidentCommunity'
import { communityDate, useCommunityQuery } from './resident-community-state'
import styles from './ResidentWorkspace.module.css'
import { communityError } from './resident-community-api'
import type {
  CommonArea,
  Reservation,
  ReservationSlot,
  ResidentCommunityClient,
} from './resident-community-api'

type UnitProps = { unit: CommunityUnit; api: ResidentCommunityClient }

const condoTime = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'America/Sao_Paulo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function ResidentReservePage() {
  return (
    <ResidentCommunity activeKey="reserve" title="Reservar área comum">
      {(unit, api) => <AvailableAreas unit={unit} api={api} />}
    </ResidentCommunity>
  )
}

function AvailableAreas({ unit, api }: UnitProps) {
  const [areaId, setAreaId] = useState('')
  const { result, reload } = useCommunityQuery(useCallback((signal) => api.areas(signal), [api]))
  if (result?.error) return <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>
  if (!result?.data) return <Text role="status">Carregando áreas comuns…</Text>
  const area = result.data.find(({ id }) => id === areaId) ?? result.data[0]
  if (!area) return <Notice>Nenhuma área disponível para reserva neste condomínio.</Notice>

  return (
    <>
      <Select
        label="Área comum"
        options={result.data.map(({ id, nome }) => ({ value: id, label: nome }))}
        value={area.id}
        onChange={(event) => setAreaId(event.target.value)}
      />
      <AreaSchedule key={area.id} area={area} unit={unit} api={api} />
    </>
  )
}

function AreaSchedule({ area, unit, api }: UnitProps & { area: CommonArea }) {
  const [today] = useState(() => new Date(`${condoTime.format(new Date()).slice(0, 10)}T12:00:00`))
  const [day, setDay] = useState(today)
  const [month, setMonth] = useState(() => dateKey(today).slice(0, 7))
  const [slot, setSlot] = useState<ReservationSlot>()
  const [pending, setPending] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const date = dateKey(day)
  const { result, reload } = useCommunityQuery(
    useCallback(
      (signal) => api.agenda(area.id, unit.id, date, signal),
      [api, area.id, unit.id, date],
    ),
  )
  const agenda = result?.data
  const calendar = useCommunityQuery(
    useCallback(
      (signal) => api.calendar(area.id, unit.id, month, signal),
      [api, area.id, unit.id, month],
    ),
  )
  const monthData = calendar.result?.data
  const dayMarkers: NonNullable<React.ComponentProps<typeof Calendar>['dayMarkers']> = {}
  if (monthData?.dias_disponiveis) {
    const available = new Set(monthData.dias_disponiveis)
    const booked = new Set(
      monthData.dias.filter((item) => item.tem_reserva_da_minha_unidade).map((item) => item.data),
    )
    const [year, monthNumber] = month.split('-').map(Number)
    for (let day = 1; day <= new Date(year, monthNumber, 0).getDate(); day += 1) {
      const date = `${month}-${String(day).padStart(2, '0')}`
      if (date < dateKey(today)) continue
      dayMarkers[date] = booked.has(date)
        ? { label: 'Sua reserva', variant: 'warning' }
        : available.has(date)
          ? { label: 'Com horários livres', variant: 'success' }
          : { label: 'Sem horários livres', variant: 'neutral' }
    }
  }

  async function confirmReservation() {
    if (!slot || submitting.current) return
    submitting.current = true
    setPending(true)
    try {
      await api.reserve(area.id, unit.id, date, slot.hora_inicio)
      setSuccess(true)
    } catch (failure) {
      setError(communityError(failure))
    } finally {
      setSlot(undefined)
      reload()
      calendar.reload()
      setPending(false)
      submitting.current = false
    }
  }

  return (
    <>
      <Text tone="secondary">
        Capacidade de {area.capacidade} pessoas · {area.abre_as} às {area.fecha_as}
      </Text>
      <div className={styles.content}>
        <Heading level={2}>Escolha uma data</Heading>
        <Calendar
          value={day}
          min={today}
          onMonthChange={(date) => setMonth(dateKey(date).slice(0, 7))}
          dayMarkers={dayMarkers}
          onChange={(value) => {
            setDay(value)
            setError('')
            setSuccess(false)
          }}
        />
        {monthData?.dias_disponiveis && (
          <Text size="sm" tone="secondary">
            ● Com horários livres · ○ Sua reserva · — Sem horários livres
          </Text>
        )}
        {calendar.result?.error && (
          <CommunityLoadError retry={calendar.reload}>{calendar.result.error}</CommunityLoadError>
        )}
      </div>
      {success && (
        <Notice tone="success" role="status">
          <div className={styles.actions}>
            Reserva confirmada.
            <ButtonLink to="/app/morador/reservas" variant="secondary" size="sm">
              Ver minhas reservas
            </ButtonLink>
          </div>
        </Notice>
      )}
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      <Heading level={2}>Horários de {communityDate(date)}</Heading>
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {!result && <Text role="status">Carregando horários…</Text>}
      {agenda?.unidade_ja_reservou && (
        <Notice>Sua unidade já tem uma reserva nesta área para esta data.</Notice>
      )}
      {agenda && !agenda.slots.length && <Text>Nenhum horário disponível para esta data.</Text>}
      {agenda && (
        <TimeGrid
          label={`Horários de ${area.nome}`}
          slots={agenda.slots.map(({ hora_inicio, estado }) => ({
            time: hora_inicio,
            status: estado === 'livre' ? 'free' : estado === 'da_minha_unidade' ? 'own' : 'other',
            caption:
              estado === 'bloqueado' ? 'Bloqueado' : estado === 'passado' ? 'Encerrado' : undefined,
            disabled: estado !== 'livre' || agenda.unidade_ja_reservou || pending,
          }))}
          onSlotClick={(time) => {
            setSuccess(false)
            setError('')
            setSlot(
              agenda.slots.find((item) => item.hora_inicio === time && item.estado === 'livre'),
            )
          }}
        />
      )}
      <Modal
        isOpen={Boolean(slot)}
        onClose={() => {
          if (!submitting.current) setSlot(undefined)
        }}
        title="Confirmar reserva"
      >
        {slot && (
          <div className={styles.content}>
            <Text>
              {area.nome} · {communityDate(date)} · {slot.hora_inicio} às {slot.hora_fim}
            </Text>
            <Text>Unidade {unit.identificacao}</Text>
            {area.regras && (
              <Notice title="Regras de uso">
                <span className={styles.preserveLines}>{area.regras}</span>
              </Notice>
            )}
            <div className={styles.actions}>
              <Button variant="secondary" disabled={pending} onClick={() => setSlot(undefined)}>
                Voltar
              </Button>
              <Button loading={pending} onClick={() => void confirmReservation()}>
                Confirmar reserva
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

export function ResidentReservationsPage() {
  return (
    <ResidentCommunity activeKey="reservations" title="Minhas reservas">
      {(unit, api) => <UnitReservations unit={unit} api={api} />}
    </ResidentCommunity>
  )
}

function UnitReservations({ unit, api }: UnitProps) {
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Reservation>()
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [pending, setPending] = useState(false)
  const submitting = useRef(false)
  const { result, reload } = useCommunityQuery(
    useCallback((signal) => api.reservations(unit.id, page, signal), [api, unit.id, page]),
  )
  const list = result?.data
  const now = condoTime.format(new Date())

  async function cancel() {
    if (!selected || submitting.current) return
    submitting.current = true
    setPending(true)
    setError('')
    try {
      await api.cancelReservation(selected.id)
      setSuccess(true)
    } catch (failure) {
      setError(communityError(failure))
    } finally {
      setSelected(undefined)
      reload()
      setPending(false)
      submitting.current = false
    }
  }

  return (
    <>
      <div className={styles.actions}>
        <ButtonLink to="/app/morador/areas-comuns">Reservar área comum</ButtonLink>
      </div>
      {success && (
        <Notice tone="success" role="status">
          Reserva cancelada.
        </Notice>
      )}
      {error && (
        <Notice tone="alert" role="alert">
          {error}
        </Notice>
      )}
      {result?.error && <CommunityLoadError retry={reload}>{result.error}</CommunityLoadError>}
      {!result && <Text role="status">Carregando reservas…</Text>}
      {list && !list.items.length && <Text>Nenhuma reserva encontrada para esta unidade.</Text>}
      {list?.items.map((reservation) => {
        const upcoming = `${reservation.data} ${reservation.hora_inicio}` > now
        const cancelled = reservation.status === 'cancelada'
        return (
          <article className={styles.listItem} key={reservation.id}>
            <Heading level={3}>{reservation.area.nome}</Heading>
            <Text>
              {communityDate(reservation.data)} · {reservation.hora_inicio} às{' '}
              {reservation.hora_fim}
            </Text>
            <div className={styles.actions}>
              <Badge variant={cancelled || !upcoming ? 'neutral' : 'success'}>
                {cancelled ? 'Cancelada' : upcoming ? 'Confirmada' : 'Horário iniciado'}
              </Badge>
              {upcoming && !cancelled && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setSuccess(false)
                    setError('')
                    setSelected(reservation)
                  }}
                >
                  Cancelar reserva
                </Button>
              )}
            </div>
            {reservation.cancelamento?.por === 'administracao' && (
              <Text size="sm">Cancelada pela administração. {reservation.cancelamento.motivo}</Text>
            )}
          </article>
        )
      })}
      {list && (
        <CommunityPageControls
          page={page}
          pages={Math.ceil(list.total / list.page_size)}
          onChange={setPage}
        />
      )}
      <Modal
        isOpen={Boolean(selected)}
        title="Cancelar reserva"
        onClose={() => {
          if (!submitting.current) setSelected(undefined)
        }}
      >
        {selected && (
          <div className={styles.content}>
            <Text>
              Cancelar a reserva de {selected.area.nome} em {communityDate(selected.data)}, às{' '}
              {selected.hora_inicio}?
            </Text>
            <div className={styles.actions}>
              <Button variant="secondary" disabled={pending} onClick={() => setSelected(undefined)}>
                Voltar
              </Button>
              <Button variant="alert" loading={pending} onClick={() => void cancel()}>
                Confirmar cancelamento
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
